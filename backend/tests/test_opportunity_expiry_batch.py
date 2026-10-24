"""Atomic bounded expiry preserves every positive/negative/unavailable observation."""

import json
import sqlite3

import pytest
from sqlalchemy import event, select
from sqlalchemy.exc import OperationalError

from backend.app.config import Settings
from backend.app.db import Base, Database, OpportunityPendingRow
from backend.app.domain import Token
from backend.app.opportunity import load_intelligence_settings, opportunity_view
from backend.app.opportunity_research import OpportunityResearch


def research(path, n=25):
    db = Database(path)
    Base.metadata.create_all(db.engine)
    db.configure_budget(16)
    settings, cfg = Settings(mode="OBSERVE"), load_intelligence_settings()
    owner = OpportunityResearch(db, settings, cfg, "synthetic")
    for i in range(n):
        token = Token(f"synthetic:{i}", "", "", 100)
        owner.transition(token, opportunity_view(token, settings, 100, cfg), 100, "unchanged")
    for i, (identity, payload) in enumerate(owner.pending.items()):
        if i % 3:
            payload.update(
                baseline_price=10,
                latest_price=12 if i % 3 == 1 else 8,
                latest_price_ts=160,
                price_max=12,
                price_min=8,
                entry_liquidity=20000,
                latest_liquidity=20000,
                latest_liquidity_ts=160,
            )
            owner.save_pending(identity, payload)
    return db, owner


def persisted(db):
    with db.sessions() as sql:
        return {r.id: r.payload for r in sql.scalars(select(OpportunityPendingRow))}


@pytest.mark.parametrize("now", [160, 161, 2000])
def test_batch_equals_single_outcomes_exactly_and_preserves_order(tmp_path, now):
    a, single = research(tmp_path / "single.db")
    b, batched = research(tmp_path / "batch.db")
    for identity, payload in list(single.pending.items()):
        single.settle(identity, payload, now)
    batched.expire(now)
    assert a.rows("opportunity_outcome") == b.rows("opportunity_outcome")
    assert persisted(a) == persisted(b)
    assert single.pending == batched.pending
    assert single.outcome_count == batched.outcome_count
    if now == 161:
        rows = b.rows("opportunity_outcome")
        assert any(r["status"] == "UNAVAILABLE_GAP" for r in rows)
        assert any((r["estimated_after_cost_return_pct"] or 0) < 0 for r in rows)
        assert any((r["estimated_after_cost_return_pct"] or 0) > 0 for r in rows)
    batched.expire(now)
    assert a.rows("opportunity_outcome") == b.rows("opportunity_outcome")
    a.engine.dispose()
    b.engine.dispose()


def test_three_bounded_commits_then_cold_restart_and_noop(tmp_path):
    path = tmp_path / "bounded.db"
    db, owner = research(path)
    commits = []
    event.listen(db.engine, "commit", lambda conn: commits.append(1))
    owner.expire(161)
    assert len(commits) == 3 and owner.outcome_count == 25
    before = len(commits)
    for identity, payload in owner.pending.items():
        owner.save_pending(identity, payload)
    assert len(commits) == before  # Exact committed cache, no duplicate read/commit.
    old = db.rows("opportunity_outcome")
    db.engine.dispose()
    reopened = Database(path)
    reopened.configure_budget(16)
    restored = OpportunityResearch(
        reopened, Settings(mode="OBSERVE"), load_intelligence_settings(), "synthetic"
    )
    restored.expire(161)
    assert old == reopened.rows("opportunity_outcome")
    assert all(p["remaining"] == [180, 300, 600, 1800] for p in restored.pending.values())
    reopened.engine.dispose()


def test_failed_second_group_keeps_prefix_and_rolls_back_memory_then_retries(tmp_path):
    db, owner = research(tmp_path / "rollback.db")
    before = persisted(db)
    cache = dict(owner.committed_pending)
    attempts = []

    def fail(conn):
        attempts.append(1)
        if len(attempts) == 2:
            raise OSError("injected commit failure")

    event.listen(db.engine, "commit", fail)
    with pytest.raises(OSError):
        owner.expire(161)
    event.remove(db.engine, "commit", fail)
    assert len(db.rows("opportunity_outcome")) == owner.outcome_count == 10
    for index, (identity, payload) in enumerate(owner.pending.items()):
        if index >= 10:
            assert persisted(db)[identity] == before[identity]
            assert owner.committed_pending[identity] == cache[identity]
            assert 60 in payload["remaining"]
    owner.expire(161)
    rows = db.rows("opportunity_outcome")
    assert len(rows) == owner.outcome_count == 25
    assert len({(r["signal_id"], r["horizon"]) for r in rows}) == 25
    db.engine.dispose()


def test_partial_preparation_failure_rolls_back_whole_group(tmp_path, monkeypatch):
    db, owner = research(tmp_path / "partial.db")
    old = persisted(db)
    cache = dict(owner.committed_pending)
    original = owner.outcome_payload
    calls = []

    def failure(*args, **kwargs):
        calls.append(1)
        if len(calls) == 2:
            raise ValueError("invalid outcome")
        return original(*args, **kwargs)

    monkeypatch.setattr(owner, "outcome_payload", failure)
    with pytest.raises(ValueError):
        owner.expire(161)
    assert not db.rows("opportunity_outcome") and owner.outcome_count == 0
    assert persisted(db) == old and dict(owner.committed_pending) == cache
    assert all(60 in p["remaining"] for p in owner.pending.values())
    monkeypatch.setattr(owner, "outcome_payload", original)
    owner.expire(161)
    assert len(db.rows("opportunity_outcome")) == 25
    db.engine.dispose()


def test_busy_rollback_preserves_evidence_and_retry(tmp_path):
    path = tmp_path / "busy.db"
    db, owner = research(path, 3)
    before = persisted(db)
    with db.engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA busy_timeout=10")  # Test-only contention bound.
    lock = sqlite3.connect(path)
    lock.execute("BEGIN IMMEDIATE")
    try:
        with pytest.raises(OperationalError):
            owner.expire(161)
        assert owner.outcome_count == 0
        assert all(60 in p["remaining"] for p in owner.pending.values())
    finally:
        lock.rollback()
        lock.close()
    assert persisted(db) == before
    owner.expire(161)
    assert len(db.rows("opportunity_outcome")) == 3
    db.engine.dispose()


def test_replayed_horizon_and_oversized_group_are_not_acknowledged_twice(tmp_path):
    db, owner = research(tmp_path / "retry.db", 1)
    identity, payload = next(iter(owner.pending.items()))
    stale = json.loads(json.dumps(payload))
    owner.write_outcome(identity, payload, 60, 161, "UNAVAILABLE_GAP")
    owner.write_outcome(identity, stale, 60, 161, "UNAVAILABLE_GAP")
    assert len(db.rows("opportunity_outcome")) == owner.outcome_count == 1
    assert 60 not in stale["remaining"]
    with pytest.raises(ValueError):
        owner.commit_outcomes([(identity, payload, 60, 161, "UNAVAILABLE_GAP")] * 11)
    db.engine.dispose()


def test_killed_partial_group_cold_restart_preserves_prefix(tmp_path):
    import signal
    import subprocess
    import sys

    path = tmp_path / "killed.db"
    db, _ = research(path)
    db.engine.dispose()
    code = """
import os,signal,sys
from pathlib import Path
from sqlalchemy import event
from backend.app.db import Database
from backend.app.config import Settings
from backend.app.opportunity import load_intelligence_settings
from backend.app.opportunity_research import OpportunityResearch
x=Database(Path(sys.argv[1]));x.configure_budget(16)
r=OpportunityResearch(x,Settings(mode='OBSERVE'),load_intelligence_settings(),'synthetic')
n=[0]
def die(conn,cursor,statement,*args):
 if statement.startswith('INSERT INTO records'):
  n[0]+=1
  if n[0]==11:os.kill(os.getpid(),signal.SIGKILL)
event.listen(x.engine,'before_cursor_execute',die)
r.expire(161)
"""
    child = subprocess.run([sys.executable, "-c", code, str(path)], timeout=15)
    assert child.returncode == -signal.SIGKILL
    reopened = Database(path)
    reopened.configure_budget(16)
    assert len(reopened.rows("opportunity_outcome")) == 10
    restored = OpportunityResearch(
        reopened, Settings(mode="OBSERVE"), load_intelligence_settings(), "synthetic"
    )
    restored.expire(161)
    rows = reopened.rows("opportunity_outcome")
    assert len(rows) == len({(r["signal_id"], r["horizon"]) for r in rows}) == 25
    with reopened.engine.connect() as sql:
        assert sql.exec_driver_sql("PRAGMA integrity_check").scalar() == "ok"
    reopened.engine.dispose()


def test_full_error_rolls_back_without_discarding_negative_evidence(tmp_path):
    db, owner = research(tmp_path / "full.db")
    before = persisted(db)
    n = []

    def full(conn, cursor, statement, *args):
        if statement.startswith("INSERT INTO records"):
            n.append(1)
            if len(n) == 2:
                raise OperationalError(statement, {}, sqlite3.OperationalError("database or disk is full"))

    event.listen(db.engine, "before_cursor_execute", full)
    with pytest.raises(OperationalError):
        owner.expire(161)
    event.remove(db.engine, "before_cursor_execute", full)
    assert not db.rows("opportunity_outcome") and persisted(db) == before
    assert all(60 in p["remaining"] for p in owner.pending.values())
    owner.expire(161)
    assert len(db.rows("opportunity_outcome")) == 25
    db.engine.dispose()


@pytest.mark.parametrize("final", [False, True])
def test_commit_response_failure_is_reconciled_without_duplicate_or_missing_ack(tmp_path, monkeypatch, final):
    db, owner = research(tmp_path / "ambiguous.db", 3)
    if final:
        for identity, payload in owner.pending.items():
            payload["remaining"] = [60]
            owner.save_pending(identity, payload)
    original = db.engine.dialect.do_commit

    def committed_then_failed(connection):
        original(connection)
        raise OSError("commit response lost after durable commit")

    monkeypatch.setattr(db.engine.dialect, "do_commit", committed_then_failed)
    with pytest.raises(OSError):
        owner.expire(161)
    monkeypatch.setattr(db.engine.dialect, "do_commit", original)
    assert len(db.rows("opportunity_outcome")) == 3
    assert owner.outcome_count == 0
    assert all(60 in p["remaining"] for p in owner.pending.values())
    owner.expire(161)
    assert len(db.rows("opportunity_outcome")) == owner.outcome_count == 3
    if final:
        assert not owner.pending
    else:
        assert all(60 not in p["remaining"] for p in owner.pending.values())
    db.engine.dispose()


def test_missing_pending_without_durable_outcome_fails_closed(tmp_path):
    db, owner = research(tmp_path / "missing.db", 1)
    identity, payload = next(iter(owner.pending.items()))
    owner.save_pending(identity, None)
    with pytest.raises(RuntimeError, match="Missing committed research outcome"):
        owner.expire(161)
    assert 60 in payload["remaining"]
    assert not db.rows("opportunity_outcome") and owner.outcome_count == 0
    db.engine.dispose()
