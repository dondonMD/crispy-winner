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


@pytest.mark.parametrize("source", ["Solana WSS", "PumpSwap WSS"])
async def test_untracked_trade_terminal_filter_is_explicit(tmp_path, source):
    e = RadarEngine(Settings(mode="OBSERVE"), tmp_path / "test.db", offline=True)
    ev = event(1).model_copy(update={"source": source})
    e.submit(ev)
    await e.drain_events()
    row = e.accounting.snapshot(e.queue)["events"]["trade"]
    assert row["terminal"] == {"untracked": 1} and row["reconciled"]
    await e.stop()
