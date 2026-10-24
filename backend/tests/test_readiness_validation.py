"""Controlled synthetic validation only. Never uses historical or live research DBs."""
import asyncio
from copy import deepcopy
import json
import sqlite3
import time

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


def test_reader_pinned_wal_cannot_bypass_physical_budget(tmp_path):
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
