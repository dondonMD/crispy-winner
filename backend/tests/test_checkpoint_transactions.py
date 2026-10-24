"""Bounded persistence units, never synthetic prospective evidence."""

import json
import signal
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import event
from sqlalchemy.exc import OperationalError

from backend.app.db import Base, Database, EvidenceRun, StorageBudgetError
from backend.app.config import Settings
from backend.app.opportunity import load_intelligence_settings
from backend.app.opportunity_research import OpportunityResearch


def database(path, mb=16):
    db = Database(path)
    Base.metadata.create_all(db.engine)
    db.configure_budget(mb)
    return db


def records(n=25):
    return [
        (
            "snapshot",
            dict(
                created=1,
                state="WATCHING",
                name="SYNTHETIC",
                symbol="S",
                creator="",
                graduation=None,
                scores={},
                i=i,
            ),
            f"synthetic:{i}",
        )
        for i in range(n)
    ]


def receipt(db, session="synthetic"):
    with db.sessions() as sql:
        row = sql.get(EvidenceRun, "cp:" + session)
        return json.loads(row.payload) if row else None


def test_bounded_commit_ack_and_idempotent_retry(tmp_path):
    db = database(tmp_path / "unit.db")
    commits = []
    event.listen(db.engine, "commit", lambda conn: commits.append(1))
    ids = db.checkpoint_records(records(), "synthetic", 100)
    assert len(commits) == 3 and len(ids) == 25
    assert receipt(db)["complete"] and receipt(db)["row_ids"] == ids
    assert db.checkpoint_records(records(), "synthetic", 100) == ids
    assert len(db.rows("snapshot")) == 25
    changed = records()
    changed[0][1]["i"] = -1
    with pytest.raises(ValueError, match="changed frozen"):
        db.checkpoint_records(changed, "synthetic", 100)
    db.engine.dispose()


def test_partial_failure_rolls_back_group_and_retry_preserves_negative_evidence(tmp_path):
    db = database(tmp_path / "rollback.db")
    db.add("outcome", dict(status="MEASURED", net_return_pct=-100))
    db.add("outcome", dict(status="UNAVAILABLE_PROVIDER_GAP"))

    def fail(conn, cursor, statement, *args):
        if statement.startswith("UPDATE evidence_runs"):
            raise OSError("Injected checkpoint receipt failure")

    event.listen(db.engine, "before_cursor_execute", fail)
    with pytest.raises(OSError):
        db.checkpoint_records(records(), "synthetic", 100)
    assert len(db.rows("snapshot")) == 10
    assert receipt(db)["complete"] is False and len(receipt(db)["row_ids"]) == 10
    event.remove(db.engine, "before_cursor_execute", fail)
    assert len(db.checkpoint_records(records(), "synthetic", 100)) == 25
    assert len(db.rows("snapshot")) == 25
    assert db.rows("outcome")[0]["net_return_pct"] == -100
    assert db.rows("outcome")[1]["status"] == "UNAVAILABLE_PROVIDER_GAP"
    db.engine.dispose()


def test_busy_claim_fails_without_ack_then_can_retry(tmp_path):
    db = database(tmp_path / "busy.db")
    # Test-only bounded wait. Production busy_timeout remains 5000ms.
    with db.engine.connect() as sql:
        sql.exec_driver_sql("PRAGMA busy_timeout=1")
    blocker = sqlite3.connect(db.path)
    blocker.execute("BEGIN IMMEDIATE")
    try:
        with pytest.raises(OperationalError, match="locked"):
            db.checkpoint_records(records(), "synthetic", 100)
        assert not db.rows("snapshot") and receipt(db) is None
    finally:
        blocker.rollback()
        blocker.close()
    assert len(db.checkpoint_records(records(), "synthetic", 100)) == 25
    db.engine.dispose()


def test_parallel_retry_claims_prevent_duplicate_rows(tmp_path):
    path = tmp_path / "parallel.db"
    db = database(path)
    other = Database(path)
    other.configure_budget(16)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda d: d.checkpoint_records(records(), "synthetic", 100), [db, other]))
    assert results[0] == results[1] and len(db.rows("snapshot")) == 25
    other.engine.dispose()
    db.engine.dispose()


def test_checkpoint_guard_and_pinned_wal_remain_bounded(tmp_path):
    db = database(tmp_path / "guard.db", mb=1)
    db.add("outcome", dict(net_return_pct=-100))
    reader = sqlite3.connect(db.path)
    reader.execute("BEGIN")
    reader.execute("SELECT count(*) FROM records").fetchone()
    data = [("snapshot", {"synthetic": True, "body": "x" * 4000}, f"m{i}") for i in range(25)]
    try:
        with pytest.raises(StorageBudgetError):
            for at in range(100):
                db.checkpoint_records(data, "synthetic", at)
        db.evidence_run("synthetic-stop", dict(status="STORAGE_STOP"))
        assert db.size() <= 1048576
        assert db.rows("outcome")[0]["net_return_pct"] == -100
    finally:
        reader.rollback()
        reader.close()
        db.engine.dispose()


def test_unsupported_oversized_and_out_of_order_checkpoint_rejected(tmp_path):
    db = database(tmp_path / "bound.db")
    for data in [[("outcome", {"net_return_pct": -1}, "m")], records(501)]:
        with pytest.raises((ValueError, StorageBudgetError)):
            db.checkpoint_records(data, "synthetic", 100)
    assert not db.rows("snapshot")
    db.checkpoint_records(records(), "synthetic", 100)
    with pytest.raises(ValueError, match="Older"):
        db.checkpoint_records(records(), "synthetic", 99)
    db.engine.dispose()


def test_pending_exact_noop_and_failed_commit_does_not_poison_cache(tmp_path):
    db = database(tmp_path / "pending.db")
    research = OpportunityResearch(db, Settings(mode="OBSERVE"), load_intelligence_settings(), "synthetic")
    payload = dict(mint="synthetic", remaining=[300], value=1)
    research.save_pending(1, payload)

    def fail(conn, cursor, statement, *args):
        if statement.startswith("SELECT opportunity_pending") or statement.startswith(
            "UPDATE opportunity_pending"
        ):
            raise OSError("Injected pending write failure")

    event.listen(db.engine, "before_cursor_execute", fail)
    research.save_pending(1, dict(payload))  # Byte-identical committed state: no SQL at all.
    payload["value"] = 2
    with pytest.raises(OSError):
        research.save_pending(1, payload)
    assert json.loads(research.committed_pending[1])["value"] == 1
    event.remove(db.engine, "before_cursor_execute", fail)
    research.save_pending(1, payload)
    assert json.loads(research.committed_pending[1])["value"] == 2
    research.save_pending(1, None)
    assert 1 not in research.committed_pending
    research.LIMIT = 3  # Test cache eviction only; production limit unchanged.
    for i in range(5):
        research.save_pending(i, dict(payload))
    assert len(research.committed_pending) == 3
    db.engine.dispose()


def test_killed_transaction_keeps_committed_prefix_and_retry_is_exact(tmp_path):
    path = tmp_path / "killed.db"
    db = database(path)
    db.engine.dispose()
    code = """
import os,signal,sys
from sqlalchemy import event
from backend.app.db import Database
from backend.tests.test_checkpoint_transactions import records
x=Database(__import__('pathlib').Path(sys.argv[1]));x.configure_budget(16)
n=[0]
def die(conn,cursor,statement,*args):
 if statement.startswith('INSERT INTO records'):
  n[0]+=1
  if n[0]==11: os.kill(os.getpid(),signal.SIGKILL)
event.listen(x.engine,'before_cursor_execute',die)
x.checkpoint_records(records(),'synthetic',100)
"""
    process = subprocess.run([sys.executable, "-c", code, str(path)], timeout=15)
    assert process.returncode == -signal.SIGKILL
    reopened = Database(path)
    reopened.configure_budget(16)
    assert len(reopened.rows("snapshot")) == 10 and not receipt(reopened)["complete"]
    assert len(reopened.checkpoint_records(records(), "synthetic", 100)) == 25
    assert len(reopened.rows("snapshot")) == 25
    with reopened.engine.connect() as sql:
        assert sql.exec_driver_sql("PRAGMA integrity_check").scalar() == "ok"
    reopened.engine.dispose()


def test_commit_failure_cannot_acknowledge_uncommitted_prefix(tmp_path):
    db = database(tmp_path / "commit.db")
    attempts = []

    def fail_commit(conn):
        attempts.append(1)
        if len(attempts) == 2:
            raise OSError("Injected commit failure")

    event.listen(db.engine, "commit", fail_commit)
    with pytest.raises(OSError, match="commit failure"):
        db.checkpoint_records(records(), "synthetic", 100)
    assert len(db.rows("snapshot")) == 10
    assert len(receipt(db)["row_ids"]) == 10 and not receipt(db)["complete"]
    event.remove(db.engine, "commit", fail_commit)
    assert len(db.checkpoint_records(records(), "synthetic", 100)) == 25
    db.engine.dispose()


async def test_stop_preserves_terminal_receipt_even_when_checkpoint_fails(tmp_path, monkeypatch):
    import time
    from backend.app.engine import RadarEngine
    from backend.app.domain import MarketEvent

    path = tmp_path / "stop-failure.db"
    e = RadarEngine(Settings(mode="OBSERVE"), path, offline=True)
    for i in range(3):
        e.submit(
            MarketEvent(
                event_id=f"queued:{i}", mint="synthetic", ts=time.time(), source="SYNTHETIC", kind="trade"
            )
        )

    def fail(now):
        raise OSError("Injected checkpoint failure")

    monkeypatch.setattr(e, "checkpoint", fail)
    with pytest.raises(OSError, match="checkpoint failure"):
        await e.stop()
    reopened = Database(path)
    with reopened.sessions() as sql:
        stopped = json.loads(sql.get(EvidenceRun, e.session).payload)
    assert stopped["checkpoint_complete"] is False and stopped["checkpoint_failure"] == "OSError"
    assert stopped["accounting"]["events"]["trade"]["terminal"] == {"shutdown_unprocessed": 3}
    assert stopped["accounting"]["events"]["trade"]["reconciled"]
    reopened.engine.dispose()
