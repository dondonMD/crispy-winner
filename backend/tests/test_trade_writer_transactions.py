"""Two durable boundaries are preserved; no whole-engine rollback is claimed."""

import json
import signal
import sqlite3
import subprocess
import sys
import time
from contextlib import closing

import pytest
from sqlalchemy import event
from sqlalchemy.exc import OperationalError

from backend.app.db import Base, Database


def database(path):
    db = Database(path)
    Base.metadata.create_all(db.engine)
    db.configure_budget(16)
    return db


def test_exact_two_transactions_indexed_identity_and_no_raw_observer(tmp_path):
    db = database(tmp_path / "two.db")
    commits, statements, checkouts, callbacks = [], [], [], []
    event.listen(db.engine, "commit", lambda conn: commits.append(1))
    event.listen(db.engine, "checkout", lambda *args: checkouts.append(1))
    event.listen(db.engine, "before_cursor_execute", lambda conn, cursor, sql, *args: statements.append(sql))
    db.record_observer = lambda *args: callbacks.append(1)
    assert db.reserve_event("one", 100)
    assert db.add("event", {"negative": "UNAVAILABLE"}, "synthetic", "test", 100)
    assert len(commits) == len(checkouts) == 2
    assert sum(s.startswith("PRAGMA freelist_count") for s in statements) == 2
    assert sum(s.startswith("INSERT INTO event_identities") for s in statements) == 1
    assert sum(s.startswith("INSERT INTO records") for s in statements) == 1
    assert not callbacks
    assert not db.reserve_event("one", 101)
    db.add("outcome", {"net_return_pct": -100}, "synthetic", "test", 101)
    assert len(callbacks) == 1 and db.rows("outcome")[0]["net_return_pct"] == -100
    db.engine.dispose()


@pytest.mark.parametrize("kind", ["identity", "event"])
def test_before_commit_rolls_back_and_direct_retry_is_safe(tmp_path, kind):
    db = database(tmp_path / "rollback.db")

    def fail(conn):
        raise OSError("before commit")

    event.listen(db.engine, "commit", fail)
    with pytest.raises(OSError):
        if kind == "identity":
            db.reserve_event("one", 100)
        else:
            db.add("event", {"x": 1}, ts=100)
    event.remove(db.engine, "commit", fail)
    assert db.persistence_snapshot()[kind + "_absent"] == 1
    if kind == "identity":
        assert db.reserve_event("one", 100)
        assert not db.reserve_event("one", 100)
    else:
        assert not db.rows("event")
        assert db.add("event", {"x": 1}, ts=100)
        assert len(db.rows("event")) == 1
    db.engine.dispose()


@pytest.mark.parametrize("kind", ["identity", "event"])
def test_real_commit_response_failure_verified_after_scope_close(tmp_path, monkeypatch, kind):
    db = database(tmp_path / "response.db")
    original = db.engine.dialect.do_commit

    def fail_after(connection):
        original(connection)
        raise OSError("response lost AFTER actual commit")

    monkeypatch.setattr(db.engine.dialect, "do_commit", fail_after)
    if kind == "identity":
        assert db.reserve_event("one", 100)
    else:
        assert db.add("event", {"x": 1}, "mint", "synthetic", 100)
    assert db.persistence_snapshot()[kind + "_verified"] == 1
    monkeypatch.setattr(db.engine.dialect, "do_commit", original)
    if kind == "identity":
        assert not db.reserve_event("one", 100)
    else:
        assert len(db.rows("event")) == 1
    db.engine.dispose()


@pytest.mark.parametrize(
    "field,value",
    [("kind", "foreign"), ("mint", "foreign"), ("session", "foreign"), ("ts", 999), ("payload", "{}")],
)
def test_mismatched_raw_proof_never_acknowledges(tmp_path, monkeypatch, field, value):
    path = tmp_path / "mismatch.db"
    db = database(path)
    original = db.engine.dialect.do_commit

    def fail_after(connection):
        original(connection)
        with closing(sqlite3.connect(path)) as writer:
            writer.execute(f"UPDATE records SET {field}=? WHERE id=1", (value,))
            writer.commit()
        raise OSError("response lost")

    monkeypatch.setattr(db.engine.dialect, "do_commit", fail_after)
    with pytest.raises(OSError):
        db.add("event", {"x": 1}, "mint", "synthetic", 100)
    assert db.persistence_snapshot()["event_uncertain"] == 1
    db.engine.dispose()


def test_unreadable_proof_preserves_original_exception_and_uncertainty(tmp_path, monkeypatch):
    db = database(tmp_path / "unreadable.db")
    original_commit, connect = db.engine.dialect.do_commit, db.engine.connect

    def fail_connect(*args, **kwargs):
        raise RuntimeError("proof unavailable")

    def fail_after(connection):
        original_commit(connection)
        monkeypatch.setattr(db.engine, "connect", fail_connect)
        raise OSError("original response lost")

    monkeypatch.setattr(db.engine.dialect, "do_commit", fail_after)
    with pytest.raises(OSError, match="original response lost"):
        db.add("event", {"x": 1}, ts=100)
    assert db.persistence_snapshot()["event_uncertain"] == 1
    monkeypatch.setattr(db.engine, "connect", connect)
    monkeypatch.setattr(db.engine.dialect, "do_commit", original_commit)
    assert len(db.rows("event")) == 1
    db.engine.dispose()


def test_busy_retry_and_storage_censorship_preserve_negative_evidence(tmp_path, monkeypatch):
    path = tmp_path / "busy.db"
    db = database(path)
    db.add("outcome", {"status": "UNAVAILABLE_GAP", "net_return_pct": -100})
    with db.engine.connect() as conn:
        conn.exec_driver_sql("PRAGMA busy_timeout=10")
    lock = sqlite3.connect(path)
    lock.execute("BEGIN IMMEDIATE")
    try:
        with pytest.raises(OperationalError):
            db.reserve_event("one", 100)
    finally:
        lock.rollback()
        lock.close()
    assert db.reserve_event("one", 100)
    writable = db.writable
    monkeypatch.setattr(
        db, "writable", lambda raw=False, connection=None: False if raw else writable(connection=connection)
    )
    assert db.add("event", {"x": 1}, ts=100) == 0
    assert db.storage_audit["raw_omitted"] == 1
    assert db.rows("outcome")[0]["net_return_pct"] == -100
    assert db.rows("outcome")[0]["status"] == "UNAVAILABLE_GAP"
    db.engine.dispose()


@pytest.mark.parametrize("stage", ["identity_only", "before_raw_commit", "after_raw_commit"])
def test_sigkill_and_cold_restart_prove_both_original_boundaries(tmp_path, stage):
    path = tmp_path / "killed.db"
    db = database(path)
    db.engine.dispose()
    code = """
import os,signal,sys
from pathlib import Path
from backend.app.db import Database
from sqlalchemy import event
x=Database(Path(sys.argv[1]));x.configure_budget(16)
assert x.reserve_event('one',100)
if sys.argv[2]=='identity_only':os.kill(os.getpid(),signal.SIGKILL)
if sys.argv[2]=='before_raw_commit':
 def die(conn):os.kill(os.getpid(),signal.SIGKILL)
 event.listen(x.engine,'commit',die)
else:
 original=x.engine.dialect.do_commit
 def die(conn):
  original(conn)
  os.kill(os.getpid(),signal.SIGKILL)
 x.engine.dialect.do_commit=die
x.add('event',{'negative':'UNAVAILABLE'},'synthetic','synthetic',100)
"""
    child = subprocess.run([sys.executable, "-c", code, str(path), stage], timeout=15)
    assert child.returncode == -signal.SIGKILL
    reopened = Database(path)
    reopened.configure_budget(16)
    assert not reopened.reserve_event("one", 100)
    assert len(reopened.rows("event")) == (1 if stage == "after_raw_commit" else 0)
    with reopened.engine.connect() as conn:
        assert conn.exec_driver_sql("PRAGMA integrity_check").scalar() == "ok"
    reopened.engine.dispose()


@pytest.mark.parametrize("after_commit", [False, True])
async def test_engine_dispositions_gap_and_durable_receipt(tmp_path, monkeypatch, after_commit):
    from backend.app.engine import RadarEngine
    from backend.app.config import Settings
    from backend.app.domain import MarketEvent
    from backend.app.db import EvidenceRun

    e = RadarEngine(Settings(mode="OBSERVE"), tmp_path / "ledger.db", offline=True)
    now = time.time()
    e.process(
        MarketEvent(mint="synthetic", source="SYNTHETIC", kind="create", event_id="create", ts=now), now
    )
    active = {"raw": False, "done": False}

    def mark(conn, cursor, sql, params, *args):
        if sql.startswith("INSERT INTO records") and params[0] == "event":
            active["raw"] = True

    event.listen(e.db.engine, "before_cursor_execute", mark)
    original = e.db.engine.dialect.do_commit

    def commit(conn):
        if active["raw"] and not active["done"]:
            active["done"] = True
            if after_commit:
                original(conn)
            raise OSError("raw commit response")
        return original(conn)

    monkeypatch.setattr(e.db.engine.dialect, "do_commit", commit)
    trade = MarketEvent(
        mint="synthetic",
        source="Solana WSS",
        kind="trade",
        event_id="trade",
        ts=time.time(),
        side="sell",
        currency="SOL",
        volume=0.1,
    )
    assert e.submit(trade)
    await e.drain_events()
    ledger = e.accounting.snapshot(e.queue)["events"]["trade"]
    assert ledger["terminal"] == {"processed" if after_commit else "exception": 1}
    assert ledger["persisted"] == (1 if after_commit else 0) and ledger["reconciled"]
    assert e.trade_continuity["per_token_resets"] == (0 if after_commit else 1)
    monkeypatch.setattr(e.db.engine.dialect, "do_commit", original)
    event.remove(e.db.engine, "before_cursor_execute", mark)
    assert e.submit(trade)
    await e.drain_events()
    ledger = e.accounting.snapshot(e.queue)["events"]["trade"]
    assert ledger["terminal"]["duplicate_memory"] == 1
    assert ledger["persisted"] == (1 if after_commit else 0) and ledger["reconciled"]
    await e.stop()
    with e.db.sessions() as sql:
        receipt = json.loads(sql.get(EvidenceRun, e.session).payload)
    assert receipt["persistence_reconciliation"]["event_verified" if after_commit else "event_absent"] == 1
    assert e.tokens["synthetic"].features["180"]["trade_evidence"] != "CURRENT"
    e.db.engine.dispose()


async def test_legacy_session_writer_has_identical_features_rankings_and_decisions(tmp_path, monkeypatch):
    from backend.app.engine import RadarEngine
    from backend.app.config import Settings
    from backend.app.demo import demo_events
    from backend.app.db import IDENTITY_INSERT, RAW_EVENT_INSERT

    current = RadarEngine(Settings(mode="DEMO"), tmp_path / "current.db", offline=True)
    old = RadarEngine(Settings(mode="DEMO"), tmp_path / "legacy.db", offline=True)
    financial_add = old.db.add

    # Exact pre-change7a265da identity/raw Session semantics, actual SQLite (not mocks).
    def reserve(identity, ts):
        with old.db.sessions.begin() as sql:
            old.db.writable(connection=sql.connection())
            return sql.execute(IDENTITY_INSERT, dict(event_id=identity, ts=ts)).rowcount == 1

    def add(kind, payload, mint="", session="", ts=None):
        if kind != "event":
            return financial_add(kind, payload, mint, session, ts)
        with old.db.sessions.begin() as sql:
            assert old.db.writable(raw=True, connection=sql.connection())
            encoded = json.dumps(payload, separators=(",", ":"), allow_nan=False)
            assert len(encoded.encode()) <= min(1048576, int(old.db.budget * 0.01))
            result = sql.connection().execute(
                RAW_EVENT_INSERT, dict(kind=kind, mint=mint, session=session, ts=ts, payload=encoded)
            )
            identity = result.inserted_primary_key[0]
        return identity

    monkeypatch.setattr(old.db, "reserve_event", reserve)
    monkeypatch.setattr(old.db, "add", add)
    try:
        for tick in range(12):
            for observation in demo_events(1000, tick):
                assert old.process(observation.model_copy(deep=True)) == current.process(
                    observation.model_copy(deep=True)
                )
                assert list(sorted(old.tokens, key=lambda m: old.tokens[m].priority())) == list(
                    sorted(current.tokens, key=lambda m: current.tokens[m].priority())
                )
                for mint, expected in old.tokens.items():
                    actual = current.tokens[mint]
                    assert (
                        actual.features,
                        actual.scores,
                        actual.decision,
                        actual.state,
                        actual.priority(),
                    ) == (
                        expected.features,
                        expected.scores,
                        expected.decision,
                        expected.state,
                        expected.priority(),
                    )
        assert old.paper.state["cash"] == current.paper.state["cash"] == 20
        assert len(old.db.rows("event", limit=10000)) == len(current.db.rows("event", limit=10000))
    finally:
        await old.stop()
        await current.stop()
