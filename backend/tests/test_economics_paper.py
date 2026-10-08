import pytest
from backend.app.config import Settings
from backend.app.db import Base, Database
from backend.app.domain import Token, State
from backend.app.economics import TradeCostEstimator, PositionSizer, evaluate_candidate
from backend.app.paper import PaperAccount


def candidate(now=1000):
    t = Token("mint", "token", "TOK", now - 600, "creator")
    t.state = State.POST_GRAD_OBSERVATION
    t.security = {
        "data_quality": "VERIFIED",
        "risk_score": 10,
        "hard_failures": [],
        "warnings": [],
        "top_1_independent_pct": 4,
        "top_5_independent_pct": 15,
        "creator_pct": 2,
        "last_updated": now,
        "verified_pools": [{"base_mint": "mint"}],
    }
    t.graduation = now - 120
    t.grad_high = 1.2
    t.grad_low = 1
    t.price = 1.05
    t.liquidity = 25000
    t.last_price = t.last_trade = t.last_liquidity = now
    t.features = {
        "180": {
            "creator_sell_volume": 0,
            "estimated_independent_buyers": 40,
            "units_valid": True,
            "buy_pressure_persistence": 0.8,
            "whale_share": 0.1,
            "volatility_pct": 1,
        }
    }
    t.scores = {"maturity": 80, "momentum": 85, "chase": 10}
    s = Settings(mode="PAPER")
    estimator = TradeCostEstimator(s)
    t.viability = PositionSizer(s, estimator).size(20, t.liquidity, 5, 1)
    return t


def evidence():
    return {"count": 200, "lower_ci": 2, "expectancy_net_pct": 5}


def test_costs_break_even_and_small_account():
    s = Settings()
    c = TradeCostEstimator(s)
    assert c.estimate(4, None) is None
    cost = c.estimate(4, 25000, 0)
    assert cost["net_pnl_usd"] < 0
    point = c.break_even(4, 25000)
    assert c.estimate(4, 25000, point)["net_pnl_usd"] == pytest.approx(0, abs=1e-8)
    assert PositionSizer(s, c).size(20, 25000)["position_size_usd"] == 0
    assert PositionSizer(s, c).size(20, 25000, 5)["position_size_usd"] == 4
    assert c.estimate(4, 10)["estimated_price_impact_pct"] > 10


@pytest.mark.parametrize(
    "mutation,expected",
    [
        (lambda t: setattr(t, "last_price", 0), "WAIT"),
        (lambda t: setattr(t, "degraded", True), "WAIT"),
        (lambda t: setattr(t, "disagreement", True), "WAIT"),
        (lambda t: t.security.update(data_quality="UNKNOWN"), "WAIT"),
        (lambda t: t.security.update(hard_failures=["Active freezeAuthority"]), "REJECT"),
        (lambda t: t.scores.update(chase=80), "MISSED"),
        (lambda t: t.features["180"].update(creator_sell_volume=1), "REJECT"),
    ],
)
def test_gate(mutation, expected):
    t = candidate()
    assert evaluate_candidate(t, Settings(), 1000, evidence=evidence())["decision"] == "ALLOW_PAPER_ENTRY"
    mutation(t)
    assert evaluate_candidate(t, Settings(), 1000, evidence=evidence())["decision"] == expected


def test_provider_and_resource_gate():
    t = candidate()
    assert evaluate_candidate(t, Settings(), 1000, healthy=False, evidence=evidence())["decision"] == "WAIT"
    assert (
        evaluate_candidate(t, Settings(), 1000, resource_pressure=True, evidence=evidence())["decision"]
        == "WAIT"
    )
    assert evaluate_candidate(t, Settings(), 1000, evidence=None)["decision"] == "WAIT"


def test_delayed_fills_net_and_restart(tmp_path):
    db = Database(tmp_path / "paper.db")
    Base.metadata.create_all(db.engine)
    s = Settings(mode="PAPER", latency_ms=500)
    paper = PaperAccount(db, s, TradeCostEstimator(s))
    t = candidate()
    t.decision = evaluate_candidate(t, s, 1000, evidence=evidence())
    assert paper.request_entry(t, 1000, "v1")
    paper.observe(t, 1000.25)
    assert not paper.state["positions"]
    t.price = 1.10
    t.last_price = 1001
    paper.observe(t, 1001)
    position = paper.state["positions"]["mint"]
    assert position["entry_fill"] > 1.10 and position["signal_price"] == 1.05
    t.price = 1.40
    t.last_price = 1002
    paper.observe(t, 1002)
    assert paper.state["pending"]["mint"]["action"] == "exit"
    t.last_price = 1003
    paper.observe(t, 1003)
    assert paper.state["trades"] == 1 and paper.state["realized_net_pnl"] > 0
    assert paper.state["realized_net_pnl"] < paper.state["gross_pnl"]
    restart = PaperAccount(Database(db.path), s, TradeCostEstimator(s))
    assert restart.state == paper.state
    assert len(db.rows("paper_trade", mint="real")) == 2


def test_rejected_and_recheck_cannot_fill(tmp_path):
    db = Database(tmp_path / "paper.db")
    Base.metadata.create_all(db.engine)
    s = Settings(mode="PAPER")
    paper = PaperAccount(db, s, TradeCostEstimator(s))
    t = candidate()
    t.decision = {"decision": "REJECT"}
    assert not paper.request_entry(t, 1000, "v1")
    t.decision = {"decision": "ALLOW_PAPER_ENTRY"}
    assert paper.request_entry(t, 1000, "v1")
    t.decision = {"decision": "WAIT"}
    t.last_price = 1001
    paper.observe(t, 1001)
    assert not paper.state["positions"] and paper.state["cash"] == 20


def test_atomic_account_memory_rollback(tmp_path, monkeypatch):
    db = Database(tmp_path / "atomic.db")
    Base.metadata.create_all(db.engine)
    settings = Settings(mode="PAPER")
    paper = PaperAccount(db, settings, TradeCostEstimator(settings))
    t = candidate()
    t.decision = evaluate_candidate(t, settings, 1000, evidence=evidence())

    def fail():
        raise RuntimeError("simulated database failure")

    monkeypatch.setattr(db.sessions, "begin", fail)
    with pytest.raises(RuntimeError):
        paper.request_entry(t, 1000, "v1")
    assert paper.state["cash"] == 20 and not paper.state["pending"]
