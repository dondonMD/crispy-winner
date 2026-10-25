"""Pure unvalidated attention ranking. Never supplies core entry or paper evidence."""

from enum import StrEnum
from functools import lru_cache
import hashlib
import json
import math
import inspect
from typing import Any
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


@lru_cache(maxsize=8)
def _parse_intelligence_settings(content):
    return IntelligenceSettings(**(yaml.safe_load(content) or {}))


def load_intelligence_settings(path: Path | None = None):
    path = path or ROOT / "config/intelligence.yaml"
    # Read every time so source/config drift is never hidden by a stat/TTL cache.
    # Copies prevent one caller from mutating another caller's frozen settings.
    content = path.read_text() if path.exists() else ""
    return _parse_intelligence_settings(content).model_copy(deep=True)


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
    observed_at: float | None = None
    curve_observed_at: float | None = None
    trade_observed_at: float | None = None
    security_observed_at: float | None = None
    trade_coverage_seconds: float | None = None
    early_market: dict | None = None
    entry_review_eligible: bool = False
    review_valid_until: float | None = None


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
        (settings.trade_stream_enabled or features.get("trade_evidence") == "CURRENT")
        and features.get("continuity_valid", True)
        and features.get("trade_evidence", "CURRENT") == "CURRENT"
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
    # Presentation only. Never changes the research action or strict approval.
    review = bool(action == OpportunityAction.EARLY_OPPORTUNITY and not hard and not token.degraded
                  and token.graduation is None and d.current is not None and d.current < 85
                  and token.state in (State.WATCHING, State.MATURING, State.NEAR_GRADUATION)
                  and security == "CURRENT" and trade and bool(token.creator)
                  and sec.get("creator_pct") is not None
                  and all(isinstance(sec.get(key), (int, float)) and not isinstance(sec.get(key), bool)
                          and math.isfinite(sec[key]) and 0 <= sec[key] <= limit
                          for key, limit in (("top_1_independent_pct", settings.max_top1_pct),
                                             ("top_5_independent_pct", settings.max_top5_pct))))
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
        observed_at=now,
        curve_observed_at=token.last_curve or None,
        trade_observed_at=token.last_trade or None,
        security_observed_at=sec.get("last_updated") or None,
        trade_coverage_seconds=features.get("coverage_seconds"),
        entry_review_eligible=review,
        review_valid_until=min(now + settings.max_data_age_seconds,
                              token.last_curve + cfg.curve_fresh_seconds,
                              token.last_trade + settings.max_data_age_seconds,
                              sec.get("last_updated", 0) + settings.security_ttl_seconds) if review else None,
    )


# Separate descriptive research policy. Does not change opportunity-v1 or entry gates.
EARLY_MARKET_POLICY: dict[str, Any] = dict(windows=[10, 30, 60, 180], min_samples=3, min_buyers=3,
                           persistence_fraction=0.5, semantics='counts_then_consistent_amounts',
                           revision='2.1', bullish_window_seconds=10, history_window_seconds=30)


def early_market_view(token, settings, cfg, now, dynamics, clean_seconds, pending):
    """Bounded read-only interpretation over existing caches and retained observations.

    Clean observed-window coverage never means CURRENT or executable. Amount-based estimates
    are reused only with identical timestamp membership to the cached calculation.
    Caller supplies as-of processed state; source time alone cannot reconstruct historical availability.
    """
    clean_seconds = min(max(0, clean_seconds), max(0, now - max(
        token.trade_tracking_since, token.trade_gap, token.postgrad_gap, token.buffer_loss_at or 0)))
    events = list(token.events)  # Existing <=500 bound, no additional retained history.
    # Snapshot canonical count fields once; reuse existing cached amount/cluster math.
    observed = [(e.ts, e.side, e.wallet, e.currency) for e in events
                if e.kind == 'trade' and 0 <= now-e.ts <= 180
                and (e.source == 'Solana WSS' or settings.mode == 'DEMO' and e.source == 'DEMO')]
    windows = {}
    cache = getattr(token, '_feature_window_cache', {}).get('windows', {})
    for seconds in EARLY_MARKET_POLICY['windows']:
        trades = [e for e in observed if now-e[0] <= seconds]
        f = token.features.get(str(seconds), {})
        cached_key = cache.get(seconds, {}).get('key')
        same = bool(cached_key and cached_key[0] == tuple(e[0] for e in trades))
        same = same and f.get('samples') == len(trades)
        currencies = {e[3] for e in trades}
        units = bool(trades) and len(currencies) == 1 and currencies <= {'SOL', 'USDC'}
        def metric(name):
            value = f.get(name)
            return value if (isinstance(value, (int, float)) and not isinstance(value, bool)
                             and math.isfinite(value)) else None
        buys = sum(e[1] == 'buy' for e in trades)
        ready = clean_seconds >= seconds and not pending.get(seconds, True)
        windows[str(seconds)] = dict(samples=len(trades), buys=buys, sells=len(trades)-buys,
            coverage_seconds=min(seconds, max(0, clean_seconds)), complete=ready,
            freshness='RECENT' if trades and current(max(e[0] for e in trades), now,
                                                    settings.max_data_age_seconds) else 'STALE / ABSENT',
            last_trade_age=now-max(e[0] for e in trades) if trades else None,
            first_trade_age=now-min(e[0] for e in trades) if trades else None,
            units_valid=units, currency=next(iter(currencies)) if units else None,
            raw_unique_buyers=(f['raw_unique_buyers'] if same else
                               len({e[2] for e in trades if e[1] == 'buy' and e[2]})),
            independent_buyers=metric('estimated_independent_buyers') if same and units else None,
            net_flow=metric('net_flow') if same and units else None,
            flow_ratio=metric('flow_ratio') if same and units else None,
            arrival_acceleration=metric('trade_acceleration') if same else None,
            buying_persistence=metric('buy_pressure_persistence') if same and units else None,
            whale_share=metric('whale_share') if same and units else None,
            coordination_suspected=bool(f.get('cluster_evidence')) if same and units else None,
            pending_recovery=pending.get(seconds, True),
            limitations=([f'Incomplete {seconds}s continuity; retained samples only'] if not ready else [])
                + ([] if units else ['Amount-weighted flow/coordination unavailable: unknown or mixed units'])
                + ([] if same else ['Cached amount/breadth metrics unavailable for this exact membership']))
    def supported(window):
        return (window['complete'] and window['samples'] >= EARLY_MARKET_POLICY['min_samples']
                and window['freshness'] == 'RECENT')
    latest = windows[str(EARLY_MARKET_POLICY['bullish_window_seconds'])]
    history = windows[str(EARLY_MARKET_POLICY['history_window_seconds'])]
    medium = windows['60']
    short = latest if supported(latest) else history if supported(history) else None
    active_buying = bool(supported(latest) and latest['buys'] > latest['sells']
                        and latest['raw_unique_buyers'] >= EARLY_MARKET_POLICY['min_buyers']
                        and (latest['net_flow'] is None or latest['net_flow'] > 0))
    active_selling = bool(supported(latest) and (latest['sells'] > latest['buys']
                         or latest['net_flow'] is not None and latest['net_flow'] < 0))
    positive_history = bool(supported(history) and history['buys'] > history['sells']
                           and (history['net_flow'] is None or history['net_flow'] > 0))
    activity = ('UNAVAILABLE' if not latest['complete'] else 'QUIET' if not latest['samples'] else
                'SELL DOMINANT' if active_selling else 'ACTIVE BUYING' if active_buying else 'THIN / MIXED')
    timeframe = 'UNAVAILABLE'
    supporting_seconds: int | None = None
    missing = ['Executable buy/sell routes, actual interface costs and after-cost outcomes unverified']
    warnings = []
    evidence = []
    if dynamics.freshness != 'CURRENT':
        missing.append('Fresh independently verified curve observation unavailable')
    if dynamics.samples < 3 or dynamics.coverage_seconds < cfg.progression_min_seconds:
        missing.append('Timed curve progression/reversal history limited')
    security_current = (token.security.get('data_quality') == 'VERIFIED'
                        and current(token.security.get('last_updated', 0), now, settings.security_ttl_seconds))
    distribution_known = bool(token.creator and all(
        isinstance(token.security.get(key), (int, float)) and not isinstance(token.security.get(key), bool)
        and math.isfinite(token.security[key]) and 0 <= token.security[key] <= 100
        for key in ('creator_pct', 'top_1_independent_pct', 'top_5_independent_pct')))
    if not security_current:
        missing.append('Security UNKNOWN / STALE — loss and transfer restrictions not excluded')
    if not distribution_known:
        missing.append('Creator/holder concentration measurements incomplete; distribution safety unknown')
    if token.liquidity is None or not current(token.last_liquidity, now, settings.max_data_age_seconds):
        missing.append('Current provider liquidity unavailable; exit feasibility unknown')
    prices = sorted({e.ts: e.price for e in events if e.kind == 'market' and e.source == 'DEX Screener'
                     and e.currency == 'USD' and e.price and 0 <= now - e.ts <= 60}.items())
    price = None
    if len(prices) >= 3 and current(prices[-1][0], now, settings.max_data_age_seconds):
        changes = [b[1]-a[1] for a, b in zip(prices, prices[1:])]
        change_pct = (prices[-1][1]/prices[0][1]-1)*100
        price = dict(source='DEX Screener displayed USD marks; not fills', samples=len(prices),
            observed_at=prices[-1][0], change_pct=change_pct,
            pattern='RISING SAMPLED MARKS' if all(x > 0 for x in changes) else
                    'FALLING SAMPLED MARKS' if all(x < 0 for x in changes) else 'MIXED SAMPLED MARKS')
        if not math.isfinite(change_pct):
            price = None
    if price is None:
        missing.append('Timestamped provider price series unavailable; no chart/return pattern inferred')
    creator_sell = any(e[1] == 'sell' and token.creator and e[2] == token.creator for e in observed)
    invalid_distribution = any(token.security.get(key) is not None and (
        not isinstance(token.security[key], (int, float)) or isinstance(token.security[key], bool)
        or not math.isfinite(token.security[key]) or not 0 <= token.security[key] <= 100)
        for key in ('creator_pct', 'top_1_independent_pct', 'top_5_independent_pct'))
    concentration = any(isinstance(token.security.get(key), (int, float))
                        and not isinstance(token.security.get(key), bool)
                        and token.security[key] > limit
                        for key, limit in (('top_1_independent_pct', settings.max_top1_pct),
                                           ('top_5_independent_pct', settings.max_top5_pct)))
    risks = []
    if token.security.get('hard_failures'):
        risks.append('Recorded hard security failure; inspect the existing security report')
    if invalid_distribution:
        risks.append('Invalid/nonfinite holder-distribution evidence')
    if concentration:
        risks.append('Known holder concentration exceeds the unchanged strategy limits')
    if token.decision.get('decision') == 'REJECT' or token.state in (State.REJECTED, State.EXPIRED):
        risks.append('Existing core rejection or rejected/expired lifecycle')
    if creator_sell:
        risks.append('Canonical creator sell direction observed; no unknown amount is inferred')
    if token.disagreement:
        risks.append('Recorded provider disagreement')
    if token.degraded:
        risks.append('Recorded evidence degradation')
    hard = bool(risks)
    coordination_window = (latest if supported(latest) and latest['coordination_suspected'] else
                           history if supported(history) and history['coordination_suspected'] else None)
    coordinated = coordination_window is not None
    label, direction = 'NEUTRAL / WAIT', 'NEUTRAL'
    if hard:
        label, direction = 'AVOID', 'RISK'
        timeframe = 'RECORDED RISK EVIDENCE'
        evidence.extend(risks)
    elif (token.graduation is not None or token.decision.get('decision') == 'MISSED'
          or dynamics.current is not None and dynamics.current >= 85):
        label, direction = 'TOO EXTENDED', 'CAUTION'
        timeframe = 'LIFECYCLE / CORE ASSESSMENT'
        evidence.append('Existing missed/extended assessment, post-graduation or >=85% high lifecycle region; not a claim of price growth')
    elif not latest['complete'] or not short or dynamics.freshness != 'CURRENT':
        label = 'INSUFFICIENT DATA'
        evidence.append('Current interpretation needs clean 10s continuity and supported observations; gaps are not inactivity')
    elif dynamics.retreat_pp is not None and dynamics.retreat_pp >= cfg.collapse_pp:
        label, direction = 'BEARISH PRESSURE', 'BEARISH'
        timeframe = 'VERIFIED CURVE HISTORY'
        evidence.append('Verified curve retreat meets the existing collapse boundary; this is lifecycle evidence, not inferred selling')
    elif coordinated:
        label, direction = 'AVOID', 'RISK'
        timeframe, supporting_seconds = ('10s SIZE/TIMING', 10) if coordination_window is latest else ('30s SIZE/TIMING', 30)
        evidence.append('Suspected coordinated sizes/timing; not proof of common ownership; bullish reading withheld')
    elif active_selling:
        label, direction = 'BEARISH PRESSURE', 'BEARISH'
        timeframe, supporting_seconds = '10s', 10
        evidence.append('Observed sell dominance by count or consistent-unit net flow in the clean latest 10s')
    elif active_buying:
        timeframe, supporting_seconds = '10s', 10
        if dynamics.retreat_pp is not None and dynamics.retreat_pp >= cfg.pullback_min_pp:
            label, direction = 'PULLBACK WATCH', 'RECOVERING'
            timeframe = '10s + VERIFIED CURVE HISTORY'
            evidence.append('Verified curve retreat with renewed clean 10s buying; not a price pullback claim')
        elif (supported(medium) and medium['units_valid'] and medium['independent_buyers'] is not None
              and medium['independent_buyers'] >= EARLY_MARKET_POLICY['min_buyers']
              and (medium['buying_persistence'] or 0) >= EARLY_MARKET_POLICY['persistence_fraction']
              and (medium['net_flow'] or 0) > 0 and positive_history
              and (latest['arrival_acceleration'] or 0) >= 0
              and (history['arrival_acceleration'] or 0) >= 0):
            label, direction = 'BULLISH DEVELOPING', 'BULLISH'
            timeframe, supporting_seconds = '10s + 30s + 60s', 60
            evidence.append('Active 10s buying supported by positive 30s history and persistent consistent-unit 60s breadth/flow')
        else:
            label, direction = 'ACTIVE EMERGING BULLISH', 'BULLISH'
            evidence.append('Clean latest 10s buy-count dominance across at least three observed buyer addresses; not proof of acceleration')
        if history['arrival_acceleration'] is not None and history['arrival_acceleration'] < 0:
            warnings.append('30s arrival has declined despite active 10s buying; longer persistence unconfirmed')
    elif positive_history:
        label, direction = 'BUYING COOLING / WAIT', 'COOLING'
        timeframe, supporting_seconds = '30s HISTORY; 10s QUIET / INSUFFICIENT BUYING', 30
        evidence.append('Positive 30s buying history, but latest 10s buying/breadth is insufficient; historical net flow is not current acceleration')
    elif supported(latest):
        timeframe, supporting_seconds = '10s', 10
        evidence.append('Mixed current participation; no supported bullish continuation')
    else:
        label = 'INSUFFICIENT DATA'
        evidence.append('No adequately sampled current interpretation; quiet/thin activity is not bearish selling')
    if active_buying and supported(history) and not positive_history:
        warnings.append('Active 10s buying conflicts with 30s context; developing momentum is unconfirmed')
    if not short:
        missing.append('Fresh clean 10s/30s coverage with at least three canonical trades unavailable')
    if short:
        evidence.append(f"{'10s' if short is latest else '30s historical context'}: {short['buys']} buys / {short['sells']} sells; "
                        f"{short['raw_unique_buyers']} observed buyer addresses, not necessarily independent")
        if not short['units_valid']:
            missing.append('Amount-weighted flow, independent-buyer estimate and coordination model unavailable')
    if price and price['change_pct'] > 0 and (not short or (short['net_flow'] or 0) <= 0):
        warnings.append('Rising displayed price lacks supporting current amount-weighted buying flow')
    if windows['180']['complete'] is False:
        warnings.append('180s established evidence incomplete; short-window interpretation only')
    eligible = bool(direction in ('BULLISH', 'RECOVERING') and active_buying and not hard and not coordinated
                    and token.graduation is None and dynamics.freshness == 'CURRENT'
                    and token.state in (State.WATCHING, State.MATURING, State.NEAR_GRADUATION))
    # Ordinal attention only, never expected return or probability.
    rank = (3 if label == 'BULLISH DEVELOPING' else 2 if label == 'ACTIVE EMERGING BULLISH' else
            1 if label == 'PULLBACK WATCH' else 0)
    valid_until = min(now + min(EARLY_MARKET_POLICY['windows']),
                      token.last_trade + settings.max_data_age_seconds,
                      token.last_curve + cfg.curve_fresh_seconds)
    if active_buying:
        valid_until = min(valid_until, max(e[0] for e in observed if e[1] == 'buy') + 10)
    if security_current:
        valid_until = min(valid_until, token.security['last_updated'] + settings.security_ttl_seconds)
    if price:
        valid_until = min(valid_until, price['observed_at'] + settings.max_data_age_seconds)
    if token.liquidity is not None and current(token.last_liquidity, now, settings.max_data_age_seconds):
        valid_until = min(valid_until, token.last_liquidity + settings.max_data_age_seconds)
    return dict(version=EARLY_MARKET_VERSION, observed_at=now,
        valid_until=valid_until,
        classification=label, direction=direction, attention_rank=rank,
        supporting_timeframe=timeframe, supporting_window_seconds=supporting_seconds,
        activity_state=activity, active_buying=active_buying,
        latest_trade_age=now-max(e[0] for e in observed) if observed else None,
        latest_buy_age=now-max(e[0] for e in observed if e[1] == 'buy')
                       if any(e[1] == 'buy' for e in observed) else None,
        uncertainty='VERY HIGH' if (not security_current or not distribution_known or not short
                                   or not short['units_valid'] or short['independent_buyers'] is None) else
                    'HIGH' if not windows['180']['complete'] or price is None else 'UNCALIBRATED',
        basis='CONSISTENT-UNIT FLOW' if short and short['units_valid'] and short['independent_buyers'] is not None
              else 'CANONICAL EVENT COUNTS ONLY' if short else 'LIFECYCLE / INCOMPLETE OBSERVATIONS',
        speculative_review=eligible, windows=windows, price=price,
        curve_progress=dynamics.current, curve_retreat_pp=dynamics.retreat_pp,
        curve_samples=dynamics.samples, curve_coverage_seconds=dynamics.coverage_seconds,
        security=('CURRENT VERIFIED SNAPSHOT' + ('; DISTRIBUTION UNKNOWN' if not distribution_known else '')
                  if security_current else 'UNKNOWN / STALE'),
        interpretation=evidence, missing=missing, warnings=warnings,
        strengthens=(['Persistent canonical selling across additional fresh windows',
                      'Verified security and current liquidity/route evidence'] if direction == 'BEARISH' else
                     ['Independent risk investigation; hard gates remain binding'] if direction == 'RISK' else
                     ['Fresh independent buyer breadth and sustained consistent-unit buying',
                      'Verified security and current liquidity/route evidence']),
        invalidates=(['Renewed supported clean 10s buying can replace cooling; 30s history alone cannot',
                     'New selling/risk or loss of continuity ends the watch context'] if direction == 'COOLING' else
                    ['Sustained buying replacing selling across clean windows',
                     'Loss of continuity or stale observations'] if direction == 'BEARISH' else
                    ['Momentum cannot override known hard risks or core rejection',
                     'Stale observations cannot establish that a historical risk disappeared'] if direction == 'RISK' else
                    ['Creator selling, security failure or provider disagreement',
                     'Loss of active 10s buying, sell dominance, continuity loss or stale observations']),
        manual_only=True, validated_edge=False)


# Source-pinned separately from the unchanged opportunity-v1 research protocol.
EARLY_MARKET_VERSION = 'early-market-v2.1-' + hashlib.sha256(
    json.dumps(EARLY_MARKET_POLICY, sort_keys=True).encode()
    + inspect.getsource(early_market_view).encode()).hexdigest()[:12]
