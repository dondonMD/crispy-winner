"""Synthetic diagnostic accounting only; never qualifies real strategy evidence."""
from copy import deepcopy

import pytest

from scripts.analyze_evidence_backlog import analyze, growth, scheduled_count
from scripts.validate_evidence_load import scheduled_offset


def report():
    return dict(synthetic=True, declared_seconds=40, target_trade_rate=50, endurance=True,
                durable_commits_per_10s={'0': 450, '1': 500, '2': 500, '3': 500, '4': 50},
                trade_producer_ready_per_10s={'0': 500, '1': 500, '2': 500, '3': 500},
                trade_processing_starts_per_10s={'0': 480, '1': 500, '2': 500, '3': 500, '4': 20}, samples=[])


def test_schedule_count_exact_half_open_boundary_and_burst_preserved():
    for bursts in [False, True]:
        offsets = [scheduled_offset(i, 50, bursts) for i in range(2000)]
        for at in [0, .001, .5, 1, 1.01, 10, 20, 39.99, 40, 41]:
            assert scheduled_count(at, 2000, 50, bursts) == sum(t < at for t in offsets)
    assert scheduled_count(1, 2000, 50, True) == 100
    assert scheduled_count(10, 2000, 50, True) == 500


def test_original_pass_and_failure_not_relabelled_by_low_latency_or_oscillation():
    passing = [66, 75, 47, 68, 62, 39, 55, 67, 39, 37, 43]
    failing = [44, 66, 44, 57, 60, 67, 69, 45, 77, 41, 75]
    assert growth([(20+i*10, v) for i, v in enumerate(passing)])['passed'] is True
    result = growth([(20+i*10, v) for i, v in enumerate(failing)])
    assert result['passed'] is False
    assert result['slope_events_per_second'] == pytest.approx(.12636363636)
    assert growth([])['passed'] is None


def test_exact_pipeline_cut_reconciles_without_historical_fabrication_or_mutation():
    original = report()
    frozen = deepcopy(original)
    result = analyze(original)
    assert original == frozen
    row = result['boundaries'][0]
    assert (row['scheduled_not_ready'], row['ready_not_started'], row['started_not_durable']) == (0, 20, 30)
    assert sum(row[k] for k in ['scheduled_not_ready', 'ready_not_started', 'started_not_durable']) == row['deficit']
    del original['trade_producer_ready_per_10s']
    historical = analyze(original)['boundaries'][0]
    assert historical['exact_pipeline_decomposition'] == 'UNAVAILABLE_HISTORICAL'
    assert 'scheduled_not_ready' not in historical


def test_sample_loss_and_nonpersisted_terminal_stay_distinct_and_unknown_pressure_is_not_zero():
    original = report()
    original['samples'] = [dict(at=20, accounted=dict(events=dict(trade=dict(
        submitted=1000, accepted=990, rejected_incoming=10, evicted_accepted=5,
        pending=20, in_processing=15, terminal={'processed': 940, 'stale': 10}, persisted=940))))]
    result = analyze(original)
    row = result['sample_decomposition'][0]
    assert row['rejected'] == 10 and row['evicted'] == 5 and row['terminal_not_persisted'] == 10
    assert row['scheduled_not_persisted'] == 60 and result['sample_reconciliation_residual_max'] == 0
    assert result['shared_psi_delta_seconds'] == dict(cpu=None, io=None, memory=None)


def test_analysis_refuses_live_or_unbounded_reports():
    for update in [dict(synthetic=False), dict(declared_seconds=1801), dict(target_trade_rate=101),
                   dict(samples=[{}]*1802)]:
        with pytest.raises(ValueError):
            analyze(dict(report(), **update))
