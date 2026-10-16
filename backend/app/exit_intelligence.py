"""Explainable, unvalidated exit context for manually journalled positions only."""

from enum import StrEnum
import math
from pydantic import BaseModel

from backend.app.economics import TradeCostEstimator
from backend.app.opportunity import current


class ExitAction(StrEnum):
    MONITOR = "MONITOR"
    HEALTHY = "HEALTHY"
    PROTECT_PROFIT = "PROTECT_PROFIT"
    MOMENTUM_DETERIORATING = "MOMENTUM_DETERIORATING"
    EXIT_RISK = "EXIT_RISK"
    THESIS_INVALIDATED = "THESIS_INVALIDATED"
    DATA_STALE = "DATA_STALE"


class ExitResult(BaseModel):
    action: ExitAction
    reasons: list[str]
    warnings: list[str]
    mark: dict | None
    peak_mark: float | None
    gross_change_pct: float | None
    market_cap_change_pct: float | None
    estimated_net_pnl_usd: float | None
    estimated_net_return_pct: float | None
    drawdown_pct: float | None
    cost_estimate: dict | None
    thesis_invalidated: bool
    manual_execution_only: bool = True
    validated_edge: bool = False


def exit_view(position, token, opportunity, settings, cfg, now):
    usable = []
    for key, mark in position["marks"].items():
        ttl = (
            cfg.manual_fresh_seconds
            if mark["source"] == "MANUAL USER OBSERVATION"
            else settings.max_data_age_seconds
        )
        if current(mark["observed_at"], now, ttl):
            usable.append((key, mark))
    # Never mix cap and price or manual/provider peaks; prefer a current price to a cap proxy.
    usable.sort(key=lambda pair: (pair[1]["metric"] == "price_usd", pair[1]["observed_at"]), reverse=True)
    selected = usable[0] if usable else None
    key, mark = selected if selected else (None, None)
    peak = position["peaks"].get(key) if key else None
    entry = (
        position["entry_price_usd"]
        if mark and mark["metric"] == "price_usd"
        else position["entry_market_cap_usd"]
    )
    move = (mark["value"] / entry - 1) * 100 if mark and entry else None
    if move is not None and not math.isfinite(move):
        move = None
    drawdown = max(0, (1 - mark["value"] / peak) * 100) if mark and peak else None
    price_move = move if mark and mark["metric"] == "price_usd" else None
    cap_move = move if mark and mark["metric"] == "market_cap_usd" else None
    liquidity = (
        token.liquidity
        if token and current(token.last_liquidity, now, settings.max_data_age_seconds)
        else None
    )
    costs = (
        TradeCostEstimator(settings).estimate(position["amount_usd"], liquidity, price_move)
        if price_move is not None and price_move > -100
        else None
    )
    reasons, invalid = [], []
    if token:
        invalid += list(token.security.get("hard_failures", []))
        if token.features.get("180", {}).get("creator_sell_volume", 0) > 0:
            invalid.append("Observed creator selling invalidates the recorded thesis")
        if token.disagreement:
            invalid.append("Material provider disagreement")
        original_curve = position["thesis"].get("dynamics", {}).get("current")
        if (
            original_curve is not None
            and opportunity.dynamics.current is not None
            and original_curve - opportunity.dynamics.current >= cfg.collapse_pp
        ):
            invalid.append("Severe verified curve regression from the entry thesis")
    deterioration = opportunity.dynamics.quality == "REGRESSING"
    original_liquidity = position["thesis"].get("entry_liquidity_usd")
    liquidity_deteriorated = (
        liquidity is not None
        and original_liquidity is not None
        and liquidity <= original_liquidity * cfg.liquidity_retention_fraction
    )
    if invalid:
        action = ExitAction.THESIS_INVALIDATED
        reasons = invalid
    elif (
        not mark
        or (opportunity.dynamics.freshness != "CURRENT" and not (token and token.graduation is not None))
        or opportunity.security_quality != "CURRENT"
    ):
        action = ExitAction.DATA_STALE
        reasons = [
            "Important mark, lifecycle or security evidence is unavailable/stale; no reassurance is possible"
        ]
    elif (
        (drawdown or 0) >= cfg.exit_drawdown_pct
        or (move or 0) <= -cfg.exit_drawdown_pct
        or liquidity_deteriorated
        or (liquidity is not None and liquidity < settings.min_liquidity_usd)
    ):
        action = ExitAction.EXIT_RISK
        reasons = ["Observed peak drawdown or current liquidity exceeds the configured risk boundary"]
    elif (
        costs
        and costs["net_return_pct"] >= cfg.profit_buffer_pct
        and (deterioration or (drawdown or 0) >= cfg.profit_retreat_pct)
    ):
        action = ExitAction.PROTECT_PROFIT
        reasons = [
            "Estimated profit after costs is positive with a buffer, while progression/peak retention deteriorates"
        ]
    elif deterioration:
        action = ExitAction.MOMENTUM_DETERIORATING
        reasons = [
            "Verified lifecycle progression is regressing; unavailable trade flow is not bearish zero flow"
        ]
    elif opportunity.trade_evidence == "CURRENT":
        action = ExitAction.HEALTHY
        reasons = [
            "Available current mark, lifecycle, security and trade evidence show no configured deterioration"
        ]
    else:
        action = ExitAction.MONITOR
        reasons = ["Current partial evidence only; trade flow remains unavailable"]
    return ExitResult(
        action=action,
        reasons=reasons,
        warnings=[
            "Unvalidated decision support; closing the journal sends no transaction.",
            "Market-cap change is a proxy, not token return or P&L.",
            "Costs use a current balanced-pool approximation, not an execution quote.",
        ],
        mark=mark,
        peak_mark=peak,
        gross_change_pct=price_move,
        market_cap_change_pct=cap_move,
        estimated_net_pnl_usd=costs["net_pnl_usd"] if costs else None,
        estimated_net_return_pct=costs["net_return_pct"] if costs else None,
        drawdown_pct=drawdown,
        cost_estimate=costs,
        thesis_invalidated=bool(invalid),
    )
