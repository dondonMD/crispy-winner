"""Bounded synchronous SYNTHETIC computation profile; no scheduler, network or cohort run."""
import sys
from pathlib import Path

import argparse
import asyncio
from bisect import bisect_right
from collections import Counter, deque
import dataclasses
import hashlib
import io
import json
import os
import subprocess
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.config import Settings
from backend.app.domain import MarketEvent, Token
from backend.app.early_edge import manifest
from backend.app.early_edge_runtime import attach_observer
from backend.app.engine import RadarEngine
from scripts.early_edge_diagnostic import DryObserver


def digest(value):
    # Diagnostic hashes preserve existing inf/NaN sentinels; never a business cache.
    # Only the hash is persisted; result JSON still rejects nonfinite metrics.
    def default(obj):
        if hasattr(obj, 'model_dump'):
            return obj.model_dump(mode='json')
        if isinstance(obj, deque):
            return list(obj)
        raise TypeError('Unsupported diagnostic input')
    return hashlib.sha256(json.dumps(value, default=default, sort_keys=True,
        separators=(',', ':'), allow_nan=True).encode()).hexdigest()


class Versions:
    """Aggregate hashes only, <=2500 previous slots; no token/wallet/payload persistence."""
    def __init__(self):
        self.previous = {}
        self.counts: Counter = Counter()

    def record(self, operation, slot, evidence, now=None, effective=None):
        if len(self.previous) >= 2500 and (operation, slot) not in self.previous:
            raise ValueError('Input-version diagnostic bound exceeded')
        e = digest(evidence)
        full = digest((e, now))
        effective = full if effective is None else digest(effective)
        previous = self.previous.get((operation, slot))
        self.counts[(operation, 'calls')] += 1
        if previous:
            self.counts[(operation, 'evidence_unchanged')] += previous[0] == e
            self.counts[(operation, 'exact_call_unchanged')] += previous[1] == full
            self.counts[(operation, 'effective_unchanged')] += previous[2] == effective
            self.counts[(operation, 'time_changed')] += previous[3] != now
        self.previous[(operation, slot)] = (e, full, effective, now)

    def report(self):
        operations = sorted({k for k, _ in self.counts})
        return {op: {name: self.counts[(op, name)] for name in (
            'calls', 'evidence_unchanged', 'exact_call_unchanged', 'effective_unchanged', 'time_changed')}
            for op in operations}


def token_data(token):
    return {f.name: getattr(token, f.name) for f in dataclasses.fields(Token)}


def audit_inputs(engine):
    """Separate pass: hashing cost is deliberately NOT included in CPU profile results."""
    import backend.app.features as features
    import backend.app.intelligence as intelligence
    import backend.app.opportunity as opportunity
    audit, undo, active = Versions(), [], [None]

    def patch(obj, name, fn):
        undo.append((obj, name, getattr(obj, name)))
        setattr(obj, name, fn)

    parse = opportunity._parse_intelligence_settings

    def parsed(content):
        audit.record('configuration_parse_input', 'single', content)
        return parse(content)
    patch(opportunity, '_parse_intelligence_settings', parsed)
    project = intelligence.opportunity_view

    def projected(token, settings, now, cfg=None, market=None):
        audit.record('opportunity_projection', token.mint,
            (token_data(token), settings.model_dump(), cfg.model_dump() if cfg else None, market), now)
        return project(token, settings, now, cfg, market)
    patch(intelligence, 'opportunity_view', projected)
    calculate = features.calculate_features
    engine_calculate = __import__('backend.app.engine', fromlist=['calculate_features'])

    def calculated(token, now):
        previous, active[0] = active[0], token.mint
        evidence = (token.creator, token.flow_venue, token.flow_epoch, list(token.events))
        audit.record('calculate_features', token.mint, evidence, now)
        try:
            return calculate(token, now)
        finally:
            active[0] = previous
    patch(engine_calculate, 'calculate_features', calculated)
    window = features.cached_window_features

    def windowed(events, now, seconds, creator, cache, **kwargs):
        trades = [e for e in events if e.kind == 'trade' and 0 <= now-e.ts <= seconds]
        prices = [(e.ts, e.price) for e in events if e.price is not None and 0 <= now-e.ts <= seconds]
        business = (seconds, creator, [(e.ts, e.side, e.wallet, repr(e.volume), e.currency, e.price) for e in trades], prices)
        boundaries = [i*seconds/6 for i in range(7)]
        classes = [(now-e.ts <= seconds/2, bisect_right(boundaries, now-e.ts)-1) for e in trades]
        audit.record(f'window_{seconds}', active[0], business, now, (business, classes))
        return window(events, now, seconds, creator, cache, **kwargs)
    patch(features, 'cached_window_features', windowed)
    now = time.time()
    try:
        # Same evidence/time repetition vs REAL time-bin changes, no producer/cadence simulation.
        for offset in [0, 0, 1.8, 3.6]:
            for token in engine.tokens.values():
                engine.analyse(token, now+offset)
        for _ in range(2):
            engine.intelligence.refresh(now+3.6, force=True)
    finally:
        for obj, name, fn in reversed(undo):
            setattr(obj, name, fn)
    return dict(operations=audit.report(), previous_slot_count=len(audit.previous),
        limitations='Separate untimed audit. Token hashes for projection are conservative complete snapshots; '
        'window effective keys include original membership/half-window/bin classifications. No audit key is used for production reuse.')


def profile(engine, function, output, name, operations):
    # The project has scripts/profile.py: remove that CLI path before stdlib import.
    script_directory = str(Path(__file__).resolve().parent)
    if script_directory in sys.path:
        sys.path.remove(script_directory)
    import cProfile
    import pstats
    profiler = cProfile.Profile()
    start, cpu = time.perf_counter(), time.process_time()
    profiler.enable()
    try:
        function()
    finally:
        profiler.disable()
    elapsed, cpu = time.perf_counter()-start, time.process_time()-cpu
    stats = pstats.Stats(profiler)
    rows = [dict(file=file, line=line, function=fn, calls=entry[1], exclusive_wall_seconds=entry[2],
                 inclusive_wall_seconds=entry[3]) for (file, line, fn), entry in vars(stats)['stats'].items()]
    rows.sort(key=lambda r: r['exclusive_wall_seconds'], reverse=True)
    text = io.StringIO()
    pstats.Stats(profiler, stream=text).sort_stats('tottime').print_stats(50)
    (output/(name+'-exclusive.txt')).write_text(text.getvalue())
    return dict(wall_seconds=elapsed, cpu_seconds=cpu, operations=operations, functions=rows)


def run(output, candidates=250, warm=200, passes=4, refreshes=8, events=500):
    if (os.getenv('RADAR_COHORT') or os.getenv('PUMPPORTAL_ENABLED', 'false').lower() == 'true'
            or not 1 <= candidates <= 250 or not 0 <= warm <= 500 or not 1 <= passes <= 8
            or not 1 <= refreshes <= 16 or not 1 <= events <= 2000):
        raise ValueError('Bounded synthetic-only component configuration required')
    output.mkdir(exist_ok=False, parents=True)
    engine = RadarEngine(Settings(mode='OBSERVE'), output/'synthetic.db', offline=False)
    detach = None
    try:
        anchor = time.time()
        for i in range(candidates):
            mint = f'synthetic:{i}'
            engine.process(MarketEvent(event_id=f'create:{i}', mint=mint, ts=anchor, source='SYNTHETIC', kind='create'))
            for j in range(warm):
                engine.tokens[mint].events.append(MarketEvent(event_id=f'warm:{i}:{j}', mint=mint,
                    ts=anchor-180+j*180/max(1, warm), source='SYNTHETIC', kind='market' if j%10==0 else 'trade',
                    side='buy' if j%3 else 'sell', wallet=f'synthetic-wallet:{j%64}', volume=.001+j%5/1000,
                    currency='SOL', price=1+j*.0001*(1+i/250) if j%10==0 else None))
        observer = DryObserver(engine.settings, manifest(engine.settings, draft=True))
        detach = attach_observer(engine, observer)
        for token in engine.tokens.values():
            engine.analyse(token, time.time())
        engine.intelligence.refresh(time.time(), force=True)

        def analyses():
            for _ in range(passes):
                for token in engine.tokens.values():
                    engine.analyse(token, time.time())

        def intelligence():
            for _ in range(refreshes):
                engine.intelligence.refresh(time.time(), force=True)

        def trades():
            for i in range(events):
                now = time.time()
                engine.process(MarketEvent(event_id=f'trade:{i}', mint=f'synthetic:{i%candidates}', ts=now,
                    source='Solana WSS', kind='trade', side='buy' if i%3 else 'sell',
                    wallet=f'synthetic-wallet:{i%64}', volume=.001+i%5/1000, currency='SOL'), now)
        result = dict(synthetic=True, cohort_created=False, scheduler_started=False,
            source_sha=subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
            source_files_sha256={name: hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in (
                'backend/app/features.py', 'backend/app/engine.py', 'backend/app/intelligence.py',
                'backend/app/opportunity.py', 'backend/app/early_edge.py',
                'backend/app/early_edge_runtime.py', 'backend/app/early_edge_design.py',
                'scripts/profile_evidence_computation.py')},
            candidates=candidates, warm_events=warm, stages={
                'analysis': profile(engine, analyses, output, 'analysis', passes*candidates),
                'refresh': profile(engine, intelligence, output, 'refresh', refreshes),
                'trades': profile(engine, trades, output, 'trades', events)}, input_audit=audit_inputs(engine),
            limitations='Synchronous cProfile component costs with profiling overhead, not throughput acceptance. '
            'Inputs synthetic; no provider tasks started; no profile timer is summed with its parent.')
        with engine.db.engine.connect() as sql:
            from sqlalchemy import text
            assert sql.execute(text('SELECT count(*) FROM prospective_cohorts')).scalar_one() == 0
        (output/'profile.json').write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
        return result
    finally:
        if detach:
            detach()
        asyncio.run(engine.stop())  # Real close/join; no worker or scheduler tasks were started.
        engine.db.engine.dispose()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--candidates', type=int, default=250)
    parser.add_argument('--warm', type=int, default=200)
    parser.add_argument('--passes', type=int, default=4)
    parser.add_argument('--refreshes', type=int, default=8)
    parser.add_argument('--events', type=int, default=500)
    args = parser.parse_args()
    result = run(args.output, args.candidates, args.warm, args.passes, args.refreshes, args.events)
    print(json.dumps({k: result[k] for k in ('synthetic', 'scheduler_started', 'cohort_created')}))
