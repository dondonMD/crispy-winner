"""Deterministic simulated scenarios; never imported by a real-data provider."""

import random
from backend.app.domain import MarketEvent

SCENARIOS = [
    "healthy maturing",
    "dead launch",
    "whale momentum",
    "creator dump",
    "possible sybil",
    "pump collapse",
    "near graduation failure",
    "graduation dump",
    "consolidation",
    "healthy recovery",
    "distributed buying",
    "liquidity deterioration",
]


def demo_events(start, tick, seed=47, namespace=""):
    rng = random.Random(seed + tick)
    events = []
    for i, scenario in enumerate(SCENARIOS):
        mint = f"DEMO{i:02d}{namespace}simulated"
        ts = start + tick
        if tick == 0:
            events.append(
                MarketEvent(
                    mint=mint,
                    ts=ts,
                    source="DEMO",
                    kind="create",
                    event_id=f"{mint}-create",
                    name=scenario.title(),
                    symbol=f"SIM{i}",
                    creator=f"creator{i}",
                )
            )
            events.append(
                MarketEvent(
                    mint=mint,
                    ts=ts,
                    source="DEMO",
                    kind="security",
                    event_id=f"{mint}-security",
                    evidence={
                        "data_quality": "SIMULATED",
                        "risk_score": 10,
                        "hard_failures": [],
                        "warnings": ["SIMULATED SECURITY"],
                        "top_1_independent_pct": 4,
                        "top_5_independent_pct": 15,
                        "creator_pct": 2,
                        "last_updated": ts,
                        "token_program": "SIMULATED",
                    },
                )
            )
        if i == 1 or (i == 6 and tick > 60):
            continue
        if tick == 90 and i >= 7:
            events.append(
                MarketEvent(
                    mint=mint,
                    ts=ts,
                    source="DEMO",
                    kind="migration",
                    event_id=f"{mint}-graduation",
                    signature=f"SIM-GRAD-{i}",
                )
            )
        if i == 5:
            price = 0.001 * (1 + tick * 0.045) if tick < 40 else 0.0028 * max(0.05, 1 - (tick - 40) * 0.025)
        elif i >= 7 and tick >= 90:
            x = tick - 90
            price = 0.0019 * (1 - min(x, 20) * 0.012 + max(0, x - 40) * (0.003 if i in [9, 10] else 0.0002))
            if i == 7:
                price *= max(0.1, 1 - x * 0.008)
        else:
            price = 0.001 * (1 + tick * 0.0025)
        price *= 1 + rng.uniform(-0.003, 0.003)
        for j in range(2 if i in [0, 9, 10] else 1):
            wallet = f"wallet{i}-{(tick * 2 + j) % 100}"
            if i == 2:
                wallet = f"whale-{tick % 2}"
            if i == 3 and tick > 25:
                wallet = f"creator{i}"
            if i == 4:
                wallet = f"cluster{tick}-{j}"
            side = "sell" if (i == 3 and tick > 25) or (i == 7 and tick > 90) or rng.random() < 0.2 else "buy"
            amount = 5 if i == 4 else rng.uniform(1, 15)
            events.append(
                MarketEvent(
                    mint=mint,
                    ts=ts + j * 0.01,
                    source="DEMO",
                    kind="trade",
                    event_id=f"{mint}-{tick}-{j}",
                    wallet=wallet,
                    side=side,
                    volume=amount,
                    currency="USD",
                    price=price,
                    market_cap=price * 1e9,
                    liquidity=max(30, 15000 - tick * 100) if i == 11 else 25000,
                    curve_progress=min(98, tick * 1.0) if i < 7 else None,
                )
            )
    return events


def companion_examples(settings, now):
    """Isolated UI fixtures: never admitted to scanner, collector or paper account."""
    from backend.app.companion import companion_view
    from backend.app.domain import Token, State
    from backend.app.economics import PositionSizer, TradeCostEstimator, evaluate_candidate

    if settings.mode != "DEMO":
        return []
    evidence = {
        "count": settings.min_holdout_samples + 100,
        "lower_ci": 2,
        "expectancy_net_pct": 5,
        "status": "SIMULATED UI FIXTURE",
    }
    result = []
    for label in ["Entry", "Wait", "Reject", "Too late"]:
        t = Token(
            f"DEMO-COMPANION-{label.replace(' ', '-')}",
            f"SIMULATED {label}",
            "DEMO",
            now - 600,
            "SIMULATED creator",
        )
        t.state = State.POST_GRAD_OBSERVATION
        t.security = {
            "data_quality": "SIMULATED",
            "risk_score": 10,
            "hard_failures": [],
            "warnings": ["SIMULATED UI fixture; not research evidence"],
            "top_1_independent_pct": 4,
            "top_5_independent_pct": 15,
            "creator_pct": 2,
            "last_updated": now,
        }
        t.graduation = now - settings.post_grad_wait_seconds - 60
        t.grad_high, t.grad_low, t.price, t.liquidity = 1.2, 1, 1.05, 25000
        t.last_price = t.last_trade = t.last_liquidity = t.last_curve = now
        t.curve_progress, t.curve_peak_progress = 87, 89
        t.features = {
            "180": {
                "creator_sell_volume": 0,
                "estimated_independent_buyers": settings.min_buyers + 10,
                "units_valid": True,
                "buy_pressure_persistence": 0.8,
                "whale_share": 0.1,
            }
        }
        t.scores = {
            "maturity": max(80, settings.min_maturity),
            "momentum": max(85, settings.min_momentum),
            "chase": 0,
        }
        t.viability = PositionSizer(settings, TradeCostEstimator(settings)).size(20, t.liquidity, 5, 1)
        if label == "Entry":
            t.features["180"].update(
                buy_volume=24.0,
                sell_volume=8.0,
                flow_ratio=3.0,
                net_flow=16.0,
                flow_balance=0.5,
                currency="SOL",
            )
        if label == "Wait":
            t.last_trade = 0
            t.graduation = None
            t.state = State.NEAR_GRADUATION
        elif label == "Reject":
            t.security["hard_failures"] = ["SIMULATED active freeze authority"]
        elif label == "Too late":
            t.scores["chase"] = settings.max_chase
        t.decision = evaluate_candidate(t, settings, now, evidence=evidence)
        result.append(
            {
                "mint": t.mint,
                "name": t.name,
                "symbol": t.symbol,
                "state": t.state.value,
                "liquidity": t.liquidity,
                "viability": t.viability,
                "features": t.features["180"],
                "companion": companion_view(t, settings, now, evidence=evidence).model_dump(mode="json"),
            }
        )
    return result
