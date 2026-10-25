"""Passive operational receipts only; isolated synthetic databases, no providers."""
import json
from collections import deque
from copy import deepcopy

import pytest

from backend.app import token_receipts
from backend.app.config import Settings
from backend.app.db import Database, EvidenceRun
from backend.app.domain import MarketEvent, Token
from backend.app.engine import RadarEngine


@pytest.fixture
async def engine(tmp_path):
    e = RadarEngine(Settings(mode='OBSERVE'), tmp_path / 'receipt.db', offline=True)
    e.tokens.clear()
    yield e
    await e.stop()


def token(engine, mint='SYNTHETIC', now=10000):
    t = Token(mint, 'Synthetic', 'TEST', now-200)
    t.trade_tracking_since = now-190
    engine.tokens[mint] = t
    return t


def trade(mint, stamp, currency='SOL', reason=None):
    return MarketEvent(mint=mint, ts=stamp, event_id=f'synthetic:{stamp}:{currency}',
        source='SYNTHETIC', kind='trade', currency=currency, side='buy', volume=1,
        wallet='WALLET_MUST_NOT_APPEAR', evidence={'unit_failure_reason': reason})


def test_window_units_reasons_and_no_mutation(engine):
    t = token(engine)
    t.events = deque([trade(t.mint, 9819), trade(t.mint, 9820),
        trade(t.mint, 9998, 'unknown', 'curve_not_verified'),
        trade(t.mint, 9999, 'unknown'), trade(t.mint, 10001)], maxlen=500)
    t.last_trade = 9999
    t.features = {'180': dict(samples=99, units_valid=True, continuity_valid=False)}
    before = deepcopy(t.__dict__)
    r = engine.token_evidence_receipt(10000)['current']['tokens'][0]
    assert r['retained_window']['samples'] == 3
    assert r['retained_window']['recognised_units'] == 1
    assert r['retained_window']['unknown_or_unrecognised_units'] == 2
    assert r['retained_window']['mixed_currencies']
    assert r['retained_window']['unit_failure_reasons']['curve_not_verified'] == 1
    assert r['retained_window']['unit_failure_reasons']['UNAVAILABLE'] == 1
    assert r['feature_samples'] == 99  # Discrepancy visible, never rewritten.
    assert r['last_trade_age'] == 1
    assert t.__dict__ == before
    assert 'WALLET_MUST_NOT_APPEAR' not in json.dumps(r)
    assert r['classification'] == engine.trade_status(t, 10000)


def test_selection_and_serialized_size_bound(engine):
    for i in range(250):
        t = token(engine, f'{i:064d}')
        t.last_trade = 9999
        for reason in token_receipts.RESET_REASONS:
            engine.invalidate_token_trade_coverage(t.mint, reason=reason, now=9998)
    a = engine.token_evidence_receipt(10000)
    assert len(a['current']['tokens']) <= 12
    assert a['current']['omitted_selection'] == 238
    assert len(json.dumps(a['current']).encode()) <= token_receipts.SECTION_BYTES
    assert len(a['current']['tokens']) + a['current']['omitted_bytes'] == 12
    assert a == engine.token_evidence_receipt(10000)
    assert a['current']['tokens'][0]['mint'] == '0'*64


def test_saturated_counts_and_active_loss(engine):
    t = token(engine)
    t.operational_evidence['buffer_evictions'] = token_receipts.MAX_COUNT
    token_receipts.increment(t.operational_evidence, 'buffer_evictions')
    assert t.operational_evidence['buffer_evictions'] == token_receipts.MAX_COUNT
    assert t.operational_evidence['counter_saturated']
    engine.invalidate_token_trade_coverage(t.mint, 'buffer', now=10000, known_loss_at=9820)
    row = engine.token_evidence_receipt(10000)['current']['tokens'][0]
    assert row['active_window_trade_lost'] and row['blockers']['loss_watermark_unexpired']
    assert not engine.token_evidence_receipt(10001)['current']['tokens'][0]['active_window_trade_lost']


def test_diagnostic_failure_does_not_upgrade_or_mutate(engine, monkeypatch):
    t = token(engine)
    before = deepcopy(t.__dict__)
    def fail(*args):
        raise ValueError('untrusted exception text must not leak')
    monkeypatch.setattr(token_receipts, 'section', fail)
    r = engine.token_evidence_receipt(10000)
    assert r['current']['status'] == 'UNAVAILABLE' and r['current']['omitted_error'] == 1
    assert r['current']['errors'] == 1
    assert 'untrusted' not in json.dumps(r)
    assert before == t.__dict__


async def test_shutdown_receipt_is_durable_and_restart_does_not_restore_coverage(tmp_path):
    path = tmp_path / 'restart.db'
    e = RadarEngine(Settings(mode='OBSERVE'), path, offline=True)
    t = token(e)
    engine_before = e.trade_continuity['global_resets']
    e.invalidate_token_trade_coverage(t.mint, 'recovery', now=9999)
    # Post-grad shutdown uses the old decode reason: receipt separates its phase.
    t.flow_venue = 'PUMPSWAP'
    await e.stop()
    db = Database(path)
    with db.sessions() as sql:
        p = json.loads(sql.get(EvidenceRun, e.session).payload)
    db.engine.dispose()
    r = p['token_evidence']
    assert p['checkpoint_complete'] and p['continuity']['global_resets'] == engine_before + 1
    assert r['pre_shutdown']['phase'] == 'LIVE'
    before = r['pre_shutdown']['tokens'][0]['counters']
    after = r['current']['tokens'][0]['counters']
    assert before['live_resets'] == {'recovery': 1}
    assert before['last_reset']['gap_at'] == 9999 and before['last_reset']['phase'] == 'LIVE'
    assert before['last_reset']['recorded_at'] > 9999
    assert after['shutdown_resets'] == {'decode': 1}
    assert r['current']['global_resets']['SHUTDOWN'] == 1
    restored = RadarEngine(Settings(mode='OBSERVE'), path, offline=True)
    try:
        assert all(not t.operational_evidence and not t.events for t in restored.tokens.values())
        assert all(restored.trade_status(t) != 'CURRENT' for t in restored.tokens.values())
        with restored.db.sessions() as sql:
            assert json.loads(sql.get(EvidenceRun, e.session).payload) == p
    finally:
        await restored.stop()


def test_record_budget_trims_only_optional_tokens(engine):
    for i in range(12):
        token(engine, f'{i:064d}')
    payload = dict(status='RUNNING', at=10000, accounting={'essential': 'x'*55000},
                   token_evidence=engine.token_evidence_receipt(10000))
    original = deepcopy(payload)
    engine.db.evidence_run('budget', payload)
    with engine.db.sessions() as sql:
        row = sql.get(EvidenceRun, 'budget')
        result = json.loads(row.payload)
        assert len(row.payload.encode()) < 65536
    assert result['accounting'] == payload['accounting']
    assert result['token_evidence']['omitted_record_budget'] > 0
    assert payload == original


def test_retention_expires_only_new_optional_data(engine):
    token(engine)
    payload = dict(status='STOPPED', at=10000, continuity={'global_resets': 3},
                   token_evidence=engine.token_evidence_receipt(10000))
    engine.db.evidence_run('old-diagnostics', payload)
    engine.db.evidence_run('legacy', {'status': 'STOPPED', 'at': 1})
    engine.db.retention(engine.settings, 10000 + 8*86400)
    with engine.db.sessions() as sql:
        old = json.loads(sql.get(EvidenceRun, 'old-diagnostics').payload)
        legacy = json.loads(sql.get(EvidenceRun, 'legacy').payload)
    assert old['token_evidence']['status'] == 'EXPIRED'
    assert old['continuity'] == payload['continuity'] and old['status'] == 'STOPPED'
    assert 'token_evidence' not in legacy


@pytest.mark.parametrize('quote,account,amount,reason', [
    ('11111111111111111111111111111111', '', 1, 'curve_not_verified'),
    ('Xs8S1uUs1zvS2p7iwtsG3b6fkhpvmwz4GYU3gWAmWHZ', '', 1, 'unsupported_quote'),
    ('EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v',
     'So11111111111111111111111111111111111111112', 1, 'identity_conflict'),
    ('11111111111111111111111111111111',
     'So11111111111111111111111111111111111111112', 0, 'unverified_quote_semantics'),
    ('So11111111111111111111111111111111111111112', '', 0, 'zero_executed_amount'),
])
def test_decoder_preserves_exact_failure_reason_without_accepting_units(quote, account, amount, reason):
    from backend.app.discovery import OnchainPumpDiscovery
    from backend.tests.test_onchain_trades import payload, wire
    events = []
    discovery = OnchainPumpDiscovery(lambda e: events.append(e) or True,
        tracked=lambda _: True, quote_for=lambda _: account)
    discovery.receive(payload(wire(quote_mint=quote, quote_amount=amount, sol_amount=1)))
    assert len(events) == 1
    assert events[0].currency == 'unknown' and events[0].volume == 0
    assert events[0].evidence['unit_failure_reason'] == reason
    assert discovery.health['unit_failure_reasons'][reason] == 1


def test_byte_omissions_and_no_unbounded_samples(engine, monkeypatch):
    for i in range(12):
        token(engine, f'{i:064d}')
    monkeypatch.setattr(token_receipts, 'SECTION_BYTES', 900)
    result = engine.token_evidence_receipt(10000)['current']
    assert result['omitted_bytes'] == 12 and result['tokens'] == []
    assert len(json.dumps(result).encode()) <= 900


def test_durable_failure_preserves_previous_receipt(engine, monkeypatch):
    from sqlalchemy import event
    from sqlalchemy.exc import OperationalError
    engine.db.evidence_run('durability', {'status': 'RUNNING', 'at': 1})

    def failed_commit(conn):
        raise OperationalError('commit', {}, Exception('synthetic rollback'))

    event.listen(engine.db.engine, 'commit', failed_commit)
    try:
        with pytest.raises(OperationalError):
            engine.db.evidence_run('durability', {'status': 'STOPPED', 'at': 2,
                'token_evidence': engine.token_evidence_receipt(10000)})
    finally:
        event.remove(engine.db.engine, 'commit', failed_commit)
    with engine.db.sessions() as sql:
        assert json.loads(sql.get(EvidenceRun, 'durability').payload)['at'] == 1


def test_bad_optional_encoding_cannot_prevent_core_accounting(engine):
    engine.db.evidence_run('encoding', {'status': 'RUNNING', 'accounting': {'processed': 3},
                                     'token_evidence': {'at': float('nan')}})
    with engine.db.sessions() as sql:
        row = json.loads(sql.get(EvidenceRun, 'encoding').payload)
    assert row['accounting'] == {'processed': 3}
    assert row['token_evidence']['status'] == 'UNAVAILABLE_ENCODING'


def test_mixed_recognised_assets_are_not_homogeneous(engine):
    t = token(engine)
    t.events.extend([trade(t.mint, 9998, 'SOL'), trade(t.mint, 9999, 'USDC')])
    row = engine.token_evidence_receipt(10000)['current']['tokens'][0]
    assert row['retained_window']['recognised_units'] == 2
    assert row['retained_window']['unknown_or_unrecognised_units'] == 0
    assert row['retained_window']['mixed_currencies']
    assert row['classification'] != 'CURRENT'


def test_retention_batch_is_bounded(engine):
    for i in range(34):
        engine.db.evidence_run(f'old:{i}', {'status': 'RUNNING',
            'token_evidence': engine.token_evidence_receipt(10000)})
    engine.db.retention(engine.settings, 10000 + 8*86400)
    with engine.db.sessions() as sql:
        rows = sql.query(EvidenceRun).filter(EvidenceRun.session.like('old:%')).all()
        expired = sum(json.loads(row.payload)['token_evidence'].get('status') == 'EXPIRED' for row in rows)
    assert expired == 32 and len(rows) == 34


async def test_running_receipt_survives_interrupted_session_without_claiming_new_coverage(tmp_path):
    path = tmp_path / 'interrupted.db'
    first = RadarEngine(Settings(mode='OBSERVE'), path, offline=True)
    t = token(first)
    first.invalidate_token_trade_coverage(t.mint, 'stale', now=9999)
    first.db.evidence_run(first.session, {'status': 'RUNNING',
                                        'token_evidence': first.token_evidence_receipt(10000)})
    original = None
    with first.db.sessions() as sql:
        original = sql.get(EvidenceRun, first.session).payload
    # New session must never adopt the old diagnostics as current evidence.
    second = RadarEngine(Settings(mode='OBSERVE'), path, offline=True)
    try:
        with second.db.sessions() as sql:
            assert sql.get(EvidenceRun, first.session).payload == original
        assert second.token_evidence_receipt(10001)['current']['global_resets']['LIVE'] == 0
    finally:
        await second.stop()
        await first.stop()


def test_failed_counter_hook_cannot_interrupt_real_invalidation(engine, monkeypatch):
    t = token(engine)
    t.features = {'180': dict(samples=3, units_valid=True, continuity_valid=True)}
    def fail(*args):
        raise ValueError('synthetic diagnostic failure')
    monkeypatch.setattr(token_receipts, 'reset', fail)
    engine.invalidate_token_trade_coverage(t.mint, 'recovery', now=10000)
    assert t.trade_gap == 10000 and not t.features['180']['continuity_valid']
    assert engine.trade_continuity['per_token_reasons']['recovery'] == 1
    row = engine.token_evidence_receipt(10000)['current']
    assert row['status'] == 'PARTIAL' and row['errors'] == 1
    assert row['tokens'][0]['classification'] != 'CURRENT'
