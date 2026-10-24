"""Bounded synthetic consumer benchmark. No providers, cohort, or trading."""
import asyncio
import json
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.config import Settings
from backend.app.domain import MarketEvent
from backend.app.engine import RadarEngine
from backend.app.early_edge_runtime import attach_observer
from backend.app.early_edge import manifest
from scripts.early_edge_diagnostic import DryObserver


async def benchmark():
    with tempfile.TemporaryDirectory(prefix="crispy-synthetic-benchmark-") as directory:
        settings = Settings(mode="OBSERVE")
        engine = RadarEngine(settings, Path(directory) / "synthetic.db", offline=False)
        observer = DryObserver(settings, manifest(settings, draft=True))
        detach = attach_observer(engine, observer)
        for i in range(10):
            engine.process(MarketEvent(event_id=f"create:{i}", mint=f"synthetic:{i}",
                ts=time.time(), source="SYNTHETIC", kind="create"))
        started = time.perf_counter()

        async def producer():
            for i in range(500):
                engine.submit(MarketEvent(event_id=f"trade:{i}", mint=f"synthetic:{i % 10}",
                    ts=time.time(), source="Solana WSS", kind="trade", side="buy" if i % 2 else "sell",
                    volume=1, currency="SOL"))
                await asyncio.sleep(max(0, started + (i + 1) * .02 - time.perf_counter()))

        producer_task = asyncio.create_task(producer())
        while not producer_task.done() or engine.queue.heap:
            await engine.drain_events()
            await asyncio.sleep(.005)
        await producer_task
        result = dict(synthetic=True, network_requests=engine.rpc.health["requests"] + engine.dex.health["requests"], cohort_created=False,
            elapsed=time.perf_counter() - started, target_arrival_rate=50,
            actual_processed=engine.trade_observations, queue=engine.queue.snapshot(),
            accounting=engine.accounting.snapshot(engine.queue), bytes=engine.db.size())
        assert not observer.failed
        detach()
        await engine.stop()
        return result


if __name__ == "__main__":
    print(json.dumps(asyncio.run(benchmark()), indent=2))
