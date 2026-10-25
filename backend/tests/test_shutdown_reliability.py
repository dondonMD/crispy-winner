"""Offline shutdown regressions: no sockets, providers or historical databases."""
import asyncio
import json
from types import SimpleNamespace

import pytest
from uvicorn import Config, Server

from backend.app import main
from backend.app.config import Settings
from backend.app.db import Database, EvidenceRun
from backend.app.engine import RadarEngine


def test_launcher_bounds_http_drain(monkeypatch):
    import uvicorn
    captured = {}
    monkeypatch.setattr(uvicorn, 'run', lambda *args, **kwargs: captured.update(kwargs))
    main.run_server()
    assert captured['timeout_graceful_shutdown'] == 5


async def test_persistent_response_is_cancelled_before_lifespan_shutdown():
    """Uvicorn's real shutdown path must reach lifespan with a persistent response."""
    server = Server(Config(main.app, timeout_graceful_shutdown=0.01))
    server.servers = []
    cancelled = asyncio.Event()
    finished = asyncio.Event()

    async def response():
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    task = asyncio.create_task(response())
    server.server_state.tasks.add(task)
    task.add_done_callback(server.server_state.tasks.discard)
    connection = SimpleNamespace(shutdown=lambda: None)
    # A persistent HTTP connection remains until its response task is cancelled.
    server.server_state.connections = [connection]
    task.add_done_callback(lambda _: server.server_state.connections.clear())

    async def lifespan_shutdown():
        await cancelled.wait()
        await asyncio.gather(task, return_exceptions=True)
        finished.set()

    server.lifespan = SimpleNamespace(shutdown=lifespan_shutdown)
    await asyncio.wait_for(server.shutdown(), 1)
    assert finished.is_set() and task.cancelled()


async def test_provider_close_failure_still_records_and_disposes(tmp_path, monkeypatch):
    path = tmp_path / 'shutdown.db'
    engine = RadarEngine(Settings(mode='OBSERVE'), path, offline=True)
    closed = []
    disposed = []
    dispose = engine.db.engine.dispose

    async def rpc_close():
        closed.append('rpc')
        await engine.rpc.client.aclose()
        raise OSError('synthetic close error')

    async def dex_close():
        closed.append('dex')
        await engine.dex.client.aclose()

    def db_dispose():
        disposed.append(True)
        dispose()

    monkeypatch.setattr(engine.rpc, 'close', rpc_close)
    monkeypatch.setattr(engine.dex, 'close', dex_close)
    monkeypatch.setattr(engine.db.engine, 'dispose', db_dispose)
    with pytest.raises(OSError, match='synthetic close error'):
        await engine.stop()
    assert closed == ['rpc', 'dex'] and disposed
    restored = Database(path)
    with restored.sessions() as sql:
        receipt = json.loads(sql.get(EvidenceRun, engine.session).payload)
    restored.engine.dispose()
    assert receipt['status'] == 'STOPPED'
    assert receipt['provider_close_failures'] == ['OSError']


async def test_default_http_drain_can_block_lifespan():
    """Reproduce the pre-fix wait stage without opening a listening socket."""
    server = Server(Config(main.app))
    server.servers = []
    server.server_state.connections = [SimpleNamespace(shutdown=lambda: None)]
    reached = []

    async def lifespan_shutdown():
        reached.append(True)

    server.lifespan = SimpleNamespace(shutdown=lifespan_shutdown)
    assert server.config.timeout_graceful_shutdown is None
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(server.shutdown(), 0.15)
    assert not reached
    server.server_state.connections.clear()


async def test_cancel_blocked_provider_then_account_queue_and_cold_restart(tmp_path):
    import time
    from backend.app.domain import MarketEvent

    path = tmp_path / 'cancel.db'
    engine = RadarEngine(Settings(mode='OBSERVE'), path, offline=True)
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def blocked_request():
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    worker = asyncio.create_task(blocked_request(), name='synthetic-blocked-provider')
    engine.tasks.append(worker)
    await started.wait()
    for i in range(3):
        engine.submit(MarketEvent(event_id=f'synthetic:{i}', mint='synthetic', ts=time.time(),
                                  source='SYNTHETIC', kind='trade'))
    await asyncio.wait_for(engine.stop(), 2)
    assert worker.cancelled() and cancelled.is_set()
    assert all(task.done() for task in engine.tasks)
    assert not engine.queue.heap
    restored = Database(path)
    with restored.sessions() as sql:
        receipt = json.loads(sql.get(EvidenceRun, engine.session).payload)
    assert receipt['checkpoint_complete']
    assert receipt['provider_close_failures'] == []
    trade = receipt['accounting']['events']['trade']
    assert trade['terminal'] == {'shutdown_unprocessed': 3} and trade['reconciled']
    with restored.engine.connect() as sql:
        assert sql.exec_driver_sql('PRAGMA quick_check').scalar() == 'ok'
    restored.engine.dispose()
