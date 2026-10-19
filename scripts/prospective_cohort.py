"""Create/check/run frozen cohorts without editing DB rows or changing strategy."""
import argparse
import asyncio
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.config import ROOT, load_settings
from backend.app.db import Database
from backend.app.prospective import create_cohort, ProspectiveCohort, CohortIntegrityError


def database(path):
    from alembic import command
    from alembic.config import Config
    db = Database(path)
    cfg = Config(str(ROOT / "backend/alembic.ini"))
    with db.engine.begin() as connection:
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, "head")
    return db


async def run(path, cohort_id, settings, seconds=None):
    from backend.app.engine import RadarEngine
    engine = RadarEngine(settings, path, cohort_id=cohort_id)
    timer = None
    try:
        await engine.start()
        timer = asyncio.create_task(asyncio.Event().wait() if seconds is None else asyncio.sleep(seconds))
        done, _ = await asyncio.wait([timer, *engine.tasks], return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            if task is not timer:
                task.result()
                raise RuntimeError("Cohort acquisition task ended unexpectedly")
    finally:
        if timer is not None:
            timer.cancel()
            await asyncio.gather(timer, return_exceptions=True)
        await engine.stop()


def main():
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("create", "check", "run"))
    parser.add_argument("--db", type=Path, default=ROOT / "data/prospective.db")
    parser.add_argument("--cohort")
    parser.add_argument("--seconds", type=int)
    args = parser.parse_args()
    if args.action == "create" and args.cohort:
        parser.error("Creation generates a new immutable ID; existing cohorts cannot be adopted")
    if args.action != "create" and not args.cohort:
        parser.error("--cohort is required")
    if args.seconds is not None and args.seconds < 1:
        parser.error("--seconds must be positive")
    settings = load_settings()
    db = database(args.db)
    try:
        if args.action == "create":
            print(json.dumps(create_cohort(db, settings), indent=2))
        else:
            cohort = ProspectiveCohort(db, settings, args.cohort)
            if args.action == "check":
                print(json.dumps({"cohort_id": args.cohort, "integrity": "MATCH", "manifest": cohort.manifest}, indent=2))
            else:
                db.engine.dispose()
                asyncio.run(run(args.db, args.cohort, settings, args.seconds))
    finally:
        db.engine.dispose()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        # URLs/keys in provider exceptions are never printed.
        print(json.dumps({"error_type": type(exc).__name__, "error": str(exc) if isinstance(exc, CohortIntegrityError) else "Cohort operation refused; check local DB integrity"}), file=sys.stderr)
        raise SystemExit(1)
