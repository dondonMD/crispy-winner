"""Controlled synthetic validation only. Never uses historical or live research DBs."""
import asyncio
from copy import deepcopy
import json
import sqlite3
import time
import subprocess
import sys

import httpx
import pytest
from sqlalchemy import event as sql_event

from backend.app.config import Settings
from backend.app.db import Base, Database, EvidenceRun, StorageBudgetError
from backend.app.domain import MarketEvent
from backend.app.engine import RadarEngine


def synthetic_db(path, mb=8):
    db = Database(path)
    Base.metadata.create_all(db.engine)
    db.configure_budget(mb)
    return db


def test_reader_pinned_wal_cannot_bypass_physical_budget(tmp_path, record_property):
    db = synthetic_db(tmp_path / "pinned.db")
    db.add("outcome", {"status": "MEASURED", "net_return_pct": -100})
    reader = sqlite3.connect(db.path)
    reader.execute("BEGIN")
    reader.execute("SELECT count(*) FROM records").fetchone()
    peak = 0
    try:
        with pytest.raises(StorageBudgetError, match="Physical"):
            for i in range(1500):
                db.add("event", {"synthetic": True, "i": i, "body": "x" * 16000})
                peak = max(peak, db.size())
                assert peak <= 8 * 1048576
        db.evidence_run("synthetic", {"status": "STORAGE_STOP"})
        assert db.size() <= 8 * 1048576
        assert db.rows("outcome")[0]["net_return_pct"] == -100
        record_property("peak_allocated_bytes", max(peak, db.size()))
        record_property("budget_bytes", 8 * 1048576)
    finally:
        reader.rollback()
        reader.close()
        db.engine.dispose()


def test_failed_reclamation_rolls_back_both_rows_and_in_memory_receipt(tmp_path):
    db = synthetic_db(tmp_path / "rollback.db")
    db.add("event", {"synthetic": True})
    before = deepcopy(db.storage_audit)

    def fail(conn, cursor, statement, *args):
        if statement.startswith("INSERT INTO evidence_runs"):
            raise OSError("Synthetic failed receipt write")

    sql_event.listen(db.engine, "before_cursor_execute", fail)
    with pytest.raises(OSError):
        db._raw_pressure(123)
    sql_event.remove(db.engine, "before_cursor_execute", fail)
    assert db.storage_audit == before
    assert len(db.rows("event")) == 1
    db.engine.dispose()


async def test_shutdown_has_durable_terminal_queue_and_recovery_accounting(tmp_path):
    e = RadarEngine(Settings(mode="OBSERVE"), tmp_path / "shutdown.db", offline=True)
    entered = asyncio.Event()
    never = asyncio.Event()

    async def delayed(request):
        entered.set()
        await never.wait()
        return httpx.Response(200, json={"result": None})

    await e.rpc.client.aclose()
    e.rpc.client = httpx.AsyncClient(transport=httpx.MockTransport(delayed))
    for i in range(27):
        e.submit(MarketEvent(event_id=f"synthetic:{i}", mint="synthetic", ts=time.time(),
                            source="Solana WSS", kind="trade"))
    e.recovery.submit("synthetic-signature", 1, time.time())
    e.tasks = [asyncio.create_task(e.recovery.run())]
    await asyncio.wait_for(entered.wait(), 2)
    await e.stop()
    db = Database(tmp_path / "shutdown.db")
    with db.sessions() as sql:
        row = json.loads(sql.get(EvidenceRun, e.session).payload)
    trade = row["accounting"]["events"]["trade"]
    assert trade["pending"] == trade["in_processing"] == 0
    assert trade["terminal"] == {"shutdown_unprocessed": 27} and trade["reconciled"]
    recovery = row["recovery"]
    assert recovery["accepted"] == recovery["shutdown_unresolved"] == 1
    assert recovery["completed"] == recovery["pending"] == recovery["in_flight"] == 0
    assert recovery["accepted_reconciled"] and recovery["coverage_state"] == "STOPPED INCOMPLETE"
    assert not e.recovery.claimed and not e.onchain.health["connected"]
    db.engine.dispose()


async def test_observer_batch_reuses_exact_ranking_without_changing_selection(tmp_path):
    from types import SimpleNamespace
    from backend.app.early_edge_runtime import attach_observer

    e = RadarEngine(Settings(mode="OBSERVE"), tmp_path / "ranking.db", offline=False)
    for i in range(30):
        e.process(MarketEvent(event_id=str(i), mint=f"synthetic:{i}", ts=time.time(),
                             source="SYNTHETIC", kind="create"))
    expected = set(e.deep_mints())
    ranked = e.deep_mints
    calls = []

    def counted():
        calls.append(1)
        return ranked()

    e.deep_mints = counted
    observed = {}
    observer = SimpleNamespace(clock=time.time, settings=e.settings, failed=False)
    observer.observe = lambda token, view, now: observed.update({token.mint: observer.tier(token.mint)})
    detach = attach_observer(e, observer)
    e.intelligence.refresh(time.time(), force=True)
    assert len(calls) == 1
    assert {mint for mint, tier in observed.items() if tier == "hot"} == expected
    assert set(e.deep_mints()) == expected
    observer.tier("synthetic:0")  # Outside the batch the current ranking is read again.
    assert len(calls) == 3
    detach()
    await e.stop()


def test_small_budget_preserves_room_for_bounded_final_receipt(tmp_path, record_property):
    db = synthetic_db(tmp_path / "small.db", 1)
    reader = sqlite3.connect(db.path)
    reader.execute("BEGIN")
    reader.execute("SELECT count(*) FROM records").fetchone()
    try:
        with pytest.raises(StorageBudgetError):
            for _ in range(2000):
                db.add("event", {"synthetic": "x" * 1000})
        db.evidence_run("synthetic", {"status": "STORAGE_STOP", "bounded_fixture": "x" * 62000})
        assert db.size() <= 1048576
        record_property("allocated_after_receipt", db.size())
        record_property("budget_bytes", 1048576)
    finally:
        reader.rollback()
        reader.close()
        db.engine.dispose()


def test_sustained_retention_keeps_protected_evidence_and_contexts(tmp_path, record_property):
    db = synthetic_db(tmp_path / "sustained.db", 16)
    ref = db.context_reference({"synthetic": True, "degraded": {str(i): True for i in range(250)}})
    for value in (-100, 2):
        db.add("outcome", {"status": "MEASURED", "net_return_pct": value, "context": ref})
    db.add("outcome", {"status": "UNAVAILABLE_PROVIDER_GAP"})
    db.add("strategy", {"version": "synthetic"})
    db.add("paper_account", {"cash": 20})
    peak = 0
    for i in range(3000):
        db.reserve_event(str(i), 10000 + i)
        db.add("event", {"synthetic": "x" * 16000, "context_before": ref}, ts=10000 + i)
        peak = max(peak, db.size())
        assert peak <= 16 * 1048576
    assert db.storage_audit["raw_reclaimed"] and db.storage_audit["raw_omitted"]
    record_property("peak_allocated_bytes", peak)
    record_property("budget_bytes", 16 * 1048576)
    record_property("raw_omitted", db.storage_audit["raw_omitted"])
    record_property("raw_reclaimed", db.storage_audit["raw_reclaimed"])
    db.retention(Settings())
    assert not db.rows("event")
    assert len(db.rows("outcome")) == 3
    assert db.rows("strategy") and db.rows("paper_account")
    assert db.resolve_context(ref)["synthetic"] is True
    with db.engine.connect() as conn:
        assert conn.exec_driver_sql("PRAGMA integrity_check").scalar_one() == "ok"
    db.engine.dispose()


def test_process_kill_preserves_committed_audit_and_rolls_back_partial_write(tmp_path):
    path, ready = tmp_path / "crash.db", tmp_path / "ready.json"
    code = '''
import json,sys,time
from pathlib import Path
from backend.app.db import Database,Base,Record
db=Database(Path(sys.argv[1]));Base.metadata.create_all(db.engine);db.configure_budget(8)
for i in range(100): db.add("outcome",dict(status="MEASURED",net_return_pct=-i))
db.evidence_run("synthetic",dict(status="RUNNING",at=time.time()))
sql=db.sessions();sql.begin();sql.add(Record(kind="outcome",mint="",session="",ts=time.time(),payload='{"uncommitted":true}'));sql.flush()
Path(sys.argv[2]).write_text(json.dumps(dict(committed=100,uncommitted=1)))
while True: time.sleep(1)
'''
    child = subprocess.Popen([sys.executable, "-c", code, str(path), str(ready)])
    try:
        deadline = time.monotonic() + 10
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(.01)
        assert ready.exists()
    finally:
        child.kill()
        child.wait(timeout=5)
    db = synthetic_db(path)
    rows = db.rows("outcome")
    assert len(rows) == 100 and all("uncommitted" not in r for r in rows)
    with db.sessions() as sql:
        assert json.loads(sql.get(EvidenceRun, "synthetic").payload)["status"] == "RUNNING"
    with db.engine.connect() as conn:
        assert conn.exec_driver_sql("PRAGMA integrity_check").scalar_one() == "ok"
    db.engine.dispose()


def test_load_driver_counts_detached_work_as_outstanding():
    from types import SimpleNamespace
    from scripts.validate_evidence_load import outstanding

    engine = SimpleNamespace(queue=SimpleNamespace(heap=[], in_processing={"trade": 20}),
                             recovery=SimpleNamespace(pending={}))
    assert outstanding(engine)
    engine.queue.in_processing["trade"] = 0
    assert not outstanding(engine)


@pytest.mark.parametrize("backlog,expected", [(False, .25), (True, 0)])
async def test_consumer_yields_without_idle_sleep_when_work_is_waiting(tmp_path, monkeypatch, backlog, expected):
    e = RadarEngine(Settings(mode="OBSERVE"), tmp_path / "idle.db", offline=True)
    e.last_lab = e.last_maintenance = time.time()
    if backlog:
        e.submit(MarketEvent(event_id="synthetic", mint="synthetic", ts=time.time(), source="SYNTHETIC", kind="create"))

    async def held_drain():
        pass  # Isolate the end-of-cycle scheduling decision; no event is falsely processed.

    sleeps = []

    async def capture_delay(delay):
        sleeps.append(delay)
        raise asyncio.CancelledError()

    monkeypatch.setattr(e, "drain_events", held_drain)
    monkeypatch.setattr("backend.app.engine.asyncio.sleep", capture_delay)
    with pytest.raises(asyncio.CancelledError):
        await e.run_loop()
    assert sleeps == [expected]
    monkeypatch.undo()
    await e.stop()
