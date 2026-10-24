"""Synthetic 250-candidate sustained consumer validation; no live network/cohort."""
import argparse
from contextlib import nullcontext, closing
from collections import Counter, deque
import os
import sqlite3
import asyncio
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
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


def scheduled_offset(index, rate, bursts=False):
    if not bursts:
        return index / rate
    # Every ten-second block has the same total arrivals, including a one-second 2x pulse.
    block, within = divmod(index, rate * 10)
    pulse = rate * 2
    return block * 10 + (within / pulse if within < pulse else 1 + (within - pulse) * 9 / (rate * 8))


def storage_bytes(path):
    return {name: target.stat().st_size if target.exists() else 0 for name, target in (
        ("db", path), ("wal", Path(str(path) + "-wal")), ("shm", Path(str(path) + "-shm")))}


def seal_report(result):
    # Normalize integer dictionary keys before hashing so JSON reload is reproducible.
    normalized = json.loads(json.dumps(result, allow_nan=False))
    encoded = json.dumps(normalized, sort_keys=True, allow_nan=False)
    normalized["sha256"] = hashlib.sha256(encoded.encode()).hexdigest()
    return normalized


def install_shutdown_watchdog(loop, interval=.05, ticks=100):
    """Bounded timer service during REAL Runner cleanup; never marks a worker done.

    Some restricted runtimes fail to wake select on executor-join callbacks. Timers
    keep the loop progressing, but a genuinely stuck worker still blocks/fails.
    Activated only after validation, so it cannot influence measured ingestion.
    """
    state = dict(ticks=0, maximum_ticks=ticks, interval_seconds=interval)
    def wake():
        state["ticks"] += 1
        if state["ticks"] < ticks and not loop.is_closed():
            loop.call_later(interval, wake)
    loop.call_later(interval, wake)
    return state


async def validate(seconds, rate, recovery_rate, warm_events, output, profile_runtime=False, endurance=False, cleanup_state=None, diagnose_repro=False):
    # scripts/profile.py must not shadow Python's profiling module in CLI mode.
    script_directory = str(Path(__file__).resolve().parent)
    if script_directory in sys.path:
        sys.path.remove(script_directory)
    import cProfile
    import pstats

    if os.getenv("RADAR_COHORT") or os.getenv("PUMPPORTAL_ENABLED", "false").lower() == "true":
        raise ValueError("Synthetic diagnostic forbids cohort/PumpPortal selection")
    settings = Settings(mode="OBSERVE")
    source = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    process = psutil.Process()
    from scripts.evidence_repro import ReproTrace, digest
    trace = ReproTrace() if diagnose_repro else None
    setup_started = time.perf_counter()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() or output.with_suffix(".profile.txt").exists():
        raise FileExistsError("Diagnostic output already exists")
    run_directory = output.with_suffix(".run")
    if endurance:
        run_directory.mkdir(exist_ok=False)
    directory_context = (nullcontext(str(run_directory)) if endurance else
                         tempfile.TemporaryDirectory(prefix="synthetic-capacity-only-"))
    with directory_context as directory:
        engine = RadarEngine(settings, Path(directory) / "synthetic.db", offline=False)
        mock_requests = 0
        mock_plan: deque = deque(maxlen=8192)

        async def transport(request):
            nonlocal mock_requests
            mock_requests += 1
            body = json.loads(request.content)
            delay = (1.5 if mock_requests % 5 == 0 else .35) if endurance and body["method"] != "getTransaction" else .15
            if trace is not None:
                mock_plan.append(dict(method=body["method"], delay=delay, request_ordinal=mock_requests,
                                      at=time.perf_counter()-trace.epoch if trace.epoch is not None else None))
            await asyncio.sleep(delay)
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

        import backend.app.engine as engine_module
        import backend.app.features as feature_module
        from sqlalchemy import event as sql_event
        sql_counts: Counter = Counter()
        commit_samples: deque[float] = deque(maxlen=8192)
        commit_totals = dict(count=0, seconds=0., maximum=0.)
        commit_scope = threading.local()
        original_commit = engine.db.engine.dialect.do_commit
        def timed_commit(connection):
            start = time.perf_counter()
            try:
                return original_commit(connection)
            finally:
                duration = time.perf_counter() - start
                if trace is not None:
                    trace.record("sqlite.commit", start, duration, role=getattr(commit_scope, "role", "unattributed"))
                commit_samples.append(duration)
                commit_totals["count"] += 1
                commit_totals["seconds"] += duration
                commit_totals["maximum"] = max(commit_totals["maximum"], duration)
        setattr(engine.db.engine.dialect, "do_commit", timed_commit)
        def sql_count(conn, cursor, statement, *args):
            sql = statement.upper()
            category = next((name for name in ("PRAGMA FREELIST_COUNT", "PRAGMA PAGE_SIZE",
                "INSERT INTO EVENT_IDENTITIES", "INSERT INTO RECORDS", "SELECT EVENT_IDENTITIES")
                if sql.startswith(name)), sql.split()[0])
            sql_counts[category] += 1
        sql_event.listen(engine.db.engine, "before_cursor_execute", sql_count)
        stages = {}
        restore_wrappers = []
        for obj, name in ((engine, "analyse"), (engine.db, "add"), (engine.db, "reserve_event"),
                          (engine.intelligence, "refresh"), (engine.collector, "observe"),
                          (engine.intelligence.research, "save_pending"), (engine, "checkpoint"),
                          (engine.db, "writable"), (engine.db, "context_reference"),
                          (engine.dedup, "accept"), (engine.intelligence, "observe"),
                          (observer, "observe"), (engine_module, "calculate_features"),
                          (feature_module, "window_features"),
                          *(((engine.db, "retention"), (engine_module, "evaluate"),
                             (engine.intelligence.research, "commit_outcomes")) if trace is not None else ())):
            original = getattr(obj, name)
            key = type(obj).__name__ + "." + name
            stages[key] = dict(calls=0, seconds=0., maximum=0.)

            role = {"reserve_event": "event_identity", "checkpoint": "restore_checkpoint",
                    "save_pending": "pending_state", "retention": "retention",
                    "evaluate": "evaluation", "commit_outcomes": "outcome_batch"}.get(name)
            if obj is engine.db and name == "add":
                role = "record"

            def measured(*args, _original=original, _key=key, _role=role, **kwargs):
                started = time.perf_counter()
                previous = getattr(commit_scope, "role", "unattributed")
                if _role is not None:
                    commit_scope.role = ("raw_event" if args and args[0] == "event" else "other_record") if _role == "record" else _role
                try:
                    return _original(*args, **kwargs)
                finally:
                    commit_scope.role = previous
                    elapsed = time.perf_counter() - started
                    if trace is not None:
                        trace.record(_key, started, elapsed)
                    row = stages[_key]
                    row["calls"] += 1
                    row["seconds"] += elapsed
                    row["maximum"] = max(row["maximum"], elapsed)

            restore_wrappers.append((obj, name, original))
            setattr(obj, name, measured)
        admitted: dict[str, float] = {}
        queue_waits: list[float] = []
        producer_lags: list[float] = []
        app_ages: list[float] = []
        durable_ages: list[float] = []
        committed_bins: Counter = Counter()
        ready_bins: Counter = Counter()
        processing_bins: Counter = Counter()
        durations: list[float] = []  # Bounded by CLI: 1800s * 100 events/s.
        by_minute: dict[int, list[float]] = {}
        quote_stats: Counter = Counter()
        turnover_stats: Counter = Counter()
        db_path = engine.db.path
        original_process = engine.process

        def processed(event, now=None, **kwargs):
            start = time.perf_counter()
            if kwargs.get("queued") and event.kind == "trade":
                processing_bins[int((start - started) // 10)] += 1
                age = time.time() - event.ts
                app_ages.append(age)
                by_minute.setdefault(int((time.perf_counter() - started) // 60), []).append(age)
                arrival = admitted.pop(event.event_id, None)
                if arrival is not None:
                    queue_waits.append(time.perf_counter() - arrival)
            try:
                result = original_process(event, now, **kwargs)
                if result and kwargs.get("queued") and event.kind == "trade" and engine._event_persisted:
                    durable_ages.append(time.time() - event.ts)
                    committed_bins[int((time.perf_counter() - started) // 10)] += 1
                return result
            finally:
                if kwargs.get("queued") and event.kind == "trade":
                    durations.append(time.perf_counter() - start)

        setattr(engine, "process", processed)
        reproducibility: dict[str, Any] = {}
        if trace is not None:
            with engine.db.engine.connect() as conn:
                pragmas = {name: conn.exec_driver_sql("PRAGMA " + name).scalar() for name in
                           ["journal_mode", "synchronous", "busy_timeout", "wal_autocheckpoint", "page_size"]}
            # Hash only predetermined workload/config; no secret values are emitted.
            reproducibility = dict(settings_sha256=digest(settings.model_dump(mode="json")),
                workload_sha256=digest(dict(seconds=seconds, rate=rate, recovery_rate=recovery_rate,
                    warm_events=warm_events, candidates=settings.max_candidates, endurance=endurance,
                    trades=[(i, scheduled_offset(i, rate, endurance), i % 250, i % 3,
                             i % 64, .001 + i % 5 / 1000) for i in range(int(seconds * rate))],
                    warm=[(j, -180 + j * 180 / max(1, warm_events), j % 10, j % 3)
                          for j in range(warm_events)])),
                setup_seconds=time.perf_counter() - setup_started, sqlite=pragmas,
                warm_anchor_age_seconds=time.time()-before,
                candidate_age_seconds=dict(minimum=min(time.time()-t.created for t in engine.tokens.values()),
                    maximum=max(time.time()-t.created for t in engine.tokens.values())),
                storage_at_start=storage_bytes(db_path),
                maintenance_offsets=dict(last_lab=engine.last_lab, last_maintenance=engine.last_maintenance))
        cpu_start = sum(process.cpu_times()[:2])
        started, wall = time.perf_counter(), time.time()
        if trace is not None:
            trace.start(started)
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
                await asyncio.sleep(max(0, started + scheduled_offset(i, rate, endurance) - time.perf_counter()))
                ready = time.perf_counter()
                admitted[f"trade:{i}"] = ready
                ready_bins[int((ready - started) // 10)] += 1
                offset = scheduled_offset(i, rate, endurance)
                producer_lags.append(time.time() - (wall + offset))
                # Always target the currently admitted set; turnover uses normal create admission.
                active = list(engine.tokens) if endurance else None
                mint = active[i % len(active)] if active else f"synthetic:{i % 250}"
                engine.submit(MarketEvent(event_id=f"trade:{i}", mint=mint,
                    ts=wall + offset, source="Solana WSS", kind="trade", side="buy" if i % 3 else "sell",
                    wallet=f"synthetic-wallet:{i % 64}", volume=.001 + i % 5 / 1000, currency="SOL"))

        async def turnover():
            for i in range(1, seconds // 60):
                await asyncio.sleep(max(0, started + i * 60 - time.perf_counter()))
                turnover_stats["submitted"] += 1
                accepted = engine.submit(MarketEvent(event_id=f"turnover:{i}",
                    mint=f"synthetic-new:{i}", ts=time.time(), source="SYNTHETIC", kind="create"))
                turnover_stats["accepted"] += bool(accepted)

        async def quote_provider_load():
            # Bounded delayed shared-RPC workload, not an executable quote or research outcome.
            for i in range((seconds + 19) // 30):
                await asyncio.sleep(max(0, started + i * 30 + 10 - time.perf_counter()))
                deadline = wall + i * 30 + 20
                quote_stats["attempted"] += 1
                if time.time() >= deadline:
                    quote_stats["unavailable_deadline"] += 1
                    continue
                try:
                    await asyncio.wait_for(engine.rpc.rpc("getSlot", []), timeout=min(5, deadline - time.time()))
                    quote_stats["available_within_deadline" if time.time() <= deadline
                                else "unavailable_deadline"] += 1
                except asyncio.TimeoutError:
                    quote_stats["unavailable_timeout"] += 1
                except Exception:
                    quote_stats["unavailable_provider"] += 1

        inputs = [asyncio.create_task(producer()), asyncio.create_task(recoveries()),
                  asyncio.create_task(monitor_rpc())]
        if endurance:
            inputs.extend([asyncio.create_task(turnover()), asyncio.create_task(quote_provider_load())])
        samples = []
        if profile_runtime:
            profiler.clear()
            profiler.enable()
        try:
            while time.perf_counter() - started < seconds:
                samples.append(dict(at=time.perf_counter() - started, rss_mb=process.memory_info().rss / 1048576,
                    cpu=process.cpu_percent(), depth=len(engine.queue.heap), active=len(engine.tokens),
                    storage=storage_bytes(db_path) if endurance else None,
                    accounted=engine.accounting.snapshot(engine.queue) if endurance else None,
                    recovery=engine.recovery.snapshot() if endurance else None,
                    continuity=dict(engine.trade_continuity) if endurance else None))
                if endurance:
                    if trace is not None:
                        samples[-1]["environment"] = trace.sample()
                    # Freeze nested counters; later mutations must not rewrite sampled history.
                    samples[-1] = json.loads(json.dumps(samples[-1]))
                    progress = output.with_suffix(".progress.json")
                    temporary = progress.with_suffix(".tmp")
                    temporary.write_text(json.dumps(dict(synthetic=True, at=samples[-1]["at"],
                        source_sha=source, latest=samples[-1], total_samples=len(samples))))
                    temporary.replace(progress)
                if not engine.running or observer.failed:
                    break
                sample_due = time.perf_counter() + 1
                await asyncio.sleep(1)
                if trace is not None:
                    trace.sample_lag(sample_due)
            if not engine.running or observer.failed:
                # Stop producing after a genuine guard/failure; retain explicitly censored work.
                for task in inputs:
                    task.cancel()
                await asyncio.gather(*inputs, return_exceptions=True)
            else:
                await inputs[0]
                await inputs[1]
            if endurance and engine.running and not observer.failed:
                await asyncio.gather(*inputs[3:])
            deadline = time.perf_counter() + settings.max_data_age_seconds
            while outstanding(engine) and time.perf_counter() < deadline:
                await asyncio.sleep(.1)
            pre_stop = dict(accounting=engine.accounting.snapshot(engine.queue),
                            recovery=engine.recovery.snapshot(), queue=engine.queue.snapshot())
        finally:
            if profile_runtime:
                profiler.disable()
                with output.with_suffix(".runtime-profile.txt").open("x") as file:
                    pstats.Stats(profiler, stream=file).sort_stats("cumulative").print_stats(50)
            stop.set()
            for task in inputs:
                task.cancel()
            await asyncio.gather(*inputs, return_exceptions=True)
            detach()
            try:
                await engine.stop()
            finally:
                for obj, name, original in reversed(restore_wrappers):
                    setattr(obj, name, original)
                setattr(engine.db.engine.dialect, "do_commit", original_commit)
        elapsed = time.perf_counter() - started
        cpu_seconds = sum(process.cpu_times()[:2]) - cpu_start
        shutdown_storage = storage_bytes(db_path)
        restart = None
        if endurance:
            with closing(sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)) as connection:
                integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
                persisted_stop = json.loads(connection.execute(
                    "SELECT payload FROM evidence_runs WHERE session=?", (engine.session,)).fetchone()[0])
            restart_started = time.perf_counter()
            restart = dict(integrity=integrity, stopped_receipt=persisted_stop,
                           blocked_storage_guard=engine.storage_stopped)
            if not engine.storage_stopped:
                restarted = RadarEngine(settings, db_path, offline=True)
                restart.update(restored_candidates=len(restarted.tokens),
                    windows_empty=all(not t.events for t in restarted.tokens.values()),
                    security_requires_refresh=all(t.last_security == 0 for t in restarted.tokens.values()),
                    paper_cash=restarted.paper.state["cash"], positions=len(restarted.paper.state["positions"]))
                await restarted.stop()
            restart.update(elapsed_seconds=time.perf_counter() - restart_started,
                           storage_after_restart=storage_bytes(db_path))
        result = dict(synthetic=True, sql_counts=dict(sql_counts),
            sqlite_commit=dict(**commit_totals, sample_limit=8192,
                sampled_count=len(commit_samples), p50=percentile(commit_samples,.5),
                p95=percentile(commit_samples,.95), p99=percentile(commit_samples,.99)), endurance=endurance, storage_retained=endurance,
            storage_after_shutdown=shutdown_storage, storage_budget_bytes=engine.db.budget,
            per_minute_application_age={str(k): dict(count=len(v), p50=percentile(v,.5),
                p95=percentile(v,.95), p99=percentile(v,.99), maximum=max(v)) for k,v in by_minute.items()},
            quote_provider_standin=dict(quote_stats), turnover=dict(turnover_stats), restart=restart, live_network_requests=0, mock_http_requests=mock_requests,
            cohort_created=False, runtime_profiled=profile_runtime, source_sha=source, harness_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), configured_candidates=settings.max_candidates,
            configured_max_events=settings.max_events, queue_capacity=settings.queue_size,
            configured_freshness=settings.max_data_age_seconds, declared_seconds=seconds, elapsed_seconds=elapsed,
            target_trade_rate=rate, recovery_arrival_rate=recovery_rate, warm_events_per_token=warm_events,
            active_min=min(s["active"] for s in samples), active_max=max(s["active"] for s in samples),
            peak_rss_mb=max(s["rss_mb"] for s in samples), peak_cpu=max(s["cpu"] for s in samples),
            mean_cpu=100 * cpu_seconds / elapsed,
            processed_trades=engine.trade_observations, pre_stop=pre_stop,
            final_accounting=engine.accounting.snapshot(engine.queue), final_recovery=engine.recovery.snapshot(),
            persistence_reconciliation=engine.db.persistence_snapshot(),
            continuity=engine.trade_continuity, monitoring_standin_requests=monitoring, stages=stages,
            trade_application_age=dict(p50=percentile(app_ages,.5), p95=percentile(app_ages,.95),
                                       p99=percentile(app_ages,.99), maximum=max(app_ages,default=0)),
            durable_commits_per_10s=dict(committed_bins),
            trade_producer_ready_per_10s=dict(ready_bins),
            trade_processing_starts_per_10s=dict(processing_bins),
            trade_durable_completion_age=dict(count=len(durable_ages),
                p50=percentile(durable_ages,.5), p95=percentile(durable_ages,.95),
                p99=percentile(durable_ages,.99), maximum=max(durable_ages,default=0)),
            trade_queue_wait_seconds={k: percentile(queue_waits, f) for k, f in (("p50", .5), ("p95", .95), ("p99", .99), ("maximum", 1))},
            producer_schedule_lag_seconds={k: percentile(producer_lags, f) for k, f in (("p50", .5), ("p95", .95), ("p99", .99), ("maximum", 1))},
            trade_processing_seconds=dict(p50=percentile(durations,.5), p95=percentile(durations,.95),
                p99=percentile(durations,.99), maximum=max(durations,default=0)), samples=samples,
            limitation="Synthetic normalized events; no decoder/network/real CURRENT or prospective outcomes. CPU excludes setup; input warm history is synthetic.")
        if trace is not None:
            result["reproducibility"] = dict(**reproducibility, diagnostics=trace.result(), mock_request_plan=list(mock_plan),
                source_end_sha=subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
                settings_end_sha256=digest(settings.model_dump(mode="json")))
        result = seal_report(result)
        with output.open("x") as file:
            json.dump(result, file, indent=2)
        watchdog = install_shutdown_watchdog(asyncio.get_running_loop())
        if cleanup_state is not None:
            cleanup_state["watchdog"] = watchdog
        return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endurance", action="store_true", help="Opt-in synthetic bursts/turnover/delays, retained DB, <=1800s")
    parser.add_argument("--diagnose-repro", action="store_true", help="Bounded scheduling/environment diagnostics; no policy changes")
    parser.add_argument("--profile-runtime", action="store_true", help="Separate diagnostic; profiled latency is not comparable")
    parser.add_argument("--seconds", type=int, default=210)
    parser.add_argument("--rate", type=int, default=15)
    parser.add_argument("--recovery-rate", type=float, default=.7)
    parser.add_argument("--warm-events", type=int, default=200)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not (1 <= args.seconds <= (1800 if args.endurance else 600) and 1 <= args.rate <= 100 and 0 <= args.recovery_rate <= 2
            and 0 <= args.warm_events <= 500):
        parser.error("Bounded synthetic load required")
    import threading
    status_path = args.output.with_suffix(".process-status.json")
    if status_path.exists():
        parser.error("Process status already exists")
    cleanup: dict[str, Any] = {}
    cli_started = time.perf_counter()
    async def run_cli():
        try:
            return await validate(args.seconds, args.rate, args.recovery_rate, args.warm_events,
                                  args.output, args.profile_runtime, args.endurance, cleanup_state=cleanup, diagnose_repro=args.diagnose_repro)
        finally:
            cleanup["validation_returned_at"] = time.perf_counter()
            if "watchdog" not in cleanup:
                cleanup["watchdog"] = install_shutdown_watchdog(asyncio.get_running_loop())
    report = asyncio.run(run_cli())  # Still awaits/cancels tasks, asyncgens, and executor shutdown.
    remaining = [t.name for t in threading.enumerate() if t is not threading.main_thread()]
    status = dict(synthetic=True, runner_returned=True, remaining_thread_count=len(remaining),
                  clean_exit=len(remaining) == 0, watchdog=cleanup["watchdog"],
                  total_seconds=time.perf_counter() - cli_started,
                  cleanup_seconds=time.perf_counter() - cleanup["validation_returned_at"],
                  report_sha256=hashlib.sha256(args.output.read_bytes()).hexdigest())
    with status_path.open("x") as file:
        json.dump(status, file, indent=2)
    if remaining:
        raise RuntimeError("Diagnostic executor threads remain after Runner cleanup")
    print(json.dumps({k: report[k] for k in ("source_sha", "elapsed_seconds", "processed_trades",
                     "peak_rss_mb", "mean_cpu", "trade_application_age")}, indent=2))
