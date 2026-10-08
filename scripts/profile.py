"""Reproducible bounded monitoring load benchmark; no fabricated measurements."""

import argparse
import json
import platform
import statistics
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.config import Settings
from backend.app.domain import MarketEvent
from backend.app.engine import RadarEngine

parser = argparse.ArgumentParser()
parser.add_argument("--events", type=int, default=5000)
args = parser.parse_args()
with tempfile.TemporaryDirectory() as directory:
    engine = RadarEngine(Settings(mode="DEMO"), Path(directory) / "profile.db")
    baseline = engine.resources.sample()
    started = time.perf_counter()
    cpu = engine.resources.process.cpu_times()
    latencies = []
    for i in range(250):
        event = MarketEvent(mint=f"SIM{i}", ts=1000, source="DEMO", kind="create", event_id=f"create{i}")
        engine.process(event)
    max_queue = 0
    for i in range(args.events):
        tick = i // 25
        mint = f"SIM{i % 25}"
        event = MarketEvent(
            mint=mint,
            ts=1001 + tick,
            source="DEMO",
            kind="trade",
            event_id=f"trade{i}",
            wallet=f"w{i % 73}",
            side="buy" if i % 5 else "sell",
            volume=(i % 11) + 1,
            currency="USD",
            price=0.001 * (1 + tick * 0.001),
            liquidity=25000,
        )
        before = time.perf_counter()
        engine.submit(event)
        max_queue = max(max_queue, len(engine.queue.heap))
        for e in engine.queue.drain():
            engine.process(e)
        latencies.append((time.perf_counter() - before) * 1000)
    elapsed = time.perf_counter() - started
    for i in range(2500):
        engine.submit(
            MarketEvent(mint=f"SIM{i % 25}", ts=2000, source="DEMO", kind="trade", event_id=f"burst{i}")
        )
    overload = {
        "submitted": 2500,
        "queue_size": len(engine.queue.heap),
        "queue_limit": engine.queue.maximum,
        "dropped_events": engine.queue.dropped,
    }
    final = engine.resources.sample()
    cpu_after = engine.resources.process.cpu_times()
    result = {
        "environment": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "logical_cpus": __import__("os").cpu_count(),
        },
        "events": args.events,
        "candidate_count": len(engine.tokens),
        "deep_limit": engine.settings.max_deep,
        "idle_rss_mb": baseline["rss_mb"],
        "load_rss_mb": final["rss_mb"],
        "cpu_seconds": round(cpu_after.user + cpu_after.system - cpu.user - cpu.system, 3),
        "elapsed_seconds": round(elapsed, 3),
        "events_per_second": round(args.events / elapsed, 1),
        "median_event_latency_ms": round(statistics.median(latencies), 3),
        "p95_event_latency_ms": round(sorted(latencies)[int(len(latencies) * 0.95)], 3),
        "max_queue": max_queue,
        "overload": overload,
        "db_mb": final["db_mb"],
        "processed": engine.processed,
        "notes": "Synthetic synchronous ingestion including indexed SQLite journal writes; not network latency. No remote calls.",
    }
    Path("data/performance.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    engine.db.engine.dispose()
