"""Exact parity at every rolling boundary, including rounding and missing units."""
import math
import random

import pytest

from backend.app.domain import MarketEvent
from backend.app.features import window_features, price_volatility
from backend.tests.feature_reference_0357 import window_features as reference


@pytest.mark.parametrize('seconds', [10, 30, 60, 180, 300, 600])
def test_window_exact_parity(seconds):
    rng = random.Random(510)
    now = 10000.
    times = [now - rng.uniform(-1, seconds + 1) for _ in range(400)]
    for i in range(7):
        edge = now - i * seconds / 6
        times.extend([edge, math.nextafter(edge, -math.inf), math.nextafter(edge, math.inf)])
    events = [MarketEvent(event_id=str(i), mint='synthetic', source='SYNTHETIC', ts=t, kind='market' if i % 9 == 0 else 'trade',
        side='buy' if i % 3 else 'sell', wallet=f'w{i % 23}', currency='unknown' if i % 17 == 0 else 'SOL',
        volume=rng.choice([.0001, .12, 1e12, 0]), price=1 + rng.random() if i % 11 == 0 else None)
        for i, t in enumerate(sorted(times))]
    for at in [now, now + .001, now + 10, now + seconds]:
        assert window_features(events, at, seconds, 'w2') == reference(events, at, seconds, 'w2')
    assert window_features([], now, seconds) == reference([], now, seconds)


def test_volatility_cache_is_bounded_and_reuses_capacity_working_set():
    price_volatility.cache_clear()
    for i in range(1500):
        price_volatility((i / 10000, .1))
    before = price_volatility.cache_info()
    for i in range(1500):
        assert price_volatility((i / 10000, .1)) == pytest.approx(abs(i / 10000 - .1) * 50)
    assert price_volatility.cache_info().hits - before.hits == 1500
    for i in range(2000):
        price_volatility((float(i),))
    assert price_volatility.cache_info().currsize <= 1536
    price_volatility.cache_clear()
