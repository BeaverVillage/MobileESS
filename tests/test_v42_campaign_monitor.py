"""Read-only display regressions; no native model creation or solve."""
from datetime import datetime, timezone
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from v42_campaign_monitor.monitor import build_progress, clean, enrich_worker, view


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf-8')


def stamp(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat()


@pytest.fixture
def worker(tmp_path):
    request = dict(output=str(tmp_path / 'output'), result=str(tmp_path / 'RESULT.json'), started_UTC=stamp(1000))
    write(tmp_path / 'request.json', request)
    write(tmp_path / 'NATIVE_RUNTIME_LEDGER.json', dict(calls=[], measured_Native_Runtime=0, inflight=None))
    return dict(arm='B1', day='2025-05-01', request=str(tmp_path / 'request.json'),
                started_UTC=stamp(1000), worker_alive=True, PID=123, worker_slot=1,
                heartbeat=dict(timestamp_UTC=stamp(1999)), resource={},
                progress=dict(phase='A_ORIGINAL_NATIVE_CONSTRUCTION', builder_phase='MODEL_BUILD',
                              timestamp_UTC=stamp(1100), Wall_Time=100, Native_Runtime=0))


def test_silent_builder_wall_clock_advances_without_inventing_native_runtime(worker):
    first, second = enrich_worker(worker, 2000), enrich_worker(worker, 2010)
    assert first['wall_seconds'] == 1000
    assert second['wall_seconds'] == 1010
    assert first['remaining_seconds'] == second['remaining_seconds'] == 5400
    assert second['reported_wall_seconds'] == 100
    assert first['Native_Runtime_seconds'] == second['Native_Runtime_seconds'] == 0
    assert first['report_delayed'] and first['heartbeat_recent']


def test_dead_worker_does_not_keep_advancing_last_report(worker):
    worker['worker_alive'] = False
    assert enrich_worker(worker, 5000)['wall_seconds'] == 100


def test_time_consumption_is_not_model_completion(worker, tmp_path):
    first = enrich_worker(worker, 2000)
    second = enrich_worker(worker, 5000)
    assert first['build']['percent'] == second['build']['percent'] == 0
    (tmp_path / 'output/STATIC/DATA').mkdir(parents=True)
    (tmp_path / 'output/STATIC/DATA/DATA.pkl').touch()
    result = enrich_worker(worker, 5000)
    assert result['build']['confirmed_steps'] == 1
    assert result['build']['percent'] == 20
    assert result['build']['basis'] == 'confirmed_milestones'


def test_data_classes_do_not_masquerade_as_generated_native_blocks(tmp_path):
    write(tmp_path / 'STATIC/DATA/SCIENTIFIC_JOB_CLASS_AUDIT.json', dict(jobs=1499, class_count=117))
    progress = dict(phase='A_ORIGINAL_NATIVE_CONSTRUCTION', builder_phase='MODEL_BUILD',
                    jobs_complete=1400, classes_complete=98)
    result = build_progress('B1', progress, tmp_path)
    assert result['classes'] == 117
    assert '완료 블록' not in result['counters']
    assert result['block_fraction'] is None
    assert result['confirmed_steps'] == 0


def test_complete_block_fraction_requires_actual_block_phase(tmp_path):
    progress = dict(phase='A_COMPLETE_NATIVE_BLOCKS', classes_complete=30, classes_required=100)
    result = build_progress('B1', progress, tmp_path)
    assert result['block_fraction'] == .3
    assert result['confirmed_steps'] == 3
    assert result['current'] == '클래스별 완전 블록'


def test_independent_aliases_are_used_and_solver_gap_is_not_certified(worker):
    worker['progress'].update(UB=1.1, BestBd=1.0, gap=.02)
    result = enrich_worker(worker, 2000)
    assert result['independent_Global_LB'] is result['Certified_Gap'] is None
    worker['progress']['Certified_Global_LB'] = 1.0
    result = enrich_worker(worker, 2000)
    assert result['Certified_Gap'] == pytest.approx(.1 / 1.1)
    worker['arm'] = 'B2'
    worker['progress'].pop('Certified_Global_LB')
    worker['progress']['global_LB'] = 1.05
    assert enrich_worker(worker, 2000)['independent_Global_LB'] == 1.05


def test_stale_or_invalid_timestamps_and_nonfinite_metrics_are_safe(worker):
    worker['progress'].update(timestamp_UTC='invalid', UB=float('inf'))
    worker['heartbeat'] = dict(timestamp_UTC='invalid')
    result = enrich_worker(worker, 2000)
    assert result['UB'] is result['heartbeat_age_seconds'] is result['solver_report_age_seconds'] is None
    assert json.dumps(clean(dict(x=float('nan'), y=[float('inf')])), allow_nan=False) == '{"x": null, "y": [null]}'


def test_three_b2_worker_clocks_and_objectives_are_isolated(worker, tmp_path):
    workers = []
    for slot in range(1, 4):
        request = tmp_path / str(slot) / 'request.json'
        write(request, dict(output=str(request.parent / 'output'), result=str(request.parent / 'RESULT.json')))
        workers.append(dict(worker, arm='B2', day=f'2025-05-0{slot}', worker_slot=slot,
                            request=str(request), started_UTC=stamp(1000 + 100 * slot),
                            progress=dict(phase='M_ADAPTIVE_U1', UB=1 + slot / 10, global_LB=1.0)))
    base = dict(workers=workers, completed=1, total_arm_dates=62)
    with patch('v42_campaign_monitor.monitor.original.view', return_value=base), patch('v42_campaign_monitor.monitor.time.time', return_value=2000):
        result = view(tmp_path)
    assert [r['wall_seconds'] for r in result['worker_slots']] == [900, 800, 700]
    assert [r['UB'] for r in result['worker_slots']] == [1.1, 1.2, 1.3]
    assert result['campaign_percent'] == pytest.approx(100 / 62)


def test_enrichment_never_changes_request_progress_or_ledger(worker, tmp_path):
    before = {str(p): p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    enrich_worker(worker, 2000)
    after = {str(p): p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    assert before == after


def test_verified_case_marks_model_complete(tmp_path):
    write(tmp_path / 'A_PREPARE_RECEIPT.json', dict(PASS=True))
    result = build_progress('B1', dict(phase='LONG_NATIVE_COMPONENT'), tmp_path)
    assert result['complete'] and result['percent'] == 100
    assert all(step['state'] == 'done' for step in result['steps'])
