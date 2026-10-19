"""Read-only primary and explicitly exploratory prospective cohort report."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.config import ROOT
from backend.app.prospective_report import report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort", required=True)
    parser.add_argument("--db", type=Path, default=ROOT / "data/prospective.db")
    parser.add_argument("--as-of", type=float, help="Fixed Unix timestamp for reproducible as-of analysis")
    args = parser.parse_args()
    print(json.dumps(report(args.db, args.cohort, args.as_of), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
