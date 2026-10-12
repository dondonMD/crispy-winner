import time
from unittest.mock import AsyncMock

import httpx
import pytest
from solders.pubkey import Pubkey

from backend.app.config import Settings
from backend.app.domain import MarketEvent, State
from backend.app.engine import RadarEngine
from backend.app.providers import SolanaProvider


def launch(engine, mint, now):
    engine.process(MarketEvent(mint=mint, ts=now, source="PumpPortal", kind="create", event_id=mint))


def observation(engine, mint, now, progress, identity):
    engine.process(
        MarketEvent(
            mint=mint,
            ts=now,
            source="Solana RPC",
            kind="curve",
            event_id=identity,
            evidence={
                "curve_progress": progress,
                "data_quality": "UNKNOWN" if progress is None else "VERIFIED",
            },
        )
    )


async def test_regression_hysteresis_scores_and_migration(tmp_path):
    e = RadarEngine(Settings(), tmp_path / "regression.db")
    now = time.time()
    mint = str(Pubkey.new_unique())
    launch(e, mint, now)
    t = e.tokens[mint]
    quality = (t.scores["maturity"], t.scores["momentum"])
    for i, (progress, state) in enumerate(
        [
            (84, State.MATURING),
            (86, State.NEAR_GRADUATION),
            (82, State.NEAR_GRADUATION),
            (75, State.NEAR_GRADUATION),
            (70, State.MATURING),
            (90, State.NEAR_GRADUATION),
            (100, State.NEAR_GRADUATION),
        ]
    ):
        observation(e, mint, now, progress, f"curve:{i}")
        assert t.state == state
        assert (t.scores["maturity"], t.scores["momentum"]) == quality
        assert t.decision["decision"] == "WAIT" and t.graduation is None
    assert e.token_view(t, now)["curve_peak_progress"] == 100
    observation(e, mint, now, 60.2, "retreat")
    assert t.state == State.MATURING and t.curve_peak_progress == 100
    e.process(MarketEvent(mint=mint, ts=now, source="PumpPortal", kind="migration", event_id="migration"))
    assert t.state == State.POST_GRAD_OBSERVATION and t.graduation == now
    observation(e, mint, now, 20, "post-migration-curve")
    assert t.state == State.POST_GRAD_OBSERVATION
    await e.stop()


@pytest.mark.parametrize("progress", [None, 90])
async def test_unknown_or_stale_does_not_keep_near_label(tmp_path, progress):
    e = RadarEngine(Settings(), tmp_path / "unknown.db")
    now = time.time()
    mint = str(Pubkey.new_unique())
    launch(e, mint, now)
    observation(e, mint, now, 90, "maturing")
    e.analyse(e.tokens[mint], now)
    assert e.tokens[mint].state == State.NEAR_GRADUATION
    if progress is None:
        observation(e, mint, now, None, "unknown")
    else:
        e.analyse(e.tokens[mint], now + 61)
    assert e.tokens[mint].state == State.MATURING
    assert e.tokens[mint].curve_peak_progress == 90
    e.analyse(e.tokens[mint], now + 61)
    assert e.tokens[mint].state == State.WATCHING
    await e.stop()


async def test_all_250_receive_fair_sweeps_without_extra_services(tmp_path, monkeypatch):
    now = time.time()
    clock = [now]
    monkeypatch.setattr("backend.app.engine.time.time", lambda: clock[0])
    e = RadarEngine(Settings(), tmp_path / "fair.db")
    for _ in range(250):
        launch(e, str(Pubkey.new_unique()), now)
    # Fix 25 hot members at moderate meaningful progress; background stays WATCHING.
    hot = set(e.deep_mints())
    for mint in hot:
        observation(e, mint, now, 40, "hot:" + mint)
    e.rpc.inspect = AsyncMock()
    e.dex.markets = AsyncMock(return_value=[])
    seen = set()
    background_seen = set()
    background_calls = []

    async def curves(mints, size, **kwargs):
        assert len(mints) <= 25
        seen.update(mints)
        if kwargs.get("retry_attempts") == 1:
            background_calls.append(set(mints))
            assert set(mints).isdisjoint(hot)
            background_seen.update(mints)
        return {m: {"curve_progress": 40 if m in hot else 5, "data_quality": "VERIFIED"} for m in mints}

    e.rpc.curve_progress_batch = AsyncMock(side_effect=curves)
    for tick in range(19):
        clock[0] = now + tick * 30
        await e.enrich_once()
        for event in e.queue.drain():
            e.process(event)
        assert len(e.deep_mints()) == 25
    assert seen == set(e.tokens)
    assert background_seen == set(e.tokens) - hot
    assert len(background_calls) >= 18  # Every background token receives a second visit.
    assert max(clock[0] - t.last_curve_attempt for t in e.background_tokens(hot)) <= 270
    assert e.rpc.inspect.await_count == 0
    assert all(c.args[0] == [] for c in e.dex.markets.call_args_list)
    assert len(e.pump.subscribed) == 0 and e.queue.dropped == 0
    health = e.snapshot()["health"]
    assert health["curve_background_poll_requests"] == len(background_calls)
    assert health["background_candidates"] == 225
    assert health["curve_accounts_checked"] == health["curve_accounts_attempted"]
    await e.stop()


async def test_background_promotion_and_new_arrival_fairness(tmp_path, monkeypatch):
    now = time.time()
    clock = [now]
    monkeypatch.setattr("backend.app.engine.time.time", lambda: clock[0])
    e = RadarEngine(
        Settings(max_candidates=10, max_deep=2, curve_background_batch_size=2), tmp_path / "promote.db"
    )
    for _ in range(8):
        launch(e, str(Pubkey.new_unique()), now)
    hot = set(e.deep_mints())
    for mint in hot:
        observation(e, mint, now, 40, "hot:" + mint)
    oldest = min(e.background_tokens(hot), key=lambda t: (t.created, t.mint)).mint
    e.rpc.inspect = AsyncMock(return_value={"data_quality": "UNKNOWN"})
    e.dex.markets = AsyncMock(return_value=[])
    polled = []

    async def curves(mints, size, **kwargs):
        if kwargs:
            polled.extend(mints)
        return {m: {"curve_progress": 90 if m == oldest else 40 if m in hot else 5} for m in mints}

    e.rpc.curve_progress_batch = AsyncMock(side_effect=curves)
    await e.enrich_once()
    assert e.rpc.inspect.await_count == 0  # Promotion cannot start security from background tier.
    for event in e.queue.drain():
        e.process(event)
    assert oldest in e.deep_mints() and e.tokens[oldest].state == State.MATURING
    e.analyse(e.tokens[oldest], now)
    assert e.tokens[oldest].state == State.NEAR_GRADUATION
    clock[0] += 30
    new = str(Pubkey.new_unique())
    launch(e, new, clock[0])
    await e.enrich_once()
    assert e.rpc.inspect.call_args.args[0] in e.deep_mints()
    assert new not in polled  # Older waiting tokens precede the new arrival.
    await e.stop()


async def test_rate_limit_suppresses_background_first_and_recovers(tmp_path, monkeypatch):
    now = time.time()
    clock = [now]
    monkeypatch.setattr("backend.app.engine.time.time", lambda: clock[0])
    e = RadarEngine(
        Settings(max_candidates=4, max_deep=1, curve_background_batch_size=2), tmp_path / "429.db"
    )
    for _ in range(4):
        launch(e, str(Pubkey.new_unique()), now)
    e.rpc.inspect = AsyncMock()
    e.dex.markets = AsyncMock(return_value=[])

    async def curves(mints, size, **kwargs):
        if kwargs:
            e.rpc.health.update(
                errors=1, rate_limits=1, rate_limited_until=clock[0] + 10, attempted=True, connected=False
            )
            raise RuntimeError("429")
        return {m: {"curve_progress": 5} for m in mints}

    e.rpc.curve_progress_batch = AsyncMock(side_effect=curves)
    await e.enrich_once()
    assert e.curve_metrics["curve_background_poll_requests"] == 1
    assert e.snapshot()["health"]["providers"]["Solana RPC"]["status"] == "RATE LIMITED"
    for event in e.queue.drain():
        e.process(event)
    clock[0] += 30
    await e.enrich_once()
    assert e.curve_metrics["curve_hot_poll_requests"] == 2
    assert e.curve_metrics["curve_background_poll_requests"] == 1

    # Expired backoff permits a single background recovery probe, oldest-first.
    async def recovered(mints, size, **kwargs):
        return {m: {"curve_progress": 5} for m in mints}

    e.rpc.curve_progress_batch = AsyncMock(side_effect=recovered)
    clock[0] += 31
    await e.enrich_once()
    assert e.curve_metrics["curve_background_poll_requests"] == 2
    assert e.background_backoff_level == 0
    await e.stop()


async def test_background_http_429_has_no_retry_storm():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(429, headers={"Retry-After": "120"})

    rpc = SolanaProvider(httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    with pytest.raises(RuntimeError):
        await rpc.curve_progress_batch([str(Pubkey.new_unique())], retry_attempts=1)
    assert len(calls) == 1 and rpc.health["rate_limits"] == 1
    assert rpc.health["rate_limited_until"] > time.time()
    await rpc.close()


def test_hysteresis_threshold_validation():
    for exit_pct in [30, 85, 90]:
        with pytest.raises(ValueError):
            Settings(lifecycle_near_exit_pct=exit_pct)


async def test_expiry_during_curve_request_does_not_stop_enrichment(tmp_path):
    e = RadarEngine(Settings(max_candidates=2, max_deep=1), tmp_path / "expiry.db")
    now = time.time()
    mint = str(Pubkey.new_unique())
    launch(e, mint, now)

    async def curves(mints, size):
        del e.tokens[mints[0]]  # Monitor expiry while an HTTP response was in flight.
        return {m: {"curve_progress": 40} for m in mints}

    e.rpc.curve_progress_batch = AsyncMock(side_effect=curves)
    e.rpc.inspect = AsyncMock()
    e.dex.markets = AsyncMock(return_value=[])
    await e.enrich_once()
    for event in e.queue.drain():
        assert not e.process(event)
    assert not e.tokens and e.rpc.inspect.await_count == 0
    await e.stop()


async def test_resource_pressure_pauses_background_without_enlarging_hot_set(tmp_path):
    e = RadarEngine(Settings(max_candidates=4, max_deep=2), tmp_path / "pressure.db")
    now = time.time()
    for _ in range(4):
        launch(e, str(Pubkey.new_unique()), now)
    e.metrics["resource_pressure"] = True
    e.rpc.curve_progress_batch = AsyncMock(return_value={})
    e.rpc.inspect = AsyncMock()
    e.dex.markets = AsyncMock(return_value=[])
    await e.enrich_once()
    assert len(e.deep_mints()) == 1
    assert e.rpc.curve_progress_batch.await_count == 1
    assert e.curve_metrics["curve_background_poll_requests"] == 0
    assert e.snapshot()["health"]["background_candidates_waiting"] == 3
    await e.stop()


async def test_restart_requires_new_lifecycle_evidence_and_resets_session_peak(tmp_path):
    path = tmp_path / "restart.db"
    e = RadarEngine(Settings(), path)
    now = time.time()
    mint = str(Pubkey.new_unique())
    launch(e, mint, now)
    observation(e, mint, now, 90, "progress")
    e.analyse(e.tokens[mint], now)
    assert e.tokens[mint].state == State.NEAR_GRADUATION
    await e.stop()
    restarted = RadarEngine(Settings(), path)
    assert restarted.tokens[mint].state == State.WATCHING
    assert restarted.tokens[mint].curve_progress is None
    assert restarted.tokens[mint].curve_peak_progress is None
    await restarted.stop()
