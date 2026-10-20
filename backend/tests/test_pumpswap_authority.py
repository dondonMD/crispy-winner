"""Synthetic public-account/diagnostic fixtures, never strategy evidence."""

import asyncio
import base64
import copy
import hashlib
import json
import struct
from unittest.mock import Mock
import zlib

import pytest
from solders.pubkey import Pubkey
from solders.signature import Signature

from backend.app import pumpswap
from backend.app.discovery import DecodeFailure
from backend.tests.test_pumpswap_diagnostic import account
from backend.tests.test_pumpswap_flow import MINT, POOL, USER, notification, wire
from scripts import inspect_pumpswap_program as program
from scripts import describe_pumpswap_tail as tail
from scripts.diagnose_pumpswap_layout import inspect_decode


def encoded(raw, owner=program.LOADER, executable=False):
    return dict(owner=owner, executable=executable, data=[base64.b64encode(raw).decode(), "base64"])


def test_loader_state_and_canonical_programdata_identity():
    pd = Pubkey.find_program_address(
        [bytes(Pubkey.from_string(pumpswap.PROGRAM))], Pubkey.from_string(program.LOADER)
    )[0]
    a = encoded(struct.pack("<I", 2) + bytes(pd), executable=True)
    assert program.programdata_address(a) == str(pd)
    authority = Pubkey.new_unique()
    data = encoded(struct.pack("<IQB", 3, 12345, 1) + bytes(authority))
    assert program.deployment(data) == dict(upgrade_slot=12345, upgrade_authority=str(authority))
    data = encoded(struct.pack("<IQB", 3, 12345, 0) + bytes(32))
    assert program.deployment(data)["upgrade_authority"] is None


@pytest.mark.parametrize(
    "mutation",
    [
        lambda a: a.update(owner=str(Pubkey.new_unique())),
        lambda a: a.update(executable=False),
        lambda a: a.update(data=encoded(bytes(36))["data"]),
        lambda a: a.update(data=encoded(struct.pack("<I", 2) + bytes(Pubkey.new_unique()))["data"]),
    ],
)
def test_bad_program_identity_rejected(mutation):
    pd = Pubkey.find_program_address(
        [bytes(Pubkey.from_string(pumpswap.PROGRAM))], Pubkey.from_string(program.LOADER)
    )[0]
    a = encoded(struct.pack("<I", 2) + bytes(pd), executable=True)
    mutation(a)
    with pytest.raises(ValueError):
        program.programdata_address(a)


def test_invalid_programdata_and_exact_canonical_idl_addresses():
    with pytest.raises(ValueError):
        program.deployment(encoded(struct.pack("<IQB", 3, 12345, 2) + bytes(32)))
    assert program.idl_addresses() == {
        "anchor_0_31": "5fLnXNNoZcZt9Qku6HARM3un3Ttm2cGsR7gN9Zp1R7h3",
        "canonical_program_metadata": "EB4BfHDFEUqTmRsUGqUusgk7B37LT9GyG8TTqM6eS1jN",
    }


def idl_account(doc):
    raw = json.dumps(doc, separators=(",", ":")).encode()
    compressed = zlib.compress(raw)
    discriminator = hashlib.sha256(b"internal:IdlAccount").digest()[:8]
    return encoded(
        discriminator
        + bytes(Pubkey.new_unique())
        + struct.pack("<I", len(compressed))
        + compressed
        + bytes(8),
        owner=pumpswap.PROGRAM,
    ), raw


def test_canonical_idl_owner_discriminator_compression_identity_and_bounds(monkeypatch):
    a, raw = idl_account(dict(address=pumpswap.PROGRAM, types=[]))
    assert program.decode_legacy_idl(a) == raw
    bad = copy.deepcopy(a)
    bad["owner"] = program.LOADER
    with pytest.raises(ValueError):
        program.decode_legacy_idl(bad)
    bad = copy.deepcopy(a)
    data = base64.b64decode(bad["data"][0])
    bad["data"][0] = base64.b64encode(bytes(8) + data[8:]).decode()
    with pytest.raises(ValueError):
        program.decode_legacy_idl(bad)
    bad, _ = idl_account(dict(address=str(Pubkey.new_unique())))
    with pytest.raises(ValueError):
        program.decode_legacy_idl(bad)
    monkeypatch.setattr(program, "LIMIT", 128)
    bad, _ = idl_account(dict(address=pumpswap.PROGRAM, text="x" * 1000))
    with pytest.raises(ValueError):
        program.decode_legacy_idl(bad)


@pytest.mark.parametrize("name", ["BuyEvent", "SellEvent"])
@pytest.mark.parametrize("raw_tail", [bytes(8), b"\xff" * 8])
def test_descriptive_integer_views_never_accept_or_name_unknown_field(name, raw_tail):
    raw = base64.b64decode(wire(name)) + raw_tail
    data = base64.b64encode(raw).decode()
    with pytest.raises(DecodeFailure):
        pumpswap.decode_event(data)
    result, meta = inspect_decode(data, POOL, describe_tail=True)
    assert result is None
    view = meta["tail_descriptive_only"]
    assert view["unsigned_le_u64"] == int.from_bytes(raw_tail, "little")
    assert view["signed_le_i64"] == int.from_bytes(raw_tail, "little", signed=True)
    assert meta["trailing_sha256"] == hashlib.sha256(raw_tail).hexdigest()
    _, default = inspect_decode(data, POOL)
    assert "tail_descriptive_only" not in default
    assert USER not in json.dumps(meta)


def test_constant_tail_equality_is_not_a_correlation_or_semantic_claim():
    stats = tail.Statistics()
    for i in range(4):
        stats.add(
            dict(
                unsigned_le_u64=0,
                documented_values_under_pinned_interpretation={
                    f: (0 if f == "holder_rewards" else i + 1) for f in tail.FIELDS
                },
            )
        )
    r = stats.report()
    assert r["constant"] and r["arrival_order_same"] == 3 and r["arrival_order_changed"] == 0
    assert r["comparisons"]["holder_rewards"]["equal"] == 4
    assert r["comparisons"]["holder_rewards"]["equal_nonzero"] == 0
    assert all(c["pearson_r"] is None for c in r["comparisons"].values())


async def test_bounded_tail_probe_no_engine_database_or_trade_state(monkeypatch):
    from backend.app.engine import RadarEngine
    from backend.app.db import Database

    forbidden = Mock(side_effect=AssertionError("Forbidden state"))
    monkeypatch.setattr(RadarEngine, "__init__", forbidden)
    monkeypatch.setattr(Database, "__init__", forbidden)
    monkeypatch.setattr(tail, "MAX_OBSERVATIONS", 2)
    messages = []
    for name in ("BuyEvent", "SellEvent"):
        payload = base64.b64encode(base64.b64decode(wire(name)) + bytes(8)).decode()
        m = notification(payload)
        m["params"]["result"]["value"]["signature"] = str(Signature.new_unique())
        messages.append(m)

    class Socket:
        def __init__(self):
            self.queue = asyncio.Queue()
            self.closed = False

        async def send(self, raw):
            request = json.loads(raw)
            assert request["params"] == [{"mentions": [POOL]}, {"commitment": "confirmed"}]
            await self.queue.put(json.dumps({"id": 1, "result": 10}))
            for m in messages:
                await self.queue.put(json.dumps(m))

        async def recv(self):
            return await self.queue.get()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            self.closed = True

    class RPC:
        def __init__(self):
            self.health = {"requests": 0}

        async def rpc(self, method, params):
            self.health["requests"] += 1
            if method == "getAccountInfo":
                return {"context": {"slot": 124}, "value": account()}
            raise ValueError("Unavailable sample")

    socket = Socket()
    monkeypatch.setattr(tail.websockets, "connect", lambda *a, **kw: socket)
    schema = {"types": [{"name": "Pool", "type": {"fields": [{"name": "pool_bump", "type": "u8"}]}}]}
    report = await tail.describe(POOL, MINT, 1, schema, rpc=RPC(), url="wss://synthetic?secret=never-print")
    assert (
        report["all"]["count"] == 2
        and report["accepted_events"] == 0
        and report["semantic_field_name"] is None
    )
    assert len(report["examples"]) <= tail.MAX_EXAMPLES and report["diagnostic_rpc_requests"] == 4
    assert "never-print" not in json.dumps(report) and USER not in json.dumps(report)
    assert socket.closed
    forbidden.assert_not_called()
