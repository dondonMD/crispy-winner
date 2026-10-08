import pytest
from alembic import command
from alembic.config import Config
from backend.app.config import ROOT, Settings
from backend.app.db import Database


def test_risk_config():
    with pytest.raises(ValueError):
        Settings(max_position_fraction=1)
    with pytest.raises(ValueError):
        Settings(max_deep=30, max_candidates=10)


def test_migration_retention_restart(tmp_path):
    db = Database(tmp_path / "test.db")
    cfg = Config(str(ROOT / "backend/alembic.ini"))
    with db.engine.begin() as connection:
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, "head")
    for kind in ["event", "snapshot", "paper_trade", "paper_account", "strategy", "evaluation"]:
        db.add(kind, {"value": 20}, ts=0)
    assert db.retention(Settings(), now=100000000) == 2
    restarted = Database(tmp_path / "test.db")
    assert restarted.rows("paper_account")[0]["value"] == 20
    assert restarted.rows("strategy")
    with db.engine.connect() as conn:
        assert conn.exec_driver_sql("PRAGMA journal_mode").scalar() == "wal"
