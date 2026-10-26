"""Synthetic accounts and USD references; no live prices, fills or profit claims."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from solders.pubkey import Pubkey
from backend.app.early_prices import reserve_state, usd_mark, PriceResearch, HORIZONS
from backend.app.early_edge_quotes import WSOL, USDC, ZERO, pda, QuoteUnavailable
from backend.app.providers import PUMP_PROGRAM, SolanaProvider
from backend.app.db import Database, Base
from backend.tests.test_early_edge import encode_account, mint_account

NOW = 10000.0
MINT = str(Pubkey.new_unique())
ADDRESS = pda([b"bonding-curve", bytes(Pubkey.from_string(MINT))], PUMP_PROGRAM)


def inputs():
    curve = encode_account(
        "BondingCurve",
        dict(
            virtual_token_reserves=10**15,
            virtual_quote_reserves=30 * 10**9,
            real_token_reserves=8 * 10**14,
            real_quote_reserves=10**9,
            token_total_supply=10**15,
            quote_mint=ZERO,
        ),
        PUMP_PROGRAM,
    )
    quotes = {WSOL: mint_account(9), USDC: mint_account(6)}
    return curve, mint_account(), quotes


def state(at=NOW):
    return reserve_state(MINT, ADDRESS, *inputs(), 100, at - 0.1, at)


def refs(at=NOW):
    return {
        WSOL: dict(
            source="Coinbase Exchange public ticker",
            product="SOL-USD",
            usd=200,
            published_at=at - 0.2,
            acquired_at=at,
        )
    }


def mark(at=NOW):
    return usd_mark(state(at), refs(at), at)


def test_known_ratio_and_no_curve_progress_no_fees_or_executable_claim():
    result = mark()
    assert result["price"] == pytest.approx(0.000006)
    assert result["currency"] == "USD" and result["quote_decimals"] == 9
    assert result["evidence_level"] == "INDICATIVE_MARGINAL_MARK_NOT_EXECUTABLE"
    assert result["fees"] is result["liquidity_usd"] is result["net_return_pct"] is None
    assert len(result["account_hashes"]) == 3
    assert "curve_progress" not in result


@pytest.mark.parametrize(
    "fault",
    [
        "identity",
        "decimals",
        "quote",
        "owner",
        "uninitialized",
        "supply",
        "complete",
        "extension",
        "slot",
        "slow",
    ],
)
def test_account_inputs_fail_closed(fault):
    curve, mint, quotes = inputs()
    address, slot, requested = ADDRESS, 100, NOW - 0.1
    if fault in ("quote", "complete", "supply", "extension"):
        change = {
            "quote": dict(quote_mint=str(Pubkey.new_unique())),
            "complete": dict(complete=True),
            "supply": dict(token_total_supply=1),
            "extension": dict(depth=1),
        }[fault]
        curve = encode_account(
            "BondingCurve",
            dict(
                virtual_token_reserves=10**15,
                virtual_quote_reserves=30 * 10**9,
                real_token_reserves=8 * 10**14,
                token_total_supply=10**15,
                **change,
            )
            if fault != "supply"
            else dict(
                virtual_token_reserves=10**15,
                virtual_quote_reserves=30 * 10**9,
                real_token_reserves=8 * 10**14,
                **change,
            ),
            PUMP_PROGRAM,
        )
    if fault == "identity":
        address = str(Pubkey.new_unique())
    if fault == "decimals":
        quotes[WSOL] = mint_account(6)
    if fault == "owner":
        mint["owner"] = PUMP_PROGRAM
    if fault == "uninitialized":
        mint["executable"] = True
    if fault == "slot":
        slot = 0
    if fault == "slow":
        requested = NOW - 6
    with pytest.raises((QuoteUnavailable, ValueError)):
        reserve_state(MINT, address, curve, mint, quotes, slot, requested, NOW)


@pytest.mark.parametrize(
    "fault",
    ["stale", "future", "missing", "fx_stale", "fx_future", "fx_nan", "disagreement", "wrong_reference"],
)
def test_usd_reference_temporal_and_disagreement_contract(fault):
    s, r, now = state(), refs(), NOW
    if fault == "stale":
        now += 21
    if fault == "future":
        now -= 1
    if fault == "missing":
        r = {}
    if fault == "fx_stale":
        r[WSOL]["published_at"] -= 21
    if fault == "fx_future":
        r[WSOL]["acquired_at"] += 1
    if fault == "fx_nan":
        r[WSOL]["usd"] = float("nan")
    if fault == "wrong_reference":
        r[WSOL]["product"] = "OTHER"
    with pytest.raises(QuoteUnavailable):
        usd_mark(s, r, now, fault == "disagreement")


def test_later_fx_sets_later_observation_not_backfilled_state_time():
    value = usd_mark(state(), refs(NOW + 1), NOW + 1)
    assert value["state_acquired_at"] == NOW
    assert value["observed_at"] == value["acquired_at"] == NOW + 1
    assert value["valid_until"] <= NOW + 20


def projections(now=NOW):
    return {
        MINT: dict(
            early_market=dict(
                version="early-market-v2.1-SYNTHETIC",
                speculative_review=True,
                observed_at=now,
                valid_until=now + 10,
            )
        )
    }


def tokens():
    return {MINT: SimpleNamespace(graduation=None, disagreement=False)}


def test_missing_baseline_never_backfilled_or_excluded(tmp_path):
    db = Database(tmp_path / "test.db")
    Base.metadata.create_all(db.engine)
    r = PriceResearch(db, "synthetic")
    r.tick(tokens(), projections(), NOW)
    r.accept(mark(NOW + 15), NOW + 15)
    r.tick(tokens(), projections(NOW + 15), NOW + 15)
    assert len(db.rows("v21_price_signal")) == 1
    assert db.rows("v21_price_signal")[0]["baseline"] is None
    r.tick(tokens(), {}, NOW + 36)
    out = db.rows("v21_price_outcome")[0]
    assert out["status"] == "UNAVAILABLE_BASELINE" and out["measurement"] is None
    assert out["net_return_pct"] is None
    r.stop()
    assert len(db.rows("v21_price_outcome")) == len(HORIZONS)
    db.engine.dispose()


def test_first_prospective_endpoint_duplicate_order_and_snapshot_immutability(tmp_path):
    db = Database(tmp_path / "test.db")
    Base.metadata.create_all(db.engine)
    r = PriceResearch(db, "synthetic")
    baseline = mark()
    assert r.accept(baseline, NOW)
    r.tick(tokens(), projections(), NOW)
    frozen = deepcopy(db.rows("v21_price_signal")[0])
    assert not r.accept(baseline, NOW)
    assert not r.accept(mark(NOW - 1), NOW)
    early = mark(NOW + 14)
    r.accept(early, NOW + 14)
    r.tick(tokens(), {}, NOW + 15)
    assert not db.rows("v21_price_outcome")
    endpoint_state = state(NOW + 16)
    endpoint_state["quote_raw"] //= 2  # Synthetic negative movement retained.
    endpoint = usd_mark(endpoint_state, refs(NOW + 16), NOW + 16)
    r.accept(endpoint, NOW + 16)
    r.tick(tokens(), {}, NOW + 16)
    out = db.rows("v21_price_outcome")[0]
    assert out["status"] == "OBSERVED_GROSS_MARK"
    assert out["measurement"]["gross_price_change_pct"] == -50
    assert not out["executable"] and out["net_return_pct"] is None
    assert db.rows("v21_price_signal")[0] == frozen
    r.stop()
    db.engine.dispose()


@pytest.mark.parametrize("condition", ["migration", "disagreement", "missing", "late"])
def test_missing_or_incompatible_exit_not_zero_or_profit(tmp_path, condition):
    db = Database(tmp_path / "test.db")
    Base.metadata.create_all(db.engine)
    r = PriceResearch(db, "synthetic")
    r.accept(mark(), NOW)
    r.tick(tokens(), projections(), NOW)
    ts = NOW + 36 if condition == "late" else NOW + 16
    if condition != "missing":
        r.accept(mark(ts), ts)
    t = tokens()
    if condition == "migration":
        t[MINT].graduation = NOW + 10
    if condition == "disagreement":
        t[MINT].disagreement = True
    r.tick(t, {}, NOW + 36)
    row = db.rows("v21_price_outcome")[0]
    assert row["status"] == "UNAVAILABLE_PRICE" and row["measurement"] is None
    r.stop()
    db.engine.dispose()


def test_restart_censors_pending_and_preserves_existing_research(tmp_path):
    db = Database(tmp_path / "test.db")
    Base.metadata.create_all(db.engine)
    db.add("opportunity_outcome", {"original": True}, MINT, "old", NOW)
    r = PriceResearch(db, "synthetic")
    r.tick(tokens(), projections(), NOW)
    old = db.rows("opportunity_outcome")
    again = PriceResearch(db, "new-session")
    assert not again.pending
    assert {x["status"] for x in db.rows("v21_price_outcome")} == {"UNAVAILABLE_RESTART"}
    assert len(db.rows("v21_price_outcome")) == 5
    PriceResearch(db, "newer-session")
    assert len(db.rows("v21_price_outcome")) == 5
    assert db.rows("opportunity_outcome") == old
    db.engine.dispose()


async def test_one_slot_coherent_rpc_batch_not_extra_requests():
    rpc = SolanaProvider()
    curve, mint, quotes = inputs()

    async def response(method, params, **kwargs):
        assert method == "getMultipleAccounts"
        assert params[0][:4] == [ADDRESS, MINT, WSOL, USDC]
        return dict(context={"slot": 100}, value=[curve, mint, quotes[WSOL], quotes[USDC], None])

    rpc.rpc = AsyncMock(side_effect=response)
    reports = await rpc.curve_progress_batch([MINT], price_inputs=True)
    assert reports[MINT]["price_state"]["slot"] == 100
    assert rpc.rpc.await_count == 1
    await rpc.close()


@pytest.mark.parametrize(
    "change",
    [
        dict(currency="SOL"),
        dict(price=float("nan")),
        dict(price=1),
        dict(quote_decimals=6),
        dict(mint=str(Pubkey.new_unique())),
        dict(quote_mint=str(Pubkey.new_unique())),
        dict(slot=0),
        dict(verification="ASSUMED"),
    ],
)
def test_inconsistent_internal_marks_rejected(tmp_path, change):
    db = Database(tmp_path / "reject.db")
    Base.metadata.create_all(db.engine)
    r = PriceResearch(db, "synthetic")
    assert not r.accept({**mark(), **change}, NOW)
    assert not r.marks and r.rejected == 1
    assert not db.rows("v21_price_signal")
    db.engine.dispose()


def test_receipt_cache_owns_copy_and_capacity_omission_is_explicit(tmp_path):
    db = Database(tmp_path / "bounded.db")
    Base.metadata.create_all(db.engine)
    r = PriceResearch(db, "synthetic")
    m = mark()
    assert r.accept(m, NOW)
    m["price"] = 100
    assert r.marks[MINT]["price"] != 100
    r.tick(tokens(), projections(), NOW)
    r.LIMIT = 1
    other = str(Pubkey.new_unique())
    p = {other: next(iter(projections().values()))}
    r.tick({other: SimpleNamespace(graduation=None, disagreement=False)}, p, NOW)
    assert len(r.seen) == 1 and r.snapshot()["capacity_omitted_assessments"] == 1
    r.stop()
    assert len(db.rows("v21_price_outcome")) == 5
    db.engine.dispose()


@pytest.mark.parametrize("guard", [False, True])
async def test_engine_curve_delivery_precedes_usd_and_never_changes_core_price(tmp_path, monkeypatch, guard):
    from backend.app.engine import RadarEngine
    from backend.app.domain import MarketEvent
    from backend.app.config import Settings
    import time

    now = time.time()
    e = RadarEngine(Settings(mode="OBSERVE"), tmp_path / "integration.db")
    e.process(
        MarketEvent(mint=MINT, ts=now, source="SYNTHETIC", kind="create", event_id="synthetic-launch"), now
    )
    e.rpc.curve_progress_batch = AsyncMock(
        return_value={MINT: dict(curve_progress=5, data_quality="VERIFIED", price_state=state(now))}
    )

    async def refresh(*args, **kwargs):
        # USD I/O cannot delay admission of the original curve evidence.
        assert len(e.queue.heap) == 1

    e.price_reference = SimpleNamespace(refresh=refresh, snapshot=lambda: refs(now))
    before = deepcopy(e.tokens[MINT].decision)
    original_add = e.db.add

    def add(kind, *args, **kwargs):
        from backend.app.db import StorageBudgetError

        if guard and kind == "v21_price_mark":
            raise StorageBudgetError("Synthetic guard")
        return original_add(kind, *args, **kwargs)

    monkeypatch.setattr(e.db, "add", add)
    await e.poll_curves([e.tokens[MINT]], "hot", 25)
    assert len(e.db.rows("v21_price_mark")) == (0 if guard else 1)
    if guard:
        assert e.storage_stopped and not e.running and not e.price_research.marks
        assert e.trade_continuity["global_resets"] > 0
        import asyncio

        await asyncio.wait_for(e.run_loop(), 0.2)  # Guarded consumer cannot resume evidence processing.
    assert e.tokens[MINT].price is None and e.tokens[MINT].decision == before
    queued = e.queue.drain()
    assert len(queued) == 1 and "price_state" not in queued[0].evidence
    await e.stop()


async def test_bounded_fx_products_alternate_without_starving_or_new_requests(monkeypatch):
    from backend.app.early_edge_runtime import UsdReference
    from datetime import datetime, timezone
    import time

    ref = UsdReference()
    called = []
    now = time.time()

    async def request(method, url, **kwargs):
        called.append(url)
        if "coinbase" in url:
            return dict(price="200", time=datetime.fromtimestamp(now, timezone.utc).isoformat())
        return dict(error=[], result={"USDCUSD": [["1.001", "1", now]], "last": "synthetic"})

    monkeypatch.setattr(ref, "request", request)
    await ref.refresh({WSOL, USDC}, max_products=1)
    assert len(called) == 1
    await ref.refresh({WSOL, USDC}, max_products=1)
    assert len(called) == 2 and "kraken" in called[1]
    assert ref.cache[USDC]["usd"] == 1.001  # No silent USD peg.
    await ref.close()


def test_failed_mark_commit_cannot_be_used_as_signal_baseline(tmp_path, monkeypatch):
    from backend.app.db import StorageBudgetError

    db = Database(tmp_path / "guard.db")
    Base.metadata.create_all(db.engine)
    r = PriceResearch(db, "synthetic")

    def fail(*args, **kwargs):
        raise StorageBudgetError("Synthetic guard")

    monkeypatch.setattr(db, "add", fail)
    with pytest.raises(StorageBudgetError):
        r.accept(mark(), NOW, persist=True)
    assert not r.marks and not r.seen and not r.pending
    db.engine.dispose()


@pytest.mark.parametrize("kind", ["v21_price_signal", "v21_price_outcome"])
def test_uncertain_commit_retry_does_not_duplicate_or_replace_baseline(tmp_path, monkeypatch, kind):
    db = Database(tmp_path / "retry.db")
    Base.metadata.create_all(db.engine)
    r = PriceResearch(db, "synthetic")
    r.accept(mark(), NOW)
    original = db.add
    failed = []

    def add(record_kind, *args, **kwargs):
        result = original(record_kind, *args, **kwargs)
        if record_kind == kind and not failed:
            failed.append(True)
            raise RuntimeError("Synthetic acknowledgement failure after commit")
        return result

    monkeypatch.setattr(db, "add", add)
    if kind == "v21_price_signal":
        with pytest.raises(RuntimeError):
            r.tick(tokens(), projections(), NOW)
        r.accept(mark(NOW + 1), NOW + 1)
        r.tick(tokens(), projections(NOW + 1), NOW + 1)
        assert len(db.rows("v21_price_signal")) == 1
        assert next(iter(r.pending.values()))["baseline"]["observed_at"] == NOW
    else:
        r.tick(tokens(), projections(), NOW)
        r.accept(mark(NOW + 16), NOW + 16)
        with pytest.raises(RuntimeError):
            r.tick(tokens(), {}, NOW + 16)
        r.tick(tokens(), {}, NOW + 17)
        assert len(db.rows("v21_price_outcome")) == 1
        assert 15 not in next(iter(r.pending.values()))["remaining"]
    r.stop()
    assert len(db.rows("v21_price_outcome")) == 5
    db.engine.dispose()
