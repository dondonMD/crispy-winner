"""Deterministic simulated scenarios; never imported by a real-data provider."""
import random
from backend.app.domain import MarketEvent

SCENARIOS = ['healthy maturing', 'dead launch', 'whale momentum', 'creator dump', 'possible sybil',
             'pump collapse', 'near graduation failure', 'graduation dump', 'consolidation',
             'healthy recovery', 'distributed buying', 'liquidity deterioration']


def demo_events(start, tick, seed=47):
    rng = random.Random(seed+tick)
    events = []
    for i, scenario in enumerate(SCENARIOS):
        mint = f'DEMO{i:02d}simulated'
        ts = start+tick
        if tick == 0:
            events.append(MarketEvent(mint=mint, ts=ts, source='DEMO', kind='create',
                                     event_id=f'{mint}-create', name=scenario.title(), symbol=f'SIM{i}',
                                     creator=f'creator{i}'))
            events.append(MarketEvent(mint=mint, ts=ts, source='DEMO', kind='security',
                                     event_id=f'{mint}-security', evidence={
                                         'data_quality': 'SIMULATED', 'risk_score': 10,
                                         'hard_failures': [], 'warnings': ['SIMULATED SECURITY'],
                                         'top_1_independent_pct': 4, 'top_5_independent_pct': 15,
                                         'creator_pct': 2, 'last_updated': ts, 'token_program': 'SIMULATED'}))
        if i == 1 or (i == 6 and tick > 60):
            continue
        if tick == 90 and i >= 7:
            events.append(MarketEvent(mint=mint, ts=ts, source='DEMO', kind='migration',
                                     event_id=f'{mint}-graduation', signature=f'SIM-GRAD-{i}'))
        if i == 5:
            price = .001*(1+tick*.045) if tick<40 else .0028*max(.05, 1-(tick-40)*.025)
        elif i >= 7 and tick>=90:
            x = tick-90
            price = .0019*(1-min(x, 20)*.012+max(0,x-40)*(.003 if i in [9,10] else .0002))
            if i == 7:
                price *= max(.1, 1-x*.008)
        else:
            price = .001*(1+tick*.0025)
        price *= 1+rng.uniform(-.003,.003)
        for j in range(2 if i in [0,9,10] else 1):
            wallet = f'wallet{i}-{(tick*2+j)%100}'
            if i == 2:
                wallet = f'whale-{tick%2}'
            if i == 3 and tick>25:
                wallet = f'creator{i}'
            if i == 4:
                wallet = f'cluster{tick}-{j}'
            side = 'sell' if (i == 3 and tick>25) or (i == 7 and tick>90) or rng.random()<.2 else 'buy'
            amount = 5 if i == 4 else rng.uniform(1,15)
            events.append(MarketEvent(mint=mint, ts=ts+j*.01, source='DEMO', kind='trade',
                                     event_id=f'{mint}-{tick}-{j}', wallet=wallet, side=side, volume=amount,
                                     currency='USD', price=price, market_cap=price*1e9,
                                     liquidity=max(30, 15000-tick*100) if i==11 else 25000,
                                     curve_progress=min(98,tick*1.0) if i<7 else None))
    return events
