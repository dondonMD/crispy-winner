"""Bounded identity-only recovery of explicit logsSubscribe truncations.

Never reads transaction logs or interprets requested amounts as executed flow.
"""
import asyncio
from collections import OrderedDict
from dataclasses import dataclass
import json
from pathlib import Path
import time
from typing import Any

from solders.pubkey import Pubkey

from backend.app.discovery import PUMP_PROGRAM
from backend.app.domain import Deduplicator

SCHEMA = json.loads(Path(__file__).with_name("pump_instructions.json").read_text())
INSTRUCTIONS = {bytes(i["discriminator"]): i for i in SCHEMA["instructions"]}
EVENTS = {bytes(d) for d in SCHEMA["event_discriminators"]}
# Official Anchor 14cec14617f372b69403c6fe0c904e46a723ca3f
# lang/src/event.rs: Sha256(anchor:event)[..8], little endian.
EVENT_CPI = bytes.fromhex("e445a52e51cb9a1d")
EVENT_AUTHORITY = str(Pubkey.find_program_address([b"__event_authority"], Pubkey.from_string(PUMP_PROGRAM))[0])
BASE58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
TRADE_NAMES = {"buy", "buy_exact_sol_in", "buy_v2", "buy_v3", "buy_exact_quote_in_v2",
               "buy_exact_quote_in_v3", "sell", "sell_v2", "sell_v3"}
CLASSIFICATIONS = ("UNTRACKED_CONFIRMED", "TRACKED_AFFECTED", "UNSUPPORTED_PUMP_TRADE",
                   "TRANSACTION_UNAVAILABLE", "TRANSACTION_FAILED", "MALFORMED")


def decode_base58(value):
    if not isinstance(value, str) or len(value) > 16384:
        raise ValueError("instruction data bound")
    number = 0
    for char in value:
        number = number * 58 + BASE58.index(char)
    return b"\0" * (len(value) - len(value.lstrip("1"))) + number.to_bytes((number.bit_length() + 7) // 8, "big")


def transaction_impact(result, signature, slot, tracked):
    """Validate legacy/v0/v1 compiled instruction identities, including complete CPI data."""
    try:
        if result["slot"] != slot or type(result["slot"]) is not int:
            raise ValueError("slot mismatch")
        version = result.get("version", "legacy")
        if version != "legacy" and not (type(version) is int and version in (0, 1)):
            raise ValueError("unsupported version")
        meta = result["meta"]
        if meta["err"] is not None:
            return "TRANSACTION_FAILED", set()
        tx = result["transaction"]
        if not isinstance(tx["signatures"], list) or not tx["signatures"] or tx["signatures"][0] != signature:
            raise ValueError("signature mismatch")
        message = tx["message"]
        if version == 1:
            config = message["transactionConfig"]
            fields = {"priorityFee": 64, "computeUnitLimit": 32,
                      "loadedAccountsDataSizeLimit": 32, "heapSize": 32}
            if not isinstance(config, dict) or set(config) != set(fields):
                raise ValueError("unsupported v1 configuration")
            for field, bits in fields.items():
                value = config[field]
                if value is not None and (type(value) is not int or not 0 <= value < 2**bits):
                    raise ValueError("invalid v1 configuration")
            if "addressTableLookups" in message:
                raise ValueError("v1 cannot use lookup tables")
        elif "transactionConfig" in message:
            raise ValueError("configuration on older message")
        keys = list(message["accountKeys"])
        if not 1 <= len(keys) <= 256:
            raise ValueError("account bounds")
        lookups = message.get("addressTableLookups", [])
        if not isinstance(lookups, list) or len(lookups) > 256:
            raise ValueError("lookup bounds")
        if version == "legacy" and lookups:
            raise ValueError("legacy address lookups")
        loaded = meta.get("loadedAddresses", {"writable": [], "readonly": []})
        for kind, indexes in (("writable", "writableIndexes"), ("readonly", "readonlyIndexes")):
            addresses = loaded[kind]
            if not isinstance(addresses, list) or len(addresses) > 256:
                raise ValueError("loaded bounds")
            count = 0
            for lookup in lookups:
                Pubkey.from_string(lookup["accountKey"])
                indices = lookup[indexes]
                if not isinstance(indices, list) or any(type(i) is not int or not 0 <= i <= 255 for i in indices):
                    raise ValueError("lookup index")
                count += len(indices)
            if count != len(addresses):
                raise ValueError("missing loaded addresses")
            keys.extend(addresses)
        if len(keys) > 256:
            raise ValueError("resolved account bounds")
        for key in keys:
            Pubkey.from_string(key)
        outer = message["instructions"]
        inner = meta["innerInstructions"]  # null/missing means CPI coverage cannot be established.
        if not isinstance(outer, list) or not isinstance(inner, list) or len(outer) > 256 or len(inner) > len(outer):
            raise ValueError("instruction bounds")
        instructions = [(i, False) for i in outer]
        groups = set()
        for group in inner:
            index = group["index"]
            if type(index) is not int or not 0 <= index < len(outer) or index in groups:
                raise ValueError("inner group index")
            groups.add(index)
            if not isinstance(group["instructions"], list) or len(group["instructions"]) > 1024:
                raise ValueError("inner bounds")
            instructions.extend((i, True) for i in group["instructions"])
        if len(instructions) > 2048:
            raise ValueError("total instructions")
        affected = set()
        unsupported = False
        for instruction, is_inner in instructions:
            program = instruction["programIdIndex"]
            accounts = instruction["accounts"]
            if (type(program) is not int or not 0 <= program < len(keys) or not isinstance(accounts, list)
                    or len(accounts) > 256 or any(type(i) is not int or not 0 <= i < len(keys) for i in accounts)):
                raise ValueError("compiled account index")
            if keys[program] != PUMP_PROGRAM:
                continue
            data = decode_base58(instruction["data"])
            if (data[:8] == EVENT_CPI and is_inner and len(accounts) == 1
                    and keys[accounts[0]] == EVENT_AUTHORITY and len(data) >= 16 and data[8:16] in EVENTS):
                continue  # Canonical Anchor event emission, not a trade invocation.
            definition = INSTRUCTIONS.get(data[:8])
            if definition is None or definition["name"] == "multi_hop_curve_swap":
                unsupported = True
                continue
            required = sum(not a.get("optional", False) for a in definition["accounts"])
            if len(accounts) < required:
                raise ValueError("canonical account layout")
            if definition["name"] in TRADE_NAMES:
                if len(data) < 24:
                    raise ValueError("truncated trade arguments")
                names = [a["name"] for a in definition["accounts"]]
                position = names.index("mint" if "mint" in names else "base_mint")
                mint = keys[accounts[position]]
                if mint == str(Pubkey.default()):
                    raise ValueError("default mint")
                if tracked(mint):
                    affected.add(mint)
        if unsupported:
            return "UNSUPPORTED_PUMP_TRADE", set()
        return ("TRACKED_AFFECTED" if affected else "UNTRACKED_CONFIRMED"), affected
    except (ValueError, KeyError, TypeError, IndexError, AttributeError):
        return "MALFORMED", set()


@dataclass
class Recovery:
    signature: str
    slot: int
    observed: float
    attempts: int = 0
    next_attempt: float = 0


class TruncationRecovery:
    MAX_PENDING = 32
    MAX_ATTEMPTS = 3
    MAX_AGE = 45

    def __init__(self, rpc, tracked, local_gap, global_gap, changed):
        self.rpc, self.tracked = rpc, tracked
        self.local_gap, self.global_gap, self.changed = local_gap, global_gap, changed
        self.pending: OrderedDict[str, Recovery] = OrderedDict()
        self.seen = Deduplicator(10000)
        self.health: dict[str, Any] = {"requests": 0, "successful_requests": 0, "errors": 0, "rate_limits": 0,
                       "deduplicated": 0, "peak_pending": 0, "overflow": 0, "global_gaps": 0,
                       "token_local_gaps": 0, "classifications": dict.fromkeys(CLASSIFICATIONS, 0)}

    def submit(self, signature, slot, observed):
        if not self.seen.accept(signature):
            self.health["deduplicated"] += 1
            return
        if len(self.pending) >= self.MAX_PENDING:
            self.health["overflow"] += 1
            self.health["global_gaps"] += 1
            self.global_gap()
            return
        self.pending[signature] = Recovery(signature, slot, observed)
        self.health["peak_pending"] = max(self.health["peak_pending"], len(self.pending))
        self.changed()

    def overlaps(self, token, now, seconds=180):
        return any(r.observed >= max(now - seconds, token.trade_tracking_since) for r in self.pending.values())

    def snapshot(self):
        return {**self.health, **self.rpc.truncation_metrics, "pending": len(self.pending),
                "oldest_pending_age": max((time.time() - r.observed for r in self.pending.values()), default=0),
                "coverage_state": "PENDING RECOVERY" if self.pending else "RESOLVED"}

    def resolve(self, recovery, classification, affected=()):
        self.health["classifications"][classification] += 1
        if classification == "TRACKED_AFFECTED":
            for mint in affected:
                self.local_gap(mint, reason="recovery", now=recovery.observed)
                self.health["token_local_gaps"] += 1
        elif classification != "UNTRACKED_CONFIRMED":
            self.health["global_gaps"] += 1
            self.global_gap()
        self.pending.pop(recovery.signature, None)
        self.changed()

    async def step(self):
        # Single worker / one RPC in flight. Shared provider limiter and pressure apply.
        now = time.time()
        for expired in list(self.pending.values()):
            if now - expired.observed >= self.MAX_AGE:
                self.resolve(expired, "TRANSACTION_UNAVAILABLE")
        recovery = next((r for r in self.pending.values() if r.next_attempt <= now), None)
        if recovery is None or not self.rpc.eligible():
            return
        recovery.attempts += 1
        try:
            result = await self.rpc.rpc("getTransaction", [recovery.signature,
                {"encoding": "json", "commitment": "confirmed", "maxSupportedTransactionVersion": 1}],
                purpose="truncation")
        except (RuntimeError, ValueError, OSError):
            result = None
        if result is not None:
            classification, affected = transaction_impact(result, recovery.signature, recovery.slot, self.tracked)
            self.resolve(recovery, classification, affected)
        elif recovery.attempts >= self.MAX_ATTEMPTS:
            self.resolve(recovery, "TRANSACTION_UNAVAILABLE")
        else:
            recovery.next_attempt = time.time() + 2 ** recovery.attempts

    async def run(self):
        while True:
            await self.step()
            await asyncio.sleep(0.1)
