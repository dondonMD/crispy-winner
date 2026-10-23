"""Separate EARLY study plan/check/OBSERVE runner. Never selects the retired cohort."""

import argparse
import asyncio
import json
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.config import ROOT, load_settings
from backend.app.early_edge import Study, IntegrityError, manifest
from backend.app.early_edge_runtime import (
    EarlyEdgeObserver,
    UsdReference,
    acquire,
    attach_observer,
    refresh_reference,
)


async def run(path, engine_path, settings, seconds):
    if (
        settings.mode != "OBSERVE"
        or os.getenv("PUMPPORTAL_ENABLED", "false").lower() == "true"
        or os.getenv("RADAR_COHORT")
        or engine_path.exists()
        or engine_path.resolve() == path.resolve()
    ):
        raise IntegrityError("Fresh separate OBSERVE database required; no existing cohort may be selected")
    import fcntl
    from backend.app.engine import RadarEngine

    with Path(str(path) + ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        study = Study(path, settings)
        study.begin()
        reference = UsdReference()
        engine = None
        observer = None
        task = None
        reference_task = None
        detach = None
        stop = asyncio.Event()
        started = time.time()
        try:
            engine = RadarEngine(settings, engine_path)
            observer = EarlyEdgeObserver(study, settings, reference)
            detach = attach_observer(engine, observer)
            await reference.refresh()
            from backend.app.early_edge import fx_value
            from backend.app.early_edge_quotes import QUOTES

            try:
                for quote in QUOTES:
                    fx_value(reference.snapshot(), quote, time.time())
            except ValueError:
                study.quality(dict(enrollment_not_started="USD_REFERENCE_PREFLIGHT_UNAVAILABLE"))
                raise IntegrityError(
                    "USD reference unavailable before collection; no enrollment started"
                ) from None
            await engine.start()
            reference_task = asyncio.create_task(refresh_reference(reference, stop))
            study.quality(
                dict(
                    enrollment_start=started,
                    enrollment_stop=started + seconds,
                    drain_deadline=started + seconds + 1821,
                )
            )
            task = asyncio.create_task(acquire(study, engine, observer, reference, stop))
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline and not study.enrollment_state(time.time())["closed"]:
                if reference_task.done():
                    reference_task.result()
                    raise IntegrityError("USD reference task ended")
                if task.done():
                    task.result()
                    raise IntegrityError("Research acquisition ended")
                for original in engine.tasks:
                    if original.done():
                        original.result()
                        raise IntegrityError("Core acquisition ended")
                if path.stat().st_size > (settings.db_limit_mb - 20) * 1024**2:
                    raise IntegrityError("Research storage guard")
                await asyncio.sleep(0.5)
            observer.accepting = False
            drain = time.monotonic() + 1821
            while (
                study.db.execute("SELECT count(*) FROM ee_pending").fetchone()[0] and time.monotonic() < drain
            ):
                if task.done():
                    task.result()
                    raise IntegrityError("Research drain interrupted")
                await asyncio.sleep(0.5)
        finally:
            stop.set()
            if task:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            if reference_task:
                reference_task.cancel()
                await asyncio.gather(reference_task, return_exceptions=True)
            if detach:
                detach()
            try:
                if engine:
                    try:
                        study.quality(
                            dict(
                                final_recovery=dict(engine.recovery.health),
                                final_rpc=dict(engine.rpc.health),
                                observer_failed=observer.failed if observer else True,
                                observer_error=observer.error if observer else None,
                            )
                        )
                    finally:
                        await engine.stop()
            finally:
                try:
                    await reference.close()
                finally:
                    try:
                        study.close()
                    finally:
                        # Even source drift must release resources. Restart will account unfinished work.
                        study.db.close()


def main():
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("plan", "create", "check", "run"))
    parser.add_argument("--db", type=Path)
    parser.add_argument("--engine-db", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--enrollment-seconds", type=int, default=600)
    parser.add_argument("--confirm-reviewed-design", action="store_true")
    parser.add_argument("--parity-report", type=Path)
    args = parser.parse_args()
    settings = load_settings()
    if settings.mode != "OBSERVE":
        parser.error("OBSERVE only")
    if args.action == "plan":
        payload = manifest(settings, draft=True)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x") as f:
                json.dump(payload, f, indent=2, allow_nan=False)
                f.write("\n")
        print(json.dumps(payload, indent=2, allow_nan=False))
        return 0
    if args.db is None:
        parser.error("Explicit isolated --db required")
    if args.action == "create":
        if not args.confirm_reviewed_design:
            parser.error(
                "Review the draft and explicitly pass --confirm-reviewed-design before future real creation"
            )
        if args.db.exists():
            parser.error("Refuse existing database")
        from backend.app.early_edge_parity import validate_attestation

        if args.parity_report is None:
            parser.error("Source-bound live parity report required")
        frozen = manifest(settings, draft=False)
        frozen["parity_attestation_hash"] = validate_attestation(frozen, args.parity_report, time.time())
        frozen["parity_attestation"] = json.loads(args.parity_report.read_text())
        study = Study(args.db, settings, cohort=frozen)
        print(json.dumps(study.plan, indent=2))
        study.db.close()
    elif args.action == "check":
        study = Study(args.db, settings)
        print(json.dumps(dict(cohort_id=study.plan["cohort_id"], integrity="PASS")))
        study.db.close()
    else:
        if args.engine_db is None or not 1 <= args.enrollment_seconds <= 86400:
            parser.error("Fresh --engine-db and enrollment duration 1..86400 required")
        asyncio.run(run(args.db, args.engine_db, settings, args.enrollment_seconds))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (IntegrityError, ValueError) as exc:
        print(json.dumps(dict(error_type=type(exc).__name__, collection_refused=True)), file=sys.stderr)
        raise SystemExit(1) from None
