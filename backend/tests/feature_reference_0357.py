"""Frozen exact feature reference from 0357de8; synthetic regression only."""
import math
import statistics
from collections import Counter
from backend.app.features import price_volatility

def window_features(events, now, seconds, creator=""):
    trades = [e for e in events if e.kind == "trade" and 0 <= now - e.ts <= seconds]
    buys = [e for e in trades if e.side == "buy"]
    sells = [e for e in trades if e.side == "sell"]
    wallets = {e.wallet for e in buys if e.wallet}
    volumes = [e.volume for e in buys]
    by_wallet: Counter = Counter()
    patterns: dict = {}
    for e in buys:
        by_wallet[e.wallet] += e.volume
        # Conservative synchrony/size evidence, no ownership inference.
        key = (int(e.ts // 2), round(e.volume, 5))
        patterns.setdefault(key, set()).add(e.wallet)
    suspicious = set().union(*(v for v in patterns.values() if len(v) >= 3)) if patterns else set()
    clusters = sum(max(0, len(v) - 1) for v in patterns.values() if len(v) >= 3)
    independent = max(0, len(wallets) - min(len(suspicious), clusters))
    buy_volume, sell_volume = sum(volumes), sum(e.volume for e in sells)
    total = buy_volume + sell_volume
    currency = {e.currency for e in trades}
    consistent_units = bool(trades) and len(currency) == 1 and "unknown" not in currency
    recent = sum(e.volume if e.side == "buy" else -e.volume for e in trades if now - e.ts <= seconds / 2)
    previous = sum(e.volume if e.side == "buy" else -e.volume for e in trades if now - e.ts > seconds / 2)
    priced = [e for e in events if e.price is not None and 0 <= now - e.ts <= seconds]
    prices = [e.price for e in priced]
    returns = [math.log(b / a) for a, b in zip(prices, prices[1:]) if a > 0 and b > 0]
    bins = [
        sum(
            e.volume if e.side == "buy" else -e.volume
            for e in trades
            if i * seconds / 6 <= now - e.ts < (i + 1) * seconds / 6
        )
        for i in range(6)
    ]
    vwap = (
        sum(e.price * e.volume for e in trades if e.price) / sum(e.volume for e in trades if e.price)
        if any(e.price and e.volume for e in trades)
        else None
    )
    return {
        "buy_count": len(buys),
        "sell_count": len(sells),
        "buy_volume": buy_volume if consistent_units else None,
        "sell_volume": sell_volume if consistent_units else None,
        "flow_ratio": buy_volume / sell_volume if sell_volume else (10 if buy_volume else 0),
        "flow_balance": (buy_volume - sell_volume) / total if total and consistent_units else 0,
        "net_flow": buy_volume - sell_volume if consistent_units else None,
        "currency": next(iter(currency)) if len(currency) == 1 else "mixed",
        "raw_unique_buyers": len(wallets),
        "estimated_independent_buyers": independent,
        "cluster_probability_score": 100 * len(suspicious) / len(wallets) if wallets else 0,
        "cluster_evidence": ["POSSIBLY RELATED WALLETS: matched size within 2s"] if suspicious else [],
        "whale_share": max(by_wallet.values(), default=0) / buy_volume if buy_volume else 1,
        "median_buy": statistics.median(volumes) if volumes else 0,
        "p75_buy": sorted(volumes)[int((len(volumes) - 1) * 0.75)] if volumes else 0,
        "largest_buy": max(volumes, default=0),
        "largest_sell": max((e.volume for e in sells), default=0),
        "buyer_arrival_rate": len(wallets) / seconds,
        "seller_arrival_rate": len({e.wallet for e in sells if e.wallet}) / seconds,
        "repeat_buyers": sum(v > 1 for v in Counter(e.wallet for e in buys).values()),
        "creator_sell_volume": sum(e.volume for e in sells if creator and e.wallet == creator),
        "creator_buy_volume": sum(e.volume for e in buys if creator and e.wallet == creator),
        "trade_velocity": len(trades) / seconds,
        "trade_acceleration": (sum(now - e.ts <= seconds / 2 for e in trades) * 2 - len(trades))
        / (seconds / 2),
        "volume_velocity": total / seconds if consistent_units else None,
        "flow_acceleration": recent - previous if consistent_units else None,
        "buy_pressure_persistence": sum(x > 0 for x in bins) / 6,
        "sell_pressure_persistence": sum(x < 0 for x in bins) / 6,
        "volatility_pct": price_volatility(tuple(returns)),
        "drawdown_pct": (1 - prices[-1] / max(prices)) * 100 if prices else 0,
        "price_move_pct": (prices[-1] / prices[0] - 1) * 100 if len(prices) > 1 else 0,
        "vwap": vwap,
        "samples": len(trades),
        "units_valid": consistent_units,
    }

