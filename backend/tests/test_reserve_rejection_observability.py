"""Synthetic-only diagnostic equivalence; no providers or historical databases."""

from copy import deepcopy
import json
from unittest.mock import AsyncMock

import pytest

from backend.app.early_prices import reserve_state, usd_mark, PriceResearch
from backend.app.early_edge_quotes import QuoteUnavailable, WSOL, USDC, ZERO
from backend.app.reserve_rejection_diagnostics import ReserveRejections, CONDITIONS
from backend.app.price_diagnostics import PriceDiagnostics
from backend.tests.test_early_prices import MINT, ADDRESS, NOW, inputs, refs, state
from backend.tests.test_early_edge import encode_account
from backend.tests.test_price_diagnostics import diagnostics, receipt
from backend.app.providers import PUMP_PROGRAM


def curve_for(mask, quote=ZERO):
    return encode_account(
        "BondingCurve",
        dict(
            virtual_token_reserves=10**15,
            virtual_quote_reserves=30 * 10**9,
            real_token_reserves=8 * 10**14,
            real_quote_reserves=10**9,
            token_total_supply=1 if mask & 4 else 10**15,
            complete=bool(mask & 1),
            is_mayhem_mode=bool(mask & 2),
            depth=int(bool(mask & 8)),
            post_complete_base_out=int(bool(mask & 16)),
            post_complete_quote_in=int(bool(mask & 32)),
            quote_mint=quote,
        ),
        PUMP_PROGRAM,
    )


@pytest.mark.parametrize("mask", range(64))
def test_all_original_predicate_combinations_unchanged(mask):
    curve, mint, quotes = inputs()
    curve = curve_for(mask)
    # Reference truth table for the unchanged original OR predicate; all combinations.
    if mask == 0:
        got = reserve_state(MINT, ADDRESS, curve, mint, quotes, 100, NOW - 0.1, NOW)
        expected = state()
        assert got == expected
        assert usd_mark(got, refs(), NOW) == usd_mark(expected, refs(), NOW)
    else:
        with pytest.raises(QuoteUnavailable) as caught:
            reserve_state(MINT, ADDRESS, curve, mint, quotes, 100, NOW - 0.1, NOW)
        assert type(caught.value) is QuoteUnavailable
        assert caught.value.reason == str(caught.value) == "UNSUPPORTED_CURVE_STATE"
        assert caught.value.args == ("UNSUPPORTED_CURVE_STATE",)
        assert caught.value._reserve_rejection == (mask, 1)


@pytest.mark.parametrize(
    "quote,category,reason",
    [
        (ZERO, 1, "UNSUPPORTED_CURVE_STATE"),
        (WSOL, 1, "UNSUPPORTED_CURVE_STATE"),
        (USDC, 2, "UNSUPPORTED_CURVE_STATE"),
        ("11111111111111111111111111111112", 3, "UNSUPPORTED_QUOTE"),
    ],
)
def test_quote_categories_do_not_add_support_or_override_rejection_order(quote, category, reason):
    _, mint, quotes = inputs()
    with pytest.raises(QuoteUnavailable) as caught:
        reserve_state(MINT, ADDRESS, curve_for(63, quote), mint, quotes, 100, NOW - 0.1, NOW)
    assert caught.value.reason == reason
    assert caught.value._reserve_rejection == (63 if category != 3 else 0, category)


def test_missing_or_malformed_accounts_keep_original_failure():
    curve, mint, quotes = inputs()
    for bad in (None, {}, {**curve, "owner": "INVALID"}, {**curve, "data": ["!", "base64"]}):
        with pytest.raises(QuoteUnavailable, match="CURVE_ACCOUNT_LAYOUT") as caught:
            reserve_state(MINT, ADDRESS, bad, mint, quotes, 100, NOW - 0.1, NOW)
        assert not hasattr(caught.value, "_reserve_rejection")


def test_original_short_circuit_is_not_replaced_by_diagnostic_field_access(monkeypatch):
    from backend.app import early_prices

    monkeypatch.setattr(
        early_prices, "decode_account", lambda *a: {"quote_mint": ZERO, "token_total_supply": 1}
    )
    with pytest.raises(QuoteUnavailable, match="UNSUPPORTED_CURVE_STATE") as caught:
        reserve_state(MINT, ADDRESS, *inputs(), 100, NOW - 0.1, NOW)
    assert caught.value._reserve_rejection == (0, 1)  # Unknown flags; same original rejection.


def test_masks_overlap_reconcile_durable_and_restore(tmp_path):
    db, diag = diagnostics(tmp_path)
    try:
        for mask in (1, 2, 4, 8, 16, 32, 63):
            diag.note(MINT, "ATTEMPTED", NOW)
            diag.note(MINT, "UNSUPPORTED_CURVE_STATE", NOW)
            diag.reserve_rejections.record("UNSUPPORTED_CURVE_STATE", (mask, 1))
        diag.note(MINT, "UNSUPPORTED_QUOTE", NOW)
        diag.reserve_rejections.record("UNSUPPORTED_QUOTE", (0, 3))
        diag.flush()
        d = receipt(db, diag)
        s = d["reserve_rejections"]
        assert s["reconciled"] and s["rejected_state_attempts"] == 7
        assert s["condition_counts"] == dict.fromkeys(CONDITIONS, 2)
        assert s["multi_condition_attempts"] == 1
        assert sum(s["condition_counts"].values()) == 12  # Conditions, not attempts.
        assert s["unsupported_quote_categories"]["UNSUPPORTED_IDENTITY"] == 1
        restored = PriceDiagnostics(db, "synthetic")
        assert restored.snapshot()["reserve_rejections"] == s
        assert restored.summary()["reserve_rejections"] == s
    finally:
        db.engine.dispose()


def test_legacy_receipt_counts_remain_unknown_not_backfilled(tmp_path):
    db, diag = diagnostics(tmp_path)
    try:
        diag.note(MINT, "UNSUPPORTED_CURVE_STATE", NOW)
        diag.note(MINT, "UNSUPPORTED_QUOTE", NOW)
        old = diag.snapshot()
        old.pop("reserve_rejections")
        db.evidence_run(diag.key, old)
        s = PriceDiagnostics(db, "synthetic").snapshot()["reserve_rejections"]
        assert s["unknown_condition_attempts"] == 1
        assert s["unsupported_quote_categories"]["UNKNOWN"] == 1
        assert s["reconciled"] and not any(s["condition_counts"].values())
    finally:
        db.engine.dispose()


@pytest.mark.parametrize(
    "bad", [None, {"API_KEY": "SENSITIVE"}, (1, "SENSITIVE"), (-1, 1), (64, 1), (True, 1), [1, 1]]
)
def test_untrusted_details_never_inject_keys(bad):
    r = ReserveRejections(None, {})
    r.record("UNSUPPORTED_CURVE_STATE", bad)
    s = r.snapshot({"UNSUPPORTED_CURVE_STATE": 1})
    assert s["unknown_condition_attempts"] == 1 and s["reconciled"]
    assert "SENSITIVE" not in json.dumps(s) and "API_KEY" not in json.dumps(s)
    assert set(s["condition_masks"]) == {str(i) for i in range(64)}


def test_restore_allowlist_and_size_under_sustained_numeric_updates(tmp_path):
    r = ReserveRejections({"condition_masks": {"evil": "secret"}}, {})
    assert "evil" not in json.dumps(r.snapshot({}))
    for _ in range(10000):
        r.record("UNSUPPORTED_CURVE_STATE", (63, 2))
    snapshot = r.snapshot({"UNSUPPORTED_CURVE_STATE": 10000})
    assert snapshot["reconciled"] and len(json.dumps(snapshot)) < 2500
    db, diag = diagnostics(tmp_path)
    try:
        diag.reserve_rejections = r
        diag.counts["UNSUPPORTED_CURVE_STATE"] = 10000
        for i in range(32):
            # Existing cache entries only; force byte pressure in an isolated fixture.
            diag.tokens[str(i)] = {"mint": "SYNTHETIC", "attempts": 0, "test_padding": "x" * 2000}
        diag.flush()
        saved = receipt(db, diag)
        assert len(json.dumps(saved).encode()) <= diag.BYTE_LIMIT
        assert saved["byte_omissions"] > 0
        assert all(saved["reserve_rejections"][key] == value for key, value in snapshot.items())
        assert not saved["reserve_rejections"]["telemetry_integrity_failed"]
    finally:
        db.engine.dispose()


async def test_private_report_details_never_change_market_events_or_processing(tmp_path, monkeypatch):
    from backend.app.config import Settings
    from types import SimpleNamespace
    import time
    from backend.app import engine as engine_module

    monkeypatch.setattr(
        engine_module,
        "time",
        SimpleNamespace(time=lambda: NOW, perf_counter=time.perf_counter, monotonic=time.monotonic),
    )
    from backend.app.engine import RadarEngine
    from backend.app.domain import MarketEvent

    engines = [RadarEngine(Settings(mode="OBSERVE"), tmp_path / f"{i}.db", offline=True) for i in range(2)]
    for i, e in enumerate(engines):
        e.price_research = PriceResearch(e.db, e.session)
        e.process(MarketEvent(mint=MINT, kind="create", ts=NOW, source="SYNTHETIC", event_id="create"), NOW)
        report = {
            "data_quality": "UNKNOWN",
            "curve_progress": None,
            "price_status": "UNSUPPORTED_CURVE_STATE",
        }
        if i:
            report["_reserve_rejection"] = (63, 1)
        e.rpc.curve_progress_batch = AsyncMock(return_value={MINT: deepcopy(report)})
        await e.poll_curves([e.tokens[MINT]], "hot", 25)
        await e.drain_events()
    try:
        a, b = engines
        assert a.accounting.terminal == b.accounting.terminal
        assert a.accounting.persisted == b.accounting.persisted
        assert a.price_research.diagnostics.counts == b.price_research.diagnostics.counts
        assert a.tokens[MINT].features == b.tokens[MINT].features
        assert a.tokens[MINT].scores == b.tokens[MINT].scores
        assert a.tokens[MINT].state == b.tokens[MINT].state
        assert a.approved_evidence is b.approved_evidence is None
        assert a.paper.state["positions"] == b.paper.state["positions"] == {}
        assert a.tokens[MINT].decision == b.tokens[MINT].decision
        for e in engines:
            e.intelligence.refresh(NOW, force=True)
            assert not any("_reserve_rejection" in json.dumps(x) for x in e.db.rows("event", MINT, e.session))
        assert a.intelligence.results == b.intelligence.results
        assert b.price_research.diagnostics.snapshot()["reserve_rejections"]["condition_masks"]["63"] == 1
    finally:
        for e in engines:
            await e.stop()


@pytest.mark.parametrize(
    "mask,quote,reason,detail",
    [
        (63, ZERO, "UNSUPPORTED_CURVE_STATE", (63, 1)),
        (1, USDC, "UNSUPPORTED_CURVE_STATE", (1, 2)),
        (63, "11111111111111111111111111111112", "UNSUPPORTED_QUOTE", (0, 3)),
    ],
)
async def test_actual_rpc_report_preserves_status_and_private_numeric_details(mask, quote, reason, detail):
    import time
    from backend.app.providers import SolanaProvider

    rpc = SolanaProvider()
    rpc.global_cache = dict(
        initial_real_token_reserves=8 * 10**14,
        initial_virtual_token_reserves=10**15,
        token_total_supply=10**15,
    )
    rpc.global_cached_at = time.time()
    _, mint, quotes = inputs()
    rpc.rpc = AsyncMock(
        return_value={
            "context": {"slot": 100},
            "value": [curve_for(mask, quote), mint, quotes[WSOL], quotes[USDC]],
        }
    )
    try:
        report = (await rpc.curve_progress_batch([MINT], price_inputs=True))[MINT]
        assert report["price_status"] == reason
        assert report["_reserve_rejection"] == detail
        assert not report.get("price_state")
    finally:
        await rpc.close()


def test_corrupt_retained_details_fail_reconciliation_without_changing_stage_counts():
    counts = {"UNSUPPORTED_CURVE_STATE": 1}
    r = ReserveRejections({"version": 1, "condition_masks": {"1": 99, "private_url": "secret"}}, counts)
    s = r.snapshot(counts)
    assert not s["reconciled"] and s["invalid_updates"] > 0
    assert "private_url" not in json.dumps(s) and counts == {"UNSUPPORTED_CURVE_STATE": 1}


@pytest.mark.parametrize("error", [RuntimeError, ValueError, TypeError])
def test_diagnostic_calculation_failure_keeps_original_rejection(monkeypatch, error):
    from backend.app import reserve_rejection_diagnostics as telemetry

    def fail(*args):
        raise error("PRIVATE_DIAGNOSTIC_ERROR")

    monkeypatch.setattr(telemetry, "condition_mask", fail)
    _, mint, quotes = inputs()
    with pytest.raises(QuoteUnavailable) as caught:
        reserve_state(MINT, ADDRESS, curve_for(63), mint, quotes, 100, NOW - 0.1, NOW)
    assert type(caught.value) is QuoteUnavailable
    assert caught.value.reason == str(caught.value) == "UNSUPPORTED_CURVE_STATE"
    assert caught.value.args == ("UNSUPPORTED_CURVE_STATE",)
    assert caught.value._reserve_rejection == (0, 1)
    assert caught.value._reserve_rejection_failed is True


@pytest.mark.parametrize(
    "fault", ["calculation", "aggregation_before", "aggregation_after", "snapshot", "snapshot_malformed"]
)
async def test_telemetry_failure_never_changes_curve_processing(tmp_path, monkeypatch, fault):
    import time
    from types import SimpleNamespace
    from backend.app import engine as engine_module
    from backend.app.engine import RadarEngine
    from backend.app.config import Settings
    from backend.app.domain import MarketEvent

    monkeypatch.setattr(
        engine_module,
        "time",
        SimpleNamespace(time=lambda: NOW, perf_counter=time.perf_counter, monotonic=time.monotonic),
    )
    engines = [
        RadarEngine(Settings(mode="OBSERVE"), tmp_path / f"isolated-{i}.db", offline=True) for i in range(2)
    ]
    try:
        for i, e in enumerate(engines):
            e.price_research = PriceResearch(e.db, e.session)
            e.process(
                MarketEvent(mint=MINT, kind="create", source="SYNTHETIC", ts=NOW, event_id="create"), NOW
            )
            report = {
                "data_quality": "UNKNOWN",
                "curve_progress": None,
                "price_status": "UNSUPPORTED_CURVE_STATE",
                "_reserve_rejection": (63, 1),
            }
            diag = e.price_research.diagnostics
            if i:
                if fault == "calculation":
                    report.update(_reserve_rejection=(0, 1), _reserve_rejection_failed=True)
                else:
                    original = diag.reserve_rejections.record

                    def fail(*args):
                        if fault == "aggregation_after":
                            original(*args)
                        raise RuntimeError("PRIVATE_DIAGNOSTIC_ERROR")

                    monkeypatch.setattr(
                        diag.reserve_rejections,
                        "snapshot" if fault.startswith("snapshot") else "record",
                        (lambda *a: {}) if fault == "snapshot_malformed" else fail,
                    )
            e.rpc.curve_progress_batch = AsyncMock(return_value={MINT: report})
            await e.poll_curves([e.tokens[MINT]], "hot", 25)
            await e.drain_events()
        a, b = engines
        assert a.accounting.terminal == b.accounting.terminal
        assert a.accounting.persisted == b.accounting.persisted
        assert a.tokens[MINT].features == b.tokens[MINT].features
        assert a.tokens[MINT].decision == b.tokens[MINT].decision
        assert a.price_research.diagnostics.counts == b.price_research.diagnostics.counts
        for e in engines:
            events = e.db.rows("event", MINT, e.session)
            assert "_reserve_rejection" not in json.dumps(events)
            assert "PRIVATE_DIAGNOSTIC_ERROR" not in json.dumps(events)
        saved = receipt(b.db, b.price_research.diagnostics)
        s = saved["reserve_rejections"]
        assert s["telemetry_integrity_failed"] is True and s["reconciled"] is False
        assert s["calculation_failures"] == int(fault == "calculation")
        assert s["aggregation_failures"] >= int(fault != "calculation")
        assert "PRIVATE_DIAGNOSTIC_ERROR" not in json.dumps(saved)
        assert len(json.dumps(saved).encode()) <= PriceDiagnostics.BYTE_LIMIT
        restored = PriceDiagnostics(b.db, b.session).snapshot()["reserve_rejections"]
        assert restored["telemetry_integrity_failed"] and not restored["reconciled"]
    finally:
        for e in engines:
            await e.stop()


async def test_calculation_failure_survives_real_rpc_adapter(monkeypatch):
    import time
    from backend.app import reserve_rejection_diagnostics as telemetry
    from backend.app.providers import SolanaProvider

    def fail(*args):
        raise RuntimeError("PRIVATE_DIAGNOSTIC_ERROR")

    monkeypatch.setattr(telemetry, "condition_mask", fail)
    rpc = SolanaProvider()
    rpc.global_cache = dict(
        initial_real_token_reserves=8 * 10**14,
        initial_virtual_token_reserves=10**15,
        token_total_supply=10**15,
    )
    rpc.global_cached_at = time.time()
    _, mint, quotes = inputs()
    rpc.rpc = AsyncMock(
        return_value={"context": {"slot": 100}, "value": [curve_for(63), mint, quotes[WSOL], quotes[USDC]]}
    )
    try:
        report = (await rpc.curve_progress_batch([MINT], price_inputs=True))[MINT]
        assert report["price_status"] == "UNSUPPORTED_CURVE_STATE"
        assert report["_reserve_rejection"] == (0, 1)
        assert report["_reserve_rejection_failed"] is True
        assert "PRIVATE_DIAGNOSTIC_ERROR" not in json.dumps(report)
    finally:
        await rpc.close()


def test_pricing_error_outside_telemetry_is_not_suppressed(monkeypatch):
    from backend.app import early_prices

    def fail(*args):
        raise RuntimeError("ORIGINAL_PRICING_FAILURE")

    monkeypatch.setattr(early_prices, "decode_account", fail)
    with pytest.raises(RuntimeError, match="ORIGINAL_PRICING_FAILURE"):
        reserve_state(MINT, ADDRESS, *inputs(), 100, NOW - 0.1, NOW)


def test_valid_state_never_calls_rejection_telemetry(monkeypatch):
    from backend.app import reserve_rejection_diagnostics as telemetry

    monkeypatch.setattr(
        telemetry, "condition_mask", lambda *a: pytest.fail("Valid states must bypass telemetry")
    )
    assert reserve_state(MINT, ADDRESS, *inputs(), 100, NOW - 0.1, NOW)["slot"] == 100


@pytest.mark.parametrize("bad", [None, "PRIVATE_DIAGNOSTIC_ERROR", True, 64])
def test_malformed_calculated_mask_remains_original_rejection(monkeypatch, bad):
    from backend.app import reserve_rejection_diagnostics as telemetry

    monkeypatch.setattr(telemetry, "condition_mask", lambda *a: bad)
    _, mint, quotes = inputs()
    with pytest.raises(QuoteUnavailable) as caught:
        reserve_state(MINT, ADDRESS, curve_for(63), mint, quotes, 100, NOW - 0.1, NOW)
    assert caught.value.reason == "UNSUPPORTED_CURVE_STATE"
    assert caught.value.args == ("UNSUPPORTED_CURVE_STATE",)
    assert caught.value._reserve_rejection == (0, 1)
    assert caught.value._reserve_rejection_failed is True
