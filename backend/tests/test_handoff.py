"""Read-only bounded handoff diagnostics, using isolated synthetic tokens."""
import copy
import time

from backend.app.domain import State
from backend.app.handoff import HandoffTrace
from backend.tests.test_pumpswap_flow import engine, postgrad, POOL, MINT


def status(e, t, now):
    e.trace_handoff(t, now)
    return e.handoff.snapshot(e.tokens, now)["records"][-1]


def test_pool_verification_ack_and_coverage_trace_does_not_change_policy(tmp_path):
    e = engine(tmp_path)
    now = time.time()
    t = postgrad(e, now)
    before = copy.deepcopy((t.decision, t.features, e.pumpswap.active, e.pumpswap.since, e.queue.snapshot()))
    requests = e.rpc.health['requests']
    r = status(e, t, now)
    assert r['stage'] == 'SAMPLES_INSUFFICIENT'
    assert r['migration_pool_verified'] is False
    assert (t.decision, t.features, e.pumpswap.active, e.pumpswap.since, e.queue.snapshot(now=e.queue.created))[:4] == before[:4]
    assert e.rpc.health['requests'] == requests
    e.pumpswap.since.clear()
    assert status(e, t, now)['stage'] == 'ACK_PENDING'
    e.pumpswap.pools.clear()
    assert status(e, t, now)['stage'] == 'SELECTION_PENDING'
    e.pumpswap.health['connected'] = False
    assert status(e, t, now)['stage'] == 'WSS_DISCONNECTED'
    t.security['verified_pools'] = []
    t.migration_pool = POOL
    assert status(e, t, now)['stage'] == 'SECURITY_NOT_ATTEMPTED'
    t.last_security_attempt = now
    assert status(e, t, now)['stage'] == 'SECURITY_PENDING'
    t.last_security = now
    assert status(e, t, now)['stage'] == 'POOL_NOT_VERIFIED'
    e.db.engine.dispose()


def test_rejection_and_removal_keep_the_exact_bounded_reason(tmp_path):
    e = engine(tmp_path)
    now = time.time()
    t = postgrad(e, now)
    reason = 'Synthetic security rejection: concentration gate'
    t.decision = {'decision':'REJECT', 'reasons':[reason]}
    e.transition(t, State.REJECTED, reason, now)
    del e.tokens[MINT]
    report = e.handoff_snapshot(now + 2)
    r = report['records'][0]
    assert r['stage'] == 'NO_LONGER_TRACKED'
    assert r['state'] == 'REJECTED' and r['decision_reasons'] == [reason]
    assert r['history'][-2]['reason'] == reason
    assert r['history'][-2]['stage'] == 'LIFECYCLE_INELIGIBLE'
    assert report['counts']['NO_LONGER_TRACKED'] == 1
    e.db.engine.dispose()


def test_trace_history_and_candidate_retention_are_bounded_and_copied():
    trace = HandoffTrace()
    for i in range(110):
        for j in range(40):
            trace.observe({'mint':str(i),'state':'REJECTED','stage':'LIFECYCLE_INELIGIBLE'}, j, 'transition', 'x'*500)
    report = trace.snapshot({str(i) for i in range(110)}, 50)
    assert len(report['records']) == trace.maximum == 100
    assert all(len(r['history']) == 32 for r in report['records'])
    assert all(len(h['reason']) <= 240 for r in report['records'] for h in r['history'])
    report['records'][0]['history'].clear()
    assert len(trace.snapshot({str(i) for i in range(110)}, 51)['records'][0]['history']) == 32


def test_probe_snapshots_retain_history_without_repeated_samples(tmp_path):
    e = engine(tmp_path)
    t = postgrad(e, time.time())
    now = time.time()
    r = e.handoff_snapshot(now)['records'][0]
    for _ in range(100):
        e.handoff_snapshot(now)
    assert len(e.handoff_snapshot(now)['records'][0]['history']) == len(r['history'])
    assert e.rpc.health['requests'] == 0
    assert t.state == State.POST_GRAD_OBSERVATION
    e.db.engine.dispose()
