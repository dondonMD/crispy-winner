"""Research-only reference security and diagnostic isolation regressions."""

import hashlib
import json
from pathlib import Path
import pytest


def test_goldens_full_provenance_without_sdk():
    path = Path(__file__).parent / "fixtures/early_edge/sdk_quotes.json"
    vectors = json.loads(path.read_text())["vectors"]
    from backend.app.early_edge_parity import validate_golden_provenance

    assert validate_golden_provenance(vectors)
    assert len(vectors) == 48
    for v in vectors:
        p = v["provenance"]
        assert p["integrity"].startswith("sha512-") and p["source_files_sha256"]
        inputs = {"state": v["state"]}
        inputs.update(
            {"budget": v["budget"]} if v["state"]["venue"] == "PUMP" else {"quantity": v["quantity"]}
        )
        assert (
            p["fixture_sha256"]
            == hashlib.sha256(json.dumps(inputs, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        )
        assert p["expected"]["exit"] == v["exit"]
        assert p["generator_version"] == "early-edge-golden-v2"


def test_normal_diagnostic_sdk_optional_and_failure_not_zero_parity():
    from scripts.early_edge_diagnostic import build_parser

    args = build_parser().parse_args(["--output", "/tmp/non-enrolling-unused.json"])
    assert args.node_path is None


def test_trade_diagnostics_delegates_without_mutating_events():
    from scripts.early_edge_diagnostic import TradeDiagnostics
    from backend.app.domain import MarketEvent

    event = MarketEvent(
        kind="trade",
        mint="synthetic-mint",
        ts=1,
        source="SYNTHETIC",
        event_id="synthetic",
        side="buy",
        currency="SOL",
        evidence={"units_valid": True},
    )
    before = event.model_dump()
    calls = []
    wrapper = TradeDiagnostics(lambda e: calls.append(e) or True)
    assert wrapper(event) is True and calls == [event] and event.model_dump() == before
    assert wrapper.counts["buy"] == wrapper.counts["SOL"] == 1
    assert len(wrapper.known_unit_mints) == 1
    refused = TradeDiagnostics(lambda e: False)
    assert refused(event) is False and not refused.counts


def test_trade_diagnostic_memory_bound():
    from scripts.early_edge_diagnostic import TradeDiagnostics
    from backend.app.domain import MarketEvent

    wrapper = TradeDiagnostics(lambda e: True)
    for i in range(2050):
        wrapper(
            MarketEvent(
                kind="trade",
                mint=str(i),
                ts=1,
                source="SYNTHETIC",
                event_id=str(i),
                side="sell",
                currency="USDC",
                evidence={"units_valid": True},
            )
        )
    assert len(wrapper.known_unit_mints) == 2048 and wrapper.counts["sell"] == 2050


async def test_isolated_reference_has_no_host_secrets_or_network(monkeypatch):
    import asyncio
    import os
    from backend.app import early_edge_parity as parity

    observed = {}
    monkeypatch.setenv("SOLANA_RPC_URL", "SYNTHETIC_SECRET_DO_NOT_INHERIT")
    monkeypatch.setattr(parity, "artifact_identity", lambda p: [])

    class Input:
        def write(self, data):
            observed["payload"] = data

        async def drain(self):
            pass

        def close(self):
            pass

    class Process:
        stdin = Input()
        returncode = 0
        stdout = asyncio.StreamReader()
        stderr = asyncio.StreamReader()

        async def wait(self):
            return 0

    process = Process()
    process.stdout.feed_data(b'{"verified":true}')
    process.stdout.feed_eof()
    process.stderr.feed_eof()

    async def spawn(*args, **kwargs):
        observed.update(args=args, env=kwargs["env"])
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    result = await parity.isolated_reference(
        Path("scripts/early_edge_sdk_compare.cjs"), {"state": {}}, Path("/tmp/reference")
    )
    assert result == {"verified": True}
    assert "--unshare-all" in observed["args"] and "--die-with-parent" in observed["args"]
    assert set(observed["env"]) == {"PATH", "NODE_PATH", "LANG"}
    assert os.environ["SOLANA_RPC_URL"] not in repr(observed)
    assert ("--ro-bind", "/", "/") != observed["args"][:3]


def test_reference_dependency_lock_is_isolated_test_data(tmp_path):
    from backend.app.early_edge_parity import REFERENCE_LOCK_SHA256, artifact_identity

    lock = Path("backend/tests/fixtures/early_edge/reference_lock.json")
    assert hashlib.sha256(lock.read_bytes()).hexdigest() == REFERENCE_LOCK_SHA256
    parsed = json.loads(lock.read_text())
    assert parsed["packages"]["node_modules/@pump-fun/pump-sdk"]["version"] == "4.1.0"
    assert parsed["packages"]["node_modules/@pump-fun/pump-swap-sdk"]["version"] == "2.1.0"
    (tmp_path / "package-lock.json").write_text("{}")
    with pytest.raises(ValueError, match="dependency lock drift"):
        artifact_identity(tmp_path / "node_modules")
    for name in ("frontend/package.json", "frontend/package-lock.json", "backend/requirements.txt"):
        assert "@pump-fun/" not in Path(name).read_text()
