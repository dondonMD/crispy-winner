"""Counterexamples for rejected consolidation designs, not production alternatives."""

import pytest
from sqlalchemy.exc import OperationalError

from backend.app.db import Base, Database, IDENTITY_INSERT


def database(path):
    db = Database(path)
    Base.metadata.create_all(db.engine)
    db.configure_budget(16)
    return db


def test_held_identity_transaction_blocks_existing_independent_observer_writer(tmp_path):
    db = database(tmp_path / "independent.db")
    # Two pooled connections; test-only timeout, production remains5000ms.
    with db.engine.connect() as a, db.engine.connect() as b:
        a.exec_driver_sql("PRAGMA busy_timeout=10")
        b.exec_driver_sql("PRAGMA busy_timeout=10")
    with pytest.raises(OperationalError):
        with db.engine.begin() as outer:
            outer.execute(IDENTITY_INSERT, {"event_id": "synthetic", "ts": 100})
            # Real existing signal/outcome writer uses its own Session, not outer.
            db.add(
                "outcome",
                {"status": "UNAVAILABLE_GAP", "net_return_pct": None},
                "synthetic",
                "synthetic",
                100,
            )
    assert not db.rows("outcome")
    assert db.reserve_event("synthetic", 100)  # Outer reservation rolled back.
    db.engine.dispose()


@pytest.mark.parametrize("reserve_first", [True, False])
def test_restart_counterexample_for_moving_identity_after_side_effects(tmp_path, reserve_first):
    path = tmp_path / "late-reservation.db"
    db = database(path)
    evidence = {"signal_id": 1, "horizon": 300, "status": "MEASURED", "net_return_pct": -12}
    if reserve_first:
        assert db.reserve_event("synthetic", 100)
    db.add("outcome", evidence, "synthetic", "synthetic", 100)
    # Interrupt before raw insertion/late reservation. Only committed state survives.
    db.engine.dispose()
    restored = Database(path)
    restored.configure_budget(16)
    admitted = restored.reserve_event("synthetic", 100)
    if admitted:
        restored.add("outcome", evidence, "synthetic", "synthetic", 100)
    rows = restored.rows("outcome")
    assert len(rows) == (1 if reserve_first else 2)
    assert all(r["net_return_pct"] == -12 for r in rows)
    assert not restored.rows("event")
    # Late reservation would duplicate a negative side effect, not recover it.
    restored.engine.dispose()
