import json
import time
from unittest.mock import AsyncMock

import httpx
import pytest
from solders.pubkey import Pubkey

from backend.app.config import Settings
from backend.app.domain import MarketEvent, State
from backend.app.engine import RadarEngine
from backend.app.providers import SolanaProvider, PumpPortalProvider
from backend.tests.test_onchain import encoded
from backend.app.providers import PUMP_PROGRAM
import hashlib
import struct


def accounts(complete=False):
    real = 0 if complete else 12
    curve = (
        hashlib.sha256(b"account:BondingCurve").digest()[:8]
        + struct.pack("<QQQQQ", real + 280, 100, real, 80, 1000)
        + bytes([complete])
    )
    global_raw = (
        hashlib.sha256(b"account:Global").digest()[:8] + b"\0" * 65 + struct.pack("<QQQQ", 400, 30, 120, 1000)
    )
    return encoded(curve, PUMP_PROGRAM), encoded(global_raw, PUMP_PROGRAM)


@pytest.mark.parametrize("complete", [False, True])
async def test_batch_cache_unknown_and_completion(complete):
    calls = []
    curve, global_account = accounts(complete)

    def handle(request):
        body = json.loads(request.content)
        calls.append(body)
        count = len(body["params"][0])
        values = [curve, None] + ([global_account] if count == 3 else [])
        return httpx.Response(200, json={"result": {"value": values}})

    rpc = SolanaProvider(httpx.AsyncClient(transport=httpx.MockTransport(handle)))
    mints = [str(Pubkey.new_unique()) for _ in range(3)]
    result = await rpc.curve_progress_batch(mints, 2)
    assert len(result) == 2
    assert result[mints[0]]["curve_progress"] == (100 if complete else 90)
    assert result[mints[1]]["curve_progress"] is None
    await rpc.curve_progress_batch(mints, 2)
    assert [len(c["params"][0]) for c in calls] == [3, 2]
    assert all(c["method"] == "getMultipleAccounts" for c in calls)
    assert RadarEngine.provider_health(rpc.health)["status"] == "CURRENT"
    await rpc.close()


@pytest.mark.parametrize("progress", [90, 100])
async def test_free_observe_funnel_bounded_and_conservative(tmp_path, progress):
    e = RadarEngine(Settings(max_candidates=30, max_deep=5, curve_batch_size=5), tmp_path / "o.db")
    now = time.time()
    e.last_background_batch = now  # Isolate hot-tier regression within one background interval.
    for i in range(30):
        mint = str(Pubkey.new_unique())
        e.process(MarketEvent(mint=mint, ts=now, source="PumpPortal", kind="create", event_id=str(i)))

    async def curves(mints, size):
        return {m: {"curve_progress": progress, "data_quality": "VERIFIED"} for m in mints}

    e.rpc.curve_progress_batch = AsyncMock(side_effect=curves)
    e.rpc.inspect = AsyncMock(return_value={"data_quality": "UNKNOWN"})
    e.dex.markets = AsyncMock(return_value=[])
    before = {m: dict(t.scores) for m, t in e.tokens.items()}
    await e.enrich_once()
    assert e.rpc.inspect.await_count == 0
    selected = e.rpc.curve_progress_batch.call_args.args[0]
    assert len(selected) == 5
    assert all(e.tokens[m].features["180"]["raw_unique_buyers"] == 0 for m in selected)
    for event in e.queue.drain():
        e.process(event)
    for m in selected:
        t = e.tokens[m]
        assert t.curve_progress == progress and t.state == State.MATURING
        assert t.scores["momentum"] == before[m]["momentum"]
        assert t.scores["maturity"] == before[m]["maturity"]
        e.analyse(t, time.time())
        assert t.state == State.NEAR_GRADUATION and t.graduation is None
        assert t.decision["decision"] == "WAIT"
        assert any("Trade stream unavailable" in r for r in t.decision["reasons"])
        view = e.token_view(t, now)
        assert view["features"]["estimated_independent_buyers"] is None
        assert view["features"]["flow_ratio"] is None
    await e.enrich_once()
    await e.enrich_once()
    assert e.rpc.inspect.await_count == 1
    assert e.rpc.inspect.call_args.args[0] in selected
    assert all(call.args[0] == [] for call in e.dex.markets.call_args_list)
    mint = selected[0]
    e.process(
        MarketEvent(mint=mint, ts=time.time(), source="PumpPortal", kind="migration", event_id="migration")
    )
    assert e.tokens[mint].graduation is not None
    assert e.tokens[mint].state == State.POST_GRAD_OBSERVATION
    await e.stop()


async def test_failed_refresh_and_health(tmp_path):
    e = RadarEngine(Settings(), tmp_path / "o.db")
    assert e.snapshot()["health"]["providers"]["Solana RPC"]["status"] == "NOT USED YET"
    e.rpc.health.update(attempted=True, connected=False, errors=1)
    assert e.snapshot()["health"]["providers"]["Solana RPC"]["status"] == "DEGRADED"
    e.rpc.health.update(connected=True, last_success=time.time())
    assert e.snapshot()["health"]["providers"]["Solana RPC"]["status"] == "CURRENT"
    e.rpc.health["rate_limited_until"] = time.time() + 10
    assert e.snapshot()["health"]["providers"]["Solana RPC"]["status"] == "RATE LIMITED"
    e.rpc.health["rate_limited_until"] = 0
    mint = str(Pubkey.new_unique())
    now = time.time()
    e.process(MarketEvent(mint=mint, ts=now, source="PumpPortal", kind="create", event_id="new"))
    t = e.tokens[mint]
    t.curve_progress, t.last_curve = 90, now
    t.security = {"data_quality": "VERIFIED", "last_updated": now}
    e.rpc.curve_progress_batch = AsyncMock(side_effect=RuntimeError())
    e.rpc.inspect = AsyncMock(side_effect=RuntimeError())
    e.dex.markets = AsyncMock(return_value=[])
    await e.enrich_once()
    for event in e.queue.drain():
        e.process(event)
    assert t.curve_progress is None
    assert t.security["data_quality"] == "UNKNOWN"
    assert t.decision["decision"] == "WAIT"
    await e.stop()


def test_launch_fields_preserved_without_price_inference():
    p = PumpPortalProvider(Settings(), lambda e: None, lambda: [])
    event = p.normalize(
        {
            "txType": "create",
            "mint": str(Pubkey.new_unique()),
            "marketCapSol": 20,
            "vSolInBondingCurve": 30,
            "initialBuy": 1,
        }
    )
    assert event.evidence["launch_metadata"]["marketCapSol"] == 20
    assert event.price is None and event.market_cap is None and event.curve_progress is None


def test_low_progress_does_not_lock_out_new_auditions(tmp_path):
    e = RadarEngine(Settings(max_candidates=3, max_deep=2), tmp_path / "o.db")
    now = time.time()
    mints = [str(Pubkey.new_unique()) for _ in range(4)]
    for i, mint in enumerate(mints[:3]):
        e.process(MarketEvent(mint=mint, ts=now + i, source="PumpPortal", kind="create", event_id=mint))
        e.tokens[mint].curve_progress = 0.1
    e.process(MarketEvent(mint=mints[3], ts=now + 3, source="PumpPortal", kind="create", event_id=mints[3]))
    assert mints[3] in e.tokens and mints[3] in e.deep_mints()
    assert len(e.tokens) == 3 and len(e.deep_mints()) == 2
    e.db.engine.dispose()
