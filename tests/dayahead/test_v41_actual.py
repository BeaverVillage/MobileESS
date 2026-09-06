from datetime import datetime, timedelta, timezone
from copy import deepcopy
import pytest
from dayahead.v40g_segments.canonical import import_frozen
from dayahead.v40d_actual.rack_dispatch import Rack
from dayahead.v41.actual import replay_jobs, compare_occupancy
from tests.dayahead.test_v40f_min_rho import setup


def fixture():
    ctx, job = setup()
    issue = datetime(2025, 4, 30, 8, tzinfo=timezone.utc)
    job.update(submit_time=(issue - timedelta(days=1)).isoformat(), requested_walltime_seconds=900.)
    obs = {'one': {'start_time': issue + timedelta(days=2), 'end_time': issue + timedelta(days=2, seconds=1801), 'gpus_requested': 1}}
    return job, obs, dict(issue_time=issue, site_capacity=ctx.capacity.site_capacity,
                         racks=[Rack(s, s + '_LP01', 2) for s in ctx.capacity.aidc_ids])


def test_actual_replaces_runtime_preserves_policy_start_site_rack():
    job, obs, kwargs = fixture(); frozen = import_frozen([job]); before = deepcopy(frozen)
    result = replay_jobs(frozen, obs, **kwargs); row = result['job_ledger'][0]
    assert row['actual_execution_start'] == 24
    assert row['actual_execution_end'] == 24 + 1801 / 900
    assert row['actual_Rack'] == job['Rack_label']
    assert row['actual_compute_segments'][0]['site'] == job['AIDC_site']
    assert result['GPU'][:3, 0].tolist() == [1, 1, 1]
    assert frozen == before and result['counters']['Actual_optimizer_calls'] == 0


def test_unselected_policy_is_explicit_backlog_no_historical_policy_record():
    job, obs, kwargs = fixture(); job.update(AIDC_site='UNASSIGNED', Rack_label=None)
    result = replay_jobs(import_frozen([job]), obs, **kwargs); row = result['job_ledger'][0]
    assert row['status'] == 'FROZEN_UNADMITTED_BACKLOG'
    assert row['actual_compute_segments'] == [] and row['actual_execution_start'] is None
    assert row['backlog_GPU_hours'] == 1801 / 3600
    assert result['GPU'].sum() == 0


def test_realized_overload_is_reported_without_rescheduling_or_clipping():
    job, obs, kwargs = fixture()
    jobs = [job, {**job, 'job_uid': 'two'}, {**job, 'job_uid': 'three'}]
    obs.update(two=obs['one'], three=obs['one'])
    result = replay_jobs(import_frozen(jobs), obs, **kwargs)
    assert result['capacity_audit']['status'] == 'FAIL'
    assert result['GPU'][0, 0] == 3
    assert all(r['actual_execution_start'] == 24 for r in result['job_ledger'])
    with pytest.raises(ValueError, match='FROZEN_ACTUAL_SITE_CAPACITY_EXCEEDED'):
        compare_occupancy(result, kwargs['site_capacity'])


def test_missing_actual_runtime_is_real_data_error():
    job, obs, kwargs = fixture()
    with pytest.raises(ValueError, match='REALIZED_RUNTIME_MISSING'):
        replay_jobs(import_frozen([job]), {}, **kwargs)


def test_running_migration_retains_frozen_checkpoint_and_ready():
    from tests.dayahead.test_v40g_joint import Wan
    from dayahead.v40g.domain import options, materialize
    ctx, job = setup(); base, obs, kwargs = fixture()
    job = {**base, 'state_at_issue': 'RUNNING', 'start_slot': 0, 'end_slot': 29,
           'safe_duration_slots': 29, 'safe_duration_seconds': 26100., 'initial_Rack_label': base['Rack_label']}
    opt = next(o for o in options(job, ctx.capacity, Wan(), {'one': 900.}) if o.migrated)
    frozen = import_frozen([materialize(job, opt, ctx.capacity, Wan())])
    issue = kwargs['issue_time']; obs['one'].update(start_time=issue-timedelta(hours=1), end_time=issue+timedelta(hours=9))
    result = replay_jobs(frozen, obs, **kwargs); row = result['job_ledger'][0]
    assert row['actual_compute_segments'][0]['end'] == opt.checkpoint
    assert row['actual_compute_segments'][1]['start'] == opt.transfer_end + 1
    assert sum((s['end'] - s['start']) * 900 for s in row['actual_compute_segments']) == 9 * 3600
    assert row['migration_events'] == frozen[0]['migration_events']
