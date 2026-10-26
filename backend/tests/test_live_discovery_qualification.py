"""Offline synthetic operational qualification tests; never start providers."""

from copy import deepcopy
import json
import time
from types import SimpleNamespace as NS

import pytest

from scripts import qualify_live_discovery as q
from scripts import signal_quality_pilot as p


def inputs():
    from backend.app.discovery import OnchainPumpDiscovery

    health = p.discovery_snapshot(OnchainPumpDiscovery(lambda e: None, url="").health)
    health["messages"] = 20
    health["launch_events"] = 1
    return dict(
        reason="SCHEDULED_COMPLETION",
        discovery=health,
        counts={"live_persisted_on_return": 1, "transitions": 1},
        admitted=1,
        audit={
            "sqlite_ok": True,
            "cohort_count": 0,
            "durable_live_create_records": 1,
            "durable_live_create_mints": 1,
            "queue_losses": {"trade": 0, "critical": 0},
            "shutdown": {
                "status": "STOPPED",
                "checkpoint_complete": True,
                "v21_prices": {
                    "acquisition_diagnostics": {
                        "reserve_rejections": {
                            "reconciled": True,
                            "snapshot_available": True,
                            "calculation_failures": 0,
                            "aggregation_failures": 0,
                            "invalid_updates": 0,
                            "telemetry_integrity_failed": False,
                        }
                    }
                },
                "accounting": {
                    "events": {
                        "create": {
                            "in_processing": 0,
                            "pending": 0,
                            "reconciled": True,
                            "persisted": 1,
                            "terminal": {"processed": 1},
                        }
                    }
                },
            },
        },
        source_ok=True,
        trace_ok=True,
        pending_tasks=0,
    )


def test_plan_separate_and_long_protocol_unchanged():
    assert q.plan()["duration_seconds"] == 120
    assert not q.plan()["outcome_measurements"]
    assert q.plan()["PRE_COHORT_READY"] == "NO"
    assert (p.TOTAL, p.CAPTURE) == (1200, 880)
    assert q.verdict(**inputs())["status"] == "PASS"


@pytest.mark.parametrize(
    "failure",
    [
        "source",
        "ledger",
        "sqlite",
        "shutdown",
        "cohort",
        "pending",
        "stranded",
        "reconciliation",
        "loss",
        "processing",
        "histogram",
        "persistence",
        "admission",
        "transition",
        "cancelled",
        "noncanonical",
    ],
)
def test_fail_closed_acceptance(failure):
    d = inputs()
    row = d["audit"]["shutdown"]["accounting"]["events"]["create"]
    if failure == "source":
        d["source_ok"] = False
    elif failure == "ledger":
        d["trace_ok"] = False
    elif failure == "sqlite":
        d["audit"]["sqlite_ok"] = False
    elif failure == "shutdown":
        d["audit"]["shutdown"]["checkpoint_complete"] = False
    elif failure == "cohort":
        d["audit"]["cohort_count"] = 1
    elif failure == "pending":
        d["pending_tasks"] = 1
    elif failure == "stranded":
        row["in_processing"] = 1
    elif failure == "reconciliation":
        row["reconciled"] = False
    elif failure == "loss":
        d["audit"]["queue_losses"]["trade"] = 1
    elif failure == "processing":
        row["terminal"]["exception"] = 1
    elif failure == "histogram":
        d["discovery"]["decode_failures_by_reason"] = {}
    elif failure == "persistence":
        d["audit"]["durable_live_create_records"] = 0
    elif failure == "admission":
        d["admitted"] = 0
    elif failure == "transition":
        d["counts"]["transitions"] = 0
    elif failure == "cancelled":
        d["reason"] = "CANCELLED"
    elif failure == "noncanonical":
        d["counts"]["noncanonical_create_observations"] = 1
    assert q.verdict(**d)["status"] == "FAILED"


def test_connected_without_create_is_inconclusive_not_pass():
    d = inputs()
    d["discovery"]["connected"] = True
    d["discovery"]["launch_events"] = 0
    d["counts"] = {}
    d["admitted"] = 0
    d["audit"]["durable_live_create_records"] = 0
    d["audit"]["durable_live_create_mints"] = 0
    row = d["audit"]["shutdown"]["accounting"]["events"]["create"]
    row.update(persisted=0, terminal={})
    assert q.verdict(**d)["status"] == "INCONCLUSIVE_NO_LIVE_CREATE"
    row["in_processing"] = 1
    assert q.verdict(**d)["status"] == "FAILED"


async def test_real_queue_observation_and_durable_shutdown(tmp_path):
    from backend.app.config import Settings
    from backend.app.domain import MarketEvent
    from backend.app.discovery import PUMP_PROGRAM
    from backend.app.engine import RadarEngine

    now = time.time()
    # Synthetic canonical-shaped fixture; all assertions are offline, not real discoveries.
    event = MarketEvent(
        mint="OFFLINE_SYNTHETIC",
        event_id="offline-create",
        ts=now,
        source="Onchain Pump",
        kind="create",
        evidence={"program": PUMP_PROGRAM, "commitment": "confirmed"},
    )
    left = RadarEngine(Settings(mode="OBSERVE"), tmp_path / "left.db", offline=True)
    right = RadarEngine(Settings(mode="OBSERVE"), tmp_path / "observe.db", offline=True)
    ledger = p.Ledger(tmp_path / "history.jsonl")
    recorder = q.SmokeRecorder(ledger, now, right)
    detach = p.attach(right, recorder, clock=lambda: now)
    try:
        recorder.emit("START", {"synthetic": True})
        for engine in (left, right):
            assert engine.submit(event)
            assert engine.submit(event)
            await engine.drain_events()
            engine.intelligence.refresh(now, force=True)
        assert set(left.tokens) == set(right.tokens) == {event.mint}
        assert left.accounting.terminal == right.accounting.terminal
        assert left.accounting.persisted == right.accounting.persisted
        assert left.intelligence.results == right.intelligence.results
        assert recorder.counts["transitions"] > 0
        assert recorder.counts["live_persisted_on_return"] == 1
        assert recorder.admitted == {event.mint}
        assert not recorder.pending and not recorder.due
        recorder.emit("STOP", {"reason": "SYNTHETIC_ONLY"})
        ledger.close()
        trace = p.verify_ledger(ledger.path)
        assert trace["complete"] and not trace["populations"] and not trace["outcomes"]
        rows = [json.loads(x) for x in ledger.path.read_text().splitlines()]
        assert sum(x["kind"] == "DISCOVERY" for x in rows) == 2
        assert all(not x["payload"]["measurement_scheduled"] for x in rows if x["kind"] == "TRANSITION")
    finally:
        detach()
        ledger.file.close()
        await left.stop()
        await right.stop()
    audit = q.read_shutdown(tmp_path, right.session)
    assert audit["sqlite_ok"] and audit["cohort_count"] == 0
    assert audit["durable_live_create_records"] == audit["durable_live_create_mints"] == 1
    row = audit["shutdown"]["accounting"]["events"]["create"]
    assert row["reconciled"] and row["in_processing"] == row["pending"] == 0


def test_synthetic_sources_never_qualify(tmp_path):
    from backend.app.demo import demo_events

    ledger = p.Ledger(tmp_path / "synthetic.jsonl")
    recorder = q.SmokeRecorder(ledger, 1000, NS(_event_persisted=True))
    recorder.discovery(demo_events(1000, 0)[0], True, "processed", 1000)
    assert recorder.stop_reason == "NONCANONICAL_CREATE_SOURCE"
    assert not recorder.admitted and not recorder.counts["live_persisted_on_return"]
    ledger.close()


def test_preflight_refusal_before_engine_output_or_network(tmp_path, monkeypatch):
    monkeypatch.setattr(q.pilot, "verify_source", lambda sha: (_ for _ in ()).throw(p.PilotRefusal("test")))
    from dotenv import load_dotenv

    monkeypatch.setattr("dotenv.load_dotenv", lambda *a: None)
    assert callable(load_dotenv)
    with pytest.raises(p.PilotRefusal):
        q.preflight("a" * 40, tmp_path / "forbidden")
    assert not (tmp_path / "forbidden").exists()


def test_default_cli_never_runs_engine(monkeypatch, capsys):
    monkeypatch.setattr(q.sys, "argv", ["qualify_live_discovery.py"])
    monkeypatch.setattr(q, "run", lambda *a: pytest.fail("No live execution allowed"))
    q.main()
    assert json.loads(capsys.readouterr().out)["duration_seconds"] == 120


def test_competing_process_is_rejected_without_termination(monkeypatch):
    import psutil

    proc = NS(info={"pid": -1, "cmdline": ["python", "scripts/signal_quality_pilot.py"]})
    monkeypatch.setattr(psutil, "process_iter", lambda *a: [proc])
    with pytest.raises(p.PilotRefusal, match="Competing"):
        q.check_processes()


def test_report_does_not_mutate_diagnostic_inputs():
    d = inputs()
    saved = deepcopy(d)
    assert q.verdict(**d)["status"] == "PASS"
    assert d == saved


@pytest.mark.parametrize("blocked_start", [False, True])
async def test_bounded_controller_and_shutdown_without_providers(tmp_path, monkeypatch, blocked_start):
    import asyncio
    from backend.app import engine as engine_module
    from backend.app.config import Settings
    from backend.app.discovery import PUMP_PROGRAM
    from backend.app.domain import MarketEvent

    real_engine = engine_module.RadarEngine

    class OfflineEngine(real_engine):
        def __init__(self, settings, path):
            super().__init__(settings, path, offline=True)
            from backend.app.early_prices import PriceResearch

            self.price_research = PriceResearch(self.db, self.session)

        async def start(self):
            if blocked_start:
                await asyncio.Event().wait()
            self.running = True
            now = time.time()
            event = MarketEvent(
                mint="SYNTHETIC_CONTROLLER",
                kind="create",
                event_id="fixture",
                ts=now,
                source="Onchain Pump",
                evidence={"program": PUMP_PROGRAM, "commitment": "confirmed"},
            )
            self.onchain.health.update(messages=1, launch_events=1)
            self.submit(event)
            await self.drain_events()
            self.intelligence.refresh(now, force=True)

    monkeypatch.setattr(engine_module, "RadarEngine", OfflineEngine)
    monkeypatch.setattr(q, "ROOT", tmp_path)
    (tmp_path / "data/early_edge").mkdir(parents=True)
    monkeypatch.setattr(
        q, "preflight", lambda sha, output: ({"synthetic": True}, Settings(mode="OBSERVE"), output)
    )
    monkeypatch.setattr(q, "check_processes", lambda: None)
    monkeypatch.setattr(p, "source_unchanged", lambda source: True)
    monkeypatch.setattr(q, "SECONDS", 0.03)
    output = tmp_path / "data/early_edge/synthetic"
    result = await q.run("a" * 40, output)
    assert result["status"] == ("FAILED" if blocked_start else "PASS")
    assert result["reason"] == ("STARTUP_TIMEOUT" if blocked_start else "SCHEDULED_COMPLETION")
    assert result["pending_async_tasks_after_stop"] == 0
    assert result["observation_elapsed_seconds"] < 1
    assert json.loads((output / "shutdown.json").read_text())["checkpoint_complete"]
    assert p.verify_ledger(output / "history.jsonl")["complete"]


@pytest.mark.parametrize(
    "pressure,expected",
    [
        ("rss", "PILOT_RSS_STOP"),
        ("queue", "PILOT_QUEUE_STOP"),
        ("loss", "UNACCEPTABLE_QUEUE_LOSS"),
        ("storage", "PILOT_STORAGE_STOP"),
        ("stopped", "ENGINE_STOPPED"),
    ],
)
def test_unchanged_resource_guards(tmp_path, monkeypatch, pressure, expected):
    import psutil
    import shutil

    monkeypatch.setattr(
        psutil,
        "Process",
        lambda: NS(memory_info=lambda: NS(rss=(501 if pressure == "rss" else 100) * 1048576)),
    )
    monkeypatch.setattr(shutil, "disk_usage", lambda output: NS(free=1024 * 1048576))
    if pressure == "storage":
        with (tmp_path / "sparse-test-only").open("wb") as f:
            f.truncate(640 * 1048576)
    engine = NS(
        queue=NS(
            dropped_trades=int(pressure == "loss"),
            dropped_critical=0,
            heap=[None] * (800 if pressure == "queue" else 0),
        ),
        tasks=[],
        storage_stopped=False,
        running=pressure != "stopped",
        metrics={},
    )
    assert p.resource_reason(engine, tmp_path, 0) == expected


@pytest.mark.parametrize(
    "field,value",
    [
        ("reconciled", False),
        ("snapshot_available", False),
        ("calculation_failures", 1),
        ("aggregation_failures", 1),
        ("invalid_updates", 1),
        ("telemetry_integrity_failed", True),
    ],
)
def test_qualification_rejects_reserve_telemetry_failure(field, value):
    d = inputs()
    d["audit"]["shutdown"]["v21_prices"]["acquisition_diagnostics"]["reserve_rejections"][field] = value
    result = q.verdict(**d)
    assert result["status"] == "FAILED"
    assert not result["checks"]["reserve_diagnostics_integrity"]


def test_qualification_checks_policy_and_fairness_without_claiming_observation():
    from backend.app.fx_selection import FxSelection

    d = inputs()
    fx = FxSelection().snapshot()
    d["audit"]["shutdown"]["v21_prices"]["acquisition_diagnostics"]["fx_selection"] = fx
    assert q.verdict(**d)["checks"]["fx_selection_integrity"]
    fx["per_product"]["SOL-USD"]["missed_eligible_mixed_rounds"] = 3
    assert not q.verdict(**d)["checks"]["fx_selection_integrity"]
