"""Short real-mode pipeline probe in an isolated database; free streams only."""

import asyncio
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.config import Settings
from backend.app.engine import RadarEngine


async def main():
    with tempfile.TemporaryDirectory() as directory:
        engine = RadarEngine(Settings(mode="OBSERVE", max_candidates=50), Path(directory) / "observe.db")
        await engine.start()
        try:
            await asyncio.sleep(25)
            snapshot = engine.snapshot()
            events = engine.db.rows("event", limit=100)
            result = {
                "mode": snapshot["mode"],
                "simulated": snapshot["simulated"],
                "candidate_count": len(snapshot["tokens"]),
                "processed_events": engine.processed,
                "pump_connected": engine.pump.health["connected"],
                "sources": sorted({r["event"]["source"] for r in events}),
                "decisions": sorted({t["decision"]["decision"] for t in snapshot["tokens"]}),
                "paper_cash": engine.paper.state["cash"],
                "paid_stream_enabled": False,
            }
            Path("data/observe-verification.json").write_text(json.dumps(result, indent=2))
            print(json.dumps(result, indent=2))
        finally:
            await engine.stop()


asyncio.run(main())
