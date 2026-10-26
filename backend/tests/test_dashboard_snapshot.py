"""Offline HTTP/SSE serialization: no providers, workers or live databases."""

import asyncio
from copy import deepcopy
import json
import time
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import event as sql_event

from backend.app.config import Settings
from backend.app.domain import MarketEvent
from backend.app.engine import RadarEngine
from backend.app.main import create_app, dashboard_json


@pytest.fixture
async def engine(tmp_path):
    engine = RadarEngine(Settings(mode="OBSERVE"), tmp_path / "isolated.db", offline=True)
    engine.process(MarketEvent(kind="create", mint="synthetic", ts=time.time(),
                               source="SYNTHETIC", event_id="create"))
    yield engine
    await engine.stop()
    engine.db.engine.dispose()


def stream_route(app):
    return next(route.endpoint for route in app.routes if getattr(route, "path", "") == "/api/events")


class Viewer:
    def __init__(self):
        self.app = None
        self.closed = False

    async def is_disconnected(self):
        return self.closed


async def test_http_equivalent_json_without_recursive_conversion(engine, monkeypatch):
    monkeypatch.setattr(time, "time", lambda: 10000.0)
    expected = json.loads(json.dumps(engine.snapshot(), allow_nan=False))
    before = deepcopy((engine.paper.state, engine.approved_evidence,
                       engine.accounting.snapshot(engine.queue), engine.tokens["synthetic"].decision,
                       engine.intelligence.results, engine.tokens["synthetic"].features))
    sql = []

    def query(*args):
        sql.append(True)

    sql_event.listen(engine.db.engine, "before_cursor_execute", query)
    try:
        app = create_app()
        app.state.engine = engine

        def forbidden(*args, **kwargs):
            raise AssertionError("Dashboard must not recursively convert JSON-native values")

        monkeypatch.setattr("fastapi.routing.jsonable_encoder", forbidden)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://testserver") as client:
            response = await client.get("/api/dashboard")
        assert response.status_code == 200
        assert response.json() == expected
        assert response.headers["content-type"] == "application/json"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert int(response.headers["content-length"]) == len(response.content)
        assert not sql
        assert before == (engine.paper.state, engine.approved_evidence,
                          engine.accounting.snapshot(engine.queue), engine.tokens["synthetic"].decision,
                          engine.intelligence.results, engine.tokens["synthetic"].features)
    finally:
        sql_event.remove(engine.db.engine, "before_cursor_execute", query)


def test_compact_encoding_preserves_values_and_rejects_nonfinite():
    value = {"text": "研究\nline", "array": [1, None, True], "fraction": .125}
    encoded = dashboard_json(SimpleNamespace(snapshot=lambda: value))
    assert json.loads(encoded) == value
    assert len(encoded) < len(json.dumps(value))
    with pytest.raises(ValueError):
        dashboard_json(SimpleNamespace(snapshot=lambda: {"bad": float("nan")}))
    with pytest.raises(RuntimeError, match="original"):
        dashboard_json(SimpleNamespace(snapshot=lambda: (_ for _ in ()).throw(RuntimeError("original"))))


async def test_demo_http_matches_legacy_json_conversion(tmp_path, monkeypatch):
    from fastapi.encoders import jsonable_encoder

    engine = RadarEngine(Settings(mode="DEMO"), tmp_path / "demo.db", offline=True)
    try:
        engine.process(MarketEvent(kind="create", mint="synthetic-demo", ts=time.time(),
                                   source="DEMO", event_id="demo"))
        monkeypatch.setattr(time, "time", lambda: 10000.0)
        expected = json.loads(json.dumps(jsonable_encoder(engine.snapshot()), allow_nan=False))
        app = create_app()
        app.state.engine = engine
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://testserver") as client:
            result = await client.get("/api/dashboard")
        assert result.status_code == 200
        assert result.json() == expected
        assert result.json()["simulated"] is True
    finally:
        await engine.stop()
        engine.db.engine.dispose()


async def test_each_viewer_gets_new_snapshot_and_disconnect_stops_work(engine, monkeypatch):
    original = engine.snapshot
    calls = []

    def observed():
        calls.append(True)
        return original()

    monkeypatch.setattr(engine, "snapshot", observed)
    app = create_app()
    app.state.engine = engine
    route = stream_route(app)
    viewers = [Viewer(), Viewer()]
    responses = [await route(viewer) for viewer in viewers]
    bodies = [response.body_iterator for response in responses]
    first = [json.loads((await anext(body))[6:]) for body in bodies]
    assert len(calls) == 2
    assert all(value["tokens"][0]["mint"] == "synthetic" for value in first)
    assert all(response.media_type == "text/event-stream" for response in responses)
    assert all(response.headers["cache-control"] == "no-cache" for response in responses)
    for viewer, body in zip(viewers, bodies):
        viewer.closed = True
        # Closing a generator must not leave a publisher/background worker.
        await body.aclose()
    third = Viewer()
    third.closed = True
    response = await route(third)
    with pytest.raises(StopAsyncIteration):
        await anext(response.body_iterator)
    assert len(calls) == 2
    engine.process(MarketEvent(kind="create", mint="new-synthetic", ts=time.time(),
                               source="SYNTHETIC", event_id="second"))
    value = json.loads(dashboard_json(engine))
    assert {t["mint"] for t in value["tokens"]} == {"synthetic", "new-synthetic"}


async def test_sse_cancellation_during_original_cadence_leaves_no_task(engine):
    app = create_app()
    app.state.engine = engine
    body = (await stream_route(app)(Viewer())).body_iterator
    await anext(body)
    task = asyncio.create_task(anext(body))
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await body.aclose()
    assert task.done()
    assert not engine.tasks


async def test_two_viewers_follow_queued_changes_without_replay_or_cadence_change(engine, monkeypatch):
    import backend.app.main as main

    sleeps = []
    original_sleep = asyncio.sleep

    async def cadence(seconds):
        sleeps.append(seconds)
        await original_sleep(0)

    monkeypatch.setattr(main, "asyncio", SimpleNamespace(sleep=cadence))
    app = create_app()
    app.state.engine = engine
    viewers = [Viewer(), Viewer()]
    bodies = [(await stream_route(app)(viewer)).body_iterator for viewer in viewers]
    try:
        for body in bodies:
            await anext(body)
        engine.submit(MarketEvent(kind="create", mint="queued-new", ts=time.time(),
                                   source="SYNTHETIC", event_id="queued"))
        await engine.drain_events()
        before = deepcopy(engine.accounting.snapshot(engine.queue))
        frames = await asyncio.gather(*(anext(body) for body in bodies))
        assert sleeps == [2, 2]
        for frame in frames:
            assert "queued-new" in {t["mint"] for t in json.loads(frame[6:])["tokens"]}
        assert before == engine.accounting.snapshot(engine.queue)
        creates = before["events"]["create"]
        assert creates["reconciled"] and creates["in_processing"] == creates["pending"] == 0
        assert creates["persisted"] == 1
    finally:
        for body in bodies:
            await body.aclose()


async def test_no_cached_evidence_after_expiration_or_continuity_loss(engine, monkeypatch):
    now = time.time()
    clock = [now]
    monkeypatch.setattr(time, "time", lambda: clock[0])
    token = engine.tokens["synthetic"]
    token.trade_tracking_since = now - 200
    token.last_trade = now
    token.last_curve = now
    token.curve_progress = 40
    token.features["180"].update(samples=3, units_valid=True, continuity_valid=True,
                                  trade_evidence="CURRENT", estimated_independent_buyers=3,
                                  flow_ratio=2)
    token.security = {"data_quality": "VERIFIED", "last_updated": now, "hard_failures": []}
    engine.onchain.health.update(connected=True, connected_since=now - 200)
    first = json.loads(dashboard_json(engine))["tokens"][0]
    assert first["trade_evidence"] == "CURRENT"
    clock[0] = now + 21
    stale = json.loads(dashboard_json(engine))["tokens"][0]
    assert stale["trade_evidence"] != "CURRENT"
    assert stale["companion"]["trade_evidence"] != "CURRENT"
    clock[0] = now + 301
    assert json.loads(dashboard_json(engine))["tokens"][0]["companion"]["security_quality"] == "STALE"
    engine.invalidate_trade_coverage()
    assert json.loads(dashboard_json(engine))["tokens"][0]["trade_evidence"] != "CURRENT"
    assert engine.approved_evidence is None
    assert not engine.paper.state["positions"]
    assert engine.accounting.snapshot(engine.queue)["events"]["create"]["reconciled"]
