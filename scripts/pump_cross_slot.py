"""Bounded finalized exact-layout corroboration; no engine, database or event submission."""

import argparse
import asyncio
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
import websockets
from dotenv import load_dotenv
from solders.pubkey import Pubkey
from backend.app.discovery import decode_event, TRADE_DISCRIMINATOR
from backend.app.providers import PUMP_PROGRAM
from backend.app.truncation import decode_base58, INSTRUCTIONS, TRADE_NAMES
from scripts.pump_trade_forensics import scoped_events, inspect_payload


def match_instruction(fields, instructions):
    matches = []
    for ix in instructions:
        if ix.get("programId") != PUMP_PROGRAM or "data" not in ix:
            continue
        definition = INSTRUCTIONS.get(decode_base58(ix["data"])[:8])
        if not definition or definition["name"] not in TRADE_NAMES:
            continue
        accounts = ix.get("accounts", [])
        if len(accounts) < len(definition["accounts"]):
            continue
        named = {a["name"]: accounts[i] for i, a in enumerate(definition["accounts"])}
        if named.get("base_mint", named.get("mint")) != fields["mint"] or named.get("user") != fields["user"]:
            continue
        name = definition["name"]

        def normal(value):
            return value.replace("_", "").lower()

        if name.startswith("buy") == fields["is_buy"] and normal(fields["ix_name"]) == normal(name):
            matches.append((name, named))
    return matches


async def run():
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    started = time.time()
    candidates: dict[str, tuple[int, int]] = {}
    per_slot: Counter[int] = Counter()
    sides: Counter[str] = Counter()
    counts: Counter[str] = Counter()
    async with websockets.connect(os.environ["SOLANA_WS_URL"], max_size=2**20, max_queue=16) as ws:
        await ws.send(
            json.dumps(
                dict(
                    jsonrpc="2.0",
                    id=911,
                    method="logsSubscribe",
                    params=[{"mentions": [PUMP_PROGRAM]}, {"commitment": "confirmed"}],
                )
            )
        )
        ack = json.loads(await asyncio.wait_for(ws.recv(), 15))
        if not isinstance(ack.get("result"), int):
            raise ValueError("ACK")
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            try:
                msg = json.loads(await asyncio.wait_for(ws.recv(), 3))
            except asyncio.TimeoutError:
                continue
            counts["notifications"] += 1
            r = msg.get("params", {}).get("result", {})
            v = r.get("value", {})
            if v.get("err") is not None:
                continue
            events, bad = scoped_events(v.get("logs", []))
            if bad:
                counts["framing_notifications"] += 1
                continue
            slot = r.get("context", {}).get("slot")
            for ordinal, encoded in events:
                meta, fields = inspect_payload(encoded)
                if meta.get("discriminator") != TRADE_DISCRIMINATOR.hex():
                    continue
                if meta.get("remaining", 0) > 0:
                    raise ValueError("UNEXPLAINED_PUMP_TAIL_STOP")
                decoded = decode_event(encoded)
                if not decoded or decoded[0] != "TradeEvent":
                    continue
                counts["full_36_decodes"] += 1
                signature = v["signature"]
                side = "BUY" if fields["is_buy"] else "SELL"
                if (
                    signature not in candidates
                    and len(candidates) < 24
                    and per_slot[slot] < 3
                    and sides[side] < 12
                ):
                    candidates[signature] = (slot, ordinal)
                    per_slot[slot] += 1
                    sides[side] += 1
            if len(candidates) >= 24 and time.time() - started >= 40:
                break
    samples = []
    rpc_count = 0
    async with httpx.AsyncClient(timeout=25) as client:
        for signature in candidates:
            rpc_count += 1
            response = await client.post(
                os.environ["SOLANA_RPC_URL"],
                json=dict(
                    jsonrpc="2.0",
                    id=rpc_count,
                    method="getTransaction",
                    params=[
                        signature,
                        dict(encoding="jsonParsed", commitment="finalized", maxSupportedTransactionVersion=1),
                    ],
                ),
            )
            response.raise_for_status()
            tx = response.json().get("result")
            if not tx:
                counts["unavailable_lookup"] += 1
                continue
            if tx["meta"]["err"] is not None:
                continue
            events, bad = scoped_events(tx["meta"].get("logMessages", []))
            if bad:
                continue
            instructions = list(tx["transaction"]["message"]["instructions"])
            for group in tx["meta"].get("innerInstructions") or []:
                instructions.extend(group["instructions"])
            for ordinal, encoded in events:
                meta, fields = inspect_payload(encoded)
                if meta.get("discriminator") != TRADE_DISCRIMINATOR.hex():
                    continue
                if meta.get("remaining", 0) > 0:
                    raise ValueError("UNEXPLAINED_PUMP_TAIL_STOP")
                decoded = decode_event(encoded)
                matches = match_instruction(fields, instructions)
                if not decoded or meta["category"] != "ACCEPTED" or len(matches) != 1:
                    counts["ambiguous_instruction"] += 1
                    continue
                name, named = matches[0]
                quote = fields["quote_mint"]
                if quote == str(Pubkey.default()) and name in ("buy", "sell", "buy_exact_sol_in"):
                    quote = "So11111111111111111111111111111111111111112"
                known = quote in (
                    "So11111111111111111111111111111111111111112",
                    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                )
                samples.append(
                    dict(
                        signature_hash=hashlib.sha256(signature.encode()).hexdigest(),
                        slot=tx["slot"],
                        ordinal=ordinal,
                        mint_hash=hashlib.sha256(fields["mint"].encode()).hexdigest(),
                        direction="BUY" if fields["is_buy"] else "SELL",
                        instruction=name,
                        ix_name_matches=True,
                        named_mint_user_matches=True,
                        quote_units="SOL"
                        if known and quote.startswith("So111")
                        else "USDC"
                        if known
                        else "UNAVAILABLE",
                        quote_account_matches=named.get("quote_mint", quote) == quote,
                        **{
                            k: meta[k]
                            for k in ("discriminator", "raw_length", "consumed", "remaining", "parsed_fields")
                        },
                        final_field="quote_transfer_fee",
                        quote_transfer_fee=fields["quote_transfer_fee"],
                        version=tx.get("version"),
                    )
                )
                break
            if sufficient(samples):
                break
    return dict(
        passed=sufficient(samples),
        finalized=True,
        samples=samples,
        distinct_slots=len({s["slot"] for s in samples}),
        distinct_mints=len({s["mint_hash"] for s in samples}),
        directions=dict(Counter(s["direction"] for s in samples)),
        counters=dict(counts),
        rpc_requests=rpc_count,
        duration=time.time() - started,
        cohort_created=False,
    )


def sufficient(samples):
    return (
        len(samples) >= 12
        and len({s["slot"] for s in samples}) >= 3
        and len({s["mint_hash"] for s in samples}) >= 3
        and min(Counter(s["direction"] for s in samples).get(d, 0) for d in ("BUY", "SELL")) >= 4
        and all(
            s["parsed_fields"] == 36 and s["remaining"] == 0 and s["quote_account_matches"] for s in samples
        )
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    try:
        result = asyncio.run(run())
        with args.output.open("x") as f:
            json.dump(result, f, indent=2)
        print(json.dumps({k: v for k, v in result.items() if k != "samples"}))
        raise SystemExit(0 if result["passed"] else 2)
    except Exception as exc:
        print(json.dumps(dict(error_category=type(exc).__name__)), file=sys.stderr)
        raise SystemExit(1) from None
