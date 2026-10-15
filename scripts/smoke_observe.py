"""Short read-only free OBSERVE probe, isolated temporary DB; no paid subscriptions."""

import asyncio
import argparse
from collections import OrderedDict
import json
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
        states = set()
        background_observations: OrderedDict[str, int] = OrderedDict()
        curve_events = {"hot": 0, "background": 0}
        scan_counts = {"security_attempts": 0, "security_completed": 0, "security_outside_hot": 0}
        peaks = {"rss_mb": 0.0, "queue_size": 0, "active": 0, "hot": 0, "background": 0}
        pressure_changes = []
        previous_level = -1
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
        start = time.monotonic()
        await engine.start()
        try:
            while time.monotonic() - start < seconds:
                await asyncio.sleep(min(1, max(0, seconds - (time.monotonic() - start))))
                level = engine.rpc.health["backoff_level"]
                if level != previous_level:
                    pressure_changes.append({"seconds": round(time.monotonic() - start, 1), "level": level})
                    previous_level = level
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
            report = {
                "elapsed_seconds": round(elapsed, 2),
                "configured_hot_limit": max_deep,
                "launches": launch_count,
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
    if not 1 <= args.seconds <= 600:
        parser.error("--seconds must be between 1 and 600")
    asyncio.run(main(args.seconds, args.max_deep))
