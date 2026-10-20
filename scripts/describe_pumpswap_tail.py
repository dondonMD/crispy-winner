"""Bounded descriptive tail statistics, never a trade decoder or strategy input."""

import argparse
import asyncio
from collections import OrderedDict
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import websockets
from solders.signature import Signature
from backend.app.onchain import parse_pool, binary_account
from backend.app.providers import SolanaProvider
from backend.app.pumpswap import PROGRAM
from scripts.diagnose_pumpswap_layout import parse_failures

MAX_OBSERVATIONS = 256
MAX_EXAMPLES = 16
FIELDS = (
    "creator_fee_unclaimed",
    "holder_rewards",
    "buyback_fee",
    "protocol_fee",
    "coin_creator_fee",
    "base_supply",
)


class Statistics:
    def __init__(self):
        self.n = 0
        self.low = self.high = self.last = None
        self.same = self.changed = 0
        self.comparisons = {
            f: dict(n=0, equal=0, equal_nonzero=0, sx=0.0, sy=0.0, xx=0.0, yy=0.0, xy=0.0) for f in FIELDS
        }

    def add(self, tail):
        value = tail["unsigned_le_u64"]
        self.n += 1
        self.low = value if self.low is None else min(value, self.low)
        self.high = value if self.high is None else max(value, self.high)
        if self.last is not None:
            self.same += value == self.last
            self.changed += value != self.last
        self.last = value
        for field, acc in self.comparisons.items():
            known = tail["documented_values_under_pinned_interpretation"].get(field)
            if type(known) is not int:
                continue
            acc["n"] += 1
            acc["equal"] += value == known
            acc["equal_nonzero"] += value == known and value != 0
            x, y = float(value), float(known)
            acc["sx"] += x
            acc["sy"] += y
            acc["xx"] += x * x
            acc["yy"] += y * y
            acc["xy"] += x * y

    def report(self):
        comparisons = {}
        for field, a in self.comparisons.items():
            vx, vy = a["n"] * a["xx"] - a["sx"] ** 2, a["n"] * a["yy"] - a["sy"] ** 2
            r = (
                (a["n"] * a["xy"] - a["sx"] * a["sy"]) / math.sqrt(vx * vy)
                if a["n"] >= 3 and vx > 0 and vy > 0
                else None
            )
            comparisons[field] = {
                "numeric_equality_label": "EXACT_MATCH",
                "tested": a["n"],
                "equal": a["equal"],
                "equal_nonzero": a["equal_nonzero"],
                "correlation_label": "CORRELATION",
                "pearson_r": None if r is None else max(-1.0, min(1.0, r)),
                "caveat": "Pinned-prefix interpretation only; equality is not semantic proof. Constant values give no correlation estimate.",
            }
        return dict(
            count=self.n,
            unsigned_min=self.low,
            unsigned_max=self.high,
            constant=self.low == self.high if self.n else None,
            arrival_order_same=self.same,
            arrival_order_changed=self.changed,
            comparisons=comparisons,
        )


def pool_numeric_prefix(account, mint, schema):
    parse_pool(account, mint)  # Existing ownership, discriminator and base-mint authority.
    raw = binary_account(account, PROGRAM, "Pool", 243)
    fields = next(t["type"]["fields"] for t in schema["types"] if t["name"] == "Pool")
    widths = {"u8": 1, "u16": 2, "u64": 8, "i128": 16, "bool": 1, "pubkey": 32}
    offset, selected = 8, {}
    for field in fields:
        kind = field["type"]
        size = widths[kind]
        if offset + size > len(raw):
            break  # Historical account suffix not present; never invent zero values.
        if field["name"] in ("protocol_fees", "creator_fees", "virtual_quote_reserves", "lp_supply"):
            selected[field["name"]] = int.from_bytes(
                raw[offset : offset + size], "little", signed=kind == "i128"
            )
        offset += size
    return selected


async def describe(pool, mint, seconds, schema, rpc=None, url=None):
    if not 1 <= seconds <= 120:
        raise ValueError("Duration bound")
    own = rpc is None
    rpc = rpc or SolanaProvider()
    before = rpc.health["requests"]
    stats = {name: Statistics() for name in ("BuyEvent", "SellEvent")}
    all_stats = Statistics()
    examples: list[dict[str, Any]] = []
    lookups: list[tuple[str, int, str]] = []
    seen = OrderedDict()
    messages = gaps = foreign = 0
    started = time.monotonic()
    last_slot = 0
    try:
        info = await rpc.rpc("getAccountInfo", [pool, {"encoding": "base64", "commitment": "confirmed"}])
        parsed = parse_pool(info["value"], mint)
        from backend.app.pumpswap import key

        for field in ("base_mint", "quote_mint", "base_account", "quote_account"):
            key(parsed[field])
        if parsed["base_mint"] == parsed["quote_mint"]:
            raise ValueError("Mint relationship")
        async with websockets.connect(
            url or os.getenv("SOLANA_WS_URL", ""),
            max_size=262144,
            max_queue=16,
            open_timeout=10,
            close_timeout=2,
            ping_interval=20,
            ping_timeout=20,
        ) as ws:
            await ws.send(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "logsSubscribe",
                        "params": [{"mentions": [pool]}, {"commitment": "confirmed"}],
                    }
                )
            )
            ack = json.loads(await asyncio.wait_for(ws.recv(), 15))
            if ack.get("id") != 1 or type(ack.get("result")) is not int:
                raise ValueError("ACK")
            sid = ack["result"]
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline and all_stats.n < MAX_OBSERVATIONS and messages < 10000:
                try:
                    message = json.loads(
                        await asyncio.wait_for(ws.recv(), min(1, max(0.001, deadline - time.monotonic())))
                    )
                except asyncio.TimeoutError:
                    continue
                if message.get("method") != "logsNotification" or message["params"]["subscription"] != sid:
                    raise ValueError("Attribution")
                messages += 1
                result = message["params"]["result"]
                value = result["value"]
                signature = value["signature"]
                Signature.from_string(signature)
                slot = result["context"]["slot"]
                if type(slot) is not int or slot < 0:
                    raise ValueError("Slot")
                if value["err"] is not None:
                    continue
                logs = value["logs"]
                if (
                    not isinstance(logs, list)
                    or len(logs) > 4096
                    or not all(isinstance(s, str) and len(s) <= 16384 for s in logs)
                ):
                    gaps += 1
                    continue
                if any("Log truncated" in line for line in logs):
                    gaps += 1
                    continue
                try:
                    failures = parse_failures(logs, pool, describe_tail=True)
                except ValueError:
                    gaps += 1
                    continue
                for ordinal, failure in failures:
                    if not failure["identity"].startswith("TARGET_"):
                        foreign += 1
                        continue
                    tail = failure.get("tail_descriptive_only")
                    identity = (signature, ordinal)
                    if tail is None or identity in seen or all_stats.n >= MAX_OBSERVATIONS:
                        continue
                    seen[identity] = True
                    # Target observations and therefore this identity cache are capped at 256.
                    stats[failure["event_name"]].add(tail)
                    all_stats.add(tail)
                    last_slot = max(last_slot, slot)
                    if len(examples) < MAX_EXAMPLES:
                        examples.append(
                            dict(
                                event=failure["event_name"],
                                signature_hash=hashlib.sha256(signature.encode()).hexdigest()[:16],
                                ordinal=ordinal,
                                slot=slot,
                                tail_sha256=failure["trailing_sha256"],
                                **tail,
                            )
                        )
                    if len(lookups) < 2 and not any(item[2] == failure["event_name"] for item in lookups):
                        lookups.append((signature, tail["unsigned_le_u64"], failure["event_name"]))
        snapshot = await rpc.rpc(
            "getAccountInfo",
            [pool, {"encoding": "base64", "commitment": "confirmed", "minContextSlot": last_slot}],
        )
        snapshot_values = pool_numeric_prefix(snapshot["value"], mint, schema)
        snapshot_matches = {
            field: {
                "label": "EXACT_MATCH",
                "equal_to_last_observed_tail": value == all_stats.last,
                "snapshot_value": value,
            }
            for field, value in snapshot_values.items()
        }
        postbalances = []
        for signature, tail_value, event_name in lookups:
            item: dict[str, Any] = {"event": event_name, "status": "UNAVAILABLE"}
            try:
                tx = await rpc.rpc(
                    "getTransaction",
                    [
                        signature,
                        {"encoding": "json", "commitment": "confirmed", "maxSupportedTransactionVersion": 1},
                    ],
                )
                if tx["meta"]["err"] is not None or tx["transaction"]["signatures"][0] != signature:
                    raise ValueError("Transaction")
                keys = tx["transaction"]["message"]["accountKeys"]
                loaded = tx["meta"].get("loadedAddresses") or {}
                keys = keys + loaded.get("writable", []) + loaded.get("readonly", [])
                pairs = {}
                for balance in tx["meta"].get("postTokenBalances", []):
                    index = balance["accountIndex"]
                    if type(index) is not int or not 0 <= index < len(keys):
                        raise ValueError("Balance index")
                    for field in ("base_account", "quote_account"):
                        if keys[index] == parsed[field]:
                            amount = int(balance["uiTokenAmount"]["amount"])
                            pairs[field] = {
                                "label": "EXACT_MATCH",
                                "raw_balance": amount,
                                "tail_equals_balance": tail_value == amount,
                            }
                item.update(status="POST_TRANSACTION_VAULT_BALANCES", comparisons=pairs)
            except Exception:
                pass
            postbalances.append(item)
        return {
            "diagnostic_only": True,
            "production_changed": False,
            "pool": pool,
            "base_mint": mint,
            "quote_mint": parsed["quote_mint"],
            "ownership_layout_verified": True,
            "acks": 1,
            "messages": messages,
            "runtime_seconds": time.monotonic() - started,
            "gaps": gaps,
            "foreign_failures": foreign,
            "all": all_stats.report(),
            "by_event": {n: s.report() for n, s in stats.items()},
            "examples": examples,
            "pool_snapshot_slot": snapshot["context"]["slot"],
            "last_event_slot": last_slot,
            "pool_snapshot_comparisons": snapshot_matches,
            "snapshot_caveat": "Later confirmed snapshot, not guaranteed immediate post-transaction state; numeric equality only.",
            "post_transaction_vault_comparisons": postbalances,
            "sequential_caveat": "Arrival order only; intra-slot chain order unknown.",
            "diagnostic_rpc_requests": rpc.health["requests"] - before,
            "max_rpc_requests": 4,
            "max_observations": MAX_OBSERVATIONS,
            "accepted_events": 0,
            "semantic_field_name": None,
        }
    finally:
        lookups.clear()
        seen.clear()
        if own:
            await rpc.close()


def main():
    from dotenv import load_dotenv

    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pool", required=True)
    parser.add_argument("--base-mint", required=True)
    parser.add_argument(
        "--schema", type=Path, required=True, help="Official SDK JSON IDL for documented pool snapshot fields"
    )
    parser.add_argument("--seconds", type=int, default=30)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Choose a unique output path")
    try:
        report = asyncio.run(
            describe(args.pool, args.base_mint, args.seconds, json.loads(args.schema.read_text()))
        )
    except Exception as exc:
        print(json.dumps({"error_type": type(exc).__name__}), file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as output:
        json.dump(report, output, indent=2, allow_nan=False)
        output.write("\n")
    print(json.dumps({k: v for k, v in report.items() if k not in ("examples",)}, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
