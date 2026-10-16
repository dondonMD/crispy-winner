"""Isolated DEMO and 250-candidate computation verification; makes no network requests."""

import asyncio
from collections import deque
import json
from pathlib import Path
import sys
import tempfile
import time

import psutil
from solders.pubkey import Pubkey
from sqlalchemy import event

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.config import Settings
from backend.app.domain import Token, State
from backend.app.engine import RadarEngine
from backend.app.intelligence_demo import examples


async def main():
    with tempfile.TemporaryDirectory() as directory:
        engine = RadarEngine(Settings(), Path(directory) / "intelligence.db", offline=True)
        now = time.time()
        try:
            demo = examples(Settings(mode="DEMO"), engine.intelligence.cfg, now)
            assert [v["action"] for v in demo["opportunities"]] == [
                "EARLY_OPPORTUNITY",
                "DEVELOPING",
                "PULLBACK_WATCH",
                "TOO_EXTENDED",
                "AVOID",
            ]
            assert [v["exit"]["action"] for v in demo["positions"]] == [
                "HEALTHY",
                "PROTECT_PROFIT",
                "EXIT_RISK",
                "THESIS_INVALIDATED",
            ]
            baseline = psutil.Process().memory_info().rss / 1048576
            for i in range(250):
                t = Token(str(Pubkey.new_unique()), f"Synthetic load {i}", "LOAD", now - 960)
                t.state = State.WATCHING
                t.curve_history = deque([(now - (31 - j) * 30, 10 + j * 2) for j in range(32)], maxlen=32)
                t.last_curve = now
                t.curve_progress = t.curve_peak_progress = 72
                t.last_event = t.last_curve_attempt = now
                engine.tokens[t.mint] = t
            # Warm the independent computation, then measure cached SSE and pure refresh work.
            engine.intelligence.refresh(now, force=True)
            started = time.perf_counter()
            for _ in range(20):
                engine.intelligence.refresh(now, force=True)
            projection_ms = (time.perf_counter() - started) * 1000 / 20
            selects = []

            def count_select(conn, cursor, statement, parameters, context, many):
                if statement.lstrip().upper().startswith("SELECT"):
                    selects.append(1)

            event.listen(engine.db.engine, "before_cursor_execute", count_select)
            started = time.perf_counter()
            for _ in range(20):
                engine.snapshot()
            snapshot_ms = (time.perf_counter() - started) * 1000 / 20
            event.remove(engine.db.engine, "before_cursor_execute", count_select)
            rss = psutil.Process().memory_info().rss / 1048576
            report = {
                "synthetic_only": True,
                "demo_opportunity_actions": [v["action"] for v in demo["opportunities"]],
                "demo_exit_actions": [v["exit"]["action"] for v in demo["positions"]],
                "active": len(engine.tokens),
                "hot": len(engine.deep_mints()),
                "history_points": sum(len(t.curve_history) for t in engine.tokens.values()),
                "baseline_rss_mb": round(baseline, 2),
                "loaded_rss_mb": round(rss, 2),
                "delta_rss_mb": round(rss - baseline, 2),
                "projection_250_ms": round(projection_ms, 2),
                "snapshot_250_ms": round(snapshot_ms, 2),
                "snapshot_selects": len(selects),
                "rpc_requests": engine.rpc.health["requests"],
                "research_signals": len(engine.db.rows("opportunity_signal")),
                "paper_cash": engine.paper.state["cash"],
            }
            assert rss < 500 and len(engine.deep_mints()) == 25
            assert not selects and report["rpc_requests"] == report["research_signals"] == 0
            Path("data/intelligence-verification.json").write_text(json.dumps(report, indent=2))
            print(json.dumps(report, indent=2))
        finally:
            await engine.stop()


if __name__ == "__main__":
    asyncio.run(main())
