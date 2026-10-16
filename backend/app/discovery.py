"""Bounded, standard Solana log discovery. No HTTP requests or trade subscriptions."""

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


def decode_event(encoded: str) -> tuple[str, dict] | None:
    """Decode only the official IDL event prefix through its timestamp.

    Subsequent reserve/feature fields are deliberately not used for price, security
    or lifecycle. Appended IDL fields do not change this prefix's Borsh layout.
    """
    if len(encoded) > 16384:
        raise ValueError("oversize event")
    raw = base64.b64decode(encoded, validate=True)
    name = EVENTS.get(raw[:8])
    if name is None:
        return None
    offset = 8
    result: dict[str, Any] = {}
    for field in FIELDS[name]:
        kind = field["type"]
        if kind == "string":
            length = struct.unpack_from("<I", raw, offset)[0]
            offset += 4
            if length > 2048 or offset + length > len(raw):
                raise ValueError("invalid Borsh string")
            value = raw[offset : offset + length].decode("utf-8")
            offset += length
        elif kind == "pubkey":
            value = str(Pubkey.from_bytes(raw[offset : offset + 32]))
            offset += 32
        elif kind in ("u64", "i64"):
            value = struct.unpack_from("<Q" if kind == "u64" else "<q", raw, offset)[0]
            offset += 8
        else:
            raise ValueError("unsupported prefix schema")
        result[field["name"]] = value
        if field["name"] == "timestamp":
            break
    mint = Pubkey.from_string(result["mint"])
    curve = Pubkey.find_program_address([b"bonding-curve", bytes(mint)], Pubkey.from_string(PUMP_PROGRAM))[0]
    if result["bonding_curve"] != str(curve) or result["timestamp"] <= 0:
        raise ValueError("invalid event identity")
    # Migration's pool follows timestamp; read it explicitly from the canonical IDL.
    if name == "CompletePumpAmmMigrationEvent":
        result["pool"] = str(Pubkey.from_bytes(raw[offset : offset + 32]))
    return name, result


class OnchainPumpDiscovery:
    def __init__(self, submit, url=None):
        self.submit = submit
        self.url = os.getenv("SOLANA_WS_URL", "").strip() if url is None else url
        self.seen = Deduplicator(10000)
        self.health: dict[str, Any] = {
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
            "configuration_error": False,
        }
        try:
            parsed = urlsplit(self.url)
            if self.url and (parsed.scheme != "wss" or not parsed.hostname or parsed.fragment):
                raise ValueError("a valid wss endpoint is required")
        except ValueError:
            self.health["configuration_error"] = True
            self.health["enabled"] = False

    def receive(self, payload):
        """Synchronous bounded decode/submit, independent of HTTP RPC availability."""
        self.health["messages"] += 1
        self.health["last_success"] = time.time()
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
            if not any(line.startswith("Program data: ") for line in logs):
                self.health["ignored_events"] += 1
                return
            signature = str(Signature.from_string(value["signature"]))
            # Stage events inside invocation frames. A caught failed CPI must not
            # supply evidence, even if the overall transaction later succeeds.
            frames: list[tuple[str, list]] = []
            decoded: list[tuple[str, dict]] = []
            for line in logs:
                if match := INVOKE.fullmatch(line):
                    if int(match[2]) != len(frames) + 1 or len(frames) >= 64:
                        raise ValueError("invalid invocation depth")
                    frames.append((match[1], []))
                elif match := FINISH.fullmatch(line):
                    if not frames or frames[-1][0] != match[1]:
                        raise ValueError("unbalanced invocation")
                    _, events = frames.pop()
                    if match[2] == "success":
                        (frames[-1][1] if frames else decoded).extend(events)
                elif line.startswith("Program data: ") and frames and frames[-1][0] == PUMP_PROGRAM:
                    decoded_event = decode_event(line[14:])
                    if decoded_event is not None:
                        frames[-1][1].append(decoded_event)
            if frames:
                raise ValueError("incomplete logs")
            if not decoded:
                self.health["ignored_events"] += 1
                return
            # One transaction may contain several creates; deduplicate the whole
            # notification only after decoding all events successfully.
            if not self.seen.accept(signature):
                self.health["duplicates"] += 1
                return
            for name, fields in decoded:
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
        except (ValueError, TypeError, KeyError, IndexError, struct.error, binascii.Error):
            self.health["decoding_errors"] += 1
            self.health["errors"] += 1

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
                            subscriptions=1,
                            last_success=time.time(),
                        )
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
                                self.health["decoding_errors"] += 1
                                self.health["errors"] += 1
                except (OSError, websockets.WebSocketException, TimeoutError, ValueError):
                    self.health.update(
                        connected=False,
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
            self.health.update(connected=False, subscriptions=0, connected_since=0)
