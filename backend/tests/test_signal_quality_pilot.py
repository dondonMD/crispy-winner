"""Synthetic instrumentation qualification. Never starts an engine or quote provider."""

import json
from copy import deepcopy
from types import SimpleNamespace as NS
import pytest
from scripts import signal_quality_pilot as p

START = 1000.0
MINT = "SYNTHETIC_MINT"


def mark(at, price=1):
    return dict(
        mint=MINT,
        price=price,
        observed_at=at,
        acquired_at=at,
        requested_at=at,
        valid_until=at + 20,
        quote_mint="SYNTHETIC_QUOTE",
        slot=int(at),
        currency="USD",
        evidence_level="SYNTHETIC_INDICATIVE_ONLY",
    )


def engine(at=START, label="ACTIVE EMERGING BULLISH", baseline=True):
    early = dict(
        classification=label,
        observed_at=at,
        valid_until=at + 10,
        version="early-market-v2.1-SYNTHETIC",
        windows={},
        manual_only=True,
        validated_edge=False,
    )
    token = NS(state=NS(value="WATCHING"), graduation=None, disagreement=False, created=START - 10)
    return NS(
        tokens={MINT: token},
        intelligence=NS(results={MINT: dict(early_market=early)}),
        price_research=NS(
            marks={MINT: mark(at)} if baseline else {},
            diagnostics=NS(first_review=lambda *args: dict(status="SYNTHETIC_UNKNOWN")),
        ),
    )


def rows(ledger):
    ledger.flush()
    return [json.loads(x) for x in ledger.path.read_text().splitlines()]


def test_plan_is_noncollectable_and_reserves_all_followup_time():
    plan = p.protocol()
    assert plan["duration_seconds"] == 1200
    assert (
        plan["first_class_measurement_cutoff_seconds"]
        + max(plan["horizons"])
        + plan["endpoint_delay_seconds"]
        == 1200
    )
    assert plan["PRE_COHORT_READY"] == "NO" and not plan["phase4_authorized"] and not plan["collectable"]


@pytest.mark.parametrize("sha", [p.BASE, None, "bd56824", "main"])
def test_parent_or_implicit_sha_refused_before_git_or_providers(monkeypatch, sha):
    monkeypatch.setattr(
        p, "git", lambda *args: pytest.fail("Parent must fail before any source/provider work")
    )
    with pytest.raises(ValueError):
        p.verify_source(sha)


def test_successor_must_match_published_origin_and_clean_source(monkeypatch):
    sha = "a" * 40

    def git(*args):
        if args == ("branch", "--show-current"):
            return p.BRANCH
        if args == ("rev-parse", "HEAD"):
            return sha
        return p.BASE

    monkeypatch.setattr(p, "git", git)
    with pytest.raises(ValueError, match="origin"):
        p.verify_source(sha)


def test_full_append_only_history_includes_risk_neutral_and_missing(tmp_path):
    ledger = p.Ledger(tmp_path / "history.jsonl")
    r = p.Recorder(ledger, START)
    e = engine(baseline=False)
    for i, label in enumerate(p.CLASSES):
        e.intelligence.results[MINT]["early_market"].update(classification=label, observed_at=START + i)
        r.refresh(e, START + i)
    transition = [x for x in rows(ledger) if x["kind"] == "TRANSITION"]
    assert len(transition) == len(p.CLASSES)
    assert [x["payload"]["classification"] for x in transition] == list(p.CLASSES)
    assert all(x["payload"]["baseline"] is None for x in transition)
    r.endpoints(e, START + 1200, closing=True)
    r.emit("STOP", dict(reason="synthetic"))
    ledger.close()
    report = p.verify_ledger(ledger.path)
    assert report["complete"] and report["unresolved_horizons"] == 0
    assert len(report["outcomes"]) == len(p.CLASSES) * 5
    assert all("UNAVAILABLE" in k for k in report["outcomes"])


def test_first_token_class_dedup_and_no_later_baseline_replacement(tmp_path):
    ledger = p.Ledger(tmp_path / "history.jsonl")
    r = p.Recorder(ledger, START)
    e = engine(baseline=False)
    r.refresh(e, START)
    e.price_research.marks[MINT] = mark(START + 1, 100)
    e.intelligence.results[MINT]["early_market"]["observed_at"] = START + 1
    r.refresh(e, START + 1)
    first = rows(ledger)[0]["payload"]
    assert r.counts["measurements"] == 1 and first["baseline"] is None
    e.price_research.marks[MINT] = mark(START + 16)
    r.endpoints(e, START + 16)
    outcome = [x["payload"] for x in rows(ledger) if x["kind"] == "OUTCOME"][0]
    assert outcome["endpoint_available"] and not outcome["baseline_available"]
    assert outcome["status"] == "UNAVAILABLE" and outcome["gross_change_pct"] is None
    ledger.close()


@pytest.mark.parametrize("price,status", [(2, "POSITIVE_GROSS"), (0.5, "NEGATIVE_GROSS"), (1, "FLAT_GROSS")])
def test_gross_only_first_followup_keeps_negative_and_flat(tmp_path, price, status):
    ledger = p.Ledger(tmp_path / "history.jsonl")
    r = p.Recorder(ledger, START)
    e = engine()
    r.refresh(e, START)
    e.price_research.marks[MINT]["price"] = 99  # Cannot mutate the frozen baseline.
    e.price_research.marks[MINT] = mark(START + 14, price)
    r.endpoints(e, START + 15)
    assert not [x for x in rows(ledger) if x["kind"] == "OUTCOME"]
    e.price_research.marks[MINT] = mark(START + 16, price)
    r.endpoints(e, START + 16)
    row = [x["payload"] for x in rows(ledger) if x["kind"] == "OUTCOME"][0]
    assert row["status"] == status and row["gross_change_pct"] == pytest.approx((price - 1) * 100)
    assert row["net_return_pct"] is None and not row["executable"]
    ledger.close()


def test_tail_transitions_still_recorded_without_future_selected_measurements(tmp_path):
    ledger = p.Ledger(tmp_path / "history.jsonl")
    r = p.Recorder(ledger, START)
    e = engine(START + p.CAPTURE)
    r.refresh(e, START + p.CAPTURE)
    e.intelligence.results[MINT]["early_market"].update(
        classification="BEARISH PRESSURE", observed_at=START + 900, valid_until=START + 910
    )
    r.refresh(e, START + 900)
    assert not r.pending and r.counts["transitions"] == 2
    assert all(not x["payload"]["measurement_scheduled"] for x in rows(ledger))
    ledger.close()


def test_shutdown_censoring_distinct_from_missing_data(tmp_path):
    ledger = p.Ledger(tmp_path / "history.jsonl")
    r = p.Recorder(ledger, START)
    e = engine(baseline=False)
    r.refresh(e, START)
    r.endpoints(e, START + 40, closing=True)
    out = [x["payload"] for x in rows(ledger) if x["kind"] == "OUTCOME"]
    assert len(out) == 5
    assert next(x for x in out if x["horizon"] == 15)["status"] == "UNAVAILABLE"
    assert all(x["status"] == "CENSORED_SHUTDOWN" for x in out if x["horizon"] >= 30)
    ledger.close()


def test_candidate_departure_does_not_drop_outstanding_outcomes(tmp_path):
    ledger = p.Ledger(tmp_path / "history.jsonl")
    r = p.Recorder(ledger, START)
    e = engine()
    r.refresh(e, START)
    e.tokens.clear()
    e.intelligence.results.clear()
    r.refresh(e, START + 1)
    r.endpoints(e, START + 400)
    assert not r.pending and len([x for x in rows(ledger) if x["kind"] == "OUTCOME"]) == 5
    assert any(x["kind"] == "LEFT_MONITORED_SET" for x in rows(ledger))
    ledger.close()


def test_clock_regression_source_future_and_missing_assessment_not_invented(tmp_path):
    ledger = p.Ledger(tmp_path / "history.jsonl")
    r = p.Recorder(ledger, START)
    e = engine(START + 1)
    r.refresh(e, START)
    x = rows(ledger)[0]["payload"]
    assert x["classification"] == "UNASSESSED" and not x["measurement_scheduled"]
    r.refresh(e, START - 1)
    assert r.stop_reason == "CLOCK_REGRESSION"
    ledger.close()


def test_truncated_or_modified_ledger_never_verified(tmp_path):
    ledger = p.Ledger(tmp_path / "history.jsonl")
    ledger.emit("DISCOVERY", dict(mint=MINT))
    ledger.close()
    report = p.verify_ledger(ledger.path)
    assert not report["complete"] and "INTERRUPTION" in report["interruption"]
    with ledger.path.open("ab") as f:
        f.write(b"{")
    with pytest.raises(ValueError):
        p.verify_ledger(ledger.path)


def test_byte_failure_retains_unresolved_accounting(tmp_path, monkeypatch):
    ledger = p.Ledger(tmp_path / "history.jsonl")
    r = p.Recorder(ledger, START)
    e = engine()
    r.refresh(e, START)
    ledger.flush()

    def fail(*args):
        raise p.StopPilot("SYNTHETIC_LIMIT")

    monkeypatch.setattr(ledger, "emit", fail)
    r.endpoints(e, START + 400, closing=True)
    assert r.stop_reason and sum(len(x["remaining"]) for x in r.pending.values()) == 5
    ledger.close()
    assert p.verify_ledger(ledger.path)["unresolved_horizons"] == 5


def test_observer_preserves_original_return_and_state_on_own_failure(tmp_path):
    ledger = p.Ledger(tmp_path / "history.jsonl")
    r = p.Recorder(ledger, START)
    e = engine()
    original = e.tokens[MINT].__dict__.copy()
    e.process = lambda event, now=None: "ORIGINAL_RETURN"
    e.intelligence.last_refresh = 0

    def refresh(now):
        e.intelligence.last_refresh = now
        return "REFRESH_RETURN"

    e.intelligence.refresh = refresh
    detach = p.attach(e, r, clock=lambda: START)
    event = NS(kind="create", mint=MINT, ts=START)
    assert e.process(event) == "ORIGINAL_RETURN"
    assert e.intelligence.refresh(START) == "REFRESH_RETURN"
    assert e.tokens[MINT].__dict__ == original
    detach()
    ledger.close()


def test_recorder_limit_does_not_exclude_favourable_only(tmp_path):
    ledger = p.Ledger(tmp_path / "history.jsonl")
    r = p.Recorder(ledger, START)
    e = engine()
    r.counts["measurements"] = 2000
    r.refresh(e, START)
    assert r.stop_reason == "MEASUREMENT_LIMIT" and not r.pending
    ledger.close()


def test_published_successor_accepts_only_explicit_preserved_dirty_paths_and_detects_drift(
    tmp_path, monkeypatch
):
    sha = "a" * 40
    script = tmp_path / "scripts/signal_quality_pilot.py"
    script.parent.mkdir()
    script.write_text("# synthetic published fixture")
    conf = tmp_path / "config/conservative.yaml"
    conf.parent.mkdir()
    conf.write_text("mode: OBSERVE")
    monkeypatch.delenv("RADAR_CONFIG", raising=False)
    monkeypatch.setattr(p, "ROOT", tmp_path)
    dirty = ["backend/tests/test_endurance_harness.py"]
    f = tmp_path / dirty[0]
    f.parent.mkdir(parents=True)
    f.write_text("# preserved synthetic dirty fixture")

    def git(*args):
        if args == ("branch", "--show-current"):
            return p.BRANCH
        if args[:1] == ("rev-parse",):
            return sha
        if args == ("diff", "--name-only", "HEAD"):
            return "\n".join(dirty)
        if args == ("ls-files", "--others", "--exclude-standard"):
            return ""
        if args == ("ls-files",):
            return "scripts/signal_quality_pilot.py\nconfig/conservative.yaml\n" + dirty[0]
        pytest.fail(f"unexpected Git call {args}")

    calls = []
    monkeypatch.setattr(p, "git", git)
    monkeypatch.setattr(p.subprocess, "run", lambda command, **kw: calls.append(command))
    source = p.verify_source(sha)
    assert source["sha"] == sha and source["allowed_local_changes"] == dirty
    assert calls[0][-2:] == [p.BASE, sha] and p.source_unchanged(source)
    script.write_text("# synthetic uncommitted change")
    assert not p.source_unchanged(source)
    dirty.append("backend/app/opportunity.py")
    with pytest.raises(ValueError, match="Unpublished"):
        p.verify_source(sha)


def test_unavailable_risk_control_is_retained_and_does_not_trigger_provider_work(tmp_path):
    ledger = p.Ledger(tmp_path / "history.jsonl")
    r = p.Recorder(ledger, START)
    e = engine(label="AVOID", baseline=False)
    snapshot = deepcopy(e.intelligence.results)
    r.refresh(e, START)
    assert e.intelligence.results == snapshot and r.counts["measurements"] == 1
    assert rows(ledger)[0]["payload"]["classification"] == "AVOID"
    ledger.close()


def test_bulk_shutdown_censoring_flushes_bounded_chunks_without_losing_denominators(tmp_path):
    import heapq

    ledger = p.Ledger(tmp_path / "history.jsonl")
    r = p.Recorder(ledger, START)
    e = engine(baseline=False)
    for identity in range(1000):
        r.pending[identity] = dict(
            mint=MINT, signal_at=START, label="NEUTRAL / WAIT", baseline=None, remaining=set(p.HORIZONS)
        )
        for h in p.HORIZONS:
            heapq.heappush(r.due, (START + h, identity, h))
    r.endpoints(e, START + 1, closing=True)
    assert not r.pending and not r.stop_reason
    assert sum(r.counts.values()) == 5000
    ledger.close()


def test_source_interruption_censors_instead_of_manufacturing_measurement(tmp_path):
    ledger = p.Ledger(tmp_path / "history.jsonl")
    r = p.Recorder(ledger, START)
    e = engine()
    r.refresh(e, START)
    e.price_research.marks[MINT] = mark(START + 16, 2)
    r.integrity_interrupted = True
    r.endpoints(e, START + 16, closing=True)
    outcomes = [x["payload"] for x in rows(ledger) if x["kind"] == "OUTCOME"]
    assert len(outcomes) == 5 and all(x["status"] == "CENSORED_INTERRUPTION" for x in outcomes)
    assert all(x["gross_change_pct"] is None for x in outcomes)
    ledger.close()


async def test_real_offline_engine_scores_and_decisions_are_identical_with_observer(tmp_path):
    from backend.app.engine import RadarEngine
    from backend.app.config import Settings
    from backend.app.demo import demo_events

    a = RadarEngine(Settings(mode="DEMO"), tmp_path / "baseline.db", offline=True)
    b = RadarEngine(Settings(mode="DEMO"), tmp_path / "observed.db", offline=True)
    ledger = p.Ledger(tmp_path / "history.jsonl")
    recorder = p.Recorder(ledger, START)
    clock = [START]
    detach = p.attach(b, recorder, clock=lambda: clock[0])
    for tick in range(12):
        clock[0] = START + tick
        for event in demo_events(START, tick):
            assert a.process(event, event.ts) == b.process(event, event.ts)
        a.intelligence.refresh(clock[0], force=True)
        b.intelligence.refresh(clock[0], force=True)
        assert a.intelligence.results == b.intelligence.results
        for mint in a.tokens:
            left, right = a.tokens[mint], b.tokens[mint]
            assert (left.state, left.features, left.scores, left.decision) == (
                right.state,
                right.features,
                right.scores,
                right.decision,
            )
    assert not recorder.stop_reason and recorder.counts["transitions"] > 0
    recorder.endpoints(b, clock[0], closing=True)
    detach()
    ledger.close()
    await a.stop()
    await b.stop()


def test_resource_guard_is_earlier_without_changing_engine_limits(tmp_path, monkeypatch):
    import psutil

    monkeypatch.setattr(psutil, "Process", lambda: NS(memory_info=lambda: NS(rss=500 * 1048576)))
    assert p.resource_reason(NS(), tmp_path, 10) == "PILOT_RSS_STOP"


async def test_live_entry_refuses_parent_without_engine_or_output(tmp_path, monkeypatch):
    import dotenv
    from backend.app import engine as engine_module

    monkeypatch.setattr(dotenv, "load_dotenv", lambda *args: None)
    monkeypatch.setattr(
        engine_module, "RadarEngine", lambda *args: pytest.fail("No engine may be constructed")
    )
    out = tmp_path / "must-not-exist"
    with pytest.raises(ValueError, match="successor"):
        await p.run(p.BASE, out)
    assert not out.exists()


def test_failed_ledger_write_is_never_retried_or_acknowledged(tmp_path):
    ledger = p.Ledger(tmp_path / "history.jsonl")
    ledger.emit("DISCOVERY", dict(mint=MINT))
    original = ledger.file

    def fail(data):
        raise OSError("synthetic disk failure")

    ledger.file = NS(write=fail, fileno=original.fileno, close=original.close)
    with pytest.raises(OSError):
        ledger.flush()
    assert ledger.failed and ledger.bytes == 0
    ledger.file = original
    with pytest.raises(p.StopPilot):
        ledger.flush()
    ledger.close()
    assert ledger.path.stat().st_size == 0 and not p.verify_ledger(ledger.path)["complete"]
