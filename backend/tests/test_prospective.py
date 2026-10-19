"""Synthetic, isolated DB fixtures; never enroll these in real prospective research."""
import json
import subprocess
import time
from types import SimpleNamespace

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from backend.app.config import Settings
from backend.app.domain import MarketEvent, State, Token
from backend.app.economics import TradeCostEstimator
from backend.app.evaluation import OutcomeCollector, evaluate
from backend.app.prospective import CohortIntegrityError, ProspectiveCohort, create_cohort, repository_identity as real_repository_identity
from backend.app.prospective_report import report
from scripts.prospective_cohort import database


@pytest.fixture
def cohort(tmp_path, monkeypatch):
    clock = [2_000_000_000.0]
    provenance = ["a" * 40]
    monkeypatch.setattr(time, "time", lambda: clock[0])
    monkeypatch.setattr("backend.app.prospective.repository_identity", lambda: provenance[0])
    db = database(tmp_path / "synthetic.db")
    settings = Settings(mode="OBSERVE")
    manifest = create_cohort(db, settings)
    frozen = ProspectiveCohort(db, settings, manifest["cohort_id"])
    db.record_observer = frozen.on_record
    collector = OutcomeCollector(db, settings, TradeCostEstimator(settings), "synthetic-session")
    collector.prospective = frozen
    clock[0] += 1
    result = SimpleNamespace(db=db, settings=settings, manifest=manifest, frozen=frozen,
                             collector=collector, clock=clock, provenance=provenance)
    yield result
    db.engine.dispose()


def token(c, mint="synthetic-token"):
    t = Token(mint, "SYNTHETIC", "TEST", c.clock[0] - 600)
    t.state = State.POST_GRAD_OBSERVATION
    t.features = {"180": {"trade_evidence": "CURRENT", "units_valid": True, "buy_count": 25}}
    t.scores = {"maturity": 70, "momentum": 80, "chase": 5}
    t.security = {"risk_score": 10}
    t.decision = {"decision": "WAIT", "reasons": ["holdout unavailable"], "research_eligible": True}
    t.price, t.liquidity = 1, 100000
    t.viability = {"proposed_position_usd": 4}
    return t


def enroll(c, t=None):
    return c.collector.signal(t or token(c), c.clock[0], c.manifest["strategy_version"])


def stats(c):
    return report(c.db.path, c.manifest["cohort_id"], c.clock[0])


def test_manifest_frozen_before_and_after_enrollment(cohort):
    c = cohort
    assert c.manifest["git_sha"] == "a" * 40
    assert c.manifest["latency_ms"] == c.settings.latency_ms
    for sql in ["UPDATE prospective_cohorts SET manifest='{}'", "DELETE FROM prospective_cohorts"]:
        with pytest.raises(IntegrityError), c.db.engine.begin() as conn:
            conn.execute(text(sql))
    with pytest.raises(CohortIntegrityError):
        create_cohort(c.db, c.settings)
    enroll(c)
    for table in ("prospective_cohorts", "prospective_enrollments"):
        with pytest.raises(IntegrityError), c.db.engine.begin() as conn:
            conn.execute(text(f"DELETE FROM {table}"))
    changed = c.frozen.manifest
    changed["primary_endpoint"]["horizon_seconds"] = 60
    assert c.frozen.manifest["primary_endpoint"]["horizon_seconds"] == 300


@pytest.mark.parametrize("change", ["git", "settings", "mode", "version"])
def test_drift_refused_atomically(cohort, change):
    c = cohort
    if change == "git":
        c.provenance[0] = "b" * 40
    elif change == "settings":
        c.settings.latency_ms += 1
    elif change == "mode":
        c.settings.mode = "PAPER"
    with pytest.raises(CohortIntegrityError):
        c.collector.signal(token(c), c.clock[0], "wrong" if change == "version" else c.manifest["strategy_version"])
    with c.db.engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM prospective_enrollments")).scalar() == 0
    assert not c.db.rows("signal")


def test_no_historical_or_ineligible_enrollment_and_first_sample_fixed(cohort):
    c = cohort
    t = token(c)
    c.collector.signal(t, c.manifest["created_at"], c.manifest["strategy_version"])
    t.decision["research_eligible"] = False
    enroll(c, t)
    t.decision["research_eligible"] = True
    first = enroll(c, t)
    c.clock[0] += 30
    enroll(c, t)
    r = stats(c)
    assert r["raw_eligible_signals"] == 2
    assert r["unique_token_session_primary_samples"] == 1
    assert r["repeated_signals_excluded_from_primary"] == 1
    with c.db.engine.connect() as conn:
        assert conn.execute(text("SELECT signal_id FROM prospective_enrollments WHERE primary_sample=1")).scalar() == first
    with pytest.raises(CohortIntegrityError):
        c.collector.signal(t, c.manifest["created_at"] + .5, c.manifest["strategy_version"])


def test_snapshot_immutable_no_future_leak_and_primary_is_300(cohort):
    c = cohort
    t = token(c)
    signal = enroll(c, t)
    t.features["180"]["buy_count"] = 999
    t.scores["momentum"] = 1
    t.decision["reasons"].append("future information")
    assert c.collector.pending[signal]["signal"]["scores"]["momentum"] == 80
    with c.db.engine.connect() as conn:
        snapshot = json.loads(conn.execute(text("SELECT snapshot FROM prospective_enrollments")).scalar())
    assert snapshot["features"]["buy_count"] == 25 and len(snapshot["decision"]["reasons"]) == 1
    r = stats(c)
    assert r["primary"]["horizon_seconds"] == 300 and r["primary"]["role"] == "PRIMARY"
    assert all(s["role"] == "SECONDARY_EXPLORATORY" for s in r["secondary_exploratory"])
    assert r["primary"]["status"] == "INSUFFICIENT_SAMPLE"


def test_reuses_collector_after_costs_and_unavailable_denominator(cohort):
    c = cohort
    t = token(c)
    first = enroll(c, t)
    second = enroll(c, token(c, "missing"))
    c.clock[0] += 1
    c.collector.observe(t, MarketEvent(mint=t.mint, kind="market", ts=c.clock[0], event_id=str(c.clock[0]), source="SYNTHETIC", price=1, liquidity=100000))
    c.clock[0] += 299
    c.collector.observe(t, MarketEvent(mint=t.mint, kind="market", ts=c.clock[0], event_id=str(c.clock[0]), source="SYNTHETIC", price=1.1, liquidity=100000))
    old_as_of = c.clock[0] - 1
    c.db.add("outcome", {"signal_id": second, "horizon": 300, "status": "UNAVAILABLE_NO_PRICE"}, ts=c.clock[0])
    r = stats(c)
    original = next(row for row in c.db.rows("outcome") if row.get("signal_id") == first and row.get("horizon") == 300)
    assert original["status"] == "MEASURED" and original["net_return_pct"] < original["gross_return_pct"]
    assert r["primary"]["mean_net_return_pct"] == original["net_return_pct"]
    assert r["primary"]["measured"] == r["primary"]["unavailable"] == 1
    assert r["primary"]["coverage_pct"] == 50
    assert report(c.db.path, c.manifest["cohort_id"], old_as_of)["primary"]["measured"] == 0
    # Retrospective evaluation remains separate and available.
    assert evaluate(c.db, c.settings, version=c.manifest["strategy_version"], now=c.clock[0])["horizon"] == 300


def test_restart_gaps_unfinished_work_and_report_is_deterministic(cohort):
    c = cohort
    enroll(c)
    before = stats(c)
    c.db.engine.dispose()
    restarted = database(c.db.path)
    frozen = ProspectiveCohort(restarted, c.settings, c.manifest["cohort_id"])
    restarted.record_observer = frozen.on_record
    collector = OutcomeCollector(restarted, c.settings, TradeCostEstimator(c.settings), "new-session")
    collector.prospective = frozen
    assert len(frozen.restore_pending()) == 1
    c.clock[0] += 1
    collector.close_prospective()
    assert not frozen.restore_pending()
    assert report(restarted.path, c.manifest["cohort_id"], c.clock[0] - 1) == before
    r = report(restarted.path, c.manifest["cohort_id"], c.clock[0])
    assert r["primary"]["status_counts"]["UNAVAILABLE_GAP"] == 1
    assert r == report(restarted.path, c.manifest["cohort_id"], c.clock[0])
    assert not r["approval_modified"] and not r["live_trading_enabled"]
    restarted.engine.dispose()


def fake_measured(c, signal_id, net):
    # Synthetic statistical fixtures; production values are generated only by OutcomeCollector.
    c.db.add("outcome", {"signal_id": signal_id, "horizon": 300, "status": "MEASURED",
                        "net_return_pct": net, "mfe_pct": 2, "mae_pct": -2}, ts=c.clock[0])


@pytest.mark.parametrize("returns,unavailable,status", [
    ([1] * 5, 0, "INSUFFICIENT_SAMPLE"),
    ([-10, 11] * 50, 0, "NEGATIVE_OR_INCONCLUSIVE"),
    ([1] * 100, 1, "POSITIVE_DESCRIPTIVE"),
    ([1] * 100, 0, "PROSPECTIVE_EVIDENCE_CANDIDATE"),
])
def test_statistical_status_never_unlocks_anything(cohort, returns, unavailable, status):
    c = cohort
    ids = [enroll(c, token(c, f"synthetic-{i}")) for i in range(len(returns) + unavailable)]
    c.clock[0] += 300
    for sid, value in zip(ids, returns):
        fake_measured(c, sid, value)
    for sid in ids[len(returns):]:
        c.db.add("outcome", {"signal_id": sid, "status": "UNAVAILABLE_CAPACITY"})
    r = stats(c)
    assert r["primary"]["status"] == status
    assert not r["approval_modified"] and not r["live_trading_enabled"]
    assert not c.db.rows("evidence") and not c.db.rows("paper_trade")
    assert len(r["warnings"]) >= 9


def test_quality_degraded_sessions_kept_and_retention_does_not_erase_research(cohort):
    c = cohort
    enroll(c)
    quality = {"updated_at": c.clock[0], "providers_connected": {"rpc": False}, "recovery_overflow": 5}
    c.frozen.quality("synthetic-session", quality)
    c.db.retention(c.settings, c.clock[0] + 1000 * 86400)
    r = stats(c)
    assert r["raw_eligible_signals"] == 1
    assert r["session_quality"][0]["quality"]["recovery_overflow"] == 5
    assert r["session_quality"][0]["quality"]["unavailable_provider_samples"] == 1
    assert c.db.rows("signal")  # Protected source identity/provenance survives retention too.


def test_report_command_read_only(cohort):
    c = cohort
    enroll(c)
    before = c.db.path.read_bytes()
    output = subprocess.check_output([".venv/bin/python", "scripts/prospective_report.py", "--db", str(c.db.path),
                                      "--cohort", c.manifest["cohort_id"], "--as-of", str(c.clock[0])], text=True)
    assert json.loads(output)["primary"]["status"] == "INSUFFICIENT_SAMPLE"
    assert before == c.db.path.read_bytes()


def test_immutable_outcome_and_future_horizon_cannot_replace_primary(cohort):
    c = cohort
    sid = enroll(c)
    c.clock[0] += 300
    fake_measured(c, sid, -1)
    fake_measured(c, sid, 100)
    assert stats(c)["primary"]["mean_net_return_pct"] == -1
    with pytest.raises(IntegrityError), c.db.engine.begin() as conn:
        conn.execute(text("UPDATE prospective_outcomes SET horizon=60"))
    with pytest.raises(IntegrityError), c.db.engine.begin() as conn:
        conn.execute(text("UPDATE prospective_cohorts SET manifest='{}'"))


def test_creation_rejects_demo_and_undeclared_horizons(cohort):
    c = cohort
    with pytest.raises(CohortIntegrityError):
        create_cohort(c.db, Settings(mode="DEMO"))
    with pytest.raises(CohortIntegrityError):
        create_cohort(c.db, Settings(horizons=[60, 300]))


def test_persisted_source_outcome_cannot_change_after_retention(cohort):
    c = cohort
    t = token(c)
    sid = enroll(c, t)
    c.clock[0] += 300
    fake_measured(c, sid, 2)
    before = stats(c)
    c.db.retention(c.settings, c.clock[0] + 1000 * 86400)
    assert not c.db.rows("outcome")
    assert stats(c) == before


async def test_engine_binding_and_offline_replay_isolation(cohort, monkeypatch):
    from backend.app.engine import RadarEngine
    c = cohort
    monkeypatch.setenv("RADAR_COHORT", c.manifest["cohort_id"])
    engine = RadarEngine(c.settings, c.db.path, offline=True)
    assert engine.prospective is None
    await engine.stop()
    bound = RadarEngine(c.settings, c.db.path, offline=True, cohort_id=c.manifest["cohort_id"])
    bound.capture_cohort_quality(c.clock[0])
    rows = stats(c)["session_quality"]
    assert rows and rows[0]["quality"]["quality_samples"] == 1
    await bound.stop()


def test_future_signal_refused(cohort):
    c = cohort
    with pytest.raises(CohortIntegrityError):
        c.collector.signal(token(c), c.clock[0] + 10, c.manifest["strategy_version"])
    assert stats(c)["raw_eligible_signals"] == 0


def test_later_measured_signal_cannot_replace_missing_first_primary(cohort):
    c = cohort
    enroll(c)
    c.clock[0] += 30
    later = enroll(c)
    c.clock[0] += 300
    fake_measured(c, later, 100)
    r = stats(c)
    assert r["raw_eligible_signals"] == 2 and r["repeated_signals_excluded_from_primary"] == 1
    assert r["primary"]["measured"] == 0
    assert r["primary"]["unavailable"] == 1
    assert r["primary"]["mean_net_return_pct"] is None


def test_unavailable_costs_and_exit_delay_retained_from_collector(cohort):
    c = cohort
    t = token(c)
    enroll(c, t)
    c.clock[0] += 1
    c.collector.observe(t, MarketEvent(mint=t.mint, kind="market", event_id="entry", source="SYNTHETIC",
                                      ts=c.clock[0], price=1, liquidity=100000))
    c.clock[0] += 299
    c.collector.observe(t, MarketEvent(mint=t.mint, kind="market", event_id="exit", source="SYNTHETIC",
                                      ts=c.clock[0], price=1.1, liquidity=None))
    assert stats(c)["primary"]["status_counts"]["UNAVAILABLE_COSTS"] == 1


def test_dirty_repository_and_cli_drift_check_fail_closed(cohort, monkeypatch):
    c = cohort
    # The real CLI sees the real repository, not the synthetic fixture's SHA.
    result = subprocess.run([".venv/bin/python", "scripts/prospective_cohort.py", "check", "--db", str(c.db.path),
                             "--cohort", c.manifest["cohort_id"]], capture_output=True, text=True)
    assert result.returncode == 1 and "CohortIntegrityError" in result.stderr
    # Independently exercise the real clean-tree gate, without touching source files.
    from unittest.mock import Mock
    monkeypatch.setattr("backend.app.prospective.subprocess.check_output",
                        Mock(side_effect=["a" * 40, " M backend/app/economics.py"]))
    with pytest.raises(CohortIntegrityError):
        real_repository_identity()


def test_research_db_cannot_silently_run_without_cohort(cohort, monkeypatch):
    from backend.app.engine import RadarEngine
    monkeypatch.delenv("RADAR_COHORT", raising=False)
    with pytest.raises(CohortIntegrityError, match="explicit cohort"):
        RadarEngine(cohort.settings, cohort.db.path)


def test_restart_cleans_terminal_work_after_interrupted_pending_cleanup(cohort):
    c = cohort
    sid = enroll(c)
    for horizon in c.settings.horizons:
        c.db.add("outcome", {"signal_id": sid, "horizon": horizon, "status": "UNAVAILABLE_NO_PRICE"})
    # Simulates a crash after terminal ledger commits but before mutable work cleanup.
    assert not c.frozen.restore_pending()
    with c.db.engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM prospective_pending")).scalar() == 0
