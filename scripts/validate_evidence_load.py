"""Synthetic 250-candidate sustained consumer validation; no live network/cohort."""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any
import time

import httpx
import psutil

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.config import Settings
from backend.app.domain import MarketEvent
from backend.app.early_edge import manifest
from backend.app.early_edge_runtime import attach_observer
from backend.app.engine import RadarEngine
from scripts.early_edge_diagnostic import DryObserver


def outstanding(engine):
    return bool(engine.queue.heap or any(engine.queue.in_processing.values()) or engine.recovery.pending)


def percentile(values, fraction):
    values = sorted(values)
    return values[min(len(values) - 1, int((len(values) - 1) * fraction))] if values else None


async def validate(seconds, rate, recovery_rate, warm_events, output):
    # scripts/profile.py must not shadow Python's profiling module in CLI mode.
    script_directory = str(Path(__file__).resolve().parent)
    if script_directory in sys.path:
        sys.path.remove(script_directory)
    import cProfile
    import pstats

    settings = Settings(mode="OBSERVE")
    source = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    process = psutil.Process()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="synthetic-capacity-only-") as directory:
        engine = RadarEngine(settings, Path(directory) / "synthetic.db", offline=False)
        mock_requests = 0

        async def transport(request):
            nonlocal mock_requests
            mock_requests += 1
            body = json.loads(request.content)
            await asyncio.sleep(.15)
            if body["method"] == "getTransaction":
                result: Any = dict(slot=123, version="legacy", meta=dict(err=None, innerInstructions=[]),
                    transaction=dict(signatures=[body["params"][0]], message=dict(
                        accountKeys=["11111111111111111111111111111111"], instructions=[])))
            else:
                result = 123
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": result})

        await engine.rpc.client.aclose()
        engine.rpc.client = httpx.AsyncClient(transport=httpx.MockTransport(transport))
        engine.rpc.url = "https://synthetic.invalid"
        before = time.time()
        for i in range(settings.max_candidates):
            mint = f"synthetic:{i}"
            engine.process(MarketEvent(event_id=f"create:{i}", mint=mint, ts=time.time(),
                source="SYNTHETIC", kind="create"))
            for j in range(warm_events):
                # Initial synthetic histories are inputs, not acquired observations.
                at = before - 180 + j * 180 / max(1, warm_events)
                engine.tokens[mint].events.append(MarketEvent(event_id=f"warm:{i}:{j}", mint=mint,
                    ts=at, source="SYNTHETIC", kind="market" if j % 10 == 0 else "trade",
                    side="buy" if j % 3 else "sell", wallet=f"synthetic-wallet:{j % 64}",
                    volume=.001 + j % 5 / 1000, currency="SOL",
                    price=1 + j * .0001 * (1 + i / 250) if j % 10 == 0 else None))
        observer = DryObserver(settings, manifest(settings, draft=True))
        detach = attach_observer(engine, observer)
        profiler = cProfile.Profile()
        profiler.enable()
        for token in engine.tokens.values():
            engine.analyse(token, time.time())
        engine.intelligence.refresh(time.time(), force=True)
        profiler.disable()
        with output.with_suffix(".profile.txt").open("x") as file:
            pstats.Stats(profiler, stream=file).sort_stats("cumulative").print_stats(30)

        stages = {}
        for obj, name in ((engine, "analyse"), (engine.db, "add"), (engine.db, "reserve_event"),
                          (engine.intelligence, "refresh"), (engine.collector, "observe")):
            original = getattr(obj, name)
            key = type(obj).__name__ + "." + name
            stages[key] = dict(calls=0, seconds=0., maximum=0.)

            def measured(*args, _original=original, _key=key, **kwargs):
                started = time.perf_counter()
                try:
                    return _original(*args, **kwargs)
                finally:
                    elapsed = time.perf_counter() - started
                    row = stages[_key]
                    row["calls"] += 1
                    row["seconds"] += elapsed
                    row["maximum"] = max(row["maximum"], elapsed)

            setattr(obj, name, measured)
        app_ages, durations = [], []  # Hard bounded by 600s * 100 events/s.
        original_process = engine.process

        def processed(event, now=None, **kwargs):
            start = time.perf_counter()
            if kwargs.get("queued") and event.kind == "trade":
                app_ages.append(time.time() - event.ts)
            try:
                return original_process(event, now, **kwargs)
            finally:
                if kwargs.get("queued") and event.kind == "trade":
                    durations.append(time.perf_counter() - start)

        setattr(engine, "process", processed)
        cpu_start = sum(process.cpu_times()[:2])
        started, wall = time.perf_counter(), time.time()
        engine.accounting.last_tick = wall
        engine.running = True
        engine.tasks = [asyncio.create_task(engine.run_loop(), name="monitor"),
                        asyncio.create_task(engine.recovery.run(), name="synthetic-recovery")]
        stop = asyncio.Event()
        monitoring = 0

        async def recoveries():
            for i in range(int(seconds * recovery_rate)):
                await asyncio.sleep(max(0, started + i / recovery_rate - time.perf_counter()))
                engine.recovery.submit(f"synthetic-signature:{i}", 123, time.time())

        async def monitor_rpc():
            nonlocal monitoring
            while not stop.is_set():
                await engine.rpc.rpc("getSlot", [])
                monitoring += 1
                await asyncio.sleep(5)

        async def producer():
            for i in range(int(seconds * rate)):
                await asyncio.sleep(max(0, started + i / rate - time.perf_counter()))
                engine.submit(MarketEvent(event_id=f"trade:{i}", mint=f"synthetic:{i % 250}",
                    ts=wall + i / rate, source="Solana WSS", kind="trade", side="buy" if i % 3 else "sell",
                    wallet=f"synthetic-wallet:{i % 64}", volume=.001 + i % 5 / 1000, currency="SOL"))

        inputs = [asyncio.create_task(producer()), asyncio.create_task(recoveries()),
                  asyncio.create_task(monitor_rpc())]
        samples = []
        try:
            while time.perf_counter() - started < seconds:
                samples.append(dict(at=time.perf_counter() - started, rss_mb=process.memory_info().rss / 1048576,
                    cpu=process.cpu_percent(), depth=len(engine.queue.heap), active=len(engine.tokens)))
                if not engine.running or observer.failed:
                    break
                await asyncio.sleep(1)
            await inputs[0]
            await inputs[1]
            deadline = time.perf_counter() + settings.max_data_age_seconds
            while outstanding(engine) and time.perf_counter() < deadline:
                await asyncio.sleep(.1)
            pre_stop = dict(accounting=engine.accounting.snapshot(engine.queue),
                            recovery=engine.recovery.snapshot(), queue=engine.queue.snapshot())
        finally:
            stop.set()
            for task in inputs:
                task.cancel()
            await asyncio.gather(*inputs, return_exceptions=True)
            detach()
            await engine.stop()
        elapsed = time.perf_counter() - started
        result = dict(synthetic=True, live_network_requests=0, mock_http_requests=mock_requests,
            cohort_created=False, source_sha=source, harness_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), configured_candidates=settings.max_candidates,
            configured_max_events=settings.max_events, queue_capacity=settings.queue_size,
            configured_freshness=settings.max_data_age_seconds, declared_seconds=seconds, elapsed_seconds=elapsed,
            target_trade_rate=rate, recovery_arrival_rate=recovery_rate, warm_events_per_token=warm_events,
            active_min=min(s["active"] for s in samples), active_max=max(s["active"] for s in samples),
            peak_rss_mb=max(s["rss_mb"] for s in samples), peak_cpu=max(s["cpu"] for s in samples),
            mean_cpu=100 * (sum(process.cpu_times()[:2]) - cpu_start) / elapsed,
            processed_trades=engine.trade_observations, pre_stop=pre_stop,
            final_accounting=engine.accounting.snapshot(engine.queue), final_recovery=engine.recovery.snapshot(),
            continuity=engine.trade_continuity, monitoring_standin_requests=monitoring, stages=stages,
            trade_application_age=dict(p50=percentile(app_ages,.5), p95=percentile(app_ages,.95),
                                       p99=percentile(app_ages,.99), maximum=max(app_ages,default=0)),
            trade_processing_seconds=dict(p50=percentile(durations,.5), p95=percentile(durations,.95),
                p99=percentile(durations,.99), maximum=max(durations,default=0)), samples=samples,
            limitation="Synthetic normalized events; no decoder/network/real CURRENT or prospective outcomes. CPU excludes setup; input warm history is synthetic.")
        encoded = json.dumps(result, sort_keys=True)
        result["sha256"] = hashlib.sha256(encoded.encode()).hexdigest()
        with output.open("x") as file:
            json.dump(result, file, indent=2)
        return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=int, default=210)
    parser.add_argument("--rate", type=int, default=15)
    parser.add_argument("--recovery-rate", type=float, default=.7)
    parser.add_argument("--warm-events", type=int, default=200)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not (1 <= args.seconds <= 600 and 1 <= args.rate <= 100 and 0 <= args.recovery_rate <= 2
            and 0 <= args.warm_events <= 500):
        parser.error("Bounded synthetic load required")
    report = asyncio.run(validate(args.seconds, args.rate, args.recovery_rate, args.warm_events, args.output))
    print(json.dumps({k: report[k] for k in ("source_sha", "elapsed_seconds", "processed_trades",
                     "peak_rss_mb", "mean_cpu", "trade_application_age")}, indent=2))
