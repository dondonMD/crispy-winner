"""Deterministic observations, never prospective profits or production mocks."""

import json
from collections import deque
from copy import deepcopy

import pytest

from backend.app.config import Settings
from backend.app.domain import Token, State, MarketEvent
from backend.app.features import calculate_features
from backend.app.opportunity import IntelligenceSettings, curve_dynamics, early_market_view

NOW = 10000.0


def candidate(age=65, units="SOL"):
    t = Token("SYNTHETIC-MINT", "Synthetic", "TEST", NOW - age, creator="creator")
    t.state = State.WATCHING
    t.trade_tracking_since = NOW - age
    t.curve_history = deque([(NOW - age, 30), (NOW - age / 2, 35), (NOW, 40)], maxlen=32)
    t.curve_progress = t.curve_peak_progress = 40
    t.last_curve = NOW
    t.security = dict(
        data_quality="VERIFIED",
        last_updated=NOW,
        hard_failures=[],
        creator_pct=1,
        top_1_independent_pct=5,
        top_5_independent_pct=20,
    )
    # Different sizes/times, no accidental matched-size coordination signal.
    t.events = deque(
        [
            MarketEvent(
                mint=t.mint,
                ts=NOW - i,
                source="Solana WSS",
                kind="trade",
                event_id=f"synthetic:{i}",
                side="buy",
                wallet=f"buyer-{i}",
                volume=1 + i / 13,
                currency=units,
            )
            for i in range(1, int(min(age, 60)), 3)
        ],
        maxlen=500,
    )
    prepare(t)
    return t


def prepare(t):
    t.events = deque(sorted(t.events, key=lambda e: e.ts), maxlen=500)
    t.last_trade = max((e.ts for e in t.events if e.kind == "trade"), default=0)
    t.last_analysis = NOW
    t.features = calculate_features(t, NOW)
    for f in t.features.values():
        f["continuity_valid"] = False  # No fabricated strict CURRENT.


def view(t, clean=None, pending=False, now=NOW):
    cfg = IntelligenceSettings()
    return early_market_view(
        t,
        Settings(),
        cfg,
        now,
        curve_dynamics(t, now, cfg),
        now - t.trade_tracking_since if clean is None else clean,
        {s: pending for s in (10, 30, 60, 180)},
    )


def test_developing_bullish_is_separate_from_current_and_immutable():
    t = candidate()
    before = deepcopy(t.__dict__)
    r = view(t)
    assert r["classification"] == "BULLISH DEVELOPING" and r["speculative_review"]
    assert r["windows"]["60"]["complete"] and not r["windows"]["180"]["complete"]
    assert r["price"] is None and not r["validated_edge"]
    assert r["uncertainty"] == "HIGH"
    assert before == t.__dict__
    assert not t.features["180"]["continuity_valid"]


def test_10_second_activity_can_emerge_before_180():
    t = candidate(age=15)
    r = view(t)
    assert r["classification"] == "ACTIVE EMERGING BULLISH"
    assert r["windows"]["10"]["complete"] and not r["windows"]["30"]["complete"]


def test_pump_followed_by_sell_pressure_and_buying_exhaustion():
    t = candidate()
    for e in t.events:
        if e.ts >= NOW - 30:
            e.side = "sell"
    prepare(t)
    r = view(t)
    assert r["classification"] == "BEARISH PRESSURE" and not r["speculative_review"]
    assert r["price"] is None  # Trade direction cannot make a pump price series.
    for e in t.events:
        e.ts -= 12
    prepare(t)
    # Earlier buys alone never imply ongoing bullish continuation.
    assert view(t, now=NOW + 40)["classification"] == "INSUFFICIENT DATA"


def test_verified_curve_pullback_with_renewed_buying():
    t = candidate()
    t.curve_peak_progress = 50
    r = view(t)
    assert r["classification"] == "PULLBACK WATCH"
    assert any("not a price pullback" in x for x in r["interpretation"])


def test_truncated_active_history_does_not_become_complete():
    t = candidate(age=240)
    t.events = deque(
        [
            MarketEvent(
                mint=t.mint,
                ts=NOW - 10 + i / 100,
                source="Solana WSS",
                kind="trade",
                event_id=f"burst:{i}",
                side="buy",
                wallet=f"b{i}",
                currency="SOL",
                volume=1 + i / 999,
            )
            for i in range(500)
        ],
        maxlen=500,
    )
    t.buffer_loss_at = NOW - 8
    prepare(t)
    r = view(t, clean=8)
    assert r["classification"] == "INSUFFICIENT DATA"
    assert all(not w["complete"] for w in r["windows"].values())
    assert len(t.events) == 500 and not t.features["180"]["continuity_valid"]


def test_coordinated_wallets_withhold_bullish_attention():
    t = candidate()
    for i, e in enumerate(t.events):
        e.ts = NOW - 2 + i * 0.01
        e.volume = 1
    prepare(t)
    r = view(t)
    assert r["classification"] == "AVOID"
    assert any("Suspected coordinated" in x for x in r["interpretation"])
    assert not r["speculative_review"]


def test_unknown_units_allow_counts_but_never_amount_or_chart_claim():
    t = candidate(units="unknown")
    r = view(t)
    w = r["windows"]["30"]
    assert w["buys"] > 0 and w["raw_unique_buyers"] > 0
    assert w["independent_buyers"] is None and w["net_flow"] is None and w["flow_ratio"] is None
    assert w["coordination_suspected"] is None and r["price"] is None
    assert r["classification"] == "ACTIVE EMERGING BULLISH" and r["uncertainty"] == "VERY HIGH"


@pytest.mark.parametrize("kind", ["stale", "recovery", "late_discovery", "unverified_curve"])
def test_missing_coverage_never_promoted(kind):
    t = candidate()
    if kind == "unverified_curve":
        t.curve_history.clear()
    r = view(
        t,
        pending=kind == "recovery",
        clean=4 if kind == "late_discovery" else None,
        now=NOW + 100 if kind == "stale" else NOW,
    )
    assert r["classification"] == "INSUFFICIENT DATA" and not r["speculative_review"]


@pytest.mark.parametrize("risk", ["hard", "creator", "concentration", "disagreement"])
def test_hard_risk_overrides_momentum_even_when_units_unknown(risk):
    t = candidate(units="unknown")
    if risk == "hard":
        t.security["hard_failures"] = ["SYNTHETIC restriction"]
    elif risk == "creator":
        t.events[-1].side = "sell"
        t.events[-1].wallet = "creator"
        prepare(t)
    elif risk == "concentration":
        t.security["top_1_independent_pct"] = 11
    else:
        t.disagreement = True
    assert view(t)["classification"] == "AVOID" and not view(t)["speculative_review"]


def test_only_timestamped_provider_marks_can_describe_price_and_chase():
    t = candidate()
    for i, price in enumerate((1, 2, 3)):
        t.events.append(
            MarketEvent(
                mint=t.mint,
                ts=NOW - 9 + i * 3,
                kind="market",
                source="DEX Screener",
                event_id=f"mark:{i}",
                currency="USD",
                price=price,
            )
        )
    prepare(t)
    assert view(t)["price"]["pattern"] == "RISING SAMPLED MARKS"
    for e in t.events:
        if e.kind == "market":
            e.source = "Manual journal"
    prepare(t)
    assert view(t)["price"] is None
    t.curve_history[-1] = (NOW, 86)
    t.curve_progress = 86
    t.curve_peak_progress = 86
    assert view(t)["classification"] == "TOO EXTENDED"


async def test_integration_preserves_original_projection_paper_and_receipts(tmp_path):
    from backend.app.engine import RadarEngine
    from backend.app.opportunity import opportunity_view

    e = RadarEngine(Settings(mode="OBSERVE"), tmp_path / "isolated.db", offline=True)
    t = candidate()
    e.tokens[t.mint] = t
    e.onchain.health.update(connected=True, connected_since=NOW - 65)
    old = opportunity_view(t, e.settings, NOW, e.intelligence.cfg).model_dump(mode="json")
    paper = json.dumps(e.paper.state, sort_keys=True)
    try:
        projected = e.intelligence.project(t, NOW).model_dump(mode="json")
        assert projected["early_market"]["speculative_review"]
        assert e.intelligence.project(t, NOW, manual=False).early_market is None
        assert {k: v for k, v in projected.items() if k != "early_market"} == {
            k: v for k, v in old.items() if k != "early_market"
        }
        assert e.approved_evidence is None and json.dumps(e.paper.state, sort_keys=True) == paper
        assert e.trade_status(t, NOW) != "CURRENT"
        assert e.token_evidence_receipt(NOW)["current"]["tokens"]
    finally:
        await e.stop()


def test_active_ten_seconds_can_coexist_with_declining_thirty_second_history():
    t = candidate()
    # Heavy earlier activity; only a few recent buys, still source-fresh.
    for i in range(20):
        t.events.append(
            MarketEvent(
                mint=t.mint,
                ts=NOW - 20 - i / 10,
                source="Solana WSS",
                kind="trade",
                event_id=f"exhaust:{i}",
                side="buy",
                wallet=f"old-{i}",
                volume=1 + i / 7,
                currency="SOL",
            )
        )
    prepare(t)
    r = view(t)
    assert r["classification"] == "ACTIVE EMERGING BULLISH"
    assert any("declined" in x for x in r["warnings"])
    assert r["speculative_review"]


def test_loss_watermark_caps_optimistic_context_and_future_data_is_excluded():
    t = candidate(age=240)
    t.buffer_loss_at = NOW - 5
    r = view(t, clean=240)
    assert r["classification"] == "INSUFFICIENT DATA"
    assert all(w["coverage_seconds"] <= 5 for w in r["windows"].values())
    t = candidate()
    before = view(t)["windows"]["10"]["samples"]
    t.events.append(
        MarketEvent(
            mint=t.mint,
            ts=NOW + 1,
            source="Solana WSS",
            kind="trade",
            event_id="future",
            side="buy",
            wallet="future",
            volume=100,
            currency="SOL",
        )
    )
    assert view(t)["windows"]["10"]["samples"] == before
    assert view(t)["price"] is None


def test_unknown_and_invalid_distribution_are_not_silent_safety():
    t = candidate()
    t.security.pop("top_5_independent_pct")
    r = view(t)
    assert "DISTRIBUTION UNKNOWN" in r["security"] and r["uncertainty"] == "VERY HIGH"
    t.security["top_5_independent_pct"] = float("nan")
    r = view(t)
    assert r["classification"] == "AVOID" and not r["speculative_review"]
    json.dumps(r, allow_nan=False)


def test_severe_curve_regression_is_not_promoted_as_pullback_recovery():
    t = candidate()
    t.curve_peak_progress = 70
    r = view(t)
    assert r["classification"] == "BEARISH PRESSURE" and not r["speculative_review"]
    assert any("collapse boundary" in text for text in r["interpretation"])


def test_research_display_expires_with_its_underlying_evidence():
    t = candidate()
    t.security["last_updated"] = NOW - Settings().security_ttl_seconds + 1
    assert view(t)["valid_until"] == NOW + 1
    t.security["last_updated"] = NOW
    for i, price in enumerate((1, 2, 3)):
        t.events.append(
            MarketEvent(
                mint=t.mint,
                ts=NOW - 19 + i,
                kind="market",
                source="DEX Screener",
                event_id=f"expiry:{i}",
                currency="USD",
                price=price,
            )
        )
    prepare(t)
    assert view(t)["valid_until"] == NOW + 3


def test_known_net_selling_cannot_be_hidden_by_many_small_buys():
    t = candidate()
    t.events[-1].side = "sell"
    t.events[-1].volume = 1000
    prepare(t)
    r = view(t)
    assert r["windows"]["30"]["buys"] > r["windows"]["30"]["sells"]
    assert r["windows"]["30"]["net_flow"] < 0
    assert r["classification"] == "BEARISH PRESSURE" and not r["speculative_review"]


def quiet_positive_history():
    t = candidate()
    t.events = deque(
        [
            MarketEvent(
                mint=t.mint,
                ts=NOW - age,
                source="Solana WSS",
                kind="trade",
                event_id=f"quiet:{i}",
                side="buy" if i < 5 else "sell",
                wallet=f"history-{i}",
                volume=1 + i / 11,
                currency="SOL",
            )
            for i, age in enumerate((18, 17, 16, 14, 13, 12.62))
        ],
        maxlen=500,
    )
    prepare(t)
    return t


def test_minemons_like_positive_history_is_cooling_not_active_or_bearish():
    t = quiet_positive_history()
    r = view(t)
    assert r["windows"]["10"]["samples"] == 0
    assert r["windows"]["30"]["buys"] == 5 and r["windows"]["30"]["sells"] == 1
    assert r["windows"]["30"]["net_flow"] > 0
    assert r["classification"] == "BUYING COOLING / WAIT"
    assert r["activity_state"] == "QUIET" and not r["active_buying"] and not r["speculative_review"]
    assert r["valid_until"] > NOW  # Valid assessment is distinct from active momentum.
    assert r["supporting_window_seconds"] == 30
    assert r["latest_trade_age"] == pytest.approx(12.62)


def test_pepeoz_like_clean_ten_seconds_is_count_led_and_early():
    t = candidate(age=25)
    t.security["data_quality"] = "UNKNOWN"
    t.events = deque(
        [
            MarketEvent(
                mint=t.mint,
                ts=NOW - 9 + i / 4,
                source="Solana WSS",
                kind="trade",
                event_id=f"active:{i}",
                side="buy" if i < 19 else "sell",
                wallet=f"observed-{i % 3}",
                volume=0 if i < 9 else 1 + i / 17,
                currency="unknown" if i < 9 else "SOL",
            )
            for i in range(26)
        ],
        maxlen=500,
    )
    prepare(t)
    r = view(t)
    assert r["classification"] == "ACTIVE EMERGING BULLISH" and r["speculative_review"]
    assert r["supporting_window_seconds"] == 10 and r["active_buying"]
    assert r["windows"]["10"]["buys"] == 19 and r["windows"]["10"]["sells"] == 7
    assert r["uncertainty"] == "VERY HIGH"
    assert r["windows"]["10"]["net_flow"] is None and r["windows"]["10"]["independent_buyers"] is None
    assert not r["windows"]["30"]["complete"] and not r["windows"]["180"]["complete"]
    assert not t.features["180"]["continuity_valid"] and r["price"] is None


def test_quiet_curve_pullback_requires_genuine_new_buying():
    t = quiet_positive_history()
    t.curve_peak_progress = 50
    before = view(t)
    assert before["classification"] == "BUYING COOLING / WAIT"
    for i in range(3):
        t.events.append(
            MarketEvent(
                mint=t.mint,
                ts=NOW - 3 + i,
                source="Solana WSS",
                kind="trade",
                event_id=f"renewed:{i}",
                side="buy",
                wallet=f"new-{i}",
                volume=3 + i / 7,
                currency="SOL",
            )
        )
    prepare(t)
    after = view(t)
    assert (
        after["classification"] == "PULLBACK WATCH" and after["active_buying"] and after["speculative_review"]
    )
    assert before["windows"]["10"]["samples"] == 0  # Prior snapshot was not rewritten.


def test_immediate_selling_overturns_older_positive_history():
    t = candidate()
    for i in range(5):
        t.events.append(
            MarketEvent(
                mint=t.mint,
                ts=NOW - 1 - i / 10,
                source="Solana WSS",
                kind="trade",
                event_id=f"selling:{i}",
                side="sell",
                wallet=f"seller-{i}",
                volume=5 + i / 7,
                currency="SOL",
            )
        )
    prepare(t)
    r = view(t)
    assert r["classification"] == "BEARISH PRESSURE" and not r["speculative_review"]
    assert r["supporting_window_seconds"] == 10 and r["activity_state"] == "SELL DOMINANT"


def test_pending_or_missing_ten_second_coverage_is_not_proven_quiet():
    t = quiet_positive_history()
    for kw in ({"pending": True}, {"clean": 4}):
        r = view(t, **kw)
        assert r["classification"] == "INSUFFICIENT DATA"
        assert r["activity_state"] == "UNAVAILABLE" and not r["speculative_review"]


def test_late_processed_trade_cannot_rewrite_frozen_assessment():
    t = candidate(age=15)
    prefix = deepcopy(t)  # Availability cut: source-time filtering alone is insufficient.
    recorded = view(prefix)
    immutable = deepcopy(recorded)
    late = MarketEvent(
        mint=t.mint,
        ts=NOW - 1,
        source="Solana WSS",
        kind="trade",
        event_id="later-processed-old-source-time",
        side="sell",
        wallet="later",
        volume=100,
        currency="SOL",
    )
    t.events.append(late)  # This processing occurs at NOW+2, after the frozen cut.
    t.last_analysis = NOW + 2
    t.features = calculate_features(t, NOW + 2)
    current = view(t, now=NOW + 2)
    assert current["windows"]["30"]["samples"] == recorded["windows"]["30"]["samples"] + 1
    assert recorded == immutable and view(prefix) == immutable
    assert recorded["classification"] == "ACTIVE EMERGING BULLISH"
    assert current["classification"] == "BEARISH PRESSURE"


def test_no_activity_after_last_buy_expires_active_interpretation():
    t = candidate(age=15)
    active = view(t)
    assert active["speculative_review"]
    assert active["valid_until"] <= t.last_trade + 10
    after = view(t, now=NOW + 11)
    assert not after["active_buying"] and not after["speculative_review"]
    assert after["classification"] != "BEARISH PRESSURE"  # No new selling was observed.


def test_continuously_strengthening_buys_retain_supported_developing_status():
    t = candidate()
    for i in range(3):
        t.events.append(
            MarketEvent(
                mint=t.mint,
                ts=NOW - 3 + i,
                source="Solana WSS",
                kind="trade",
                event_id=f"strength:{i}",
                side="buy",
                wallet=f"breadth-{i}",
                volume=3 + i / 7,
                currency="SOL",
            )
        )
    prepare(t)
    r = view(t)
    assert r["classification"] == "BULLISH DEVELOPING" and r["speculative_review"]
    assert r["supporting_timeframe"] == "10s + 30s + 60s"
    assert r["windows"]["10"]["arrival_acceleration"] >= 0
    assert r["active_buying"] and not t.features["180"]["continuity_valid"]
