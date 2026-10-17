"""Bounded, standard Solana log discovery. No HTTP requests or trade subscriptions."""

from collections import deque
import asyncio
import base64
import binascii
import json
import os
import random
import re
import struct
import time
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit

import websockets
from solders.pubkey import Pubkey
from solders.signature import Signature

from backend.app.domain import Deduplicator, MarketEvent
from backend.app.providers import PUMP_PROGRAM

SCHEMA = json.loads(Path(__file__).with_name("pump_events.json").read_text())
EVENTS = {bytes(e["discriminator"]): e["name"] for e in SCHEMA["events"]}
FIELDS = {t["name"]: t["type"]["fields"] for t in SCHEMA["types"]}
INVOKE = re.compile(r"^Program ([1-9A-HJ-NP-Za-km-z]{32,44}) invoke \[(\d+)\]$")
FINISH = re.compile(r"^Program ([1-9A-HJ-NP-Za-km-z]{32,44}) (success|failed:.*)$")


class DiscoveryProvider(Protocol):
    health: dict[str, Any]

    async def run(self) -> None: ...


FAILURE_REASONS = (
    "truncated", "unsupported_layout", "invalid_bool", "invalid_string", "invalid_pubkey",
    "invalid_timestamp_value", "invocation_framing", "invalid_encoding", "outer_notification", "other",
)
FAILURE_EVENTS = tuple(e["name"] for e in SCHEMA["events"]) + ("unknown", "notification")
TRADE_DISCRIMINATOR = next(k for k, v in EVENTS.items() if v == "TradeEvent")


class DecodeFailure(ValueError):
    """Fixed diagnostic category; never includes payloads, addresses or wallets."""

    def __init__(self, reason, detail="other"):
        super().__init__(reason)
        self.reason = reason
        self.detail = detail


def event_prefix(encoded: str) -> tuple[str, str | None]:
    """Read only discriminator and TradeEvent mint, even if its tail is corrupt.

    Partial base64 quanta are padded locally; ignored low bits cannot affect any
    recovered complete byte. Every 32-byte nondefault key is a valid Solana key;
    trading users/PDAs are not required to be on the Ed25519 curve.
    """
    def prefix(length):
        chars = (length * 8 + 5) // 6
        if len(encoded) < chars:
            raise DecodeFailure("truncated")
        part = encoded[:chars]
        try:
            return base64.b64decode(part + "=" * (-len(part) % 4), validate=True)
        except (ValueError, binascii.Error):
            raise DecodeFailure("invalid_encoding") from None

    name = EVENTS.get(prefix(8), "unknown")
    if name != "TradeEvent":
        return name, None
    raw = prefix(40)
    mint = str(Pubkey.from_bytes(raw[8:40]))
    if mint == str(Pubkey.default()):
        raise DecodeFailure("invalid_pubkey")
    return name, mint


def decode_event(encoded: str) -> tuple[str, dict] | None:
    """Strict pinned TradeEvent layout; unchanged create/migration prefixes."""
    if len(encoded) > 16384:
        raise DecodeFailure("unsupported_layout")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        raise DecodeFailure("invalid_encoding") from None
    name = EVENTS.get(raw[:8])
    if name is None:
        return None
    offset = 8
    result: dict[str, Any] = {}

    def take(size):
        nonlocal offset
        if offset + size > len(raw):
            raise DecodeFailure("truncated")
        value = raw[offset:offset + size]
        offset += size
        return value

    for field in FIELDS[name]:
        value: Any
        kind = field["type"]
        if kind == "string":
            length = struct.unpack("<I", take(4))[0]
            if length > 2048:
                raise DecodeFailure("invalid_string")
            data = take(length)
            try:
                value = data.decode("utf-8")
            except UnicodeDecodeError:
                raise DecodeFailure("invalid_string") from None
        elif kind == "pubkey":
            value = str(Pubkey.from_bytes(take(32)))
        elif kind == "bool":
            value = take(1)[0]
            if value not in (0, 1):
                raise DecodeFailure("invalid_bool")
            value = bool(value)
        elif isinstance(kind, dict) and kind == {"vec": {"defined": {"name": "Shareholder"}}}:
            length = struct.unpack("<I", take(4))[0]
            if length > 10:
                raise DecodeFailure("unsupported_layout")
            value = []
            for _ in range(length):
                address = str(Pubkey.from_bytes(take(32)))
                share = struct.unpack("<H", take(2))[0]
                if share > 10000:
                    raise DecodeFailure("invalid_timestamp_value")
                value.append((address, share))
        elif kind in ("u64", "i64"):
            value = struct.unpack("<Q" if kind == "u64" else "<q", take(8))[0]
        else:
            raise DecodeFailure("unsupported_layout")
        result[field["name"]] = value
        if field["name"] == "timestamp" and name != "TradeEvent":
            break
    if name == "TradeEvent":
        if offset != len(raw):
            raise DecodeFailure("unsupported_layout")
        if (result["mint"] == str(Pubkey.default()) or result["user"] == str(Pubkey.default())):
            raise DecodeFailure("invalid_pubkey")
        if (not result["token_amount"] or not (result["quote_amount"] or result["sol_amount"])
                or not 1_500_000_000 <= result["timestamp"] <= time.time() + 60):
            raise DecodeFailure("invalid_timestamp_value")
        return name, result
    mint = Pubkey.from_string(result["mint"])
    curve = Pubkey.find_program_address([b"bonding-curve", bytes(mint)], Pubkey.from_string(PUMP_PROGRAM))[0]
    if result["bonding_curve"] != str(curve):
        raise DecodeFailure("invalid_pubkey")
    if result["timestamp"] <= 0:
        raise DecodeFailure("invalid_timestamp_value")
    if name == "CompletePumpAmmMigrationEvent":
        result["pool"] = str(Pubkey.from_bytes(take(32)))
    return name, result


class OnchainPumpDiscovery:
    def __init__(self, submit, url=None, tracked=None, on_gap=None, quote_for=None, on_trade_gap=None, on_truncation=None):
        self.on_truncation = on_truncation
        self.submit = submit
        self.tracked = tracked or (lambda mint: False)
        self.on_gap = on_gap or (lambda: None)
        # Missing local callback must remain fail-closed for standalone consumers.
        self.on_trade_gap = on_trade_gap or (lambda mint: self.global_gap("unknown_trade_identity"))
        self.quote_for = quote_for or (lambda mint: "")
        self.url = os.getenv("SOLANA_WS_URL", "").strip() if url is None else url
        self.seen = Deduplicator(10000)
        self.connected_intervals: deque[tuple[float, float]] = deque(maxlen=32)
        self.health: dict[str, Any] = {
            "trade_events_prefix_classified": 0,
            "untracked_trades_prefix_filtered": 0,
            "tracked_trades_fully_decoded": 0,
            "tracked_trade_decode_failures": 0,
            "unknown_mint_decode_failures": 0,
            "global_continuity_resets": 0,
            "per_token_decode_resets": 0,
            "global_reset_reasons": dict.fromkeys(("transport", "shutdown", "unknown_trade_identity",
                                                   "invocation_framing", "outer_notification", "event_decode", "log_truncation", "truncation_recovery"), 0),
            "framing_failure_details": dict.fromkeys(("depth_mismatch", "unbalanced_finish",
                                                     "unfinished_invocations", "other"), 0),
            "log_truncation_notifications": 0,
            "balanced_log_truncation_gaps": 0,
            "no_event_log_truncation_gaps": 0,
            "framing_with_log_truncation": 0,
            "framing_without_log_truncation": 0,
            "decode_failures_by_reason": dict.fromkeys(FAILURE_REASONS, 0),
            "decode_failures_by_event": dict.fromkeys(FAILURE_EVENTS, 0),
            "decode_failure_matrix": {name: dict.fromkeys(FAILURE_REASONS, 0) for name in FAILURE_EVENTS},
            "diagnostic_discriminators": {name: key.hex() for key, name in EVENTS.items()},
            "trade_events": 0, "tracked_trades": 0, "untracked_trades": 0,
            "duplicate_trades": 0, "invalid_unit_trades": 0,
            "last_disconnect": 0, "reconnected_at": 0, "last_decode_gap": 0,
            "outage_trade_loss": "UNKNOWN — no backfill",
            "enabled": bool(self.url),
            "attempted": False,
            "connected": False,
            "last_attempt": 0,
            "last_success": 0,
            "last_event": 0,
            "connected_since": 0,
            "errors": 0,
            "reconnects": 0,
            "messages": 0,
            "launch_events": 0,
            "migration_events": 0,
            "ignored_events": 0,
            "decoding_errors": 0,
            "duplicates": 0,
            "enrichment_attempts": 0,
            "enrichment_successes": 0,
            "enrichment_failures": 0,
            "http_requests": 0,
            "reconnect_level": 0,
            "subscriptions": 0,
            "transport_transitions": [],
            "configuration_error": False,
        }
        try:
            parsed = urlsplit(self.url)
            if self.url and (parsed.scheme != "wss" or not parsed.hostname or parsed.fragment):
                raise ValueError("a valid wss endpoint is required")
        except ValueError:
            self.health["configuration_error"] = True
            self.health["enabled"] = False

    def record_transport_transition(self, state):
        history = self.health["transport_transitions"]
        history.append({"at": time.time(), "state": state})
        del history[:-32]

    def record_decode_failure(self, name, exc):
        name = name if name in FAILURE_EVENTS else "unknown"
        reason = exc.reason if isinstance(exc, DecodeFailure) else "other"
        reason = reason if reason in FAILURE_REASONS else "other"
        self.health["decode_failures_by_reason"][reason] += 1
        self.health["decode_failures_by_event"][name] += 1
        self.health["decode_failure_matrix"][name][reason] += 1
        if reason == "invocation_framing":
            detail = exc.detail if isinstance(exc, DecodeFailure) else "other"
            detail = detail if detail in self.health["framing_failure_details"] else "other"
            self.health["framing_failure_details"][detail] += 1
        self.health["decoding_errors"] += 1
        self.health["errors"] += 1

    def global_gap(self, reason):
        reason = reason if reason in self.health["global_reset_reasons"] else "outer_notification"
        self.health["global_continuity_resets"] += 1
        self.health["global_reset_reasons"][reason] += 1
        if reason not in ("transport", "shutdown"):
            self.health["last_decode_gap"] = time.time()
        self.on_gap()

    def receive(self, payload):
        """Synchronous bounded decode/submit, independent of HTTP RPC availability."""
        self.health["messages"] += 1
        self.health["last_success"] = time.time()
        recovering = False
        try:
            if not isinstance(payload, dict) or payload.get("method") != "logsNotification":
                self.health["ignored_events"] += 1
                return
            result = payload["params"]["result"]
            slot = result["context"]["slot"]
            value = result["value"]
            if type(slot) is not int or slot < 0:
                raise ValueError("invalid slot")
            if value["err"] is not None:
                self.health["ignored_events"] += 1
                return
            logs = value["logs"]
            if (
                not isinstance(logs, list)
                or len(logs) > 2048
                or any(not isinstance(line, str) or len(line) > 20000 for line in logs)
            ):
                raise ValueError("invalid logs")
            log_truncated = any(line == "Log truncated" for line in logs)
            self.health["log_truncation_notifications"] += log_truncated
            signature = str(Signature.from_string(value["signature"]))
            if log_truncated and self.on_truncation is not None:
                self.on_truncation(signature, slot, time.time())
                recovering = True
            if not any(line.startswith("Program data: ") for line in logs):
                if log_truncated:
                    self.health["no_event_log_truncation_gaps"] += 1
                    if not recovering:
                        self.global_gap("log_truncation")
                self.health["ignored_events"] += 1
                return
            # Stage events inside invocation frames. A caught failed CPI must not
            # supply evidence, even if the overall transaction later succeeds.
            frames: list[tuple[str, list]] = []
            decoded: list[tuple[str, dict]] = []
            for line in logs:
                if match := INVOKE.fullmatch(line):
                    if int(match[2]) != len(frames) + 1 or len(frames) >= 64:
                        raise DecodeFailure("invocation_framing", "depth_mismatch")
                    frames.append((match[1], []))
                elif match := FINISH.fullmatch(line):
                    if not frames or frames[-1][0] != match[1]:
                        raise DecodeFailure("invocation_framing", "unbalanced_finish")
                    _, events = frames.pop()
                    if match[2] == "success":
                        (frames[-1][1] if frames else decoded).extend(events)
                elif line.startswith("Program data: ") and frames and frames[-1][0] == PUMP_PROGRAM:
                    name = "unknown"
                    mint = None
                    try:
                        # Recover the discriminator independently so a broken mint
                        # still has an explicit TradeEvent diagnostic category.
                        try:
                            name = EVENTS.get(base64.b64decode(line[14:25] + "=", validate=True), "unknown")
                        except (ValueError, binascii.Error):
                            pass
                        if name == "TradeEvent":
                            self.health["trade_events_prefix_classified"] += 1
                            _, mint = event_prefix(line[14:])
                            if not self.tracked(mint):
                                self.health["untracked_trades_prefix_filtered"] += 1
                                # A placeholder keeps the supported-event ordinal
                                # stable despite filtering or membership changes.
                                frames[-1][1].append((name, {"_filtered": True, "mint": mint}))
                                continue
                        decoded_event = decode_event(line[14:])
                    except (ValueError, TypeError, IndexError, struct.error, binascii.Error) as exc:
                        self.record_decode_failure(name, exc)
                        if name == "TradeEvent" and mint is not None:
                            self.health["tracked_trade_decode_failures"] += 1
                            if not recovering:
                                self.health["per_token_decode_resets"] += 1
                                self.on_trade_gap(mint)
                        else:
                            if name == "TradeEvent":
                                self.health["unknown_mint_decode_failures"] += 1
                            if not recovering:
                                self.global_gap("unknown_trade_identity" if name == "TradeEvent" else "event_decode")
                        # Preserve ordinal even for a supported malformed event.
                        if name in FAILURE_EVENTS[:3]:
                            frames[-1][1].append((name, {"_invalid": True}))
                        continue
                    if decoded_event is not None:
                        frames[-1][1].append(decoded_event)
            if frames:
                raise DecodeFailure("invocation_framing", "unfinished_invocations")
            if log_truncated:
                # Visible frames can balance despite omitted logs. Keep the existing
                # decoded create/migration behavior, but never claim complete flow.
                self.health["balanced_log_truncation_gaps"] += 1
                if not recovering:
                    self.global_gap("log_truncation")
            if not decoded:
                self.health["ignored_events"] += 1
                return
            # One transaction may contain several creates; deduplicate the whole
            # notification only after decoding all events successfully.
            full_trades = sum(n == "TradeEvent" and not f.get("_filtered") and not f.get("_invalid")
                              for n, f in decoded)
            self.health["trade_events"] += full_trades
            self.health["tracked_trades_fully_decoded"] += full_trades
            if not self.seen.accept(signature):
                self.health["duplicate_trades"] += full_trades
                self.health["duplicates"] += 1
                return
            for ordinal, (name, fields) in enumerate(decoded):
                if fields.get("_invalid"):
                    continue
                if name == "TradeEvent":
                    if fields.get("_filtered") or not self.tracked(fields["mint"]):
                        self.health["untracked_trades"] += 1
                        continue
                    quote = fields["quote_mint"]
                    account_quote = self.quote_for(fields["mint"])
                    account_sol = (
                        quote == str(Pubkey.default())
                        and account_quote == "So11111111111111111111111111111111111111112"
                    )
                    legacy_sol = (
                        account_sol
                        and fields["ix_name"] in ("buy", "sell", "buy_exact_sol_in")
                        and fields["quote_amount"] == 0
                    )
                    if account_sol:
                        quote = account_quote
                    elif account_quote and quote != account_quote:
                        quote = ""  # Conflicting canonical account/event identities fail closed.
                    currency, decimals = {
                        "So11111111111111111111111111111111111111112": ("SOL", 9),
                        "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": ("USDC", 6),
                    }.get(quote, ("unknown", 0))
                    amount = fields["sol_amount"] if legacy_sol else fields["quote_amount"]
                    if currency == "unknown" or not amount:
                        currency, amount = "unknown", 0
                        self.health["invalid_unit_trades"] += 1
                    event = MarketEvent(
                        kind="trade", mint=fields["mint"], wallet=fields["user"],
                        side="buy" if fields["is_buy"] else "sell",
                        volume=amount / 10**decimals, currency=currency,
                        ts=fields["timestamp"], source="Solana WSS", signature=signature,
                        event_id=f"{signature}:trade:{ordinal}",
                        evidence={"slot": slot, "event_ordinal": ordinal, "units_valid": currency != "unknown",
                                  "quote_mint": quote, "quote_source": "verified curve" if account_sol else "event",
                                  "canonical_trade": fields},
                    )
                    if self.submit(event):
                        self.health["tracked_trades"] += 1
                    continue
                kind = "create" if name == "CreateEvent" else "migration"
                evidence = {
                    "data_quality": "VERIFIED",
                    "slot": slot,
                    "chain_timestamp": fields["timestamp"],
                    "commitment": "confirmed",
                    "program": PUMP_PROGRAM,
                    "discovery_source": "Solana program logs",
                }
                if kind == "create":
                    evidence["launch_metadata"] = {
                        "bondingCurveKey": fields["bonding_curve"],
                        "uri": fields["uri"],
                        "source": "ONCHAIN",
                    }
                event = MarketEvent(
                    mint=fields["mint"],
                    ts=fields["timestamp"],
                    source="Onchain Pump",
                    kind=kind,
                    event_id=f"{signature}:{kind}:{fields['mint']}",
                    signature=signature,
                    name=fields.get("name", "")[:100],
                    symbol=fields.get("symbol", "")[:30],
                    creator=fields.get("creator", ""),
                    pair=fields.get("pool", ""),
                    evidence=evidence,
                )
                self.health["launch_events" if kind == "create" else "migration_events"] += 1
                self.health["last_event"] = time.time()
                self.submit(event)
        except (ValueError, TypeError, KeyError, IndexError, struct.error, binascii.Error) as exc:
            failure = exc if isinstance(exc, DecodeFailure) else DecodeFailure("outer_notification")
            self.record_decode_failure("notification", failure)
            if failure.reason == "invocation_framing":
                key = "framing_with_log_truncation" if any(line == "Log truncated" for line in logs) else "framing_without_log_truncation"
                self.health[key] += 1
            if not recovering:
                self.global_gap(failure.reason if failure.reason == "invocation_framing" else "outer_notification")

    async def run(self):
        if not self.health["enabled"]:
            return
        attempt = 0
        try:
            while True:
                try:
                    self.health.update(attempted=True, last_attempt=time.time())
                    async with websockets.connect(
                        self.url,
                        max_size=262144,
                        max_queue=16,
                        open_timeout=15,
                        ping_interval=20,
                        ping_timeout=20,
                        close_timeout=5,
                    ) as ws:
                        await ws.send(
                            json.dumps(
                                {
                                    "jsonrpc": "2.0",
                                    "id": 1,
                                    "method": "logsSubscribe",
                                    "params": [{"mentions": [PUMP_PROGRAM]}, {"commitment": "confirmed"}],
                                }
                            )
                        )
                        ack = json.loads(await asyncio.wait_for(ws.recv(), timeout=15))
                        if (
                            not isinstance(ack, dict)
                            or ack.get("id") != 1
                            or type(ack.get("result")) is not int
                        ):
                            raise ValueError("subscription rejected")
                        subscription = ack["result"]
                        connected_at = time.monotonic()
                        self.health.update(
                            connected=True,
                            connected_since=time.time(),
                            reconnected_at=time.time(),
                            subscriptions=1,
                            last_success=time.time(),
                        )
                        self.record_transport_transition("CONNECTED")
                        while True:
                            message = await asyncio.wait_for(ws.recv(), timeout=90)
                            if time.monotonic() - connected_at >= 60:
                                attempt = 0
                                self.health["reconnect_level"] = 0
                            try:
                                payload = json.loads(message)
                                if (
                                    isinstance(payload, dict)
                                    and payload.get("params", {}).get("subscription") == subscription
                                ):
                                    self.receive(payload)
                                else:
                                    self.health["ignored_events"] += 1
                            except (ValueError, TypeError, AttributeError):
                                self.global_gap("outer_notification")
                                self.record_decode_failure("notification", DecodeFailure("outer_notification"))
                except (OSError, websockets.WebSocketException, TimeoutError, ValueError):
                    self.record_transport_transition("DISCONNECTED")
                    self.global_gap("transport")
                    if self.health["connected_since"]:
                        self.connected_intervals.append((self.health["connected_since"], time.time()))
                    self.health.update(
                        connected=False,
                        last_disconnect=time.time(),
                        subscriptions=0,
                        connected_since=0,
                        errors=self.health["errors"] + 1,
                        reconnects=self.health["reconnects"] + 1,
                    )
                    delay = min(60, 2 ** min(attempt, 6))
                    attempt = min(attempt + 1, 6)
                    self.health["reconnect_level"] = attempt
                    await asyncio.sleep(min(60, delay + random.uniform(0, delay * 0.2)))
        finally:
            self.global_gap("shutdown")
            self.health.update(connected=False, subscriptions=0, connected_since=0)
