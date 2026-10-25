"""Recorded external fills only; offline journal, no wallet or provider calls."""

from copy import deepcopy

import httpx
import pytest
from pydantic import ValidationError

from backend.app.config import Settings
from backend.app.engine import RadarEngine
from backend.app.main import create_app
from backend.app.manual import OpenPositionInput, MarketInput, ManualJournal, ClosePositionInput
from backend.tests.test_opportunity import candidate, NOW


@pytest.fixture
async def engine(tmp_path):
    e = RadarEngine(Settings(mode="OBSERVE"), tmp_path / "offline.db", offline=True)
    t = candidate()
    t.liquidity, t.last_liquidity = 50000, NOW
    e.tokens[t.mint] = t
    yield e, t
    await e.stop()


def record(e, t, **overrides):
    fields = dict(mint=t.mint, amount_usd=4.0, price_usd=1.0, quantity_tokens=4.0,
                  actual_entry_fees_usd=0.20, confirm=True)
    return e.intelligence.open_position(OpenPositionInput(**(fields | overrides)), NOW)


def test_external_fill_persists_and_costs_use_actual_entry_once(engine):
    e, t = engine
    before = deepcopy(t), deepcopy(e.paper.state), deepcopy(e.rpc.health), e.approved_evidence
    p = record(e, t)
    assert p["quantity_tokens"] == 4 and p["actual_entry_fees_usd"] == .2
    e.intelligence.journal.observe_market(MarketInput(mint=t.mint, price_usd=1.5), NOW + 1)
    e.intelligence.refresh_positions(NOW + 1)
    x = e.intelligence.exit_results[p["position_id"]]["exit"]
    costs = x["cost_estimate"]
    assert costs["entry_cost_usd"] == .2
    assert costs["entry"] == {"actual_recorded_fees_usd": .2}
    assert costs["net_pnl_usd"] == pytest.approx(6 - 4 - .2 - costs["exit_cost_usd"])
    assert costs["entry_cost_basis"] == "USER_REPORTED_ACTUAL"
    restored = ManualJournal(e.db, e.settings, e.intelligence.cfg)
    assert restored.positions[p["position_id"]]["actual_entry_fees_usd"] == .2
    assert restored.positions[p["position_id"]]["quantity_tokens"] == 4
    e.intelligence.journal.close(p["position_id"], ClosePositionInput(confirm=True), NOW + 2)
    assert e.intelligence.journal.closed()[0]["actual_entry_fees_usd"] == .2
    assert before == (t, e.paper.state, e.rpc.health, e.approved_evidence)
    assert not e.tasks and not e.db.rows("evidence")


@pytest.mark.parametrize("values", [dict(quantity_tokens=None), dict(actual_entry_fees_usd=None),
                                  dict(quantity_tokens=5.0)])
def test_partial_or_inconsistent_fill_has_no_net_estimate(engine, values):
    e, t = engine
    p = record(e, t, **values)
    e.intelligence.journal.observe_market(MarketInput(mint=t.mint, price_usd=1.5), NOW + 1)
    e.intelligence.refresh_positions(NOW + 1)
    x = e.intelligence.exit_results[p["position_id"]]["exit"]
    assert x["estimated_net_pnl_usd"] is None and x["cost_estimate"] is None
    assert x["action"] != "PROTECT_PROFIT"


def test_stale_mark_liquidity_and_large_paid_fees_never_invent_profit(engine):
    e, t = engine
    p = record(e, t, actual_entry_fees_usd=10.0)
    e.intelligence.journal.observe_market(MarketInput(mint=t.mint, price_usd=1.5), NOW)
    e.intelligence.refresh_positions(NOW)
    assert e.intelligence.exit_results[p["position_id"]]["exit"]["estimated_net_pnl_usd"] < 0
    e.intelligence.refresh_positions(NOW + 121)
    x = e.intelligence.exit_results[p["position_id"]]["exit"]
    assert x["action"] == "DATA_STALE" and x["estimated_net_pnl_usd"] is None


@pytest.mark.parametrize("field,bad", [("quantity_tokens", 0), ("quantity_tokens", -1),
                                    ("quantity_tokens", float("inf")), ("actual_entry_fees_usd", -1),
                                    ("actual_entry_fees_usd", float("nan")), ("actual_entry_fees_usd", True)])
def test_fill_fields_fail_closed(field, bad):
    with pytest.raises(ValidationError):
        OpenPositionInput(mint=candidate().mint, amount_usd=4.0, price_usd=1.0,
                          confirm=True, **{field: bad})


def test_explicit_zero_fee_is_known_not_missing(engine):
    e, t = engine
    p = record(e, t, actual_entry_fees_usd=0.0)
    e.intelligence.journal.observe_market(MarketInput(mint=t.mint, price_usd=1.5), NOW)
    e.intelligence.refresh_positions(NOW)
    assert e.intelligence.exit_results[p["position_id"]]["exit"]["cost_estimate"]["entry_cost_usd"] == 0


async def test_local_api_records_and_closes_external_fill_without_provider_activity(engine):
    e, t = engine
    before = deepcopy(e.rpc.health), deepcopy(e.paper.state), deepcopy(t.decision), e.approved_evidence
    app = create_app()
    app.state.engine = e  # No lifespan or provider startup.
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as c:
        result = await c.post("/api/manual-positions", json=dict(
            mint=t.mint, amount_usd=4, price_usd=1, quantity_tokens=4,
            actual_entry_fees_usd=.2, confirm=True,
        ))
        assert result.status_code == 200
        entry = result.json()
        assert entry["quantity_tokens"] == 4 and entry["actual_entry_fees_usd"] == .2
        identity = entry["position_id"]
        assert (await c.get("/api/manual-positions")).json()["open"][0]["position_id"] == identity
        closed = await c.post(f"/api/manual-positions/{identity}/close", json={"confirm": True})
        assert closed.status_code == 200 and closed.json()["status"] == "CLOSED"
        assert (await c.get("/api/manual-positions")).json()["closed"][0]["quantity_tokens"] == 4
    assert before == (e.rpc.health, e.paper.state, t.decision, e.approved_evidence)
    assert not e.tasks and not e.db.rows("paper_trade")
