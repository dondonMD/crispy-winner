from copy import deepcopy
import pytest
from backend.app.companion import companion_view
from backend.app.config import Settings
from backend.app.domain import State, Token
from backend.app.demo import companion_examples
from backend.app.economics import evaluate_candidate
from backend.app.engine import RadarEngine
from test_economics_paper import candidate, evidence

S = Settings(mode="OBSERVE", trade_stream_enabled=True)


def entry():
    t = candidate()
    t.features["180"]["flow_ratio"] = 3.0
    t.decision = evaluate_candidate(t, S, 1000, evidence=evidence())
    return t


@pytest.mark.parametrize(
    "core,action",
    [
        ("WAIT", "WAIT"),
        ("REJECT", "REJECT"),
        ("MISSED", "TOO_LATE"),
        ("ALLOW_PAPER_ENTRY", "ENTRY_CANDIDATE"),
    ],
)
def test_mapping(core, action):
    t = entry()
    t.decision["decision"] = core
    assert companion_view(t, S, 1000, evidence=evidence()).action == action


@pytest.mark.parametrize(
    "mutation,action",
    [
        (lambda t: t.viability.update(economically_viable=False), "WAIT"),
        (lambda t: t.viability.update(position_size_usd=0), "WAIT"),
        (lambda t: t.viability.update(position_size_usd=None), "WAIT"),
        (lambda t: setattr(t, "last_trade", 0), "WAIT"),
        (lambda t: t.security.update(data_quality="UNKNOWN"), "WAIT"),
        (lambda t: t.security.update(last_updated=1), "WAIT"),
        (lambda t: t.security.update(last_updated=1001), "WAIT"),
        (lambda t: t.security.update(data_quality="SIMULATED"), "WAIT"),
        (lambda t: t.security.update(hard_failures=["Freeze authority"]), "REJECT"),
        (lambda t: setattr(t, "liquidity", None), "WAIT"),
        (lambda t: setattr(t, "price", 0), "WAIT"),
        (lambda t: setattr(t, "price", float("nan")), "WAIT"),
        (lambda t: t.viability.update(position_size_usd=True), "WAIT"),
        (lambda t: t.viability.update(position_size_usd=float("inf")), "WAIT"),
        (lambda t: setattr(t, "last_price", 1), "WAIT"),
        (lambda t: t.scores.update(chase=100), "TOO_LATE"),
    ],
)
def test_stored_entry_is_revalidated(mutation, action):
    t = entry()
    mutation(t)
    view = companion_view(t, S, 1000, evidence=evidence())
    assert view.action == action
    assert view.manual_position_cap_usd is None
    assert view.blockers


def test_missing_history_or_health_fail_closed():
    t = entry()
    for kwargs in [
        dict(evidence=None),
        dict(healthy=False),
        dict(resource_pressure=True),
    ]:
        args = dict(settings=S, evidence=evidence()) | kwargs
        assert companion_view(t, now=1000, **args).action == "WAIT"


@pytest.mark.parametrize("progress", [87, 99])
def test_lifecycle_alone_is_wait_and_peak_is_separate(progress):
    t = Token("mint", "name", "TOK", 900, state=State.NEAR_GRADUATION)
    t.curve_progress, t.curve_peak_progress, t.last_curve = progress, 99, 1000
    view = companion_view(t, S, 1000)
    assert view.action == "WAIT" and view.attention == "HIGH"
    assert (view.curve_progress, view.curve_peak_progress) == (progress, 99)
    assert view.security_quality == "UNKNOWN" and view.security_risk_score is None
    assert t.liquidity is None and t.viability == {}
    t.state, t.curve_progress = State.MATURING, 60.2
    regressed = companion_view(t, S, 1000)
    assert regressed.attention == "MEDIUM" and regressed.action == "WAIT"
    assert regressed.lifecycle == "MATURING" and regressed.curve_peak_progress == 99


def test_deterministic_nonmutating_nulls_and_missed_reason():
    t = entry()
    t.decision["decision"] = "MISSED"
    t.decision["reasons"] = ["MISSED — DO NOT CHASE"]
    t.viability.update(costs=None, break_even_move_pct=None)
    before = deepcopy(t)
    a = companion_view(t, S, 1000, evidence=evidence())
    assert a == companion_view(t, S, 1000, evidence=evidence())
    assert t == before
    assert a.action == "TOO_LATE" and a.chase_risk == 10
    assert "MISSED — DO NOT CHASE" in a.blockers
    assert t.viability["costs"] is None


def test_demo_examples_isolated_and_real_never_gets_defaults():
    examples = companion_examples(Settings(mode="DEMO"), 1000)
    assert {t["companion"]["action"] for t in examples} == {"WAIT", "REJECT", "TOO_LATE", "ENTRY_CANDIDATE"}
    assert all("SIMULATED" in t["name"] for t in examples)
    assert companion_examples(S, 1000) == []
    assert companion_view(entry(), S, 1000).action == "WAIT"


def test_demo_entry_has_coherent_flow_and_wait_has_unavailable_evidence():
    examples = companion_examples(Settings(mode="DEMO"), 1000)
    assert examples == companion_examples(Settings(mode="DEMO"), 1000)
    demo_entry, wait = examples[:2]
    flow = demo_entry["features"]
    assert demo_entry["companion"]["trade_evidence"] == "CURRENT"
    assert demo_entry["companion"]["evidence_quality"]["Trade flow"] == "CURRENT"
    assert flow["estimated_independent_buyers"] > 0
    assert flow["flow_ratio"] == flow["buy_volume"] / flow["sell_volume"] == 3
    assert flow["net_flow"] == flow["buy_volume"] - flow["sell_volume"]
    assert wait["companion"]["action"] == "WAIT"
    assert wait["companion"]["trade_evidence"] == "UNAVAILABLE"
    assert wait["companion"]["evidence_quality"]["Trade flow"] == "UNAVAILABLE"
    assert "flow_ratio" not in wait["features"]


@pytest.mark.parametrize("field", ["flow_ratio", "estimated_independent_buyers"])
@pytest.mark.parametrize("value", [None, True, -1, float("nan"), float("inf"), "3"])
def test_missing_or_invalid_structured_trade_fails_closed(field, value):
    t = entry()
    t.features["180"][field] = value
    before = deepcopy(t)
    view = companion_view(t, S, 1000, evidence=evidence())
    assert view.action == "WAIT"
    assert view.trade_evidence == "UNAVAILABLE"
    assert view.manual_position_cap_usd is None
    assert "Need observed trade/buyer evidence" in view.missing_evidence
    assert t == before


def test_absent_flow_does_not_change_observe_core_decision():
    t = entry()
    del t.features["180"]["flow_ratio"]
    before = deepcopy(t)
    assert evaluate_candidate(t, S, 1000, evidence=evidence())["decision"] == "ALLOW_PAPER_ENTRY"
    assert companion_view(t, S, 1000, evidence=evidence()).action == "WAIT"
    assert t == before
    assert companion_examples(S, 1000) == []


@pytest.mark.parametrize("field", ["flow_ratio", "estimated_independent_buyers", "units_valid"])
def test_absent_required_trade_fields_fail_closed(field):
    t = entry()
    del t.features["180"][field]
    view = companion_view(t, S, 1000, evidence=evidence())
    assert view.action == "WAIT"
    assert view.trade_evidence == "UNAVAILABLE"


def test_engine_snapshot_detail_share_current_view_without_provider_activity(tmp_path):
    engine = RadarEngine(Settings(mode="OBSERVE"), tmp_path / "test.db", offline=True)
    try:
        t = entry()
        engine.tokens[t.mint] = t
        before = deepcopy([p.health for p in [engine.rpc, engine.pump, engine.dex]])
        snap = engine.snapshot()
        detail = engine.token_view(t, snap["timestamp"], detail=True)
        assert detail["companion"] == snap["tokens"][0]["companion"]
        assert detail["companion"]["action"] == "WAIT"
        assert snap["companion_examples"] == []
        assert before == [p.health for p in [engine.rpc, engine.pump, engine.dex]]
        assert engine.paper.state["cash"] == 20
    finally:
        engine.db.engine.dispose()
