"""Synthetic fixtures for the standalone production-provider acquisition probe."""
import asyncio
import base64
import copy
import hashlib
import json
from unittest.mock import AsyncMock, Mock

import pytest
from solders.pubkey import Pubkey
from solders.signature import Signature

from backend.app import pumpswap
from backend.app.engine import RadarEngine
from backend.tests.test_pumpswap_flow import MINT, POOL, USER, WSOL, notification, wire
from scripts.validate_pumpswap_flow import Observations, diagnose, verify_pool


def account(quote=WSOL):
    raw = bytearray(243)
    raw[:8] = hashlib.sha256(b"account:Pool").digest()[:8]
    for offset, value in [(43, MINT), (75, quote), (139, str(Pubkey.new_unique())),
                           (171, str(Pubkey.new_unique()))]:
        raw[offset:offset + 32] = bytes(Pubkey.from_string(value))
    return {"owner": pumpswap.PROGRAM, "data": [base64.b64encode(raw).decode(), "base64"]}


class RPC:
    def __init__(self, value):
        self.value = value
        self.health = {"requests": 0}

    async def rpc(self, method, params):
        assert method == "getAccountInfo" and params[0] == POOL
        self.health["requests"] += 1
        return {"value": self.value}


@pytest.mark.parametrize("mutation", [lambda a: a.update(owner=str(Pubkey.new_unique())),
    lambda a: a.update(data=["AA==", "base64"]),
    lambda a: a.update(data=account(str(Pubkey.default()))["data"])])
async def test_invalid_pool_never_subscribes(monkeypatch, mutation):
    a = account()
    mutation(a)
    connect = Mock()
    monkeypatch.setattr(pumpswap.websockets, "connect", connect)
    with pytest.raises(ValueError):
        await diagnose(POOL, MINT, 1, RPC(a), "wss://synthetic")
    connect.assert_not_called()


async def test_wrong_base_mint_rejected():
    with pytest.raises(ValueError):
        await verify_pool(RPC(account()), POOL, str(Pubkey.new_unique()))


@pytest.mark.parametrize("quote,accepted", [(WSOL, 2), (str(Pubkey.new_unique()), 0)])
async def test_production_transport_decoder_ack_units_dedup_and_isolation(monkeypatch, quote, accepted):
    decoded = Mock(wraps=pumpswap.decode_event)
    monkeypatch.setattr(pumpswap, "decode_event", decoded)
    engine_init = Mock(side_effect=AssertionError("Engine forbidden"))
    process = Mock(side_effect=AssertionError("Strategy forbidden"))
    monkeypatch.setattr(RadarEngine, "__init__", engine_init)
    monkeypatch.setattr(RadarEngine, "process", process)
    buy, sell = notification(wire()), notification(wire("SellEvent"))
    sell["params"]["result"]["value"]["signature"] = str(Signature.new_unique())
    malformed = notification(wire(user_quote_amount_in=0))
    messages = [buy, copy.deepcopy(buy), sell, malformed]
    sockets = []
    class Socket:
        def __init__(self):
            self.queue = asyncio.Queue()
            self.closed = False
        async def send(self, raw):
            request = json.loads(raw)
            assert request["params"][0] == {"mentions": [POOL]}
            await self.queue.put(json.dumps({"id": request["id"], "result": 10}))
            for message in messages:
                await self.queue.put(json.dumps(message))
        async def recv(self):
            return await self.queue.get()
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            self.closed = True
    def connect(*args, **kwargs):
        socket = Socket()
        sockets.append(socket)
        return socket
    monkeypatch.setattr(pumpswap.websockets, "connect", connect)
    rpc = RPC(account(quote))
    report = await diagnose(POOL, MINT, 1, rpc, "wss://synthetic?api-key=never-print-this")
    assert sockets[0].closed
    assert report["ownership_layout_verified"] and report["subscription_ack"]
    assert decoded.call_count == 4
    health, observations = report["transport"], report["observations"]
    assert health["buy_events"] == health["sell_events"] == 1
    assert health["duplicates"] == 1 and health["decode_failures"] == 1
    assert health["accepted"] == observations["sample_count"] == accepted
    assert health["invalid_units"] == (2 if not accepted else 0)
    assert rpc.health["requests"] == 1 and report["normal_path_trade_http_delta"] == 0
    if accepted:
        assert observations["total_actual_quote_buy_volume"] == "1.1"
        assert observations["total_actual_quote_sell_volume"] == "0.9"
        assert len(observations["examples"]) == 2
    text = json.dumps(report)
    assert USER not in text and "never-print-this" not in text and "wallet" not in text
    assert not report["strategy_current_claimed"]
    engine_init.assert_not_called()
    process.assert_not_called()


def test_example_storage_is_bounded_and_bad_units_rejected():
    from backend.tests.test_pumpswap_flow import provider
    p, events, _ = provider()
    p.handle(notification(wire(), wire("SellEvent")))
    observations = Observations(p.pools[POOL])
    for _ in range(100):
        for event in events:
            assert observations.submit(event)
    assert len(observations.examples) == 3 and not hasattr(observations, "events")
    events[0].evidence["units_valid"] = False
    assert observations.submit(events[0]) is False


async def test_cancelled_diagnostic_closes_owned_rpc(monkeypatch):
    rpc = RPC(account())
    rpc.close = AsyncMock()
    monkeypatch.setattr("scripts.validate_pumpswap_flow.SolanaProvider", lambda: rpc)
    async def idle(self):
        await asyncio.Event().wait()
    monkeypatch.setattr(pumpswap.PumpSwapFlow, "run", idle)
    task = asyncio.create_task(diagnose(POOL, MINT, 600, url="wss://synthetic"))
    await asyncio.sleep(.01)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    rpc.close.assert_awaited_once()


async def test_production_reconnect_replays_stay_deduplicated(monkeypatch):
    connections = []
    message = notification(wire(), wire("SellEvent"))
    class Socket:
        def __init__(self):
            self.queue = asyncio.Queue()
            self.closed = False
        async def send(self, raw):
            await self.queue.put(json.dumps({"id": json.loads(raw)["id"], "result": 10}))
            await self.queue.put(json.dumps(message))
        async def recv(self):
            if self.queue.empty() and self is connections[0]:
                raise ConnectionError("synthetic disconnect")
            return await self.queue.get()
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            self.closed = True
    def connect(*args, **kwargs):
        result = Socket()
        connections.append(result)
        return result
    monkeypatch.setattr(pumpswap.websockets, "connect", connect)
    monkeypatch.setattr(pumpswap.random, "uniform", lambda *a: 0)
    report = await diagnose(POOL, MINT, 3, RPC(account()), "wss://synthetic")
    assert len(connections) == 2 and all(s.closed for s in connections)
    assert report["transport"]["acks"] == 2 and report["transport"]["reconnects"] == 1
    assert report["transport"]["duplicates"] == 2
    assert report["observations"]["sample_count"] == 2
    assert report["observations"]["local_gaps"] == 1
