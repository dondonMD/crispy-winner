"""Opt-in 120-second operational discovery qualification; default prints plan, never connects."""

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import signal_quality_pilot as pilot  # noqa: E402

SECONDS = 120
CORRECTED_PARENT = "b3b346b168878526bd8b41574b12e780a07f669e"


def plan():
    return dict(
        purpose="OPERATIONAL_DISCOVERY_QUALIFICATION_ONLY",
        duration_seconds=SECONDS,
        mode="OBSERVE",
        outcome_measurements=False,
        prospective_cohort=False,
        PRE_COHORT_READY="NO",
        phase4_authorized=False,
        limits=dict(
            rss_mb=500,
            combined_output_mb=640,
            queue_stop=800,
            ledger_soft_records=12000,
            ledger_hard_bytes=64 * 1048576,
        ),
    )


class SmokeRecorder(pilot.Recorder):
    """Reuse corrected post-process discovery accounting, never schedule study measurements."""

    def __init__(self, ledger, start, engine):
        super().__init__(ledger, start)
        self.engine = engine
        self.admitted = set()

    def discovery(self, event, accepted, reason, now):
        from backend.app.discovery import PUMP_PROGRAM

        if event.kind != "create":
            return
        if (
            event.source != "Onchain Pump"
            or event.evidence.get("program") != PUMP_PROGRAM
            or event.evidence.get("commitment") != "confirmed"
        ):
            self.counts["noncanonical_create_observations"] += 1
            self.stop_reason = "NONCANONICAL_CREATE_SOURCE"
            return
        super().discovery(event, accepted, reason, now)
        if accepted and not self.stop_reason:
            self.admitted.add(event.mint)  # Parent bounds all discovered mints at 1,000.
            self.counts["live_persisted_on_return"] += bool(self.engine._event_persisted)

    def refresh(self, engine, now):
        if self.stop_reason:
            return
        for mint in sorted(self.admitted):
            assessment = engine.intelligence.results.get(mint, {}).get("early_market")
            if not assessment:
                continue
            label = assessment.get("classification")
            if label not in pilot.CLASSES or self.last.get(mint) == label:
                continue
            if (
                self.emit(
                    "TRANSITION",
                    dict(
                        mint=mint,
                        recorded_at=now,
                        classification=label,
                        measurement_scheduled=False,
                        assessment=assessment,
                    ),
                )
                is None
            ):
                return
            self.last[mint] = label
            self.counts["transitions"] += 1


def preflight(expected, output):
    """No engine construction or output writes before source/configuration verification."""
    from dotenv import load_dotenv
    from backend.app.config import Settings, load_settings
    import yaml

    load_dotenv(ROOT / ".env")
    source = pilot.verify_source(expected)
    # In addition to the pilot ancestry guard, require the published queued-wrapper repair.
    pilot.subprocess.run(
        ["git", "merge-base", "--is-ancestor", CORRECTED_PARENT, expected],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    if "scripts/qualify_live_discovery.py" not in source["files"]:
        raise pilot.PilotRefusal("Qualification script must be published tracked source")
    if any(v for k, v in os.environ.items() if "COHORT" in k.upper()) or os.getenv(
        "PUMPPORTAL_ENABLED", "false"
    ).lower() not in ("false", "0", ""):
        raise pilot.PilotRefusal("Cohort/PumpPortal environment forbidden")
    if not (
        (os.getenv("SOLANA_RPC_HTTP_URL") and os.getenv("SOLANA_RPC_WSS_URL")) or os.getenv("HELIUS_API_KEY")
    ):
        raise pilot.PilotRefusal("Existing standard HTTP/WSS configuration unavailable")
    settings = load_settings()
    frozen = Settings(
        **{**yaml.safe_load(pilot.git("show", f"{pilot.BASE}:config/conservative.yaml")), "mode": "OBSERVE"}
    )
    if settings.mode != "OBSERVE" or settings.model_dump() != frozen.model_dump():
        raise pilot.PilotRefusal("Require unchanged conservative OBSERVE configuration")
    output = Path(output).resolve()
    if output.parent != (ROOT / "data/early_edge").resolve() or output.exists():
        raise pilot.PilotRefusal("Require new isolated output directory")
    return source, settings, output


def check_processes():
    import psutil

    for proc in psutil.process_iter(["pid", "cmdline"]):
        if proc.info["pid"] == os.getpid():
            continue
        if any(
            Path(a).name
            in (
                "uvicorn",
                "smoke_observe.py",
                "verify_observe.py",
                "signal_quality_pilot.py",
                "qualify_live_discovery.py",
            )
            or a == "backend.app.main:app"
            for a in (proc.info["cmdline"] or [])
        ):
            raise pilot.PilotRefusal("Competing observation process detected")


def read_shutdown(output, session):
    """Only this new database. Verify durable receipt rather than an in-memory acknowledgement."""
    with sqlite3.connect(f"file:{output / 'observe.db'}?mode=ro", uri=True) as db:
        row = db.execute("SELECT payload FROM evidence_runs WHERE session=?", (session,)).fetchone()
        shutdown = json.loads(row[0]) if row else None
        from backend.app.discovery import PUMP_PROGRAM

        persisted = db.execute(
            "SELECT count(*), count(DISTINCT mint) FROM records WHERE kind='event' AND session=? "
            "AND json_extract(payload, '$.event.kind')='create' "
            "AND json_extract(payload, '$.event.source')='Onchain Pump' "
            "AND json_extract(payload, '$.event.evidence.program')=? "
            "AND json_extract(payload, '$.event.evidence.commitment')='confirmed'",
            (session, PUMP_PROGRAM),
        ).fetchone()
        return dict(
            durable_live_create_records=persisted[0],
            durable_live_create_mints=persisted[1],
            shutdown=shutdown,
            sqlite_ok=db.execute("PRAGMA quick_check").fetchone()[0] == "ok",
            cohort_count=db.execute("SELECT count(*) FROM prospective_cohorts").fetchone()[0],
        )


def verdict(reason, discovery, counts, admitted, audit, source_ok, trace_ok, pending_tasks):
    shutdown = audit.get("shutdown") or {}
    events = shutdown.get("accounting", {}).get("events", {})
    create = events.get("create", {})
    checks = dict(
        scheduled=reason == "SCHEDULED_COMPLETION",
        source_unchanged=source_ok,
        ledger_complete=trace_ok,
        sqlite_ok=audit.get("sqlite_ok") is True,
        no_cohort=audit.get("cohort_count") == 0,
        shutdown_complete=shutdown.get("status") == "STOPPED" and shutdown.get("checkpoint_complete") is True,
        no_async_work=pending_tasks == 0,
        no_stranded_processing=bool(events) and all(r.get("in_processing") == 0 for r in events.values()),
        queue_reconciled=bool(events)
        and all(r.get("reconciled") is True and r.get("pending") == 0 for r in events.values()),
        no_queue_loss=audit.get("queue_losses") == {"trade": 0, "critical": 0},
        no_processing_failures=bool(events)
        and all(r.get("terminal", {}).get("exception", 0) == 0 for r in events.values()),
        diagnostics_readable=all(
            isinstance(discovery.get(k), dict)
            and bool(discovery[k])
            and all(isinstance(v, (int, float)) for v in discovery[k].values())
            for k in (
                "decode_failures_by_reason",
                "decode_failures_by_event",
                "framing_failure_details",
                "transport_failure_counts",
                "global_reset_reasons",
            )
        ),
        decoded_create=(discovery.get("launch_events") or 0) > 0,
        processed_create=create.get("terminal", {}).get("processed", 0) > 0,
        persisted_create=create.get("persisted", 0) > 0 and counts.get("live_persisted_on_return", 0) > 0,
        durable_create_correspondence=(
            audit.get("durable_live_create_records")
            == counts.get("live_persisted_on_return", 0)
            == create.get("persisted", 0)
        ),
        admitted_token=admitted > 0 and audit.get("durable_live_create_mints", 0) > 0,
        classification_transition=counts.get("transitions", 0) > 0,
        canonical_sources=not counts.get("noncanonical_create_observations", 0),
    )
    missing = [k for k, v in checks.items() if not v]
    # No live creates is inconclusive only when all operational integrity checks passed.
    sample_checks = {
        "decoded_create",
        "processed_create",
        "persisted_create",
        "admitted_token",
        "classification_transition",
    }
    status = "PASS" if not missing else "FAILED"
    if not checks["decoded_create"] and set(missing) <= sample_checks:
        status = "INCONCLUSIVE_NO_LIVE_CREATE"
    return dict(status=status, checks=checks, failed_checks=missing)


async def run(expected, output):
    source, settings, output = preflight(expected, output)
    import fcntl
    import psutil
    from backend.app.engine import RadarEngine

    # Same cooperative lock as the long pilot; release it on every exit path.
    with (ROOT / "data/early_edge/.signal-quality-pilot.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        check_processes()
        output.mkdir(exist_ok=False)
        manifest = dict(
            protocol=plan(), source=source, settings=settings.model_dump(), created_at=time.time()
        )
        manifest["sha256"] = hashlib.sha256(pilot.canonical(manifest).encode()).hexdigest()
        (output / "manifest.json").write_text(pilot.canonical(manifest))
        engine = RadarEngine(settings, output / "observe.db")
        start, mono = time.time(), time.monotonic()
        ledger = pilot.Ledger(output / "history.jsonl")
        recorder = SmokeRecorder(ledger, start, engine)
        detach = pilot.attach(engine, recorder)
        reason, error = "UNEXPECTED_INTERRUPTION", None
        audit, trace = {}, {}
        peak_rss = 0.0
        peak_storage = 0
        started = False
        pending_tasks = None
        source_ok = False
        try:
            recorder.emit("START", dict(at=start, source_sha=expected, manifest_sha256=manifest["sha256"]))
            ledger.flush()
            last_tick = next_health = next_source = mono
            async with asyncio.timeout(SECONDS):
                await engine.start()
                started = True
                while True:
                    elapsed = time.monotonic() - mono
                    peak_rss = max(peak_rss, psutil.Process().memory_info().rss / 1048576)
                    peak_storage = max(
                        peak_storage, sum(x.stat().st_size for x in output.iterdir() if x.is_file())
                    )
                    now = time.monotonic()
                    if now - last_tick > 20:
                        reason = "CONTROLLER_GAP"
                        break
                    last_tick = now
                    if now >= next_health:
                        recorder.emit("HEALTH", pilot.operational_snapshot(engine, time.time(), elapsed))
                        next_health = now + 10
                    if now >= next_source:
                        if not pilot.source_unchanged(source):
                            reason = "SOURCE_DRIFT"
                            break
                        next_source = now + 10
                    reason = recorder.stop_reason or (
                        "RECORD_SOFT_STOP"
                        if ledger.sequence >= 12000
                        else pilot.resource_reason(engine, output, elapsed)
                    )
                    ledger.flush()
                    if reason:
                        break
                    await asyncio.sleep(min(1, max(0, SECONDS - elapsed)))
        except TimeoutError:
            reason = "SCHEDULED_COMPLETION" if started else "STARTUP_TIMEOUT"
        except BaseException as exc:
            reason = "CANCELLED" if isinstance(exc, asyncio.CancelledError) else "OBSERVER_OR_IO_FAILURE"
            error = exc
        finally:
            cutoff = time.monotonic()
            if reason == "SCHEDULED_COMPLETION" and cutoff - mono > SECONDS + 1:
                reason = "OBSERVATION_DEADLINE_OVERRUN"
            # Capture the last live state before intentional transport cancellation.
            live_discovery = pilot.discovery_snapshot(engine.onchain.health)
            try:
                if not ledger.failed:
                    recorder.emit("HEALTH", pilot.operational_snapshot(engine, time.time(), cutoff - mono))
                    ledger.flush()
            except Exception:
                reason = "LEDGER_IO_FAILURE"
            detach()
            try:
                await engine.stop()
                pending_tasks = sum(
                    not t.done() and t is not asyncio.current_task() for t in asyncio.all_tasks()
                )
                audit = read_shutdown(output, engine.session)
                audit["queue_losses"] = dict(
                    trade=engine.queue.dropped_trades, critical=engine.queue.dropped_critical
                )
                if engine.approved_evidence is not None:
                    reason = "APPROVAL_BOUNDARY_FAILURE"
                (output / "shutdown.json").write_text(pilot.canonical(audit.get("shutdown")))
            except BaseException as exc:
                reason, error = "SHUTDOWN_FAILED", error or exc
            try:
                source_ok = pilot.source_unchanged(source)
                if not source_ok:
                    reason = "SOURCE_DRIFT"
                if not ledger.failed:
                    recorder.emit(
                        "STOP",
                        dict(
                            at=time.time(),
                            reason=reason,
                            source_unchanged=source_ok,
                            outstanding_measurements=0,
                            outstanding_horizons=0,
                        ),
                    )
                    ledger.flush()
            except Exception:
                reason = "LEDGER_IO_FAILURE"
            finally:
                ledger.file.close()
            try:
                trace = pilot.verify_ledger(output / "history.jsonl")
            except Exception:
                trace = dict(complete=False, error="INVALID_OR_PARTIAL_LEDGER")
            result = verdict(
                reason,
                live_discovery,
                recorder.counts,
                len(recorder.admitted),
                audit,
                source_ok,
                trace.get("complete") is True,
                pending_tasks,
            )
            result.update(
                protocol=plan(),
                reason=reason,
                source_sha=expected,
                session=engine.session,
                observation_elapsed_seconds=cutoff - mono,
                shutdown_elapsed_seconds=time.monotonic() - cutoff,
                process_exit_confirmation="Operator must confirm normal exit; executor cleanup is not bypassed",
                discovery=live_discovery,
                discovery_after_shutdown=pilot.discovery_snapshot(engine.onchain.health),
                observer_counts=dict(recorder.counts),
                distinct_admitted_tokens=len(recorder.admitted),
                create_accounting=(audit.get("shutdown") or {})
                .get("accounting", {})
                .get("events", {})
                .get("create"),
                queue=(audit.get("shutdown") or {}).get("queue"),
                ledger=trace,
                peak_rss_mb_sampled=peak_rss,
                peak_output_bytes_sampled=peak_storage,
                observation_deadline_seconds=SECONDS,
                deadline_overshoot_seconds=max(0, cutoff - mono - SECONDS),
                final_sqlite_file_bytes={
                    name: (output / name).stat().st_size
                    for name in ("observe.db", "observe.db-wal", "observe.db-shm")
                    if (output / name).exists()
                },
                final_database_bytes=(output / "observe.db").stat().st_size
                if (output / "observe.db").exists()
                else None,
                pending_async_tasks_after_stop=pending_tasks,
                durable_live_create_records=audit.get("durable_live_create_records"),
                durable_live_create_mints=audit.get("durable_live_create_mints"),
                queue_losses=audit.get("queue_losses"),
            )
            (output / "report.json").write_text(pilot.canonical(result))
        if error:
            raise error
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--expected-sha")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not args.run:
        print(json.dumps(plan(), indent=2))
        return
    if not args.expected_sha or args.output is None:
        parser.error("--run requires full published --expected-sha and new --output")
    try:
        result = asyncio.run(run(args.expected_sha, args.output))
        print(json.dumps(dict(status=result["status"], reason=result["reason"])))
        if result["status"] != "PASS":
            raise SystemExit(1)
    except KeyboardInterrupt:
        raise SystemExit(130) from None
    except Exception:
        print(
            "Qualification failed; inspect isolated bounded receipts. Exception text suppressed.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
