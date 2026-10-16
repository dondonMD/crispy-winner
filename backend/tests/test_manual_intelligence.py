import json
from copy import deepcopy
from unittest.mock import AsyncMock

import httpx
import pytest
from pydantic import ValidationError

from backend.app.config import Settings
from backend.app.engine import RadarEngine
from backend.app.main import create_app
from backend.app.manual import (
    CashInput,
    MarketInput,
    OpenPositionInput,
    ClosePositionInput,
    ManualJournal,
    manual_economics,
)
from backend.app.opportunity import opportunity_view
from backend.app.exit_intelligence import exit_view
from backend.app.intelligence_demo import examples
from backend.tests.test_opportunity import candidate, NOW


@pytest.fixture
async def engine(tmp_path):
    e = RadarEngine(Settings(), tmp_path / "manual.db")
    token = candidate()
    e.tokens[token.mint] = token
    yield e, token
    await e.stop()


@pytest.mark.parametrize("bad", [-1, float("nan"), float("inf"), True])
def test_reject_bad_numbers_and_mint(bad):
    with pytest.raises(ValidationError):
        CashInput(cash_usd=bad)
    with pytest.raises(ValidationError):
        MarketInput(mint=candidate().mint, price_usd=bad)
    with pytest.raises(ValidationError):
        MarketInput(mint="not a mint", price_usd=1)


def test_manual_observation_persists_is_labelled_and_expires(engine):
    e, t = engine
    j = e.intelligence.journal
    before = deepcopy(t)
    j.observe_market(MarketInput(mint=t.mint, price_usd=1, market_cap_usd=10000), NOW)
    r = j.market_view(t.mint, NOW + 42)
    assert r["source"] == "MANUAL USER OBSERVATION" and not r["verified"]
    assert r["status"] == "CURRENT" and r["age_seconds"] == 42
    assert j.market_view(t.mint, NOW + 121)["status"] == "STALE"
    restored = ManualJournal(e.db, e.settings, e.intelligence.cfg)
    assert restored.market_view(t.mint, NOW + 42) == r
    assert t == before
    assert opportunity_view(t, e.settings, NOW).market_context["price_usd"] is None


def test_manual_economics_unknown_liquidity_is_not_zero_or_viable(engine):
    e, t = engine
    r = manual_economics(e.settings, None, 4, t, NOW)
    assert r["costs"] is None and r["break_even_pct"] is None
    assert r["economically_viable"] is False and r["account_fraction_pct"] is None
    t.liquidity, t.last_liquidity = 50000, NOW
    r = manual_economics(e.settings, 20, 4, t, NOW)
    assert r["costs"]["round_trip_cost_usd"] > 0 and r["break_even_pct"] > 0
    assert r["remaining_cash_after_entry_cost_usd"] < 16
    assert r["affordable"] is True and not r["economically_viable"]
    assert manual_economics(e.settings, 0, 4, t, NOW)["affordable"] is False


def open_position(e, t, now=NOW, **kwargs):
    value = OpenPositionInput(mint=t.mint, amount_usd=4, price_usd=1, confirm=True, **kwargs)
    return e.intelligence.open_position(value, now)


def test_manual_position_reload_mark_peak_close_without_core_side_effects(engine):
    e, t = engine
    before = deepcopy(e.paper.state), deepcopy(t.decision), deepcopy(e.rpc.health), e.approved_evidence
    p = open_position(e, t)
    identity = p["position_id"]
    assert p["exit"]["action"] == "DATA_STALE"
    j = e.intelligence.journal
    j.observe_market(MarketInput(mint=t.mint, price_usd=1.5), NOW + 10)
    e.intelligence.refresh_positions(NOW + 10)
    j.observe_market(MarketInput(mint=t.mint, price_usd=1.2), NOW + 20)
    e.intelligence.refresh_positions(NOW + 20)
    r = e.intelligence.exit_results[identity]["exit"]
    assert r["gross_change_pct"] == pytest.approx(20)
    assert r["peak_mark"] == 1.5 and r["drawdown_pct"] == pytest.approx(20)
    assert r["estimated_net_pnl_usd"] is None
    restored = ManualJournal(e.db, e.settings, e.intelligence.cfg)
    assert restored.positions[identity]["peaks"] == j.positions[identity]["peaks"]
    j.close(identity, ClosePositionInput(confirm=True), NOW + 30)
    assert not j.positions and j.closed()[0]["status"] == "CLOSED"
    assert e.db.rows("manual_position_close")
    assert before == (e.paper.state, t.decision, e.rpc.health, e.approved_evidence)


def test_manual_limits_confirmation_backdating_and_source_peaks(engine):
    e, t = engine
    with pytest.raises(ValueError):
        e.intelligence.open_position(
            OpenPositionInput(mint=t.mint, amount_usd=4, price_usd=1, confirm=False), NOW
        )
    with pytest.raises(ValueError):
        open_position(e, t, opened_at=NOW + 1)
    p = open_position(e, t, opened_at=NOW - 30)
    assert p["thesis"]["snapshot_kind"].startswith("UNAVAILABLE")
    for _ in range(2):
        open_position(e, t)
    with pytest.raises(ValueError):
        open_position(e, t)
    with pytest.raises(ValueError):
        e.intelligence.journal.close(p["position_id"], ClosePositionInput(confirm=False), NOW)


def test_exit_states_and_profit_is_not_an_exit_target(engine):
    e, t = engine
    t.liquidity, t.last_liquidity = 50000, NOW
    p = open_position(e, t)
    position = e.intelligence.journal.positions[p["position_id"]]
    cfg = e.intelligence.cfg
    projection = opportunity_view(t, e.settings, NOW)
    key = "MANUAL USER OBSERVATION:price_usd"

    def result(value, peak):
        position["marks"] = {
            key: {
                "value": value,
                "metric": "price_usd",
                "source": "MANUAL USER OBSERVATION",
                "observed_at": NOW,
            }
        }
        position["peaks"] = {key: peak}
        return exit_view(position, t, projection, e.settings, cfg, NOW)

    r = result(1.5, 1.5)
    assert r.action == "MONITOR"  # Missing flow is not bearish or falsely healthy.
    assert r.estimated_net_pnl_usd > 0
    assert result(1.5, 1.7).action == "PROTECT_PROFIT"
    assert result(0.7, 1.2).action == "EXIT_RISK"
    t.features["180"]["creator_sell_volume"] = 1
    assert result(1.1, 1.1).action == "THESIS_INVALIDATED"
    t.features["180"].clear()
    t.security["hard_failures"] = ["Hard failure appeared"]
    assert result(1, 1).action == "THESIS_INVALIDATED"


def test_market_cap_proxy_is_not_pnl_and_missing_mark_stale(engine):
    e, t = engine
    p = e.intelligence.open_position(
        OpenPositionInput(mint=t.mint, amount_usd=4, market_cap_usd=10000, confirm=True), NOW
    )
    j = e.intelligence.journal
    j.observe_market(MarketInput(mint=t.mint, market_cap_usd=15000), NOW + 10)
    e.intelligence.refresh_positions(NOW + 10)
    r = e.intelligence.exit_results[p["position_id"]]["exit"]
    assert r["market_cap_change_pct"] == 50 and r["gross_change_pct"] is None
    assert r["estimated_net_pnl_usd"] is None
    e.intelligence.refresh_positions(NOW + 200)
    assert e.intelligence.exit_results[p["position_id"]]["exit"]["action"] == "DATA_STALE"


def test_demo_workflow_examples_are_isolated_and_exact(engine):
    e, t = engine
    before = deepcopy(e.paper.state), len(e.db.rows("opportunity_signal"))
    assert examples(e.settings, e.intelligence.cfg, NOW) == {"opportunities": [], "positions": []}
    sample = examples(Settings(mode="DEMO"), e.intelligence.cfg, NOW)
    assert [o["action"] for o in sample["opportunities"]] == [
        "EARLY_OPPORTUNITY",
        "DEVELOPING",
        "PULLBACK_WATCH",
        "TOO_EXTENDED",
        "AVOID",
    ]
    assert [p["exit"]["action"] for p in sample["positions"]] == [
        "HEALTHY",
        "PROTECT_PROFIT",
        "EXIT_RISK",
        "THESIS_INVALIDATED",
    ]
    assert before == (e.paper.state, len(e.db.rows("opportunity_signal")))


async def test_api_manual_context_journal_and_origin_validation(tmp_path, monkeypatch):
    monkeypatch.setattr(RadarEngine, "start", AsyncMock())
    app = create_app(Settings(), tmp_path / "api.db")
    async with app.router.lifespan_context(app):
        e = app.state.engine
        t = candidate()
        e.tokens[t.mint] = t
        e.intelligence.refresh(NOW, force=True)
        before = deepcopy(t.decision), deepcopy(e.paper.state), deepcopy(e.rpc.health)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://testserver"
        ) as client:
            assert (await client.get("/api/opportunities")).status_code == 200
            assert (await client.get(f"/api/opportunities/{t.mint}")).status_code == 200
            assert (await client.post("/api/manual-account", json={"cash_usd": 19.25})).status_code == 200
            assert (
                await client.post(
                    "/api/manual-market-context", json={"mint": t.mint, "market_cap_usd": 10000}
                )
            ).json()["verified"] is False
            opened = (
                await client.post(
                    "/api/manual-positions",
                    json={"mint": t.mint, "amount_usd": 4, "price_usd": 1, "confirm": True},
                )
            ).json()
            identity = opened["position_id"]
            assert (
                await client.post(
                    f"/api/manual-positions/{identity}/mark", json={"mint": t.mint, "price_usd": 1.2}
                )
            ).status_code == 200
            assert (
                await client.post(f"/api/manual-positions/{identity}/close", json={"confirm": True})
            ).status_code == 200
            assert len((await client.get("/api/manual-positions")).json()["closed"]) == 1
            for payload in [
                {"cash_usd": -1},
                {"cash_usd": "inf"},
                {"cash_usd": 2, "private_key": "forbidden"},
            ]:
                assert (await client.post("/api/manual-account", json=payload)).status_code == 422
            assert (
                await client.post(
                    "/api/manual-account",
                    content='{"cash_usd":NaN}',
                    headers={"content-type": "application/json"},
                )
            ).status_code == 422
            assert (
                await client.post(
                    "/api/manual-account", json={"cash_usd": 1}, headers={"origin": "https://evil.example"}
                )
            ).status_code == 403
            assert (await client.post("/api/manual-account", content="cash_usd=1")).status_code == 415
            assert (
                await client.post(
                    "/api/manual-account",
                    content=json.dumps({"cash_usd": 1}) + " " * 17000,
                    headers={"content-type": "application/json"},
                )
            ).status_code == 413
            assert (
                await client.post("/api/manual-market-context", json={"mint": "bad", "price_usd": 1})
            ).status_code == 422
            assert before == (t.decision, e.paper.state, e.rpc.health)


def test_current_migration_can_replace_expired_pregrad_curve_for_exit(engine):
    e, t = engine
    p = open_position(e, t)
    t.graduation = NOW
    t.liquidity, t.last_liquidity = 50000, NOW + 200
    t.security["last_updated"] = NOW + 200
    e.intelligence.journal.observe_market(MarketInput(mint=t.mint, price_usd=1.1), NOW + 200)
    e.intelligence.refresh_positions(NOW + 200)
    assert e.intelligence.exit_results[p["position_id"]]["exit"]["action"] == "MONITOR"


def test_liquidity_deterioration_and_stale_security_are_not_reassuring(engine):
    e, t = engine
    t.liquidity, t.last_liquidity = 100000, NOW
    p = open_position(e, t)
    e.intelligence.journal.observe_market(MarketInput(mint=t.mint, price_usd=1.1), NOW + 10)
    t.liquidity, t.last_liquidity = 40000, NOW + 10
    e.intelligence.refresh_positions(NOW + 10)
    assert e.intelligence.exit_results[p["position_id"]]["exit"]["action"] == "EXIT_RISK"
    t.security["data_quality"] = "UNKNOWN"
    e.intelligence.refresh_positions(NOW + 10)
    assert e.intelligence.exit_results[p["position_id"]]["exit"]["action"] == "DATA_STALE"
