"""Bounded standard-PubSub filter comparison; no engine, database or strategy state."""
import argparse
import base64
import asyncio
import copy
from collections import OrderedDict
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from solders.pubkey import Pubkey
from solders.signature import Signature
import websockets

from backend.app.discovery import DecodeFailure
from backend.app.pumpswap import EVENTS, PROGRAM, QUOTES, REASONS, PumpSwapFlow
from backend.app.providers import SolanaProvider
from scripts.validate_pumpswap_flow import verify_pool

MAX_MESSAGES = 20000
MAX_PROGRAM_MESSAGES = 1000
MAX_EXAMPLES = 3
MAX_SEEN = 4096
MAX_HTTP_SAMPLES = 3


def address_placement(transaction, pool, mint):
    """Only accept raw JSON account keys; parsed keys have different semantics."""
    if not isinstance(transaction, dict) or transaction.get("meta", {}).get("err") is not None:
        raise ValueError("Untrusted transaction")
    message = transaction["transaction"]["message"]
    static = message["accountKeys"]
    loaded = transaction["meta"].get("loadedAddresses") or {}
    writable, readonly = loaded.get("writable", []), loaded.get("readonly", [])
    if not all(isinstance(keys, list) and len(keys) <= 256 for keys in (static, writable, readonly)):
        raise ValueError("Invalid key arrays")
    if len(static + writable + readonly) > 256:
        raise ValueError("Resolved key bounds")
    version = transaction.get("version", "legacy")
    if version != 0 and (writable or readonly):
        raise ValueError("Loaded addresses on non-v0 message")
    for address in static + writable + readonly:
        Pubkey.from_string(address)  # System Program is a valid default-valued account key.
    def location(address):
        return [label for label, keys in (("STATIC", static), ("ALT_WRITABLE", writable),
                                         ("ALT_READONLY", readonly)) if address in keys] or ["ABSENT"]
    version = transaction.get("version", "legacy")
    if version not in ("legacy", 0, 1) or isinstance(version, bool):
        raise ValueError("Unsupported version")
    return {"version": version, "pool": location(pool), "base_mint": location(mint)}


class Comparison:
    def __init__(self, record):
        self.record = record
        self.sequence = 0
        self.pending = {}
        self.active = {}
        self.seen = OrderedDict()
        self.samples = OrderedDict()
        self.notification_samples = OrderedDict()
        self.payload_shapes: dict[str, dict[str, Any]] = {name: dict(count=0, min_bytes=None, max_bytes=None)
                               for name in ("BuyEvent", "SellEvent")}
        self.filters: dict[str, dict[str, Any]] = {name: dict(requests=0, acks=0, messages=0, target_buys=0, target_sells=0,
                                  foreign_events=0, accepted_units=0, unknown_units=0, duplicates=0,
                                  truncations=0, decode_failures=0, failed_transactions=0,
                                  cross_filter_duplicates=0, examples=[], ack_ids=[],
                                  failure_categories=dict.fromkeys((*REASONS, "other"), 0))
                        for name in ("pool", "mint", "program")}
        self.unique = OrderedDict()
        self.errors = 0
        self.reconnects = 0
        self.connections = 0
        self.total_messages = 0

    async def subscribe(self, ws, name):
        self.sequence += 1
        self.pending[self.sequence] = name
        address = {"pool": self.record.address, "mint": self.record.mint, "program": PROGRAM}[name]
        self.filters[name]["requests"] += 1
        await ws.send(json.dumps({"jsonrpc": "2.0", "id": self.sequence, "method": "logsSubscribe",
                                  "params": [{"mentions": [address]}, {"commitment": "confirmed"}]}))

    def disconnected(self):
        self.active.clear()
        self.pending.clear()

    @staticmethod
    def remember(mapping, identity):
        duplicate = identity in mapping
        mapping[identity] = True
        mapping.move_to_end(identity)
        if len(mapping) > MAX_SEEN:
            mapping.popitem(last=False)
        return duplicate

    def handle(self, message):
        if not isinstance(message, dict):
            raise ValueError("Invalid notification")
        if "id" in message:
            name = self.pending.pop(message["id"], None)
            sid = message.get("result")
            if name is None or "error" in message or type(sid) is not int or sid in self.active:
                raise ValueError("Invalid ACK")
            self.active[sid] = name
            count = self.filters[name]
            count["acks"] += 1
            # Bounded ACK history, including independent request/subscription attribution.
            if len(count["ack_ids"]) < 8:
                count["ack_ids"].append({"request_id": message["id"], "subscription_id": sid})
            return
        if message.get("method") != "logsNotification":
            raise ValueError("Unexpected method")
        params = message["params"]
        name = self.active[params["subscription"]]
        count = self.filters[name]
        count["messages"] += 1
        self.total_messages += 1
        try:
            result = params["result"]
            value = result["value"]
            signature = value["signature"]
            Signature.from_string(signature)
            slot = result["context"]["slot"]
            if type(slot) is not int or slot < 0:
                raise ValueError("Invalid slot")
            if value["err"] is not None:
                count["failed_transactions"] += 1
                return
            if name == "pool" and len(self.notification_samples) < MAX_HTTP_SAMPLES:
                self.notification_samples.setdefault(signature, slot)
            logs = value["logs"]
            if not isinstance(logs, list) or len(logs) > 4096 or not all(
                    isinstance(line, str) and len(line) <= 16384 for line in logs):
                raise ValueError("Invalid logs")
            if any("Log truncated" in line for line in logs):
                count["truncations"] += 1
                return
            # Shape diagnostics confer no identity/amount validity and retain no payloads.
            for line in logs:
                if line.startswith("Program data: ") and len(line) <= 8206:
                    try:
                        raw = base64.b64decode(line[14:], validate=True)
                        event_type = EVENTS.get(raw[:8])
                        if event_type:
                            shape = self.payload_shapes[event_type]
                            shape["count"] += 1
                            shape["min_bytes"] = min(shape["min_bytes"] or len(raw), len(raw))
                            shape["max_bytes"] = max(shape["max_bytes"] or len(raw), len(raw))
                    except ValueError:
                        pass
            events = PumpSwapFlow.parse_logs(logs)
            for ordinal, event_name, event in events:
                if event["pool"] != self.record.address:
                    count["foreign_events"] += 1
                    continue
                identity = f"amm:{signature}:{ordinal}:{self.record.address}"
                if self.remember(self.seen, (name, identity)):
                    count["duplicates"] += 1
                    continue
                if self.remember(self.unique, identity):
                    count["cross_filter_duplicates"] += 1
                side = "buy" if event_name == "BuyEvent" else "sell"
                count["target_buys" if side == "buy" else "target_sells"] += 1
                if self.record.quote_mint not in QUOTES:
                    count["unknown_units"] += 1
                else:
                    count["accepted_units"] += 1
                if len(self.samples) < MAX_HTTP_SAMPLES and signature not in self.samples:
                    self.samples[signature] = slot
                if len(count["examples"]) < MAX_EXAMPLES:
                    count["examples"].append({"signature_hash": hashlib.sha256(signature.encode()).hexdigest()[:16],
                        "pool": self.record.address, "ordinal": ordinal, "side": side, "slot": slot})
        except Exception as exc:
            reason = exc.reason if isinstance(exc, DecodeFailure) and exc.reason in REASONS else "other"
            count["failure_categories"][reason] += 1
            # No exception text or raw payload can leak into diagnostics.
            count["decode_failures"] += 1

    def statuses(self):
        result = []
        for name, count in self.filters.items():
            if count["target_buys"] + count["target_sells"]:
                result.append(f"{name.upper()}_FILTER_TARGET_EVENTS")
            elif count["acks"]:
                result.append(f"{name.upper()}:" + ("ACK_WITH_NO_NOTIFICATIONS" if not count["messages"]
                                                   else "NOTIFICATIONS_WITHOUT_TARGET_EVENTS"))
        if self.errors:
            result.append("TRANSPORT_FAILURE")
        if not any(c["target_buys"] + c["target_sells"] for c in self.filters.values()):
            result.append("INCONCLUSIVE_NO_CONFIRMED_TARGET_ACTIVITY")
        return result


async def diagnose(pool, base_mint, seconds=120, program_seconds=0, rpc=None, url=None):
    if not 1 <= seconds <= 600 or not 0 <= program_seconds <= 15:
        raise ValueError("Invalid duration")
    own_rpc = rpc is None
    rpc = rpc or SolanaProvider()
    try:
        before = rpc.health["requests"]
        record = await verify_pool(rpc, pool, base_mint)
        probe = Comparison(record)
        started = time.monotonic()
        started_at = time.time()
        comparison_snapshot = None
        deadline = started + seconds
        program_deadline = None
        program_used = False
        stop_reason = "duration"
        while time.monotonic() < deadline:
            try:
                async with websockets.connect(url or os.getenv("SOLANA_WS_URL", ""), max_size=262144,
                        max_queue=16, open_timeout=10, close_timeout=2, ping_interval=20, ping_timeout=20) as ws:
                    probe.connections += 1
                    if probe.connections > 1:
                        probe.reconnects += 1
                    await probe.subscribe(ws, "pool")
                    await probe.subscribe(ws, "mint")
                    ack_deadline = time.monotonic() + 15
                    while time.monotonic() < deadline:
                        if probe.pending and time.monotonic() > ack_deadline:
                            raise TimeoutError("ACK timeout")
                        if probe.total_messages >= MAX_MESSAGES:
                            stop_reason = "message_bound"
                            deadline = time.monotonic()
                            break
                        try:
                            raw = await asyncio.wait_for(ws.recv(), min(1, max(.001, deadline-time.monotonic())))
                        except asyncio.TimeoutError:
                            continue
                        probe.handle(json.loads(raw))
                    comparison_snapshot = copy.deepcopy(probe.filters)
                    no_target = not any(c["target_buys"] + c["target_sells"] for c in probe.filters.values())
                    if no_target and program_seconds and not program_used and stop_reason == "duration":
                        program_used = True
                        program_deadline = time.monotonic() + program_seconds
                        await probe.subscribe(ws, "program")
                        while time.monotonic() < program_deadline and probe.total_messages < MAX_MESSAGES:
                            if probe.filters["program"]["messages"] >= MAX_PROGRAM_MESSAGES:
                                break
                            try:
                                raw = await asyncio.wait_for(ws.recv(), min(1, max(.001, program_deadline-time.monotonic())))
                            except asyncio.TimeoutError:
                                continue
                            probe.handle(json.loads(raw))
            except Exception:
                probe.errors += 1
                probe.disconnected()
                if time.monotonic() < deadline:
                    await asyncio.sleep(min(1, max(0, deadline-time.monotonic())))
        placements = []
        samples = probe.samples or probe.notification_samples
        for signature, slot in samples.items():
            entry = {"signature_hash": hashlib.sha256(signature.encode()).hexdigest()[:16], "slot": slot,
                     "sample_basis": "DECODED_TARGET_EVENT" if probe.samples else "POOL_MENTION_ONLY"}
            try:
                transaction = await rpc.rpc("getTransaction", [signature, {"encoding": "json",
                    "commitment": "confirmed", "maxSupportedTransactionVersion": 1}])
                entry.update(address_placement(transaction, record.address, record.mint))
            except Exception:
                entry["classification"] = "UNAVAILABLE_OR_MALFORMED"
            placements.append(entry)
        return {"diagnostic_only": True, "production_changed": False,
            "isolation": "No engine, database, cohort, research, scoring or paper state instantiated",
            "pool": record.address, "base_mint": record.mint, "quote_mint": record.quote_mint,
            "ownership_layout_verified": True, "commitment": "confirmed",
            "started_at": started_at,
            "comparison_window_filters": comparison_snapshot,
            "runtime_seconds": time.monotonic() - started, "comparison_seconds": seconds,
            "optional_program_seconds": program_seconds if program_used else 0,
            "filters": probe.filters, "statuses": probe.statuses(), "connections": probe.connections,
            "reconnects": probe.reconnects, "errors": probe.errors, "stop_reason": stop_reason,
            "transaction_samples": placements,
            "unvalidated_discriminator_payload_shapes": probe.payload_shapes, "diagnostic_http_requests": rpc.health["requests"] - before,
            "http_sample_limit": MAX_HTTP_SAMPLES, "message_limit": MAX_MESSAGES,
            "program_message_limit": MAX_PROGRAM_MESSAGES, "normal_path_trade_http_delta": 0,
            "strategy_current_claimed": False}
    finally:
        if own_rpc:
            await rpc.close()


def main():
    from dotenv import load_dotenv
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pool", required=True)
    parser.add_argument("--base-mint", required=True)
    parser.add_argument("--seconds", type=int, default=120)
    parser.add_argument("--program-seconds", type=int, default=0, help="Optional fallback only, hard maximum 15s/1000 messages")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Choose a unique output filename")
    try:
        report = asyncio.run(diagnose(args.pool, args.base_mint, args.seconds, args.program_seconds))
    except Exception as exc:
        print(json.dumps({"diagnostic_only": True, "error_type": type(exc).__name__}), file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as output:
        json.dump(report, output, indent=2, allow_nan=False)
        output.write("\n")
    print(json.dumps(report, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
