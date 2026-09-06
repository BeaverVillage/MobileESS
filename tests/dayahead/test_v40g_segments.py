from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import numpy as np
import pytest
from tests.dayahead.test_v40f_min_rho import setup
from tests.dayahead.test_v40g_joint import Wan
from tests.dayahead.test_v40a_coordination import trajectory
from dayahead.v40g.domain import options, materialize
from dayahead.v40g_segments.canonical import import_frozen, validate, identities, occupancy, terminal, terminal_audit, wan_audit, planning_power, deviation


def migrant():
    ctx, row = setup()
    row.update(state_at_issue='RUNNING', start_slot=0, end_slot=29,
        safe_duration_slots=29, safe_duration_seconds=26100., migration_destination=None,
        submit_time='2025-04-29T18:00:00+10:00', requested_walltime_seconds=100000.)
    opt = next(o for o in options(row, ctx.capacity, Wan(), {'one': 900.}) if o.migrated)
    return import_frozen([materialize(row, opt, ctx.capacity, Wan())])[0]


def context96():
    from dayahead.v38.authority import CapacityAuthority, RackPool
    ctx, row = setup(); sites = tuple(f'AIDC{i:02}' for i in range(1, 13))
    ctx.capacity = CapacityAuthority(site_capacity={s: 2 for s in sites}, historical_site_capacity={s: 2. for s in sites},
        rack_pools=tuple(RackPool(s, s + '_LP01', 2.) for s in sites), source_sha256='toy')
    w = np.array([.4] + [.1] * 11 + [-.05, 0.]); c = ctx.coefficients[0]
    c = replace(c, control_names=tuple([f'aidc_load_kw[{s}]' for s in sites] + ['mess_p_kw[STA01]', 'mess_q_kvar[STA01]']),
        anchor=np.zeros(14), voltage_matrix=np.zeros((14, 1)), current_matrix=np.column_stack([w / 10, w / 10]),
        flow_p_matrix=np.array([w, w]), flow_q_matrix=np.zeros((2, 14)))
    ctx.coefficients = tuple(replace(c, slot=t) for t in range(96))
    ctx.tables = {s: np.tile([[0., 1., 2.]], (96, 1)) for s in sites}
    row['migration_destination'] = None
    return ctx, import_frozen([row])[0]


def test_canonical_normalization_and_pause_conserve_service():
    row = migrant(); a, b = row['compute_segments']; e = row['migration_events'][0]
    gpu, contributions = occupancy([row], ('AIDC01', 'AIDC02'))
    assert gpu[a['end'] - 24:b['start'] - 24].sum() == 0
    assert sum(s['end'] - s['start'] for s in (a, b)) == row['safe_duration_slots']
    assert e['checkpoint'] < e['restart_end']
    assert len({(r['job_uid'], r['slot']) for r in contributions}) == len(contributions)
    assert import_frozen([row]) == [row]
    assert deviation(row, row) == 0


@pytest.mark.parametrize('damage', ['missing', 'collapsed', 'overlap', 'bytes', 'path', 'first_placement', 'ready'])
def test_invalid_migration_fails_closed(damage):
    row = migrant()
    if damage == 'missing':
        row.pop('segment_schema'); row.pop('compute_segments')
    elif damage == 'collapsed': row['compute_segments'] = [{'site': row['AIDC_site'], 'start': 0, 'end': row['safe_duration_slots']}]
    elif damage == 'overlap': row['compute_segments'][1]['start'] = 1
    elif damage == 'bytes': row['migration_events'][0]['bytes_by_slot'][2] += 1
    elif damage == 'path': row['migration_events'][0]['fixed_path_id'] = 'UNAUTHORIZED'
    elif damage == 'first_placement': row['state_at_issue'] = 'PENDING'
    elif damage == 'ready': row['frozen_execution_ready_slot'] += 1
    with pytest.raises(ValueError): import_frozen([row])


def test_terminal_uses_source_pause_and_destination_states():
    row = migrant(); a, b = row['compute_segments']; e = row['migration_events'][0]
    for h, state, site in [(24, 'RUNNING', a['site']), (e['checkpoint'], 'MIGRATING', a['site']),
                            (e['ready'], 'MIGRATING', b['site']), (b['start'], 'RUNNING', b['site'])]:
        r = terminal(row, horizon=h)
        assert r['state_at_H'] == state and r['site_at_H'] == site
        assert r['WAN_bytes_sent'] + r['WAN_bytes_remaining'] == e['payload_bytes']
    assert terminal(row, horizon=b['start'])['post_H_site'] == b['site']
    assert terminal_audit([row], [row])['status'] == 'PASS'
    assert wan_audit([row], Wan())['migration_count'] == 1


@pytest.mark.parametrize('residual', [4, 25, 29.125, 125.5])
def test_actual_realized_service_and_terminal_equivalence(residual):
    from dayahead.v40g_segments.actual import replay_jobs
    from dayahead.v40g.actual import replay_jobs as prior_replay
    from dayahead.v40d_actual.rack_dispatch import Rack
    row = migrant(); issue = datetime(2025, 4, 30, 18, tzinfo=timezone(timedelta(hours=10)))
    obs = {'one': {'start_time': issue - timedelta(hours=1), 'end_time': issue + timedelta(seconds=residual * 900), 'gpus_requested': 1}}
    args = dict(issue_time=issue, site_capacity={'AIDC01': 2, 'AIDC02': 2}, racks=[Rack(s, s + '_LP01', 2) for s in ('AIDC01', 'AIDC02')])
    r = replay_jobs([row], obs, **args); old = prior_replay([row], obs, **args)
    final = r['job_ledger'][0]; parts = final['actual_compute_segments']
    assert sum((s['end'] - s['start']) for s in parts) == residual
    assert parts == old['job_ledger'][0]['actual_compute_segments']
    assert r['site_occupancy'] == old['site_occupancy']
    if residual > 120:
        assert final['terminal_segment_state']['site_at_H'] == row['AIDC_site']
        assert final['terminal_segment_state']['post_H_site'] == row['AIDC_site']
    assert wan_audit(r['job_ledger'], Wan(), actual=True)['migration_count'] == int(residual > row['migration_events'][0]['checkpoint'])


def test_segment_a1_solver_keeps_migrated_running_and_moves_pending():
    from dayahead.v40g_segments.feedback import solve_feedback
    ctx, pending = context96(); pending['job_uid'] = 'pending'; pending.update(start_slot=28, end_slot=29, RSP_start_slot=28, RW_completion_slot=29)
    pending['compute_segments'] = [{'site': pending['AIDC_site'], 'start': 28, 'end': 29}]
    running = migrant(); result = solve_feedback([running, pending], trajectory(), ctx)
    assert result['status'] == 'PASS'
    assert identities([result['jobs'][0]]) == identities([running])
    assert result['jobs'][1]['AIDC_site'] != 'AIDC01'
    assert result['terminal_audit']['status'] == 'PASS'


def test_b1_a0_exact_reuse_rejects_segment_drift_without_optimize(tmp_path, monkeypatch):
    import gurobipy as gp
    from dayahead.paper_analysis.storage import write_json
    from dayahead.v40a.invariants import digest
    from dayahead.v40g_segments.b3 import bind_b1
    ctx, _ = context96(); jobs = [migrant()]; power = planning_power(jobs, ctx)
    p, z = tmp_path / 'B1.json', tmp_path / 'B1.npz'
    write_json(p, {'status': 'PASS', 'diagnostic_only': False, 'jobs': jobs,
        'final_decision_SHA': digest(jobs), 'GPU': power['gpu'], 'PCC': power['pcc']})
    np.savez_compressed(z, **power)
    monkeypatch.setattr(gp.Model, 'optimize', lambda *a, **k: pytest.fail('A0 must never optimize'))
    handle = bind_b1(p, z, ctx, tmp_path / 'A0')
    assert handle.load(ctx)[0] == jobs
    assert (tmp_path / 'A0/B1_FINAL_AS_A0.json').read_bytes() == p.read_bytes()
    altered = deepcopy(jobs); altered[0]['migration_events'][0]['checkpoint'] += 1
    write_json(handle.canonical_path, altered)
    with pytest.raises(ValueError, match='CANONICAL_B1_FILE_DRIFT'): handle.load(ctx)


def test_b3_callbacks_receive_true_segment_power_and_fixed_aidc():
    from dayahead.v40g_segments.b3 import coordinate_segments
    ctx, _ = context96(); jobs = [migrant()]; expected = planning_power(jobs, ctx)['pcc']; calls = []
    def search(pcc, cert):
        calls.append('M1'); assert np.array_equal(pcc, expected)
        assert cert['segment_and_event_SHA'] == identities(jobs)['segment_and_event_SHA']
        return trajectory(), {}
    def feedback(j, m): calls.append('A1'); return {'status': 'PASS', 'jobs': deepcopy(j)}
    def recourse(pcc, m, cert):
        calls.append('MF'); assert np.array_equal(pcc, expected)
        return {'status': 'PASS', 'trajectory': m}
    result = coordinate_segments(jobs, ctx, search, feedback, recourse, {'frozen': 'toy'})
    assert calls == ['M1', 'A1', 'MF'] and result['B3_A0_optimize_calls'] == 0
    assert identities(result['a1']) == identities(jobs)


@pytest.mark.parametrize('stage', ['A1_segments', 'MF_PCC', 'MF_route'])
def test_b3_forbids_canonical_mutation_or_route_reselection(stage):
    from dayahead.v40g_segments.b3 import coordinate_segments
    ctx, _ = context96(); jobs = [migrant()]
    def feedback(j, m):
        altered = deepcopy(j)
        if stage == 'A1_segments': altered[0]['compute_segments'][1]['site'] = 'AIDC03'
        return {'status': 'PASS', 'jobs': altered}
    def recourse(pcc, m, cert):
        if stage == 'MF_PCC': pcc[0, 0] += 1
        if stage == 'MF_route': return {'status': 'PASS', 'trajectory': trajectory(service='STA02')}
        return {'status': 'PASS', 'trajectory': m}
    kwargs = (jobs, ctx, lambda p, cert: (trajectory(), {}), feedback, recourse, {'frozen': 'toy'})
    if stage != 'MF_route':
        with pytest.raises(ValueError): coordinate_segments(*kwargs)
    else:
        result = coordinate_segments(*kwargs)
        assert not result['FINAL_PQ_RECOURSE_ACCEPTED'] and result['mf'] == result['m1']


def test_production_b3_gate_blocks_before_m1(tmp_path):
    from dayahead.v40g_segments.b3 import run
    from dayahead.v40g_segments.authority import REL
    from dayahead.paper_analysis.storage import write_json
    write_json(tmp_path / REL / 'EXECUTION_AUTHORIZATION.json', {'B2_B3_AUTHORIZED': 'NO'})
    with pytest.raises(ValueError, match='B2_B3_EXECUTION_NOT_AUTHORIZED'): run(tmp_path, None, None, None, None)
