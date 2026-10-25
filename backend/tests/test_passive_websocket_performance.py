"""Passive numeric measurements only: fake clock and existing connection."""

import asyncio
import json
from types import SimpleNamespace

import pytest

from backend.app.discovery import OnchainPumpDiscovery, PERFORMANCE_SAMPLE_LIMIT


class TimerLoop:
    now = 100.0

    def __init__(self):
        self.handles = []

    def time(self):
        return self.now

    def call_later(self, delay, callback, *args):
        handle = SimpleNamespace(cancelled=False, due=self.now + delay)
        handle.cancel = lambda: setattr(handle, "cancelled", True)
        handle.fire = lambda: callback(*args)
        self.handles.append(handle)
        return handle


def test_exact_buckets_fixed_keys_and_invalid_values():
    p = OnchainPumpDiscovery(lambda _: None, url="")
    for value in [0, 0.001, 0.002, 21]:
        p.record_performance_duration("json_decode", value)
    for value in [True, "secret", float("nan"), float("inf"), -1]:
        p.record_performance_duration("json_decode", value)
    p.record_performance_duration("secret", 1)
    summaries = p.health["passive_performance"]["durations"]
    assert len(summaries) == 4
    s = summaries["json_decode"]
    assert s["count"] == sum(s["bucket_counts"]) == 4
    assert s["max_seconds"] == s["last_seconds"] == 21
    assert s["total_seconds"] == pytest.approx(21.003)
    assert s["bucket_counts"] == [1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 1]


def test_sampler_uses_only_public_latency_bounded_history_and_no_catchup(monkeypatch):
    loop = TimerLoop()
    monkeypatch.setattr("backend.app.discovery.asyncio.get_running_loop", lambda: loop)

    class Socket:
        latency = 0.25

        def __getattr__(self, name):
            raise AssertionError(f"Unexpected socket operation: {name}")

    ws = Socket()
    p = OnchainPumpDiscovery(lambda _: None, url="")
    stop = p.start_performance_sampler(lambda: ws)
    for _ in range(100):
        old = loop.handles[-1]
        loop.now = old.due + 0.5
        old.fire()
        assert loop.handles[-1].due == loop.now + 1
    metrics = p.health["passive_performance"]
    assert metrics["durations"]["event_loop_lag"]["max_seconds"] == 0.5
    assert metrics["durations"]["completed_rtt_snapshots"]["count"] == 100
    assert len(metrics["recent"]) == PERFORMANCE_SAMPLE_LIMIT
    assert metrics["recent_evicted"] == 100 - PERFORMANCE_SAMPLE_LIMIT
    assert metrics["recent"][-1]["last_completed_rtt_seconds"] == 0.25
    assert all(metrics[k] == "UNAVAILABLE_SUPPORTED_INTERFACE" for k in (
        "receive_frame_depth", "read_pause_duration", "outstanding_ping_age"))
    stop()
    assert loop.handles[-1].cancelled
    before = json.dumps(metrics)
    loop.handles[-1].fire()  # Even an already queued callback cannot restart sampling.
    assert json.dumps(metrics) == before
    assert len(loop.handles) == 101


@pytest.mark.parametrize("latency", [None, 0, -1, float("nan"), float("inf"), True, "private"])
def test_unknown_latency_not_invented(monkeypatch, latency):
    loop = TimerLoop()
    monkeypatch.setattr("backend.app.discovery.asyncio.get_running_loop", lambda: loop)
    p = OnchainPumpDiscovery(lambda _: None, url="")
    stop = p.start_performance_sampler(lambda: SimpleNamespace(latency=latency))
    loop.now += 1
    loop.handles[-1].fire()
    stop()
    m = p.health["passive_performance"]
    assert m["unavailable_rtt_snapshots"] == 1
    assert m["durations"]["completed_rtt_snapshots"]["count"] == 0
    assert m["recent"][-1]["last_completed_rtt_seconds"] is None
    assert "private" not in json.dumps(m, allow_nan=False)


@pytest.mark.parametrize("message,decode_errors", [("{", 1), ('{"params":{"subscription":7}}', 0)])
async def test_run_timing_no_extra_network_or_gap_changes(monkeypatch, message, decode_errors):
    sent, options, received, stops, gaps = [], [], [], [], []
    ticks = iter([10.0, 11.0, 11.25, 12.0])
    monkeypatch.setattr("backend.app.discovery.perf_counter", lambda: next(ticks))

    class Socket:
        reads = 0

        async def send(self, value):
            sent.append(json.loads(value))

        async def recv(self):
            self.reads += 1
            if self.reads == 1:
                return '{"id":1,"result":7}'
            if self.reads == 2:
                return message
            raise asyncio.CancelledError()

    class Context:
        async def __aenter__(self):
            return Socket()

        async def __aexit__(self, *args):
            return False

    def connect(*args, **kwargs):
        options.append(kwargs)
        return Context()

    monkeypatch.setattr("backend.app.discovery.websockets.connect", connect)
    p = OnchainPumpDiscovery(lambda _: pytest.fail("No fabricated market events"), "wss://example.test",
                             on_gap=lambda: gaps.append(True))
    monkeypatch.setattr(p, "start_performance_sampler", lambda get_socket: lambda: stops.append(True))
    monkeypatch.setattr(p, "receive", received.append)
    with pytest.raises(asyncio.CancelledError):
        await p.run()
    metrics = p.health["passive_performance"]["durations"]
    assert metrics["json_decode"]["last_seconds"] == 0.25
    assert metrics["message_processing"]["last_seconds"] == 2
    assert len(sent) == len(options) == 1 and sent[0]["method"] == "logsSubscribe"
    assert options[0] == dict(max_size=262144, max_queue=16, open_timeout=15,
                             ping_interval=20, ping_timeout=20, close_timeout=5)
    assert len(received) == 1 - decode_errors and stops == [True]
    assert len(gaps) == 1 + decode_errors  # Original malformed-message and shutdown gaps.
    assert p.health["reconnects"] == 0
    assert p.health["global_reset_reasons"]["outer_notification"] == decode_errors
    assert p.health["global_reset_reasons"]["shutdown"] == 1


async def test_measurements_do_not_upgrade_incomplete_evidence(tmp_path):
    from backend.app.config import Settings
    from backend.app.domain import Token
    from backend.app.engine import RadarEngine

    engine = RadarEngine(Settings(mode="OBSERVE"), tmp_path / "offline.db", offline=True)
    try:
        token = Token("synthetic", "Synthetic", "TEST", 1000)
        token.features = {"180": {"samples": 3, "units_valid": True, "continuity_valid": False}}
        engine.tokens[token.mint] = token
        before = engine.trade_status(token)
        for name in engine.onchain.health["passive_performance"]["durations"]:
            engine.onchain.record_performance_duration(name, 0.001)
        assert engine.trade_status(token) == before != "CURRENT"
        assert engine.approved_evidence is None and not engine.tasks
    finally:
        await engine.stop()


async def test_real_timer_cancelled_on_run_shutdown_and_disabled_provider(monkeypatch):
    loop = asyncio.get_running_loop()
    original = loop.call_later
    samplers = []

    def call_later(delay, callback, *args, **kwargs):
        handle = original(delay, callback, *args, **kwargs)
        if callback.__name__ == "sample":
            samplers.append(handle)
        return handle

    class Context:
        async def __aenter__(self):
            raise asyncio.CancelledError()

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(loop, "call_later", call_later)
    monkeypatch.setattr("backend.app.discovery.websockets.connect", lambda *args, **kwargs: Context())
    disabled = OnchainPumpDiscovery(lambda _: None, url="")
    await disabled.run()
    assert not samplers
    p = OnchainPumpDiscovery(lambda _: None, url="wss://example.test")
    tasks = asyncio.all_tasks()
    with pytest.raises(asyncio.CancelledError):
        await p.run()
    assert len(samplers) == 1 and samplers[0].cancelled()
    assert asyncio.all_tasks() == tasks
    assert p.health["global_reset_reasons"]["shutdown"] == 1
