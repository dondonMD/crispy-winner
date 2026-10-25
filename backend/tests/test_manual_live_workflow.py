"""Deterministic workflow/evidence fixtures; never live market observations."""

from copy import deepcopy

import pytest
from solders.pubkey import Pubkey

from backend.app.config import Settings
from backend.app.domain import MarketEvent, State
from backend.app.engine import RadarEngine
from backend.app.manual import ManualJournal, OpenPositionInput
from backend.app.opportunity import opportunity_view
from backend.tests.test_opportunity import candidate, NOW


def current_candidate():
    t = candidate()
    t.creator = str(Pubkey.from_bytes(b"c" * 32))
    t.security.update(creator_pct=1, top_1_independent_pct=1, top_5_independent_pct=5)
    t.last_trade = NOW
    t.features["180"].update(trade_evidence="CURRENT", units_valid=True, continuity_valid=True,
                             estimated_independent_buyers=20, flow_ratio=2.0, coverage_seconds=180)
    return t


@pytest.mark.parametrize("change", [None, "stale", "graduated", "security", "units", "degraded", "late_curve", "risk", "concentration"])
def test_review_is_a_stricter_presentation_not_entry_approval(change):
    t = current_candidate()
    if change == "stale":
        t.last_trade = NOW - 21
    elif change == "graduated":
        t.graduation = NOW - 1
    elif change == "security":
        t.security["last_updated"] = NOW - 301
    elif change == "units":
        t.features["180"]["units_valid"] = False
    elif change == "degraded":
        t.degraded = True
    elif change == "late_curve":
        t.curve_progress = 90
        t.curve_history[-1] = (NOW, 90)
    elif change == "risk":
        t.security["hard_failures"] = ["CONCENTRATION"]
    elif change == "concentration":
        t.security["top_1_independent_pct"] = 11
    before = deepcopy(t)
    view = opportunity_view(t, Settings(), NOW)
    assert view.entry_review_eligible is (change is None)
    if change is None:
        assert view.review_valid_until == NOW + 20
        assert view.trade_coverage_seconds == 180
    assert t == before and not view.validated_edge
    assert t.decision.get("decision") != "ALLOW_PAPER_ENTRY"


@pytest.fixture
async def engine(tmp_path):
    e = RadarEngine(Settings(mode="OBSERVE", max_candidates=2, max_deep=1), tmp_path / "offline.db", offline=True)
    yield e
    await e.stop()


def open_record(e, token):
    return e.intelligence.open_position(OpenPositionInput(mint=token.mint, amount_usd=4,
                                       price_usd=1, quantity_tokens=4, actual_entry_fees_usd=.1, confirm=True), NOW)


def test_held_candidate_gets_existing_slot_and_no_eviction_or_expiry(engine):
    e = engine
    held, other = candidate(), candidate()
    other.state = State.POST_GRAD_OBSERVATION
    e.tokens = {t.mint: t for t in (held, other)}
    before = deepcopy(e.paper.state), e.approved_evidence
    p = open_record(e, held)
    assert e.deep_mints() == [held.mint]
    e.metrics["resource_pressure"] = True
    assert len(e.deep_mints()) == 1
    e.intelligence.refresh_positions(NOW)
    assert e.intelligence.exit_results[p["position_id"]]["monitoring"]["status"] == "MONITORING DEGRADED"
    e.metrics["resource_pressure"] = False
    # At capacity, ordinary admission cannot displace the known held token.
    incoming = candidate()
    e.admit(MarketEvent(mint=incoming.mint, kind="migration", ts=NOW, source="synthetic", event_id="new"))
    assert held.mint in e.tokens and len(e.tokens) <= 2
    e.expire_inactive_candidates(NOW + 100000)
    assert held.mint in e.tokens
    assert before == (e.paper.state, e.approved_evidence)


def test_journal_restart_and_untracked_position_are_explicit(engine):
    e = engine
    held = candidate()
    e.tokens[held.mint] = held
    p = open_record(e, held)
    e.intelligence.journal = ManualJournal(e.db, e.settings, e.intelligence.cfg)
    assert e.deep_mints() == [held.mint]
    del e.tokens[held.mint]
    e.intelligence.refresh_positions(NOW + 1)
    row = e.intelligence.exit_results[p["position_id"]]
    assert row["monitoring"]["status"] == "MONITORING DEGRADED"
    assert row["exit"]["action"] == "DATA_STALE"
    assert not e.tokens  # No guessed restoration/admission or extra scans.


async def test_cold_engine_restart_restores_journal_priority_without_current_evidence(engine):
    e = engine
    held = candidate()
    e.tokens[held.mint] = held
    p = open_record(e, held)
    e.checkpoint(NOW)
    restored = RadarEngine(e.settings, e.db.path, offline=True)
    try:
        assert restored.manual_mints() == [held.mint]
        assert restored.deep_mints() == [held.mint]
        restored.intelligence.refresh_positions(NOW + 1)
        assert restored.intelligence.exit_results[p["position_id"]]["monitoring"]["status"] == "MONITORING DEGRADED"
        assert restored.trade_status(restored.tokens[held.mint], NOW + 1) != "CURRENT"
        assert not restored.tasks and restored.approved_evidence is None
    finally:
        await restored.stop()


def test_migration_preserves_monitoring_but_never_forces_pool_eligibility(engine):
    e = engine
    held = candidate()
    e.tokens[held.mint] = held
    p = open_record(e, held)
    assert e.process(MarketEvent(mint=held.mint, kind="migration", source="Solana WSS",
                                ts=NOW + 1, event_id="synthetic-migration"), NOW + 1)
    assert held.flow_venue == "PUMPSWAP" and held.flow_epoch == NOW + 1
    assert e.deep_mints() == [held.mint]
    assert not e.verified_flow_pools()
    e.intelligence.refresh_positions(NOW + 1)
    assert e.intelligence.exit_results[p["position_id"]]["monitoring"]["status"] == "MONITORING DEGRADED"
    assert e.trade_status(held, NOW + 1) != "CURRENT"


def test_exit_change_notifications_deduplicate_without_masking_different_risk(engine):
    e = engine
    held = candidate()
    e.tokens[held.mint] = held
    p = open_record(e, held)  # Initial missing mark creates DATA_STALE alert.
    e.intelligence.refresh_positions(NOW)
    assert len([a for a in e.alerts if a["level"] == "MANUAL_POSITION"]) == 1
    held.security["hard_failures"] = ["FROZEN"]
    e.intelligence.refresh_positions(NOW + 1)
    e.intelligence.refresh_positions(NOW + 2)
    alerts = [a for a in e.alerts if a["level"] == "MANUAL_POSITION"]
    assert len(alerts) == 2 and "THESIS_INVALIDATED" in alerts[-1]["message"]
    assert e.intelligence.exit_results[p["position_id"]]["exit"]["thesis_invalidated"]
    assert e.approved_evidence is None and not e.db.rows("paper_trade")
