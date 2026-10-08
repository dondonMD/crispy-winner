import pytest
import httpx
from backend.app.config import Settings
from backend.app.domain import Deduplicator, MarketEvent, PriorityBuffer, State, Token
from backend.app.providers import HttpProvider, PumpPortalProvider, TOKEN_PROGRAM, TOKEN_2022
from backend.app.security import analyse_security

MINT = "So11111111111111111111111111111111111111112"


def test_dedup_bounded_and_queue_priority():
    seen = Deduplicator(2)
    assert seen.accept("one") and not seen.accept("one")
    seen.accept("two")
    seen.accept("three")
    assert len(seen.seen) == 2
    q = PriorityBuffer(2)
    for i, p in enumerate([1, 2, 5]):
        q.put(MarketEvent(mint=str(i), ts=i, source="test", kind="create", event_id=str(i)), p)
    assert len(q.heap) == 2 and q.dropped == 1
    assert {e.mint for e in q.drain()} == {"1", "2"}


def test_state_no_direct_entry():
    t = Token("mint", "name", "symbol", 0)
    with pytest.raises(ValueError):
        t.transition(State.ENTRY_CANDIDATE)
    t.transition(State.SCREENING)
    t.transition(State.WATCHING)
    t.transition(State.GRADUATING)
    t.transition(State.GRADUATED)
    t.transition(State.POST_GRAD_OBSERVATION)


def test_pump_normalization():
    p = PumpPortalProvider(Settings(), lambda e: None, lambda: [])
    e = p.normalize({"txType": "create", "mint": MINT, "name": "hello"}, 100)
    assert e.kind == "create" and e.price is None and e.ts == 100
    assert p.normalize({"txType": "buy", "mint": MINT, "solAmount": 2}) is None
    e = p.normalize(
        {"txType": "buy", "mint": MINT, "signature": "sig", "solAmount": 2, "traderPublicKey": "wallet"}, 100
    )
    assert e.currency == "unknown" and e.volume == 2 and e.price is None


def report(program=TOKEN_PROGRAM, extensions=None):
    return analyse_security(
        {
            "owner": program,
            "data": {
                "parsed": {
                    "type": "mint",
                    "info": {"mintAuthority": None, "freezeAuthority": None, "extensions": extensions or []},
                }
            },
        },
        {"amount": "1000"},
        [
            {"address": "a", "amount": "400"},
            {"address": "b", "amount": "30"},
            {"address": "c", "amount": "20"},
        ],
        [
            {"data": {"parsed": {"info": {"owner": "curve", "mint": MINT}}}},
            {"data": {"parsed": {"info": {"owner": "person", "mint": MINT}}}},
            {"data": {"parsed": {"info": {"owner": "person", "mint": MINT}}}},
        ],
        "person",
        {"curve"},
        100,
    )


def test_owner_grouping_excludes_curve():
    r = report()
    assert r["top_1_independent_pct"] == 5 and r["creator_pct"] == 5
    assert r["excluded_supply_pct"] == 40


def test_token2022_metadata_safe_unknown_fails_closed():
    r = report(TOKEN_2022, [{"extension": "metadataPointer"}])
    assert not r["hard_failures"] and r["data_quality"] == "VERIFIED"
    r = report(TOKEN_2022, [{"extension": "transferHook"}])
    assert r["hard_failures"]
    r = report(TOKEN_2022, [{"extension": "newUnknownExtension"}])
    assert r["data_quality"] == "UNKNOWN" and r["risk_score"] > 0


async def test_http_errors_bounded(monkeypatch):
    calls = []

    async def no_wait(*args):
        pass

    monkeypatch.setattr("backend.app.providers.asyncio.sleep", no_wait)

    def handler(request):
        calls.append(request)
        return httpx.Response(429, headers={"Retry-After": "1"})

    p = HttpProvider("test", 100000, httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    with pytest.raises(RuntimeError):
        await p.request("GET", "https://example.test")
    assert len(calls) == 3 and not p.health["connected"]
    await p.close()


async def test_malformed_json_timeout_and_size(monkeypatch):
    async def no_wait(*args):
        pass

    monkeypatch.setattr("backend.app.providers.asyncio.sleep", no_wait)
    for response in [httpx.Response(200, content=b"not-json"), httpx.Response(200, content=b"x" * 2_000_001)]:
        provider = HttpProvider(
            "test", 100000, httpx.AsyncClient(transport=httpx.MockTransport(lambda r: response))
        )
        with pytest.raises(RuntimeError):
            await provider.request("GET", "https://example.test")
        assert provider.health["errors"] == 3
        await provider.close()

    def timeout(request):
        raise httpx.ReadTimeout("slow provider")

    provider = HttpProvider("test", 100000, httpx.AsyncClient(transport=httpx.MockTransport(timeout)))
    with pytest.raises(RuntimeError):
        await provider.request("GET", "https://example.test")
    assert provider.health["errors"] == 3
    await provider.close()


async def test_websocket_disconnect_reconnect_resubscribe(monkeypatch):
    import asyncio
    from websockets.exceptions import ConnectionClosedError

    sent = []
    connections = []

    class Socket:
        async def send(self, message):
            sent.append(message)

        async def recv(self):
            if len(connections) > 1:
                raise asyncio.CancelledError()
            raise ConnectionClosedError(None, None)

    class Connection:
        async def __aenter__(self):
            connections.append(1)
            return Socket()

        async def __aexit__(self, *args):
            return False

    async def no_sleep(*args):
        pass

    monkeypatch.setattr("backend.app.providers.websockets.connect", lambda *a, **k: Connection())
    monkeypatch.setattr("backend.app.providers.asyncio.sleep", no_sleep)
    provider = PumpPortalProvider(Settings(), lambda e: None, lambda: [])
    with pytest.raises(asyncio.CancelledError):
        await provider.run()
    assert provider.health["reconnects"] == 1
    assert len(connections) == 2
    assert sum("subscribeNewToken" in s for s in sent) == 2
    assert not any("subscribeTokenTrade" in s for s in sent)
