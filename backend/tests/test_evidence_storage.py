"""Synthetic bounded storage pressure: never opens the research database."""
import json

import pytest

from backend.app.db import Base, Database, EvidenceRun, StorageBudgetError


def database(path, mb=8):
    db = Database(path)
    Base.metadata.create_all(db.engine)
    db.configure_budget(mb)
    return db


def test_context_is_lossless_reused_and_corruption_fails_closed(tmp_path):
    db = database(tmp_path / "context.db")
    context = {"degraded": {str(i): True for i in range(250)}}
    ref = db.context_reference(context)
    assert db.context_reference(context) == ref
    assert db.resolve_context(ref) == context
    assert len(json.dumps(ref)) < 100 < len(json.dumps(context))
    with pytest.raises(ValueError):
        db.resolve_context({"reference": "missing"})
    assert db.resolve_context(context) == context
    db.engine.dispose()


def test_sustained_raw_writes_reclaim_only_expendable_data_and_record_censorship(tmp_path):
    path = tmp_path / "bounded.db"
    db = database(path)
    db.add("outcome", {"status": "MEASURED", "net_return_pct": -100})
    db.add("strategy", {"version": "synthetic"})
    db.add("paper_account", {"cash": 20})
    for i in range(1000):
        db.add("event", {"index": i, "synthetic": "x" * 16000}, ts=i + 1)
    assert db.storage_audit["raw_omitted"] > 0
    assert db.storage_audit["raw_reclaimed"] > 0
    assert db.size() < 8 * 1048576
    assert db.rows("outcome")[0]["net_return_pct"] == -100
    assert db.rows("paper_account") and db.rows("strategy")
    before = dict(db.storage_audit)
    # Dispose without a clean engine/session receipt simulates interruption.
    db.engine.dispose()
    reopened = database(path)
    assert reopened.storage_audit == before
    with reopened.sessions() as sql:
        assert sql.get(EvidenceRun, "storage")
    reopened.engine.dispose()


def test_essential_records_are_never_deleted_to_make_room(tmp_path):
    db = database(tmp_path / "protected.db", 4)
    written = 0
    with pytest.raises(StorageBudgetError):
        for _ in range(1000):
            db.add("outcome", {"status": "UNAVAILABLE_GAP", "synthetic": "x" * 16000})
            written += 1
    assert len(db.rows("outcome", limit=1000)) == written
    db.evidence_run("synthetic", {"status": "STORAGE_STOP"})
    assert db.size() < 4 * 1048576
    db.engine.dispose()


def test_raw_replay_cannot_claim_complete_after_censorship(tmp_path):
    from backend.app.evaluation import replay

    db = database(tmp_path / "censored.db")
    db._raw_pressure(123)
    with pytest.raises(ValueError, match="storage-censored"):
        replay(db, "synthetic")
    db.engine.dispose()
