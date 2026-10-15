"""Small Native0 diagnostics; never construct a solver or OpenDSS engine."""
from copy import deepcopy

import numpy as np
import pytest

from v42_integration.rc02_voltage_audit import (
    episode_roster, integrated_gpu, experiment_inputs, time_fields, violation_cells)


def fixture():
    initial = dict(running=[dict(uid='initial', site='AIDC01', gpu=2, observed_start_seconds=-900)])
    queues = [dict(job_uid='initial', admitted_time=-900, completion_observed_time=450,
                   site='AIDC01', GPU_gang=2, migration_count=0, origin_unknown=False),
              dict(job_uid='known', admitted_time=0, completion_observed_time=1200,
                   site='AIDC02', GPU_gang=1, migration_count=0, origin_unknown=False),
              dict(job_uid='unknown', admitted_time=900, completion_observed_time=None,
                   site='AIDC01', GPU_gang=1, migration_count=0, origin_unknown=True)]
    starts = [dict(uid='known',time_seconds=0,site='AIDC02',GPU=1,origin_unknown=False),
              dict(uid='unknown',time_seconds=900,site='AIDC01',GPU=1,origin_unknown=True)]
    return initial, queues, starts


@pytest.mark.parametrize('label,expected', [('E0',{'initial'}),('E1',{'initial','known'}),
    ('E2',{'initial','known','unknown'}),('E3',{'initial','known','unknown'})])
def test_ablation_never_reschedules_observed_episode(label,expected):
    initial, queues, starts = fixture()
    rows = episode_roster(initial,queues,starts,label=label,begin=0,end=1800)
    assert {r['uid'] for r in rows} == expected
    assert rows[0]['start_seconds'] == -900


def test_observed_completion_integral_is_not_previous_tick_gpu_hold():
    initial, queues, starts = fixture()
    rows = episode_roster(initial,queues,starts,label='E2',begin=0,end=1800)
    gpu = integrated_gpu(rows,('AIDC01','AIDC02'),0,2)
    np.testing.assert_array_equal(gpu,[[1.,1.],[1.,1/3]])


@pytest.mark.parametrize('field,value', [('site','AIDC02'),('GPU_gang',3),('admitted_time',-800)])
def test_initial_site_start_gpu_source_drift_rejected(field,value):
    initial, queues, starts = fixture()
    queues[0][field] = value
    with pytest.raises(ValueError,match='INITIAL_RUNNING_SOURCE_DRIFT'):
        episode_roster(initial,queues,starts,label='E0',begin=0,end=1800)


def test_initial_running_cannot_be_restarted():
    initial, queues, starts = fixture()
    starts.append(dict(uid='initial'))
    with pytest.raises(ValueError,match='INITIAL_RUNNING_RESTARTED'):
        episode_roster(initial,queues,starts,label='E2',begin=0,end=1800)


def test_no_unexplained_actual_start_or_migration():
    initial, queues, starts = fixture()
    with pytest.raises(ValueError,match='UNEXPLAINED_EXECUTED'):
        episode_roster(initial,queues,starts[:-1],label='E0',begin=0,end=1800)
    queues[1]['migration_count'] = 1
    with pytest.raises(ValueError,match='NONSTATIC'):
        episode_roster(initial,queues,starts,label='E1',begin=0,end=1800)


def test_native_seconds_separate_from_internal_iteration_count():
    fields = time_fields(1746021600,23)
    assert fields['local_time_AEST']=='2025-05-01T00:00:23+10:00'
    assert fields['native_seconds']==23 and fields['native_slot']==0
    assert fields['before_May01_begin'] is False
    assert fields['iteration_to_seconds_conversion'] is False


@pytest.mark.parametrize('time',[float('nan'),float('inf'),-1])
def test_invalid_native_time_fails_closed(time):
    with pytest.raises(ValueError):
        time_fields(1746021600,time)


def test_original_c1_uses_ablated_gpu_and_same_asof_weather():
    class Model:
        def recompute(self,gpu,sites,weather):
            assert weather==[{'t_wb_c':8}]
            return dict(PCC_P_kw=10+gpu, PCC_Q_kvar=gpu/2)
    initial, queues, starts = fixture()
    roster = episode_roster(initial,queues,starts,label='E0',begin=0,end=1800)
    prefix = [dict(slot=t,start_seconds=t*900,end_seconds=(t+1)*900,
                   observations=dict(weather=dict(values=dict(t_wb_c=8)))) for t in range(2)]
    rows = experiment_inputs(roster,prefix,('AIDC01','AIDC02'),Model())
    assert rows[0]['P']==[11.,10.] and rows[1]['P']==[10.,10.]
    assert rows[0]['observations']==prefix[0]['observations']


def test_all_voltage_cells_are_recorded_and_hold_has_physical_duration():
    row = dict(experiment='E0',slot=0,native_seconds=23,native_step=4,
        event=dict(kind='NATIVE_QUEUED_EVENT',control_iterations=2,electrical_iterations=5,solution_converged=True),
        physical=dict(nodes=[dict(node_phase='sta.1',voltage_pu=1.051),
            dict(node_phase='sta.2',voltage_pu=.92),dict(node_phase='sta.3',voltage_pu=1.05)]),
        control_context_sha='c',physical_sha='p',SVR_sha='s')
    inputs=[dict(P=[1],Q=[2],GPU=[3],observations={})]
    mess=dict(P_by_site={'STA01':[0]},Q_by_site={'STA01':[392]})
    cells=violation_cells(row,25,1746021600,inputs,mess)
    assert len(cells)==2 and {r['phase'] for r in cells}=={'1','2'}
    assert all(r['physical_hold_seconds']==2 and not r['internal_iteration_sample'] for r in cells)
    assert all(r['control_iterations']==2 and r['native_seconds']==23 for r in cells)
    assert cells[0]['MESS_Q_kvar']=={'STA01':392}
    with pytest.raises(ValueError,match='BACKWARDS'):
        violation_cells(row,21,1746021600,inputs,mess)
