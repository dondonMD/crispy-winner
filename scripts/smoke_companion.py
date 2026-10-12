"""Offline bounded DEMO companion verification; no real evidence or paper fills."""

import asyncio
import json
from pathlib import Path
import sys
import tempfile
import time
import psutil

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.config import Settings  # noqa: E402
from backend.app.engine import RadarEngine  # noqa: E402


async def main():
    with tempfile.TemporaryDirectory() as directory:
        engine = RadarEngine(Settings(mode="DEMO"), Path(directory) / "demo.db")
        await engine.start()
        try:
            await asyncio.sleep(5)
            snap = engine.snapshot()
            started = time.perf_counter()
            for _ in range(100):
                engine.snapshot()
            report = {
                "mode": snap["mode"],
                "simulated": snap["simulated"],
                "scanner_candidates": len(snap["tokens"]),
                "isolated_example_actions": [t["companion"]["action"] for t in snap["companion_examples"]],
                "paper_cash": snap["paper"]["cash"],
                "rss_mb": round(psutil.Process().memory_info().rss / 1024**2, 1),
                "mean_snapshot_ms": round((time.perf_counter() - started) * 10, 3),
                "provider_requests": engine.rpc.health["requests"],
                "dropped_events": engine.queue.dropped,
            }
            assert set(report["isolated_example_actions"]) == {
                "ENTRY_CANDIDATE",
                "WAIT",
                "REJECT",
                "TOO_LATE",
            }
            assert report["paper_cash"] == 20 and report["provider_requests"] == 0
            Path("data/companion-demo-smoke.json").write_text(json.dumps(report, indent=2))
            print(json.dumps(report, indent=2))
        finally:
            await engine.stop()


if __name__ == "__main__":
    asyncio.run(main())
