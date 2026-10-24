"""Storage decision equivalence; no cached allocation or weaker guard boundary."""
from types import SimpleNamespace

import pytest

from backend.app.db import Base, Database, StorageBudgetError


def legacy_guard(budget, allocated, reusable, raw):
    if not budget:
        return True
    reserve = max(int(budget * .05), 262144)
    if allocated >= budget - reserve:
        raise StorageBudgetError("Physical evidence storage reserve reached")
    if allocated - reusable >= budget * .85:
        if raw:
            return False
        raise StorageBudgetError("Essential evidence storage reserve reached")
    return not raw or allocated - reusable < budget * .70


def outcome(call):
    try:
        return call()
    except StorageBudgetError as exc:
        return str(exc)


def test_exact_legacy_decisions_at_all_budget_boundaries_and_free_page_counts():
    # Include small budgets where the fixed physical reserve overrides logical limits.
    for budget in [0, 262144, 1048576, 16 * 1048576]:
        boundaries = [0, budget * .70, budget * .85, budget - max(int(budget * .05), 262144)]
        allocations = {max(0, int(b) + offset) for b in boundaries for offset in [-1, 0, 1]}
        for allocated in allocations:
            for pages in [0, 1, 64, 4096]:
                for raw in [False, True]:
                    calls = []
                    connection = SimpleNamespace(exec_driver_sql=lambda sql: (
                        calls.append(sql) or SimpleNamespace(scalar_one=lambda: pages)))
                    db = SimpleNamespace(budget=budget, page_size=4096, size=lambda: allocated)
                    actual = outcome(lambda: Database.writable(db, raw, connection))
                    expected = outcome(lambda: legacy_guard(budget, allocated, pages * 4096, raw))
                    assert actual == expected, (budget, allocated, pages, raw)
                    if calls:
                        assert calls == ["PRAGMA freelist_count"]
                        assert allocated >= budget * (.70 if raw else .85)


def test_rechecks_live_allocation_and_queries_near_threshold_without_caching():
    allocations = iter([100, 7500000, 100, 8500000, 9500000])
    calls = []
    connection = SimpleNamespace(exec_driver_sql=lambda sql: (
        calls.append(sql) or SimpleNamespace(scalar_one=lambda: 0)))
    db = SimpleNamespace(budget=10000000, page_size=4096, size=lambda: next(allocations))
    assert Database.writable(db, True, connection)
    assert Database.writable(db, True, connection) is False
    assert Database.writable(db, True, connection)
    with pytest.raises(StorageBudgetError, match="Essential"):
        Database.writable(db, False, connection)
    with pytest.raises(StorageBudgetError, match="Physical"):
        Database.writable(db, True, connection)
    assert len(calls) == 2


@pytest.mark.parametrize("name", ["state.db", "state[ab].db"])
def test_same_file_set_as_legacy_glob_with_sidecars_symlinks_and_directories(tmp_path, name):
    db = Database(tmp_path / name)
    for filename, size in [(name, 11), ("statea.db", 12), ("stateb.db", 14),
                           (name + "-wal", 13), (name + "-shm", 17),
                           (name + "-journal", 19), (name + ".bak", 23), ("unrelated", 29)]:
        (tmp_path / filename).write_bytes(b"x" * size)
    (tmp_path / (name + "-dir")).mkdir()
    (tmp_path / (name + "-link")).symlink_to(tmp_path / "unrelated")
    (tmp_path / (name + "-broken")).symlink_to(tmp_path / "missing")
    def expected():
        return sum(p.stat().st_size for p in tmp_path.glob(name + "*") if p.is_file())
    assert db.size() == expected()
    (tmp_path / (name + "-wal")).write_bytes(b"x" * 101)
    assert db.size() == expected()  # A second observation never uses stale allocation.
    db.engine.dispose()


def test_allocation_failure_still_fails_closed(tmp_path, monkeypatch):
    db = Database(tmp_path / "blocked.db")
    Base.metadata.create_all(db.engine)
    db.configure_budget(16)

    def unavailable(*args):
        raise PermissionError("Synthetic unavailable directory metadata")

    monkeypatch.setattr("backend.app.db.os.scandir", unavailable)
    with pytest.raises(PermissionError):
        db.reserve_event("synthetic", 100)
    monkeypatch.undo()
    assert db.reserve_event("synthetic", 100)  # Failed write did not reserve identity.
    db.engine.dispose()
