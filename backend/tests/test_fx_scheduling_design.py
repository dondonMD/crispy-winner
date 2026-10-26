"""Design-only synthetic comparisons, not an implemented scheduler or historical counterfactual."""

from types import SimpleNamespace
from datetime import datetime, timezone
import httpx
import pytest

from backend.app.early_edge_quotes import WSOL, USDC
from backend.app.early_edge_runtime import UsdReference
from backend.app.early_edge import fx_value
from backend.app.early_edge_quotes import QuoteUnavailable

PRODUCTS = (WSOL, USDC)


def lru(needed, last, now):
    # Existing slice-before-attempt-interval ordering, including product order tie-break.
    ordered = sorted((q for q in PRODUCTS if q in needed), key=lambda q: last.get(q, 0))
    return ordered[0] if ordered and now - last.get(ordered[0], 0) >= 10 else None


def proposed(needed, last, now, fresh, missed, fair=False):
    """Toy candidate only: reuse fresh cache, then weight missing demand, optional fairness."""
    due = [q for q in PRODUCTS if q in needed and q not in fresh and now - last.get(q, 0) >= 10]
    if not due:
        return None
    if fair and any(missed.get(q, 0) >= 2 for q in due):
        return max(due, key=lambda q: (missed.get(q, 0), -last.get(q, 0)))
    return max(due, key=lambda q: (needed[q], -last.get(q, 0)))


def simulate(policy):
    last = {WSOL: 999, USDC: 950}
    requests, usable = [], 0
    missed = dict.fromkeys(PRODUCTS, 0)
    needed = {WSOL: 14, USDC: 1}
    # Thirty-one seconds between polls: every previous reference has expired.
    for now in (1030, 1061, 1092, 1123):
        if policy == "lru":
            selected = lru(needed, last, now)
        else:
            selected = proposed(needed, last, now, set(), missed, policy == "fair")
        if selected:
            requests.append((now, selected))
            last[selected] = now
            usable += needed[selected]  # Assumes immediate, valid provider publication; toy only.
        for q in PRODUCTS:
            missed[q] = 0 if q == selected else missed[q] + 1
    return requests, usable


def test_synthetic_budget_and_starvation_tradeoff():
    results = {p: simulate(p) for p in ("lru", "weighted", "fair")}
    assert {p: v for p, (_, v) in results.items()} == {"lru": 30, "weighted": 56, "fair": 43}
    for requests, _ in results.values():
        assert len(requests) == 4  # One per poll, no request-frequency increase.
        assert all(b[0] - a[0] >= 5 for a, b in zip(requests, requests[1:]))
    assert not any(q == USDC for _, q in results["weighted"][0])  # Disqualifying starvation risk.
    assert any(q == USDC for _, q in results["fair"][0])


def test_fresh_cache_reuse_and_attempt_cooldown():
    last = {WSOL: 1000, USDC: 1000}
    needed = {WSOL: 14, USDC: 1}
    assert proposed(needed, last, 1012, set(PRODUCTS), {}) is None
    assert lru(needed, last, 1012) == WSOL
    assert proposed(needed, last, 1005, set(), {}) is None
    assert lru(needed, last, 1005) is None


async def test_design_reference_lru_matches_actual_existing_adapter(monkeypatch):
    from backend.app import early_edge_runtime as runtime

    clock = [1030.0]
    monkeypatch.setattr(runtime, "time", SimpleNamespace(time=lambda: clock[0]))
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: pytest.fail("No network")))
    ref = UsdReference(client=client)
    ref.last_attempt = {WSOL: 999, USDC: 950}
    calls = []

    async def request(method, url, **kwargs):
        now = clock[0]
        product = WSOL if "coinbase" in url else USDC
        calls.append((now, product))
        if product == WSOL:
            return {"price": "100", "time": datetime.fromtimestamp(now, timezone.utc).isoformat()}
        return {"error": [], "result": {"USDCUSD": [["1", "1", str(now)]], "last": "ignored"}}

    ref.request = request
    try:
        for now in (1030, 1061, 1092, 1123):
            clock[0] = now
            await ref.refresh(set(PRODUCTS), max_products=1)
        assert calls == simulate("lru")[0]
    finally:
        await client.aclose()


@pytest.mark.parametrize("fault", ["stale", "future", "timeout_missing"])
def test_no_policy_can_make_bad_reference_fresh(fault):
    now = 1000
    reference = dict(
        source="Coinbase Exchange public ticker",
        product="SOL-USD",
        usd=100,
        published_at=now,
        acquired_at=now,
    )
    if fault == "stale":
        reference["published_at"] -= 21
    if fault == "future":
        reference["acquired_at"] += 1
    with pytest.raises(QuoteUnavailable):
        fx_value({} if fault == "timeout_missing" else {WSOL: reference}, WSOL, now)
