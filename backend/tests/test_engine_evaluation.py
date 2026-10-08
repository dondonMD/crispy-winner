from backend.app.config import Settings
from backend.app.demo import demo_events
from backend.app.domain import MarketEvent
from backend.app.engine import RadarEngine
from backend.app.evaluation import replay, Summary
from backend.app.main import create_app
import httpx


def test_demo_funnel_migration_replay(tmp_path):
    engine = RadarEngine(Settings(mode="DEMO"), tmp_path / "test.db")
    for tick in range(170):
        for event in demo_events(1000, tick):
            engine.process(event, event.ts)
    assert len(engine.tokens) == 12
    assert engine.tokens["DEMO09simulated"].graduation == 1090
    assert engine.tokens["DEMO09simulated"].state.value == "POST_GRAD_OBSERVATION"
    assert engine.tokens["DEMO03simulated"].state.value == "REJECTED"
    assert engine.paper.state["cash"] == 20
    result = replay(engine.db, engine.session)
    assert result["scores_match"] is True
    assert result["decisions_match"] is True
    assert result["states_match"] is True
    assert result["events_replayed"] == engine.processed
    rows = engine.db.rows("outcome", limit=10000)
    assert any(r.get("status") == "MEASURED" for r in rows)
    for r in rows:
        if r.get("status") == "MEASURED":
            assert r["ts"] >= r["signal_ts"] + r["horizon"]


def test_duplicates_and_out_of_order(tmp_path):
    e = RadarEngine(Settings(mode="DEMO"), tmp_path / "test.db")
    event = MarketEvent(mint="test", ts=100, source="DEMO", kind="create", event_id="new")
    assert e.process(event)
    assert not e.process(event)
    late = MarketEvent(mint="test", ts=90, source="DEMO", kind="trade", event_id="late")
    assert not e.process(late, 100)
    assert e.tokens["test"].degraded and e.duplicates == 1


def test_small_samples_never_positive_label():
    s = Summary(100)
    for _ in range(10):
        s.add(10)
    assert s.result()["status"] == "INSUFFICIENT DATA"


async def test_api_demo_and_local_security(tmp_path):
    app = create_app(Settings(mode="DEMO"), tmp_path / "test.db")
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            assert (await client.get("/api/health")).json()["mode"] == "DEMO"
            body = (await client.get("/api/dashboard")).json()
            assert body["simulated"] and body["paper"]["starting_balance"] == 20
            assert (await client.get("/api/health", headers={"host": "evil.example"})).status_code == 403
            assert (await client.get("/api/tokens/does-not-exist")).status_code == 404
            assert (await client.get("/api/paper/trades")).json() == []


def test_restart_event_dedup_and_real_demo_isolation(tmp_path):
    path = tmp_path / "restart.db"
    e = RadarEngine(Settings(mode="DEMO"), path)
    event = MarketEvent(mint="test", ts=100, source="DEMO", kind="create", event_id="new")
    assert e.process(event)
    e.checkpoint(101)
    e.db.engine.dispose()
    restarted = RadarEngine(Settings(mode="DEMO"), path)
    assert not restarted.process(event)
    assert restarted.duplicates == 1
    real = RadarEngine(Settings(mode="OBSERVE"), tmp_path / "real.db")
    assert not real.process(event)
    assert not real.tokens and real.paper.state["cash"] == 20


def test_evaluation_first_signal_missing_is_not_replaced(tmp_path):
    from backend.app.evaluation import evaluate

    e = RadarEngine(Settings(mode="DEMO"), tmp_path / "selection.db")
    first = e.db.add(
        "signal",
        {"mode": "DEMO", "strategy_version": e.version, "eligible_research": True},
        "test",
        e.session,
        100,
    )
    second = e.db.add(
        "signal",
        {"mode": "DEMO", "strategy_version": e.version, "eligible_research": True},
        "test",
        e.session,
        200,
    )
    e.db.add(
        "outcome", {"signal_id": first, "horizon": 300, "status": "UNAVAILABLE_GAP"}, "test", e.session, 500
    )
    e.db.add(
        "outcome",
        {"signal_id": second, "horizon": 300, "status": "MEASURED", "net_return_pct": 100},
        "test",
        e.session,
        600,
    )
    result = evaluate(e.db, e.settings, "demo", e.version, 300, 1000)
    assert result["eligible_due_signals"] == 1 and result["missing_outcomes"] == 1
    assert result["sample_count"] == 0 and result["coverage_pct"] == 0


async def test_resource_pressure_survives_and_blocks_expansion(tmp_path, monkeypatch):
    import asyncio

    e = RadarEngine(Settings(mode="DEMO"), tmp_path / "pressure.db")
    metrics = {**e.metrics, "resource_pressure": True, "rss_mb": 720}
    monkeypatch.setattr(e.resources, "sample", lambda: metrics.copy())
    e.metrics = metrics.copy()
    await e.start()
    try:
        await asyncio.sleep(0.3)
        assert e.running and all(not t.done() for t in e.tasks)
        assert not e.tokens and e.snapshot()["health"]["resource_pressure"]
        assert e.paper.state["cash"] == 20
    finally:
        await e.stop()


def test_storage_full_blocks_expendable_records(tmp_path):
    e = RadarEngine(Settings(mode="DEMO"), tmp_path / "full.db")
    e.metrics["storage_full"] = True
    event = MarketEvent(mint="test", ts=100, source="DEMO", kind="create", event_id="new")
    assert not e.process(event)
    assert not e.db.rows("event")
    assert e.db.rows("paper_account") and e.db.rows("strategy")
