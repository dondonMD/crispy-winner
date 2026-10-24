"""Read-only bounded SYNTHETIC replay analysis; never changes acceptance or runtime policy."""
import argparse
import json
from pathlib import Path
import re
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.validate_evidence_load import scheduled_offset  # noqa: E402


def scheduled_count(at, count, rate, bursts):
    """Half-open arrival count, using the original harness schedule without a new array."""
    low, high = 0, count
    while low < high:
        mid = (low + high) // 2
        if scheduled_offset(mid, rate, bursts) < at:
            low = mid + 1
        else:
            high = mid
    return low


def cumulative(bins, boundary):
    return sum(value for key, value in bins.items() if int(key) < boundary)


def growth(points):
    if len(points) < 3:
        return dict(passed=None, reason="INSUFFICIENT_ALIGNED_POINTS")
    mx, my = statistics.mean(t for t, _ in points), statistics.mean(y for _, y in points)
    slope = sum((t-mx)*(y-my) for t, y in points) / sum((t-mx)**2 for t, _ in points)
    early, late = statistics.mean(y for _, y in points[:3]), statistics.mean(y for _, y in points[-3:])
    return dict(passed=slope <= 0 and late <= early, slope_events_per_second=slope,
                early_three_mean=early, late_three_mean=late,
                criterion="UNCHANGED: slope<=0 AND late-three mean<=early-three mean; exact10s phases after20s")


def numeric_summary(values):
    if not values:
        return None
    ordered = sorted(values)
    return dict(count=len(values), minimum=ordered[0], mean=statistics.mean(values),
                p50=ordered[int((len(ordered)-1)*.5)], p95=ordered[int((len(ordered)-1)*.95)], maximum=ordered[-1])


def psi_total(sample, kind):
    text = sample.get("environment", {}).get("pressure", {}).get(kind)
    match = re.search(r"total=(\d+)", text or "")
    return int(match[1]) / 1000000 if match else None


def analyze(report):
    seconds, rate = report['declared_seconds'], report['target_trade_rate']
    samples = report.get('samples', [])
    if (report.get('synthetic') is not True or not 1 <= seconds <= 1800 or not 1 <= rate <= 100
            or len(samples) > 1801):
        raise ValueError('Only bounded synthetic harness reports are supported')
    count = int(seconds * rate)
    diagnostics = report.get('reproducibility', {}).get('diagnostics', {})
    intervals = diagnostics.get('intervals', {})
    points, boundaries = [], []
    for b in range(2, int(seconds // 10)+1):
        due = min(count, b*10*rate)
        done = cumulative(report['durable_commits_per_10s'], b)
        row = dict(at=b*10, scheduled=due, durable=done, deficit=due-done)
        ready, starts = report.get('trade_producer_ready_per_10s'), report.get('trade_processing_starts_per_10s')
        if ready is not None and starts is not None:
            r, s = cumulative(ready, b), cumulative(starts, b)
            row.update(scheduled_not_ready=due-r, ready_not_started=r-s, started_not_durable=s-done)
        else:
            row['exact_pipeline_decomposition'] = 'UNAVAILABLE_HISTORICAL'
        boundaries.append(row)
        points.append((b*10, due-done))
    periods = []
    for b in range(int(seconds // 10)):
        stage = intervals.get(str(b), {})
        commit = stage.get('sqlite.commit', {})
        periods.append(dict(at=b*10, durable=report['durable_commits_per_10s'].get(str(b), 0),
            commit_seconds=commit.get('seconds'), commit_maximum=commit.get('maximum'),
            analysis_seconds=stage.get('RadarEngine.analyse', {}).get('seconds'),
            refresh_seconds=stage.get('Intelligence.refresh', {}).get('seconds'),
            checkpoint_seconds=stage.get('RadarEngine.checkpoint', {}).get('seconds')))
    decomposed = []
    for sample in samples:
        trade = sample.get('accounted', {}).get('events', {}).get('trade')
        if not trade:
            continue
        due = scheduled_count(sample['at'], count, rate, report.get('endurance', False))
        unpersisted_terminal = sum(trade['terminal'].values()) - trade['persisted']
        row = dict(at=sample['at'], scheduled_not_submitted=due-trade['submitted'],
            pending=trade['pending'], detached=trade['in_processing'],
            terminal_not_persisted=unpersisted_terminal,
            rejected=trade['rejected_incoming'], evicted=trade['evicted_accepted'],
            scheduled_not_persisted=due-trade['persisted'])
        row['reconciliation_residual'] = row['scheduled_not_persisted'] - sum(row[k] for k in (
            'scheduled_not_submitted', 'pending', 'detached', 'terminal_not_persisted', 'rejected', 'evicted'))
        decomposed.append(row)
    psi = {}
    for kind in ['cpu', 'io', 'memory']:
        first, last = (psi_total(samples[i], kind) for i in [0, -1]) if samples else (None, None)
        psi[kind] = last-first if first is not None and last is not None else None
    return dict(synthetic=True, source_sha=report.get('source_sha'), declared_seconds=seconds, rate=rate,
        gate=growth(points), boundaries=boundaries, periods=periods,
        post_warmup_completion_rate=(boundaries[-1]['durable']-boundaries[0]['durable']) /
            (boundaries[-1]['at']-boundaries[0]['at']) if len(boundaries)>1 else None,
        sample_summaries={key: numeric_summary([r[key] for r in decomposed]) for key in (
            'scheduled_not_submitted', 'pending', 'detached', 'scheduled_not_persisted')},
        sample_reconciliation_residual_max=max((abs(r['reconciliation_residual']) for r in decomposed), default=0),
        shared_psi_delta_seconds=psi, loop_lag=diagnostics.get('loop_lag'),
        environment=diagnostics.get('environment'), sample_decomposition=decomposed,
        limitations=['Exact pipeline cuts unavailable in historical reports remain unavailable.',
            'Ready/starts count pipeline stages, not successful persistence; failures remain in the event ledger.',
            'Sample timestamps precede counter snapshots slightly; not exact10s cuts.',
            'Shared host/cgroup pressure does not attribute I/O to this process.',
            'Commit timing includes automatic WAL work; separate checkpoint timing is not available.',
            'Periodic inclusive timers overlap and must not be added as exclusive CPU.'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.report.stat().st_size > 32*1048576:
        raise ValueError('Report exceeds diagnostic byte bound')
    result = analyze(json.loads(args.report.read_text()))
    with args.output.open('x') as file:
        json.dump(result, file, indent=2, allow_nan=False)
    print(json.dumps({'output': str(args.output), 'gate': result['gate']}))
