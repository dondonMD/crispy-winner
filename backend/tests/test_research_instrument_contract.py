"""Offline contract characterization, including gaps; no executable route claims."""

from dataclasses import fields, replace
import json

import pytest

from backend.app.early_edge import canonical
from backend.app.early_edge_quotes import StateObservation
from backend.app.early_edge_report import report
from backend.tests.test_early_edge import NOW, refs, snap, state, token, study as study


@pytest.mark.parametrize("offset,accepted", [(9.999, False), (10, True), (20, True), (20.001, False)])
def test_state_entry_window_is_bounded_but_not_a_provider_route_receipt(study, offset, accepted):
    snapshot = snap()
    study.enroll(snapshot, NOW)
    study.observe_state(state(snapshot["mint"], NOW + offset), refs(NOW + offset), NOW + offset)
    rows = study.db.execute("SELECT payload FROM ee_entries").fetchall()
    assert bool(rows) is accepted
    if rows:
        entry = json.loads(rows[0][0])
        assert entry["latency_boundary"] == NOW + 10
        assert entry["state"]["requested_at"] == NOW + offset
        assert entry["state"]["acquired_at"] == NOW + offset
        assert entry["quantity"] > 0 and entry["quote_raw"] > 0
        assert entry["sources"] == study.plan["quote_sources"]
        # This characterizes a qualification gap, not acceptable route evidence.
        assert {"route_available", "route_id", "expires_at", "quote_provider"}.isdisjoint(entry)
        assert "expires_at" not in {f.name for f in fields(StateObservation)}


def test_unavailable_sell_does_not_become_zero_loss_or_successful_exit(study):
    treatment = snap()
    control = snap(token(), action="DEVELOPING")
    sid = study.enroll(treatment, NOW, controls=[control])
    pair = study.db.execute("SELECT * FROM ee_pairs WHERE treatment=?", (sid,)).fetchone()
    assert pair["control"] is not None
    for snapshot in (treatment, control):
        study.observe_state(state(snapshot["mint"], NOW + 10), refs(NOW + 10), NOW + 10)
        observation = state(snapshot["mint"], NOW + 300)
        data = observation.data
        data["complete"] = True  # No supported sell on this old Pump venue snapshot.
        study.observe_state(replace(observation, data_json=canonical(data)), refs(NOW + 300), NOW + 300)
    study.expire(NOW + 321)
    rows = list(study.db.execute("SELECT status,payload FROM ee_outcomes WHERE horizon=300"))
    assert len(rows) == 2
    assert all(r["status"] == "UNAVAILABLE_QUOTE" for r in rows)
    assert all("net_return_pct" not in json.loads(r["payload"]) for r in rows)
    result = report(study.path)
    assert result["primary_unavailable"] == 2
    assert result["primary_accounting_fraction"] == 1
    assert result["primary_outcome_coverage"] == 0
    assert result["status"] != "EARLY_EDGE_SUPPORTED"


def test_unmatched_and_missing_entry_remain_in_denominator_no_later_backfill(study):
    snapshot = snap()
    sid = study.enroll(snapshot, NOW)
    assert study.db.execute("SELECT reason FROM ee_pairs WHERE treatment=?", (sid,)).fetchone()[0] == "UNMATCHED_AT_T"
    study.expire(NOW + 21)
    # Later on-chain state cannot reconstruct the missed entry.
    study.observe_state(state(snapshot["mint"], NOW + 300), refs(NOW + 300), NOW + 300)
    assert study.db.execute("SELECT count(*) FROM ee_entries").fetchone()[0] == 0
    rows = list(study.db.execute("SELECT status FROM ee_outcomes WHERE signal=?", (sid,)))
    assert len(rows) == len(study.plan["secondary_horizons"]) + 1
    assert all(r[0] == "UNAVAILABLE_QUOTE" for r in rows)
    result = report(study.path)
    assert result["unmatched_treatments"] == result["primary_unavailable"] == 1
    assert result["primary_accounting_fraction"] == 1
    assert result["primary_outcome_coverage"] == 0


def test_eligibility_refusal_does_not_supply_an_auditable_reason_snapshot(study):
    candidate = token()
    candidate.disagreement = True
    # Correct fail-closed exclusion; the snapshot API itself has no refusal receipt.
    # Coverage summaries elsewhere must not be represented as a full attempt ledger.
    assert snap(candidate) is None
    assert study.db.execute("SELECT count(*) FROM ee_signals").fetchone()[0] == 0
    assert study.db.execute("SELECT count(*) FROM ee_quality").fetchone()[0] == 0
