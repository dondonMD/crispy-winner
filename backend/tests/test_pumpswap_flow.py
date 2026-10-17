"""Synthetic canonical wire fixtures; never supplied to live research."""
import base64
import json
import struct
import time

import pytest
from solders.pubkey import Pubkey
from solders.signature import Signature

from backend.app.config import Settings
from backend.app.domain import MarketEvent, State, Token
from backend.app.engine import RadarEngine
from backend.app.features import calculate_features
from backend.app.pumpswap import FIELDS, PROGRAM, QUOTES, SCHEMA, PumpSwapFlow, VerifiedPool

WSOL, USDC = QUOTES
POOL, MINT, USER = (str(Pubkey.new_unique()) for _ in range(3))


def wire(name="BuyEvent", **overrides):
    values = dict(timestamp=int(time.time()), pool=POOL, user=USER, base_amount_in=100, base_amount_out=100,
                  quote_amount_in=1_000_000_000, quote_amount_out=1_000_000_000,
                  user_quote_amount_in=1_100_000_000, user_quote_amount_out=900_000_000,
                  max_quote_amount_in=99_000_000_000, min_quote_amount_out=1, ix_name="buy_v2")
    values.update(overrides)
    raw = bytes(next(e["discriminator"] for e in SCHEMA["events"] if e["name"] == name))
    for f in FIELDS[name]:
        kind, value = f["type"], values.get(f["name"])
        if kind == "pubkey":
            raw += bytes(Pubkey.from_string(value) if value else Pubkey.default())
        elif kind == "string":
            encoded = (value or "").encode()
            raw += struct.pack("<I", len(encoded)) + encoded
        elif kind == "bool":
            raw += bytes([bool(value)])
        else:
            raw += int(value or 0).to_bytes(16 if kind == "i128" else 8, "little", signed=kind != "u64")
    return base64.b64encode(raw).decode()


def notification(*events, subscription=10):
    return {"method": "logsNotification", "params": {"subscription": subscription, "result": {
        "context": {"slot": 123}, "value": {"signature": str(Signature.default()), "err": None,
        "logs": [f"Program {PROGRAM} invoke [1]", *["Program data: " + e for e in events], f"Program {PROGRAM} success"]}}}}


def provider(quote=WSOL):
    accepted, gaps = [], []
    record = VerifiedPool(POOL, MINT, quote)
    p = PumpSwapFlow(lambda e: accepted.append(e) or True, lambda: [record],
                     lambda mint, **kw: gaps.append(mint), "wss://test")
    p.pools[POOL] = record
    p.registry[POOL] = record
    p.active[10] = POOL
    p.since[POOL] = time.time() - 200
    p.health["connected"] = True
    return p, accepted, gaps


@pytest.mark.parametrize("name,side,volume", [("BuyEvent", "buy", 1.1), ("SellEvent", "sell", .9)])
def test_canonical_executed_user_quote_fields_and_identity(name, side, volume):
    p, events, gaps = provider()
    p.handle(notification(wire(name)))
    assert not gaps and len(events) == 1
    event = events[0]
    assert (event.mint, event.wallet, event.side, event.volume) == (MINT, USER, side, volume)
    assert event.currency == "SOL" and event.price is None and event.source == "PumpSwap WSS"
    assert event.evidence["pool"] == POOL and event.evidence["slot"] == 123
    assert p.health["normal_trade_http_requests"] == 0


@pytest.mark.parametrize("quote,currency,volume", [(USDC, "USDC", 1100), (str(Pubkey.new_unique()), "unknown", 0)])
def test_units(quote, currency, volume):
    p, events, _ = provider(quote)
    p.handle(notification(wire()))
    assert events[0].currency == currency and events[0].volume == volume
    assert events[0].evidence["units_valid"] == (currency != "unknown")


@pytest.mark.parametrize("overrides", [{"pool": str(Pubkey.default())}, {"user": str(Pubkey.default())},
    {"timestamp": 0}, {"timestamp": int(time.time()) + 1000}, {"base_amount_out": 0}, {"user_quote_amount_in": 0},
    {"quote_amount_in": 0}])
def test_invalid_event_values_fail_closed(overrides):
    p, events, gaps = provider()
    p.handle(notification(wire(**overrides)))
    assert not events and gaps == [MINT] and p.health["decode_failures"] == 1


@pytest.mark.parametrize("mode", ["truncate", "short_discriminator", "tail", "bool", "pool", "framing"])
def test_malformed_and_pool_conflicts_gap_only_subscribed_token(mode):
    p, events, gaps = provider()
    raw = base64.b64decode(wire())
    if mode == "short_discriminator":
        raw = raw[:3]
    elif mode == "truncate":
        raw = raw[:20]
    elif mode == "tail":
        raw += b"x"
    elif mode == "bool":
        # BuyEvent track_volume follows seven pubkeys, two creator fee u64s.
        raw = raw[:360] + bytes([3]) + raw[361:]
    n = notification(base64.b64encode(raw).decode() if mode != "pool" else wire(pool=str(Pubkey.new_unique())))
    if mode == "framing":
        n["params"]["result"]["value"]["logs"].pop()
    p.handle(n)
    assert not events and gaps == [MINT]
    assert len(p.health["failure_categories"]) == 10


def test_failed_invocation_and_failed_transaction_no_evidence():
    p, events, gaps = provider()
    n = notification(wire())
    n["params"]["result"]["value"]["logs"][-1] = f"Program {PROGRAM} failed: custom error"
    p.handle(n)
    n["params"]["result"]["value"]["err"] = {"InstructionError": [0, "failed"]}
    p.handle(n)
    assert not events and not gaps


def test_multi_event_replay_dedup_bounded():
    p, events, _ = provider()
    p.dedup.maximum = 2
    n = notification(wire(), wire("SellEvent"))
    p.handle(n)
    p.handle(n)
    assert len(events) == 2 and events[0].event_id != events[1].event_id
    assert p.health["duplicates"] == 2 and len(p.dedup.seen) == 2


def test_truncation_local_transport_all():
    p, _, gaps = provider()
    other = VerifiedPool(str(Pubkey.new_unique()), str(Pubkey.new_unique()), WSOL)
    p.pools[other.address] = other
    p.active[11] = other.address
    old = p.since[other.address] = time.time() - 200
    n = notification()
    n["params"]["result"]["value"]["logs"] = ["Log truncated"]
    p.handle(n)
    assert gaps == [MINT] and p.since[other.address] == old
    p.disconnect()
    assert other.mint in gaps and not p.active and not p.since


class Socket:
    def __init__(self):
        self.sent = []

    async def send(self, raw):
        self.sent.append(json.loads(raw))


async def test_capacity_deterministic_duplicate_unsubscribe_ack_and_reconnect():
    records = [VerifiedPool(str(Pubkey.new_unique()), str(Pubkey.new_unique()), WSOL) for _ in range(30)]
    p = PumpSwapFlow(lambda e: True, lambda: records, lambda *a, **k: None, "wss://test")
    p.health["connected"] = True
    ws = Socket()
    await p.reconcile(ws)
    assert len(ws.sent) == 25 and list(p.pools) == [r.address for r in records[:25]]
    assert p.health["capacity_limited"] == 5 and not p.since
    await p.reconcile(ws)
    assert len(ws.sent) == 25
    for request in ws.sent:
        assert request["params"][0]["mentions"] == [records[request["id"] - 1].address]
        p.handle({"id": request["id"], "result": request["id"]}, now=1000)
    assert len(p.since) == 25
    records.pop(0)
    await p.reconcile(ws)
    unsub = ws.sent[-1]
    assert unsub["method"] == "logsUnsubscribe" and len(p.since) == 24
    p.handle({"id": unsub["id"], "result": True})
    await p.reconcile(ws)
    assert ws.sent[-1]["method"] == "logsSubscribe"
    p.disconnect()
    ws.sent.clear()
    await p.reconcile(ws)
    assert len(ws.sent) == 25 and not p.since


def engine(tmp_path):
    return RadarEngine(Settings(mode="OBSERVE", trade_stream_enabled=False), tmp_path / "flow.db", offline=True)


def postgrad(e, now):
    token = Token(MINT, "Synthetic test", "TEST", now - 500)
    token.state = State.POST_GRAD_OBSERVATION
    token.graduation = token.flow_epoch = now - 200
    token.flow_venue = "PUMPSWAP"
    token.security["verified_pools"] = [{"address": POOL, "base_mint": MINT, "quote_mint": WSOL}]
    e.tokens[MINT] = token
    e.pumpswap.pools[POOL] = VerifiedPool(POOL, MINT, WSOL)
    e.pumpswap.registry[POOL] = e.pumpswap.pools[POOL]
    e.pumpswap.since[POOL] = now - 200
    e.pumpswap.active[10] = POOL
    e.pumpswap.health["connected"] = True
    return token


def test_verified_registry_only_and_priority(tmp_path):
    e = engine(tmp_path)
    t = postgrad(e, time.time())
    assert e.verified_flow_pools() == [VerifiedPool(POOL, MINT, WSOL)]
    t.security["verified_pools"][0]["base_mint"] = str(Pubkey.new_unique())
    assert not e.verified_flow_pools()
    t.security["verified_pools"] = []
    assert not e.verified_flow_pools()
    e.db.engine.dispose()


def test_epoch_units_samples_freshness_and_provider_isolation(tmp_path):
    e = engine(tmp_path)
    now = time.time()
    t = postgrad(e, now)
    t.events.append(MarketEvent(mint=MINT, ts=now, source="Solana WSS", kind="trade", event_id="pre", wallet=USER,
                               side="buy", volume=50, currency="SOL"))
    e.analyse(t, now)
    assert t.features["180"]["samples"] == 0 and e.trade_status(t, now) == "UNAVAILABLE"
    for i in range(3):
        t.events.append(MarketEvent(mint=MINT, ts=now - 3 + i, source="PumpSwap WSS", kind="trade", event_id=str(i),
            wallet=str(Pubkey.new_unique()), side="buy", volume=i + 1, currency="SOL",
            evidence={"venue": "PUMPSWAP", "pool": POOL}))
    t.last_trade = now - 1
    e.analyse(t, now)
    assert e.trade_status(t, now) == "CURRENT"
    assert t.features["180"]["samples"] == 3 and t.features["180"]["estimated_independent_buyers"] == 3
    assert t.features["180"]["whale_share"] == .5
    e.invalidate_trade_coverage()
    e.invalidate_pump_token_coverage(MINT)
    assert e.trade_status(t, now) == "CURRENT"
    assert t.decision["decision"] != "ALLOW_PAPER_ENTRY"
    e.pumpswap.since[POOL] = now - 179
    e.refresh_trade_continuity(t, now)
    assert e.trade_status(t, now) == "PARTIAL"
    e.pumpswap.since[POOL] = now - 180
    e.refresh_trade_continuity(t, now)
    assert e.trade_status(t, now) == "CURRENT"
    assert e.trade_status(t, now + 20) == "PARTIAL"
    e.invalidate_postgrad_coverage(MINT, now=now)
    e.refresh_trade_continuity(t, now)
    assert e.trade_status(t, now) == "PARTIAL"
    assert e.settings.max_data_age_seconds == 20
    e.db.engine.dispose()


def test_migration_resets_epoch_and_late_pump_cannot_supply_flow(tmp_path):
    e = engine(tmp_path)
    now = time.time()
    t = Token(MINT, "Synthetic", "TEST", now - 500, state=State.WATCHING)
    t.last_trade = now
    e.tokens[MINT] = t
    assert e.process(MarketEvent(mint=MINT, ts=now, source="Solana WSS", kind="migration", event_id="migration"), now)
    assert t.flow_venue == "PUMPSWAP" and t.flow_epoch == now and t.last_trade == 0
    assert not e.process(MarketEvent(mint=MINT, ts=now, source="Solana WSS", kind="trade", event_id="late"), now)
    assert calculate_features(t, now)["180"]["samples"] == 0
    e.db.engine.dispose()


def test_actual_pipeline_creator_flow_and_zero_http(tmp_path):
    e = engine(tmp_path)
    now = time.time()
    t = postgrad(e, now)
    t.creator = USER
    requests = e.rpc.health["requests"]
    e.pumpswap.handle(notification(wire(), wire("SellEvent"), wire(user=str(Pubkey.new_unique()))))
    assert len(e.queue.heap) == 3
    for event in e.queue.drain():
        assert e.process(event, now)
    f = t.features["180"]
    assert e.rpc.health["requests"] == requests
    assert e.pumpswap.health["normal_trade_http_requests"] == 0
    assert f["buy_count"] == 2 and f["sell_count"] == 1
    assert f["creator_sell_volume"] == .9 and f["creator_buy_volume"] == 1.1
    assert f["flow_ratio"] == pytest.approx(2.2 / .9)
    assert t.decision["decision"] == "REJECT"  # Genuine creator selling preserves the existing hard gate.
    t.events[-1] = t.events[-1].model_copy(update={"currency": "unknown", "volume": 0})
    e.analyse(t, now)
    assert e.trade_status(t, now) == "UNAVAILABLE"
    e.db.engine.dispose()


def test_two_samples_not_current_and_pre_epoch_amm_excluded(tmp_path):
    e = engine(tmp_path)
    now = time.time()
    t = postgrad(e, now)
    for i in range(2):
        t.events.append(MarketEvent(mint=MINT, ts=now - i, source="PumpSwap WSS", kind="trade", event_id=str(i),
            wallet=USER, side="buy", volume=1, currency="SOL", evidence={"venue": "PUMPSWAP"}))
    t.last_trade = now
    e.analyse(t, now)
    assert e.trade_status(t, now) == "PARTIAL"
    t.flow_epoch = now - .5
    assert calculate_features(t, now)["180"]["samples"] == 1
    e.db.engine.dispose()


def test_lost_ack_and_changed_eligibility_fail_closed():
    p, events, gaps = provider()
    p.eligible = lambda: []
    p.selection()
    p.handle(notification(wire()))
    assert not events and gaps == [MINT] and not p.since
    p.pending[1] = ("subscribe", POOL, time.time())
    p.handle({"id": 1, "result": 12})
    assert not p.since
    p.pending[2] = ("subscribe", POOL, time.time())
    with pytest.raises(ValueError):
        p.handle({"id": 2, "error": {"code": -1}})


def test_pinned_schema_event_discriminators_and_types():
    assert SCHEMA["source"]["commit"] == "639b87fb45c3adeffa6f7c4a1bf0cb85e392bf22"
    assert next(e["discriminator"] for e in SCHEMA["events"] if e["name"] == "BuyEvent") == [103,244,82,31,44,245,119,119]
    assert next(e["discriminator"] for e in SCHEMA["events"] if e["name"] == "SellEvent") == [62,47,55,10,165,3,220,42]


def test_capacity_partial_token_pool_coverage_stays_unavailable():
    p, _, _ = provider()
    other = VerifiedPool(str(Pubkey.new_unique()), MINT, WSOL)
    p.registry[other.address] = other
    assert p.coverage(MINT, time.time()) == 0


def test_wrong_program_never_supplies_flow():
    p, events, gaps = provider()
    n = notification(wire())
    other = str(Pubkey.new_unique())
    logs = n["params"]["result"]["value"]["logs"]
    logs[0], logs[-1] = f"Program {other} invoke [1]", f"Program {other} success"
    p.handle(n)
    assert not events and not gaps


async def test_subscription_rejection_uses_exponential_backoff(monkeypatch):
    import asyncio
    import backend.app.pumpswap as module

    record = VerifiedPool(POOL, MINT, WSOL)
    p = PumpSwapFlow(lambda e: True, lambda: [record], lambda *a, **k: None, "wss://test")
    delays = []

    class RejectingSocket(Socket):
        async def recv(self):
            return json.dumps({"id": self.sent[-1]["id"], "error": {"code": -1}})

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    async def pause(delay):
        delays.append(delay)
        if len(delays) == 2:
            raise asyncio.CancelledError

    monkeypatch.setattr(module.websockets, "connect", lambda *a, **k: RejectingSocket())
    monkeypatch.setattr(module.random, "uniform", lambda *a: 0)
    monkeypatch.setattr(module.asyncio, "sleep", pause)
    with pytest.raises(asyncio.CancelledError):
        await p.run()
    assert delays == [1, 2] and p.health["errors"] == 2
    assert not p.since and not p.active and not p.pending


async def test_unsubscribe_pending_does_not_repeatedly_gap_token():
    p, _, gaps = provider()
    p.eligible = lambda: []
    ws = Socket()
    await p.reconcile(ws)
    await p.reconcile(ws)
    assert len(ws.sent) == 1 and gaps == [MINT]
