"""Exact rolling-window loss accounting; synthetic retained history, not backfill."""

from collections import deque
import math

import pytest
from solders.pubkey import Pubkey

from backend.app.config import Settings
from backend.app.domain import MarketEvent, State, Token
from backend.app.engine import RadarEngine
from backend.app.features import calculate_features, window_features

NOW = 10000.0


def trade(mint, stamp, identity, currency="SOL"):
    return MarketEvent(mint=mint, ts=stamp, source="Solana WSS", kind="trade",
                       event_id=identity, wallet=f"synthetic-{identity}", side="buy",
                       currency=currency, volume=1)


@pytest.fixture
async def setup(tmp_path):
    engine = RadarEngine(Settings(mode="OBSERVE"), tmp_path / "offline.db", offline=True)
    token = Token(str(Pubkey.new_unique()), "Synthetic", "TEST", NOW - 500, state=State.WATCHING)
    token.trade_tracking_since = NOW - 500
    engine.tokens[token.mint] = token
    engine.onchain.health.update(connected=True, connected_since=NOW - 500)
    yield engine, token
    await engine.stop()


def seed(token, first):
    # Models trades already accepted at their own observation times. Never sends
    # old events through the live freshness gate or persists them as fresh trades.
    events = [trade(token.mint, first + (NOW - 1 - first) * i / 499, f"seed{i}") for i in range(500)]
    token.events = deque(events, maxlen=500)
    token.last_event = token.last_trade = NOW - 1
    return events


def analyze(engine, token, at):
    engine.analyse(token, at)
    return engine.trade_status(token, at)


def test_known_loss_expires_with_actual_window_not_an_extra_180_seconds(setup):
    engine, token = setup
    complete = seed(token, NOW - 170)
    incoming = trade(token.mint, NOW, "fresh")
    assert engine.process(incoming, NOW)
    assert analyze(engine, token, NOW) != "CURRENT"
    # At +11 the only evicted trade is181s old; every trade in the FULL180s
    # required window remains present and the latest trade is11s old, not stale.
    assert calculate_features(token, NOW + 11)["180"] == window_features(complete + [incoming], NOW + 11, 180)
    assert analyze(engine, token, NOW + 11) == "CURRENT"
    assert engine.trade_continuity["per_token_reasons"]["buffer"] == 1
    assert len(token.events) == 500
    assert engine.approved_evidence is None and token.decision["decision"] != "ALLOW_PAPER_ENTRY"


def test_inclusive_boundary_and_late_incoming_timestamp_cannot_hide_loss(setup):
    engine, token = setup
    complete = seed(token, NOW - 180)
    incoming = trade(token.mint, NOW, "edge")
    assert engine.process(incoming, NOW)
    assert analyze(engine, token, NOW) != "CURRENT"  # Lost event at inclusive boundary.
    at = math.nextafter(NOW, math.inf)
    assert calculate_features(token, at)["180"] == window_features(complete + [incoming], at, 180)
    assert analyze(engine, token, at) == "CURRENT"


def test_expired_eviction_is_audited_without_creating_a_fake_current_window_gap(setup):
    engine, token = setup
    complete = seed(token, NOW - 181)
    incoming = trade(token.mint, NOW - 19, "late-but-fresh")
    assert engine.process(incoming, NOW)
    assert analyze(engine, token, NOW) == "CURRENT"
    assert calculate_features(token, NOW)["180"] == window_features(complete + [incoming], NOW, 180)


@pytest.mark.parametrize("currency", ["unknown", "USDC"])
def test_mixed_or_unknown_retained_units_never_become_current(setup, currency):
    engine, token = setup
    seed(token, NOW - 170)
    assert engine.process(trade(token.mint, NOW, "invalid", currency), NOW)
    assert analyze(engine, token, NOW + 11) != "CURRENT"
    assert not token.features["180"]["units_valid"]


@pytest.mark.parametrize("reason", ["queue", "recovery", "stale", "processing", "resource"])
def test_nonbuffer_gaps_still_require_full_clean_rewarm(setup, reason):
    engine, token = setup
    seed(token, NOW - 170)
    assert engine.process(trade(token.mint, NOW, "fresh"), NOW)
    engine.invalidate_token_trade_coverage(token.mint, reason=reason, now=NOW + 1)
    assert analyze(engine, token, NOW + 11) != "CURRENT"
    assert token.trade_gap == NOW + 1


def test_burst_stays_bounded_and_only_returns_current_with_complete_oracle_window(setup):
    engine, token = setup
    complete = seed(token, NOW - 170)
    for i in range(8):
        event = trade(token.mint, NOW + i / 100, f"burst{i}")
        complete.append(event)
        assert engine.process(event, event.ts)
        assert analyze(engine, token, event.ts) != "CURRENT"
        assert len(token.events) == 500
    # Actual missing evidence ages out, then new known-unit samples arrive.
    for i in range(3):
        event = trade(token.mint, NOW + 191 + i, f"later{i}")
        complete.append(event)
        assert engine.process(event, event.ts)
    assert analyze(engine, token, NOW + 193) == "CURRENT"
    assert calculate_features(token, NOW + 193)["180"] == window_features(complete, NOW + 193, 180)
    assert engine.trade_continuity["per_token_reasons"]["buffer"] == 8
    assert len(token.events) == 500


def test_out_of_order_evictions_keep_latest_missing_timestamp_not_last_removed(setup):
    engine, token = setup
    complete = seed(token, NOW - 170)
    complete[0] = trade(token.mint, NOW - 90, "newer-arrived-first")
    token.events = deque(complete, maxlen=500)
    for i in range(2):
        event = trade(token.mint, NOW + i / 10, f"new{i}")
        complete.append(event)
        assert engine.process(event, event.ts)
    assert token.buffer_loss_at == NOW - 90
    assert analyze(engine, token, NOW + 11) != "CURRENT"
    for i in range(3):
        event = trade(token.mint, NOW + 100 + i, f"end{i}")
        complete.append(event)
        assert engine.process(event, event.ts)
    assert analyze(engine, token, NOW + 102) == "CURRENT"
    assert calculate_features(token, NOW + 102)["180"] == window_features(complete, NOW + 102, 180)


def test_actual_queue_drop_stale_rejection_and_global_loss_stay_fail_closed(setup, monkeypatch):
    from backend.app.domain import PriorityBuffer

    engine, token = setup
    seed(token, NOW - 170)
    assert engine.process(trade(token.mint, NOW, "fresh"), NOW)
    monkeypatch.setattr("backend.app.engine.time.time", lambda: NOW)
    engine.queue = PriorityBuffer(1)
    assert engine.submit(trade(token.mint, NOW, "queued"))
    assert engine.submit(MarketEvent(mint="synthetic-new", kind="create", ts=NOW,
                                    source="synthetic", event_id="critical"))
    assert engine.queue.dropped_trades == 1
    assert analyze(engine, token, NOW + 11) != "CURRENT"
    assert not engine.process(trade(token.mint, NOW - 21, "stale"), NOW)
    assert engine.trade_continuity["per_token_reasons"]["stale"] == 1
    engine.invalidate_trade_coverage()
    assert analyze(engine, token, NOW + 11) != "CURRENT"


def test_resource_trim_inclusive_edge_and_restart_cannot_restore_current(setup):
    engine, token = setup
    events = [trade(token.mint, NOW - 180, "edge")]
    events += [trade(token.mint, NOW - 181, f"older{i}") for i in range(399)]
    events += [trade(token.mint, NOW - 1, f"recent{i}") for i in range(100)]
    token.events = deque(events, maxlen=500)
    token.last_trade = NOW - 1
    engine.trim_for_resource_pressure(token, NOW)
    assert engine.trade_continuity["per_token_reasons"]["resource"] == 1
    assert token.degraded and len(token.events) == 100
    assert analyze(engine, token, NOW) != "CURRENT"


def test_future_timestamp_loss_is_not_certified_at_processing_time_boundary(setup):
    engine, token = setup
    seed(token, NOW - 170)
    token.events[0] = trade(token.mint, NOW + 5, "future-clock")
    assert engine.process(trade(token.mint, NOW, "new"), NOW)
    assert token.buffer_loss_at == NOW + 5
    # Even at +180 the missing future-stamped event is only175s old.
    for i in range(3):
        assert engine.process(trade(token.mint, NOW + 180, f"fresh{i}"), NOW + 180)
    assert analyze(engine, token, NOW + 180) != "CURRENT"


async def test_restart_discards_windows_and_requires_new_live_coverage(setup):
    engine, token = setup
    seed(token, NOW - 170)
    assert engine.process(trade(token.mint, NOW, "new"), NOW)
    engine.checkpoint(NOW)
    restored = RadarEngine(engine.settings, engine.db.path, offline=True)
    try:
        t = restored.tokens[token.mint]
        assert not t.events and t.buffer_loss_at is None
        assert restored.trade_status(t, NOW + 1) != "CURRENT"
        assert not restored.onchain.health["connected"] and not restored.tasks
    finally:
        await restored.stop()
