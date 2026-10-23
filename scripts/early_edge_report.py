"""Read-only EARLY experiment report, separate from retrospective/strict cohorts."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.early_edge_report import report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(report(args.db.resolve()), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
