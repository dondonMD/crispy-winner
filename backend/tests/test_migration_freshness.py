"""Synthetic acquisition-vs-chain-time regressions; no RPC or live research."""
from unittest.mock import patch
import time

import pytest
from solders.pubkey import Pubkey

from backend.app.domain import MarketEvent, State, Token
from backend.app.pumpswap import VerifiedPool
from backend.app.truncation import Recovery, TruncationRecovery, transaction_impact
from backend.tests.test_migration_recovery import engine, fixture


def recovered(e, now, chain_age=30, observed_age=25, verified_age=0):
    tx, sig, mint, _, _ = fixture()
    tx['blockTime'] = now - chain_age
    t = Token(mint, 'Synthetic', 'TEST', now - 100, state=State.WATCHING)
    t.last_event = now - 1  # A later auxiliary observation must not hide the migration.
    t.price, t.last_price = 1, now - 30
    t.liquidity, t.last_liquidity = 10000, now - 30
    e.tokens[mint] = t
    identities = []
    transaction_impact(tx, sig, 123, lambda m: True, migrations=identities)
    with patch('backend.app.truncation.time.time', return_value=now - verified_age):
        e.recovery.emit_migrations(Recovery(sig, 123, now - observed_age), tx, identities)
    return t, e.queue.drain()[0]


@pytest.mark.parametrize('chain_age,observed_age', [(30,25),(40,39),(65,45)])
def test_old_chain_time_with_fresh_bounded_acquisition_is_accepted(tmp_path, chain_age, observed_age):
    e = engine(tmp_path)
    now = time.time()
    t, event = recovered(e, now, chain_age, observed_age)
    assert e.process(event, now)
    assert event.ts == t.graduation == now - chain_age
    row = e.db.rows('graduation')[0]
    assert row['timestamp'] == row['ts'] == event.ts
    assert e.db.rows('event')[0]['event']['ts'] == event.ts
    assert t.flow_epoch == now and t.last_analysis == now
    assert t.last_price == t.last_liquidity == now - 30
    assert t.last_trade == 0 and t.features['180']['samples'] == 0
    assert e.trade_coverage_seconds(t, now) == 0 and e.trade_status(t, now) == 'UNAVAILABLE'
    assert t.decision['decision'] != 'ALLOW_PAPER_ENTRY'
    assert e.recovery.health['recovered_migration_chain_age_accepted'] == 1
    assert not e.process(event, now)  # No second graduation/accepted-age count on replay.
    assert len(e.db.rows('graduation')) == 1
    assert e.recovery.health['recovered_migration_chain_age_accepted'] == 1
    e.db.engine.dispose()


@pytest.mark.parametrize('chain_age,observed_age,verified_age,counter', [
    (50,46,0,'recovery_window_rejected'),
    (40,40,21,'recovery_freshness_rejected'),
    (30,25,-1,'recovery_freshness_rejected'),
    (-1,0,0,'recovery_window_rejected'),
])
def test_acquisition_bounds_fail_closed(tmp_path, chain_age, observed_age, verified_age, counter):
    e = engine(tmp_path)
    now = time.time()
    t, event = recovered(e, now, chain_age, observed_age, verified_age)
    assert not e.process(event, now)
    assert not t.graduation
    assert e.recovery.health['recovered_migration_' + counter] == 1
    e.db.engine.dispose()


@pytest.mark.parametrize('field,value', [
    ('recovery_verified_at',None), ('truncation_observed_at',None),
    ('recovery_verified_at',float('nan')), ('truncation_observed_at',float('inf')),
    ('truncation_observed_at',True), ('recovery_verified_at','now'),
    ('identity_quality','PARTIAL'), ('data_quality','UNKNOWN'), ('instruction','buy_v3'),
    ('program',str(Pubkey.new_unique())), ('schema_source',{}),
])
def test_partial_spoofed_or_invalid_provenance_does_not_bypass_age(tmp_path, field, value):
    e = engine(tmp_path)
    now = time.time()
    t, event = recovered(e, now)
    event.evidence[field] = value
    assert not e.process(event, now)
    assert not t.graduation
    assert e.recovery.health['recovered_migration_missing_freshness_provenance'] == 1
    e.db.engine.dispose()


def test_complete_looking_source_is_not_a_recovery_proof(tmp_path):
    e = engine(tmp_path)
    now = time.time()
    t, event = recovered(e, now)
    e.recovery.verified_migrations.clear()
    assert not e.process(event, now)
    assert not t.graduation
    e.db.engine.dispose()


@pytest.mark.parametrize('kind', ['trade','market','security','curve','migration'])
def test_ordinary_stale_event_rules_unchanged(tmp_path, kind):
    e = engine(tmp_path)
    now = time.time()
    mint = str(Pubkey.new_unique())
    e.tokens[mint] = Token(mint, 'Synthetic', 'TEST', now - 100, state=State.WATCHING)
    event = MarketEvent(mint=mint, kind=kind, ts=now-30, source='Onchain Pump' if kind=='migration' else 'Solana WSS', event_id='stale')
    assert not e.process(event, now)
    assert not e.tokens[mint].graduation
    assert e.settings.max_data_age_seconds == 20
    e.db.engine.dispose()


def test_new_postgrad_epoch_waits_for_ack_and_full_180_seconds(tmp_path):
    e = engine(tmp_path)
    now = time.time()
    t, event = recovered(e, now, 40, 39)
    assert e.process(event, now)
    pool, quote = event.pair, event.evidence['quote_mint']
    t.security['verified_pools'] = [{'address':pool,'base_mint':t.mint,'quote_mint':quote}]
    record = VerifiedPool(pool,t.mint,quote)
    e.pumpswap.registry[pool] = e.pumpswap.pools[pool] = record
    e.pumpswap.health['connected'] = True
    assert e.trade_coverage_seconds(t, now+100) == 0  # Selected without ACK.
    e.pumpswap.since[pool] = now+100
    for delta in (279,280):
        at = now + delta
        t.events.extend(MarketEvent(mint=t.mint,kind='trade',ts=at,source='PumpSwap WSS',event_id=f'{delta}:{i}',
            currency='SOL',wallet=str(Pubkey.new_unique()),side='buy',volume=i+1,evidence={'venue':'PUMPSWAP','pool':pool}) for i in range(3))
        t.last_trade = at
        e.analyse(t, at)
        assert e.trade_status(t, at) == ('PARTIAL' if delta==279 else 'CURRENT')
    assert t.graduation == now-40 and t.flow_epoch == now
    assert TruncationRecovery.MAX_PENDING == 32 and TruncationRecovery.MAX_AGE == 45
    e.db.engine.dispose()
