"""Synthetic pinned-layout diagnostics and continuity isolation regressions."""
import base64

import pytest
from solders.pubkey import Pubkey

from backend.app.discovery import (
    DecodeFailure, FAILURE_EVENTS, FAILURE_REASONS, OnchainPumpDiscovery,
    decode_event, event_prefix,
)
from backend.tests.test_onchain_trades import wire, payload, FIXTURE


def broken_wire(reason):
    raw = bytearray(base64.b64decode(wire()))
    if reason == "truncated":
        raw = raw[:-1]
    elif reason == "unsupported_layout":
        raw += b"\0"
    elif reason == "invalid_bool":
        raw[56] = 2
    elif reason == "invalid_string":
        raw[raw.index(b"buy_v3")] = 255
    elif reason == "invalid_pubkey":
        raw[57:89] = bytes(32)
    elif reason == "invalid_timestamp_value":
        raw[89:97] = bytes(8)
    else:
        return "@@@"
    return base64.b64encode(raw).decode()


@pytest.mark.parametrize("reason", ["truncated", "unsupported_layout", "invalid_bool", "invalid_string",
                                   "invalid_pubkey", "invalid_timestamp_value", "invalid_encoding"])
def test_deterministic_failure_reason(reason):
    with pytest.raises(DecodeFailure) as caught:
        decode_event(broken_wire(reason))
    assert caught.value.reason == reason
    p = OnchainPumpDiscovery(lambda e: True, tracked=lambda mint: True)
    p.receive(payload(broken_wire(reason)))
    assert p.health["decode_failures_by_reason"][reason] == 1
    expected = "unknown" if reason == "invalid_encoding" else "TradeEvent"
    assert p.health["decode_failure_matrix"][expected][reason] == 1


def test_diagnostics_have_fixed_cardinality_and_never_retain_messages():
    p = OnchainPumpDiscovery(lambda e: True)
    for i in range(2000):
        p.record_decode_failure(f"arbitrary-{i}", ValueError(f"wallet-or-payload-{i}"))
    assert set(p.health["decode_failures_by_reason"]) == set(FAILURE_REASONS)
    assert set(p.health["decode_failures_by_event"]) == set(FAILURE_EVENTS)
    assert len(p.health["decode_failure_matrix"]) == len(FAILURE_EVENTS)
    assert all(set(row) == set(FAILURE_REASONS) for row in p.health["decode_failure_matrix"].values())
    assert p.health["decode_failures_by_reason"]["other"] == 2000
    assert "wallet-or-payload" not in repr(p.health)
    assert len(p.health["diagnostic_discriminators"]) == 3


def test_prefix_recovery_does_not_read_invalid_tail():
    encoded = wire()
    name, mint = event_prefix(encoded[:54] + "!malformed-tail")
    assert name == "TradeEvent" and mint == FIXTURE["fields"]["mint"]
    with pytest.raises(DecodeFailure, match="truncated"):
        event_prefix(base64.b64encode(base64.b64decode(encoded)[:20]).decode())
    with pytest.raises(DecodeFailure, match="invalid_pubkey"):
        event_prefix(wire(mint=str(Pubkey.default())))


def test_framing_and_outer_diagnostics_are_separate():
    p = OnchainPumpDiscovery(lambda e: True)
    n = payload(wire())
    n["params"]["result"]["value"]["logs"].pop()
    p.receive(n)
    assert p.health["decode_failure_matrix"]["notification"]["invocation_framing"] == 1
    n = payload(wire())
    n["params"]["result"]["context"]["slot"] = -1
    p.receive(n)
    assert p.health["decode_failure_matrix"]["notification"]["outer_notification"] == 1


@pytest.fixture
def tracked_engine(tmp_path):
    import time
    from backend.app.config import Settings
    from backend.app.domain import Token, State, MarketEvent
    from backend.app.engine import RadarEngine

    e = RadarEngine(Settings(mode="OBSERVE", trade_stream_enabled=False), tmp_path / "scope.db")
    now = time.time()
    e.onchain.health.update(connected=True, connected_since=now - 400)
    for mint in (FIXTURE["fields"]["mint"], str(Pubkey.new_unique())):
        token = Token(mint, "synthetic", "SYN", now - 400, state=State.WATCHING)
        token.trade_tracking_since = now - 400
        token.last_trade = now
        token.events.extend(MarketEvent(mint=mint, ts=now, source="Solana WSS", kind="trade",
            event_id=f"{mint}:{i}", side="buy", wallet=str(i), volume=1, currency="SOL") for i in range(3))
        e.tokens[mint] = token
        e.analyse(token, now)
        assert e.trade_status(token, now) == "CURRENT"
    yield e
    e.db.engine.dispose()


def test_untracked_malformed_tail_is_prefix_filtered_without_tail_decode(tracked_engine, monkeypatch):
    import backend.app.discovery as discovery

    e = tracked_engine
    mint = str(Pubkey.new_unique())
    encoded = wire(mint=mint)[:54] + "!not-borsh-or-base64"
    def forbidden(encoded):
        raise AssertionError("untracked tail must never be decoded")
    monkeypatch.setattr(discovery, "decode_event", forbidden)
    e.onchain.receive(payload(encoded))
    assert e.onchain.health["trade_events_prefix_classified"] == 1
    assert e.onchain.health["untracked_trades_prefix_filtered"] == 1
    assert e.onchain.health["untracked_trades"] == 1
    assert e.onchain.health["decoding_errors"] == 0
    assert e.onchain.health["global_continuity_resets"] == 0
    assert e.trade_continuity["global_resets"] == 0
    assert all(t.trade_gap == 0 and e.trade_status(t) == "CURRENT" for t in e.tokens.values())
    assert e.onchain.health["http_requests"] == e.rpc.health["requests"] == 0


@pytest.mark.parametrize("reason", ["truncated", "unsupported_layout", "invalid_bool", "invalid_string",
                                   "invalid_pubkey", "invalid_timestamp_value", "invalid_encoding"])
def test_tracked_failure_is_local_and_other_token_remains_current(tracked_engine, reason):
    e = tracked_engine
    mint, other = e.tokens
    encoded = broken_wire(reason) if reason != "invalid_encoding" else wire()[:54] + "!broken"
    e.onchain.receive(payload(encoded))
    assert e.onchain.health["tracked_trade_decode_failures"] == 1
    assert e.onchain.health["per_token_decode_resets"] == 1
    assert e.onchain.health["global_continuity_resets"] == 0
    assert e.onchain.health["last_decode_gap"] == 0
    assert e.tokens[mint].trade_gap > 0 and e.trade_status(e.tokens[mint]) == "PARTIAL"
    assert e.tokens[other].trade_gap == 0 and e.trade_status(e.tokens[other]) == "CURRENT"
    assert e.trade_continuity["per_token_reasons"]["decode"] == 1


def test_unknown_trade_identity_fails_globally(tracked_engine):
    e = tracked_engine
    raw = base64.b64decode(wire())[:20]
    e.onchain.receive(payload(base64.b64encode(raw).decode()))
    assert e.onchain.health["unknown_mint_decode_failures"] == 1
    assert e.onchain.health["global_continuity_resets"] == 1
    assert e.onchain.health["decode_failure_matrix"]["TradeEvent"]["truncated"] == 1
    assert all(t.trade_gap > 0 and e.trade_status(t) == "PARTIAL" for t in e.tokens.values())


def test_prefix_filter_keeps_event_ordinals_and_replay_dedup():
    events = []
    tracked = {FIXTURE["fields"]["mint"]}
    untracked = str(Pubkey.new_unique())
    p = OnchainPumpDiscovery(lambda e: events.append(e) or True, tracked=tracked.__contains__)
    n = payload(wire(mint=untracked), wire(), wire(is_buy=False))
    p.receive(n)
    assert [e.evidence["event_ordinal"] for e in events] == [1, 2]
    assert len({e.event_id for e in events}) == 2
    tracked.add(untracked)
    p.receive(n)
    assert len(events) == 2
    assert p.health["duplicates"] == 1 and p.seen.maximum == 10000


def test_stale_trade_gap_is_local_and_limits_unchanged(tracked_engine):
    import time
    from backend.app.domain import MarketEvent

    e = tracked_engine
    mint, other = e.tokens
    now = time.time()
    assert e.settings.max_data_age_seconds == 20
    old = MarketEvent(mint=mint, ts=now - 21, source="Solana WSS", kind="trade", event_id="stale")
    assert not e.process(old, now)
    assert e.tokens[mint].trade_gap == now and e.tokens[other].trade_gap == 0
    assert e.trade_continuity["per_token_reasons"]["stale"] == 1
    # New valid samples do not remove a gap until the full existing window passes.
    t = e.tokens[mint]
    for age, expected in ((179, "PARTIAL"), (180, "CURRENT")):
        t.events.clear()
        t.events.extend(MarketEvent(mint=mint, ts=now + age, source="Solana WSS", kind="trade",
            event_id=f"rebuild:{i}", side="buy", wallet=str(i), volume=1, currency="SOL") for i in range(3))
        t.last_trade = now + age
        e.analyse(t, now + age)
        assert e.trade_status(t, now + age) == expected


async def test_transport_disconnect_still_invalidates_all(tracked_engine, monkeypatch):
    import asyncio
    import json
    e = tracked_engine
    class Socket:
        reads = 0
        async def send(self, message):
            pass
        async def recv(self):
            self.reads += 1
            if self.reads == 1:
                return json.dumps({"jsonrpc": "2.0", "id": 1, "result": 7})
            raise OSError("synthetic disconnect")
    class Connection:
        async def __aenter__(self):
            return Socket()
        async def __aexit__(self, *args):
            return False
    async def stop(delay):
        raise asyncio.CancelledError()
    monkeypatch.setattr("backend.app.discovery.websockets.connect", lambda *a, **k: Connection())
    monkeypatch.setattr("backend.app.discovery.asyncio.sleep", stop)
    e.onchain.health["enabled"] = True
    with pytest.raises(asyncio.CancelledError):
        await e.onchain.run()
    assert e.onchain.health["global_reset_reasons"]["transport"] == 1
    assert not e.onchain.health["connected"]
    assert all(t.trade_gap > 0 and not t.features["180"]["continuity_valid"] for t in e.tokens.values())


def test_local_gap_cannot_be_rewound_by_an_older_buffer_timestamp(tracked_engine):
    import time
    e = tracked_engine
    mint, other = e.tokens
    now = time.time()
    e.invalidate_token_trade_coverage(mint, now=now)
    e.invalidate_token_trade_coverage(mint, reason="buffer", now=now - 10)
    assert e.tokens[mint].trade_gap == now
    assert e.tokens[other].trade_gap == 0


def test_balanced_visible_frames_with_log_truncation_still_reset_global_coverage(tracked_engine):
    e = tracked_engine
    n = payload(wire())
    n["params"]["result"]["value"]["logs"].append("Log truncated")
    e.onchain.receive(n)
    assert e.onchain.health["balanced_log_truncation_gaps"] == 1
    assert e.onchain.health["global_reset_reasons"]["log_truncation"] == 1
    assert e.onchain.health["decoding_errors"] == 0
    assert all(e.trade_status(t) == "PARTIAL" for t in e.tokens.values())
    assert len(e.queue.heap) == 1  # Existing valid structured observations are retained.


def test_no_visible_event_fast_path_cannot_ignore_explicit_log_truncation(tracked_engine):
    e = tracked_engine
    n = payload(wire())
    logs = n["params"]["result"]["value"]["logs"]
    logs[1] = "Log truncated"
    e.onchain.receive(n)
    assert e.onchain.health["no_event_log_truncation_gaps"] == 1
    assert e.onchain.health["global_reset_reasons"]["log_truncation"] == 1
    assert not e.queue.heap
    assert all(e.trade_status(t) == "PARTIAL" for t in e.tokens.values())
