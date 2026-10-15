"""Shared RPC pressure recovery and scheduling, using a deterministic wall clock."""

import json
from unittest.mock import AsyncMock

import httpx
import pytest
from solders.pubkey import Pubkey

from backend.app.config import Settings
from backend.app.engine import RadarEngine
from backend.app.providers import SolanaProvider
from backend.tests.test_lifecycle_fairness import launch


async def test_repeated_429_and_gradual_recovery(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr("backend.app.providers.time.time", lambda: clock[0])
    calls = []
    limited = [True]

    def handler(request):
        calls.append(json.loads(request.content))
        return (
            httpx.Response(429, headers={"Retry-After": "240"})
            if limited[0]
            else httpx.Response(200, json={"result": {"value": []}})
        )

    rpc = SolanaProvider(httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    rpc.limiter.wait = AsyncMock()
    try:
        for level in range(1, 5):
            with pytest.raises(RuntimeError):
                await rpc.rpc("getMultipleAccounts", [])
            assert len(calls) == level  # Default retries never multiply a 429.
            assert rpc.health["backoff_level"] == level
            assert rpc.health["rate_limited_until"] == clock[0] + 240
            assert not rpc.eligible("security")
            with pytest.raises(RuntimeError):
                await rpc.inspect(str(Pubkey.new_unique()))
            assert len(calls) == level
            assert RadarEngine.provider_health(rpc.health)["status"] == "RATE LIMITED"
            clock[0] += 241
        assert rpc.interval(30, "hot") == 120
        assert rpc.interval(30, "background") > rpc.interval(30, "hot")
        assert rpc.interval(30, "security") > rpc.interval(30, "hot")
        assert not rpc.eligible("background") and rpc.eligible("hot")
        limited[0] = False
        await rpc.rpc("getMultipleAccounts", [])
        assert rpc.health["backoff_level"] == 4
        assert RadarEngine.provider_health(rpc.health)["status"] == "BACKING OFF"
        for expected in [3, 2, 1, 0]:
            for _ in range(3):
                clock[0] += 60
                await rpc.rpc("getMultipleAccounts", [])
            assert rpc.health["backoff_level"] == expected
        assert RadarEngine.provider_health(rpc.health)["status"] == "CURRENT"
        assert rpc.health["errors"] == rpc.health["rate_limits"] == 4
    finally:
        await rpc.close()


async def test_pressure_scheduler_hot_security_and_background(tmp_path, monkeypatch):
    clock = [10000.0]
    monkeypatch.setattr("backend.app.engine.time.time", lambda: clock[0])
    engine = RadarEngine(Settings(max_candidates=4, max_deep=1), tmp_path / "pressure.db")
    for _ in range(4):
        launch(engine, str(Pubkey.new_unique()), clock[0])
    engine.rpc.curve_progress_batch = AsyncMock(return_value={})
    engine.rpc.inspect = AsyncMock(return_value={})
    engine.dex.markets = AsyncMock(return_value=[])
    hot = engine.tokens[engine.deep_mints()[0]]
    hot.curve_progress = 90
    hot.last_curve = clock[0]
    hot.last_curve_attempt = clock[0] - 31
    engine.last_security_scan = clock[0]
    engine.rpc.health.update(
        backoff_level=4, rate_limited_until=clock[0] + 10, next_eligible_rpc=clock[0] + 10
    )
    try:
        await engine.enrich_once()
        engine.rpc.inspect.assert_not_awaited()
        engine.rpc.curve_progress_batch.assert_not_awaited()
        clock[0] += 11
        await engine.enrich_once()
        engine.rpc.curve_progress_batch.assert_not_awaited()  # Hot interval is now 120s.
        # Security scan cadence also scales, even with a current high curve.
        engine.last_security_scan = clock[0]
        clock[0] += 80
        hot.last_curve = clock[0]
        await engine.enrich_once()
        engine.rpc.curve_progress_batch.assert_awaited_once()
        engine.rpc.inspect.assert_not_awaited()
        assert engine.curve_metrics["curve_background_poll_requests"] == 0
        # A newly due hot member cannot bypass the provider-wide hot batch cadence.
        hot.last_curve_attempt = 0
        clock[0] += 30
        await engine.enrich_once()
        engine.rpc.curve_progress_batch.assert_awaited_once()
        # A bounded background recovery probe eventually permits oldest-first work.
        clock[0] += 500
        await engine.enrich_once()
        assert engine.curve_metrics["curve_background_poll_requests"] == 1
    finally:
        await engine.stop()


async def test_websocket_backoff_resets_only_after_stable_connection(monkeypatch):
    import asyncio
    from websockets.exceptions import ConnectionClosedError
    from backend.app.providers import PumpPortalProvider

    clock = [0.0]
    connections = []
    delays = []
    sent = []

    class Socket:
        async def send(self, message):
            sent.append((len(connections), json.loads(message)["method"]))

        async def recv(self):
            if len(connections) == 5:
                raise asyncio.CancelledError()
            if len(connections) == 3 and clock[0] == 0:
                clock[0] = 61
                return "{}"
            raise ConnectionClosedError(None, None)

    class Connection:
        async def __aenter__(self):
            connections.append(1)
            return Socket()

        async def __aexit__(self, *args):
            return False

    async def sleep(delay):
        delays.append(delay)

    monkeypatch.setattr("backend.app.providers.websockets.connect", lambda *a, **k: Connection())
    monkeypatch.setattr("backend.app.providers.asyncio.sleep", sleep)
    monkeypatch.setattr("backend.app.providers.random.random", lambda: 0)
    monkeypatch.setattr("backend.app.providers.time.monotonic", lambda: clock[0])
    provider = PumpPortalProvider(Settings(), lambda e: None, lambda: [])
    with pytest.raises(asyncio.CancelledError):
        await provider.run()
    assert delays == [1, 2, 1, 2]
    for connection in range(1, 6):
        assert [method for number, method in sent if number == connection] == [
            "subscribeNewToken",
            "subscribeMigration",
        ]
