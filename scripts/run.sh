#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export RADAR_MODE="${1:-OBSERVE}"
exec .venv/bin/python -m backend.app.main
