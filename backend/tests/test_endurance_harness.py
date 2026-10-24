"""Synthetic diagnostic protocol; not a prospective enrollment test."""
from pathlib import Path

import pytest

from scripts.validate_evidence_load import scheduled_offset, storage_bytes


def test_burst_schedule_preserves_average_and_total_order():
    offsets = [scheduled_offset(i, 50, True) for i in range(30000)]
    assert offsets == sorted(set(offsets))
    assert offsets[100] == 1
    assert offsets[500] == 10
    assert sum(t < 1 for t in offsets) == 100
    assert sum(t < 10 for t in offsets) == 500
    assert offsets[-1] < 600
    assert scheduled_offset(30000, 50, True) == 600
    assert [scheduled_offset(i, 50) for i in range(100)] == [i / 50 for i in range(100)]


def test_storage_samples_include_allocated_wal_and_shm(tmp_path):
    path = tmp_path / 'synthetic.db'
    assert storage_bytes(path) == dict(db=0, wal=0, shm=0)
    for suffix, size in [('', 100), ('-wal', 200), ('-shm', 30)]:
        Path(str(path) + suffix).write_bytes(b'x' * size)
    assert storage_bytes(path) == dict(db=100, wal=200, shm=30)


def test_synthetic_diagnostic_refuses_selected_cohort(tmp_path, monkeypatch):
    import asyncio
    from scripts.validate_evidence_load import validate
    monkeypatch.setenv('RADAR_COHORT', 'forbidden-fixture')
    with pytest.raises(ValueError, match='forbids cohort'):
        asyncio.run(validate(1, 1, 0, 0, tmp_path / 'no.json'))
    assert not (tmp_path / 'no.json').exists()


async def test_retained_endurance_shutdown_restart_and_delayed_provider(tmp_path):
    from scripts.validate_evidence_load import validate
    output = tmp_path / 'synthetic.json'
    result = await validate(12, 5, .1, 0, output, endurance=True)
    assert result['live_network_requests'] == 0 and not result['cohort_created']
    assert result['quote_provider_standin']['attempted'] == 1
    assert sum(v for k, v in result['quote_provider_standin'].items() if k != 'attempted') == 1
    assert result['final_accounting']['events']['trade']['reconciled']
    assert result['final_recovery']['accepted_reconciled']
    assert result['restart']['integrity'] == 'ok'
    assert result['restart']['restored_candidates'] == 250
    assert result['restart']['windows_empty']
    assert result['restart']['security_requires_refresh']
    assert result['restart']['paper_cash'] == 20 and result['restart']['positions'] == 0
    assert result['restart']['stopped_receipt']['status'] == 'STOPPED'
    assert result['restart']['storage_after_restart']['wal'] == 0
    assert result['restart']['storage_after_restart']['shm'] == 0
    assert output.with_suffix('.run').joinpath('synthetic.db').exists()
    assert output.with_suffix('.progress.json').exists()
    for sample in result['samples']:
        assert sum(sample['storage'].values()) <= result['storage_budget_bytes']
    # No final cancellation may retrospectively mutate a frozen sampled counter.
    assert result['samples'][0]['continuity']['global_resets'] == 0
    assert result['continuity']['global_resets'] == 1
    with pytest.raises(FileExistsError):
        await validate(1, 1, 0, 0, output, endurance=True)


def test_report_hash_roundtrips_nested_integer_keys_without_mutating_input():
    import hashlib
    import json
    from scripts.validate_evidence_load import seal_report
    original = {"scheduling": {"rolling": {1: 2, 5: 8, 10: 9}}}
    record = json.loads(json.dumps(seal_report(original)))
    digest = record.pop("sha256")
    assert hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest() == digest
    assert original == {"scheduling": {"rolling": {1: 2, 5: 8, 10: 9}}}
