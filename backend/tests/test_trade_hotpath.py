"""Exact raw-feature cache equivalence; no cached continuity/decisions."""

import math
import random
from collections import deque

import pytest
from sqlalchemy import event

from backend.app.domain import Token, MarketEvent
from backend.app.features import calculate_features, window_features, cached_window_features
from backend.app.config import Settings
from backend.app.db import Base, Database


@pytest.mark.parametrize("seconds", [10, 30, 60, 180, 300, 600])
def test_cached_temporal_boundaries_match_reference(seconds):
    now = 10000.0
    rng = random.Random(520)
    times = [now - rng.uniform(-10, seconds + 20) for _ in range(100)]
    for i in range(7):
        at = now - i * seconds / 6
        times.extend([at, math.nextafter(at, -math.inf), math.nextafter(at, math.inf)])
    events = [
        MarketEvent(
            mint="synthetic",
            source="SYNTHETIC",
            kind="trade" if i % 7 else "market",
            event_id=str(i),
            ts=t,
            volume=rng.choice([0, 0.001, 0.2, 1e12]),
            side="buy" if i % 3 else "sell",
            wallet=f"w{i % 9}",
            currency="unknown" if i % 17 == 0 else "SOL",
            price=1 + i / 100 if i % 4 == 0 else None,
        )
        for i, t in enumerate(sorted(times))
    ]
    cache = {}
    for at in [now, now, now + 0.01, now + 1, now + seconds / 6, now - 1, now + seconds, now + seconds + 1]:
        assert cached_window_features(events, at, seconds, "w2", cache) == window_features(
            events, at, seconds, "w2"
        )
    for field, value in [
        ("volume", 0.99),
        ("wallet", "changed"),
        ("currency", "USDC"),
        ("side", "sell"),
        ("price", 3.0),
        ("ts", now + 2),
    ]:
        setattr(events[-1], field, value)
        assert cached_window_features(events, now + 2, seconds, "changed", cache) == window_features(
            events, now + 2, seconds, "changed"
        )


def test_unchanged_inputs_reuse_static_math_but_never_continuity(monkeypatch):
    import backend.app.features as module

    t = Token("synthetic", "", "", 100)
    t.events.append(
        MarketEvent(
            mint=t.mint,
            source="SYNTHETIC",
            event_id="1",
            ts=100,
            kind="trade",
            side="buy",
            volume=1,
            currency="SOL",
            wallet="w",
        )
    )
    calls = []
    original = module.window_features

    def measured(*args):
        calls.append(1)
        return original(*args)

    monkeypatch.setattr(module, "window_features", measured)
    first = calculate_features(t, 101)
    first["180"]["trade_evidence"] = "CURRENT"
    first["180"]["cluster_evidence"].append("poison")
    second = calculate_features(t, 102)
    assert len(calls) == 1 and len(t._feature_window_cache["windows"]) == 6
    assert "trade_evidence" not in second["180"] and "poison" not in second["180"]["cluster_evidence"]
    assert second["180"] == original(t.events, 102, 180, t.creator)
    t.events = deque(maxlen=500)  # Actual observation loss must not retain old breadth.
    assert calculate_features(t, 102)["180"]["samples"] == 0
    t.flow_venue = "PUMPSWAP"
    t.flow_epoch = 103
    t.events.append(
        MarketEvent(
            mint=t.mint,
            source="Solana WSS",
            event_id="2",
            ts=104,
            kind="trade",
            side="buy",
            volume=1,
            currency="SOL",
        )
    )
    assert calculate_features(t, 104)["180"]["samples"] == 0


async def test_engine_decisions_match_uncached_calculation(tmp_path, monkeypatch):
    import backend.app.engine as module
    from backend.app.demo import demo_events

    def reference(t, now):
        events = t.events
        if t.flow_venue == "PUMPSWAP":
            events = [
                e
                for e in events
                if e.kind != "trade"
                or (
                    e.source == "PumpSwap WSS"
                    and e.evidence.get("venue") == "PUMPSWAP"
                    and e.ts >= t.flow_epoch
                )
            ]
        return {str(s): window_features(events, now, s, t.creator) for s in [10, 30, 60, 180, 300, 600]}

    cached = module.RadarEngine(Settings(mode="DEMO"), tmp_path / "cached.db", offline=True)
    old = module.RadarEngine(Settings(mode="DEMO"), tmp_path / "reference.db", offline=True)
    try:
        for tick in range(10):
            for observation in demo_events(1000, tick):
                with monkeypatch.context() as ctx:
                    ctx.setattr(module, "calculate_features", reference)
                    old.process(observation.model_copy(deep=True))
                cached.process(observation.model_copy(deep=True))
                for mint, t in old.tokens.items():
                    actual = cached.tokens[mint]
                    assert (actual.features, actual.scores, actual.decision, actual.state) == (
                        t.features,
                        t.scores,
                        t.decision,
                        t.state,
                    )
    finally:
        await old.stop()
        await cached.stop()


def test_guard_uses_writer_connection_and_preserves_atomic_failure(tmp_path):
    db = Database(tmp_path / "guard.db")
    Base.metadata.create_all(db.engine)
    db.configure_budget(8)
    queries = []
    checkouts = []
    event.listen(db.engine, "before_cursor_execute", lambda conn, cursor, sql, *args: queries.append(sql))
    event.listen(db.engine, "checkout", lambda *args: checkouts.append(1))
    assert db.reserve_event("one", 100)
    db.add("outcome", {"net_return_pct": -100})
    assert len(checkouts) == 2
    assert sum("PRAGMA freelist_count" in q for q in queries) == 2
    assert not any("PRAGMA page_size" in q for q in queries)

    def fail(conn):
        raise OSError("commit failure")

    event.listen(db.engine, "commit", fail)
    with pytest.raises(OSError):
        db.reserve_event("retry", 101)
    event.remove(db.engine, "commit", fail)
    assert db.reserve_event("retry", 101)
    assert not db.reserve_event("retry", 101)
    assert db.rows("outcome")[0]["net_return_pct"] == -100
    db.engine.dispose()


def test_token_fingerprint_mutations_and_signed_zero_are_exact():
    import json

    t = Token("synthetic", "", "", 100)
    observation = MarketEvent(
        mint=t.mint,
        source="SYNTHETIC",
        event_id="one",
        ts=100,
        kind="trade",
        side="buy",
        volume=0.0,
        currency="SOL",
        price=1,
        wallet="w",
    )
    t.events.append(observation)
    for field, value in [
        ("volume", 0.0),
        ("volume", -0.0),
        ("volume", 2.0),
        ("wallet", "new"),
        ("currency", "unknown"),
        ("side", "sell"),
        ("price", 3.0),
        ("ts", 102.0),
    ]:
        setattr(observation, field, value)
        result = calculate_features(t, 103)
        expected = {str(s): window_features(t.events, 103, s, t.creator) for s in [10, 30, 60, 180, 300, 600]}
        assert json.dumps(result, sort_keys=True) == json.dumps(expected, sort_keys=True)


def test_bound_sql_keeps_constraints_callbacks_and_raw_commit_atomic(tmp_path):
    from sqlalchemy.exc import IntegrityError

    db = Database(tmp_path / "raw.db")
    Base.metadata.create_all(db.engine)
    db.configure_budget(8)
    with pytest.raises(IntegrityError):
        db.reserve_event(None, 100)  # ON CONFLICT does not hide NOT NULL failures.
    callbacks = []
    db.record_observer = lambda session, row, payload: callbacks.append((row.kind, row.id))
    db.add("outcome", {"net_return_pct": -100})
    db.add("signal", {"eligible_research": False})
    assert [kind for kind, _ in callbacks] == ["outcome", "signal"]

    def fail(conn):
        raise OSError("raw commit failed")

    event.listen(db.engine, "commit", fail)
    with pytest.raises(OSError):
        db.add("event", {"synthetic": True, "quantity": 1})
    event.remove(db.engine, "commit", fail)
    assert not db.rows("event")
    assert db.add("event", {"synthetic": True, "quantity": 1})
    assert len(db.rows("event")) == 1 and len(callbacks) == 2
    assert db.rows("outcome")[0]["net_return_pct"] == -100
    db.engine.dispose()


def test_unknown_quote_shortcut_preserves_config_reads_and_ineligibility(monkeypatch):
    import backend.app.early_edge as module

    calls = []
    original = module.load_intelligence_settings

    def settings():
        calls.append(1)
        return original()

    monkeypatch.setattr(module, "load_intelligence_settings", settings)

    def unnecessary(*args):
        raise AssertionError("Unknown quote must not repeat pure readiness work")

    monkeypatch.setattr(module, "readiness", unnecessary)
    t = Token("synthetic", "", "", 100)
    for quote in ["", "unknown"]:
        t.verified_quote_mint = quote
        assert module.signal_snapshot(t, {}, 101, Settings(mode="OBSERVE")) is None
    assert len(calls) == 2


@pytest.mark.parametrize("currency", ["SOL", "unknown"])
def test_cross_window_sharing_recomputes_all_horizon_dependent_fields(currency):
    t = Token("synthetic", "", "", 100)
    for i in range(5):
        t.events.append(
            MarketEvent(
                mint=t.mint,
                source="SYNTHETIC",
                event_id=str(i),
                ts=100 + i,
                kind="trade",
                side="buy" if i % 2 else "sell",
                volume=0.01 * (i + 1),
                currency=currency,
                wallet=f"w{i}",
                price=1 + i / 10,
            )
        )
    for now in [105, 105.01, 110, 130, 101, 200, 800]:
        actual = calculate_features(t, now)
        expected = {str(s): window_features(t.events, now, s, t.creator) for s in [10, 30, 60, 180, 300, 600]}
        assert actual == expected


def test_priority_mapping_preserves_all_states_and_tie_breaks():
    from backend.app.domain import State, _STATE_PRIORITIES

    original = {
        State.GRADUATING: 100,
        State.GRADUATED: 100,
        State.POST_GRAD_OBSERVATION: 95,
        State.ENTRY_CANDIDATE: 100,
        State.NEAR_GRADUATION: 90,
        State.MATURING: 70,
        State.WATCHING: 30,
    }
    rows = []
    for state in State:
        for curve in [None, 0, 80, 100]:
            for maturity in [0, 42]:
                t = Token(f"{state}-{curve}-{maturity}", "", "", 100, state=state)
                t.curve_progress = curve
                t.scores = {"maturity": maturity}
                expected = (original.get(state, 0), curve if curve is not None else -1, maturity, t.mint)
                assert t.priority() == expected
                rows.append((t, expected))
    assert sorted(rows, key=lambda r: r[0].priority()) == sorted(rows, key=lambda r: r[1])
    with pytest.raises(TypeError):
        _STATE_PRIORITIES[State.WATCHING] = 999
