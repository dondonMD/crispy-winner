"""Read-only finalization. Interim reports expose operations, never outcome/edge conclusions."""

from collections import Counter, defaultdict
import json
import random
import sqlite3
import statistics
from typing import Any

from backend.app.early_edge import HORIZONS, digest, identity
from backend.app.config import Settings
from backend.app.early_edge_design import SECONDARY_LATENCIES_MS

NUMERIC = ("MEASURED", "ECONOMIC_ZERO_EXIT")


def percentile(values, p):
    if not values:
        return None
    v = sorted(values)
    x = (len(v) - 1) * p
    i = int(x)
    return v[i] + (v[min(i + 1, len(v) - 1)] - v[i]) * (x - i)


def summary(values):
    import math

    if not values:
        return dict(
            n=0,
            mean=None,
            median=None,
            win_rate=None,
            stddev=None,
            variance=None,
            normal_ci95=[None, None],
            profit_factor=None,
        )
    mean = statistics.mean(values)
    sd = statistics.stdev(values) if len(values) > 1 else None
    d = 1.96 * sd / math.sqrt(len(values)) if sd is not None else None
    wins, losses = [v for v in values if v > 0], [v for v in values if v < 0]
    return dict(
        n=len(values),
        mean=mean,
        median=statistics.median(values),
        win_rate=sum(v > 0 for v in values) / len(values),
        stddev=sd,
        variance=sd**2 if sd is not None else None,
        normal_ci95=[mean - d, mean + d] if d is not None else [None, None],
        profit_factor=sum(wins) / -sum(losses) if losses else None,
        median_winner=statistics.median(wins) if wins else None,
        median_loser=statistics.median(losses) if losses else None,
        top_winner_share_of_positive_pnl=max(wins) / sum(wins) if wins else None,
        mean_without_best=statistics.mean(sorted(values)[:-1]) if len(values) > 1 else None,
    )


def contrast(rows):
    """Retained descriptive helper, not the v2 primary paired comparison."""
    groups: dict[str, Any] = defaultdict(lambda: defaultdict(list))
    for r in rows:
        groups[r["stratum"]][r["arm"]].append(r["value"])
    n = sum(len(g["EARLY"]) for g in groups.values())
    if not n or any(g["EARLY"] and not g["CONTROL"] for g in groups.values()):
        return None
    return (
        sum(
            len(g["EARLY"]) * (statistics.mean(g["EARLY"]) - statistics.mean(g["CONTROL"]))
            for g in groups.values()
            if g["EARLY"]
        )
        / n
    )


def bootstraps(rows, seed=20261020, resamples=10000):
    clusters = defaultdict(list)
    for r in rows:
        clusters[r["mint"]].append(r)
    keys = sorted(clusters)
    means = []
    differences = []
    rng = random.Random(seed)
    if len(keys) >= 2:
        for _ in range(resamples):
            sample = [r for _ in keys for r in clusters[keys[rng.randrange(len(keys))]]]
            vals = [r["value"] for r in sample if r["arm"] == "EARLY"]
            if vals:
                means.append(statistics.mean(vals))
            d = contrast(sample)
            if d is not None:
                differences.append(d)
    return dict(
        primary_ci95=[percentile(means, 0.025), percentile(means, 0.975)],
        contrast_ci95=[percentile(differences, 0.025), percentile(differences, 0.975)],
        valid_primary_resamples=len(means),
        valid_contrast_resamples=len(differences),
        mint_clusters=len(keys),
    )


def paired_bootstrap(rows, pairs, seed=20261020, resamples=10000):
    """Mint-cluster closure over pair edges; no pair or crossover can be split."""
    byid = {r["id"]: r for r in rows}
    early = [r for r in rows if r["arm"] == "EARLY"]
    primary = bootstraps(early, seed, resamples)
    parent = {r["mint"]: r["mint"] for r in rows}

    def root(m):
        while parent[m] != m:
            m = parent[m]
        return m

    valid = []
    for p in pairs:
        a, b = byid.get(p["treatment"]), byid.get(p["control"])
        if a and b:
            ra, rb = root(a["mint"]), root(b["mint"])
            parent[max(ra, rb)] = min(ra, rb)
            valid.append(dict(pair=p["treatment"], a=a, b=b, value=a["value"] - b["value"]))
    components = defaultdict(list)
    for p in valid:
        components[root(p["a"]["mint"])].append(p)
    keys = sorted(components)
    deltas = []
    rng = random.Random(seed)
    if len(keys) >= 2:
        for _ in range(resamples):
            sample = [p for _ in keys for p in components[keys[rng.randrange(len(keys))]]]
            deltas.append(statistics.mean(p["value"] for p in sample))
    return dict(
        primary_ci95=primary["primary_ci95"],
        valid_primary_resamples=primary["valid_primary_resamples"],
        contrast_ci95=[percentile(deltas, 0.025), percentile(deltas, 0.975)],
        valid_contrast_resamples=len(deltas),
        paired_difference=statistics.mean(p["value"] for p in valid) if valid else None,
        complete_pairs=len(valid),
        mint_clusters=primary["mint_clusters"],
        independent_mint_pair_components=len(keys),
        rule="Mint clusters merged by immutable pair edges; whole components resampled, retaining all sessions/crossovers",
    )


def evidence_status(
    plan, early_n, accounting, missing, mean, delta, bootstrap, integrity, finalized=False, all_matched=False
):
    if not finalized:
        return "INTERIM_OPERATIONAL_ONLY"
    if early_n < 100:
        return "INSUFFICIENT_SAMPLE"
    if not integrity or mean is None or mean <= 0 or delta is None or delta <= 0:
        return "NEGATIVE_OR_UNPROVEN"
    a, b = bootstrap["primary_ci95"][0], bootstrap["contrast_ci95"][0]
    if (
        not plan["synthetic"]
        and accounting == 1
        and missing == 0
        and all_matched
        and a is not None
        and a > 0
        and b is not None
        and b > 0
        and bootstrap["valid_primary_resamples"] == 10000
        and bootstrap["valid_contrast_resamples"] == 10000
    ):
        return "EARLY_EDGE_SUPPORTED"
    return "PROMISING_NOT_PROVEN"


def report(path):
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        m = db.execute("SELECT * FROM ee_manifest").fetchone()
        plan = json.loads(m["payload"])
        integrity = (
            digest(plan) == m["hash"]
            and plan.get("design_version") == 2
            and plan["primary_latency_seconds"] == 10
        )
        integrity &= identity(Settings(**plan["identity"]["config"]), require_clean=False) == plan["identity"]
        signals = [dict(r) for r in db.execute("SELECT * FROM ee_signals ORDER BY ts,id")]
        pairs = [dict(r) for r in db.execute("SELECT * FROM ee_pairs ORDER BY treatment")]
        for s in signals:
            integrity &= digest(json.loads(s["snapshot"])) == s["hash"] and s["ts"] > plan["created_at"]
        for p in pairs:
            integrity &= (
                digest({k: p[k] for k in ("treatment", "control", "risk_count", "reason")}) == p["hash"]
            )
        by_signal = {s["id"]: s for s in signals}
        sessions = {r["id"]: r["started"] for r in db.execute("SELECT * FROM ee_sessions")}
        for s in signals:
            snapshot = json.loads(s["snapshot"])
            integrity &= (
                s["mint"] == snapshot["mint"]
                and s["ts"] == snapshot["timestamp"]
                and s["ts"] >= sessions.get(s["session"], float("inf"))
                and s["arm"] == ("EARLY" if snapshot["action"] == "EARLY_OPPORTUNITY" else "CONTROL")
            )
        used = set()
        for p in pairs:
            t, c = by_signal.get(p["treatment"]), by_signal.get(p["control"])
            integrity &= bool(t and t["arm"] == "EARLY")
            if p["control"] is not None:
                integrity &= bool(
                    c
                    and c["arm"] == "CONTROL"
                    and t
                    and c["ts"] == t["ts"]
                    and c["session"] == t["session"]
                    and c["mint"] != t["mint"]
                    and p["control"] not in used
                )
                used.add(p["control"])
        integrity &= len(pairs) == sum(s["arm"] == "EARLY" for s in signals)
        outcomes = {
            (r["signal"], r["horizon"]): json.loads(r["payload"])
            for r in db.execute("SELECT * FROM ee_outcomes")
        }
        for table in ("ee_outcomes", "ee_secondary_outcomes", "ee_entries", "ee_secondary_entries"):
            for r in db.execute(f"SELECT * FROM {table}"):
                integrity &= digest(json.loads(r["payload"])) == r["hash"]
        closure = db.execute("SELECT * FROM ee_closure").fetchone()
        counts = Counter(s["arm"] for s in signals)
        if closure:
            if closure["reason"] == "TARGET_N":
                treatment_times = sorted(s["ts"] for s in signals if s["arm"] == "EARLY")
                integrity &= len(treatment_times) == 100 and 0 <= closure["ts"] - treatment_times[-1] <= 20
            elif closure["reason"] == "CALENDAR_LIMIT":
                integrity &= closure["ts"] == plan["created_at"] + 30 * 86400 and counts["EARLY"] < 100
            else:
                integrity = False
            integrity &= all(s["ts"] <= closure["ts"] for s in signals)
        terminal = sum((s["id"], 300) in outcomes for s in signals)
        missing = sum(o["status"] not in NUMERIC for (sid, h), o in outcomes.items() if h == 300)
        pending = len(signals) - terminal
        finalized = bool(closure) and pending == 0
        repeats = db.execute("SELECT coalesce(sum(n),0) FROM ee_repeats").fetchone()[0]
        result = dict(
            cohort_id=plan["cohort_id"],
            namespace=plan["namespace"],
            manifest=plan,
            integrity_passed=bool(integrity),
            finalized=finalized,
            enrollment_closed=bool(closure),
            closure=dict(closure) if closure else None,
            status="INTERIM_OPERATIONAL_ONLY",
            primary_unique_token_session_by_arm=dict(counts),
            raw_eligible_observations=len(signals) + repeats,
            repeat_observations_excluded=repeats,
            matched_controls=sum(p["control"] is not None for p in pairs),
            unmatched_treatments=sum(p["control"] is None for p in pairs),
            primary_accounting_fraction=terminal / len(signals) if signals else 0,
            primary_unavailable=missing,
            primary_pending=pending,
            primary_status_counts=dict(Counter(o["status"] for (sid, h), o in outcomes.items() if h == 300)),
            primary_outcome_coverage=sum(
                o["status"] in NUMERIC for (sid, h), o in outcomes.items() if h == 300
            )
            / len(signals)
            if signals
            else 0,
            session_quality=[
                dict(session=r["session"], ts=r["ts"], metrics=json.loads(r["payload"]))
                for r in db.execute("SELECT * FROM ee_quality ORDER BY id")
            ],
            observation_coverage=[
                dict(session=r["session"], mint=r["mint"], coverage=json.loads(r["payload"]))
                for r in db.execute("SELECT * FROM ee_coverage ORDER BY session,mint")
            ],
            limitations=plan["limitations"],
            horizons=None,
            primary_bootstrap=None,
            warning="No outcome statistics or approval conclusion before enrollment closure AND primary maturation. Statistical association is not causation or trading approval.",
        )
        if not finalized:
            return result
        horizons = {}
        rows = []
        for h in HORIZONS:
            values: dict[str, list[float]] = {a: [] for a in ("EARLY", "CONTROL")}
            status: Counter = Counter()
            for s in signals:
                o = outcomes.get((s["id"], h))
                status[s["arm"] + ":" + (o["status"] if o else "PENDING")] += 1
                if o and o["status"] in NUMERIC:
                    values[s["arm"]].append(o["net_return_pct"])
                    if h == 300:
                        rows.append(
                            dict(
                                id=s["id"],
                                mint=s["mint"],
                                arm=s["arm"],
                                stratum=s["stratum"],
                                value=o["net_return_pct"],
                            )
                        )
            horizons[str(h)] = dict(
                role="PRIMARY_10S" if h == 300 else "SECONDARY_EXPLORATORY",
                early=summary(values["EARLY"]),
                control=summary(values["CONTROL"]),
                statuses=dict(status),
            )
        boot = paired_bootstrap(rows, pairs, plan["bootstrap_seed"], plan["bootstrap_resamples"])
        all_matched = len(pairs) == counts["EARLY"] and all(p["control"] is not None for p in pairs)
        result["status"] = evidence_status(
            plan,
            horizons["300"]["early"]["n"],
            result["primary_accounting_fraction"],
            missing,
            horizons["300"]["early"]["mean"],
            boot["paired_difference"],
            boot,
            bool(integrity),
            True,
            all_matched,
        )
        result.update(horizons=horizons, primary_bootstrap=boot, secondary_latencies={})
        for latency in SECONDARY_LATENCIES_MS:
            vals: dict[str, list[float]] = {a: [] for a in ("EARLY", "CONTROL")}
            statuses: Counter = Counter()
            byid = {s["id"]: s for s in signals}
            for r in db.execute(
                "SELECT * FROM ee_secondary_outcomes WHERE latency_ms=? AND horizon=300", (latency,)
            ):
                a = byid[r["signal"]]["arm"]
                o = json.loads(r["payload"])
                statuses[a + ":" + o["status"]] += 1
                if o["status"] in NUMERIC:
                    vals[a].append(o["net_return_pct"])
            result["secondary_latencies"][str(latency / 1000)] = dict(
                role="SECONDARY_LATENCY_EXPLORATORY",
                early=summary(vals["EARLY"]),
                control=summary(vals["CONTROL"]),
                statuses=dict(statuses),
            )
        entries = {r["signal"]: json.loads(r["payload"]) for r in db.execute("SELECT * FROM ee_entries")}
        benchmarks = [dict(r) for r in db.execute("SELECT * FROM ee_benchmarks ORDER BY signal,kind")]
        result["crowd_descriptive"] = []
        for s in signals:
            if s["arm"] != "EARLY":
                continue
            b = {r["kind"]: r for r in benchmarks if r["signal"] == s["id"]}
            snap = json.loads(s["snapshot"])
            e = entries.get(s["id"])
            price = e["quote_raw"] * e["unit_usd"] / e["quantity"] if e else None
            obs = dict(
                signal=s["id"],
                signal_timestamp=s["ts"],
                signal_curve_progress=snap["curve_progress"],
                signal_independent_buyers=snap["features"].get("estimated_independent_buyers"),
                markers={},
            )
            for kind, qk in (
                ("CROWD_85", "CROWD_QUOTE"),
                ("BUYER_CROWD", "BUYER_QUOTE"),
                ("GRADUATION", None),
            ):
                mark = b.get(kind)
                q = json.loads(b[qk]["payload"]) if qk in b else {}
                obs["markers"][kind] = dict(
                    timestamp=mark["ts"] if mark else None,
                    elapsed_seconds=mark["ts"] - s["ts"] if mark else None,
                    quote_status=q.get(
                        "quote_status", "UNAVAILABLE_NO_PROSPECTIVE_QUOTE" if mark else "NOT_OBSERVED"
                    ),
                    quote_acquired_at=q.get("quote_acquired_at"),
                    executable_unit_cost_usd=q.get("unit_cost_usd"),
                    manual_entry_unit_cost_usd=price,
                    price_advantage_pct=100 * (q["unit_cost_usd"] / price - 1)
                    if price and q.get("unit_cost_usd")
                    else None,
                )
            result["crowd_descriptive"].append(obs)
        numeric = [(s, outcomes.get((s["id"], 300))) for s in signals]
        result["descriptive_by_arm"] = {}
        for arm in ("EARLY", "CONTROL"):
            items = [o for s, o in numeric if s["arm"] == arm and o and o["status"] in NUMERIC]
            result["descriptive_by_arm"][arm] = dict(
                mfe_median_pct=statistics.median(o["mfe_observed_pct"] for o in items) if items else None,
                mae_median_pct=statistics.median(o["mae_observed_pct"] for o in items) if items else None,
                max_observed_drawdown_pct=max((o["observed_max_drawdown_pct"] for o in items), default=None),
                non_recovery_rent_sensitivity=summary(
                    [o["non_recovery_sensitivity_net_return_pct"] for o in items]
                ),
                protocol_only_cost_view=summary([o["protocol_only_net_return_pct"] for o in items]),
            )
        early = [s for s in signals if s["arm"] == "EARLY"]
        result["signal_time_strata_counts"] = dict(Counter(s["stratum"] for s in signals))
        result["observed_reach_rates"] = {
            k: sum(any(b["signal"] == s["id"] and b["kind"] == k for b in benchmarks) for s in early)
            / len(early)
            if early
            else None
            for k in ("CROWD_85", "BUYER_CROWD", "GRADUATION")
        }
        result["reach_censoring_warning"] = (
            "Observed during prospective sessions only; no future backfill or conditioning of primary expectancy on crowd/graduation reach."
        )
        if result["status"] == "EARLY_EDGE_SUPPORTED":
            result["conclusion"] = (
                "CRISPY WINNER's prospective EARLY signals were associated with superior after-cost executable outcomes versus contemporaneous eligible non-EARLY controls, under the frozen read-only quote and cost assumptions. No causal or live execution approval claim."
            )
        return result
    finally:
        db.close()
