"""Bounded verified-pool standard WSS flow. No trade HTTP requests."""
import asyncio
import base64
import binascii
from dataclasses import dataclass
import json
import os
from pathlib import Path
import random
import struct
import time
from typing import Any
from urllib.parse import urlsplit

from solders.pubkey import Pubkey
from solders.signature import Signature
import websockets

from backend.app.discovery import DecodeFailure, FINISH, INVOKE
from backend.app.domain import Deduplicator, MarketEvent

SCHEMA = json.loads(Path(__file__).with_name("pump_amm_events.json").read_text())
PROGRAM = SCHEMA["program"]
EVENTS = {bytes(e["discriminator"]): e["name"] for e in SCHEMA["events"]}
FIELDS = {t["name"]: t["type"]["fields"] for t in SCHEMA["types"]}
QUOTES = {"So11111111111111111111111111111111111111112": ("SOL", 9),
          "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": ("USDC", 6)}
REASONS = ("truncated", "unsupported_layout", "invalid_bool", "invalid_string", "invalid_pubkey",
           "invalid_timestamp_value", "invalid_encoding", "invocation_framing", "pool_identity", "notification")


@dataclass(frozen=True)
class VerifiedPool:
    address: str
    mint: str
    quote_mint: str


def key(value):
    if not isinstance(value, str) or value == str(Pubkey.default()):
        raise DecodeFailure("invalid_pubkey")
    try:
        Pubkey.from_string(value)
    except ValueError:
        raise DecodeFailure("invalid_pubkey") from None
    return value


def decode_event(encoded, now=None):
    now = time.time() if now is None else now
    if not isinstance(encoded, str) or len(encoded) > 8192:
        raise DecodeFailure("unsupported_layout")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        raise DecodeFailure("invalid_encoding") from None
    if len(raw) < 8:
        raise DecodeFailure("truncated")
    name = EVENTS.get(raw[:8])
    if name is None:
        return None
    offset = 8

    def take(size):
        nonlocal offset
        if offset + size > len(raw):
            raise DecodeFailure("truncated")
        value = raw[offset:offset + size]
        offset += size
        return value

    result: dict[str, Any] = {}
    for field in FIELDS[name]:
        value: Any
        kind = field["type"]
        if kind == "pubkey":
            value = str(Pubkey.from_bytes(take(32)))
        elif kind == "bool":
            value = take(1)[0]
            if value not in (0, 1):
                raise DecodeFailure("invalid_bool")
            value = bool(value)
        elif kind == "string":
            size = struct.unpack("<I", take(4))[0]
            if size > 128:
                raise DecodeFailure("invalid_string")
            try:
                value = take(size).decode("utf-8")
            except UnicodeDecodeError:
                raise DecodeFailure("invalid_string") from None
        elif kind in ("u64", "i64", "i128"):
            value = int.from_bytes(take(16 if kind == "i128" else 8), "little", signed=kind != "u64")
        else:
            raise DecodeFailure("unsupported_layout")
        result[field["name"]] = value
    if offset != len(raw):
        raise DecodeFailure("unsupported_layout")
    key(result["pool"])
    key(result["user"])
    side = "in" if name == "BuyEvent" else "out"
    base = "base_amount_out" if name == "BuyEvent" else "base_amount_in"
    if (not 1_500_000_000 <= result["timestamp"] <= now + 20 or not result[base]
            or not result[f"user_quote_amount_{side}"] or not result[f"quote_amount_{side}"]):
        raise DecodeFailure("invalid_timestamp_value")
    return name, result


class PumpSwapFlow:
    capacity = 25

    def __init__(self, submit, eligible, on_gap, url=None):
        self.submit, self.eligible, self.on_gap = submit, eligible, on_gap
        self.url = os.getenv("SOLANA_WS_URL", "").strip() if url is None else url
        parsed = urlsplit(self.url)
        enabled = bool(self.url) and parsed.scheme == "wss" and bool(parsed.hostname) and not parsed.fragment
        self.pools: dict[str, VerifiedPool] = {}
        self.registry: dict[str, VerifiedPool] = {}
        self.active: dict[int, str] = {}
        self.since: dict[str, float] = {}
        self.pending: dict[int, tuple[str, str, float]] = {}
        self.sequence = 0
        self.dedup = Deduplicator(10000)
        self.health: dict[str, Any] = dict.fromkeys(("messages", "acks", "reconnects", "errors", "buy_events",
            "sell_events", "accepted", "invalid_units", "duplicates", "decode_failures", "token_local_gaps",
            "truncations", "eligible_pools", "subscribed_pools", "capacity_limited", "last_success"), 0)
        self.health.update(enabled=enabled, connected=False, attempted=False, connected_since=0, capacity=self.capacity, normal_trade_http_requests=0,
                           failure_categories=dict.fromkeys(REASONS, 0))

    def selection(self):
        # Engine returns independently verified pools in deterministic candidate priority order.
        records = self.eligible()
        unique: dict[str, VerifiedPool] = {}
        for pool in records:
            try:
                for value in (pool.address, pool.mint, pool.quote_mint):
                    key(value)
            except DecodeFailure:
                continue
            if pool.address in unique and unique[pool.address] != pool:
                raise ValueError("Conflicting verified pool identity")
            unique[pool.address] = pool
        self.registry = unique
        self.health["eligible_pools"] = len(unique)
        self.health["capacity_limited"] = max(0, len(unique) - self.capacity)
        return dict(list(unique.items())[:self.capacity])

    def coverage(self, mint, now):
        needed = {p for p, record in self.registry.items() if record.mint == mint}
        if not needed or not needed.issubset(self.since):
            return 0
        starts = [self.since[p] for p, record in self.pools.items()
                  if p in needed and record.mint == mint and p in self.since]
        return max(0, now - max(starts)) if starts and self.health["connected"] else 0

    def gap(self, pool, reason="decode", now=None):
        record = self.pools.get(pool)
        if record:
            stamp = time.time() if now is None else now
            if pool in self.since:
                self.since[pool] = stamp
            self.health["token_local_gaps"] += 1
            self.on_gap(record.mint, now=stamp)

    def disconnect(self):
        for pool in list(self.since):
            self.gap(pool, "transport")
        self.since.clear()
        self.active.clear()
        self.pending.clear()
        self.pools.clear()
        self.health.update(connected=False, subscribed_pools=0)

    async def reconcile(self, ws):
        chosen = self.selection()
        for pool, old in list(self.pools.items()):
            if chosen.get(pool) == old:
                continue
            if pool in self.since:
                self.gap(pool, "unsubscribe")
            self.since.pop(pool, None)
            # A pending subscription is allowed to ACK, then immediately removed next tick.
            for subscription, address in list(self.active.items()):
                if address == pool and not any(x[:2] == ("unsubscribe", pool) for x in self.pending.values()):
                    await self.request(ws, "unsubscribe", pool, subscription)
            if not any(x[1] == pool for x in self.pending.values()):
                self.pools.pop(pool, None)
        for pool, record in chosen.items():
            if pool in self.pools:
                continue
            # Bound all active + in-flight slots, including retiring subscriptions.
            if len(self.pools) >= self.capacity:
                break
            self.pools[pool] = record
            await self.request(ws, "subscribe", pool)
        self.health["subscribed_pools"] = len(self.since)

    async def request(self, ws, method, pool, subscription=None):
        self.sequence += 1
        self.pending[self.sequence] = (method, pool, time.time())
        params = [{"mentions": [pool]}, {"commitment": "confirmed"}] if method == "subscribe" else [subscription]
        await ws.send(json.dumps({"jsonrpc": "2.0", "id": self.sequence,
                                 "method": "logsSubscribe" if method == "subscribe" else "logsUnsubscribe", "params": params}))

    def handle(self, message, now=None):
        now = time.time() if now is None else now
        if not isinstance(message, dict):
            raise ValueError("Malformed WSS message")
        if "id" in message:
            request = self.pending.pop(message["id"], None)
            if request is None or "error" in message:
                raise ValueError("Untrusted subscription ACK")
            method, pool, _ = request
            result = message.get("result")
            if method == "subscribe":
                if not isinstance(result, int) or isinstance(result, bool) or result in self.active:
                    raise ValueError("Invalid subscription ACK")
                self.active[result] = pool
                # Eligibility may have changed while request was in flight.
                if self.selection().get(pool) == self.pools.get(pool):
                    self.since[pool] = now
            else:
                if result is not True:
                    raise ValueError("Unsubscribe rejected")
                self.active = {sid: p for sid, p in self.active.items() if p != pool}
                self.pools.pop(pool, None)
                self.since.pop(pool, None)
            self.health["acks"] += 1
            self.health["subscribed_pools"] = len(self.since)
            return
        if message.get("method") != "logsNotification":
            raise ValueError("Unexpected WSS message")
        self.health["messages"] += 1
        params = message.get("params", {})
        subscription = params.get("subscription")
        notified_pool = self.active.get(subscription)
        if notified_pool is None:
            raise ValueError("Unknown pool subscription")
        pool = notified_pool
        if pool not in self.since:
            return
        try:
            result = params["result"]
            value = result["value"]
            slot = result["context"]["slot"]
            signature = value["signature"]
            Signature.from_string(signature)
            if not isinstance(slot, int) or isinstance(slot, bool) or slot < 0:
                raise DecodeFailure("notification")
            if value["err"] is not None:
                return
            logs = value["logs"]
            if not isinstance(logs, list) or len(logs) > 4096 or not all(isinstance(s, str) and len(s) <= 16384 for s in logs):
                raise DecodeFailure("notification")
            if any("Log truncated" in s for s in logs):
                self.health["truncations"] += 1
                raise DecodeFailure("truncated")
            events = self.parse_logs(logs)
            record = self.pools[pool]
            # Validate whole notification before any submission.
            if any(event[2]["pool"] != pool for event in events):
                raise DecodeFailure("pool_identity")
            if self.registry.get(pool) != record:
                self.gap(pool, "unsubscribe", now)
                self.since.pop(pool, None)
                return
            for ordinal, name, event in events:
                identity = f"amm:{signature}:{ordinal}:{pool}"
                if not self.dedup.accept(identity):
                    self.health["duplicates"] += 1
                    continue
                side = "buy" if name == "BuyEvent" else "sell"
                self.health["buy_events" if side == "buy" else "sell_events"] += 1
                currency, decimals = QUOTES.get(record.quote_mint, ("unknown", 0))
                raw = event["user_quote_amount_in" if side == "buy" else "user_quote_amount_out"]
                valid = currency != "unknown"
                self.health["invalid_units"] += not valid
                accepted = self.submit(MarketEvent(mint=record.mint, ts=event["timestamp"], source="PumpSwap WSS",
                    kind="trade", event_id=identity, wallet=event["user"], side=side,
                    volume=raw / 10 ** decimals if valid else 0, currency=currency, signature=signature,
                    evidence={"venue": "PUMPSWAP", "pool": pool, "slot": slot, "event_ordinal": ordinal,
                              "units_valid": valid, "quote_mint": record.quote_mint,
                              "executed_quote_raw": raw, "coverage_start": self.since[pool]}))
                self.health["accepted"] += accepted is not False
            self.health["last_success"] = now
        except (KeyError, TypeError, ValueError) as exc:
            reason = exc.reason if isinstance(exc, DecodeFailure) and exc.reason in REASONS else "notification"
            self.health["decode_failures"] += 1
            self.health["failure_categories"][reason] += 1
            self.gap(pool, now=now)

    @staticmethod
    def parse_logs(logs):
        stack: list[tuple[str, list]] = []
        events: list = []
        ordinal = 0
        for line in logs:
            invocation, finish = INVOKE.match(line), FINISH.match(line)
            if invocation:
                if int(invocation[2]) != len(stack) + 1 or len(stack) >= 64:
                    raise DecodeFailure("invocation_framing")
                stack.append((invocation[1], []))
            elif finish:
                if not stack or stack[-1][0] != finish[1]:
                    raise DecodeFailure("invocation_framing")
                _, staged = stack.pop()
                if finish[2] == "success":
                    (stack[-1][1] if stack else events).extend(staged)
            elif line.startswith("Program data: "):
                ordinal += 1
                if not stack:
                    raise DecodeFailure("invocation_framing")
                if stack[-1][0] == PROGRAM:
                    decoded = decode_event(line[14:])
                    if decoded:
                        stack[-1][1].append((ordinal, *decoded))
        if stack:
            raise DecodeFailure("invocation_framing")
        return events

    async def run(self):
        delay = 1.0
        while self.health["enabled"]:
            try:
                self.health["attempted"] = True
                async with websockets.connect(self.url, max_size=262144, max_queue=16,
                        ping_interval=20, ping_timeout=20, open_timeout=15) as ws:
                    self.health.update(connected=True, connected_since=time.time())
                    connected_at = time.monotonic()
                    last_reconcile = 0.0
                    while True:
                        if time.monotonic() - last_reconcile >= 1:
                            await self.reconcile(ws)
                            last_reconcile = time.monotonic()
                        if any(time.time() - request[2] > 15 for request in self.pending.values()):
                            raise TimeoutError("Subscription ACK timeout")
                        try:
                            raw = await asyncio.wait_for(ws.recv(), timeout=1)
                        except TimeoutError:
                            continue
                        self.handle(json.loads(raw))
                        if time.monotonic() - connected_at >= 30:
                            delay = 1.0
            except asyncio.CancelledError:
                raise
            except Exception:
                self.health["errors"] += 1
            finally:
                self.disconnect()
            self.health["reconnects"] += 1
            await asyncio.sleep(delay + random.uniform(0, delay / 4))
            delay = min(60, delay * 2)
