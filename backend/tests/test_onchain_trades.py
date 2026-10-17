"""Deterministic synthetic wire examples from the pinned official field layout."""
import base64
import struct
import time

import pytest
from solders.pubkey import Pubkey

from backend.app.discovery import SCHEMA, FIELDS, OnchainPumpDiscovery, decode_event
from backend.app.domain import MarketEvent, PriorityBuffer, State
from backend.app.features import window_features
from backend.tests.test_onchain_discovery import notification, FIXTURE

WSOL = "So11111111111111111111111111111111111111112"
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"


def wire(**overrides):
    values = dict(mint=FIXTURE['fields']['mint'], user=FIXTURE['fields']['creator'],
                  timestamp=int(time.time()), token_amount=1000000, quote_amount=2000000000,
                  quote_mint=WSOL, is_buy=True, ix_name='buy_v3')
    values.update(overrides)
    raw = bytes(next(e['discriminator'] for e in SCHEMA['events'] if e['name'] == 'TradeEvent'))
    for f in FIELDS['TradeEvent']:
        kind = f['type']
        value = values.get(f['name'])
        if kind == 'pubkey':
            raw += bytes(Pubkey.from_string(value) if value else Pubkey.default())
        elif kind == 'string':
            value = (value or '').encode()
            raw += struct.pack('<I', len(value)) + value
        elif kind == 'bool':
            raw += bytes([bool(value)])
        elif isinstance(kind, dict):
            raw += struct.pack('<I', 0)
        else:
            raw += struct.pack('<q' if kind == 'i64' else '<Q', value or 0)
    return base64.b64encode(raw).decode()


def payload(*events):
    n = notification()
    n['params']['result']['value']['logs'][1:2] = ['Program data: ' + e for e in events]
    return n


@pytest.mark.parametrize('buy', [True, False])
def test_buy_sell_wallet_mint_units_and_replay(buy):
    events = []
    p = OnchainPumpDiscovery(lambda e: events.append(e) or True, 'wss://test', tracked=lambda m: True)
    n = payload(wire(is_buy=buy), wire(is_buy=buy))
    p.receive(n)
    p.receive(n)
    assert len(events) == 2 and events[0].event_id != events[1].event_id
    assert p.health['duplicate_trades'] == 2
    e = events[0]
    assert e.wallet == FIXTURE['fields']['creator'] and e.mint == FIXTURE['fields']['mint']
    assert e.side == ('buy' if buy else 'sell')
    assert e.volume == 2 and e.currency == 'SOL' and e.price is None
    assert e.evidence['slot'] == 123 and e.evidence['units_valid']
    assert p.health['http_requests'] == 0


@pytest.mark.parametrize('quote,amount,currency,volume', [(USDC, 2500000, 'USDC', 2.5),
    (str(Pubkey.default()), 5, 'unknown', 0), (str(Pubkey.new_unique()), 5, 'unknown', 0)])
def test_quote_units_fail_closed(quote, amount, currency, volume):
    events = []
    p = OnchainPumpDiscovery(lambda e: events.append(e) or True, tracked=lambda m: True)
    p.receive(payload(wire(quote_mint=quote, quote_amount=amount)))
    assert events[0].currency == currency and events[0].volume == volume
    assert events[0].evidence['units_valid'] == (currency != 'unknown')


def test_untracked_and_failed_invocation_ignored():
    events = []
    p = OnchainPumpDiscovery(events.append)
    p.receive(payload(wire()))
    assert not events and p.health['untracked_trades'] == 1
    p = OnchainPumpDiscovery(events.append, tracked=lambda m: True)
    n = payload(wire())
    n['params']['result']['value']['logs'][-1] = n['params']['result']['value']['logs'][-1].replace('success', 'failed: caught')
    p.receive(n)
    assert not events


@pytest.mark.parametrize('changes', [dict(token_amount=0), dict(quote_amount=0), dict(timestamp=1),
    dict(timestamp=9999999999), dict(user=str(Pubkey.default()))])
def test_invalid_amount_timestamp_wallet(changes):
    with pytest.raises(ValueError):
        decode_event(wire(**changes))


def test_truncated_and_unsupported():
    raw = base64.b64decode(wire())
    for broken in (raw[:-1], raw + b'\0', raw[:56] + b'\x02' + raw[57:]):
        with pytest.raises((ValueError, struct.error, IndexError)):
            decode_event(base64.b64encode(broken).decode())


def test_normalized_breadth_flow_whale_and_creator():
    events = []
    p = OnchainPumpDiscovery(lambda e: events.append(e) or True, tracked=lambda m: True)
    creator = FIXTURE['fields']['creator']
    p.receive(payload(wire(user=creator), wire(user=str(Pubkey.new_unique()), quote_amount=1000000000),
                      wire(user=creator, is_buy=False, quote_amount=1000000000)))
    f = window_features(events, time.time(), 180, creator)
    assert f['raw_unique_buyers'] == 2 and f['estimated_independent_buyers'] == 2
    assert f['flow_ratio'] == 3 and f['whale_share'] == 2/3
    assert f['creator_sell_volume'] == 1
    assert window_features(events[:2], time.time(), 180, creator)['creator_sell_volume'] == 0


def test_queue_protects_critical_and_accounts_trade_loss():
    q = PriorityBuffer(1)
    trade = MarketEvent(mint='mint', ts=1, source='test', kind='trade', event_id='1')
    create = trade.model_copy(update=dict(kind='create', event_id='2'))
    assert q.put(trade, 30) and q.put(create, 105)
    assert q.dropped_trades == 1 and q.dropped_critical == 0 and 'mint' in q.trade_gaps
    assert q.drain() == [create]


def test_continuity_outage_rebuild_and_queue_gap(tmp_path):
    from backend.app.config import Settings
    from backend.app.engine import RadarEngine
    from backend.app.domain import Token

    engine = RadarEngine(Settings(mode='OBSERVE', trade_stream_enabled=False), tmp_path / 'trade.db')
    now = time.time()
    token = Token('mint', 'name', 'sym', now - 400)
    token.trade_tracking_since = now - 400
    token.last_trade = now
    token.features = {'180': {'samples': 3, 'units_valid': True, 'continuity_valid': True}}
    engine.onchain.health.update(connected=True, connected_since=now - 200)
    assert engine.trade_status(token, now) == 'CURRENT'
    engine.onchain.health['connected'] = False
    assert engine.trade_status(token, now) == 'PARTIAL'
    engine.onchain.health.update(connected=True, connected_since=now)
    # Recalculation must invalidate the old coverage after reconnect.
    token.events.extend(MarketEvent(mint='mint', ts=now, source='Solana WSS', kind='trade',
        event_id=str(i), currency='SOL', volume=1, wallet=str(i), side='buy') for i in range(3))
    engine.analyse(token, now)
    assert engine.trade_status(token, now) == 'PARTIAL'
    token.last_trade = now + 181
    engine.analyse(token, now + 181)
    # The old samples aged out: coverage alone cannot invent observations.
    assert engine.trade_status(token, now + 181) == 'UNAVAILABLE'
    token.events.extend(e.model_copy(update={'ts': now + 181}) for e in list(token.events)[:3])
    engine.analyse(token, now + 181)
    assert engine.trade_status(token, now + 181) == 'CURRENT'
    token.trade_gap = now + 181
    engine.analyse(token, now + 181)
    assert engine.trade_status(token, now + 181) == 'PARTIAL'
    engine.db.engine.dispose()


def test_engine_tracked_submission_no_http_and_distinct_identity(tmp_path):
    from backend.app.config import Settings
    from backend.app.engine import RadarEngine
    from backend.app.domain import Token

    engine = RadarEngine(Settings(mode='OBSERVE', trade_stream_enabled=False), tmp_path / 'tracked.db')
    mint = FIXTURE['fields']['mint']
    now = time.time()
    token = Token(mint, 'name', 'sym', now, creator=FIXTURE['fields']['creator'], state=State.WATCHING)
    engine.tokens[mint] = token
    requests = engine.rpc.health['requests']
    engine.onchain.receive(payload(wire(), wire(is_buy=False)))
    assert len(engine.queue.heap) == 2
    for event in engine.queue.drain():
        assert engine.process(event, now)
    assert len(token.events) == 2
    assert engine.trade_observations == {'buy': 1, 'sell': 1}
    assert engine.rpc.health['requests'] - requests == 0
    assert engine.onchain.health['http_requests'] == 0
    del engine.tokens[mint]
    n = payload(wire())
    from solders.signature import Signature
    n['params']['result']['value']['signature'] = str(Signature.new_unique())
    engine.onchain.receive(n)
    assert not engine.queue.heap
    engine.db.engine.dispose()


def test_legacy_sol_requires_independently_verified_curve_quote():
    events = []
    p = OnchainPumpDiscovery(lambda e: events.append(e) or True, tracked=lambda m: True,
                             quote_for=lambda m: WSOL)
    p.receive(payload(wire(quote_mint=str(Pubkey.default()), quote_amount=0,
                           sol_amount=2000000000, ix_name='buy')))
    assert events[0].volume == 2 and events[0].currency == 'SOL'
    assert events[0].evidence['quote_source'] == 'verified curve'
    events.clear()
    p = OnchainPumpDiscovery(lambda e: events.append(e) or True, tracked=lambda m: True)
    p.receive(payload(wire(quote_mint=str(Pubkey.default()), quote_amount=0,
                           sol_amount=2000000000, ix_name='buy')))
    assert events[0].currency == 'unknown' and not events[0].evidence['units_valid']


def test_conflicting_verified_quote_fails_closed():
    events = []
    p = OnchainPumpDiscovery(lambda e: events.append(e) or True, tracked=lambda m: True,
                             quote_for=lambda m: USDC)
    p.receive(payload(wire()))
    assert events[0].currency == 'unknown'


def test_gap_callback_invalidates_current_features_immediately(tmp_path):
    from backend.app.config import Settings
    from backend.app.engine import RadarEngine
    from backend.app.domain import Token

    e = RadarEngine(Settings(mode='OBSERVE'), tmp_path / 'gaps.db')
    token = Token('mint', 'name', 'sym', time.time(), state=State.WATCHING)
    token.features = {'180': {'samples': 3, 'units_valid': True, 'continuity_valid': True,
                              'trade_evidence': 'CURRENT'}}
    e.tokens['mint'] = token
    e.onchain.on_gap()
    assert not token.features['180']['continuity_valid']
    assert token.features['180']['trade_evidence'] == 'PARTIAL'
    assert token.trade_gap > 0
    e.db.engine.dispose()


def test_queue_drop_degrades_engine_and_unknown_display_is_not_zero(tmp_path):
    from backend.app.config import Settings
    from backend.app.engine import RadarEngine
    from backend.app.domain import Token

    e = RadarEngine(Settings(mode='OBSERVE'), tmp_path / 'drops.db')
    now = time.time()
    token = Token('mint', 'name', 'sym', now - 400, state=State.WATCHING)
    token.trade_tracking_since = now - 400
    e.tokens['mint'] = token
    e.onchain.health.update(connected=True, connected_since=now - 400)
    e.queue = PriorityBuffer(1)
    trade = MarketEvent(mint='mint', ts=now, kind='trade', event_id='a', source='Solana WSS',
                        currency='SOL', volume=1, side='buy')
    token.events.extend(trade.model_copy(update={'event_id': str(i)}) for i in range(3))
    token.last_trade = now
    e.analyse(token, now)
    assert e.trade_status(token, now) == 'CURRENT'
    e.submit(trade)
    assert not e.submit(trade.model_copy(update={'event_id': 'b'}))
    e.analyse(token, time.time())
    assert e.trade_status(token) == 'PARTIAL'
    assert e.display_features(token)['flow_ratio'] is None
    token.events.clear()
    e.analyse(token, time.time())
    assert e.trade_status(token) == 'UNAVAILABLE'
    assert e.display_features(token)['buy_count'] is None
    e.db.engine.dispose()


@pytest.mark.parametrize('instruction', ['buy', 'buy_exact_sol_in', 'buy_exact_quote_in', 'sell'])
def test_default_event_quote_with_explicit_amount_requires_verified_sol_curve(instruction):
    events = []
    p = OnchainPumpDiscovery(lambda e: events.append(e) or True, tracked=lambda m: True,
                             quote_for=lambda m: WSOL)
    p.receive(payload(wire(quote_mint=str(Pubkey.default()), quote_amount=2000000000,
                           sol_amount=2000000000, ix_name=instruction, is_buy=instruction != 'sell')))
    assert events[0].currency == 'SOL' and events[0].volume == 2
    assert events[0].evidence['quote_source'] == 'verified curve'
