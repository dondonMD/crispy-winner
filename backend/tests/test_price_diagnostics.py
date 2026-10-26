"""Bounded local diagnostics. All prices/accounts/HTTP responses are synthetic."""

import asyncio
from datetime import datetime, timezone
import json
import time
from unittest.mock import AsyncMock
import httpx
import pytest
from solders.pubkey import Pubkey
from backend.app.db import Database, Base, EvidenceRun
from backend.app.price_diagnostics import PriceDiagnostics
from backend.app.early_prices import PriceResearch, reserve_state
from backend.app.early_edge_runtime import UsdReference
from backend.app.early_edge_quotes import WSOL, USDC, QuoteUnavailable
from backend.app.engine import RadarEngine
from backend.app.config import Settings
from backend.app.domain import MarketEvent
from backend.tests.test_early_prices import MINT, ADDRESS, NOW, inputs, mark, tokens, projections, refs, state


def diagnostics(tmp_path):
    db = Database(tmp_path / "diag.db")
    Base.metadata.create_all(db.engine)
    return db, PriceDiagnostics(db, "synthetic")


def receipt(db, diag):
    with db.sessions() as sql:
        return json.loads(sql.get(EvidenceRun, diag.key).payload)


@pytest.mark.parametrize(
    "fault,expected",
    [
        ("identity", "MINT_IDENTITY"),
        ("slot", "STATE_CONTEXT"),
        ("layout", "CURVE_ACCOUNT_LAYOUT"),
        ("mint", "MINT_METADATA"),
        ("quote", "QUOTE_METADATA"),
        ("decimals", "UNVERIFIED_DECIMALS"),
    ],
)
def test_exact_pre_mark_reasons(fault, expected):
    curve, mint, quotes = inputs()
    address, slot = ADDRESS, 123
    if fault == "identity":
        address = str(Pubkey.new_unique())
    if fault == "slot":
        slot = 0
    if fault == "layout":
        curve["owner"] = "INVALID"
    if fault == "mint":
        mint = None
    if fault == "quote":
        quotes[WSOL] = None
    if fault == "decimals":
        quotes[WSOL] = inputs()[1]
    with pytest.raises(QuoteUnavailable) as caught:
        reserve_state(MINT, address, curve, mint, quotes, slot, NOW - 0.1, NOW)
    assert caught.value.reason == expected


@pytest.mark.parametrize(
    "code",
    [
        "UNSUPPORTED_QUOTE",
        "UNSUPPORTED_CURVE_STATE",
        "INVALID_RESERVES",
        "STATE_CONTEXT",
        "NO_VERIFIED_CURVE",
        "MINT_METADATA",
    ],
)
async def test_provider_reason_survives_durably_but_not_in_curve_evidence(tmp_path, code):
    e = RadarEngine(Settings(), tmp_path / "engine.db")
    t = type("Candidate", (), {"mint": MINT, "last_curve_attempt": 0})()
    e.rpc.curve_progress_batch = AsyncMock(
        return_value={MINT: dict(curve_progress=5, data_quality="VERIFIED", price_status=code)}
    )
    await e.poll_curves([t], "hot", 25)
    diag = e.price_research.diagnostics
    r = receipt(e.db, diag)
    assert r["counts"]["ATTEMPTED"] == r["counts"][code] == 1 and r["in_progress"] == 0
    event = e.queue.drain()[0]
    assert event.evidence["data_quality"] == "VERIFIED" and "price_status" not in event.evidence
    assert e.price_reference is None
    await e.stop()


@pytest.mark.parametrize(
    "failure,code",
    [
        (TimeoutError(), "RPC_TIMEOUT"),
        (RuntimeError(), "RPC_UNAVAILABLE"),
        (ValueError(), "RPC_INVALID_RESPONSE"),
    ],
)
async def test_rpc_errors_and_cancellation_are_durable(tmp_path, failure, code):
    e = RadarEngine(Settings(), tmp_path / "rpc.db")
    t = type("Candidate", (), {"mint": MINT, "last_curve_attempt": 0})()
    e.rpc.curve_progress_batch = AsyncMock(side_effect=failure)
    if isinstance(failure, TimeoutError):
        with pytest.raises(TimeoutError):
            await e.poll_curves([t], "hot", 25)
    else:
        await e.poll_curves([t], "hot", 25)
    r = receipt(e.db, e.price_research.diagnostics)
    assert r["counts"][code] == 1 and r["in_progress"] == 0
    await e.stop()


async def test_cancelled_rpc_and_shutdown(tmp_path):
    e = RadarEngine(Settings(), tmp_path / "cancel.db")
    entered = asyncio.Event()

    async def block(*args, **kwargs):
        entered.set()
        await asyncio.Event().wait()

    e.rpc.curve_progress_batch = block
    t = type("Candidate", (), {"mint": MINT, "last_curve_attempt": 0})()
    task = asyncio.create_task(e.poll_curves([t], "hot", 25))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    diag = e.price_research.diagnostics
    assert receipt(e.db, diag)["counts"]["RPC_CANCELLED"] == 1
    await e.stop()
    reader = Database(tmp_path / "cancel.db")
    assert receipt(reader, diag)["status"] == "STOPPED"
    reader.engine.dispose()


@pytest.mark.parametrize("product,mint", [("SOL-USD", WSOL), ("USDCUSD", USDC)])
@pytest.mark.parametrize("case", ["ok", "http", "schema", "stale", "cancel", "timeout", "rate", "json"])
async def test_fx_lifecycle(product, mint, case, tmp_path):
    db, diag = diagnostics(tmp_path)
    entered = asyncio.Event()
    now = time.time()

    async def respond(request):
        entered.set()
        if case == "cancel":
            await asyncio.Event().wait()
        if case == "timeout":
            raise httpx.ReadTimeout("synthetic secret must not survive")
        if case == "rate":
            return httpx.Response(429)
        if case == "json":
            return httpx.Response(200, content=b"invalid")
        if case == "http":
            return httpx.Response(500, json={"error": "synthetic"})
        if case == "schema":
            return httpx.Response(200, json={})
        stamp = now - 30 if case == "stale" else now
        data = (
            dict(price="100", time=datetime.fromtimestamp(stamp, timezone.utc).isoformat())
            if mint == WSOL
            else dict(error=[], result={"USDCUSD": [["1.001", "1", stamp]], "last": "synthetic"})
        )
        return httpx.Response(200, json=data)

    ref = UsdReference(httpx.AsyncClient(transport=httpx.MockTransport(respond)), diagnostics=diag)
    task = asyncio.create_task(ref.refresh({mint}, max_products=1))
    if case == "cancel":
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        await task
    row = receipt(db, diag)["fx"][product]
    c = row["counts"]
    assert c["attempted"] == c["http_started"] == 1
    expected = {
        "ok": "usable",
        "http": "request_failed",
        "schema": "validation_failed",
        "stale": "stale_rejected",
        "cancel": "cancelled",
        "timeout": "request_failed",
        "rate": "request_failed",
        "json": "validation_failed",
    }[case]
    assert c[expected] == 1
    assert row["freshness"] == ("FRESH" if case == "ok" else "UNAVAILABLE")
    if case == "ok":
        assert diag.snapshot(now + 40)["fx"][product]["freshness"] == "STALE"
        assert row["reference"]["published_at"] == pytest.approx(now)
    await ref.close()
    db.engine.dispose()


def test_signal_baseline_and_later_mark_not_backfilled(tmp_path):
    db, _ = diagnostics(tmp_path)
    p = PriceResearch(db, "synthetic")
    p.tick(tokens(), projections(), NOW)
    frozen = db.rows("v21_price_signal")[0]
    p.accept(mark(NOW + 1), NOW + 1, persist=True)
    p.diagnostics.flush()
    review = receipt(db, p.diagnostics)["reviews"][0]
    assert review["baseline_status"] == "NO_ACQUISITION_ATTEMPTED"
    assert review["later_mark_not_backfilled"]
    assert db.rows("v21_price_signal")[0] == frozen and frozen["baseline"] is None
    p.tick(tokens(), {}, NOW + 30)
    assert p.diagnostics.counts["EXPIRED"] == 1
    p.tick(tokens(), {}, NOW + 31)
    assert p.diagnostics.counts["EXPIRED"] == 1
    p.stop()
    db.engine.dispose()


def test_persistence_failure_not_falsely_called_persisted(tmp_path, monkeypatch):
    db, _ = diagnostics(tmp_path)
    p = PriceResearch(db, "synthetic")

    def fail(*args, **kwargs):
        raise RuntimeError("secret URL must never be retained")

    monkeypatch.setattr(db, "add", fail)
    with pytest.raises(RuntimeError):
        p.accept(mark(), NOW, persist=True)
    r = receipt(db, p.diagnostics)
    assert r["counts"]["SUBMITTED"] == r["counts"]["NOT_PERSISTED"] == 1
    assert not r["counts"].get("PERSISTED") and not p.marks
    assert "secret URL" not in json.dumps(r)
    db.engine.dispose()


def test_bounded_counters_retention_restart_and_failed_flush(tmp_path, monkeypatch):
    db, diag = diagnostics(tmp_path)
    for _ in range(1000):
        mint = str(Pubkey.new_unique())
        diag.note(mint, "ATTEMPTED")
        diag.note(mint, "MINT_METADATA")
        diag.review(mint, NOW, None, None)
    diag.note("secret" * 10000, "secret exception")
    diag.flush()
    r = receipt(db, diag)
    assert len(r["tokens"]) == 32 and len(r["reviews"]) == 24
    assert r["review_omissions"] == 976 and r["token_omissions"] > 0
    assert len(json.dumps(r).encode()) < 48000
    assert r["counts"]["ATTEMPTED"] == r["counts"]["MINT_METADATA"] == 1000
    assert r["in_progress"] == 0 and "secret" not in json.dumps(r)
    resumed = PriceDiagnostics(db, "synthetic")
    assert resumed.counts["ATTEMPTED"] == 1000

    def fail(*args, **kwargs):
        raise OSError("synthetic")

    monkeypatch.setattr(db, "evidence_run", fail)
    resumed.flush()
    assert resumed.durable_failures == 1
    assert receipt(db, resumed)["durable_failures"] == 0  # No false durable success.
    db.engine.dispose()


async def test_verified_curve_missing_decimals_is_not_generic_rpc_failure(tmp_path):
    from backend.app.providers import SolanaProvider

    rpc = SolanaProvider()
    rpc.global_cache = dict(
        initial_real_token_reserves=8 * 10**14,
        initial_virtual_token_reserves=10**15,
        token_total_supply=10**15,
    )
    rpc.global_cached_at = time.time()
    curve, _, quotes = inputs()
    rpc.rpc = AsyncMock(
        return_value={"context": {"slot": 100}, "value": [curve, None, quotes[WSOL], quotes[USDC]]}
    )
    report = (await rpc.curve_progress_batch([MINT], price_inputs=True))[MINT]
    assert report["data_quality"] == "VERIFIED" and report["price_status"] == "MINT_METADATA"
    await rpc.close()


@pytest.mark.parametrize("which", ["missing", "stale", "disagreement", "incompatible", "overflow"])
async def test_state_to_calculation_stages_stay_separate(tmp_path, which):
    e = RadarEngine(Settings(), tmp_path / "stages.db")
    now = time.time()
    e.process(MarketEvent(mint=MINT, source="SYNTHETIC", kind="create", ts=now, event_id="synthetic"), now)
    s = state(now - 30 if which == "incompatible" else now)
    e.rpc.curve_progress_batch = AsyncMock(
        return_value={MINT: dict(data_quality="VERIFIED", curve_progress=5, price_state=s)}
    )

    async def noop(*args, **kwargs):
        pass

    ref = refs(now - 30 if which == "stale" else now)
    if which == "overflow":
        s["base_raw"] = 1
        s["quote_raw"] = 2**64 - 1
        ref[WSOL]["usd"] = 1e308
    if which == "missing":
        ref = {}
    if which == "disagreement":
        e.tokens[MINT].disagreement = True
    from types import SimpleNamespace

    e.price_reference = SimpleNamespace(refresh=noop, snapshot=lambda: ref)
    await e.poll_curves([e.tokens[MINT]], "hot", 25)
    diag = e.price_research.diagnostics
    r = receipt(e.db, diag)
    assert r["counts"]["STATE_VALIDATED"] == 1
    expected = {
        "missing": "USD_UNAVAILABLE",
        "stale": "USD_STALE",
        "disagreement": "PROVIDER_DISAGREEMENT",
        "incompatible": "STALE_STATE",
        "overflow": "INVALID_PRICE",
    }[which]
    assert r["counts"][expected] == 1 and not r["counts"].get("CONSTRUCTED") and r["in_progress"] == 0
    await e.stop()


async def test_cancel_during_fx_does_not_mislabel_rpc_or_hide_shutdown(tmp_path):
    e = RadarEngine(Settings(), tmp_path / "fxcancel.db")
    now = time.time()
    e.process(MarketEvent(mint=MINT, source="SYNTHETIC", kind="create", ts=now, event_id="synthetic"), now)
    e.rpc.curve_progress_batch = AsyncMock(
        return_value={MINT: dict(price_state=state(now), curve_progress=5)}
    )
    entered = asyncio.Event()

    async def block(request):
        entered.set()
        await asyncio.Event().wait()

    ref = UsdReference(
        httpx.AsyncClient(transport=httpx.MockTransport(block)), diagnostics=e.price_research.diagnostics
    )
    e.price_reference = ref
    task = asyncio.create_task(e.poll_curves([e.tokens[MINT]], "hot", 25))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    r = receipt(e.db, e.price_research.diagnostics)
    assert r["counts"]["ACQUISITION_CANCELLED"] == 1 and not r["counts"].get("RPC_CANCELLED")
    assert r["fx"]["SOL-USD"]["counts"]["cancelled"] == 1 and r["in_progress"] == 0
    await e.stop()
    await ref.close()


def test_unfinished_diagnostic_attempts_cannot_grow_without_bound(tmp_path):
    db, diag = diagnostics(tmp_path)
    for _ in range(1000):
        diag.note(str(Pubkey.new_unique()), "ATTEMPTED")
    r = diag.snapshot()
    assert len(diag.inflight) == 25 and len(diag.tokens) == 32
    assert r["counts"]["inflight_omissions"] == 975 and not r["attempt_reconciled"]
    diag.flush()
    assert len(json.dumps(receipt(db, diag)).encode()) < 48000
    db.engine.dispose()


def test_diagnostic_history_is_bounded_without_pruning_original_evidence(tmp_path):
    from sqlalchemy import select, func

    db, diag = diagnostics(tmp_path)
    db.evidence_run("frozen-original", {"status": "PRESERVED"})
    db.add("opportunity_outcome", {"negative": True}, MINT, "old", NOW)
    for i in range(40):
        d = PriceDiagnostics(db, f"synthetic-{i}")
        d.note(MINT, "ATTEMPTED")
        d.note(MINT, "MINT_METADATA")
        d.flush()
    with db.sessions() as sql:
        assert (
            sql.scalar(select(func.count()).select_from(EvidenceRun).where(EvidenceRun.session.like("px:%")))
            == 32
        )
        assert json.loads(sql.get(EvidenceRun, "frozen-original").payload)["status"] == "PRESERVED"
    assert db.rows("opportunity_outcome")[0]["negative"]
    assert receipt(db, d)["diagnostic_retention"]["pruned_in_this_write"] == 1
    db.engine.dispose()


def test_first_review_reason_is_not_replaced_by_later_failure(tmp_path, monkeypatch):
    from copy import deepcopy

    db, diag = diagnostics(tmp_path)
    clock = [NOW - 2]
    monkeypatch.setattr("backend.app.price_diagnostics.time.time", lambda: clock[0])
    diag.note(MINT, "ATTEMPTED")
    clock[0] = NOW - 1
    diag.note(MINT, "MINT_METADATA")
    clock[0] = NOW
    diag.review(MINT, NOW, None, None)
    frozen = deepcopy(diag.reviews[MINT])
    assert frozen["acquisition_status_at_signal"] == "MINT_METADATA"
    assert frozen["rejection_reason_at_signal"] == "MINT_METADATA"
    assert frozen["rejection_observed_at_signal"] == NOW - 1
    for code in ("ATTEMPTED", "UNSUPPORTED_QUOTE", "PERSISTED", "EXPIRED"):
        clock[0] += 1
        diag.note(MINT, code)
    diag.review(MINT, NOW + 10, mark(NOW + 10), None)
    for key, value in frozen.items():
        if key.endswith("_at_signal") or key in ("baseline_status", "signal_at"):
            assert diag.reviews[MINT][key] == value
    assert diag.reviews[MINT]["last_failure"] == "UNSUPPORTED_QUOTE"
    diag.flush()
    assert receipt(db, diag)["reviews"][0]["rejection_reason_at_signal"] == "MINT_METADATA"
    db.engine.dispose()


@pytest.mark.parametrize(
    "case,unknown",
    [
        ("none", "NO_REJECTION_RECORDED"),
        ("late", "NOT_AVAILABLE_AT_SIGNAL"),
        ("future", "NOT_AVAILABLE_AT_SIGNAL"),
        ("skew", "EVENT_AFTER_PROCESSING_TIMESTAMP"),
        ("equal_event", "EQUAL_TIMESTAMP_AMBIGUOUS"),
        ("equal_processing", "EQUAL_TIMESTAMP_AMBIGUOUS"),
        ("backwards", "NON_MONOTONIC_DIAGNOSTIC_CLOCK"),
    ],
)
def test_first_review_uses_only_unambiguous_as_of_observations(tmp_path, monkeypatch, case, unknown):
    from copy import deepcopy

    db, diag = diagnostics(tmp_path)
    clock = [NOW - 3]
    monkeypatch.setattr("backend.app.price_diagnostics.time.time", lambda: clock[0])
    if case == "late":
        clock[0] = NOW + 1
        diag.note(MINT, "MINT_METADATA", NOW - 1)
    elif case == "future":
        clock[0] = NOW - 1
        diag.note(MINT, "MINT_METADATA", NOW + 1)
    elif case == "skew":
        clock[0] = NOW - 2
        diag.note(MINT, "MINT_METADATA", NOW - 1)
    elif case == "equal_event":
        clock[0] = NOW - 1
        diag.note(MINT, "MINT_METADATA", NOW)
    elif case == "equal_processing":
        clock[0] = NOW
        diag.note(MINT, "MINT_METADATA", NOW - 1)
    elif case == "backwards":
        diag.note(MINT, "ATTEMPTED")
        clock[0] = NOW - 1
        diag.note(MINT, "MINT_METADATA")
        clock[0] = NOW - 2
        diag.note(MINT, "UNSUPPORTED_QUOTE")
    if case != "late":
        clock[0] = NOW
    diag.review(MINT, NOW, None, None)
    first = deepcopy(diag.reviews[MINT])
    assert first["rejection_reason_at_signal"] == "UNKNOWN"
    assert first["rejection_observed_at_signal"] is None
    assert first["rejection_reason_unknown_reason"] == unknown
    clock[0] = NOW + 3
    diag.note(MINT, "UNSUPPORTED_CURVE_STATE")
    assert diag.reviews[MINT]["rejection_reason_at_signal"] == "UNKNOWN"
    assert diag.reviews[MINT]["last_failure"] == "UNSUPPORTED_CURVE_STATE"
    diag.flush()
    restored = PriceDiagnostics(db, "synthetic")
    assert restored.reviews[MINT]["rejection_reason_at_signal"] == "UNKNOWN"
    db.engine.dispose()


def test_expired_baseline_then_success_keeps_original_provenance(tmp_path, monkeypatch):
    from copy import deepcopy

    db, _ = diagnostics(tmp_path)
    p = PriceResearch(db, "synthetic")
    clock = [NOW - 30]
    monkeypatch.setattr("backend.app.price_diagnostics.time.time", lambda: clock[0])
    p.accept(mark(NOW - 30), NOW - 30, persist=True)
    clock[0] = NOW - 1
    p.diagnostics.note(MINT, "MINT_METADATA")
    clock[0] = NOW
    p.tick(tokens(), projections(), NOW)
    frozen = deepcopy(db.rows("v21_price_signal")[0])
    first = frozen["first_review_price_diagnostics"]
    assert first["baseline_status"] == "EARLIER_MARK_EXPIRED"
    assert first["rejection_reason_at_signal"] == "MINT_METADATA"
    clock[0] = NOW + 1
    p.accept(mark(NOW + 1), NOW + 1, persist=True)
    p.tick(tokens(), projections(NOW + 1), NOW + 1)
    assert db.rows("v21_price_signal")[0] == frozen and frozen["baseline"] is None
    assert p.diagnostics.reviews[MINT]["baseline_status"] == "EARLIER_MARK_EXPIRED"
    assert p.diagnostics.reviews[MINT]["later_mark_not_backfilled"]
    assert p.diagnostics.reviews[MINT]["rejection_reason_at_signal"] == "MINT_METADATA"
    p.stop()
    db.engine.dispose()


def test_canonical_signal_freezes_before_write_callback_changes_diagnostics(tmp_path, monkeypatch):
    db, _ = diagnostics(tmp_path)
    p = PriceResearch(db, "synthetic")
    clock = [NOW - 1]
    monkeypatch.setattr("backend.app.price_diagnostics.time.time", lambda: clock[0])
    p.diagnostics.note(MINT, "MINT_METADATA")
    clock[0] = NOW
    original = db.add

    def add(kind, *args, **kwargs):
        if kind == "v21_price_signal":
            clock[0] = NOW + 2
            p.diagnostics.note(MINT, "UNSUPPORTED_QUOTE")
        return original(kind, *args, **kwargs)

    monkeypatch.setattr(db, "add", add)
    p.tick(tokens(), projections(), NOW)
    canonical = db.rows("v21_price_signal")[0]["first_review_price_diagnostics"]
    assert canonical["rejection_reason_at_signal"] == "MINT_METADATA"
    assert p.diagnostics.reviews[MINT]["rejection_reason_at_signal"] == "MINT_METADATA"
    assert p.diagnostics.reviews[MINT]["last_failure"] == "UNSUPPORTED_QUOTE"
    p.stop()
    db.engine.dispose()


def test_legacy_review_never_infers_history_from_mutable_latest_state(tmp_path):
    db, diag = diagnostics(tmp_path)
    diag.reviews[MINT] = dict(
        mint=MINT,
        signal_at=NOW,
        baseline_status="ATTEMPT_RECORDED_NO_MARK",
        last_failure="UNSUPPORTED_QUOTE",
        last_failure_at=NOW + 50,
    )
    old = diag.snapshot()
    old["version"] = 1
    old["reviews"] = list(diag.reviews.values())
    db.evidence_run(diag.key, old)
    restored = PriceDiagnostics(db, "synthetic")
    assert "rejection_reason_at_signal" not in restored.reviews[MINT]
    view = restored.snapshot()["reviews"][0]
    assert view["acquisition_status_at_signal"] == "UNKNOWN"
    assert view["rejection_reason_at_signal"] == "UNKNOWN"
    assert view["rejection_reason_unknown_reason"] == "LEGACY_SIGNAL_PROVENANCE_UNAVAILABLE"
    assert view["last_failure"] == "UNSUPPORTED_QUOTE"
    db.engine.dispose()


def test_signal_timestamp_after_capture_is_never_treated_as_known_history(tmp_path, monkeypatch):
    db, diag = diagnostics(tmp_path)
    clock = [NOW - 2]
    monkeypatch.setattr("backend.app.price_diagnostics.time.time", lambda: clock[0])
    diag.note(MINT, "MINT_METADATA")
    clock[0] = NOW - 1
    diag.review(MINT, NOW, None, None)
    row = diag.reviews[MINT]
    assert row["acquisition_status_at_signal"] == row["rejection_reason_at_signal"] == "UNKNOWN"
    assert row["rejection_reason_unknown_reason"] == "SIGNAL_TIMESTAMP_AFTER_CAPTURE"
    db.engine.dispose()
