"""Bounded read-only Pump layout investigation; never emits MarketEvents or opens a DB."""

import argparse
import asyncio
import base64
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import time
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.discovery import FIELDS, TRADE_DISCRIMINATOR, decode_event, DecodeFailure, INVOKE, FINISH
from backend.app.providers import PUMP_PROGRAM
from solders.pubkey import Pubkey
import httpx
import websockets

CATEGORIES = (
    "KNOWN_DISCRIMINATOR_TRAILING_BYTES",
    "RAW_TOO_SHORT",
    "FIELD_BOUNDARY_FAILURE",
    "FIELD_TYPE_UNSUPPORTED",
    "INVALID_BOOL",
    "INVALID_STRING",
    "INVALID_PUBKEY",
    "INVALID_TIMESTAMP",
    "INVOCATION_FRAMING",
    "UNKNOWN_OTHER",
)


def inspect_payload(encoded, fields=None):
    """Diagnostic field walker only; production decoder remains the acceptance authority.

    Internal values are returned to caller for bounded transaction corroboration only.
    Reports must use metadata, never serialize values (which include public wallets).
    """
    meta = dict(category="UNKNOWN_OTHER", parsed_fields=0, consumed=0)
    values: dict[str, Any] = {}
    if len(encoded) > 16384:
        return dict(meta, detail="ENCODED_STRING_TOO_LARGE"), values
    try:
        raw = base64.b64decode(encoded, validate=True)
    except ValueError:
        return dict(meta, detail="INVALID_ENCODING"), values
    meta.update(raw_length=len(raw), discriminator=raw[:8].hex())
    if len(raw) < 8:
        return dict(meta, category="RAW_TOO_SHORT"), values
    if raw[:8] != TRADE_DISCRIMINATOR:
        return dict(meta, detail="OTHER_DISCRIMINATOR"), values
    fields = FIELDS["TradeEvent"] if fields is None else fields
    meta.update(documented_fields=len(fields), final_documented_field=fields[-1]["name"])
    offset = 8

    def take(n):
        nonlocal offset
        if offset + n > len(raw):
            raise EOFError
        result = raw[offset : offset + n]
        offset += n
        return result

    try:
        for index, field in enumerate(fields):
            meta.update(failing_field=field["name"], failing_index=index)
            v: Any
            kind = field["type"]
            if kind in ("u64", "i64"):
                v = int.from_bytes(take(8), "little", signed=kind == "i64")
            elif kind == "pubkey":
                v = str(Pubkey.from_bytes(take(32)))
            elif kind == "bool":
                b = take(1)[0]
                if b > 1:
                    return dict(meta, category="INVALID_BOOL", consumed=offset), values
                v = bool(b)
            elif kind == "string":
                n = int.from_bytes(take(4), "little")
                if n > 2048:
                    return dict(meta, category="INVALID_STRING", consumed=offset), values
                try:
                    v = take(n).decode("utf8")
                except UnicodeDecodeError:
                    return dict(meta, category="INVALID_STRING", consumed=offset), values
            elif kind == {"vec": {"defined": {"name": "Shareholder"}}}:
                n = int.from_bytes(take(4), "little")
                if n > 10:
                    return dict(meta, detail="VECTOR_BOUND", consumed=offset), values
                v = [(str(Pubkey.from_bytes(take(32))), int.from_bytes(take(2), "little")) for _ in range(n)]
            else:
                return dict(meta, category="FIELD_TYPE_UNSUPPORTED", consumed=offset), values
            values[field["name"]] = v
            meta["parsed_fields"] = index + 1
    except EOFError:
        return dict(meta, category="FIELD_BOUNDARY_FAILURE", consumed=offset), values
    meta.update(consumed=offset, remaining=len(raw) - offset)
    meta.pop("failing_field", None)
    meta.pop("failing_index", None)
    tail = raw[offset:]
    if tail:
        meta.update(
            category="KNOWN_DISCRIMINATOR_TRAILING_BYTES", trailing_sha256=hashlib.sha256(tail).hexdigest()
        )
        if len(tail) <= 64 and len(tail) % 8 == 0:
            meta.update(
                u64=list(struct.unpack("<" + "Q" * (len(tail) // 8), tail)),
                i64=list(struct.unpack("<" + "q" * (len(tail) // 8), tail)),
            )
    else:
        try:
            decode_event(encoded)
            meta["category"] = "ACCEPTED"
        except DecodeFailure as exc:
            meta["category"] = {
                "invalid_pubkey": "INVALID_PUBKEY",
                "invalid_timestamp_value": "INVALID_TIMESTAMP",
            }.get(exc.reason, "UNKNOWN_OTHER")
    # Known canonical instruction names only; arbitrary text is never reported.
    ix = values.get("ix_name", "")
    allowed = {
        "buy",
        "sell",
        "buy_exact_sol_in",
        "buy_v2",
        "buy_v3",
        "sell_v2",
        "sell_v3",
        "buy_exact_quote_in_v2",
        "buy_exact_quote_in_v3",
        "multi_hop_curve_swap",
    }
    meta.update(
        ix_name=ix if ix in allowed else "OTHER",
        side="BUY" if values.get("is_buy") else "SELL",
        ix_name_length=len(ix),
    )
    return meta, values


def scoped_events(logs):
    """Stage events until their canonical program invocation succeeds; ordinals never renumber."""
    stack: list[Any] = []
    ordinal = 0
    completed = []
    bad = False
    for line in logs[:2048]:
        if line == "Log truncated":
            bad = True
        invoke = INVOKE.match(line)
        finish = FINISH.match(line)
        if invoke:
            if int(invoke[2]) != len(stack) + 1:
                bad = True
            stack.append([invoke[1], []])
        elif finish:
            if not stack or stack[-1][0] != finish[1]:
                bad = True
                continue
            _, staged = stack.pop()
            if finish[2] == "success":
                if stack:
                    stack[-1][1].extend(staged)
                else:
                    completed.extend(staged)
        elif line.startswith("Program data: "):
            if stack and stack[-1][0] == PUMP_PROGRAM:
                stack[-1][1].append((ordinal, line[14:]))
            ordinal += 1
    return completed, bad or bool(stack) or len(logs) > 2048


async def run(seconds):
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    url = os.environ["SOLANA_RPC_URL"]
    wsurl = os.environ["SOLANA_WS_URL"]
    counts = Counter({c: 0 for c in CATEGORIES})
    lengths: Counter[str] = Counter()
    examples: list[dict[str, Any]] = []
    signatures: dict[str, None] = {}  # <=12; memory only, never persisted.
    rpc_count = 0
    async with httpx.AsyncClient(timeout=25) as client:

        async def rpc(method, params):
            nonlocal rpc_count
            rpc_count += 1
            response = await client.post(
                url, json=dict(jsonrpc="2.0", id=rpc_count, method=method, params=params)
            )
            response.raise_for_status()
            body = response.json()
            if body.get("error"):
                raise ValueError("RPC_ERROR")
            return body.get("result")

        def account_bytes(result):
            return base64.b64decode(result["value"]["data"][0], validate=True)

        program = await rpc("getAccountInfo", [PUMP_PROGRAM, dict(encoding="base64", commitment="finalized")])
        raw = account_bytes(program)
        deployment = dict(loader=program["value"]["owner"], executable=program["value"]["executable"])
        if (
            deployment["loader"] == "BPFLoaderUpgradeab1e11111111111111111111111"
            and len(raw) == 36
            and int.from_bytes(raw[:4], "little") == 2
        ):
            pd = str(Pubkey.from_bytes(raw[4:36]))
            data = await rpc(
                "getAccountInfo",
                [pd, dict(encoding="base64", commitment="finalized", dataSlice=dict(offset=0, length=45))],
            )
            d = account_bytes(data)
            if data["value"]["owner"] != deployment["loader"] or int.from_bytes(d[:4], "little") != 3:
                raise ValueError("PROGRAMDATA_IDENTITY")
            slot = int.from_bytes(d[4:12], "little")
            deployment.update(
                program_data=pd,
                slot=slot,
                block_time=await rpc("getBlockTime", [slot]),
                upgrade_authority=str(Pubkey.from_bytes(d[13:45])) if d[12] == 1 else None,
            )
        # Canonical historical Anchor IDL create_with_seed address.
        program_key = Pubkey.from_string(PUMP_PROGRAM)
        base = Pubkey.find_program_address([], program_key)[0]
        idl_address = str(Pubkey.create_with_seed(base, "anchor:idl", program_key))
        idl = await rpc("getAccountInfo", [idl_address, dict(encoding="base64", commitment="finalized")])
        idl_status = dict(
            address=idl_address, exists=idl["value"] is not None, context_slot=idl["context"]["slot"]
        )
        if idl["value"]:
            idl_status.update(
                owner=idl["value"]["owner"], data_sha256=hashlib.sha256(account_bytes(idl)).hexdigest()
            )
        start = time.monotonic()
        messages = 0
        async with websockets.connect(wsurl, max_size=2**20, max_queue=16) as ws:
            await ws.send(
                json.dumps(
                    dict(
                        jsonrpc="2.0",
                        id=101,
                        method="logsSubscribe",
                        params=[dict(mentions=[PUMP_PROGRAM]), dict(commitment="confirmed")],
                    )
                )
            )
            ack = json.loads(await asyncio.wait_for(ws.recv(), 15))
            if ack.get("id") != 101 or not isinstance(ack.get("result"), int):
                raise ValueError("SUBSCRIPTION_ACK")
            while time.monotonic() - start < seconds and messages < 100000:
                try:
                    msg = json.loads(
                        await asyncio.wait_for(
                            ws.recv(), min(5, max(0.01, seconds - (time.monotonic() - start)))
                        )
                    )
                except asyncio.TimeoutError:
                    continue
                result = msg.get("params", {}).get("result", {})
                value = result.get("value", {})
                messages += 1
                if value.get("err") is not None:
                    continue
                events, bad = scoped_events(value.get("logs", []))
                if bad:
                    counts["INVOCATION_FRAMING"] += 1
                for ordinal, encoded in events:
                    meta, fields = inspect_payload(encoded)
                    if meta.get("discriminator") != TRADE_DISCRIMINATOR.hex():
                        continue
                    counts[meta["category"]] += 1
                    length_key = str((meta.get("raw_length"), meta.get("consumed"), meta.get("remaining")))
                    lengths[length_key if length_key in lengths or len(lengths) < 64 else "OTHER"] += 1
                    if len(examples) < 24:
                        examples.append(
                            dict(
                                meta,
                                slot=result.get("context", {}).get("slot"),
                                ordinal=ordinal,
                                mint_hash=hashlib.sha256(fields.get("mint", "").encode()).hexdigest(),
                            )
                        )
                    sig = value.get("signature")
                    if sig and len(signatures) < 12 and not bad:
                        signatures.setdefault(sig, None)
        transactions: list[dict[str, Any]] = []
        # Finalized lookup after capture; no historical crawling or retry polling.
        for signature in signatures:
            try:
                tx = await rpc(
                    "getTransaction",
                    [
                        signature,
                        dict(encoding="jsonParsed", commitment="finalized", maxSupportedTransactionVersion=1),
                    ],
                )
            except (ValueError, httpx.HTTPError):
                transactions.append(
                    dict(
                        signature_hash=hashlib.sha256(signature.encode()).hexdigest(),
                        status="RPC_LOOKUP_ERROR",
                    )
                )
                continue
            if tx is None:
                transactions.append(
                    dict(
                        signature_hash=hashlib.sha256(signature.encode()).hexdigest(),
                        status="NOT_FINALIZED_OR_UNAVAILABLE",
                    )
                )
                continue
            meta_tx = tx.get("meta", {})
            if meta_tx.get("err") is not None:
                continue
            evs, bad = scoped_events(meta_tx.get("logMessages", []))
            message = tx["transaction"]["message"]
            ins = list(message.get("instructions", []))
            for inner in meta_tx.get("innerInstructions") or []:
                ins.extend(inner["instructions"])
            pump_instructions = [i for i in ins if i.get("programId") == PUMP_PROGRAM]
            keys = message["accountKeys"]
            keys = [k["pubkey"] if isinstance(k, dict) else k for k in keys]
            records = []
            for ordinal, encoded in evs:
                m, f = inspect_payload(encoded)
                if m.get("discriminator") != TRADE_DISCRIMINATOR.hex():
                    continue
                mint, user = f.get("mint"), f.get("user")
                matches = [
                    i
                    for i in pump_instructions
                    if mint in i.get("accounts", []) and user in i.get("accounts", [])
                ]
                transfers = [
                    i.get("parsed", {}) for i in ins if i.get("program") in ("spl-token", "spl-token-2022")
                ]
                # Whole-transaction matching is only corroborative in the unambiguous single-trade case.
                ntrade = sum(
                    inspect_payload(e)[0].get("discriminator") == TRADE_DISCRIMINATOR.hex() for _, e in evs
                )
                exact_token = ntrade == 1 and any(
                    str(
                        t.get("info", {}).get(
                            "amount", t.get("info", {}).get("tokenAmount", {}).get("amount")
                        )
                    )
                    == str(f.get("token_amount"))
                    for t in transfers
                )
                records.append(
                    dict(
                        m,
                        ordinal=ordinal,
                        mint_hash=hashlib.sha256((mint or "").encode()).hexdigest(),
                        mint_in_keys=mint in keys,
                        user_in_keys=user in keys,
                        matching_pump_instruction_count=len(matches),
                        token_transfer_exact_match=exact_token,
                        business_fields=dict(
                            mint="INDEPENDENTLY_CORROBORATED" if len(matches) == 1 else "AMBIGUOUS",
                            user="INDEPENDENTLY_CORROBORATED" if len(matches) == 1 else "AMBIGUOUS",
                            direction="AMBIGUOUS",
                            token_amount="INDEPENDENTLY_CORROBORATED" if exact_token else "AMBIGUOUS",
                            executed_quote="AMBIGUOUS",
                            quote_units="AMBIGUOUS",
                            timestamp="AMBIGUOUS",
                        ),
                    )
                )
            transactions.append(
                dict(
                    signature_hash=hashlib.sha256(signature.encode()).hexdigest(),
                    status="SUCCESS_FINALIZED",
                    slot=tx["slot"],
                    version=tx.get("version"),
                    framing_complete=not bad,
                    events=records,
                )
            )
        return dict(
            diagnostic_only=True,
            production_acceptance_unchanged=True,
            cohort_created=False,
            runtime=time.monotonic() - start,
            messages=messages,
            ack=True,
            reconnects=0,
            categories=dict(counts),
            lengths=dict(lengths),
            examples=examples,
            transactions=transactions,
            deployment=deployment,
            onchain_anchor_idl=idl_status,
            http_requests=rpc_count,
        )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--seconds", type=int, default=60)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if not 1 <= a.seconds <= 120:
        p.error("Duration must be 1..120 seconds")
    try:
        report = asyncio.run(run(a.seconds))
    except Exception as exc:
        print(json.dumps({"diagnostic_error_category": type(exc).__name__}), file=sys.stderr)
        raise SystemExit(1) from None
    a.output.parent.mkdir(parents=True, exist_ok=True)
    with a.output.open("x") as f:
        json.dump(report, f, indent=2, allow_nan=False)


if __name__ == "__main__":
    main()
