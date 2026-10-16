from copy import deepcopy

from backend.app.opportunity import IntelligenceSettings, opportunity_view
from backend.app.opportunity_research import OpportunityResearch
from backend.app.manual import MarketInput
import pytest
from backend.app.engine import RadarEngine
from backend.app.config import Settings
from backend.tests.test_opportunity import candidate, NOW


@pytest.fixture
async def engine(tmp_path):
    e = RadarEngine(Settings(), tmp_path / "prospective.db")
    t = candidate()
    e.tokens[t.mint] = t
    yield e, t
    await e.stop()


def research(e):
    cfg = IntelligenceSettings(horizons=[60, 180])
    return OpportunityResearch(e.db, e.settings, cfg, e.session), cfg


def update_curve(t, stamp, value):
    t.curve_progress = value
    t.last_curve = stamp
    t.curve_history.append((stamp, value))
    t.curve_peak_progress = max(value, t.curve_peak_progress or 0)


def test_prospective_features_and_horizons_exclude_future_values(engine):
    e, t = engine
    r, cfg = research(e)
    original = opportunity_view(t, e.settings, NOW, cfg)
    r.transition(t, original, NOW, e.version)
    frozen = deepcopy(e.db.rows("opportunity_signal")[0])
    update_curve(t, NOW + 30, 55)
    r.observe(t, NOW + 30)
    update_curve(t, NOW + 61, 99)
    r.observe(t, NOW + 61)
    first = e.db.rows("opportunity_outcome")[0]
    assert first["horizon"] == 60 and first["max_subsequent_curve"] == 55
    assert first["endpoint_curve"] == 55 and first["curve_observed_at"] == NOW + 30
    assert e.db.rows("opportunity_signal")[0] == frozen
    assert first["forward_return_pct"] is None and first["estimated_after_cost_return_pct"] is None
    update_curve(t, NOW + 181, 100)
    r.observe(t, NOW + 181)
    assert e.db.rows("opportunity_outcome")[-1]["max_subsequent_curve"] == 99
    assert not r.pending and not r.by_mint
    assert not e.db.rows("evidence") and e.paper.state["cash"] == 20


def test_restart_pending_and_missing_outcomes_are_explicit(engine):
    e, t = engine
    r, cfg = research(e)
    r.transition(t, opportunity_view(t, e.settings, NOW, cfg), NOW, e.version)
    restored = OpportunityResearch(e.db, e.settings, cfg, "new-session")
    assert len(restored.pending) == 1
    restored.expire(NOW + 2000)
    outcomes = e.db.rows("opportunity_outcome")
    assert len(outcomes) == 2 and all(o["status"] == "UNAVAILABLE_GAP" for o in outcomes)
    assert all(o["endpoint_curve"] is None for o in outcomes)


def test_pending_capacity_actions_and_manual_data_are_bounded_isolated(engine):
    e, t = engine
    r, cfg = research(e)
    r.LIMIT = 2
    for _ in range(3):
        token = candidate()
        r.transition(token, opportunity_view(token, e.settings, NOW, cfg), NOW, e.version)
    assert len(r.pending) == 2
    assert len(e.db.rows("opportunity_outcome")) == 2
    assert all(o["status"] == "UNAVAILABLE_CAPACITY" for o in e.db.rows("opportunity_outcome"))
    before = deepcopy(t.decision)
    e.intelligence.journal.observe_market(MarketInput(mint=t.mint, price_usd=1000000), NOW)
    e.intelligence.observe(t, NOW)
    signal = e.db.rows("opportunity_signal")[-1]
    assert signal["projection"]["market_context"]["source"] == "PROVIDER: DEX Screener"
    assert signal["provider_price_usd"] is None
    assert t.decision == before


def test_real_transitions_debounce_and_demo_does_not_log(engine):
    e, t = engine
    t.security["data_quality"] = "UNKNOWN"
    t.curve_history.pop()
    t.last_curve, t.curve_progress = t.curve_history[-1]
    e.intelligence.observe(t, NOW - 60)
    update_curve(t, NOW, 48)
    e.intelligence.observe(t, NOW)
    count = len(e.db.rows("opportunity_signal"))
    for _ in range(5):
        e.intelligence.observe(t, NOW)
    assert len(e.db.rows("opportunity_signal")) == count
    assert sum(a["level"] == "OPPORTUNITY" for a in e.alerts) == 1
    e.settings.mode = "DEMO"
    update_curve(t, NOW + 30, 55)
    e.intelligence.observe(t, NOW + 30)
    assert len(e.db.rows("opportunity_signal")) == count


def test_outcome_and_horizon_checkpoint_commit_atomically(engine):
    from sqlalchemy import event

    e, t = engine
    r, cfg = research(e)
    r.transition(t, opportunity_view(t, e.settings, NOW, cfg), NOW, e.version)
    identity = next(iter(r.pending))

    def fail(conn, cursor, statement, parameters, context, many):
        if statement.startswith("INSERT INTO records") and "opportunity_outcome" in parameters:
            raise RuntimeError("Injected outcome write failure")

    event.listen(e.db.engine, "before_cursor_execute", fail)
    try:
        with pytest.raises(RuntimeError):
            r.expire(NOW + 61)
    finally:
        event.remove(e.db.engine, "before_cursor_execute", fail)
    assert r.pending[identity]["remaining"] == [60, 180]
    assert not e.db.rows("opportunity_outcome")
    r.expire(NOW + 61)
    restored = OpportunityResearch(e.db, e.settings, cfg, e.session)
    assert restored.pending[identity]["remaining"] == [180]
    r.expire(NOW + 61)
    assert len(e.db.rows("opportunity_outcome")) == 1
