"""Synthetic approval-boundary regressions; no actual cohort or network acquisition."""

import pytest

from backend.app.config import Settings
from backend.app.engine import RadarEngine


@pytest.mark.asyncio
async def test_positive_retrospective_record_cannot_authorize_restart(tmp_path):
    path = tmp_path / "synthetic.db"
    settings = Settings(mode="OBSERVE")
    engine = RadarEngine(settings, path, offline=True)
    try:
        engine.db.add("evidence", {
            "version": engine.version, "mode": "OBSERVE",
            "holdout": {"count": 200, "lower_ci": 2, "expectancy_net_pct": 5,
                        "status": "POSITIVE EXPECTANCY OBSERVED"},
            "evaluation": {"missing_outcomes": 0, "capacity_limited": False},
        })
        original = engine.db.rows("evidence")
    finally:
        await engine.stop()
    restarted = RadarEngine(settings, path, offline=True)
    try:
        assert restarted.approved_evidence is None
        assert restarted.db.rows("evidence") == original
    finally:
        await restarted.stop()


@pytest.mark.parametrize("mode", ["OBSERVE", "PAPER", "MANUAL ASSIST", "DEMO"])
@pytest.mark.parametrize("record", [
    {"approved": True, "status": "APPROVED"},
    {"provenance": {"cohort_id": "forged", "prospective": True, "integrity": "VERIFIED"}},
    {"version": "wrong-strategy", "config_hash": "wrong-config"},
    {"mode": "DEMO"},
    {"mode": "PAPER"},
    {"evaluation": {"missing_outcomes": 1}},
    {"quality": {"storage_censored": True, "recovery_overflow": 1}},
    {"holdout": "malformed"},
])
async def test_stored_flags_or_provenance_never_authorize(tmp_path, mode, record):
    settings = Settings(mode=mode)
    path = tmp_path / "synthetic.db"
    engine = RadarEngine(settings, path, offline=True)
    try:
        payload = {"version": engine.version, "mode": mode,
                   "holdout": {"count": 1000, "lower_ci": 10, "expectancy_net_pct": 20}, **record}
        engine.db.add("evidence", payload)
        original = engine.db.rows("evidence")
    finally:
        await engine.stop()
    restarted = RadarEngine(settings, path, offline=True)
    try:
        assert restarted.approved_evidence is None
        assert restarted.db.rows("evidence") == original
        assert restarted.paper.state["cash"] == 20
        assert not restarted.db.rows("paper_trade")
    finally:
        await restarted.stop()


def test_freeze_refused_before_engine_environment_or_evaluation(monkeypatch, capsys, tmp_path):
    from backend.app import cli

    def forbidden(*args, **kwargs):
        pytest.fail("Disabled approval must not construct an engine or evaluate/write anything")

    output = tmp_path / "must-not-exist.json"
    monkeypatch.setattr("sys.argv", ["radar", "freeze-evidence", "--output", str(output)])
    monkeypatch.setattr(cli, "RadarEngine", forbidden)
    monkeypatch.setattr(cli, "evaluate", forbidden)
    monkeypatch.setattr(cli, "load_dotenv", forbidden)
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 2
    assert "retrospective evaluation cannot authorize entries" in capsys.readouterr().err
    assert not output.exists()


def test_missing_approval_keeps_size_zero_and_entry_wait():
    from backend.tests.test_economics_paper import candidate
    from backend.app.economics import PositionSizer, TradeCostEstimator, evaluate_candidate
    from backend.app.companion import companion_view

    settings = Settings(mode="PAPER", trade_stream_enabled=True)
    token = candidate()
    token.viability = PositionSizer(settings, TradeCostEstimator(settings)).size(
        20, token.liquidity, historical_edge_pct=None, volatility_pct=1
    )
    token.decision = evaluate_candidate(token, settings, 1000, evidence=None)
    assert token.viability["position_size_usd"] == 0
    assert token.viability["proposed_position_usd"] == 4
    assert token.decision["decision"] == "WAIT"
    assert "Insufficient positive holdout evidence" in token.decision["reasons"]
    assert companion_view(token, settings, 1000, evidence=None).action == "WAIT"


def test_descriptive_evaluation_still_works_without_approval(monkeypatch, capsys, tmp_path):
    from types import SimpleNamespace
    from backend.app import cli
    import json

    rows = []
    disposed = []
    result = {"sample_count": 1000, "holdout": {"status": "POSITIVE EXPECTANCY OBSERVED"}}
    fake = SimpleNamespace(db=SimpleNamespace(
        add=lambda kind, value: rows.append((kind, value)),
        engine=SimpleNamespace(dispose=lambda: disposed.append(True))), version="test")
    output = tmp_path / "descriptive.json"
    monkeypatch.setattr("sys.argv", ["radar", "evaluate", "--output", str(output)])
    monkeypatch.setattr(cli, "load_dotenv", lambda *args: None)
    monkeypatch.setattr(cli, "load_settings", lambda: Settings())
    monkeypatch.setattr(cli, "RadarEngine", lambda settings: fake)
    monkeypatch.setattr(cli, "evaluate", lambda *args: result)
    cli.main()
    assert json.loads(output.read_text()) == result
    assert rows == [("evaluation", result)] and disposed == [True]
    assert json.loads(capsys.readouterr().out) == result
