"""Exercise the actual nested smoke observer with real offline queue processing.

Only engine.start is replaced: no provider/monitor task or live observation runs.
All files, including the legacy fixed report path, are isolated by test cwd.
"""

import asyncio
import json
import sqlite3
import time
from types import SimpleNamespace

import pytest
from solders.pubkey import Pubkey

from backend.app.config import Settings
from backend.app.domain import MarketEvent
from backend.app.engine import RadarEngine
import backend.app.engine as engine_module
from scripts import smoke_observe


NOW = 1800000000.0
MINT = str(Pubkey.from_bytes(bytes([7]) * 32))


def create(identity="create", mint=MINT, stamp=NOW):
    return MarketEvent(kind="create", mint=mint, ts=stamp, source="Onchain Pump",
                       event_id=identity, name="Synthetic offline test", symbol="TEST")


def row(engine, kind="create"):
    return engine.accounting.snapshot(engine.queue)["events"][kind]


@pytest.fixture
def run_smoke(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    monkeypatch.setattr(time, "time", lambda: NOW)

    async def run(action):
        engines = []

        def factory(settings, path):
            assert settings.mode == "OBSERVE" and settings.max_deep == 25
            engine = RadarEngine(settings, tmp_path / "observed.db", offline=True)
            engines.append(engine)

            async def start():
                # The real harness installs counted_process before calling start.
                await action(engine)

            engine.start = start
            return engine

        monkeypatch.setattr(smoke_observe, "RadarEngine", factory)
        await smoke_observe.main(seconds=0)
        capsys.readouterr()
        assert len(engines) == 1
        engine = engines[0]
        report = json.loads((tmp_path / "data/observe-smoke.json").read_text())
        with sqlite3.connect((tmp_path / "observed.db").as_uri() + "?mode=ro", uri=True) as sql:
            receipt = json.loads(sql.execute("SELECT payload FROM evidence_runs WHERE session=?",
                                             (engine.session,)).fetchone()[0])
            raw = sql.execute("SELECT count(*) FROM records WHERE session=? AND kind='event'",
                              (engine.session,)).fetchone()[0]
        assert receipt["status"] == "STOPPED" and receipt["checkpoint_complete"]
        assert not engine.tasks
        return engine, report, receipt, raw

    return run


async def test_real_queued_create_matches_unobserved_engine(run_smoke, tmp_path):
    async def queued(engine):
        assert engine.submit(create())
        await engine.drain_events()

    observed, report, receipt, raw = await run_smoke(queued)
    assert MINT in observed.tokens
    assert report["launches"] == report["active_candidates"] == raw == 1
    counted = row(observed)
    assert counted["reconciled"] and counted["terminal"] == {"processed": 1}
    assert counted["persisted"] == 1
    assert counted["pending"] == counted["in_processing"] == 0
    assert observed._event_persisted is True
    assert receipt["accounting"]["events"]["create"] == counted
    baseline = RadarEngine(Settings(mode="OBSERVE"), tmp_path / "baseline.db", offline=True)
    try:
        await queued(baseline)
        assert row(baseline) == counted
        # Compare the same lifecycle phase: shutdown intentionally invalidates
        # feature continuity, including empty short-window classifications.
        await baseline.stop()
        left, right = observed.tokens[MINT], baseline.tokens[MINT]
        assert (left.state, left.features, left.scores, left.decision) == (
            right.state, right.features, right.scores, right.decision)
        assert observed.processed == baseline.processed == 1
        assert observed.paper.state == baseline.paper.state
        assert observed.approved_evidence is baseline.approved_evidence is None
    finally:
        await baseline.stop()


@pytest.mark.parametrize("rejection", ["duplicate_memory", "duplicate_launch", "stale"])
async def test_queued_create_rejections_preserve_counters(run_smoke, rejection):
    async def queued(engine):
        if rejection != "stale":
            engine.submit(create())
            await engine.drain_events()
        engine.submit(create(identity="create" if rejection == "duplicate_memory" else "second",
                             stamp=NOW - 21 if rejection == "stale" else NOW))
        await engine.drain_events()

    engine, report, receipt, raw = await run_smoke(queued)
    accepted = int(rejection != "stale")
    assert report["launches"] == raw == accepted
    counted = row(engine)
    expected = {rejection: 1, **({"processed": 1} if accepted else {})}
    assert counted["terminal"] == expected and counted["reconciled"]
    assert counted["persisted"] == accepted
    assert counted["pending"] == counted["in_processing"] == 0
    assert receipt["accounting"]["events"]["create"] == counted


async def test_direct_calls_and_trade_migration_rejection_counts(run_smoke):
    async def direct(engine):
        assert engine.process(create(), NOW) is True
        stale = MarketEvent(kind="trade", mint=MINT, event_id="stale", ts=NOW - 21,
                            source="Solana WSS", side="buy", volume=1, currency="SOL")
        assert engine.process(stale, NOW) is False
        assert engine.process(create(), NOW) is False
        assert engine.process(MarketEvent(kind="migration", mint=MINT, event_id="old-migration",
                                          ts=NOW - 21, source="Solana WSS"), NOW) is False

    engine, report, _, raw = await run_smoke(direct)
    assert report["launches"] == raw == 1
    assert report["trade_process_rejections"] == {"stale": 1, "other": 0}
    assert report["migration_process_rejections"] == {"stale": 1, "other": 0}
    # Direct calls never manufacture queue lifecycle counters.
    assert row(engine)["submitted"] == row(engine)["persisted"] == 0


async def test_original_exceptions_propagate_and_queued_failure_finishes(run_smoke, monkeypatch):
    failure = RuntimeError("synthetic processing failure")

    async def broken(engine):
        def fail(*args, **kwargs):
            raise failure

        monkeypatch.setattr(engine, "_process", fail)
        with pytest.raises(RuntimeError) as caught:
            engine.process(create(), NOW)
        assert caught.value is failure
        engine.submit(create())
        await engine.drain_events()  # Original engine catches/invalidates/account-finishes.

    engine, report, _, raw = await run_smoke(broken)
    assert report["launches"] == raw == 0
    assert row(engine)["terminal"] == {"exception": 1}
    assert row(engine)["reconciled"]
    assert row(engine)["pending"] == row(engine)["in_processing"] == 0


async def test_cancellation_accounts_detached_remainder(run_smoke, monkeypatch):
    async def cancel(engine):
        reached = asyncio.Event()
        facade = SimpleNamespace(**vars(asyncio))

        async def pause(seconds):
            assert seconds == 0
            reached.set()
            await asyncio.Event().wait()

        facade.sleep = pause
        monkeypatch.setattr(engine_module, "asyncio", facade)
        for i in range(6):
            engine.submit(create(identity=f"create-{i}", mint=str(Pubkey.from_bytes(bytes([i + 1]) * 32))))
        task = asyncio.create_task(engine.drain_events())
        await reached.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    engine, report, receipt, raw = await run_smoke(cancel)
    assert report["launches"] == raw == 5
    counted = row(engine)
    assert counted["reconciled"] and counted["terminal"] == {"processed": 5, "cancelled": 1}
    assert counted["persisted"] == 5
    assert counted["pending"] == counted["in_processing"] == 0
    assert receipt["accounting"]["events"]["create"] == counted
