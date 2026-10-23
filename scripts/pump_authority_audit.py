"""Read-only bounded canonical Pump deployment/IDL authority evidence."""

import asyncio
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv
import httpx
from solders.pubkey import Pubkey
from backend.app.providers import PUMP_PROGRAM


async def main():
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    program = Pubkey.from_string(PUMP_PROGRAM)
    anchor = Pubkey.create_with_seed(Pubkey.find_program_address([], program)[0], "anchor:idl", program)
    pmp = Pubkey.from_string("ProgM6JCCvbYkfKqJYHePx4xxSUSqJp7rh8Lyv7nk7S")
    metadata = Pubkey.find_program_address([bytes(program), b"idl".ljust(16, b"\0")], pmp)[0]
    async with httpx.AsyncClient(timeout=25) as c:
        response = await c.post(
            os.environ["SOLANA_RPC_URL"],
            json=dict(
                jsonrpc="2.0",
                id=1,
                method="getMultipleAccounts",
                params=[[str(anchor), str(metadata)], dict(encoding="base64", commitment="finalized")],
            ),
        )
        j = response.json()["result"]
    out = dict(http_requests=1, commitment="finalized", context_slot=j["context"]["slot"], accounts=[])
    for label, address, owner, a in zip(
        ("ANCHOR", "CANONICAL_PMP"), (anchor, metadata), (program, pmp), j["value"]
    ):
        item = dict(mechanism=label, address=str(address), exists=a is not None)
        if a:
            if a["owner"] != str(owner):
                raise ValueError("IDL owner mismatch")
            raw = base64.b64decode(a["data"][0], validate=True)
            item.update(owner_verified=True, raw_sha256=hashlib.sha256(raw).hexdigest())
            if label == "ANCHOR":
                authority = str(Pubkey.from_bytes(raw[8:40]))
                length = int.from_bytes(raw[40:44], "little")
                if not 0 < length <= 2**20 or len(raw) < 44 + length:
                    raise ValueError("Anchor IDL length")
                d = zlib.decompressobj()
                decoded = d.decompress(raw[44 : 44 + length], 2**20)
                if d.unconsumed_tail or not d.eof:
                    raise ValueError("IDL decompression bound")
                idl = json.loads(decoded)
                if idl.get("address") not in (None, PUMP_PROGRAM):
                    raise ValueError("IDL address mismatch")
                f = next(t for t in idl["types"] if t["name"] == "TradeEvent")["type"]["fields"]
                item.update(
                    authority=authority,
                    idl_sha256=hashlib.sha256(decoded).hexdigest(),
                    trade_fields=len(f),
                    final_fields=f[-8:],
                )
                Path("data/early_edge/pump-onchain-anchor-idl-20261021.json").write_bytes(decoded)
        out["accounts"].append(item)
    prior = json.load(open("data/early_edge/pump-forensics-20261021.json"))
    deployment = prior["deployment"]
    deployment["utc"] = datetime.fromtimestamp(deployment["block_time"], timezone.utc).isoformat()
    out["deployment"] = deployment
    Path("data/early_edge/pump-authority-20261021.json").write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        print(json.dumps({"diagnostic_error_category": type(exc).__name__}), file=sys.stderr)
        raise SystemExit(1) from None
