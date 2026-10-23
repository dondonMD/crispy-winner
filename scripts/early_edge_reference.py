"""Opt-in, network-isolated official SDK golden provenance check; no installs or writes."""

import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.config import ROOT
from backend.app.early_edge_parity import isolated_reference, validate_golden_provenance


async def verify(node_path):
    fixture = json.loads((ROOT / "backend/tests/fixtures/early_edge/sdk_quotes.json").read_text())
    validate_golden_provenance(fixture["vectors"])
    actual = await isolated_reference(ROOT / "scripts/early_edge_golden.cjs", {}, node_path, 524288)
    expected = [{k: v for k, v in x.items() if k != "provenance"} for x in fixture["vectors"]]
    if actual["vectors"] != expected:
        raise ValueError("Official golden provenance mismatch; no overwrite permitted")
    print(
        json.dumps(
            dict(
                vectors=len(expected),
                match=True,
                network="OS_NAMESPACE_DISABLED",
                sha256=hashlib.sha256(json.dumps(expected, sort_keys=True).encode()).hexdigest(),
            )
        )
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--node-path", type=Path, required=True, help="Disposable pinned reference tree only")
    asyncio.run(verify(p.parse_args().node_path))
