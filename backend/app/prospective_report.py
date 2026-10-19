"""Read-only prospective analysis; consumes frozen OutcomeCollector results, never prices."""
from collections import Counter
from typing import Any
import json
import math
import sqlite3
import time

from backend.app.evaluation import Summary
from backend.app.prospective import PRIMARY, CohortIntegrityError, digest

WARNINGS = [
    "Selection bias: eligibility is frozen but not randomized",
    "Survivorship risk: missing outcomes remain in the coverage denominator",
    "Unavailable-outcome rate is reported; missingness may depend on returns",
    "Same-market correlation: token/session samples are not fully independent",
    "Overlapping token exposure: aggregate returns are not an executable portfolio",
    "Regime dependence: results may not generalize",
    "Multiple testing: secondary horizons are exploratory, never the primary endpoint",
    "Normal-CI limitation: heavy tails and dependence can invalidate nominal confidence",
    "No guarantee of future returns; no automatic evidence approval or execution",
    "Repeated interim looks and optional stopping invalidate confirmatory normal-CI claims",
]


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def endpoint(connection, manifest, horizon, as_of):
    summary = Summary(manifest["min_holdout_samples"])
    mfe, mae = Summary(), Summary()
    statuses: Counter = Counter()
    decisions: Counter = Counter(dict.fromkeys(("WAIT", "REJECT", "ENTRY_CANDIDATE", "ALLOW_PAPER_ENTRY"), 0))
    states: Counter = Counter()
    sessions: dict[str, Counter] = {}
    infrastructure: dict[str, Counter] = {name: Counter() for name in ("DEGRADED", "NO_RECORDED_DEGRADATION", "UNKNOWN_QUALITY")}
    query = """SELECT e.session,e.ts,e.snapshot,o.payload,q.payload FROM prospective_enrollments e
        LEFT JOIN prospective_outcomes o ON e.cohort_id=o.cohort_id AND e.signal_id=o.signal_id
        AND o.horizon=? AND o.ts<=? AND o.recorded_at<=?
        LEFT JOIN prospective_sessions q ON q.cohort_id=e.cohort_id AND q.session=e.session
        WHERE e.cohort_id=? AND e.primary_sample=1 AND e.enrolled_at<=? AND e.ts<=?
        ORDER BY e.ts,e.signal_id"""
    for session, stamp, snapshot, outcome, quality_payload in connection.execute(query, (horizon, as_of, as_of,
            manifest["cohort_id"], as_of, as_of)):
        signal = json.loads(snapshot)
        decisions[signal["decision"]["decision"]] += 1
        states[signal["state"]] += 1
        row = json.loads(outcome) if outcome else {}
        status = row.get("status", "PENDING" if as_of <= stamp + horizon + manifest["config"]["max_data_age_seconds"]
                         else "UNAVAILABLE_NOT_RECORDED")
        if status == "MEASURED" and not finite(row.get("net_return_pct")):
            status = "UNAVAILABLE_INVALID_LEDGER"
        statuses[status] += 1
        quality = json.loads(quality_payload) if quality_payload else None
        group = "UNKNOWN_QUALITY"
        if quality and quality["updated_at"] <= as_of:
            degraded = any(quality.get(k, 0) for k in ("recovery_overflow", "recovery_expired", "global_trade_gaps",
                "pump_reconnects", "pumpswap_reconnects", "rpc_errors", "rpc_429", "stale_trade_rejections",
                "unavailable_provider_samples", "storage_full_samples", "resource_pressure_samples")) or quality.get("queue", {}).get("stale_while_queued", 0)
            group = "DEGRADED" if degraded else "NO_RECORDED_DEGRADATION"
        infrastructure[group][status] += 1
        if session in sessions or len(sessions) < 200:
            counts = sessions.setdefault(session, Counter())
            counts[status] += 1
        if status == "MEASURED":
            summary.add(row["net_return_pct"])
            if finite(row.get("mfe_pct")):
                mfe.add(row["mfe_pct"])
            if finite(row.get("mae_pct")):
                mae.add(row["mae_pct"])
    total = sum(statuses.values())
    measured = summary.count
    coverage = 100 * measured / total if total else None
    result = summary.result()
    mean, lower = result["expectancy_net_pct"], result["lower_ci"]
    status = "INSUFFICIENT_SAMPLE"
    if measured >= manifest["min_holdout_samples"]:
        status = "NEGATIVE_OR_INCONCLUSIVE"
        if mean is not None and mean > 0 and lower is not None and lower > 0:
            status = ("PROSPECTIVE_EVIDENCE_CANDIDATE" if coverage is not None
                      and coverage >= manifest["minimum_primary_coverage_pct"] else "POSITIVE_DESCRIPTIVE")
    variance = max(0, (summary.squared - summary.total**2 / measured) / (measured - 1)) if measured > 1 else None
    return {"horizon_seconds": horizon, "role": "PRIMARY" if horizon == PRIMARY else "SECONDARY_EXPLORATORY",
        "unique_token_session_samples": total, "measured": measured,
        "pending": statuses["PENDING"], "unavailable": total - measured - statuses["PENDING"],
        "coverage_pct": coverage, "unavailable_outcome_rate_pct": 100 * (total - measured - statuses["PENDING"]) / total if total else None,
        "status_counts": dict(statuses), "status": status,
        "mean_net_return_pct": mean, "median_net_return_pct": result["median_net_pct"],
        "win_rate_pct": result["win_rate_pct"], "variance": variance,
        "stddev": math.sqrt(variance) if variance is not None else None,
        "lower_ci": lower, "upper_ci": result["upper_ci"], "confidence_level": .95,
        "ci_method": result["ci_method"], "profit_factor": result["profit_factor"],
        "median_winner_pct": result["median_winner_pct"], "median_loser_pct": result["median_loser_pct"],
        "mfe_median_pct": mfe.result()["median_net_pct"], "mae_median_pct": mae.result()["median_net_pct"],
        "median_method": "Deterministic bounded reservoir, at most 5000 values per metric",
        "median_sample_count": result["median_sample_count"],
        "decision_breakdown": dict(decisions), "state_breakdown": dict(states),
        "infrastructure_coverage_groups": {name: {"status_counts": dict(counts),
            "samples": sum(counts.values()), "measured": counts["MEASURED"],
            "coverage_pct": 100 * counts["MEASURED"] / sum(counts.values()) if counts else None}
            for name, counts in infrastructure.items()},
        "quality_limitation": "Session aggregates are descriptive; they do not establish exact gap overlap or causality",
        "profit_factor_basis": "Sums of positive/negative net return percentages, not executable portfolio P&L",
        "excursions_basis": "OutcomeCollector gross observed price MFE/MAE"}, sessions


def report(path, cohort_id, as_of=None):
    as_of = time.time() if as_of is None else as_of
    if not finite(as_of):
        raise CohortIntegrityError("Invalid report timestamp")
    connection = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
    try:
        connection.execute("PRAGMA query_only=ON")
        connection.execute("BEGIN")
        row = connection.execute("SELECT manifest,digest FROM prospective_cohorts WHERE cohort_id=?", (cohort_id,)).fetchone()
        if not row:
            raise CohortIntegrityError("Unknown cohort")
        manifest = json.loads(row[0])
        if digest(manifest) != row[1] or manifest["primary_endpoint"] != {
                "horizon_seconds": 300, "metric": "after_cost_net_return_pct", "role": "PRIMARY"}:
            raise CohortIntegrityError("Frozen manifest integrity failure")
        primary, sessions = endpoint(connection, manifest, PRIMARY, as_of)
        raw = connection.execute("SELECT count(*) FROM prospective_enrollments WHERE cohort_id=? AND enrolled_at<=? AND ts<=?",
                                 (cohort_id, as_of, as_of)).fetchone()[0]
        quality_rows: list[dict[str, Any]] = []
        quality_total = 0
        quality_seen = set()
        for session, payload in connection.execute("SELECT session,payload FROM prospective_sessions WHERE cohort_id=? ORDER BY session", (cohort_id,)):
            quality_total += 1
            quality = json.loads(payload)
            if quality["updated_at"] > as_of:
                quality = {"status": "QUALITY_NOT_AVAILABLE_AS_OF"}
            counters = dict(sessions.get(session, {}))
            if len(quality_rows) < 200:
                quality_seen.add(session)
                quality_rows.append({"session": session, "primary_status_counts": counters, "quality": quality})
        for session in sorted(sessions):
            if session not in quality_seen and len(quality_rows) < 200:
                quality_rows.append({"session": session, "primary_status_counts": dict(sessions[session]),
                                     "quality": {"status": "MISSING_SESSION_QUALITY"}})
        return {"manifest": manifest, "as_of": as_of, "analysis": "FROZEN_PROSPECTIVE, separate from retrospective 50/25/25",
            "raw_eligible_signals": raw, "unique_token_session_primary_samples": primary["unique_token_session_samples"],
            "repeated_signals_excluded_from_primary": raw - primary["unique_token_session_samples"],
            "primary": primary,
            "secondary_exploratory": [endpoint(connection, manifest, item["horizon_seconds"], as_of)[0]
                                      for item in manifest["secondary_endpoints"]],
            "session_quality": quality_rows, "session_quality_total": quality_total,
            "session_quality_display_limit": 200, "quality_includes_startup_unavailability": True,
            "warnings": WARNINGS, "approval_modified": False, "live_trading_enabled": False}
    finally:
        connection.close()
