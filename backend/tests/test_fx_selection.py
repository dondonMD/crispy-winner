"""Frozen-policy synthetic validation; no external HTTP or real profitability evidence."""

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock
import json

import httpx
import pytest

from backend.app.fx_selection import FxSelection, VERSION
from backend.app.early_edge_quotes import WSOL, USDC, QuoteUnavailable
from backend.app.early_edge_runtime import UsdReference
from backend.app.early_prices import usd_mark
from backend.tests.test_early_prices import state, NOW
from backend.tests.test_price_diagnostics import diagnostics, receipt


def ref(q, now):
    return dict(
        source="Coinbase Exchange public ticker" if q == WSOL else "Kraken public recent trades",
        product="SOL-USD" if q == WSOL else "USDCUSD",
        usd=100 if q == WSOL else 1,
        published_at=now,
        acquired_at=now,
    )


@pytest.mark.parametrize("sol", range(1, 25))
def test_fairness_all_demands_and_fixed_request_budget(sol):
    policy = FxSelection()
    last = {}
    missed = {WSOL: 0, USDC: 0}
    requested = []
    for now in range(1000, 1500, 31):
        selected = policy.select({WSOL: sol, USDC: 25 - sol}, {}, last, now)
        assert selected in (WSOL, USDC)
        requested.append((now, selected))
        last[selected] = now
        for q in missed:
            missed[q] = 0 if q == selected else missed[q] + 1
            assert missed[q] <= 2 and policy.missed[q] == missed[q]
    assert len(requested) == len(range(1000, 1500, 31))
    assert all(b[0] - a[0] >= 5 for a, b in zip(requested, requested[1:]))
    assert len(json.dumps(policy.snapshot())) < 2000


def test_fresh_cache_exact_validity_and_deterministic_ties():
    p = FxSelection()
    assert p.select({WSOL: 14, USDC: 1}, {WSOL: ref(WSOL, 1000), USDC: ref(USDC, 1000)}, {}, 1000) is None
    assert p.select({WSOL: 14, USDC: 1}, {WSOL: ref(WSOL, 1000)}, {}, 1000) == USDC
    assert p.select({WSOL: 1, USDC: 1}, {}, {}, 1031) == WSOL
    assert p.select({WSOL: 1, USDC: 1}, {}, {WSOL: 1020, USDC: 1010}, 1062) == USDC


@pytest.mark.parametrize("q", [WSOL, USDC])
def test_single_product_and_stale_reference(q):
    p = FxSelection()
    assert p.select({q: 1}, {q: ref(q, 1000)}, {}, 1020) is None
    assert p.select({q: 1}, {q: ref(q, 1000)}, {}, 1020.01) == q
    assert p.missed == {WSOL: 0, USDC: 0}


def test_only_eligible_mixed_rounds_count_and_freshness_resets_need():
    p = FxSelection()
    demand = {WSOL: 24, USDC: 1}
    assert p.select(demand, {}, {}, 1000) == WSOL
    assert p.missed[USDC] == 1
    assert p.select(demand, {}, {}, 1031, cooldown_until=1040) is None
    assert p.missed[USDC] == 1
    assert p.select(demand, {}, {}, 1062, limiter_wait=2) is None
    assert p.missed[USDC] == 1
    assert p.select(demand, {}, {WSOL: 1085, USDC: 1085}, 1090) is None
    assert p.missed[USDC] == 1
    assert p.select(demand, {}, {}, 1120) == WSOL
    assert p.missed[USDC] == 2
    assert p.select(demand, {}, {}, 1151) == USDC
    assert p.missed[USDC] == 0
    p.select({WSOL: 1}, {}, {}, 1182)
    assert p.missed[USDC] == 0


def test_clock_regression_and_future_reference_never_fresh():
    p = FxSelection()
    p.select({WSOL: 1}, {}, {}, 1000)
    assert p.select({WSOL: 1}, {}, {}, 999) is None
    assert p.select({WSOL: 1}, {}, {}, float("nan")) is None
    assert p.clock_rejections == 2
    assert p.select({WSOL: 1}, {WSOL: ref(WSOL, 1032)}, {}, 1031) == WSOL


@pytest.mark.parametrize("bad", [{"other": 1}, {WSOL: 0}, {WSOL: True}, {WSOL: 26}, {WSOL: 25, USDC: 1}])
def test_bad_demand_refused_before_selection(bad):
    with pytest.raises(ValueError):
        FxSelection().select(bad, {}, {}, 1000)


@pytest.mark.parametrize(
    "outcome", ["fresh", "stale", "negative", "nan", "http_error", "cancel", "timeout", "rate_limit"]
)
async def test_real_adapter_outcomes_durable_and_bounded(tmp_path, monkeypatch, outcome):
    from backend.app import early_edge_runtime as runtime
    import time

    clock = [NOW]
    monkeypatch.setattr(runtime, "time", NS(time=lambda: clock[0], monotonic=time.monotonic))
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: pytest.fail("No live HTTP")))
    db, diag = diagnostics(tmp_path)
    u = UsdReference(client=client, diagnostics=diag)
    calls = []

    async def request(method, url, **kwargs):
        calls.append(url)
        u.health["requests"] += 1
        if outcome == "cancel":
            raise asyncio.CancelledError()
        if outcome == "timeout":
            await asyncio.Event().wait()
        if outcome in ("http_error", "rate_limit"):
            if outcome == "rate_limit":
                u.health["rate_limited_until"] = NOW + 60
            raise httpx.HTTPStatusError(
                "synthetic",
                request=httpx.Request("GET", "https://example.invalid"),
                response=httpx.Response(429 if outcome == "rate_limit" else 500),
            )
        return dict(
            price="nan" if outcome == "nan" else "-1" if outcome == "negative" else "100",
            time=datetime.fromtimestamp(NOW - 21 if outcome == "stale" else NOW, timezone.utc).isoformat(),
        )

    u.request = request
    try:
        if outcome == "cancel":
            with pytest.raises(asyncio.CancelledError):
                await u.refresh({WSOL}, max_products=1, state_counts={WSOL: 1})
        elif outcome == "timeout":
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(u.refresh({WSOL}, max_products=1, state_counts={WSOL: 1}), 0.01)
        else:
            await u.refresh({WSOL}, max_products=1, state_counts={WSOL: 1})
        assert len(calls) == 1
        assert u.last_attempt[WSOL] == NOW
        expected = (
            "usable"
            if outcome == "fresh"
            else "stale_rejected"
            if outcome == "stale"
            else "cancelled"
            if outcome in ("cancel", "timeout")
            else "request_failed"
            if outcome in ("http_error", "rate_limit")
            else "validation_failed"
        )
        saved = receipt(db, diag)
        assert saved["fx"]["SOL-USD"]["counts"][expected] == 1
        assert saved["fx_selection"]["version"] == VERSION
        assert saved["fx_selection"]["per_product"]["SOL-USD"]["selected"] == 1
        assert bool(u.cache) == (outcome == "fresh")
        clock[0] += 5
        await u.refresh({WSOL}, max_products=1, state_counts={WSOL: 1})
        assert len(calls) == 1  # Fresh reuse, interval or cooldown; no extra call.
    finally:
        await client.aclose()
        db.engine.dispose()


def test_cached_fx_expiring_during_construction_remains_unavailable():
    r = ref(WSOL, NOW)
    assert FxSelection().select({WSOL: 1}, {WSOL: r}, {}, NOW + 19.9) is None
    with pytest.raises(QuoteUnavailable, match="USD_STALE"):
        usd_mark(state(NOW + 20), {WSOL: r}, NOW + 20.1)


async def test_actual_demand_sequence_has_same_budget_as_legacy_and_no_starvation(monkeypatch):
    from backend.app import early_edge_runtime as runtime
    import time

    clock = [1000]
    monkeypatch.setattr(runtime, "time", NS(time=lambda: clock[0], monotonic=time.monotonic))
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: pytest.fail("No live HTTP")))
    u = UsdReference(client=client)
    calls = []

    async def request(method, url, **kwargs):
        selected = WSOL if "coinbase" in url else USDC
        calls.append(selected)
        now = clock[0]
        if selected == WSOL:
            return dict(price="100", time=datetime.fromtimestamp(now, timezone.utc).isoformat())
        return {"error": [], "result": {"USDCUSD": [["1", "1", str(now)]], "last": "ignored"}}

    u.request = request
    try:
        for now in (1000, 1031, 1062, 1093):
            clock[0] = now
            await u.refresh({WSOL, USDC}, max_products=1, state_counts={WSOL: 14, USDC: 1})
        assert calls == [WSOL, WSOL, USDC, WSOL]
        assert len(calls) == 4  # Same permitted four one-product rounds as legacy.
        assert set(u.cache) == {WSOL, USDC}
    finally:
        await client.aclose()


async def test_actual_http_rate_limit_prevents_extra_selection(tmp_path):
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                429, headers={"Retry-After": "60"}, json={"error": "synthetic rate limit"}
            )
        )
    )
    db, diag = diagnostics(tmp_path)
    u = UsdReference(client=client, diagnostics=diag)
    try:
        await u.refresh({WSOL}, max_products=1, state_counts={WSOL: 1})
        assert u.health["requests"] == u.health["rate_limits"] == 1
        assert not u.cache
        await u.refresh({WSOL, USDC}, max_products=1, state_counts={WSOL: 1, USDC: 1})
        assert u.health["requests"] == 1
        assert u.selection.mixed_rounds == 0
        assert u.selection.missed == {WSOL: 0, USDC: 0}
        assert u.selection.status[USDC] == "COOLDOWN_SKIP"
        diag.flush()
        assert receipt(db, diag)["fx"]["SOL-USD"]["counts"]["request_failed"] == 1
    finally:
        await client.aclose()
        db.engine.dispose()


@pytest.mark.parametrize("quote", [WSOL, USDC])
async def test_engine_new_policy_matches_legacy_mark_and_decisions(tmp_path, monkeypatch, quote):
    from backend.app import engine as engine_module, early_edge_runtime as runtime
    from backend.app.engine import RadarEngine
    from backend.app.config import Settings
    from backend.app.domain import MarketEvent
    from backend.app.early_prices import reserve_state
    from backend.tests.test_reserve_rejection_observability import curve_for
    from backend.tests.test_early_prices import MINT, ADDRESS, inputs
    import time

    clock = NS(time=lambda: NOW, monotonic=time.monotonic, perf_counter=time.perf_counter)
    monkeypatch.setattr(engine_module, "time", clock)
    monkeypatch.setattr(runtime, "time", clock)
    engines = [RadarEngine(Settings(mode="OBSERVE"), tmp_path / f"policy-{i}.db") for i in range(2)]
    clients = []
    try:
        for i, e in enumerate(engines):
            e.process(
                MarketEvent(kind="create", mint=MINT, ts=NOW, source="SYNTHETIC", event_id="create"), NOW
            )
            _, mint, quotes = inputs()
            s = reserve_state(MINT, ADDRESS, curve_for(0, quote), mint, quotes, 100, NOW - 0.1, NOW)
            e.rpc.curve_progress_batch = AsyncMock(
                return_value={MINT: {"curve_progress": 5, "data_quality": "VERIFIED", "price_state": s}}
            )
            client = httpx.AsyncClient(
                transport=httpx.MockTransport(lambda request: pytest.fail("No live HTTP"))
            )
            clients.append(client)
            u = UsdReference(client=client, diagnostics=e.price_research.diagnostics)
            u.request = AsyncMock(
                return_value={"price": "100", "time": datetime.fromtimestamp(NOW, timezone.utc).isoformat()}
                if quote == WSOL
                else {"error": [], "result": {"USDCUSD": [["1", "1", str(NOW)]], "last": "ignored"}}
            )
            if i == 0:
                original = u.refresh

                async def legacy(mints=None, max_products=2, **kwargs):
                    return await original(mints, max_products=max_products)

                u.refresh = legacy
            e.price_reference = u
            await e.poll_curves([e.tokens[MINT]], "hot", 25)
            await e.drain_events()
            e.intelligence.refresh(NOW, force=True)
            assert len(e.db.rows("v21_price_mark", MINT, e.session)) == 1
            assert e.approved_evidence is None and not e.paper.state["positions"]
        a, b = engines
        assert a.price_research.marks[MINT] == b.price_research.marks[MINT]
        assert a.intelligence.results == b.intelligence.results
        assert a.tokens[MINT].decision == b.tokens[MINT].decision
        assert a.tokens[MINT].features == b.tokens[MINT].features
        assert a.accounting.terminal == b.accounting.terminal
        assert a.accounting.persisted == b.accounting.persisted
        assert b.price_research.diagnostics.summary()["fx_selection"]["version"] == VERSION
    finally:
        for e in engines:
            await e.stop()
        for c in clients:
            await c.aclose()


async def test_occupied_provider_slots_do_not_spend_fairness_or_request_budget():
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: pytest.fail("No HTTP")))
    u = UsdReference(client=client)
    await u.limiter.semaphore.acquire()
    await u.limiter.semaphore.acquire()
    try:
        await u.refresh({WSOL, USDC}, max_products=1, state_counts={WSOL: 14, USDC: 1})
        assert u.health["requests"] == 0 and u.selection.mixed_rounds == 0
        assert u.selection.missed == {WSOL: 0, USDC: 0}
        assert set(u.selection.status.values()) == {"LIMITER_BUDGET_SKIP"}
    finally:
        u.limiter.semaphore.release()
        u.limiter.semaphore.release()
        await client.aclose()
