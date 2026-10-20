"""Bounded read-only PumpSwap deployment and canonical IDL account inspection."""

import argparse
import asyncio
import base64
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import sys
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from solders.pubkey import Pubkey
from backend.app.providers import SolanaProvider
from backend.app.pumpswap import PROGRAM

LOADER = "BPFLoaderUpgradeab1e11111111111111111111111"
METADATA = "ProgM6JCCvbYkfKqJYHePx4xxSUSqJp7rh8Lyv7nk7S"
LIMIT = 1000000


def account_bytes(account, owner):
    if not isinstance(account, dict) or account.get("owner") != owner:
        raise ValueError("Account owner")
    encoded = account["data"]
    if (
        not isinstance(encoded, list)
        or len(encoded) != 2
        or encoded[1] != "base64"
        or len(encoded[0]) > LIMIT * 2
    ):
        raise ValueError("Account encoding bounds")
    return base64.b64decode(encoded[0], validate=True)


def programdata_address(account):
    raw = account_bytes(account, LOADER)
    if account.get("executable") is not True or len(raw) != 36 or int.from_bytes(raw[:4], "little") != 2:
        raise ValueError("Upgradeable Program state")
    address = Pubkey.from_bytes(raw[4:36])
    expected = Pubkey.find_program_address([bytes(Pubkey.from_string(PROGRAM))], Pubkey.from_string(LOADER))[
        0
    ]
    if address != expected:
        raise ValueError("ProgramData identity")
    return str(address)


def deployment(account):
    raw = account_bytes(account, LOADER)
    if account.get("executable") is not False or len(raw) != 45 or int.from_bytes(raw[:4], "little") != 3:
        raise ValueError("ProgramData state")
    option = raw[12]
    if option not in (0, 1):
        raise ValueError("Authority option")
    return {
        "upgrade_slot": int.from_bytes(raw[4:12], "little"),
        "upgrade_authority": str(Pubkey.from_bytes(raw[13:45])) if option else None,
    }


def idl_addresses():
    program = Pubkey.from_string(PROGRAM)
    base = Pubkey.find_program_address([], program)[0]
    legacy = Pubkey.create_with_seed(base, "anchor:idl", program)
    # Official program-metadata generated Seed codec is a fixed 16-byte UTF-8 seed.
    canonical = Pubkey.find_program_address(
        [bytes(program), b"idl".ljust(16, b"\0")], Pubkey.from_string(METADATA)
    )[0]
    return {"anchor_0_31": str(legacy), "canonical_program_metadata": str(canonical)}


def decode_legacy_idl(account):
    raw = account_bytes(account, PROGRAM)
    if (
        account.get("executable") is not False
        or len(raw) < 44
        or raw[:8] != hashlib.sha256(b"internal:IdlAccount").digest()[:8]
    ):
        raise ValueError("Anchor IDL identity")
    size = int.from_bytes(raw[40:44], "little")
    if not 0 < size <= LIMIT or 44 + size > len(raw):
        raise ValueError("Anchor IDL bounds")
    inflater = zlib.decompressobj()
    decoded = inflater.decompress(raw[44 : 44 + size], LIMIT + 1)
    if len(decoded) > LIMIT or not inflater.eof or inflater.unused_data or inflater.unconsumed_tail:
        raise ValueError("Anchor IDL compression bounds")
    doc = json.loads(decoded)
    if doc.get("address", PROGRAM) != PROGRAM:
        raise ValueError("IDL program mismatch")
    return decoded


async def inspect(rpc=None):
    own = rpc is None
    rpc = rpc or SolanaProvider()
    before = rpc.health["requests"]
    try:
        result = await rpc.rpc("getAccountInfo", [PROGRAM, {"encoding": "base64", "commitment": "confirmed"}])
        program = result["value"]
        report = {
            "program": PROGRAM,
            "observed_at": datetime.now(UTC).isoformat(),
            "loader": program["owner"],
            "executable": program["executable"],
            "rpc_context_slot": result["context"]["slot"],
        }
        if program["owner"] != LOADER:
            report["deployment_status"] = "LOADER_NOT_UPGRADEABLE_OR_UNSUPPORTED"
            return report
        pd = programdata_address(program)
        account = await rpc.rpc(
            "getAccountInfo",
            [pd, {"encoding": "base64", "commitment": "confirmed", "dataSlice": {"offset": 0, "length": 45}}],
        )
        report.update(programdata=pd, **deployment(account["value"]))
        blocktime = await rpc.rpc("getBlockTime", [report["upgrade_slot"]])
        report["upgrade_block_time"] = blocktime
        report["upgrade_utc"] = (
            datetime.fromtimestamp(blocktime, UTC).isoformat() if type(blocktime) is int else None
        )
        addresses = idl_addresses()
        accounts = await rpc.rpc(
            "getMultipleAccounts",
            [list(addresses.values()), {"encoding": "base64", "commitment": "confirmed"}],
        )
        if not isinstance(accounts.get("value"), list) or len(accounts["value"]) != 2:
            raise ValueError("IDL account response")
        report["idl_accounts"] = {}
        for name, value in zip(addresses, accounts["value"]):
            observation = {
                "address": addresses[name],
                "exists": value is not None,
                "rpc_context_slot": accounts["context"]["slot"],
            }
            if value is not None:
                observation["owner"] = value.get("owner")
                if name == "anchor_0_31":
                    decoded = decode_legacy_idl(value)
                    observation.update(
                        status="VALIDATED_ANCHOR_IDL",
                        sha256=hashlib.sha256(decoded).hexdigest(),
                        idl=json.loads(decoded),
                    )
                else:
                    # An existing successor account needs its canonical codec before trust.
                    account_bytes(value, METADATA)
                    observation["status"] = "PRESENT_REQUIRES_CANONICAL_METADATA_DECODE"
            else:
                observation["status"] = "ACCOUNT_ABSENT"
            report["idl_accounts"][name] = observation
        report["idl_status"] = (
            "NO_ONCHAIN_IDL" if all(v is None for v in accounts["value"]) else "IDL_ACCOUNT_PRESENT"
        )
        report["diagnostic_rpc_requests"] = rpc.health["requests"] - before
        return report
    finally:
        if own:
            await rpc.close()


def main():
    from dotenv import load_dotenv

    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Choose a unique output path")
    try:
        report = asyncio.run(inspect())
    except Exception as exc:
        print(json.dumps({"error_type": type(exc).__name__}), file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as f:
        json.dump(report, f, indent=2, allow_nan=False)
        f.write("\n")
    print(json.dumps(report, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
