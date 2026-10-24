"""Read-only replay diagnostics do not schedule work or change evidence policy."""
import time

from scripts.evidence_repro import ReproTrace, digest


def test_digest_and_bounded_trace_do_not_retain_payloads():
    assert digest({'b': 2, 'a': 1}) == digest({'a': 1, 'b': 2})
    trace = ReproTrace()
    trace.start(100)
    for i in range(5000):
        trace.record('sqlite.commit', 100 + i / 100, .1)
        trace.sample_lag(time.perf_counter())
    result = trace.result()
    assert result['long_call_count'] == 5000
    assert len(result['long_calls']) == 128
    assert result['loop_lag']['count'] == 1801
    for i in range(50):
        trace.record(f'stage{i}', 100, .01)
    assert len(trace.intervals['0']) == 20
    trace.record('ignored', 100 + 1810, .1)
    assert len(trace.intervals) == 5
    assert all(set(row) == {'stage', 'at', 'seconds'} for row in result['long_calls'])


def test_loop_lag_uses_existing_clock_without_tasks(monkeypatch):
    trace = ReproTrace()
    trace.start(100)
    monkeypatch.setattr('scripts.evidence_repro.time.perf_counter', lambda: 102.75)
    trace.sample_lag(101)
    assert trace.result()['loop_lag']['maximum'] == 1.75
    assert not hasattr(trace, 'loop_task')
    sample = trace.sample()
    assert sample['available_memory'] > 0
    assert set(sample['pressure']) == {'cpu', 'io', 'memory'}


def test_threaded_commit_role_counters_and_proc_text_are_bounded(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from scripts.evidence_repro import read_text
    trace = ReproTrace()
    trace.start(100)
    def write(_):
        for _ in range(1000):
            trace.record("sqlite.commit", 101, .03, role="raw_event")
    with ThreadPoolExecutor(max_workers=2) as workers:
        list(workers.map(write, range(2)))
    values = trace.result()["intervals"]["0"]["sqlite.commit"]
    assert values["count"] == values["roles"]["raw_event"]["count"] == 2000
    assert values["roles"]["raw_event"]["over_20ms"] == 2000
    path = tmp_path / "synthetic-text"
    path.write_text("x" * 10000)
    assert read_text(path) == "x" * 8192 + " [TRUNCATED]"
