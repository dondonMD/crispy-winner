import argparse
import csv
import json
from pathlib import Path
from dotenv import load_dotenv
from backend.app.config import ROOT, load_settings
from backend.app.engine import RadarEngine
from backend.app.evaluation import evaluate, replay


def main():
    parser = argparse.ArgumentParser(description="Local Graduation Radar research and maintenance")
    parser.add_argument("command", choices=["evaluate", "replay", "optimize", "freeze-evidence"])
    parser.add_argument("session", nargs="?")
    parser.add_argument("--output", type=Path, default=ROOT / "data/evaluation.json")
    parser.add_argument("--csv", type=Path)
    parser.add_argument("--horizon", type=int, default=300)
    args = parser.parse_args()
    if args.command == "freeze-evidence":
        parser.error(
            "Evidence approval is disabled: retrospective evaluation cannot authorize entries. "
            "Use evaluate for descriptive research; prospective approval requires a separately "
            "validated protocol and independent approval control."
        )
    load_dotenv(ROOT / ".env")
    settings = load_settings()
    engine = RadarEngine(settings)
    if args.command == "replay":
        if not args.session:
            parser.error("replay requires session ID")
        result = replay(engine.db, args.session)
    elif args.command == "optimize":
        removed = engine.db.retention(settings)
        engine.db.optimize()
        result = {"deleted_expired_records": removed, "database_bytes": engine.db.size()}
    else:
        result = evaluate(
            engine.db, settings, "demo" if settings.mode == "DEMO" else "real", engine.version, args.horizon
        )
        engine.db.add("evaluation", result)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False))
    if args.csv and "buckets" in result:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        with args.csv.open("w", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(["bucket", "samples", "net_expectancy_pct", "win_rate_pct", "status"])
            for name, row in result["buckets"].items():
                writer.writerow(
                    [name, row["count"], row["expectancy_net_pct"], row["win_rate_pct"], row["status"]]
                )
    print(json.dumps(result, indent=2, allow_nan=False))
    engine.db.engine.dispose()


if __name__ == "__main__":
    main()
