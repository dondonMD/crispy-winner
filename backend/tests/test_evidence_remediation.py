"""Synthetic loss/accounting regressions, not prospective observations."""

import statistics
import time

import pytest

from backend.app.config import Settings
from backend.app.domain import MarketEvent, PriorityBuffer
from backend.app.engine import RadarEngine
from backend.app.evidence_pipeline import EventAccounting
from backend.app.features import price_volatility


def event(i, kind="trade", ts=None):
    return MarketEvent(event_id=str(i), mint="synthetic", source="DEMO", kind=kind,
                       ts=time.time() if ts is None else ts, currency="SOL", side="buy", volume=1)


def test_queue_reject_and_eviction_have_distinct_accounting():
    q = PriorityBuffer(1)
    a = EventAccounting()
    assert q.put(event(1), 1)
    assert not q.put(event(2), 1)
    assert q.put(event(3), 2)
    row = a.snapshot(q)["events"]["trade"]
    assert row["reconciled"] and row["rejected_incoming"] == row["evicted_accepted"] == 1
    q.drain()
    assert a.snapshot(q)["events"]["trade"]["in_processing"] == 1


async def test_batch_exception_does_not_lose_remainder(tmp_path, monkeypatch):
    e = RadarEngine(Settings(mode="DEMO"), tmp_path / "test.db", offline=True)
    original = e._process

    def broken(ev, now):
        if ev.event_id == "1":
            raise RuntimeError("synthetic failure")
        return original(ev, now)

    monkeypatch.setattr(e, "_process", broken)
    for i in range(3):
        e.submit(event(i, "create" if i == 0 else "trade"))
    await e.drain_events()
    row = e.accounting.snapshot(e.queue)["events"]["trade"]
    assert row["reconciled"]
    assert row["terminal"] == {"exception": 1, "processed": 1}
    assert e.trade_continuity["per_token_reasons"]["processing"] == 1
    await e.stop()


async def test_dequeue_checks_actual_time_and_stale_trade_gaps(tmp_path):
    e = RadarEngine(Settings(mode="DEMO"), tmp_path / "test.db", offline=True)
    e.process(event(0, "create"))
    e.submit(event(1, ts=time.time() - 30))
    await e.drain_events()
    row = e.accounting.snapshot(e.queue)["events"]["trade"]
    assert row["terminal"] == {"stale": 1} and row["reconciled"]
    assert e.trade_continuity["per_token_reasons"]["stale"] == 1
    await e.stop()


def test_volatility_cache_is_exact_and_bounded():
    price_volatility.cache_clear()
    for i in range(200):
        values = (0.1, i / 1000, -0.002)
        assert price_volatility(values) == statistics.pstdev(values) * 100
    assert price_volatility.cache_info().currsize == 128


def test_cached_config_never_hides_content_drift_or_shares_mutable_settings(tmp_path):
    from backend.app.opportunity import load_intelligence_settings

    path = tmp_path / "synthetic.yaml"
    path.write_text("curve_fresh_seconds: 30\n")
    first = load_intelligence_settings(path)
    second = load_intelligence_settings(path)
    assert first.model_dump() == second.model_dump() and first is not second
    version = second.version
    first.curve_fresh_seconds = 35
    assert load_intelligence_settings(path).version == version
    path.write_text("curve_fresh_seconds: 31\n")
    assert load_intelligence_settings(path).version != version


@pytest.mark.parametrize("source", ["Solana WSS", "PumpSwap WSS"])
async def test_untracked_trade_terminal_filter_is_explicit(tmp_path, source):
    e = RadarEngine(Settings(mode="OBSERVE"), tmp_path / "test.db", offline=True)
    ev = event(1).model_copy(update={"source": source})
    e.submit(ev)
    await e.drain_events()
    row = e.accounting.snapshot(e.queue)["events"]["trade"]
    assert row["terminal"] == {"untracked": 1} and row["reconciled"]
    await e.stop()


async def test_observation_pause_and_backwards_clock_gap_both_venues(tmp_path):
    from backend.app.domain import Token

    e = RadarEngine(Settings(mode="OBSERVE"), tmp_path / "pause.db", offline=True)
    e.tokens["curve"] = Token("curve", "", "", 100)
    e.tokens["pool"] = Token("pool", "", "", 100)
    e.tokens["pool"].flow_venue = "PUMPSWAP"
    e.accounting.last_tick = 100
    e.observation_tick(130)
    assert e.accounting.observation_gaps == 1
    assert e.tokens["curve"].trade_gap > 0 and e.tokens["pool"].postgrad_gap == 130
    e.observation_tick(120)
    assert e.accounting.gaps[-1]["reason"] == "clock_backwards"
    assert e.accounting.observation_gaps == 2
    await e.stop()


async def test_overload_is_bounded_and_reconciles_without_critical_loss(tmp_path):
    e = RadarEngine(Settings(mode="DEMO"), tmp_path / "burst.db", offline=True)
    e.process(event("launch", "create"))
    for i in range(1500):
        e.submit(event(i).model_copy(update={"source": "Solana WSS"}))
    # Lifecycle/security evidence retains its higher priority; no increase in capacity.
    e.submit(event("critical", "security"))
    assert len(e.queue.heap) == 1000
    while e.queue.heap:
        await e.drain_events()
    audit = e.accounting.snapshot(e.queue)
    assert all(row["reconciled"] for row in audit["events"].values())
    assert e.queue.dropped_critical == 0 and e.queue.dropped_trades == 501
    assert e.trade_continuity["per_token_reasons"]["queue"] > 0
    assert e.trade_continuity["per_token_reasons"]["buffer"] > 0
    await e.stop()


async def test_observational_adapter_preserves_queued_accounting(tmp_path):
    from types import SimpleNamespace
    from backend.app.early_edge_runtime import attach_observer

    e = RadarEngine(Settings(mode="DEMO"), tmp_path / "adapter.db", offline=True)
    observer = SimpleNamespace(clock=time.time, settings=e.settings, failed=False,
                               observe=lambda *args: None)
    detach = attach_observer(e, observer)
    e.submit(event("create", "create"))
    await e.drain_events()
    row = e.accounting.snapshot(e.queue)["events"]["create"]
    assert row["reconciled"] and row["terminal"] == {"processed": 1}
    assert not observer.failed
    detach()
    await e.stop()


async def test_resource_trim_never_silently_keeps_complete_trade_window(tmp_path):
    e = RadarEngine(Settings(mode="DEMO"), tmp_path / "trim.db", offline=True)
    e.process(event("launch", "create"))
    token = e.tokens["synthetic"]
    for i in range(120):
        token.events.append(event(i))
    e.trim_for_resource_pressure(token, time.time())
    assert len(token.events) == 100 and token.degraded
    assert e.trade_continuity["per_token_reasons"]["resource"] == 1
    assert not token.features["180"]["continuity_valid"]
    await e.stop()
