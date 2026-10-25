"""Isolated synthetic UI examples, never engine tokens, research, approved evidence or paper."""

from copy import deepcopy

from backend.app.domain import State, Token, MarketEvent
from backend.app.features import calculate_features
from backend.app.opportunity import opportunity_view, early_market_view, curve_dynamics
from backend.app.exit_intelligence import exit_view


def examples(settings, cfg, now):
    if settings.mode != "DEMO":
        return {"opportunities": [], "positions": []}
    tokens, opportunities = [], []
    for i, (label, values) in enumerate(
        [
            ("EARLY OPPORTUNITY", [30, 36, 42, 48]),
            ("DEVELOPING", [20, 21]),
            ("PULLBACK WATCH", [40, 55, 65, 59]),
            ("TOO EXTENDED", [40, 48, 56, 64]),
            ("AVOID", [20, 30, 40, 50]),
        ]
    ):
        t = Token(f"DEMO-OPPORTUNITY-{i}", "SYNTHETIC " + label, "DEMO", now - 240)
        t.state = State.MATURING
        for index, value in enumerate(values):
            t.curve_history.append((now - (len(values) - 1 - index) * 60, value))
        t.curve_progress = values[-1]
        t.curve_peak_progress = max(values)
        t.last_curve = now
        t.security = {
            "data_quality": "VERIFIED",
            "last_updated": now,
            "hard_failures": [],
            "warnings": ["DEMO ONLY"],
        }
        t.features = {"180": {"units_valid": True, "estimated_independent_buyers": 30, "flow_ratio": 2}}
        t.last_trade = now
        if label == "TOO EXTENDED":
            t.decision = {"decision": "MISSED", "reasons": ["SYNTHETIC observed price extension / chase"]}
        if label == "AVOID":
            t.security["hard_failures"] = ["SYNTHETIC hard security failure"]
        tokens.append(t)
        result = opportunity_view(
            t, settings.model_copy(update={"trade_stream_enabled": True}), now, cfg
        ).model_dump(mode="json")
        # Independent synthetic observations for the new display; original demo
        # tokens/exit rules/research classifications remain unchanged.
        early = deepcopy(t)
        early.trade_tracking_since = now - 65
        early.last_analysis = now
        for j in range(1, 60, 3):
            early.events.append(MarketEvent(mint=early.mint, ts=now-j, kind="trade", source="DEMO",
                event_id=f"demo-early:{i}:{j}", side="sell" if label == "DEVELOPING" else "buy",
                wallet=f"demo-buyer-{j}", volume=1+j/13, currency="SOL"))
        early.last_trade = now-1
        early.features = calculate_features(early, now)
        result["early_market"] = early_market_view(early, settings, cfg, now,
            curve_dynamics(early, now, cfg), 65, {s: False for s in (10, 30, 60, 180)})
        opportunities.append({"mint": t.mint, "name": t.name, "symbol": "DEMO", "simulated": True, **result})
    positions = []
    for label, mark_value, peak in [
        ("HEALTHY", 1.1, 1.1),
        ("PROTECT_PROFIT", 1.5, 1.7),
        ("EXIT_RISK", 0.7, 1.2),
        ("THESIS_INVALIDATED", 1.0, 1.0),
    ]:
        token = deepcopy(tokens[0])
        token.name = "SYNTHETIC " + label
        token.liquidity = 50000
        token.last_liquidity = now
        if label == "THESIS_INVALIDATED":
            token.security["hard_failures"] = ["SYNTHETIC hard failure after entry"]
        projection = opportunity_view(
            token, settings.model_copy(update={"trade_stream_enabled": True}), now, cfg
        )
        key = "MANUAL USER OBSERVATION:price_usd"
        position = {
            "position_id": "DEMO-" + label,
            "mint": token.mint,
            "name": token.name,
            "status": "OPEN",
            "amount_usd": 4,
            "opened_at": now - 120,
            "entry_price_usd": 1,
            "entry_market_cap_usd": None,
            "thesis": {"dynamics": {"current": 42}, "action": "EARLY_OPPORTUNITY"},
            "marks": {
                key: {
                    "value": mark_value,
                    "metric": "price_usd",
                    "source": "MANUAL USER OBSERVATION",
                    "observed_at": now,
                }
            },
            "peaks": {key: peak},
            "simulated": True,
        }
        result = exit_view(position, token, projection, settings, cfg, now)
        positions.append({**position, "exit": result.model_dump(mode="json")})
    return {
        "opportunities": opportunities,
        "positions": positions,
        "label": "DEMO ONLY — SYNTHETIC WORKFLOW EXAMPLES",
    }
