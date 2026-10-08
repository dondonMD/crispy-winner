from collections import deque
from backend.app.domain import MarketEvent, Token
from backend.app.features import calculate_features, score_token, window_features


def trade(ts, wallet="a", volume=1, side="buy", price=1):
    return MarketEvent(
        mint="test",
        ts=ts,
        source="test",
        kind="trade",
        event_id=str(ts) + wallet,
        wallet=wallet,
        volume=volume,
        side=side,
        price=price,
        currency="USD",
    )


def test_window_future_events_excluded_and_expire():
    result = window_features([trade(10), trade(20), trade(100)], 30, 15)
    assert result["buy_count"] == 1 and result["raw_unique_buyers"] == 1
    assert window_features([trade(1)], 100, 10)["samples"] == 0


def test_cluster_penalty_conservative_language():
    result = window_features([trade(10, w) for w in ["a", "b", "c", "d"]], 11, 30)
    assert result["raw_unique_buyers"] == 4 and result["estimated_independent_buyers"] == 1
    assert "POSSIBLY RELATED" in result["cluster_evidence"][0]


def test_distributed_persistent_better_than_whales():
    broad = Token("a", "a", "a", 0)
    whale = Token("b", "b", "b", 0)
    broad.events = deque([trade(i * 3, f"w{i}", i + 1, price=1 + i * 0.001) for i in range(60)], maxlen=500)
    whale.events = deque([trade(i * 3, "whale", 100, price=1 + i * 0.04) for i in range(60)], maxlen=500)
    for t in [broad, whale]:
        t.price = t.events[-1].price
        t.features = calculate_features(t, 180)
        t.scores = score_token(t, 180)
    assert broad.scores["momentum"] > whale.scores["momentum"]
    assert broad.scores["maturity"] > whale.scores["maturity"]
    assert whale.scores["chase"] >= 60


def test_missing_units_not_positive_flow():
    e = trade(1)
    e.currency = "unknown"
    assert window_features([e], 2, 10)["net_flow"] is None
    assert window_features([e], 2, 10)["flow_balance"] == 0
