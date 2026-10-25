"""Synthetic receipts and isolated pilot ledgers; never market evidence."""

import hashlib
import json
import sqlite3
import subprocess
import sys

import pytest
from solders.pubkey import Pubkey

from backend.app.early_edge_quote_receipts import Context, COSTS, validate_receipt
from backend.app.early_edge_attempts import AttemptLedger, LedgerError, LedgerCensored
from backend.app.early_edge_quotes import USDC, WSOL
from backend.app.providers import PUMP_PROGRAM


def h(value):
    return hashlib.sha256(str(value).encode()).hexdigest()


def fixture(direction="BUY", migrated=False):
    mint = str(Pubkey.from_bytes(b"x" * 32))
    curve = str(Pubkey.find_program_address([b"bonding-curve", bytes(Pubkey.from_string(mint))],
                                          Pubkey.from_string(PUMP_PROGRAM))[0])
    context = Context(provider="SYNTHETIC", source_version="fixture-v1", quote_version="v1",
        adapter_evidence_sha256=h("adapter"), identity_evidence_sha256=h("identity"),
        signal_at=1000.0, direction=direction, base_mint=mint, quote_mint=WSOL,
        base_decimals=6, quote_decimals=9, input_amount_raw=4000000,
        venue="PUMPSWAP" if migrated else "PUMP",
        venue_address=str(Pubkey.from_bytes(b"p" * 32)) if migrated else curve,
        lifecycle="MIGRATED" if migrated else "PRE_GRAD",
        migration_evidence_sha256=h("migration") if migrated else None,
        max_slippage_bps=100, cost_policy_sha256=h("costs"), usd_reference_sha256=h("fx"))
    due = 1010.0 if direction == "BUY" else 1300.0
    receipt = dict(evidence_kind="PROVIDER_ROUTE_QUOTE", provider="SYNTHETIC", source_version="fixture-v1",
        quote_version="v1", quote_sha256=h("quote"), response_evidence_sha256=h("response"),
        requested_at=due, responded_at=due + 1, provider_quoted_at=due + .5,
        expires_at=due + 5, expiry_evidence_sha256=h("expiry"), direction=direction,
        venue=context.venue, venue_address=context.venue_address, base_mint=mint, quote_mint=WSOL,
        base_decimals=6, quote_decimals=9, input_amount_raw=4000000,
        output_amount_raw=10000, minimum_output_raw=9900, amount_semantics="EXACT_IN_RAW_NET_OUTPUT",
        route_available=True, route_evidence_sha256=h("route"),
        execution_conditions="CLASSIC_SPL_NO_FREEZE_HOOK_TRANSFER_FEE_OR_RESTRICTIONS",
        conditions_evidence_sha256=h("conditions"),
        fees=[dict(component=k, treatment="EXTERNAL", amount_raw=1, mint=WSOL,
                   decimals=9, evidence_sha256=h(k), unavailable_reason=None) for k in COSTS])
    return context, receipt, due + 1


@pytest.mark.parametrize("direction,migrated", [("BUY", False), ("SELL", False), ("SELL", True)])
def test_complete_receipt_is_neither_a_fill_nor_profitable_outcome(direction, migrated):
    c, r, now = fixture(direction, migrated)
    result = validate_receipt(r, c, now)
    assert result.accepted and result.route_valid and result.status == "QUOTE_ACCEPTED"
    assert not result.outcome_authorized
    assert result.receipt_sha256 and result.context_sha256
    assert "net_return_pct" not in result.model_dump()


@pytest.mark.parametrize("field,value,reason", [
    ("provider", "OTHER", "SOURCE_MISMATCH"),
    ("requested_at", 1009.0, "LATE_OR_OUT_OF_WINDOW"),
    ("responded_at", 1021.0, "LATE_OR_OUT_OF_WINDOW"),
    ("provider_quoted_at", 1009.0, "STALE_OR_FUTURE_PROVIDER_QUOTE"),
    ("provider_quoted_at", 1012.0, "STALE_OR_FUTURE_PROVIDER_QUOTE"),
    ("expires_at", 1011.0, "EXPIRED_QUOTE"),
    ("route_available", False, "NO_ROUTE"),
    ("input_amount_raw", 1, "UNITS_OR_AMOUNT_MISMATCH"),
    ("quote_decimals", 6, "UNITS_OR_AMOUNT_MISMATCH"),
    ("minimum_output_raw", 9899, "INCONSISTENT_SLIPPAGE_OR_OUTPUT"),
    ("minimum_output_raw", 10001, "INCONSISTENT_SLIPPAGE_OR_OUTPUT"),
    ("execution_conditions", "UNKNOWN", "INCOMPLETE_OR_UNSUPPORTED_RECEIPT"),
    ("evidence_kind", "STATE_DERIVED_HYPOTHETICAL", "INCOMPLETE_OR_UNSUPPORTED_RECEIPT"),
    ("requested_at", True, "INCOMPLETE_OR_UNSUPPORTED_RECEIPT"),
])
def test_failures_are_fixed_and_never_authorize_outcomes(field, value, reason):
    c, r, now = fixture()
    r[field] = value
    result = validate_receipt(r, c, now)
    assert not result.accepted and result.reason == reason and not result.outcome_authorized


@pytest.mark.parametrize("field", ["expires_at", "expiry_evidence_sha256", "fees", "route_evidence_sha256"])
def test_required_receipt_fields_cannot_be_invented(field):
    c, r, now = fixture()
    del r[field]
    assert not validate_receipt(r, c, now).accepted


def test_verified_context_alternative_requires_exact_independent_evidence():
    c, r, now = fixture()
    r.update(provider_quoted_at=None, context_slot=123, context_evidence_sha256=h("slot"))
    assert not validate_receipt(r, c, now).accepted
    c = c.model_copy(update=dict(verified_context_slot=123, verified_context_acquired_at=1010.5,
                                verified_context_sha256=h("slot")))
    assert validate_receipt(r, c, now).accepted
    r["context_slot"] = 122
    assert not validate_receipt(r, c, now).accepted


def test_missing_costs_are_explicit_unavailable_not_zero():
    c, r, now = fixture()
    r["fees"][0].update(treatment="UNAVAILABLE", amount_raw=None, mint=None, decimals=None,
                        evidence_sha256=None, unavailable_reason="NOT_PROVIDED")
    result = validate_receipt(r, c, now)
    assert result.route_valid and not result.accepted
    assert result.status == "UNAVAILABLE_QUOTE" and result.reason == "COST_COMPONENT_UNAVAILABLE"
    assert r["fees"][0]["amount_raw"] is None


def test_usdc_units_do_not_assume_sol_decimals_or_free_costs():
    c, r, now = fixture()
    c = c.model_copy(update={"quote_mint": USDC, "quote_decimals": 6})
    r.update(quote_mint=USDC, quote_decimals=6)
    for component in r["fees"]:
        if component["component"] in ("protocol", "creator", "lp", "platform", "transfer"):
            component.update(mint=USDC, decimals=6)
    assert validate_receipt(r, c, now).accepted
    r["fees"][0].update(treatment="NOT_APPLICABLE", amount_raw=1)
    assert not validate_receipt(r, c, now).accepted


def test_unknown_units_and_migration_fail_closed():
    c, r, now = fixture("SELL", True)
    assert not validate_receipt(r, c.model_copy(update={"migration_evidence_sha256": None}), now).accepted
    c, r, now = fixture("BUY", True)
    assert not validate_receipt(r, c, now).accepted
    c, r, now = fixture()
    other = str(Pubkey.from_bytes(b"q" * 32))
    r["quote_mint"] = other
    assert validate_receipt(r, c.model_copy(update={"quote_mint": other}), now).status == "UNAVAILABLE_UNITS"


def test_all_horizons_and_deadline_validation_time():
    for horizon in (60, 180, 300, 600, 1800):
        c, r, _ = fixture("SELL")
        c = c.model_copy(update={"horizon_seconds": horizon})
        for k in ("requested_at", "responded_at", "provider_quoted_at", "expires_at"):
            r[k] += horizon - 300
        assert validate_receipt(r, c, 1001.0 + horizon).accepted
        assert not validate_receipt(r, c, 1021.0 + horizon).accepted


def test_ledger_keeps_failures_duplicates_and_retry_denominators(tmp_path):
    ledger = AttemptLedger(tmp_path / "attempts.db", h("protocol"), 1000)
    try:
        for n, reason in enumerate(("UNITS_MISSING", "READINESS_MISSING", "HARD_RISK")):
            assert ledger.begin(h(n), h("same-observation"), "SIGNAL", 1000, h("snapshot"))
            ledger.finish(h(n), "INELIGIBLE", reason, 1000)
        assert not ledger.begin(h(0), h("same-observation"), "SIGNAL", 1001, h("snapshot"))
        ledger.finish(h(0), "INELIGIBLE", "UNITS_MISSING", 1001)
        s = ledger.summary()
        assert s["unique_attempts"] == 3 and s["unique_observations"] == 1
        assert s["dispositions"] == {"INELIGIBLE": 3} and s["duplicates"] == 2
        with pytest.raises(LedgerError, match="Conflicting"):
            ledger.finish(h(0), "ELIGIBLE", "ELIGIBLE", 1002)
        assert ledger.summary()["conflicts"] == 1
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            ledger.db.execute("DELETE FROM ee_attempt_events")
        ledger.verify()
    finally:
        ledger.close()


def test_validated_quote_recording_never_writes_outcome_tables(tmp_path):
    ledger = AttemptLedger(tmp_path / "attempts.db", h("protocol"), 1000)
    try:
        c, r, now = fixture()
        ledger.begin(h(1), h("obs"), "ENTRY_QUOTE", 1010, h("request"))
        with pytest.raises(LedgerError):
            ledger.finish(h(1), "QUOTE_ACCEPTED", "VALID_RECEIPT", now)
        assert ledger.quote(h(1), r, c, now).accepted
        stored = json.loads(ledger.db.execute("SELECT receipt FROM ee_attempt_events WHERE event='END'").fetchone()[0])
        assert stored["receipt"]["responded_at"] == now
        assert stored["context"]["base_mint"] == c.base_mint
        duplicate = ledger.quote(h(1), r, c, 1016)  # Identical but now expired: never a new fill.
        assert not duplicate.accepted and duplicate.reason == "DUPLICATE_IGNORED"
        r["quote_sha256"] = h("different-delivery")
        with pytest.raises(LedgerError, match="Conflicting"):
            ledger.quote(h(1), r, c, 1017)
        tables = {v[0] for v in ledger.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert tables == {"ee_attempt_meta", "ee_attempt_events"}
        assert ledger.summary()["unique_attempts"] == 1 and ledger.summary()["conflicts"] == 1
    finally:
        ledger.close()


def test_rollback_retry_and_cold_restart_preserve_pending_failure(tmp_path):
    path = tmp_path / "attempts.db"
    ledger = AttemptLedger(path, h("protocol"), 1000)
    ledger.begin(h(1), h("obs"), "CONTROL", 1000, h("snapshot"))
    ledger.db.execute("CREATE TRIGGER fail BEFORE INSERT ON ee_attempt_events BEGIN SELECT RAISE(ABORT,'injected'); END")
    with pytest.raises(sqlite3.IntegrityError):
        ledger.finish(h(1), "UNMATCHED", "NO_COMPARABLE_CONTROL", 1001)
    assert ledger.summary()["pending_attempts"] == 1
    ledger.db.execute("DROP TRIGGER fail")
    ledger.finish(h(1), "UNMATCHED", "NO_COMPARABLE_CONTROL", 1001)
    ledger.begin(h(2), h("obs2"), "EXIT_QUOTE", 1002, h("request"))
    ledger.close()  # Simulate unfinalized owner shutdown; no outcomes may resume.
    ledger = AttemptLedger(path, h("protocol"), 1003)
    try:
        assert ledger.summary()["pending_attempts"] == 0
        assert ledger.summary()["dispositions"] == {"UNMATCHED": 1, "UNAVAILABLE_INFRASTRUCTURE": 1}
        with pytest.raises(LedgerError, match="Conflicting"):
            ledger.finish(h(2), "UNAVAILABLE_QUOTE", "NO_ROUTE", 1004)
        ledger.verify()
    finally:
        ledger.close()


def test_capacity_and_storage_censorship_are_durable(tmp_path):
    ledger = AttemptLedger(tmp_path / "capacity.db", h("p"), 1000)
    try:
        for i in range(64):
            assert ledger.begin(h(i), h(i), "SIGNAL", 1000, h("snapshot"))
        assert not ledger.begin(h(64), h(64), "SIGNAL", 1000, h("snapshot"))
        assert ledger.summary()["unique_attempts"] == 65
        assert ledger.summary()["pending_attempts"] == 64
        assert ledger.summary()["dispositions"] == {"UNAVAILABLE_INFRASTRUCTURE": 1}
    finally:
        ledger.close()
    path = tmp_path / "bounded.db"
    ledger = AttemptLedger(path, h("p"), 1000, max_events=4)
    ledger.begin(h(1), h(1), "SIGNAL", 1000, h("s"))
    ledger.finish(h(1), "ELIGIBLE", "ELIGIBLE", 1000)
    ledger.begin(h(2), h(2), "SIGNAL", 1000, h("s"))
    with pytest.raises(LedgerCensored):
        ledger.finish(h(2), "INELIGIBLE", "HARD_RISK", 1001)
    assert ledger.summary()["unique_attempts"] == 2
    assert sum(ledger.summary()["dispositions"].values()) == 2
    ledger.close()
    ledger = AttemptLedger(path, h("p"), 1002, max_events=4)
    try:
        assert ledger.summary()["censored"]
        with pytest.raises(LedgerCensored):
            ledger.begin(h(3), h(3), "SIGNAL", 1003, h("s"))
        assert ledger.db.execute("SELECT count(*) FROM ee_attempt_events").fetchone()[0] == 4
    finally:
        ledger.close()


def test_foreign_databases_and_simultaneous_owner_refused(tmp_path):
    foreign = tmp_path / "old.db"
    with sqlite3.connect(foreign) as db:
        db.execute("CREATE TABLE historical(payload TEXT)")
        db.execute("INSERT INTO historical VALUES('negative outcome')")
    before = foreign.read_bytes()
    with pytest.raises(LedgerError, match="Foreign"):
        AttemptLedger(foreign, h("p"), 1000)
    assert foreign.read_bytes() == before
    path = tmp_path / "ledger.db"
    ledger = AttemptLedger(path, h("p"), 1000)
    try:
        with pytest.raises(BlockingIOError):
            AttemptLedger(path, h("p"), 1000)
    finally:
        ledger.close()
    with pytest.raises(LedgerError, match="drift"):
        AttemptLedger(path, h("changed-protocol"), 1001)


def test_payload_privacy_and_no_price_return_generation():
    c, r, now = fixture()
    r["provider"] = "https://private.invalid/?credential=SECRET"
    result = validate_receipt(r, c, now)
    assert "SECRET" not in result.model_dump_json()
    assert not result.accepted and not result.outcome_authorized


def test_request_time_binding_and_explicit_shutdown(tmp_path):
    ledger = AttemptLedger(tmp_path / "attempts.db", h("p"), 1000)
    c, r, now = fixture()
    ledger.begin(h(1), h(1), "ENTRY_QUOTE", 1010.5, h("request"))
    result = ledger.quote(h(1), r, c, now)
    assert not result.accepted and result.reason == "REQUEST_TIME_MISMATCH"
    ledger.begin(h(2), h(2), "EXIT_QUOTE", 1012, h("request"))
    summary = ledger.shutdown(1013)
    assert summary["pending_attempts"] == 0
    assert summary["unique_attempts"] == sum(summary["dispositions"].values()) == 2


def test_eligible_controls_and_malformed_replay_remain_auditable(tmp_path):
    ledger = AttemptLedger(tmp_path / "attempts.db", h("p"), 1000)
    for i, status, reason in ((1, "MATCHED", "SELECTED_AT_T"), (2, "NOT_SELECTED", "OTHER_CONTROL_SELECTED")):
        ledger.begin(h(i), h(i), "CONTROL", 1000, h("snapshot"))
        ledger.finish(h(i), status, reason, 1000)
    c, _, now = fixture()
    ledger.begin(h(3), h(3), "ENTRY_QUOTE", 1010, h("request"))
    assert not ledger.quote(h(3), None, c, now).accepted
    assert ledger.quote(h(3), None, c, now).reason == "DUPLICATE_UNVERIFIABLE"
    summary = ledger.shutdown(now)
    assert summary["unique_attempts"] == 3 and summary["duplicates"] == 1
    assert summary["unverifiable_duplicates"] == 1
    assert sum(summary["dispositions"].values()) == 3


def test_failed_retry_and_later_better_quote_cannot_replace_first_valid(tmp_path):
    ledger = AttemptLedger(tmp_path / "attempts.db", h("p"), 1000)
    c, r, now = fixture()
    ledger.begin(h(1), h("same-endpoint"), "ENTRY_QUOTE", 1010, h("request"))
    assert not ledger.quote(h(1), None, c, now).accepted
    ledger.begin(h(2), h("same-endpoint"), "ENTRY_QUOTE", 1011, h("request"))
    r.update(requested_at=1011.0, provider_quoted_at=1011.5, responded_at=1012.0)
    assert ledger.quote(h(2), r, c, 1012).accepted
    ledger.begin(h(3), h("same-endpoint"), "ENTRY_QUOTE", 1012, h("request"))
    r.update(requested_at=1012.0, provider_quoted_at=1012.5, responded_at=1013.0, output_amount_raw=20000,
             minimum_output_raw=19800)
    result = ledger.quote(h(3), r, c, 1013)
    assert not result.accepted and result.status == "QUOTE_NOT_SELECTED"
    summary = ledger.shutdown(1014)
    assert summary["unique_attempts"] == 3 and summary["unique_observations"] == 1
    assert summary["dispositions"] == {"UNAVAILABLE_QUOTE": 1, "QUOTE_ACCEPTED": 1, "QUOTE_NOT_SELECTED": 1}


@pytest.mark.parametrize("change", ["missing_units", "missing_cost", "missing_route", "missing_receipt"])
def test_rejected_quotes_remain_terminal_and_counted(tmp_path, change):
    c, r, now = fixture()
    if change == "missing_units":
        r["quote_decimals"] = 6
    elif change == "missing_cost":
        del r["fees"]
    elif change == "missing_route":
        r["route_available"] = False
    else:
        r = None
    ledger = AttemptLedger(tmp_path / "attempts.db", h("p"), 1000)
    ledger.begin(h(1), h("observation"), "ENTRY_QUOTE", 1010, h("request"))
    result = ledger.quote(h(1), r, c, now)
    assert not result.accepted
    summary = ledger.shutdown(now)
    assert summary["pending_attempts"] == 0 and summary["unique_attempts"] == 1
    assert sum(summary["dispositions"].values()) == 1


def test_real_process_exit_is_accounted_on_reopen(tmp_path):
    path = tmp_path / "crash.db"
    # Standard Python child; no socket, service or quote request.
    code = """
import os,sys
from backend.app.early_edge_attempts import AttemptLedger
ledger=AttemptLedger(sys.argv[1], 'a'*64, 1000)
ledger.begin('b'*64, 'c'*64, 'ENTRY_QUOTE', 1000, 'd'*64)
os._exit(0)
"""
    subprocess.run([sys.executable, "-c", code, str(path)], check=True, timeout=10)
    ledger = AttemptLedger(path, "a" * 64, 1001)
    try:
        assert ledger.summary()["dispositions"] == {"UNAVAILABLE_INFRASTRUCTURE": 1}
        assert ledger.summary()["pending_attempts"] == 0
        assert ledger.db.execute("SELECT reason FROM ee_attempt_events WHERE event='END'").fetchone()[0] == "PROCESS_INTERRUPTION"
    finally:
        ledger.close()
