"""Synthetic diagnostic failures/clock boundaries, never market observations."""

import copy
import asyncio
import itertools
import json
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

import backend.app.truncation as recovery
from backend.app.domain import MarketEvent, PriorityBuffer
from backend.tests.test_smoke_observe import NOW, MINT, create, run_smoke as run_smoke
from backend.tests.test_truncation_recovery import transaction, b58
from backend.tests.test_onchain_trades import payload, wire
from scripts.smoke_evidence_diagnostics import SmokeTiming, bounded_section, SECTION_BYTES, CAUSES


@pytest.mark.parametrize("inner,shape,data_kind", list(itertools.product((True, False),
                          ("authority", "wrong", "two", "zero"), ("known", "short", "unknown"))))
def test_cpi_every_feasible_condition_combination_preserves_classification(inner, shape, data_kind):
    tx, signature = transaction(inner=True)
    keys = tx["transaction"]["message"]["accountKeys"]
    keys.append(recovery.EVENT_AUTHORITY)
    accounts = ([len(keys) - 1] if shape == "authority" else [1] if shape == "wrong"
                else [1, 1] if shape == "two" else [])
    tag = sorted(recovery.EVENTS)[0] if data_kind == "known" else bytes([255]) * 8
    data = recovery.EVENT_CPI + (b"" if data_kind == "short" else tag)
    instruction = dict(programIdIndex=0, accounts=accounts, data=b58(data))
    if inner:
        tx["meta"]["innerInstructions"][0]["instructions"].append(instruction)
    else:
        tx["transaction"]["message"]["instructions"] = [instruction]
        tx["meta"]["innerInstructions"] = []
    metrics = {"unsupported_instruction_counts": dict.fromkeys(("other", "unknown_discriminator",
                "multi_hop_curve_swap"), 0), "event_cpi_rejections": recovery.cpi_diagnostics(),
                "event_cpi_integrity_failures": 0}
    original = copy.deepcopy(tx)
    result = recovery.transaction_impact(tx, signature, 123, lambda _: False, metrics)
    # Independent contract table: only an inner/single-authority/known-tag
    # fixture is canonical. Every other synthetic combination fails closed.
    canonical = inner and shape == "authority" and data_kind == "known"
    expected_classification = "UNTRACKED_CONFIRMED" if canonical else "UNSUPPORTED_PUMP_TRADE"
    assert result == (expected_classification, set())
    assert tx == original
    # Fixed bit expectations do not use the implementation under test as oracle.
    expected = ((0 if inner else 1) | {"authority": 0, "wrong": 4, "two": 2, "zero": 2}[shape]
                | {"known": 0, "short": 8, "unknown": 16}[data_kind])
    snapshot = recovery.cpi_snapshot(metrics)
    assert snapshot["reconciled"]
    assert snapshot["rejected_instructions"] == bool(expected)
    assert sum(snapshot["masks"]) == bool(expected)
    if expected:
        assert snapshot["masks"][expected] == 1
    assert snapshot["conditions"] == {key: int(bool(expected & bit)) for key, bit in (
        ("not_inner", 1), ("account_count", 2), ("authority", 4), ("short_data", 8), ("unknown_event", 16))}
    assert len(json.dumps(snapshot)) < 1024
    assert signature not in json.dumps(snapshot)
    assert recovery.EVENT_AUTHORITY not in json.dumps(snapshot)


def test_cpi_calculation_and_corrupt_aggregation_cannot_replace_rejection(monkeypatch):
    tx, signature = transaction(inner=True)
    tx["meta"]["innerInstructions"][0]["instructions"].append(
        dict(programIdIndex=0, accounts=[1], data=b58(recovery.EVENT_CPI)))
    metrics = {"unsupported_instruction_counts": dict.fromkeys(("other", "unknown_discriminator",
               "multi_hop_curve_swap"), 0), "event_cpi_rejections": recovery.cpi_diagnostics(),
               "event_cpi_integrity_failures": 0}

    def fail(*args):
        raise RuntimeError("synthetic telemetry failure")

    monkeypatch.setattr(recovery, "cpi_failure_mask", fail)
    assert recovery.transaction_impact(tx, signature, 123, lambda _: False, metrics)[0] == "UNSUPPORTED_PUMP_TRADE"
    assert metrics["event_cpi_integrity_failures"] == 1
    assert not recovery.cpi_snapshot(metrics)["reconciled"]
    monkeypatch.undo()
    metrics["event_cpi_rejections"]["masks"] = [0] * 33
    assert recovery.transaction_impact(tx, signature, 123, lambda _: False, metrics)[0] == "UNSUPPORTED_PUMP_TRADE"
    assert metrics["event_cpi_integrity_failures"] == 2
    assert recovery.cpi_snapshot(metrics)["available"] is False
    metrics["event_cpi_rejections"] = recovery.cpi_diagnostics()
    metrics["event_cpi_rejections"]["conditions"]["unknown_event"] = "unsafe-payload"
    sanitized = recovery.cpi_snapshot(metrics)
    assert sanitized["available"] is False
    assert "unsafe-payload" not in json.dumps(sanitized)


@pytest.mark.parametrize("reason", ["untracked", "venue", "pool_epoch", "duplicate_memory", "duplicate_db", "stale"])
async def test_smoke_uses_native_rejection_and_complete_accounting(run_smoke, reason):
    async def action(engine):
        if reason != "untracked":
            engine.submit(create())
            await engine.drain_events()
        stamp = NOW - 21 if reason in ("untracked", "venue", "pool_epoch", "stale") else NOW
        source = "PumpSwap WSS" if reason == "pool_epoch" else "Solana WSS"
        trade = MarketEvent(kind="trade", mint=MINT, ts=stamp, event_id="trade", source=source,
                            side="buy", volume=1, currency="SOL")
        if reason == "venue":
            engine.tokens[MINT].flow_venue = "PUMPSWAP"
        if reason in ("duplicate_memory", "duplicate_db"):
            engine.submit(trade)
            await engine.drain_events()
            if reason == "duplicate_db":
                engine.dedup.seen.clear()
        engine.submit(trade)
        await engine.drain_events()

    _, report, receipt, _ = await run_smoke(action)
    section = report["evidence_diagnostics"]
    for phase in ("pre_shutdown", "post_shutdown"):
        native = section[phase]["accounting"]["events"]
        assert native["create"]["reconciled"] and native["trade"]["reconciled"]
        assert native["trade"]["terminal"][reason] == 1
        assert section[phase]["timing"]["stale_partition_reconciled"]
    assert section["post_shutdown"]["accounting"]["events"]["trade"] == receipt["accounting"]["events"]["trade"]
    assert report["trade_process_rejections"] == {"stale": int(reason == "stale"), "other": int(reason != "stale")}
    assert section["shutdown"] == "RETURNED"
    assert len(json.dumps(section).encode()) <= SECTION_BYTES


@pytest.mark.parametrize("name,ages", [
    ("already_old_at_dispatch", (-30, 0, .1, .2)),
    ("old_before_admission", (-19, 0, 2, 2.1)),
    ("old_in_queue", (-19, 0, .1, 2)),
    ("old_after_selection", (-19, 0, .1, .2)),
    ("future_dated", (30, 0, .1, .2)),
    ("clock_irregular", (-19, 0, .1, .2)),
    ("provenance_unavailable", (-30, 0, .1, .2)),
    ("selection_boundary_ambiguous", (-19, 0, .1, .2)),
])
def test_every_stale_stage_category_is_explicit(name, ages, monkeypatch):
    stamp, receive, admission, selection = ages
    clock = [NOW + receive]
    monkeypatch.setattr(time, "time", lambda: clock[0])
    queue = PriorityBuffer(10)
    timing = SmokeTiming(queue)
    timing.clock = lambda: (clock[0], clock[0] - NOW)
    engine = SimpleNamespace(onchain=SimpleNamespace(receive=lambda _: None))
    detach = timing.attach(engine)
    timing.dispatch = None if name == "provenance_unavailable" else timing.clock()
    clock[0] = NOW + admission
    event = MarketEvent(kind="trade", mint="synthetic", ts=NOW + stamp, event_id="synthetic", source="Solana WSS")
    queue.put(event, 1)
    clock[0] = NOW + selection
    if name == "selection_boundary_ambiguous":
        # Supply a known bracket crossing the20s boundary; never assign this
        # interval to a precise native selection instant that was not captured.
        queue.drain()
        timing.records[1]["selection_before"] = (NOW + .2, .2)
        timing.records[1]["selected"] = (NOW + 2, 2)
    else:
        queue.drain()
    clock[0] = NOW + (3 if name not in ("already_old_at_dispatch", "future_dated", "provenance_unavailable") else .3)
    seq = timing.started(event, clock[0], True)
    if name == "clock_irregular":
        timing.records[seq]["started"] = (clock[0] + 1, clock[0] - NOW)
    timing.finished(seq, event, True, "stale", 20)
    assert timing.stale["trade"][name] == 1
    assert sum(timing.stale["trade"].values()) == 1
    assert not timing.records
    detach()


def test_timing_capacity_overflow_eviction_failure_and_size_bounds(monkeypatch):
    queue = PriorityBuffer(10)
    timing = SmokeTiming(queue)
    engine = SimpleNamespace(onchain=SimpleNamespace(receive=lambda _: None))
    detach = timing.attach(engine)
    for i in range(40):
        queue.put(MarketEvent(kind="trade", mint="synthetic", ts=NOW, event_id=str(i), source="SYNTHETIC"), i)
    assert len(timing.records) == len(queue.heap) == 10
    assert timing.peak == 10
    timing.limit = 10
    queue.drain()
    for i in range(10):
        queue.put(MarketEvent(kind="trade", mint="synthetic", ts=NOW, event_id=str(i + 40), source="SYNTHETIC"), i)
    assert timing.omitted == 10
    assert len(timing.records) == 10
    assert not timing.snapshot()["attribution_complete"]
    monkeypatch.setattr(timing, "selected", lambda *args: (_ for _ in ()).throw(RuntimeError()))
    assert len(queue.drain()) == 10
    assert timing.failures
    timing.close()
    assert timing.unresolved_shutdown["trade"] == 10 and not timing.records
    section = bounded_section(None, {"timing": timing.snapshot()}, "FAILED")
    assert len(json.dumps(section)) <= SECTION_BYTES
    huge = {"timing": {"histograms": "x" * SECTION_BYTES}}
    assert bounded_section(huge, huge, "RETURNED")["omitted_histograms"]
    assert bounded_section({"oversized": "x" * SECTION_BYTES}, {}, "FAILED")["integrity_failure"]
    assert set(timing.stale["trade"]) == set(CAUSES)
    detach()


async def test_pending_create_is_preserved_before_stop_and_terminal_after(run_smoke):
    async def pending(engine):
        engine.submit(create())

    engine, report, receipt, raw = await run_smoke(pending)
    section = report["evidence_diagnostics"]
    pre = section["pre_shutdown"]["accounting"]["events"]["create"]
    post = section["post_shutdown"]["accounting"]["events"]["create"]
    assert pre["pending"] == 1 and not pre["terminal"]
    assert post["pending"] == post["in_processing"] == 0
    assert post["terminal"] == {"shutdown_unprocessed": 1}
    assert post == receipt["accounting"]["events"]["create"]
    assert raw == 0 and pre["reconciled"] and post["reconciled"]
    assert section["post_shutdown"]["timing"]["unresolved_shutdown"]["create"] == 1
    assert not section["post_shutdown"]["timing"]["attribution_complete"]
    assert engine.queue.put.__self__ is engine.queue


async def test_detached_cancellation_has_native_final_disposition(run_smoke, monkeypatch):
    import backend.app.engine as core

    async def cancellation(engine):
        reached = asyncio.Event()
        facade = SimpleNamespace(**vars(asyncio))

        async def pause(delay):
            reached.set()
            await asyncio.Event().wait()

        facade.sleep = pause
        monkeypatch.setattr(core, "asyncio", facade)
        for i in range(6):
            engine.submit(create(str(i), mint=f"synthetic-{i}"))
        task = asyncio.create_task(engine.drain_events())
        await reached.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    _, report, _, raw = await run_smoke(cancellation)
    section = report["evidence_diagnostics"]
    assert raw == 5
    assert section["post_shutdown"]["accounting"]["events"]["create"]["terminal"] == {
        "processed": 5, "cancelled": 1}
    assert section["post_shutdown"]["timing"]["unresolved_shutdown"]["create"] == 1


@pytest.mark.parametrize("method", ["started", "finished", "snapshot"])
async def test_timing_failure_never_changes_original_decision_or_hides_integrity(run_smoke, monkeypatch, method):
    def fail(*args):
        raise RuntimeError("synthetic telemetry failure")

    monkeypatch.setattr(SmokeTiming, method, fail)

    async def action(engine):
        engine.submit(create())
        await engine.drain_events()

    _, report, _, raw = await run_smoke(action)
    assert raw == report["launches"] == 1
    state = report["evidence_diagnostics"]["post_shutdown"]
    assert state["accounting"]["events"]["create"]["terminal"] == {"processed": 1}
    assert state["timing"]["integrity_failures"] > 0
    assert not state["timing"]["attribution_complete"]


async def test_shutdown_failure_is_reported_and_original_exception_survives(run_smoke, tmp_path):
    failure = RuntimeError("synthetic shutdown failure")

    async def action(engine):
        engine.submit(create())
        original = engine.stop

        async def broken():
            await original()
            raise failure

        engine.stop = broken

    with pytest.raises(RuntimeError) as caught:
        await run_smoke(action)
    assert caught.value is failure
    section = json.loads((tmp_path / "data/observe-smoke.json").read_text())["evidence_diagnostics"]
    assert section["shutdown"] == "FAILED"
    assert section["post_shutdown"]["accounting"]["events"]["create"]["reconciled"]


async def test_body_failure_preserves_error_and_final_accounting(run_smoke, tmp_path):
    failure = RuntimeError("synthetic snapshot failure")

    async def action(engine):
        engine.submit(create())

        def broken():
            raise failure

        engine.snapshot = broken

    with pytest.raises(RuntimeError) as caught:
        await run_smoke(action)
    assert caught.value is failure
    report = json.loads((tmp_path / "data/observe-smoke.json").read_text())
    assert report["status"] == "PRE_SHUTDOWN_REPORT_UNAVAILABLE"
    section = report["evidence_diagnostics"]
    assert section["pre_shutdown"] is None and section["shutdown"] == "RETURNED"
    assert section["post_shutdown"]["accounting"]["events"]["create"]["terminal"] == {"shutdown_unprocessed": 1}


@pytest.mark.parametrize("body_fails,stop_fails", [(True, False), (False, True), (True, True), (False, False)])
async def test_report_write_failure_preserves_primary_error(run_smoke, monkeypatch, body_fails, stop_fails):
    observation = RuntimeError("synthetic observation failure")
    shutdown = RuntimeError("synthetic shutdown failure")
    persistence = OSError("synthetic write failure")
    attempted = []
    original_write = Path.write_text
    engines = []

    def fail_report(path, text, *args, **kwargs):
        if path.name == "observe-smoke.json":
            attempted.append(json.loads(text))
            raise persistence
        return original_write(path, text, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", fail_report)

    async def action(engine):
        engines.append(engine)
        engine.submit(create())
        if body_fails:
            def broken_snapshot():
                raise observation
            engine.snapshot = broken_snapshot
        if stop_fails:
            original_stop = engine.stop

            async def broken_stop():
                await original_stop()
                raise shutdown
            engine.stop = broken_stop

    primary = shutdown if stop_fails else observation if body_fails else persistence
    with pytest.raises(type(primary)) as caught:
        await run_smoke(action)
    assert caught.value is primary
    assert len(attempted) == 1  # No automatic persistence retry or fake success.
    diagnostics = attempted[0]["evidence_diagnostics"]
    assert diagnostics["shutdown"] == ("FAILED" if stop_fails else "RETURNED")
    assert diagnostics["post_shutdown"]["accounting"]["events"]["create"]["reconciled"]
    assert engines[0].accounting.snapshot(engines[0].queue)["events"]["create"]["in_processing"] == 0
    if primary is not persistence:
        assert "Smoke diagnostic report publication failed; report integrity is unverified." in primary.__notes__


async def test_actual_notification_dispatch_has_known_first_application_age(run_smoke):
    async def action(engine):
        engine.submit(create())
        await engine.drain_events()
        engine.onchain.receive(payload(wire(mint=MINT, timestamp=int(NOW - 30))))
        await engine.drain_events()

    _, report, _, _ = await run_smoke(action)
    timing = report["evidence_diagnostics"]["post_shutdown"]["timing"]
    assert timing["stale_timing"]["trade"]["already_old_at_dispatch"] == 1
    assert timing["raw_frame_arrival"] == timing["provider_send_time"] == "UNAVAILABLE"
    assert timing["integrity_failures"] == 0
    assert report["trade_process_rejections"] == {"stale": 1, "other": 0}


def test_dispatch_exception_restores_context_and_does_not_retain_payload():
    failure = RuntimeError("synthetic dispatch failure")

    def broken(value):
        raise failure

    queue = PriorityBuffer(10)
    engine = SimpleNamespace(onchain=SimpleNamespace(receive=broken))
    timing = SmokeTiming(queue)
    detach = timing.attach(engine)
    with pytest.raises(RuntimeError) as caught:
        engine.onchain.receive(object())
    assert caught.value is failure
    assert timing.dispatch is None and not timing.records
    detach()
