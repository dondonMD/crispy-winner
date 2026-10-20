"""Synthetic bounded diagnostics; no research observations are created."""
import asyncio
import json
from unittest.mock import Mock

import pytest
from solders.pubkey import Pubkey
from solders.signature import Signature

from backend.app.pumpswap import VerifiedPool
from backend.tests.test_pumpswap_diagnostic import RPC, account
from backend.tests.test_pumpswap_flow import MINT, POOL, USER, WSOL, notification, wire
from scripts import diagnose_pumpswap_filters as diagnostic


def comparison(quote=WSOL):
    probe = diagnostic.Comparison(VerifiedPool(POOL, MINT, quote))
    probe.active = {10: "pool", 20: "mint"}
    return probe


async def test_independent_ack_attribution_and_reack():
    probe = comparison()
    probe.active.clear()
    ws = Mock()
    async def send(raw):
        request = json.loads(raw)
        assert request["params"][1] == {"commitment": "confirmed"}
    ws.send = send
    await probe.subscribe(ws, "pool")
    await probe.subscribe(ws, "mint")
    probe.handle({"id": 2, "result": 20})
    assert probe.active == {20: "mint"} and probe.filters["pool"]["acks"] == 0
    probe.handle({"id": 1, "result": 10})
    probe.disconnected()
    assert not probe.active and not probe.pending
    await probe.subscribe(ws, "pool")
    probe.handle({"id": 3, "result": 30})
    assert probe.active == {30: "pool"} and probe.filters["pool"]["acks"] == 2
    with pytest.raises(ValueError):
        probe.handle({"id": 3, "result": 30})


def test_target_foreign_mixed_original_ordinals_cross_filter_duplicates(monkeypatch):
    probe = comparison()
    from backend.app import pumpswap
    decoder = Mock(wraps=pumpswap.decode_event)
    monkeypatch.setattr(pumpswap, "decode_event", decoder)
    foreign = str(Pubkey.new_unique())
    message = notification(wire(pool=foreign), wire(), wire("SellEvent"))
    probe.handle(message)
    message["params"]["subscription"] = 20
    probe.handle(message)
    probe.handle(message)
    assert decoder.call_count == 9
    for name in ("pool", "mint"):
        count = probe.filters[name]
        assert count["target_buys"] == count["target_sells"] == 1
        assert [e["ordinal"] for e in count["examples"]] == [2, 3]
    assert probe.filters["mint"]["duplicates"] == 2
    assert probe.filters["mint"]["cross_filter_duplicates"] == 2
    assert len(probe.unique) == 2
    assert USER not in json.dumps(probe.filters)


@pytest.mark.parametrize("kind", ["unknown", "truncated", "malformed", "foreign"])
def test_fail_closed_and_no_invented_events(kind):
    probe = comparison(str(Pubkey.new_unique()) if kind == "unknown" else WSOL)
    message = notification(wire())
    if kind == "truncated":
        message["params"]["result"]["value"]["logs"].append("Log truncated")
    if kind == "malformed":
        message = notification(wire(), "invalid")
    if kind == "foreign":
        message = notification(wire(pool=str(Pubkey.new_unique())))
    probe.handle(message)
    count = probe.filters["pool"]
    assert count["accepted_units"] == 0
    assert count["unknown_units"] == (kind == "unknown")
    assert count["truncations"] == (kind == "truncated")
    assert count["decode_failures"] == (kind == "malformed")


def test_bounded_memory_and_secret_safe_reporting(monkeypatch):
    monkeypatch.setattr(diagnostic, "MAX_SEEN", 8)
    probe = comparison()
    for _ in range(20):
        message = notification(wire())
        message["params"]["result"]["value"]["signature"] = str(Signature.new_unique())
        probe.handle(message)
    assert len(probe.seen) == len(probe.unique) == 8
    assert len(probe.samples) == len(probe.filters["pool"]["examples"]) == 3
    report = json.dumps(probe.filters)
    assert USER not in report and "signature_hash" in report


@pytest.mark.parametrize("version", ["legacy", 0, 1])
def test_static_and_loaded_address_classification(version):
    transaction = {"version": version, "transaction": {"message": {"accountKeys": [MINT]}},
                   "meta": {"err": None, "loadedAddresses": {"writable": [POOL] if version == 0 else [], "readonly": []}}}
    assert diagnostic.address_placement(transaction, POOL, MINT) == {
        "version": version, "pool": ["ALT_WRITABLE"] if version == 0 else ["ABSENT"], "base_mint": ["STATIC"]}
    transaction["meta"]["err"] = {"failure": 1}
    with pytest.raises(ValueError):
        diagnostic.address_placement(transaction, POOL, MINT)


async def test_invalid_pool_cannot_connect(monkeypatch):
    connect = Mock()
    monkeypatch.setattr(diagnostic.websockets, "connect", connect)
    a = account()
    a["owner"] = str(Pubkey.new_unique())
    with pytest.raises(ValueError):
        await diagnostic.diagnose(POOL, MINT, 1, rpc=RPC(a), url="wss://synthetic")
    connect.assert_not_called()


async def test_isolation_shutdown_and_report(monkeypatch):
    from backend.app.engine import RadarEngine
    from backend.app.db import Database
    forbidden = Mock(side_effect=AssertionError("State forbidden"))
    monkeypatch.setattr(RadarEngine, "__init__", forbidden)
    monkeypatch.setattr(Database, "__init__", forbidden)
    sockets = []
    class Socket:
        def __init__(self):
            self.queue = asyncio.Queue()
            self.closed = False
        async def send(self, raw):
            request = json.loads(raw)
            sid = 10 if request["id"] % 2 else 20
            await self.queue.put(json.dumps({"id": request["id"], "result": sid}))
            if sid == 10:
                await self.queue.put(json.dumps(notification(wire())))
        async def recv(self):
            return await self.queue.get()
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            self.closed = True
    def connect(*args, **kwargs):
        s = Socket()
        sockets.append(s)
        return s
    monkeypatch.setattr(diagnostic.websockets, "connect", connect)
    rpc = RPC(account())
    # Sample HTTP deliberately unavailable in this fixture; still safely reported.
    report = await diagnostic.diagnose(POOL, MINT, 1, rpc=rpc, url="wss://synthetic?secret=forbidden")
    assert sockets[0].closed and report["filters"]["pool"]["target_buys"] == 1
    assert report["filters"]["mint"]["acks"] == 1
    assert report["normal_path_trade_http_delta"] == 0 and not report["strategy_current_claimed"]
    assert "forbidden" not in json.dumps(report) and USER not in json.dumps(report)
    forbidden.assert_not_called()


def test_system_program_key_is_valid_and_impossible_loaded_layout_rejected():
    transaction = {"version": 0, "transaction": {"message": {"accountKeys": [str(Pubkey.default()), MINT]}},
                   "meta": {"err": None, "loadedAddresses": {"writable": [POOL], "readonly": []}}}
    assert diagnostic.address_placement(transaction, POOL, MINT)["pool"] == ["ALT_WRITABLE"]
    transaction["version"] = "legacy"
    with pytest.raises(ValueError):
        diagnostic.address_placement(transaction, POOL, MINT)


async def test_reconnect_restores_independent_filters_and_preserves_dedup(monkeypatch):
    sockets = []
    class Socket:
        def __init__(self):
            self.queue = asyncio.Queue()
            self.closed = False
        async def send(self, raw):
            request = json.loads(raw)
            name = "pool" if request["params"][0]["mentions"] == [POOL] else "mint"
            sid = 10 if name == "pool" else 20
            await self.queue.put(json.dumps({"id": request["id"], "result": sid}))
            if name == "pool":
                await self.queue.put(json.dumps(notification(wire())))
        async def recv(self):
            if self.queue.empty() and self is sockets[0]:
                raise ConnectionError("Do not print private connection details")
            return await self.queue.get()
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            self.closed = True
    def connect(*args, **kwargs):
        socket = Socket()
        sockets.append(socket)
        return socket
    monkeypatch.setattr(diagnostic.websockets, "connect", connect)
    report = await diagnostic.diagnose(POOL, MINT, 2, rpc=RPC(account()), url="wss://synthetic")
    assert len(sockets) == 2 and all(s.closed for s in sockets)
    assert report["reconnects"] == 1 and report["errors"] == 1
    assert report["filters"]["pool"]["acks"] == report["filters"]["mint"]["acks"] == 2
    assert report["filters"]["pool"]["target_buys"] == report["filters"]["pool"]["duplicates"] == 1


async def test_hard_duration_limits_before_any_rpc():
    rpc = RPC(account())
    for seconds, program_seconds in [(601, 0), (0, 0), (1, 16), (1, -1)]:
        with pytest.raises(ValueError):
            await diagnostic.diagnose(POOL, MINT, seconds, program_seconds, rpc=rpc)
    assert rpc.health["requests"] == 0
