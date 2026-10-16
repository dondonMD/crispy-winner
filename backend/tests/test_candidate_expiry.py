"""Expiry follows the current bounded polling schedule, without changing evidence."""

import pytest
from solders.pubkey import Pubkey

from backend.app.config import Settings
from backend.app.domain import State
from backend.app.engine import RadarEngine
from backend.tests.test_lifecycle_fairness import launch

START = 10000.0


@pytest.fixture
async def engine(tmp_path):
    e = RadarEngine(Settings(max_deep=1), tmp_path / "expiry.db")
    for _ in range(3):
        launch(e, str(Pubkey.new_unique()), START)
    for token in e.tokens.values():
        token.last_curve_attempt = START
    e.last_hot_batch = e.last_background_batch = START
    yield e
    await e.stop()


def background(e):
    return e.background_tokens(e.deep_mints())[0]


def test_healthy_inactive_expiry_and_metrics(engine):
    engine.expire_inactive_candidates(START + 300)
    assert len(engine.tokens) == 3
    engine.expire_inactive_candidates(START + 301)
    assert not engine.tokens
    assert engine.expiry_metrics == {"inactive_expirations": 3, "expiry_deferred_for_poll": 0}


@pytest.mark.parametrize("age", [301, 400, 500, 749])
def test_background_720_second_revisit_is_protected(engine, age):
    token = background(engine)
    engine.rpc.health["backoff_level"] = 2
    assert engine.rpc.interval(180, "background") == 720
    assert engine.candidate_expiry_deadline(token) == START + 750
    before = (token.last_event, token.last_curve, token.curve_progress, dict(token.security))
    engine.expire_inactive_candidates(START + age)
    assert token.mint in engine.tokens
    assert engine.expiry_metrics["expiry_deferred_for_poll"] == 2
    assert (token.last_event, token.last_curve, token.curve_progress, token.security) == before
    assert token.decision["decision"] == "WAIT"


def test_after_opportunity_and_grace_inactive_candidates_expire(engine):
    token = background(engine)
    engine.rpc.health["backoff_level"] = 2
    engine.expire_inactive_candidates(START + 751)
    assert token.mint not in engine.tokens
    assert not engine.tokens


def test_never_polled_uses_creation_not_zero(engine):
    token = background(engine)
    token.last_curve_attempt = 0
    engine.rpc.health["backoff_level"] = 2
    assert engine.candidate_expiry_deadline(token) == START + 750


def test_retry_after_global_and_background_backoff(engine):
    token = background(engine)
    engine.rpc.health.update(backoff_level=2, rate_limited_until=START + 900, next_eligible_rpc=START + 950)
    engine.background_backoff_until = START + 1000
    assert engine.candidate_expiry_deadline(token) == START + 1030
    engine.expire_inactive_candidates(START + 500)
    assert len(engine.tokens) == 3
    engine.expire_inactive_candidates(START + 1031)
    assert not engine.tokens


def test_heavy_background_probe_delay_is_included(engine):
    token = background(engine)
    engine.rpc.health.update(backoff_level=4, next_eligible_rpc=START + 3000)
    # Heavy eligibility includes the provider's additional background probe deferral.
    assert engine.candidate_expiry_deadline(token) == START + 3000 + 480 + 30


def test_bounded_retention_even_with_rolling_provider_outage(engine):
    engine.settings.candidate_expiry_max_seconds = 900
    token = background(engine)
    engine.rpc.health.update(
        backoff_level=4, rate_limited_until=START + 100000, next_eligible_rpc=START + 100000
    )
    assert engine.candidate_expiry_deadline(token) == START + 900
    engine.expire_inactive_candidates(START + 901)
    assert not engine.tokens


def test_recovery_converges_without_sticky_grace(engine):
    token = background(engine)
    engine.rpc.health["backoff_level"] = 2
    assert engine.candidate_expiry_deadline(token) == START + 750
    engine.rpc.health["backoff_level"] = 0
    assert engine.candidate_expiry_deadline(token) == START + 300
    engine.expire_inactive_candidates(START + 401)
    assert not engine.tokens


def test_hot_and_near_graduation_use_current_tier(engine):
    token = background(engine)
    engine.rpc.health["backoff_level"] = 2
    assert engine.candidate_expiry_deadline(token) == START + 750
    token.state = State.NEAR_GRADUATION
    token.last_curve_attempt = START + 280  # Recent in-flight hot lifecycle attempt.
    assert token.mint in engine.deep_mints()
    assert engine.candidate_expiry_deadline(token) == START + 385  # 280 + 75 + 30
    engine.expire_inactive_candidates(START + 301)
    assert token.mint in engine.tokens
    # Healthy current hot expectations do not inherit the slow background interval.
    engine.rpc.health["backoff_level"] = 0
    assert engine.candidate_expiry_deadline(token) == START + 340


@pytest.mark.parametrize("protection", ["position", "entry", "exit"])
def test_paper_protection(engine, protection):
    token = background(engine)
    if protection == "position":
        engine.paper.state["positions"][token.mint] = {}
    else:
        engine.paper.state["pending"][token.mint] = {"action": protection}
    engine.expire_inactive_candidates(START + 10000)
    assert (token.mint in engine.tokens) == (protection != "exit")
    # Keep teardown checkpoint independent of synthetic paper fixtures.
    engine.paper.state["positions"].clear()
    engine.paper.state["pending"].clear()


def test_demo_ignores_rpc_and_monitoring_only_states_are_not_deleted(engine):
    engine.settings.mode = "DEMO"
    engine.rpc.health.update(backoff_level=4, rate_limited_until=START + 100000)
    token = background(engine)
    token.state = State.GRADUATING
    other = next(t for t in engine.tokens.values() if t is not token)
    assert engine.candidate_expiry_deadline(other) == START + 300
    engine.expire_inactive_candidates(START + 301)
    assert list(engine.tokens) == [token.mint]


def test_bounded_queue_slots_and_admission_eviction(engine):
    assert Settings().max_candidates == 250 and Settings().max_deep == 25
    engine.settings.max_candidates = 3
    engine.settings.curve_background_batch_size = 1
    engine.rpc.health["backoff_level"] = 2
    waiting = sorted(
        engine.background_tokens(engine.deep_mints()),
        key=lambda t: (t.last_curve_attempt or t.created, t.created, t.mint),
    )
    assert engine.candidate_expiry_deadline(waiting[1]) == START + 720 + 120 + 30
    engine.expire_inactive_candidates(START + 400)
    assert len(engine.tokens) == 2  # The hot token had its fair opportunity and expired.
    launch(engine, str(Pubkey.new_unique()), START + 401)
    newcomer = str(Pubkey.new_unique())
    launch(engine, newcomer, START + 402)
    assert len(engine.tokens) == 3 and newcomer in engine.tokens
    assert len(engine.deep_mints()) == 1


def test_configuration_bounds():
    with pytest.raises(ValueError):
        Settings(candidate_inactivity_seconds=600, candidate_expiry_max_seconds=300)


async def test_monitor_uses_expiry_helper_and_reports_current_gauge(engine, monkeypatch):
    import asyncio
    from unittest.mock import AsyncMock

    engine.rpc.health["backoff_level"] = 2
    engine.last_lab = engine.last_maintenance = START + 500
    monkeypatch.setattr("backend.app.engine.time.time", lambda: START + 450)
    monkeypatch.setattr(engine, "analyse", lambda token, now: None)
    monkeypatch.setattr(engine.resources, "sample", lambda: engine.metrics.copy())
    monkeypatch.setattr("backend.app.engine.asyncio.sleep", AsyncMock(side_effect=asyncio.CancelledError))
    with pytest.raises(asyncio.CancelledError):
        await engine.run_loop()
    assert len(engine.tokens) == 2
    health = engine.snapshot()["health"]
    assert health["inactive_expirations"] == 1
    assert health["expiry_deferred_for_poll"] == 2
    # Repeated sweeps do not turn the gauge into a cumulative count.
    engine.expire_inactive_candidates(START + 450)
    assert engine.expiry_metrics["expiry_deferred_for_poll"] <= 2
