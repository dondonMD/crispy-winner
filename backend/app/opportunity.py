"""Pure unvalidated attention ranking. Never supplies core entry or paper evidence."""

from enum import StrEnum
import hashlib
import json
import math
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
import yaml

from backend.app.config import ROOT, Settings
from backend.app.domain import Token, State


class IntelligenceSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    curve_fresh_seconds: float = Field(default=180, ge=30, le=600)
    manual_fresh_seconds: float = Field(default=120, ge=15, le=300)
    progression_min_pp: float = Field(default=4, ge=1, le=20)
    progression_min_seconds: float = Field(default=60, ge=30, le=300)
    pullback_min_pp: float = Field(default=4, ge=2, le=15)
    collapse_pp: float = Field(default=25, ge=15, le=50)
    profit_retreat_pct: float = Field(default=8, ge=3, le=30)
    exit_drawdown_pct: float = Field(default=20, ge=10, le=50)
    profit_buffer_pct: float = Field(default=3, ge=1, le=20)
    liquidity_retention_fraction: float = Field(default=0.5, gt=0, lt=1)
    manual_max_open: int = Field(default=3, ge=1, le=10)
    horizons: list[int] = Field(default=[60, 180, 300, 600, 1800], min_length=1, max_length=5)

    @field_validator("horizons")
    @classmethod
    def valid_horizons(cls, values):
        if values != sorted(set(values)) or any(not 15 <= value <= 86400 for value in values):
            raise ValueError("Research horizons must be unique, increasing and between 15s and 1 day")
        return values

    @model_validator(mode="after")
    def ordered_risk(self):
        if self.pullback_min_pp >= self.collapse_pp or self.profit_retreat_pct >= self.exit_drawdown_pct:
            raise ValueError("Research caution thresholds must precede invalidation/risk thresholds")
        return self

    @property
    def version(self):
        return (
            "opportunity-v1-"
            + hashlib.sha256(json.dumps(self.model_dump(), sort_keys=True).encode()).hexdigest()[:12]
        )


def load_intelligence_settings(path: Path | None = None):
    path = path or ROOT / "config/intelligence.yaml"
    return (
        IntelligenceSettings(**(yaml.safe_load(path.read_text()) or {}))
        if path.exists()
        else IntelligenceSettings()
    )


class OpportunityAction(StrEnum):
    EARLY_OPPORTUNITY = "EARLY_OPPORTUNITY"
    DEVELOPING = "DEVELOPING"
    PULLBACK_WATCH = "PULLBACK_WATCH"
    TOO_EXTENDED = "TOO_EXTENDED"
    AVOID = "AVOID"
    DATA_LIMITED = "DATA_LIMITED"


class CurveDynamics(BaseModel):
    current: float | None = None
    peak: float | None = None
    retreat_pp: float | None = None
    short_velocity_pp_min: float | None = None
    medium_velocity_pp_min: float | None = None
    acceleration_pp_min2: float | None = None
    persistence: float | None = None
    samples: int = 0
    coverage_seconds: float = 0
    region_seconds: float | None = None
    net_progress_pp: float | None = None
    prior_progress_pp: float | None = None
    quality: str = "UNAVAILABLE"
    freshness: str = "UNKNOWN"


class OpportunityResult(BaseModel):
    action: OpportunityAction
    attention: str
    ranking_score: float
    score_components: dict[str, float]
    evidence_grade: str
    headline: str
    summary: str
    why_now: list[str]
    blockers: list[str]
    warnings: list[str]
    missing_evidence: list[str]
    lifecycle: str
    dynamics: CurveDynamics
    security_quality: str
    trade_evidence: str
    market_context: dict
    entry_context: dict
    invalidation_conditions: list[str]
    manual_execution_only: bool = True
    validated_edge: bool = False
    research_version: str


def current(stamp, now, ttl):
    return stamp > 0 and 0 <= now - stamp <= ttl


def curve_dynamics(token: Token, now: float, cfg: IntelligenceSettings) -> CurveDynamics:
    points = [(ts, value) for ts, value in token.curve_history if 0 <= now - ts <= 1800]
    fresh = (
        bool(points)
        and current(points[-1][0], now, cfg.curve_fresh_seconds)
        and token.curve_progress == points[-1][1]
        and token.last_curve == points[-1][0]
    )
    result = CurveDynamics(
        peak=token.curve_peak_progress,
        samples=len(points),
        freshness="CURRENT" if fresh else "STALE" if points else "UNKNOWN",
    )
    if not fresh:
        return result
    result.current = points[-1][1]
    result.retreat_pp = max(0, (result.peak or result.current) - result.current)
    result.coverage_seconds = points[-1][0] - points[0][0]
    result.net_progress_pp = points[-1][1] - points[0][1]
    low, rise = points[0][1], 0.0
    for _, value in points:
        rise = max(rise, value - low)
        low = min(low, value)
    result.prior_progress_pp = rise

    def velocity(window):
        selected = [(ts, p) for ts, p in points if points[-1][0] - ts <= window]
        if len(selected) < 2 or selected[-1][0] - selected[0][0] < 30:
            return None
        return 60 * (selected[-1][1] - selected[0][1]) / (selected[-1][0] - selected[0][0])

    result.short_velocity_pp_min = velocity(120)
    result.medium_velocity_pp_min = velocity(600)
    changes = [(b[1] - a[1], b[0] - a[0]) for a, b in zip(points, points[1:]) if b[0] - a[0] >= 15]
    if changes:
        result.persistence = sum(delta > 0 for delta, _ in changes) / len(changes)
    if len(points) >= 3 and all(points[i + 1][0] - points[i][0] >= 15 for i in [-3, -2]):
        a, b, c = points[-3:]
        if c[0] - a[0] >= 60:
            v1 = (b[1] - a[1]) * 60 / (b[0] - a[0])
            v2 = (c[1] - b[1]) * 60 / (c[0] - b[0])
            result.acceleration_pp_min2 = (v2 - v1) * 120 / (c[0] - a[0])

    def region(p):
        return 0 if p < 30 else 1 if p < 85 else 2

    start = points[-1][0]
    for ts, value in reversed(points):
        if region(value) != region(result.current):
            break
        start = ts
    result.region_seconds = points[-1][0] - start
    result.quality = (
        "REGRESSING"
        if len(points) >= 2 and points[-1][1] < points[-2][1]
        else "INCREASING"
        if (result.medium_velocity_pp_min or 0) > 0
        else "STABLE"
        if result.medium_velocity_pp_min is not None
        else "INSUFFICIENT HISTORY"
    )
    return result


def provider_market(token, settings, now):
    # Launch metadata and reserve-based guesses are deliberately excluded.
    price_ok = token.market_source == "DEX Screener" and current(
        token.last_price, now, settings.max_data_age_seconds
    )
    cap_ok = token.cap_source == "DEX Screener" and current(
        token.last_market_cap, now, settings.max_data_age_seconds
    )
    return {
        "source": "PROVIDER: DEX Screener",
        "observed_at": token.last_price or None,
        "price_usd": token.price if price_ok else None,
        "market_cap_usd": token.market_cap if cap_ok else None,
        "status": "CURRENT" if price_ok or cap_ok else "UNAVAILABLE",
        "price_observed_at": token.last_price if price_ok else None,
        "cap_observed_at": token.last_market_cap if cap_ok else None,
    }


def opportunity_view(
    token: Token,
    settings: Settings,
    now: float,
    cfg: IntelligenceSettings | None = None,
    market: dict | None = None,
) -> OpportunityResult:
    cfg = cfg or IntelligenceSettings()
    d = curve_dynamics(token, now, cfg)
    sec = token.security
    security = (
        "CURRENT"
        if sec.get("data_quality") == "VERIFIED"
        and current(sec.get("last_updated", 0), now, settings.security_ttl_seconds)
        else "UNKNOWN / STALE"
    )
    features = token.features.get("180", {})
    trade = (
        settings.trade_stream_enabled
        and current(token.last_trade, now, settings.max_data_age_seconds)
        and features.get("units_valid") is True
        and all(
            isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and v >= 0
            for v in [features.get("flow_ratio"), features.get("estimated_independent_buyers")]
        )
    )
    missing = []
    if not trade:
        missing.append("TRADE FLOW UNAVAILABLE — buyer breadth and flow are unknown")
    if security != "CURRENT":
        missing.append("Current verified security unavailable")
    market = dict(market or provider_market(token, settings, now))
    if market.get("status") != "CURRENT":
        missing.append("Current market cap/price unavailable; copy mint and inspect your trading interface")
    if d.freshness != "CURRENT":
        missing.append("Current verified lifecycle observation unavailable")
    components = {
        "persistence": round(25 * (d.persistence or 0), 2),
        "progression": round(min(20, max(0, d.net_progress_pp or 0)), 2),
        "coverage": min(10, d.samples * 2),
        "freshness": 15 if d.freshness == "CURRENT" else 0,
        "controlled_retreat": max(0, 10 - (d.retreat_pp or 0)) if d.current is not None else 0,
        "security": 10 if security == "CURRENT" else 0,
        "trade_evidence": 5 if trade else 0,
        "market_evidence": 5 if market.get("status") == "CURRENT" else 0,
    }
    blockers = list(token.decision.get("reasons", []))
    why = []
    hard = (
        sec.get("hard_failures")
        or token.decision.get("decision") == "REJECT"
        or token.state in [State.REJECTED, State.EXPIRED]
        or token.disagreement
        or features.get("creator_sell_volume", 0) > 0
    )
    early = (
        d.freshness == "CURRENT"
        and d.samples >= 3
        and d.coverage_seconds >= cfg.progression_min_seconds
        and (d.net_progress_pp or 0) >= cfg.progression_min_pp
        and (d.persistence or 0) >= 0.75
        and d.quality == "INCREASING"
        and (d.retreat_pp or 0) <= 3
        and (security == "CURRENT" or (d.samples >= 4 and d.coverage_seconds >= 120))
    )
    if hard:
        action = OpportunityAction.AVOID
        blockers += list(sec.get("hard_failures", [])) + (
            ["Provider disagreement"] if token.disagreement else []
        )
    elif token.decision.get("decision") == "MISSED":
        action = OpportunityAction.TOO_EXTENDED
    elif d.freshness != "CURRENT":
        action = OpportunityAction.DATA_LIMITED
    elif (
        (d.retreat_pp or 0) >= cfg.pullback_min_pp
        and (d.retreat_pp or 0) < cfg.collapse_pp
        and d.samples >= 3
        and (d.prior_progress_pp or 0) >= cfg.progression_min_pp
    ):
        action = OpportunityAction.PULLBACK_WATCH
        why.append("Verified retreat from session peak; watch for renewed progression")
    elif (d.retreat_pp or 0) >= cfg.collapse_pp:
        action = OpportunityAction.DATA_LIMITED
        blockers.append("Severe verified curve regression; progression thesis is not intact")
    elif early:
        action = OpportunityAction.EARLY_OPPORTUNITY
        why.append("Persistent verified progression across multiple timed observations")
    else:
        action = OpportunityAction.DEVELOPING
        blockers.append(
            "More sustained progression or independent security evidence needed for high attention"
        )
    if d.medium_velocity_pp_min is not None:
        why.append(
            f"{d.net_progress_pp:+.1f}pp across {d.coverage_seconds:.0f}s; {d.medium_velocity_pp_min:+.2f}pp/min medium velocity"
        )
    grade = (
        "STALE"
        if d.freshness == "STALE"
        else "LIMITED — LIFECYCLE UNKNOWN"
        if d.freshness == "UNKNOWN"
        else "FULLER EVIDENCE"
        if trade and security == "CURRENT" and market.get("status") == "CURRENT"
        else "LIMITED — "
        + ", ".join(
            (["NO TRADE FLOW"] if not trade else [])
            + (["SECURITY UNKNOWN"] if security != "CURRENT" else [])
            + (["MARKET UNKNOWN"] if market.get("status") != "CURRENT" else [])
        )
    )
    score = (
        round(sum(components.values()), 2)
        if action not in [OpportunityAction.AVOID, OpportunityAction.DATA_LIMITED]
        else 0
    )
    return OpportunityResult(
        action=action,
        attention="HIGH"
        if action == OpportunityAction.EARLY_OPPORTUNITY
        else "MEDIUM"
        if score >= 30
        else "LOW",
        ranking_score=score,
        score_components=components,
        evidence_grade=grade,
        headline=action.value.replace("_", " "),
        summary="Unvalidated manual research attention; never a validated buy or a promise of profit.",
        why_now=why,
        blockers=list(dict.fromkeys(blockers)),
        warnings=[
            "Uncalibrated ranking signal — not a probability of profit.",
            "Curve progression is not price growth.",
        ],
        missing_evidence=missing,
        lifecycle=token.state.value,
        dynamics=d,
        security_quality=security,
        trade_evidence="CURRENT" if trade else "UNAVAILABLE",
        market_context=market,
        entry_context={
            "review_zone": None,
            "maximum_chase": None,
            "status": "UNAVAILABLE",
            "reason": "Insufficient current market/target evidence; no calibrated exit target",
        },
        invalidation_conditions=[
            "Hard security failure or observed creator selling",
            "Material provider disagreement",
            f"Verified curve retreat of {cfg.collapse_pp:g}pp",
            "Loss of current lifecycle/security/market evidence",
        ],
        research_version=cfg.version,
    )
