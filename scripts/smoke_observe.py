"""Short read-only free OBSERVE probe, isolated temporary DB; no paid subscriptions."""

import asyncio
import json
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.config import Settings
from backend.app.engine import RadarEngine


async def main():
    with tempfile.TemporaryDirectory() as directory:
        engine = RadarEngine(
            Settings(mode="OBSERVE", trade_stream_enabled=False), Path(directory) / "observe.db"
        )
        curve_attempts = 0
        successes = 0
        launch_count = 0
        states = set()
        original = engine.rpc.curve_progress_batch
        original_process = engine.process

        async def counted(mints, batch_size):
            nonlocal curve_attempts, successes
            curve_attempts += len(mints)
            reports = await original(mints, batch_size)
            successes += sum(r.get("curve_progress") is not None for r in reports.values())
            return reports

        def counted_process(event, now=None):
            nonlocal launch_count
            accepted = original_process(event, now)
            if accepted:
                launch_count += event.kind == "create"
                states.add(engine.tokens[event.mint].state.value)
            return accepted

        engine.rpc.curve_progress_batch = counted
        engine.process = counted_process
        start = time.monotonic()
        await engine.start()
        try:
            await asyncio.sleep(65)
            snap = engine.snapshot()
            elapsed = time.monotonic() - start
            report = {
                "elapsed_seconds": round(elapsed, 2),
                "launches": launch_count,
                "curve_account_attempts": curve_attempts,
                "successful_curve_observations": successes,
                "rpc_requests": engine.rpc.health["requests"],
                "rpc_requests_per_second": round(engine.rpc.health["requests"] / elapsed, 4),
                "active_candidates": len(engine.tokens),
                "deep_candidates": len(engine.deep_mints()),
                "rss_mb": snap["health"]["rss_mb"],
                "providers": snap["health"]["providers"],
                "observed_states": sorted(states),
                "curve_progress": [
                    {"mint": t.mint, "progress": t.curve_progress, "state": t.state.value}
                    for t in engine.tokens.values()
                    if t.curve_progress is not None
                ],
                "trade_subscriptions": len(engine.pump.subscribed),
                "paper_cash": engine.paper.state["cash"],
            }
            Path("data/observe-smoke.json").write_text(json.dumps(report, indent=2))
            print(json.dumps(report, indent=2))
        finally:
            await engine.stop()


if __name__ == "__main__":
    asyncio.run(main())
