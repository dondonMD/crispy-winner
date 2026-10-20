"""Synthetic byte-layout tracing tests; trailers are garbage, not a new schema."""
import base64
import hashlib
import json
import struct
import sys
from unittest.mock import Mock

import pytest
from solders.pubkey import Pubkey

from backend.app import pumpswap
from backend.app.discovery import DecodeFailure
from backend.tests.test_pumpswap_flow import MINT, POOL, USER, WSOL, notification, provider, wire
from scripts.diagnose_pumpswap_layout import LayoutProbe, inspect_decode, parse_failures


def trailer(name="BuyEvent", **kwargs):
    return base64.b64encode(base64.b64decode(wire(name, **kwargs)) + b"\x01\x02\x03\x04\x05\x06\x07\x08").decode()


@pytest.mark.parametrize("name", ["BuyEvent", "SellEvent"])
def test_old_canonical_fixture_is_decoded_without_diagnostic_change(name):
    encoded = wire(name)
    original = pumpswap.decode_event(encoded)
    decoded, metadata = inspect_decode(encoded, POOL)
    assert decoded == original and metadata is None


@pytest.mark.parametrize("name,count", [("BuyEvent", 40), ("SellEvent", 33)])
def test_exact_complete_schema_trailing_branch_and_all_field_boundaries(name, count):
    encoded = trailer(name)
    with pytest.raises(DecodeFailure, match="unsupported_layout"):
        pumpswap.decode_event(encoded)
    decoded, meta = inspect_decode(encoded, POOL)
    assert decoded is None
    assert meta["cause"] == "KNOWN_DISCRIMINATOR_TRAILING_BYTES"
    assert meta["expected_field_count"] == meta["parsed_field_count"] == count
    assert meta["raw_length"] - meta["final_parsed_offset"] == meta["trailing_byte_count"] == 8
    assert meta["trailing_sha256"] == hashlib.sha256(bytes(range(1, 9))).hexdigest()
    assert len(meta["field_boundaries"]) == count
    assert meta["field_boundaries"][0]["start"] == 8
    assert meta["field_boundaries"][-1]["end"] == meta["final_parsed_offset"]
    assert all(a["end"] == b["start"] for a, b in zip(meta["field_boundaries"], meta["field_boundaries"][1:]))
    assert meta["failing_field_name"] is None
    assert meta["identity"] == ("TARGET_BUY_LAYOUT_FAILURE" if name == "BuyEvent" else "TARGET_SELL_LAYOUT_FAILURE")
    assert USER not in json.dumps(meta) and POOL not in json.dumps(meta)


@pytest.mark.parametrize("encoded,cause", [("A" * 8193, "ENCODED_STRING_TOO_LARGE"),
    (base64.b64encode(b"123").decode(), "RAW_TOO_SHORT"),
    (base64.b64encode(base64.b64decode(wire())[:-1]).decode(), "FIELD_BOUNDARY_FAILURE")])
def test_exact_other_failure_branches(encoded, cause):
    _, meta = inspect_decode(encoded, POOL)
    assert meta["cause"] == cause
    if cause == "RAW_TOO_SHORT":
        assert meta["final_parsed_offset"] == 0
    _, invalid = inspect_decode(None, POOL)
    assert invalid["cause"] == "UNKNOWN_OTHER"


def test_unsupported_schema_type_and_unknown_category(monkeypatch):
    fields = [dict(f) for f in pumpswap.FIELDS["BuyEvent"]]
    fields[0]["type"] = "u256"
    monkeypatch.setitem(pumpswap.FIELDS, "BuyEvent", fields)
    _, meta = inspect_decode(wire(), POOL)
    assert meta["cause"] == "FIELD_TYPE_UNSUPPORTED"
    assert meta["failing_field_name"] == "timestamp" and meta["parsed_field_count"] == 0


def test_string_failure_and_safe_ix_classification():
    _, meta = inspect_decode(wire(ix_name="sensitive-arbitrary-text" * 8), POOL)
    assert meta["production_reason"] == "invalid_string" and meta["failing_field_name"] == "ix_name"
    _, meta = inspect_decode(trailer(ix_name="do-not-print-this"), POOL)
    assert meta["ix_name_classification"] == "OTHER_OR_ABSENT" and meta["ix_name_length"] == 17
    assert "do-not-print-this" not in json.dumps(meta)
    raw = base64.b64decode(wire())
    string_offset = next(b["start"] for b in meta["field_boundaries"] if b["name"] == "ix_name")
    invalid = raw[:string_offset] + struct.pack("<I", 1) + b"\xff" + raw[string_offset+5:]
    with pytest.raises(DecodeFailure):
        pumpswap.decode_event(base64.b64encode(invalid).decode())


def test_successful_invocation_and_foreign_identity_preserved():
    foreign = str(Pubkey.new_unique())
    message = notification(trailer(), trailer("SellEvent", pool=foreign))
    logs = message["params"]["result"]["value"]["logs"]
    original = pumpswap.decode_event
    previous = sys.gettrace()
    failures = parse_failures(logs, POOL)
    assert pumpswap.decode_event is original and sys.gettrace() is previous
    assert [ordinal for ordinal, _ in failures] == [1, 2]
    assert [m["identity"] for _, m in failures] == ["TARGET_BUY_LAYOUT_FAILURE", "FOREIGN_SELL_LAYOUT_FAILURE"]
    failed_logs = list(logs)
    failed_logs[-1] = f"Program {pumpswap.PROGRAM} failed: custom program error: 1"
    assert parse_failures(failed_logs, POOL) == []
    with pytest.raises(DecodeFailure):
        parse_failures(logs[:-1], POOL)
    assert pumpswap.decode_event is original and sys.gettrace() is previous


def test_probe_dedup_bounds_and_truncations(monkeypatch):
    from scripts import diagnose_pumpswap_layout as diagnostic
    monkeypatch.setattr(diagnostic, "MAX_SEEN", 2)
    from solders.signature import Signature
    probe = LayoutProbe(pumpswap.VerifiedPool(POOL, MINT, WSOL))
    message = notification(trailer())
    probe.handle(message, 10)
    probe.handle(message, 10)
    for _ in range(4):
        message["params"]["result"]["value"]["signature"] = str(Signature.new_unique())
        probe.handle(message, 10)
    assert probe.duplicates == 1 and len(probe.seen) == 2
    assert len(probe.samples) == len(probe.examples) == 1
    message["params"]["result"]["value"]["logs"].append("Log truncated")
    probe.handle(message, 10)
    assert probe.truncations == 1


def test_production_pool_units_dedup_and_foreign_semantics_unchanged():
    p, accepted, gaps = provider()
    foreign = str(Pubkey.new_unique())
    message = notification(wire(pool=foreign), wire("SellEvent"))
    p.handle(message)
    p.handle(message)
    assert len(accepted) == 1 and accepted[0].evidence["event_ordinal"] == 2
    assert not gaps
    p, accepted, _ = provider(str(Pubkey.new_unique()))
    p.handle(notification(wire()))
    assert len(accepted) == 1 and accepted[0].currency == "unknown" and not accepted[0].evidence["units_valid"]


async def test_layout_diagnostic_never_constructs_engine_or_database(monkeypatch):
    import asyncio
    from backend.app.engine import RadarEngine
    from backend.app.db import Database
    from backend.tests.test_pumpswap_diagnostic import RPC, account
    from scripts import diagnose_pumpswap_layout as diagnostic
    forbidden = Mock(side_effect=AssertionError("Forbidden state"))
    monkeypatch.setattr(RadarEngine, "__init__", forbidden)
    monkeypatch.setattr(Database, "__init__", forbidden)
    class Socket:
        def __init__(self):
            self.queue = asyncio.Queue()
            self.closed = False
        async def send(self, raw):
            await self.queue.put(json.dumps({"id": 1, "result": 10}))
            await self.queue.put(json.dumps(notification(trailer())))
        async def recv(self):
            return await self.queue.get()
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            self.closed = True
    socket = Socket()
    monkeypatch.setattr(diagnostic.websockets, "connect", lambda *a, **kw: socket)
    report = await diagnostic.diagnose(POOL, MINT, 1, rpc=RPC(account()), url="wss://synthetic?secret=forbidden")
    assert socket.closed and report["acks"] == 1 and report["accepted_trade_events"] == 0
    assert report["failure_identities"]["TARGET_BUY_LAYOUT_FAILURE"] == 1
    assert USER not in json.dumps(report) and "forbidden" not in json.dumps(report)
    forbidden.assert_not_called()
