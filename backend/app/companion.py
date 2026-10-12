"""Pure manual decision support. Acquisition and strategy remain engine-owned."""

from enum import StrEnum
import math
from pydantic import BaseModel
from backend.app.config import Settings
from backend.app.domain import State, Token
from backend.app.economics import evaluate_candidate


class Action(StrEnum):
    ENTRY_CANDIDATE = "ENTRY_CANDIDATE"
    WAIT = "WAIT"
    REJECT = "REJECT"
    TOO_LATE = "TOO_LATE"


class Attention(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class CompanionResult(BaseModel):
    action: Action
    core_decision: str
    attention: Attention
    headline: str
    summary: str
    positive_evidence: list[str]
    blockers: list[str]
    missing_evidence: list[str]
    warnings: list[str]
    manual_position_cap_usd: float | None
    economically_viable: bool
    lifecycle: str
    curve_progress: float | None
    curve_peak_progress: float | None
    curve_quality: str
    trade_evidence: str
    security_quality: str
    security_risk_score: float | None
    data_freshness: str
    chase_risk: float | None
    evidence_quality: dict[str, str]
    invalidation_conditions: list[str]
    manual_execution_only: bool = True


def companion_view(
    token: Token,
    settings: Settings,
    now: float,
    *,
    evidence: dict | None = None,
    healthy: bool = True,
    resource_pressure: bool = False,
) -> CompanionResult:
    """Never upgrade a core decision. Reuse its evaluator to defend old entry snapshots."""
    core = token.decision.get("decision", "WAIT")
    checked = (
        evaluate_candidate(token, settings, now, healthy, resource_pressure, evidence)
        if core == "ALLOW_PAPER_ENTRY"
        else token.decision
    )
    action = {"REJECT": Action.REJECT, "MISSED": Action.TOO_LATE}.get(core, Action.WAIT)
    blockers = list(token.decision.get("reasons", []))
    security = token.security
    quality = security.get("data_quality", "UNKNOWN")
    security_current = (
        quality in ("VERIFIED", "SIMULATED")
        and (quality != "SIMULATED" or settings.mode == "DEMO")
        and 0 <= now - security.get("last_updated", 0) <= settings.security_ttl_seconds
    )
    security_quality = quality if security_current or quality == "UNKNOWN" else "STALE"
    trade_current = (settings.mode == "DEMO" or settings.trade_stream_enabled) and (
        token.last_trade > 0 and 0 <= now - token.last_trade <= settings.max_data_age_seconds
    )
    market_current = all(
        isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0
        for value in (token.price, token.liquidity)
    ) and all(
        stamp > 0 and 0 <= now - stamp <= settings.max_data_age_seconds
        for stamp in (token.last_price, token.last_liquidity)
    )
    history_current = bool(
        evidence
        and evidence.get("count", 0) >= settings.min_holdout_samples
        and evidence.get("lower_ci", 0) > 0
    )
    position = token.viability.get("position_size_usd")
    viable = token.viability.get("economically_viable") is True
    position_valid = (
        isinstance(position, (int, float))
        and not isinstance(position, bool)
        and math.isfinite(position)
        and position > 0
    )
    curve_current = token.curve_progress is not None and (
        settings.mode == "DEMO"
        or (token.last_curve > 0 and 0 <= now - token.last_curve <= settings.curve_poll_seconds * 2)
    )
    curve_quality = "CURRENT" if curve_current else "UNKNOWN" if token.curve_progress is None else "STALE"
    missing = []
    for present, reason in [
        (security_current, "Need current verified security evidence"),
        (trade_current, "Need observed trade/buyer evidence"),
        (token.graduation is not None, "Need migration confirmation"),
        (market_current, "Need current liquidity and exit-price evidence"),
        (history_current, "Need sufficient approved historical after-cost evidence"),
        (viable and position_valid, "Need an economically viable after-cost setup"),
    ]:
        if not present:
            missing.append(reason)
    if core == "ALLOW_PAPER_ENTRY":
        blockers = list(checked["reasons"])
        if checked["decision"] == "REJECT" or security.get("hard_failures"):
            action = Action.REJECT
        elif checked["decision"] == "MISSED":
            action = Action.TOO_LATE
        elif checked["decision"] == "ALLOW_PAPER_ENTRY" and not missing:
            action = Action.ENTRY_CANDIDATE
        else:
            action = Action.WAIT
    elif security.get("hard_failures"):
        action = Action.REJECT
        blockers.extend(security["hard_failures"])
    if action != Action.ENTRY_CANDIDATE:
        blockers = list(dict.fromkeys(blockers + missing))
    attention = Attention.LOW
    if action == Action.ENTRY_CANDIDATE or (
        action == Action.WAIT
        and (
            (token.state == State.NEAR_GRADUATION and curve_current)
            or (token.state == State.POST_GRAD_OBSERVATION and market_current)
        )
    ):
        attention = Attention.HIGH
    elif action == Action.WAIT and token.state == State.MATURING:
        attention = Attention.MEDIUM
    positives = list(token.decision.get("positive_evidence", []))
    if curve_current:
        positives.append(
            "Current verified lifecycle progress"
            if settings.mode != "DEMO"
            else "SIMULATED lifecycle progress"
        )
    if security_current:
        positives.append("Current security evidence; security is not a safety guarantee")
    summaries = {
        Action.ENTRY_CANDIDATE: "The configured strategy and economic gates currently permit manual review.",
        Action.WAIT: "Monitored; required conditions or evidence are missing.",
        Action.REJECT: "The core risk gates reject this token.",
        Action.TOO_LATE: "Do not chase this move based on the current evidence.",
    }
    return CompanionResult(
        action=action,
        core_decision=core,
        attention=attention,
        headline=action.value.replace("_", " "),
        summary=summaries[action],
        positive_evidence=list(dict.fromkeys(positives)),
        blockers=blockers,
        missing_evidence=missing,
        warnings=list(security.get("warnings", [])),
        manual_position_cap_usd=position if action == Action.ENTRY_CANDIDATE else None,
        economically_viable=viable,
        lifecycle=token.state.value,
        curve_progress=token.curve_progress,
        curve_peak_progress=token.curve_peak_progress,
        curve_quality=curve_quality,
        trade_evidence="CURRENT"
        if trade_current
        else "UNAVAILABLE"
        if not (settings.mode == "DEMO" or settings.trade_stream_enabled)
        else "STALE / UNKNOWN",
        security_quality=security_quality,
        security_risk_score=security.get("risk_score") if security_current else None,
        data_freshness="CURRENT"
        if market_current and security_current and trade_current and healthy and not token.degraded
        else "INCOMPLETE / STALE",
        chase_risk=token.scores.get("chase"),
        evidence_quality={
            "Lifecycle": "MIGRATION CONFIRMED" if token.graduation is not None else curve_quality,
            "Security": security_quality,
            "Trade flow": "CURRENT" if trade_current else "UNAVAILABLE",
            "Liquidity / exit": "CURRENT" if market_current else "UNKNOWN / STALE",
            "Historical edge": "APPROVED" if history_current else "INSUFFICIENT DATA",
            "Post-grad recovery": "CORE GATES PASS"
            if action == Action.ENTRY_CANDIDATE
            else "NOT CONFIRMED"
            if token.graduation is None
            else "UNDER OBSERVATION",
        },
        invalidation_conditions=[
            "Core decision remains ALLOW_PAPER_ENTRY",
            "Required evidence remains current",
            "Security remains acceptable",
            "Economics remain viable",
            "Chase risk remains inside the configured limit",
            "Liquidity remains sufficient",
            "Trade evidence remains acceptable",
        ]
        if action == Action.ENTRY_CANDIDATE
        else [],
    )
