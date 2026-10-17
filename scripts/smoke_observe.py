"""Short read-only free OBSERVE probe, isolated temporary DB; no paid subscriptions."""

import asyncio
import argparse
from collections import Counter, OrderedDict
import json
import math
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.config import Settings
from backend.app.engine import RadarEngine


async def main(seconds=65, max_deep=25):
    with tempfile.TemporaryDirectory() as directory:
        engine = RadarEngine(
            Settings(mode="OBSERVE", trade_stream_enabled=False, max_deep=max_deep),
            Path(directory) / "observe.db",
        )
        curve_attempts = 0
        successes = 0
        launch_count = 0
        trade_rejections = {"stale": 0, "other": 0}
        states = set()
        background_observations: OrderedDict[str, int] = OrderedDict()
        curve_events = {"hot": 0, "background": 0}
        scan_counts = {"security_attempts": 0, "security_completed": 0, "security_outside_hot": 0}
        peaks = {"rss_mb": 0.0, "queue_size": 0, "active": 0, "hot": 0, "background": 0, "cpu_pct": 0.0}
        pressure_changes = []
        previous_level = -1
        peak_expiry_deferred = 0
        maximum_clean_wss_coverage = 0.0
        maximum_token_clean_coverage = 0.0
        maximum_current_candidates = 0
        first_current_seconds = None
        observed_current_examples = []
        clean_candidates: OrderedDict[str, None] = OrderedDict()
        maximum_oldest_trade_age = 0.0
        current_ranges = {k: {"min": None, "max": None} for k in
                          ("estimated_independent_buyers", "flow_ratio", "whale_share", "samples")}
        original_inspect = engine.rpc.inspect
        original = engine.rpc.curve_progress_batch
        original_process = engine.process

        async def counted(mints, batch_size, **kwargs):
            nonlocal curve_attempts, successes
            curve_attempts += len(mints)
            reports = await original(mints, batch_size, **kwargs)
            successes += sum(r.get("curve_progress") is not None for r in reports.values())
            return reports

        def counted_process(event, now=None):
            nonlocal launch_count
            accepted = original_process(event, now)
            if event.kind == "trade" and not accepted:
                reason = "stale" if abs((now if now is not None else event.ts) - event.ts) > engine.settings.max_data_age_seconds else "other"
                trade_rejections[reason] += 1
            if accepted:
                launch_count += event.kind == "create"
                states.add(engine.tokens[event.mint].state.value)
                if event.kind == "curve":
                    tier = event.evidence.get("poll_tier", "hot")
                    curve_events[tier] += 1
                    if tier == "background":
                        background_observations[event.mint] = background_observations.get(event.mint, 0) + 1
                        background_observations.move_to_end(event.mint)
                        while len(background_observations) > engine.settings.max_candidates:
                            background_observations.popitem(last=False)
            return accepted

        async def inspected(mint, creator="", known_accounts=None):
            scan_counts["security_attempts"] += 1
            scan_counts["security_outside_hot"] += mint not in engine.deep_mints()
            report = await original_inspect(mint, creator, known_accounts)
            scan_counts["security_completed"] += 1
            return report

        engine.rpc.inspect = inspected
        engine.rpc.curve_progress_batch = counted
        engine.process = counted_process
        initial_db_bytes = engine.db.size()
        start_cpu = time.process_time()
        start_wall = time.time()
        start = time.monotonic()
        await engine.start()
        try:
            while time.monotonic() - start < seconds:
                await asyncio.sleep(min(1, max(0, seconds - (time.monotonic() - start))))
                peak_expiry_deferred = max(
                    peak_expiry_deferred, engine.expiry_metrics["expiry_deferred_for_poll"]
                )
                sample_now = time.time()
                health = engine.onchain.health
                wss_clean = (max(0, sample_now - max(health["connected_since"], health["last_decode_gap"]))
                             if health["connected"] else 0)
                maximum_clean_wss_coverage = max(maximum_clean_wss_coverage, wss_clean)
                maximum_token_clean_coverage = max(maximum_token_clean_coverage,
                    max((engine.trade_coverage_seconds(t, sample_now) for t in engine.tokens.values()), default=0))
                maximum_oldest_trade_age = max(maximum_oldest_trade_age, engine.queue.snapshot(sample_now)["oldest_trade_age"])
                for t in engine.tokens.values():
                    if engine.trade_coverage_seconds(t, sample_now) >= 180 and not engine.recovery.overlaps(t, sample_now):
                        clean_candidates[t.mint] = None
                        if len(clean_candidates) > engine.settings.max_candidates:
                            clean_candidates.popitem(last=False)
                current_tokens = [t for t in engine.tokens.values() if engine.trade_status(t, sample_now) == "CURRENT"]
                maximum_current_candidates = max(maximum_current_candidates, len(current_tokens))
                for token in current_tokens:
                    for key, bounds in current_ranges.items():
                        value = token.features["180"].get(key)
                        if isinstance(value, (int, float)) and math.isfinite(value):
                            bounds["min"] = value if bounds["min"] is None else min(value, bounds["min"])
                            bounds["max"] = value if bounds["max"] is None else max(value, bounds["max"])
                if current_tokens and first_current_seconds is None:
                    first_current_seconds = round(time.monotonic() - start, 2)
                    observed_current_examples = [
                        {k: t.features["180"].get(k) for k in ("buy_count", "sell_count",
                         "estimated_independent_buyers", "flow_ratio", "whale_share", "coverage_seconds")}
                        for t in current_tokens[:5]
                    ]
                level = engine.rpc.health["backoff_level"]
                if level != previous_level:
                    pressure_changes.append({"seconds": round(time.monotonic() - start, 1), "level": level})
                    previous_level = level
                peaks["cpu_pct"] = max(peaks["cpu_pct"], engine.metrics.get("cpu_pct", 0))
                peaks["rss_mb"] = max(peaks["rss_mb"], engine.metrics.get("rss_mb", 0))
                peaks["queue_size"] = max(peaks["queue_size"], len(engine.queue.heap))
                peaks["active"] = max(peaks["active"], len(engine.tokens))
                peaks["hot"] = max(peaks["hot"], len(engine.deep_mints()))
                peaks["background"] = max(
                    peaks["background"], len(engine.background_tokens(engine.deep_mints()))
                )
            requests_before_views = engine.rpc.health["requests"]
            snap = engine.snapshot()
            for _ in range(100):
                engine.snapshot()
            companion_view_requests = engine.rpc.health["requests"] - requests_before_views
            elapsed = time.monotonic() - start
            trade_blockers = dict.fromkeys(("no_samples", "invalid_units", "insufficient_samples",
                                           "insufficient_continuity", "stale", "disconnected", "pending_recovery"), 0)
            for token in engine.tokens.values():
                f = token.features.get("180", {})
                trade_blockers["no_samples"] += not f.get("samples")
                trade_blockers["invalid_units"] += not f.get("units_valid")
                trade_blockers["insufficient_samples"] += f.get("samples", 0) < 3
                trade_blockers["insufficient_continuity"] += engine.trade_coverage_seconds(token, time.time()) < 180
                trade_blockers["stale"] += not (0 <= time.time() - token.last_trade <= engine.settings.max_data_age_seconds)
                trade_blockers["disconnected"] += not engine.onchain.health["connected"]
                trade_blockers["pending_recovery"] += engine.recovery.overlaps(token, time.time())
            report = {
                "current_evidence_ranges": current_ranges,
                "transport_timing": [{"seconds": round(item["at"] - start_wall, 2), "state": item["state"]}
                                     for item in engine.onchain.health["transport_transitions"]],
                "truncation_recovery": engine.recovery.snapshot(),
                "ordinary_monitoring_rpc_requests": engine.rpc.health["requests"] - engine.rpc.truncation_metrics["requests"],
                "queue_lag": engine.queue.snapshot(),
                "maximum_oldest_trade_age": maximum_oldest_trade_age,
                "processed_trade_rate": sum(engine.trade_observations.values()) / elapsed,
                "candidates_reaching_180_clean_seconds_bounded": len(clean_candidates),
                "maximum_clean_wss_coverage_seconds": round(maximum_clean_wss_coverage, 2),
                "maximum_token_clean_coverage_seconds": round(maximum_token_clean_coverage, 2),
                "final_max_token_clean_coverage_seconds": round(max((engine.trade_coverage_seconds(t, time.time())
                    for t in engine.tokens.values()), default=0), 2),
                "maximum_current_candidates": maximum_current_candidates,
                "first_current_seconds": first_current_seconds,
                "observed_current_examples": observed_current_examples,
                "trade_evidence_blockers": trade_blockers,
                "trade_continuity": engine.trade_continuity,
                "average_process_cpu_pct": round(100 * (time.process_time() - start_cpu) / elapsed, 2),
                "bounded_trade_unit_observations": dict(Counter(
                    f"{event.currency}:{event.evidence.get('quote_source', 'unknown')}"
                    for token in engine.tokens.values() for event in token.events if event.kind == "trade"
                )),
                "trade_evidence_counts": snap["health"]["trade_evidence_counts"],
                "trade_observations": engine.trade_observations,
                "trade_process_rejections": trade_rejections,
                "dropped_trade_events": engine.queue.dropped_trades,
                "dropped_critical_events": engine.queue.dropped_critical,
                "clean_wss_coverage_seconds": snap["health"]["clean_wss_coverage_seconds"],
                "trade_http_requests": engine.onchain.health["http_requests"],
                "flow_examples": [
                    {k: t.features["180"].get(k) for k in
                     ("buy_count", "sell_count", "estimated_independent_buyers", "flow_ratio", "whale_share")}
                    for t in engine.tokens.values() if engine.trade_status(t) == "CURRENT"
                ][:5],
                "elapsed_seconds": round(elapsed, 2),
                "configured_hot_limit": max_deep,
                "launches": launch_count,
                "opportunity_counts": snap["opportunities"]["counts"],
                "opportunity_evidence_grades": {
                    grade: sum(o["evidence_grade"] == grade for o in snap["opportunities"]["items"])
                    for grade in sorted({o["evidence_grade"] for o in snap["opportunities"]["items"]})
                },
                "opportunity_trade_unavailable": sum(
                    o["trade_evidence"] == "UNAVAILABLE" for o in snap["opportunities"]["items"]
                ),
                "opportunity_signals": snap["opportunities"]["signals_this_session"],
                "opportunity_outcomes": snap["opportunities"]["outcomes_this_session"],
                "curve_account_attempts": curve_attempts,
                "successful_curve_observations": successes,
                "rpc_requests": engine.rpc.health["requests"],
                "rpc_requests_per_second": round(engine.rpc.health["requests"] / elapsed, 4),
                "active_candidates": len(engine.tokens),
                "deep_candidates": len(engine.deep_mints()),
                "rss_mb": snap["health"]["rss_mb"],
                "cpu_pct": snap["health"]["cpu_pct"],
                "db_mb": snap["health"]["db_mb"],
                "db_growth_mb_per_hour": round(
                    (engine.db.size() - initial_db_bytes) / 1024**2 * 3600 / elapsed, 2
                ),
                "adaptive_backoff_changes": pressure_changes,
                "peak_samples": peaks,
                "background_candidates": snap["health"]["background_candidates"],
                "background_candidates_waiting": snap["health"]["background_candidates_waiting"],
                "oldest_background_poll_age": snap["health"]["oldest_background_poll_age"],
                "background_backoff_until": snap["health"]["background_backoff_until"],
                **engine.curve_metrics,
                **engine.expiry_metrics,
                "peak_expiry_deferred_for_poll": peak_expiry_deferred,
                "curve_accounts_per_http_request": round(
                    engine.curve_metrics["curve_accounts_checked"]
                    / max(1, engine.curve_metrics["curve_http_requests"]),
                    2,
                ),
                "curve_events_by_tier": curve_events,
                "background_mints_observed": len(background_observations),
                "background_mints_revisited": sum(v > 1 for v in background_observations.values()),
                **scan_counts,
                "queue_size": len(engine.queue.heap),
                "dropped_events": engine.queue.dropped,
                "entry_candidates": sum(t.state.value == "ENTRY_CANDIDATE" for t in engine.tokens.values()),
                "discovery_status": snap["health"]["discovery_status"],
                "duplicate_discoveries": engine.duplicate_discoveries,
                "providers": snap["health"]["providers"],
                "observed_states": sorted(states),
                "curve_progress": [
                    {
                        "mint": t.mint,
                        "progress": t.curve_progress,
                        "peak": t.curve_peak_progress,
                        "state": t.state.value,
                    }
                    for t in engine.tokens.values()
                    if t.curve_progress is not None
                ],
                "additional_rpc_requests_for_101_snapshots": companion_view_requests,
                "companion_actions": {
                    action: sum(t["companion"]["action"] == action for t in snap["tokens"])
                    for action in ["ENTRY_CANDIDATE", "WAIT", "REJECT", "TOO_LATE"]
                },
                "companion_high_attention_waits": sum(
                    t["companion"]["action"] == "WAIT" and t["companion"]["attention"] == "HIGH"
                    for t in snap["tokens"]
                ),
                "companion_trade_unavailable": all(
                    t["companion"]["trade_evidence"] == "UNAVAILABLE" for t in snap["tokens"]
                ),
                "trade_subscriptions": len(engine.pump.subscribed),
                "paper_cash": engine.paper.state["cash"],
            }
            Path("data/observe-smoke.json").write_text(json.dumps(report, indent=2))
            print(json.dumps(report, indent=2))
        finally:
            await engine.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=int, default=65)
    parser.add_argument(
        "--max-deep",
        type=int,
        default=25,
        choices=range(1, 26),
        help="Isolated probe hot limit; application defaults remain unchanged",
    )
    args = parser.parse_args()
    if not 1 <= args.seconds <= 3600:
        parser.error("--seconds must be between 1 and 3600")
    asyncio.run(main(args.seconds, args.max_deep))
