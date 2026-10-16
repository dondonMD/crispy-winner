import asyncio
import copy
import json
import time
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from websockets.exceptions import ConnectionClosedError

from backend.app.config import Settings
from backend.app.discovery import OnchainPumpDiscovery, decode_event
from backend.app.domain import State
from backend.app.engine import RadarEngine
from backend.app.providers import PUMP_PROGRAM

FIXTURE = json.loads(Path(__file__).with_name("fixtures").joinpath("pump_events.json").read_text())


def notification(event="CreateEvent", signature=None):
    return {
        "method": "logsNotification",
        "params": {
            "subscription": 7,
            "result": {
                "context": {"slot": 123},
                "value": {
                    "signature": signature or FIXTURE["signature"],
                    "err": None,
                    "logs": [
                        f"Program {PUMP_PROGRAM} invoke [1]",
                        "Program data: " + FIXTURE["events"][event],
                        f"Program {PUMP_PROGRAM} success",
                    ],
                },
            },
        },
    }


def test_canonical_create_and_migration():
    events = []
    provider = OnchainPumpDiscovery(events.append, "wss://example.test")
    provider.receive(notification())
    event = events[0]
    assert event.kind == "create" and event.mint == FIXTURE["fields"]["mint"]
    assert event.name == FIXTURE["fields"]["name"] and event.creator == FIXTURE["fields"]["creator"]
    assert event.signature == FIXTURE["signature"] and event.ts == 1000
    assert event.price is None and event.market_cap is None and event.curve_progress is None
    assert event.evidence["slot"] == 123 and event.evidence["data_quality"] == "VERIFIED"
    assert event.evidence["launch_metadata"]["bondingCurveKey"] == FIXTURE["fields"]["bonding_curve"]
    assert event.evidence["launch_metadata"]["uri"] == ""  # No metadata invented.
    migration = OnchainPumpDiscovery(events.append, "wss://example.test")
    migration.receive(notification("CompletePumpAmmMigrationEvent"))
    assert events[1].kind == "migration" and events[1].pair == FIXTURE["fields"]["pool"]


def test_duplicate_signature_bounded_and_not_reemitted():
    events = []
    p = OnchainPumpDiscovery(events.append, "wss://example.test")
    p.receive(notification())
    p.receive(notification())
    assert len(events) == 1 and p.health["duplicates"] == 1
    assert p.seen.maximum == 10000


@pytest.mark.parametrize(
    "change", ["failed", "foreign", "truncated", "malformed", "wrong_curve", "unrelated", "caught_failure"]
)
def test_fail_closed(change):
    events = []
    p = OnchainPumpDiscovery(events.append, "wss://example.test")
    n = notification()
    value = n["params"]["result"]["value"]
    if change == "failed":
        value["err"] = {"InstructionError": [0, "error"]}
    elif change == "foreign":
        value["logs"] = [s.replace(PUMP_PROGRAM, FIXTURE["fields"]["mint"]) for s in value["logs"]]
    elif change == "truncated":
        value["logs"].pop()
    elif change == "malformed":
        value["logs"][1] = "Program data: @@@"
    elif change == "wrong_curve":
        import base64

        raw = bytearray(base64.b64decode(FIXTURE["events"]["CreateEvent"]))
        # Mint bytes changed; curve PDA no longer agrees.
        offset = 8 + sum(4 + len(FIXTURE["fields"][k].encode()) for k in ("name", "symbol", "uri"))
        raw[offset] ^= 1
        value["logs"][1] = "Program data: " + base64.b64encode(raw).decode()
    elif change == "unrelated":
        value["logs"][1] = "Program log: Instruction: Buy"
    else:
        value["logs"][-1] = f"Program {PUMP_PROGRAM} failed: caught"
    p.receive(n)
    assert not events and not p.health["launch_events"]


def test_invalid_or_missing_configuration_safe():
    for url in ("", "https://example.test", "wss://", "wss://example.test/#fragment"):
        p = OnchainPumpDiscovery(lambda e: None, url)
        assert not p.health["enabled"] and not p.health["connected"]
        assert RadarEngine.provider_health(p.health)["status"] in ("DISABLED", "UNAVAILABLE")


async def test_normalized_event_and_cross_source_dedup(tmp_path, monkeypatch):
    monkeypatch.delenv("PUMPPORTAL_ENABLED", raising=False)
    engine = RadarEngine(Settings(mode="OBSERVE"), tmp_path / "radar.db", offline=True)
    try:
        events = []
        p = OnchainPumpDiscovery(events.append, "wss://example.test")
        p.receive(notification())
        event = events[0]
        assert engine.process(event)
        token = engine.tokens[event.mint]
        assert token.state == State.WATCHING
        assert not engine.pump.health["connected"] and not engine.settings.trade_stream_enabled
        assert token.security["data_quality"] == "UNKNOWN"
        before = copy.deepcopy(token.launch_metadata)
        duplicate = engine.pump.normalize(
            {"mint": event.mint, "txType": "create", "name": "conflict", "signature": "other"}, 1001
        )
        assert not engine.process(duplicate)
        assert len(engine.tokens) == 1 and token.launch_metadata == before
        assert engine.duplicate_discoveries == 1
        assert Settings().max_candidates == 250 and Settings().max_deep == 25
        engine.onchain.health["connected"] = True
        assert engine.discovery_connected()
        assert engine.snapshot()["health"]["discovery_status"] == "CURRENT"
        engine.onchain.health["connected"] = False
        assert engine.snapshot()["health"]["discovery_status"] == "UNAVAILABLE"
    finally:
        await engine.stop()


async def test_discovery_makes_zero_http_requests_during_rpc_backoff(tmp_path):
    engine = RadarEngine(Settings(mode="OBSERVE"), tmp_path / "rpc.db", offline=True)
    try:
        engine.rpc.health["rate_limited_until"] = 9999999999
        engine.rpc.request_failed()
        engine.rpc.rpc = AsyncMock(side_effect=AssertionError("no enrichment permitted"))
        events = []
        p = OnchainPumpDiscovery(events.append, "wss://example.test")
        p.receive(notification())
        assert len(events) == 1 and engine.rpc.health["backoff_level"] > 0
        assert not engine.rpc.eligible("background")
        engine.rpc.rpc.assert_not_awaited()
        assert p.health["http_requests"] == p.health["enrichment_attempts"] == 0
    finally:
        await engine.stop()


async def test_reconnect_once_per_connection_no_duplicate_events_stable_reset(monkeypatch):
    connections, sent, delays, events = [], [], [], []
    clock = [0.0]

    class Socket:
        def __init__(self):
            self.reads = 0

        async def send(self, message):
            sent.append((len(connections), json.loads(message)))

        async def recv(self):
            self.reads += 1
            if self.reads == 1:
                return json.dumps({"jsonrpc": "2.0", "id": 1, "result": 7})
            if len(connections) == 5:
                raise asyncio.CancelledError()
            if len(connections) in (1, 3) and self.reads == 2:
                if len(connections) == 3:
                    clock[0] += 61
                return json.dumps(notification())
            raise ConnectionClosedError(None, None)

    class Connection:
        async def __aenter__(self):
            connections.append(1)
            return Socket()

        async def __aexit__(self, *args):
            return False

    async def sleep(delay):
        delays.append(delay)

    monkeypatch.setattr("backend.app.discovery.websockets.connect", lambda *a, **k: Connection())
    monkeypatch.setattr("backend.app.discovery.asyncio.sleep", sleep)
    monkeypatch.setattr("backend.app.discovery.random.uniform", lambda *a: 0)
    monkeypatch.setattr(
        "backend.app.discovery.time", SimpleNamespace(time=time.time, monotonic=lambda: clock[0])
    )
    p = OnchainPumpDiscovery(events.append, "wss://example.test")
    with pytest.raises(asyncio.CancelledError):
        await p.run()
    assert delays == [1, 2, 1, 2]
    assert len(events) == 1 and p.health["duplicates"] == 1
    assert len(sent) == len(connections) == 5
    assert all(
        item["method"] == "logsSubscribe"
        and item["params"] == [{"mentions": [PUMP_PROGRAM]}, {"commitment": "confirmed"}]
        for _, item in sent
    )
    assert not p.health["connected"] and p.health["subscriptions"] == 0


async def test_disabled_discovery_does_not_spawn_dead_tasks(tmp_path, monkeypatch):
    monkeypatch.delenv("SOLANA_WS_URL", raising=False)
    monkeypatch.delenv("PUMPPORTAL_ENABLED", raising=False)
    engine = RadarEngine(Settings(mode="OBSERVE"), tmp_path / "safe.db", offline=True)
    try:
        engine.last_lab = engine.last_maintenance = time.time()
        await engine.start()
        await asyncio.sleep(0)
        assert {t.get_name() for t in engine.tasks} == {"monitor", "enrichment"}
        assert not engine.discovery_connected() and all(not t.done() for t in engine.tasks)
    finally:
        await engine.stop()


def test_decoder_rejects_incomplete_prefix():
    import base64

    raw = base64.b64decode(FIXTURE["events"]["CreateEvent"])
    with pytest.raises((ValueError, __import__("struct").error)):
        decode_event(base64.b64encode(raw[:20]).decode())


async def test_migration_is_authoritative_and_core_missing_evidence_waits(tmp_path):
    from backend.app.domain import MarketEvent

    engine = RadarEngine(Settings(mode="OBSERVE"), tmp_path / "migration.db", offline=True)
    try:
        events = []
        p = OnchainPumpDiscovery(events.append, "wss://example.test")
        p.receive(notification())
        assert engine.process(events.pop())
        mint = FIXTURE["fields"]["mint"]
        assert engine.process(
            MarketEvent(
                mint=mint,
                ts=1001,
                source="Solana RPC",
                kind="curve",
                event_id="verified-curve",
                evidence={"curve_progress": 100, "data_quality": "VERIFIED"},
            )
        )
        token = engine.tokens[mint]
        assert token.graduation is None
        assert engine.token_view(token, 1001)["companion"]["action"] == "WAIT"
        # Another notification signature is unnecessary here: a separate provider
        # instance represents its fresh migration transaction fixture.
        OnchainPumpDiscovery(events.append, "wss://example.test").receive(
            notification("CompletePumpAmmMigrationEvent")
        )
        migration = events.pop().model_copy(update={"ts": 1002})
        assert engine.process(migration)
        assert token.graduation == 1002 and token.state == State.POST_GRAD_OBSERVATION
        assert engine.paper.state["cash"] == 20 and not engine.pump.subscribed
    finally:
        await engine.stop()


def test_caught_nested_failure_does_not_emit_and_multiple_events_are_not_signature_dropped():
    events = []
    p = OnchainPumpDiscovery(events.append, "wss://example.test")
    n = notification()
    outer = FIXTURE["fields"]["mint"]
    n["params"]["result"]["value"]["logs"] = [
        f"Program {outer} invoke [1]",
        f"Program {PUMP_PROGRAM} invoke [2]",
        "Program data: " + FIXTURE["events"]["CreateEvent"],
        f"Program {PUMP_PROGRAM} failed: caught",
        f"Program {outer} success",
    ]
    p.receive(n)
    assert not events
    n = notification()
    logs = n["params"]["result"]["value"]["logs"]
    logs.insert(2, "Program data: " + FIXTURE["events"]["CompletePumpAmmMigrationEvent"])
    p.receive(n)
    assert [e.kind for e in events] == ["create", "migration"]
