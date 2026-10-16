from copy import deepcopy
from collections import deque

import pytest
from solders.pubkey import Pubkey

from backend.app.config import Settings
from backend.app.domain import State, Token, MarketEvent
from backend.app.engine import RadarEngine
from backend.app.opportunity import IntelligenceSettings, opportunity_view, curve_dynamics

NOW = 10000.0


def candidate(values=(30, 36, 42, 48), times=None, security=True):
    token = Token(str(Pubkey.new_unique()), "Research token", "TEST", NOW - 240)
    token.state = State.MATURING
    times = times or [NOW - (len(values) - 1 - i) * 60 for i in range(len(values))]
    token.curve_history = deque(zip(times, values), maxlen=32)
    token.curve_progress = values[-1]
    token.curve_peak_progress = max(values)
    token.last_curve = times[-1]
    token.security = {
        "data_quality": "VERIFIED" if security else "UNKNOWN",
        "risk_score": 10,
        "last_updated": NOW,
        "hard_failures": [],
        "warnings": [],
    }
    token.features = {"180": {}}
    return token


def test_irregular_velocity_acceleration_and_minimum_coverage():
    t = candidate([10, 14, 22], [NOW - 120, NOW - 80, NOW])
    d = curve_dynamics(t, NOW, IntelligenceSettings())
    assert d.medium_velocity_pp_min == 6
    assert d.short_velocity_pp_min == 6
    assert d.acceleration_pp_min2 == 0
    assert d.persistence == 1 and d.coverage_seconds == 120
    for values, times in [([10], [NOW]), ([10, 20, 30], [NOW - 2, NOW - 1, NOW])]:
        d = curve_dynamics(candidate(values, times), NOW, IntelligenceSettings())
        assert d.medium_velocity_pp_min is None and d.acceleration_pp_min2 is None


@pytest.mark.parametrize("age", [181, 500, 2000])
def test_stale_not_current_or_zero_velocity(age):
    t = candidate()
    result = opportunity_view(t, Settings(), NOW + age)
    assert result.action == "DATA_LIMITED"
    assert result.dynamics.current is None and result.dynamics.medium_velocity_pp_min is None


def test_persistence_ranks_above_stagnation_without_fake_trade_flow():
    t = candidate(security=False)
    progressing = opportunity_view(t, Settings(), NOW)
    stationary = opportunity_view(candidate([30, 30, 30, 30], security=False), Settings(), NOW)
    assert progressing.action == "EARLY_OPPORTUNITY"
    assert progressing.ranking_score > stationary.ranking_score
    assert progressing.trade_evidence == "UNAVAILABLE" and "NO TRADE FLOW" in progressing.evidence_grade
    assert "SECURITY UNKNOWN" in progressing.evidence_grade
    assert progressing.validated_edge is False and progressing.manual_execution_only
    assert "never a validated buy" in progressing.summary
    assert progressing.entry_context["maximum_chase"] is None


def test_regression_peak_pullback_and_collapse():
    result = opportunity_view(candidate([30, 45, 60, 54]), Settings(), NOW)
    assert result.action == "PULLBACK_WATCH"
    assert result.dynamics.retreat_pp == 6 and result.dynamics.quality == "REGRESSING"
    assert result.dynamics.peak == 60 and result.dynamics.current == 54
    assert opportunity_view(candidate([30, 50, 80, 40]), Settings(), NOW).action == "DATA_LIMITED"


@pytest.mark.parametrize("risk", ["hard", "reject", "creator", "disagreement"])
def test_explicit_hard_risks_always_avoid(risk):
    t = candidate()
    if risk == "hard":
        t.security["hard_failures"] = ["Unsafe authority"]
    if risk == "reject":
        t.decision = {"decision": "REJECT", "reasons": ["Core risk gate"]}
    if risk == "creator":
        t.features["180"]["creator_sell_volume"] = 1
    if risk == "disagreement":
        t.disagreement = True
    assert opportunity_view(t, Settings(), NOW).action == "AVOID"


def test_high_curve_alone_not_too_extended_but_core_missed_is():
    t = candidate([90, 92, 94, 96])
    assert opportunity_view(t, Settings(), NOW).action == "EARLY_OPPORTUNITY"
    t.decision = {"decision": "MISSED", "reasons": ["Observed chase"]}
    assert opportunity_view(t, Settings(), NOW).action == "TOO_EXTENDED"


def test_no_curve_history_data_limited_and_deterministic_nonmutating():
    t = candidate()
    before = deepcopy(t)
    a = opportunity_view(t, Settings(), NOW)
    assert a == opportunity_view(t, Settings(), NOW) and t == before
    t.curve_history.clear()
    assert opportunity_view(t, Settings(), NOW).action == "DATA_LIMITED"


def test_no_future_samples_or_stale_launch_market_cap():
    t = candidate()
    first = opportunity_view(t, Settings(), NOW)
    t.curve_history.append((NOW + 100, 99))
    t.market_cap = 123456
    t.last_market_cap = NOW
    t.cap_source = "PumpPortal"
    assert opportunity_view(t, Settings(), NOW) == first
    assert first.market_context["market_cap_usd"] is None


def test_market_freshness_has_its_own_timestamp():
    t = candidate()
    t.market_cap = 10000
    t.cap_source = "DEX Screener"
    t.last_market_cap = NOW - 21
    t.price = 1
    t.last_price = NOW
    t.market_source = "DEX Screener"
    r = opportunity_view(t, Settings(), NOW)
    assert r.market_context["price_usd"] == 1
    assert r.market_context["market_cap_usd"] is None


async def test_engine_bounded_verified_history_and_core_isolation(tmp_path):
    e = RadarEngine(Settings(), tmp_path / "history.db")
    mint = str(Pubkey.new_unique())
    e.process(MarketEvent(mint=mint, ts=NOW - 60, source="PumpPortal", kind="create", event_id="launch"))
    try:
        for i in range(45):
            e.process(
                MarketEvent(
                    mint=mint,
                    ts=NOW + i,
                    source="Solana RPC",
                    kind="curve",
                    event_id=str(i),
                    evidence={"curve_progress": 30 + i, "data_quality": "VERIFIED"},
                )
            )
        t = e.tokens[mint]
        assert len(t.curve_history) == 32 and t.curve_history[-1] == (NOW + 44, 74)
        e.process(
            MarketEvent(
                mint=mint,
                ts=NOW + 45,
                source="Solana RPC",
                kind="curve",
                event_id="unknown",
                evidence={"curve_progress": None, "data_quality": "UNKNOWN"},
            )
        )
        assert len(t.curve_history) == 32
        assert opportunity_view(t, e.settings, NOW + 45).action == "DATA_LIMITED"
        before = (
            deepcopy(t.decision),
            deepcopy(e.paper.state),
            e.approved_evidence,
            e.version,
            deepcopy(e.rpc.health),
        )
        for _ in range(10):
            e.intelligence.refresh(NOW + 46, force=True)
            e.snapshot()
        assert before == (t.decision, e.paper.state, e.approved_evidence, e.version, e.rpc.health)
        assert t.decision["decision"] == "WAIT"
        assert e.db.rows("evidence") == [] and e.paper.state["cash"] == 20
    finally:
        await e.stop()


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), True, -1])
def test_invalid_trade_features_never_get_current_evidence(bad):
    t = candidate()
    t.last_trade = NOW
    t.features["180"] = {"units_valid": True, "flow_ratio": bad, "estimated_independent_buyers": 30}
    assert opportunity_view(t, Settings(trade_stream_enabled=True), NOW).trade_evidence == "UNAVAILABLE"


async def test_dex_fdv_is_never_projected_as_current_market_cap(tmp_path, monkeypatch):
    import httpx
    from backend.app.providers import DexScreenerProvider

    monkeypatch.setattr("backend.app.providers.time.time", lambda: NOW)
    t = candidate()
    pair = {
        "chainId": "solana",
        "baseToken": {"address": t.mint},
        "dexId": "pumpswap",
        "priceUsd": "1",
        "fdv": 1000000,
        "pairAddress": "pair",
        "liquidity": {"usd": 50000},
    }
    provider = DexScreenerProvider(
        httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=[pair])))
    )
    e = RadarEngine(Settings(), tmp_path / "fdv.db", offline=True)
    e.tokens[t.mint] = t
    try:
        events = await provider.markets([t.mint])
        assert events[0].evidence["market_cap_kind"] == "FDV"
        e.process(events[0])
        assert opportunity_view(t, e.settings, NOW).market_context["market_cap_usd"] is None
        assert e.token_view(t, NOW)["market_cap"] is None
        provider.cache.clear()
        pair["marketCap"] = 500000
        events = await provider.markets([t.mint])
        events[0].event_id += "-real-cap"
        e.process(events[0])
        assert opportunity_view(t, e.settings, NOW).market_context["market_cap_usd"] == 500000
    finally:
        await provider.close()
        await e.stop()


def test_decline_without_prior_progress_is_not_a_pullback_opportunity():
    assert opportunity_view(candidate([60, 58, 56, 54]), Settings(), NOW).action == "DEVELOPING"


def test_rejected_lifecycle_cannot_be_presented_as_early_even_if_core_snapshot_changed():
    t = candidate()
    t.state = State.REJECTED
    t.decision = {"decision": "WAIT", "reasons": []}
    assert opportunity_view(t, Settings(), NOW).action == "AVOID"
