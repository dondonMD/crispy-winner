"""Bounded scheduling and shared-provider fairness, without live transactions."""
import asyncio
import json
import time
from unittest.mock import AsyncMock
from types import SimpleNamespace

import httpx
import pytest
from solders.signature import Signature

from backend.app.recovery_metrics import RecoveryMetrics
from backend.app.truncation import TruncationRecovery
from backend.tests.test_trade_gap_scoping import tracked_engine as tracked_engine
from backend.tests.test_truncation_recovery import transaction


def test_diagnostics_bounded(monkeypatch):
    # Saturation is a deterministic count test, independent of host CPU speed.
    monkeypatch.setattr("backend.app.recovery_metrics.time", SimpleNamespace(monotonic=lambda: 1000.0))
    metrics = RecoveryMetrics()
    for i in range(10000):
        metrics.sample("queue_wait", i)
        metrics.tick("arrivals")
    snapshot = metrics.snapshot()
    assert snapshot["queue_wait_seconds"]["samples"] == 1024
    assert len(metrics.rates["arrivals"]) <= 8192
    assert snapshot["rate_saturations"] > 0


async def test_serial_worker_network_latency_prevents_permitted_overlap(tracked_engine):
    e = tracked_engine
    active = 0
    maximum = 0
    async def handler(request):
        nonlocal active, maximum
        active += 1
        maximum = max(maximum, active)
        await asyncio.sleep(.025)
        active -= 1
        body = json.loads(request.content)
        tx, _ = transaction()
        tx["transaction"]["signatures"][0] = body["params"][0]
        return httpx.Response(200, json={"result": tx})
    await e.rpc.client.aclose()
    e.rpc.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    e.rpc.limiter.wait = AsyncMock()
    for _ in range(3):
        e.recovery.submit(str(Signature.new_unique()), 123, time.time())
    for _ in range(3):
        await e.recovery.step()
    assert maximum == 1
    assert e.recovery.health["completed"] == 3
    assert e.recovery.snapshot()["scheduling"]["http_latency_seconds"]["min"] >= .025
    assert e.recovery.health["recovery_requests_with_backlog"] == 3


def test_limits_unchanged():
    assert TruncationRecovery.MAX_PENDING == 32
    assert TruncationRecovery.MAX_AGE == 45
    assert TruncationRecovery.MAX_ATTEMPTS == 3


async def test_claim_bound_cancellation_and_monitoring_fairness(tracked_engine):
    e = tracked_engine
    entered = asyncio.Event()
    release = asyncio.Event()
    signatures = []
    monitoring = []
    async def handler(request):
        body = json.loads(request.content)
        if body["method"] != "getTransaction":
            monitoring.append(body["method"])
            value = {"getMultipleAccounts": [None, None], "getTokenLargestAccounts": [],
                     "getTokenSupply": {"amount": "100", "decimals": 6}}.get(body["method"])
            return httpx.Response(200, json={"result": {"value": value}})
        signatures.append(body["params"][0])
        if len(signatures) == 2:
            entered.set()
        await release.wait()
        tx, _ = transaction()
        tx["transaction"]["signatures"][0] = body["params"][0]
        return httpx.Response(200, json={"result": tx})
    await e.rpc.client.aclose()
    e.rpc.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    e.rpc.limiter.wait = AsyncMock()
    for _ in range(32):
        e.recovery.submit(str(Signature.new_unique()), 123, time.time())
    first = asyncio.create_task(e.recovery.step())
    second = asyncio.create_task(e.recovery.step())
    try:
        await asyncio.wait_for(entered.wait(), 2)
        await asyncio.gather(*(e.recovery.step() for _ in range(20)))
        assert e.recovery.in_flight == 2
        assert len(signatures) == len(set(signatures)) == 2
        # Actual curve/security methods use the same FIFO semaphore and limiter.
        curve = asyncio.create_task(e.rpc.curve_progress_batch(list(e.tokens)[:1]))
        security = asyncio.create_task(e.rpc.inspect(next(iter(e.tokens))))
        await asyncio.sleep(0)
        release.set()
        await asyncio.wait_for(asyncio.gather(first, second, curve, security), 3)
        assert "getMultipleAccounts" in monitoring and "getAccountInfo" in monitoring
        assert len(e.recovery.pending) == 30
        assert e.recovery.health["monitoring_requests_with_backlog"] >= 2
        assert e.recovery.health["maximum_in_flight"] == 2
        assert not e.recovery.claimed
        # Cancellation releases the signature claim without silently resolving coverage.
        release.clear()
        task = asyncio.create_task(e.recovery.step())
        await asyncio.sleep(.01)
        assert len(e.recovery.claimed) == 1
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not e.recovery.claimed and e.recovery.in_flight == 0
        assert len(e.recovery.pending) == 30
    finally:
        release.set()
        for task in (first, second):
            task.cancel()
        await asyncio.gather(first, second, return_exceptions=True)


async def test_runner_cancels_its_bounded_workers(tracked_engine):
    e = tracked_engine
    e.rpc.rpc = AsyncMock(side_effect=asyncio.CancelledError)
    for _ in range(32):
        e.recovery.submit(str(Signature.new_unique()), 123, time.time())
    runner = asyncio.create_task(e.recovery.run())
    await asyncio.sleep(.01)
    runner.cancel()
    await asyncio.gather(runner, return_exceptions=True)
    assert not e.recovery.claimed and e.recovery.in_flight == 0
    assert len(e.recovery.pending) == 32


async def test_expiry_after_inflight_rpc_fails_closed_once(tracked_engine):
    e = tracked_engine
    signature = str(Signature.new_unique())
    e.recovery.submit(signature, 123, time.time())
    item = e.recovery.pending[signature]
    async def late(*args, **kwargs):
        item.observed -= 46
        tx, _ = transaction()
        return tx
    e.rpc.rpc = late
    await e.recovery.step()
    assert e.recovery.health["expired"] == 1
    assert e.recovery.health["completed"] == 1
    e.recovery.resolve(item, "UNTRACKED_CONFIRMED")
    assert e.recovery.health["completed"] == 1
    assert e.recovery.health["global_gaps"] == 1


async def test_shared_429_stops_both_recovery_and_monitoring(tracked_engine):
    e = tracked_engine
    calls = []
    async def handler(request):
        calls.append(json.loads(request.content)["method"])
        return httpx.Response(429, headers={"Retry-After": "30"})
    await e.rpc.client.aclose()
    e.rpc.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    e.rpc.limiter.wait = AsyncMock()
    for _ in range(32):
        e.recovery.submit(str(Signature.new_unique()), 123, time.time())
    await asyncio.gather(e.recovery.step(), e.recovery.step())
    for _ in range(20):
        await e.recovery.step()
    with pytest.raises(RuntimeError):
        await e.rpc.curve_progress_batch(list(e.tokens)[:1])
    with pytest.raises(RuntimeError):
        await e.rpc.inspect(next(iter(e.tokens)))
    assert calls == ["getTransaction"]
    assert e.rpc.health["rate_limits"] == 1
    assert e.rpc.health["backoff_level"] == 1
    assert len(e.recovery.pending) == 32 and not e.recovery.claimed
