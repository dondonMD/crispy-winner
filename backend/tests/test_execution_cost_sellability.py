"""Hypothetical arithmetic checks, not actual fills, recommendations or cohorts."""

import pytest

from backend.app.config import Settings
from backend.app.economics import TradeCostEstimator


@pytest.mark.parametrize("position", [2, 4, 10])
def test_unbracketed_break_even_is_unavailable(position):
    estimator = TradeCostEstimator(Settings())
    assert estimator.estimate(position, 1, 1000)["net_pnl_usd"] < 0
    assert estimator.break_even(position, 1) is None


@pytest.mark.parametrize("position", [2, 4, 10])
@pytest.mark.parametrize("liquidity", [10000, 25000])
def test_supported_break_even_remains_a_root(position, liquidity):
    estimator = TradeCostEstimator(Settings())
    point = estimator.break_even(position, liquidity)
    assert point is not None
    assert estimator.estimate(position, liquidity, point)["net_pnl_usd"] == pytest.approx(0, abs=1e-8)


@pytest.mark.parametrize("position", [2, 4, 10])
def test_hypothetical_cost_ledger_reconciles_and_small_gain_can_lose(position):
    estimator = TradeCostEstimator(Settings())
    flat = estimator.estimate(position, 10000)
    entry_debit = position + flat["entry_cost_usd"]
    exit_proceeds = position - flat["exit_cost_usd"]
    assert entry_debit - exit_proceeds == pytest.approx(flat["round_trip_cost_usd"])
    assert flat["net_pnl_usd"] == pytest.approx(exit_proceeds - entry_debit)
    assert estimator.estimate(position, 10000, 4)["net_pnl_usd"] < 0
    assert Settings().account_usd == 20 and Settings().max_position_fraction == 0.2


@pytest.mark.parametrize("liquidity", [None, 0, 1])
def test_manual_break_even_unavailable_never_becomes_sell_authorization(liquidity):
    from backend.app.domain import Token
    from backend.app.manual import manual_economics

    token = Token("synthetic", "Hypothetical", "TEST", 1000)
    token.liquidity, token.last_liquidity = liquidity, 1000
    result = manual_economics(Settings(), 20, 4, token, 1000)
    assert result["break_even_pct"] is None
    assert result["economically_viable"] is False
    assert "sellable" not in result
