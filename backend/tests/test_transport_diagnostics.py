"""Synthetic socket failures only; no live subscription or market observations."""

import asyncio
import errno
import json
import socket
from types import SimpleNamespace

import httpx
import pytest
from websockets.exceptions import (
    ConnectionClosedError, ConnectionClosedOK, InvalidHandshake, InvalidStatus, WebSocketException,
)
from websockets.frames import Close

from backend.app.config import Settings
from backend.app.discovery import OnchainPumpDiscovery, TRANSPORT_DIAGNOSTIC_LIMIT, TRANSPORT_FAILURES
from backend.app.domain import Token
from backend.app.engine import RadarEngine
from backend.app.main import create_app

MARKER = "SYNTHETIC_PRIVATE_DIAGNOSTIC_MARKER"
URL = f"wss://example.test/private?credential={MARKER}"


def test_close_fields_sanitized_without_exception_text():
    p = OnchainPumpDiscovery(lambda _: None, URL)
    exc = ConnectionClosedError(Close(1008, URL), Close(1008, MARKER), True)
    p.record_transport_failure(exc, "receive")
    item = p.health["transport_diagnostics"][-1]
    assert item["category"] == "websocket_close"
    assert item["received_close_code"] == item["sent_close_code"] == 1008
    assert MARKER not in json.dumps(p.health) and URL not in json.dumps(p.health)


@pytest.mark.parametrize("exc,phase,category", [
    (ConnectionClosedError(None, Close(1011, "keepalive ping timeout")), "receive", "ping_timeout"),
    (ConnectionClosedError(Close(1011, MARKER), Close(1011, MARKER), True), "receive", "websocket_close"),
    (ConnectionClosedError(Close(1011, "keepalive ping timeout"), Close(1011, "keepalive ping timeout"), True), "receive", "websocket_close"),
    (ConnectionClosedError(None, None), "receive", "websocket_close"),
    (ConnectionClosedOK(Close(1000, MARKER), Close(1000, MARKER), True), "receive", "websocket_close"),
    (TimeoutError(MARKER), "receive", "receive_timeout"),
    (TimeoutError(MARKER), "subscription_ack", "subscription_timeout"),
    (TimeoutError(MARKER), "connect", "connect_timeout"),
    (TimeoutError(MARKER), "subscribe_send", "send_timeout"),
    (TimeoutError(MARKER), URL, "timeout"),
    (socket.gaierror(socket.EAI_AGAIN, URL), "connect", "dns_error"),
    (ConnectionRefusedError(errno.ECONNREFUSED, URL), "connect", "connection_error"),
    (OSError(errno.EIO, URL), "receive", "os_error"),
    (InvalidStatus(SimpleNamespace(status_code=429)), "connect", "websocket_handshake"),
    (InvalidHandshake(URL), "connect", "websocket_handshake"),
    (WebSocketException(URL), "receive", "websocket_error"),
    (ValueError(URL), "subscription_validation", "subscription_rejected"),
    (ValueError(URL), "subscription_ack", "invalid_subscription_response"),
    (ValueError(URL), "connect", "value_error"),
    (Exception(URL), URL, "other_transport"),
])
def test_supported_categories_and_safe_fields(exc, phase, category):
    p = OnchainPumpDiscovery(lambda _: None, URL)
    p.record_transport_failure(exc, phase)
    item = p.health["transport_diagnostics"][-1]
    assert item["category"] == category
    assert sum(p.health["transport_failure_counts"].values()) == 1
    assert p.health["transport_failure_counts"][category] == 1
    assert MARKER not in json.dumps(RadarEngine.provider_health(p.health))
    assert URL not in json.dumps(p.health)
    if isinstance(exc, InvalidStatus):
        assert item["http_status"] == 429
    if isinstance(exc, socket.gaierror):
        assert item["errno"] == socket.EAI_AGAIN
    if phase == URL:
        assert item["phase"] == "other"


def test_storage_and_numeric_domains_bounded():
    p = OnchainPumpDiscovery(lambda _: None, URL)
    for _ in range(500):
        p.record_transport_failure(ValueError(MARKER * 1000), URL)
    assert len(p.health["transport_diagnostics"]) == TRANSPORT_DIAGNOSTIC_LIMIT == 32
    assert p.health["transport_diagnostics_evicted"] == 468
    assert tuple(p.health["transport_failure_counts"]) == TRANSPORT_FAILURES
    assert sum(p.health["transport_failure_counts"].values()) == 500
    assert len(json.dumps(p.health["transport_diagnostics"])) < 12000
    invalid = ConnectionClosedError(Close(True, URL), Close(10**100, URL), True)
    p.record_transport_failure(invalid, "receive")
    assert p.health["transport_diagnostics"][-1]["received_close_code"] is None
    assert p.health["transport_diagnostics"][-1]["sent_close_code"] is None
    p.record_transport_failure(OSError(10**100, URL), "connect")
    assert p.health["transport_diagnostics"][-1]["errno"] is None
    assert MARKER not in json.dumps(p.health)


@pytest.mark.parametrize("stage,exc,category", [
    ("connect", socket.gaierror(socket.EAI_AGAIN, URL), "dns_error"),
    ("connect", ConnectionRefusedError(errno.ECONNREFUSED, URL), "connection_error"),
    ("connect", TimeoutError(URL), "connect_timeout"),
    ("send", TimeoutError(URL), "send_timeout"),
    ("ack", TimeoutError(URL), "subscription_timeout"),
    ("ack", "invalid " + URL, "invalid_subscription_response"),
    ("ack", json.dumps({"id": 1, "error": {"message": MARKER}}), "subscription_rejected"),
    ("ack", json.dumps({"id": 2, "result": 7}), "subscription_rejected"),
    ("ack", json.dumps({"id": 1, "result": True}), "subscription_rejected"),
    ("receive", TimeoutError(URL), "receive_timeout"),
    ("receive", ConnectionClosedError(Close(1008, URL), Close(1008, URL), True), "websocket_close"),
    ("receive", ConnectionClosedError(None, Close(1011, "keepalive ping timeout")), "ping_timeout"),
])
async def test_real_run_handler_preserves_backoff_and_gap_rules(monkeypatch, stage, exc, category):
    sent, delays, gaps, options = [], [], [], []

    class Socket:
        reads = 0

        async def send(self, value):
            sent.append(json.loads(value))
            if stage == "send":
                raise exc

        async def recv(self):
            self.reads += 1
            if self.reads == 1:
                if stage == "ack":
                    if isinstance(exc, str):
                        return exc
                    raise exc
                return json.dumps({"id": 1, "result": 7})
            raise exc

    class Context:
        async def __aenter__(self):
            if stage == "connect":
                raise exc
            return Socket()

        async def __aexit__(self, *args):
            return False

    def connect(*args, **kwargs):
        options.append(kwargs)
        return Context()

    async def sleep(delay):
        delays.append(delay)
        raise asyncio.CancelledError()

    monkeypatch.setattr("backend.app.discovery.websockets.connect", connect)
    monkeypatch.setattr("backend.app.discovery.asyncio.sleep", sleep)
    monkeypatch.setattr("backend.app.discovery.random.uniform", lambda *args: 0)
    p = OnchainPumpDiscovery(lambda _: pytest.fail("No market event expected"), URL,
                             on_gap=lambda: gaps.append(True))
    with pytest.raises(asyncio.CancelledError):
        await p.run()
    assert delays == [1] and len(options) == 1
    assert options[0] == dict(max_size=262144, max_queue=16, open_timeout=15,
                             ping_interval=20, ping_timeout=20, close_timeout=5)
    assert p.health["reconnects"] == p.health["errors"] == 1
    assert p.health["transport_failure_counts"][category] == 1
    assert sum(p.health["transport_failure_counts"].values()) == 1
    assert p.health["transport_shutdowns"] == 1
    assert p.health["global_reset_reasons"]["transport"] == 1
    assert p.health["global_reset_reasons"]["shutdown"] == 1
    assert len(gaps) == 2 and not p.health["connected"] and p.health["subscriptions"] == 0
    assert len(p.connected_intervals) == (stage == "receive")
    assert [x["state"] for x in p.health["transport_transitions"]] == (
        ["CONNECTED", "DISCONNECTED"] if stage == "receive" else ["DISCONNECTED"])
    if sent:
        assert sent[0]["method"] == "logsSubscribe"
        assert sent[0]["params"][1] == {"commitment": "confirmed"}
    assert MARKER not in json.dumps(p.health)


@pytest.mark.parametrize("stage", ["connect", "ack", "receive"])
async def test_pure_application_cancellation_has_no_failure_or_retry(monkeypatch, stage):
    class Socket:
        reads = 0

        async def send(self, value):
            pass

        async def recv(self):
            self.reads += 1
            if stage == "receive" and self.reads == 1:
                return json.dumps({"id": 1, "result": 7})
            raise asyncio.CancelledError()

    class Context:
        async def __aenter__(self):
            if stage == "connect":
                raise asyncio.CancelledError()
            return Socket()

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr("backend.app.discovery.websockets.connect", lambda *args, **kwargs: Context())
    p = OnchainPumpDiscovery(lambda _: None, URL)
    with pytest.raises(asyncio.CancelledError):
        await p.run()
    assert sum(p.health["transport_failure_counts"].values()) == 0
    assert p.health["errors"] == p.health["reconnects"] == 0
    assert p.health["transport_shutdowns"] == 1
    assert p.health["global_reset_reasons"]["transport"] == 0
    assert p.health["global_reset_reasons"]["shutdown"] == 1
    assert p.health["transport_diagnostics"][-1]["kind"] == "shutdown"


async def test_health_api_safe_and_incomplete_evidence_not_upgraded(tmp_path, monkeypatch):
    monkeypatch.setenv("SOLANA_WS_URL", URL)
    engine = RadarEngine(Settings(mode="OBSERVE"), tmp_path / "synthetic.db", offline=True)
    try:
        token = Token("synthetic", "Diagnostic", "TEST", 1000)
        token.features = {"180": {"samples": 3, "units_valid": True, "continuity_valid": False}}
        engine.tokens[token.mint] = token
        before = engine.trade_status(token)
        engine.onchain.record_transport_failure(ConnectionClosedError(Close(1008, URL), None), "receive")
        assert engine.trade_status(token) == before != "CURRENT"
        app = create_app()
        app.state.engine = engine  # No lifespan: no provider or monitor tasks.
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
            for route in ("/api/health", "/api/dashboard"):
                response = await client.get(route)
                assert response.status_code == 200
                assert MARKER not in response.text and URL not in response.text
            health = (await client.get("/api/dashboard")).json()["health"]["providers"]["Onchain discovery"]
            assert health["transport_diagnostics"][-1]["received_close_code"] == 1008
        assert not engine.tasks and engine.approved_evidence is None
    finally:
        await engine.stop()
