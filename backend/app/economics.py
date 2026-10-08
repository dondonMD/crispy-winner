import math
from backend.app.config import Settings


class TradeCostEstimator:
    """One authoritative conservative constant-product approximation.

    Liquidity USD/2 approximates quote reserve only for balanced pools.
    Unknown reserves never imply zero impact. Not a route-specific execution quote.
    """

    def __init__(self, settings: Settings):
        self.settings = settings

    def impact_fraction(self, notional, liquidity):
        if liquidity is None or liquidity <= 0 or notional <= 0:
            return None
        reserve = liquidity / 2
        return notional / (reserve + notional)

    def side(self, notional, liquidity):
        s = self.settings
        impact = self.impact_fraction(notional, liquidity)
        if impact is None:
            return None
        return {
            "platform_fee_usd": notional * s.platform_fee_pct / 100,
            "dex_fee_usd": notional * s.fee_pct_per_side / 100,
            "network_usd": s.network_usd_per_side,
            "priority_usd": s.priority_usd_per_side,
            "slippage_usd": notional * s.slippage_pct / 100,
            "price_impact_usd": notional * impact,
            "price_impact_pct": impact * 100,
        }

    def estimate(self, position, liquidity, gross_return_pct=0):
        if position <= 0 or gross_return_pct <= -100:
            return None
        entry = self.side(position, liquidity)
        exit_value = position * (1 + gross_return_pct / 100)
        exit_cost = self.side(exit_value, liquidity)
        if entry is None or exit_cost is None:
            return None

        def total(side):
            return sum(value for key, value in side.items() if key.endswith("_usd"))

        entry_usd = total(entry) + self.settings.failed_tx_reserve_usd / 2
        exit_usd = total(exit_cost) + self.settings.failed_tx_reserve_usd / 2
        cost = entry_usd + exit_usd
        gross = exit_value - position
        return {
            "position_usd": position,
            "entry": entry,
            "exit": exit_cost,
            "entry_cost_usd": entry_usd,
            "exit_cost_usd": exit_usd,
            "round_trip_cost_usd": cost,
            "round_trip_cost_pct": 100 * cost / position,
            "gross_pnl_usd": gross,
            "net_pnl_usd": gross - cost,
            "net_return_pct": 100 * (gross - cost) / position,
            "estimated_slippage_pct_per_side": self.settings.slippage_pct,
            "estimated_price_impact_pct": max(entry["price_impact_pct"], exit_cost["price_impact_pct"]),
            "fee_verified": self.settings.fee_verified,
            "method": "Conservative balanced constant-product pool approximation",
        }

    def break_even(self, position, liquidity):
        if self.estimate(position, liquidity) is None:
            return None
        low, high = 0.0, 1000.0
        for _ in range(45):
            mid = (low + high) / 2
            if self.estimate(position, liquidity, mid)["net_pnl_usd"] >= 0:
                high = mid
            else:
                low = mid
        return high

    def exitability(self, position, liquidity):
        scenarios = []
        for fraction in [0.25, 0.5, 1]:
            side = self.side(position * fraction, liquidity)
            scenarios.append(
                {
                    "fraction": fraction,
                    "impact_pct": side["price_impact_pct"] if side else None,
                    "net_proceeds_usd": position * fraction
                    - sum(v for k, v in side.items() if k.endswith("_usd"))
                    if side
                    else None,
                }
            )
        impact = self.impact_fraction(position, liquidity)
        return {
            "score": max(0, 100 - 10000 * impact) if impact is not None else 0,
            "scenarios": scenarios,
            "quality": "ESTIMATED" if impact is not None else "UNKNOWN",
        }


class PositionSizer:
    def __init__(self, settings, estimator):
        self.settings, self.estimator = settings, estimator

    def size(self, balance, liquidity, historical_edge_pct=None, volatility_pct=0):
        s = self.settings
        proposed = round(balance * s.max_position_fraction * min(1, 5 / max(5, volatility_pct)), 2)
        estimate = self.estimator.estimate(proposed, liquidity)
        break_even = self.estimator.break_even(proposed, liquidity)
        reasons = []
        if estimate is None:
            reasons.append("Unknown liquidity/exit costs")
        elif estimate["estimated_price_impact_pct"] > s.max_impact_pct:
            reasons.append("Excessive price impact")
        if historical_edge_pct is None:
            reasons.append("No validated out-of-sample after-cost edge")
        elif historical_edge_pct < s.min_edge_pct:
            reasons.append("Observed after-cost edge below required safety margin")
        scenarios = [self.estimator.estimate(proposed, liquidity, x) for x in [-20, -8, 0, 5, 10, 15, 30]]
        return {
            "account_usd": balance,
            "proposed_position_usd": proposed,
            "position_size_usd": 0 if reasons else proposed,
            "economically_viable": not reasons,
            "label": "NO ECONOMICALLY VIABLE TRADE" if reasons else "PAPER SIZE AVAILABLE",
            "reasons": reasons,
            "costs": estimate,
            "break_even_move_pct": break_even,
            "maximum_acceptable_entry": None,
            "maximum_entry_reason": "Requires calibrated target/exit estimate; no target is invented",
            "historical_net_expected_return_pct": historical_edge_pct,
            "risk_adjusted_expected_return_pct": historical_edge_pct / max(1, volatility_pct)
            if historical_edge_pct is not None
            else None,
            "scenarios": [
                dict(gross_return_pct=x, **r) for x, r in zip([-20, -8, 0, 5, 10, 15, 30], scenarios) if r
            ],
            "exitability": self.estimator.exitability(proposed, liquidity),
        }


def evaluate_candidate(token, settings, now, healthy=True, resource_pressure=False, evidence=None):
    hard = []
    waits = []
    security = token.security
    features = token.features.get("180", {})
    if security.get("hard_failures"):
        hard.extend(security["hard_failures"])
    if security.get("data_quality") not in ["VERIFIED", "SIMULATED"]:
        waits.append("Security/distribution unknown or incomplete")
    if now - security.get("last_updated", 0) > settings.security_ttl_seconds:
        waits.append("Security report stale")
    if security.get("creator_pct") is None or not token.creator:
        waits.append("Creator identity/holdings unavailable")
    if features.get("creator_sell_volume", 0) > 0:
        hard.append("Creator selling detected")
    for key, limit in [
        ("top_1_independent_pct", settings.max_top1_pct),
        ("top_5_independent_pct", settings.max_top5_pct),
    ]:
        pct = security.get(key)
        if pct is None:
            waits.append("Holder concentration unknown")
        elif pct > limit:
            hard.append(f"Unacceptable concentration: {key}")
    if token.state.value in ["DISCOVERED", "SCREENING", "REJECTED", "EXPIRED"]:
        waits.append("Token state not eligible")
    for timestamp, label in [
        (token.last_price, "price"),
        (token.last_trade, "buyer flow"),
        (token.last_liquidity, "liquidity"),
    ]:
        if not timestamp or not 0 <= now - timestamp <= settings.max_data_age_seconds:
            waits.append(f"Stale or missing {label}")
    if not healthy:
        waits.append("Provider unhealthy")
    if resource_pressure or token.degraded:
        waits.append("Resource pressure or dropped events degraded data")
    if settings.mode != "DEMO" and not security.get("verified_pools"):
        waits.append("Post-graduation pool not independently verified on-chain")
    if token.disagreement:
        waits.append("Major provider disagreement")
    if token.graduation is None:
        waits.append("No confirmed graduation")
    elif now - token.graduation < settings.post_grad_wait_seconds:
        waits.append("Post-graduation price discovery still in progress")
    if token.graduation and token.price:
        if not math.isfinite(token.grad_low) or token.grad_high <= 0:
            waits.append("Insufficient post-graduation structure")
        elif token.grad_low / token.grad_high > 0.98 or token.price / token.grad_low < 1.01:
            waits.append("Pullback/stabilisation/renewed buying not established")
    if features.get("estimated_independent_buyers", 0) < settings.min_buyers:
        waits.append("Insufficient independent buyer evidence")
    if not features.get("units_valid"):
        waits.append("Trade volume units unavailable/inconsistent")
    if token.scores.get("maturity", 0) < settings.min_maturity:
        waits.append("Maturity below threshold")
    if token.scores.get("momentum", 0) < settings.min_momentum:
        waits.append("Momentum quality below threshold")
    if token.liquidity is None or token.liquidity < settings.min_liquidity_usd:
        waits.append("Insufficient verified liquidity")
    viability = token.viability
    if not viability.get("economically_viable"):
        waits.extend(viability.get("reasons", ["TRADE NOT ECONOMICALLY VIABLE"]))
    costs = viability.get("costs")
    if not costs:
        waits.append("Costs/exitability unknown")
    elif (
        costs["estimated_price_impact_pct"] > settings.max_impact_pct
        or costs["estimated_slippage_pct_per_side"] > settings.max_slippage_pct
    ):
        hard.append("Unacceptable estimated execution cost")
    if (
        not evidence
        or evidence.get("count", 0) < settings.min_holdout_samples
        or evidence.get("lower_ci", -1) <= 0
    ):
        waits.append("Insufficient positive holdout evidence")
    chase = token.scores.get("chase", 0) >= settings.max_chase
    decision = "REJECT" if hard else ("MISSED" if chase else ("WAIT" if waits else "ALLOW_PAPER_ENTRY"))
    reasons = hard + (["MISSED — DO NOT CHASE"] if chase else []) + waits
    positives = []
    if features.get("estimated_independent_buyers", 0) >= settings.min_buyers:
        positives.append(f"{features['estimated_independent_buyers']} estimated independent buyers in 3m")
    if features.get("buy_pressure_persistence", 0) >= 0.5:
        positives.append("Buying persists across rolling time bins")
    if features.get("whale_share", 1) < 0.4:
        positives.append("Observed buying distributed across wallets")
    return {
        "decision": decision,
        "reasons": list(dict.fromkeys(reasons)),
        "positive_evidence": positives,
        "historical_evidence": evidence or {"count": 0, "status": "UNVALIDATED"},
        "research_eligible": not hard
        and not chase
        and not [
            r
            for r in waits
            if r
            not in ["No validated out-of-sample after-cost edge", "Insufficient positive holdout evidence"]
        ],
    }
