"""Read-only byte-boundary tracing of the unchanged production PumpSwap decoder."""
import argparse
import asyncio
from collections import OrderedDict
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from solders.signature import Signature
import websockets

from backend.app import pumpswap
from backend.app.discovery import DecodeFailure
from backend.app.providers import SolanaProvider
from scripts.validate_pumpswap_flow import verify_pool

CAUSES = ("ENCODED_STRING_TOO_LARGE", "RAW_TOO_SHORT", "KNOWN_DISCRIMINATOR_TRAILING_BYTES",
          "FIELD_TYPE_UNSUPPORTED", "FIELD_BOUNDARY_FAILURE", "UNKNOWN_OTHER")
IDENTITIES = ("TARGET_BUY_LAYOUT_FAILURE", "TARGET_SELL_LAYOUT_FAILURE", "FOREIGN_BUY_LAYOUT_FAILURE",
              "FOREIGN_SELL_LAYOUT_FAILURE", "IDENTITY_NOT_PROVABLE")
SAFE_IX_NAMES = {"buy", "buy_exact_quote_in", "buy_v2", "buy_v3", "buy_exact_quote_in_v2",
                 "buy_exact_quote_in_v3", "sell", "sell_v2", "sell_v3"}
MAX_SAMPLES = 3
MAX_MESSAGES = 10000
MAX_SEEN = 4096


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def inspect_decode(encoded, target_pool, decoder=None, describe_tail=False):
    """Trace actual production locals, never reinterpret/accept a failed payload.

    The tracing hook is synchronous, scoped to one call and restored in finally.
    Only names/offsets and identity comparisons escape; pubkeys/values do not.
    """
    decoder = decoder or pumpswap.decode_event
    state: dict[str, Any] = {"offset": 0, "result": {}, "boundaries": []}
    def trace(frame, event, arg):
        if frame.f_code is not decoder.__code__:
            return None
        local = frame.f_locals
        result = local.get("result", {})
        name = local.get("name")
        fields = pumpswap.FIELDS.get(name, [])
        offset = local.get("offset", 0)
        if len(result) > len(state["boundaries"]):
            index = len(state["boundaries"])
            if index < len(fields):
                start = state["boundaries"][-1]["end"] if index else 8
                state["boundaries"].append({"index": index, "name": fields[index]["name"],
                    "type": fields[index]["type"], "start": start, "end": offset, "bytes": offset-start})
        if event == "exception":
            # Referenced only until metadata has been sanitized below.
            state.update(offset=offset, result=result, raw=local.get("raw"), name=name,
                         field=local.get("field"), kind=local.get("kind"))
        return trace
    previous = sys.gettrace()
    try:
        sys.settrace(trace)
        return decoder(encoded), None
    except DecodeFailure as exc:
        raw = state.get("raw")
        name = state.get("name")
        result = state["result"]
        fields = pumpswap.FIELDS.get(name, [])
        offset = state["offset"]
        cause = "UNKNOWN_OTHER"
        if isinstance(encoded, str) and len(encoded) > 8192:
            cause = "ENCODED_STRING_TOO_LARGE"
        elif isinstance(raw, bytes) and len(raw) < 8:
            cause = "RAW_TOO_SHORT"
        elif exc.reason == "unsupported_layout" and name and len(result) == len(fields) and isinstance(raw, bytes) and offset != len(raw):
            cause = "KNOWN_DISCRIMINATOR_TRAILING_BYTES"
        elif exc.reason == "unsupported_layout" and name in pumpswap.FIELDS and state.get("field") and state.get("kind") not in ("pubkey", "bool", "string", "u64", "i64", "i128"):
            cause = "FIELD_TYPE_UNSUPPORTED"
        elif exc.reason == "truncated":
            cause = "FIELD_BOUNDARY_FAILURE"
        identity = "IDENTITY_NOT_PROVABLE"
        pool = result.get("pool")
        try:
            pumpswap.key(pool)
            if name in ("BuyEvent", "SellEvent"):
                identity = ("TARGET_" if pool == target_pool else "FOREIGN_") + (
                    "BUY_LAYOUT_FAILURE" if name == "BuyEvent" else "SELL_LAYOUT_FAILURE")
        except DecodeFailure:
            pass
        trailing = raw[offset:] if isinstance(raw, bytes) and offset <= len(raw) else b""
        ix = result.get("ix_name")
        metadata = {"cause": cause, "production_reason": exc.reason, "identity": identity,
            "event_name": name if name in pumpswap.FIELDS else "UNKNOWN",
            "discriminator_hex": raw[:8].hex() if isinstance(raw, bytes) and len(raw) >= 8 else None,
            "raw_length": len(raw) if isinstance(raw, bytes) else None, "final_parsed_offset": offset,
            "expected_field_count": len(fields), "parsed_field_count": len(result),
            "failing_field_index": len(result) if len(result) < len(fields) else None,
            "failing_field_name": fields[len(result)]["name"] if len(result) < len(fields) else None,
            "trailing_byte_count": len(trailing) if cause == "KNOWN_DISCRIMINATOR_TRAILING_BYTES" else None,
            "trailing_sha256": digest(trailing) if cause == "KNOWN_DISCRIMINATOR_TRAILING_BYTES" else None,
            "payload_sha256": digest(raw) if isinstance(raw, bytes) else None,
            "ix_name_length": len(ix.encode()) if isinstance(ix, str) else None,
            "ix_name_classification": ix if ix in SAFE_IX_NAMES else "OTHER_OR_ABSENT",
            "field_boundaries": state["boundaries"]}
        if describe_tail and cause == "KNOWN_DISCRIMINATOR_TRAILING_BYTES" and len(trailing) == 8:
            metadata["tail_descriptive_only"] = {
                "unsigned_le_u64": int.from_bytes(trailing, "little", signed=False),
                "signed_le_i64": int.from_bytes(trailing, "little", signed=True),
                "documented_values_under_pinned_interpretation": {field: result.get(field) for field in
                    ("creator_fee_unclaimed", "holder_rewards", "buyback_fee", "protocol_fee", "coin_creator_fee", "base_supply")}}
        return None, metadata
    finally:
        sys.settrace(previous)


def parse_failures(logs, target_pool, describe_tail=False):
    """Production invocation staging discards failed CPI frames as usual.

    Failure markers exist only inside this diagnostic call. They cannot enter
    MarketEvent or the engine; the original module function is always restored.
    """
    original = pumpswap.decode_event
    def instrumented(encoded, now=None):
        decoded, failure = inspect_decode(encoded, target_pool, original, describe_tail=describe_tail)
        return ("DIAGNOSTIC_FAILURE", failure) if failure else decoded
    try:
        pumpswap.decode_event = instrumented
        events = pumpswap.PumpSwapFlow.parse_logs(logs)
    finally:
        pumpswap.decode_event = original
    return [(ordinal, event) for ordinal, name, event in events if name == "DIAGNOSTIC_FAILURE"]


class LayoutProbe:
    def __init__(self, record):
        self.record = record
        self.counts = dict.fromkeys(CAUSES, 0)
        self.identities = dict.fromkeys(IDENTITIES, 0)
        self.ranges = {name: {metric: {"min": None, "max": None} for metric in
            ("raw_length", "final_parsed_offset", "trailing_byte_count", "parsed_field_count")}
            for name in ("BuyEvent", "SellEvent", "UNKNOWN")}
        self.ix_counts = dict.fromkeys((*sorted(SAFE_IX_NAMES), "OTHER_OR_ABSENT"), 0)
        self.event_counts = dict.fromkeys(("BuyEvent", "SellEvent", "UNKNOWN"), 0)
        self.messages = self.truncations = self.framing_failures = self.duplicates = 0
        self.samples = []
        self.examples = []
        self.seen = OrderedDict()

    def handle(self, message, subscription):
        if message.get("method") != "logsNotification" or message["params"]["subscription"] != subscription:
            raise ValueError("Unattributed notification")
        self.messages += 1
        result = message["params"]["result"]
        value = result["value"]
        signature = value["signature"]
        Signature.from_string(signature)
        slot = result["context"]["slot"]
        if type(slot) is not int or slot < 0:
            raise ValueError("Invalid slot")
        if value["err"] is not None:
            return
        logs = value["logs"]
        if not isinstance(logs, list) or len(logs) > 4096 or not all(isinstance(s, str) and len(s) <= 16384 for s in logs):
            raise ValueError("Log bounds")
        if any("Log truncated" in s for s in logs):
            self.truncations += 1
            return
        try:
            failures = parse_failures(logs, self.record.address)
        except DecodeFailure:
            self.framing_failures += 1
            return
        for ordinal, failure in failures:
            identity = (signature, ordinal)
            if identity in self.seen:
                self.duplicates += 1
                continue
            self.seen[identity] = True
            if len(self.seen) > MAX_SEEN:
                self.seen.popitem(last=False)
            self.counts[failure["cause"]] += 1
            self.identities[failure["identity"]] += 1
            self.event_counts[failure["event_name"]] += 1
            self.ix_counts[failure["ix_name_classification"]] += 1
            for metric, bounds in self.ranges[failure["event_name"]].items():
                value = failure[metric]
                if value is not None:
                    bounds["min"] = value if bounds["min"] is None else min(bounds["min"], value)
                    bounds["max"] = value if bounds["max"] is None else max(bounds["max"], value)
            example = dict(failure, signature_hash=digest(signature.encode())[:16], slot=slot, ordinal=ordinal)
            # At most one Buy, one Sell and one other variant; no arbitrary histograms.
            if len(self.examples) < MAX_SAMPLES and not any((e["event_name"], e["identity"]) ==
                    (failure["event_name"], failure["identity"]) for e in self.examples):
                self.examples.append(example)
                self.samples.append((signature, example))


async def diagnose(pool, base_mint, seconds, rpc=None, url=None):
    if not 1 <= seconds <= 300:
        raise ValueError("Duration bounds")
    own = rpc is None
    rpc = rpc or SolanaProvider()
    before = rpc.health["requests"]
    started = time.monotonic()
    started_at = time.time()
    acks = errors = 0
    probe = None
    try:
        record = await verify_pool(rpc, pool, base_mint)
        probe = LayoutProbe(record)
        async with websockets.connect(url or os.getenv("SOLANA_WS_URL", ""), max_size=262144,
                max_queue=16, open_timeout=10, close_timeout=2, ping_interval=20, ping_timeout=20) as ws:
            await ws.send(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "logsSubscribe",
                "params": [{"mentions": [record.address]}, {"commitment": "confirmed"}]}))
            deadline = time.monotonic() + seconds
            ack_deadline = time.monotonic() + 15
            subscription = None
            while time.monotonic() < deadline and probe.messages < MAX_MESSAGES:
                if subscription is None and time.monotonic() > ack_deadline:
                    raise TimeoutError("ACK")
                try:
                    raw = await asyncio.wait_for(ws.recv(), min(1, max(.001, deadline-time.monotonic())))
                except asyncio.TimeoutError:
                    continue
                message = json.loads(raw)
                if "id" in message:
                    if message["id"] != 1 or type(message.get("result")) is not int or subscription is not None:
                        raise ValueError("Invalid ACK")
                    subscription = message["result"]
                    acks += 1
                else:
                    probe.handle(message, subscription)
        corroborations = []
        for signature, observed in probe.samples:
            item = {"signature_hash": observed["signature_hash"], "ordinal": observed["ordinal"],
                    "status": "UNAVAILABLE"}
            try:
                tx = await rpc.rpc("getTransaction", [signature, {"encoding": "json", "commitment": "confirmed",
                    "maxSupportedTransactionVersion": 1}])
                if (tx["meta"]["err"] is not None or tx["transaction"]["signatures"][0] != signature
                        or tx["slot"] != observed["slot"]):
                    raise ValueError("Untrusted transaction")
                logs = tx["meta"]["logMessages"]
                if not isinstance(logs, list) or len(logs) > 4096 or any("Log truncated" in s for s in logs):
                    raise ValueError("Incomplete transaction logs")
                candidates = parse_failures(logs, record.address)
                matches = [m for ordinal, m in candidates if ordinal == observed["ordinal"]
                           and m["payload_sha256"] == observed["payload_sha256"]]
                if len(matches) != 1:
                    raise ValueError("Payload not corroborated")
                item.update(status="EXACT_CANONICAL_INVOCATION_PAYLOAD_CONFIRMED", version=tx.get("version", "legacy"),
                    payload=matches[0])
            except Exception:
                pass  # No exception text/provider URLs or raw transactions retained.
            corroborations.append(item)
        return {"diagnostic_only": True, "production_changed": False, "started_at": started_at,
            "pool": record.address, "base_mint": record.mint, "quote_mint": record.quote_mint,
            "ownership_layout_verified": True, "seconds": seconds, "runtime_seconds": time.monotonic()-started,
            "acks": acks, "transport_errors": errors, "messages": probe.messages,
            "truncations": probe.truncations, "framing_failures": probe.framing_failures,
            "duplicates": probe.duplicates, "failure_causes": probe.counts, "failure_identities": probe.identities,
            "event_counts": probe.event_counts, "byte_ranges": probe.ranges, "ix_name_counts": probe.ix_counts, "examples": probe.examples, "corroborations": corroborations,
            "diagnostic_rpc_requests": rpc.health["requests"]-before, "max_rpc_requests": 1+MAX_SAMPLES,
            "accepted_trade_events": 0, "strategy_current_claimed": False,
            "isolation": "No engine/database/cohort/research/paper state constructed"}
    finally:
        if probe:
            probe.samples.clear()  # Raw signatures are transient diagnostic lookup keys only.
        if own:
            await rpc.close()


def main():
    from dotenv import load_dotenv
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pool", required=True)
    parser.add_argument("--base-mint", required=True)
    parser.add_argument("--seconds", type=int, default=60)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Choose a unique output path")
    try:
        report = asyncio.run(diagnose(args.pool, args.base_mint, args.seconds))
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
