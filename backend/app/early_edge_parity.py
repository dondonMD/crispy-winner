"""Read-only parity instrumentation, exact same captured state sent to official SDK."""

import asyncio
import hashlib
import json
from pathlib import Path
import time

from backend.app.config import ROOT
from backend.app.early_edge_quotes import SOURCES, pump_buy, sell, quote_budget, QUOTES


REFERENCE_LOCK_SHA256 = "08392782ed2e6ac57363b1186ada86c6d79ccc090c663320c3885bc4fa185a29"


def expected(state, budget):
    if state["venue"] == "PUMP":
        entry = pump_buy(state, budget)
        result = sell(state, entry["quantity"])
        return dict(
            quantity=str(entry["quantity"]),
            entry_cost=str(entry["quote_raw"]),
            exit=str(result["quote_raw"]),
            gross=str(result["gross_quote_raw"]),
        )
    quantity = max(1, state["base_reserve"] // 1000000)
    result = sell(state, quantity)
    return dict(quantity=str(quantity), exit=str(result["quote_raw"]), gross=str(result["gross_quote_raw"]))


def string_ints(value):
    if type(value) is int:
        return str(value)
    if isinstance(value, dict):
        return {k: string_ints(v) for k, v in value.items()}
    if isinstance(value, list):
        return [string_ints(v) for v in value]
    return value


def validate_golden_provenance(vectors):
    """Offline integrity only; no SDK installation/execution or network."""
    generator = hashlib.sha256((ROOT / "scripts/early_edge_golden.cjs").read_bytes()).hexdigest()
    for vector in vectors:
        p = vector["provenance"]
        source = next(s for s in SOURCES["sources"] if vector["source"] == s["package"] + "@" + s["version"])
        inputs = {"state": vector["state"]}
        inputs.update(
            {"budget": vector["budget"]}
            if vector["state"]["venue"] == "PUMP"
            else {"quantity": vector["quantity"]}
        )
        state_hash = hashlib.sha256(
            json.dumps(inputs, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        expected_values = {k: vector[k] for k in ("quantity", "entry_cost", "exit", "gross") if k in vector}
        if (
            p["package"] != source["package"]
            or p["version"] != source["version"]
            or p["integrity"] != source["integrity"]
            or p["source_files_sha256"] != source["files"]
            or p["fixture_sha256"] != state_hash
            or p["generator_sha256"] != generator
            or p["generator_version"] != "early-edge-golden-v2"
            or p["expected"] != expected_values
        ):
            raise ValueError("Golden provenance drift")
    return True


async def isolated_reference(script, payload, node_path, max_output=8192):
    """A bounded subprocess calls quote helpers only, no lifecycle scripts/execution."""
    import shutil

    artifact_identity(node_path)
    if not shutil.which("bwrap"):
        raise ValueError("REFERENCE_SECURITY_BLOCKED: network/filesystem namespace unavailable")
    payload = json.dumps(string_ints(payload)).encode()
    if len(payload) > 65536:
        raise ValueError("Reference input exceeds bound")
    # No host root/home/project/env mount. Public captured state arrives on stdin only.
    command = [
        "bwrap",
        "--unshare-all",
        "--die-with-parent",
        "--new-session",
        "--ro-bind",
        "/usr",
        "/usr",
        "--ro-bind",
        "/lib",
        "/lib",
        "--ro-bind",
        "/lib64",
        "/lib64",
        "--ro-bind",
        str(Path(shutil.which("node") or "/missing").resolve()),
        "/node",
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--tmpfs",
        "/tmp",
        "--dir",
        "/reference",
        "--ro-bind",
        str(Path(node_path).resolve()),
        "/reference/node_modules",
        "--ro-bind",
        str(script),
        "/verifier.cjs",
        "--chdir",
        "/tmp",
        "--",
        "/node",
        "--max-old-space-size=128",
        "/verifier.cjs",
    ]
    env = {"PATH": "/usr/bin", "NODE_PATH": "/reference/node_modules", "LANG": "C.UTF-8"}
    process = await asyncio.create_subprocess_exec(
        *command,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )

    async def bounded_read(stream, limit):
        parts = bytearray()
        while True:
            block = await stream.read(min(4096, limit + 1 - len(parts)))
            if not block:
                return bytes(parts)
            parts.extend(block)
            if len(parts) > limit:
                raise ValueError("Reference output exceeds bound")

    async def exchange():
        assert process.stdin is not None
        process.stdin.write(payload)
        await process.stdin.drain()
        process.stdin.close()
        out, _ = await asyncio.gather(
            bounded_read(process.stdout, max_output), bounded_read(process.stderr, 8192)
        )
        await process.wait()
        return out

    try:
        out = await asyncio.wait_for(exchange(), 15)
    except BaseException:
        if process.returncode is None:
            process.kill()
        await process.wait()
        raise
    if process.returncode:
        raise ValueError("REFERENCE_SECURITY_BLOCKED: isolated official SDK verifier unavailable")
    return json.loads(out)


async def sdk_compare(state, budget, node_path):
    actual = await isolated_reference(
        ROOT / "scripts/early_edge_sdk_compare.cjs", dict(state=state, budget=budget), node_path
    )
    want = expected(state, budget)
    return dict(
        match=actual == want,
        python=want,
        official_sdk=actual,
        state_sha256=hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest(),
    )


async def probe(oracle, mint, venue, pool, proof, node_path, count=3, reference=150):
    records = []
    for _ in range(min(5, max(2, count))):
        start = time.time()
        try:
            observation = await oracle.observe(mint, venue, pool, proof, diagnostic_pool=venue == "PUMPSWAP")
            q = observation.data["quote_mint"]
            budget = quote_budget(4, reference if QUOTES[q][0] == "SOL" else 1, q)
            result = await sdk_compare(observation.data, budget, node_path)
            records.append(
                dict(
                    result,
                    mint=mint,
                    pool=pool,
                    venue=venue,
                    slot=observation.slot,
                    commitment=observation.commitment,
                    acquired_at=observation.acquired_at,
                    account_hashes=observation.account_hashes,
                    identity_address=observation.identity_address,
                    directions=["buy", "sell"] if venue == "PUMP" else ["sell"],
                    elapsed_seconds=time.time() - start,
                )
            )
        except Exception as exc:
            records.append(
                dict(venue=venue, mint=mint, pool=pool, error_category=type(exc).__name__, match=False)
            )
        await asyncio.sleep(0.5)
    return records


def artifact_identity(node_path):
    """Validate the actual installed reference packages against pinned source files."""
    root = Path(node_path)
    lock = root.parent / "package-lock.json"
    if not lock.exists() or hashlib.sha256(lock.read_bytes()).hexdigest() != REFERENCE_LOCK_SHA256:
        raise ValueError("Audited SDK reference dependency lock drift")
    evidence = []
    for source in SOURCES["sources"]:
        path = root / source["package"]
        version = json.loads((path / "package.json").read_text())["version"]
        if version != source["version"]:
            raise ValueError("SDK version drift")
        for name, want in source["files"].items():
            if hashlib.sha256((path / name).read_bytes()).hexdigest() != want:
                raise ValueError("SDK source drift")
        evidence.append(
            dict(
                package=source["package"],
                version=version,
                git_head=source["git_head"],
                source_files_verified=True,
            )
        )
    return evidence


def validate_attestation(plan, path, now):
    from backend.app.early_edge import digest, IntegrityError

    r = path if isinstance(path, dict) else json.loads(Path(path).read_text())
    expected_hash = r.get("report_hash")
    body = {k: v for k, v in r.items() if k != "report_hash"}
    records = r.get("records", [])
    identities = {
        venue: {(e["mint"], e.get("pool")) for e in records if e.get("venue") == venue and e.get("match")}
        for venue in ("PUMP", "PUMPSWAP")
    }
    good = (
        expected_hash == digest(body)
        and r.get("source_hash") == plan["identity"]["source_hash"]
        and r.get("config_hash") == plan["identity"]["config_hash"]
        and r.get("live_readonly") is True
        and 0 <= now - r.get("completed_at", 0) <= 86400
        and r.get("artifacts_verified") is True
        and all(len(keys) >= 2 for keys in identities.values())
        and records
        and all(e.get("match") is True or e.get("error_category") == "QuoteUnavailable" for e in records)
    )
    for venue, keys in identities.items():
        good = good and all(
            sum(
                e.get("match") is True and (e["mint"], e.get("pool")) == key and e["venue"] == venue
                for e in records
            )
            >= 2
            for key in keys
        )
    for venue, keys in identities.items():
        for mint, pool in keys:
            matches = [
                e
                for e in records
                if e.get("match") and e["venue"] == venue and (e["mint"], e.get("pool")) == (mint, pool)
            ]
            good = good and len({e.get("slot") for e in matches}) >= 2
            good = good and all(
                e.get("commitment") == "confirmed"
                and isinstance(e.get("slot"), int)
                and 0 <= r["completed_at"] - e.get("acquired_at", 0) <= 600
                and len(e.get("account_hashes", [])) >= 5
                and e.get("identity_address")
                and e.get("python") == e.get("official_sdk")
                for e in matches
            )
    from backend.app.early_edge import fx_value

    try:
        for quote in plan["supported_quotes"]:
            fx_value(r.get("usd_reference_preflight", {}), quote, r.get("completed_at", 0))
    except (ValueError, KeyError, TypeError):
        good = False
    if not good:
        raise IntegrityError("Live official SDK parity preflight failed/missing/stale/drifted")
    return expected_hash
