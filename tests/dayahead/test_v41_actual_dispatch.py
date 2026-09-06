from copy import deepcopy
from datetime import timedelta
import numpy as np
import pandas as pd
import pytest
from dayahead.v40g_segments.canonical import import_frozen
from dayahead.v40d_actual.rack_dispatch import Rack
from dayahead.v41.actual_dispatch import replay_jobs,persist
from tests.dayahead.test_v41_actual import fixture


def contention_fixture():
    job,obs,kw=fixture(); issue=kw['issue_time']
    jobs=[]; observations={}
    for uid,start,duration in [('old_a',24,910),('old_b',24,910),('new_a',25,900),('new_b',26,900)]:
        jobs.append({**job,'job_uid':uid,'start_slot':start,'end_slot':start+1,'safe_duration_slots':1,
                     'safe_duration_seconds':900.,'RW_completion_slot':start+1})
        observations[uid]=dict(start_time=issue+timedelta(days=2),end_time=issue+timedelta(days=2,seconds=duration),gpus_requested=1)
    return import_frozen(jobs),observations,kw


def test_exact_ten_second_contention_delay_preserves_every_DA_decision(tmp_path):
    jobs,obs,kw=contention_fixture(); before=deepcopy(jobs)
    result=replay_jobs(jobs,obs,**kw); by={r['job_uid']:r for r in result['job_ledger']}
    assert jobs==before and by['new_a']['START_DELAY_SECONDS']==10.
    assert by['new_a']['actual_execution_start']==25+10/900
    assert by['new_a']['BLOCKING_JOB_IDS']==['old_a','old_b']
    assert all(r['ACTUAL_SITE']==r['DA_SITE'] and r['START_DELAY_SECONDS']>=0 for r in by.values())
    assert result['raw_runtime_contention']['naive_execution_feasibility']['max_exceedance_GPU']==1
    assert result['raw_runtime_contention']['naive_execution_feasibility']['violation_duration_site_seconds']==10
    assert result['exact_execution_feasibility']['status']=='PASS' and result['GPU'].max()<=2
    persist(tmp_path,result,obs,kw['issue_time'],kw['site_capacity'],kw['racks'])
    delayed=pd.read_parquet(tmp_path/'aidc/DELAYED_JOBS.parquet')
    assert len(delayed)==1 and delayed.job_id.iloc[0]=='new_a' and delayed.START_DELAY_SECONDS.iloc[0]==10
    events=pd.read_parquet(tmp_path/'aidc/RESOURCE_CHANGE_EVENTS.parquet')
    assert (events.GPU_occupancy_after<=events.GPU_capacity).all() and (events.GPU_occupancy_after>=0).all()
    overlap=pd.read_parquet(tmp_path/'aidc/EXACT_JOB_SLOT_OVERLAP.parquet')
    delayed_overlap=overlap[(overlap.job_id=='new_a')&(overlap.slot==1)].iloc[0]
    assert delayed_overlap.overlap_seconds==890 and delayed_overlap.slot_start_GPU==0
    assert overlap[overlap.job_id=='new_a'].overlap_seconds.sum()==900


def test_delay_propagates_and_tie_order_ignores_realized_runtime():
    jobs,obs,kw=contention_fixture(); kw['site_capacity']={'AIDC01':1,'AIDC02':2}
    jobs=import_frozen([dict(jobs[0],job_uid='one',segment_schema=None),dict(jobs[2],job_uid='two',segment_schema=None),
                        dict(jobs[3],job_uid='three',segment_schema=None)])
    issue=kw['issue_time']
    obs={uid:dict(start_time=issue+timedelta(days=2),end_time=issue+timedelta(days=2,seconds=d),gpus_requested=1)
         for uid,d in [('one',1000),('two',1800),('three',50)]}
    result=replay_jobs(jobs,obs,**kw); by={r['job_uid']:r for r in result['job_ledger']}
    assert by['two']['START_DELAY_SECONDS']==100 and by['three']['START_DELAY_SECONDS']==1000
    again=replay_jobs(list(reversed(jobs)),obs,**kw)
    assert result['job_ledger']==again['job_ledger']
    a=deepcopy(jobs[1]); a['job_uid']='a'; b=deepcopy(a); b['job_uid']='b'
    obs.update(a=obs['two'],b=obs['three'])
    tied=replay_jobs([b,a],obs,**kw); rows={r['job_uid']:r for r in tied['job_ledger']}
    assert rows['a']['START_DELAY_SECONDS']==0 and rows['b']['START_DELAY_SECONDS']==1800


def test_no_ML_Q90_or_global_optimizer_called(monkeypatch):
    import gurobipy as gp
    import lightgbm as lgb
    from dayahead.v41 import snapshot,workload
    def forbidden(*a,**k): raise AssertionError('ACTUAL_FORBIDDEN_MODEL_CALL')
    monkeypatch.setattr(gp.Model,'optimize',forbidden)
    monkeypatch.setattr(lgb.Booster,'predict',forbidden)
    monkeypatch.setattr(lgb.LGBMRegressor,'fit',forbidden)
    monkeypatch.setattr(snapshot,'create',forbidden)
    jobs,obs,kw=contention_fixture()
    result=replay_jobs(jobs,obs,**kw)
    assert result['counters']['Actual_optimizer_calls']==0 and result['counters']['migration_decision_changes']==0


def test_rack_and_gpu_are_hard_and_selected_jobs_are_never_dropped():
    jobs,obs,kw=contention_fixture(); kw['racks']=[Rack('AIDC01','AIDC01_LP01',1),Rack('AIDC02','AIDC02_LP01',2)]
    result=replay_jobs(jobs,obs,**kw)
    assert len(result['job_ledger'])==len(jobs) and result['execution_rate']['N_DA_SELECTED_JOBS']==4
    bad=deepcopy(jobs); bad[0]['requested_GPU']=2; changed=deepcopy(obs); changed['old_a']['gpus_requested']=2
    with pytest.raises(ValueError,match='RACK_INCOMPATIBLE'): replay_jobs(bad,changed,**kw)


def test_rates_include_horizon_incompletion_without_invented_carryover():
    jobs,obs,kw=contention_fixture(); jobs=jobs[:1]
    jobs[0].update(start_slot=119,end_slot=120,compute_segments=[dict(site='AIDC01',start=119,end=120)],RW_completion_slot=120)
    issue=kw['issue_time']; obs['old_a']['end_time']=issue+timedelta(days=2,seconds=1800)
    r=replay_jobs(jobs,obs,**kw); rates=r['execution_rate']
    assert rates['N_DA_SELECTED_JOBS']==rates['N_ACTUAL_STARTED_JOBS']==1 and rates['N_ACTUAL_COMPLETED_JOBS']==0
    assert rates['START_EXECUTION_RATE']==1 and rates['COMPLETION_RATE']==0
    assert rates['N_NOT_COMPLETED_BY_HORIZON']==1 and r['job_ledger'][0]['remaining_runtime_at_H']==900


def test_B0_retention_rejects_any_change_to_day_ahead_function():
    from dayahead.v41.retention import unchanged_nodes
    before='def dayahead():\n return 1\ndef actual():\n return 2\n'
    allowed={'actual'}
    assert unchanged_nodes(before,allowed)==unchanged_nodes(before.replace('return 2','return 3'),allowed)
    assert unchanged_nodes(before,allowed)!=unchanged_nodes(before.replace('return 1','return 4'),allowed)


def test_may01_aidc01_65_64_contention_resolves_exactly_10_seconds():
    from pathlib import Path
    from dayahead.paper_analysis.storage import read
    from dayahead.v41.data import issue_time
    f=read(Path(__file__).parents[1]/'fixtures/v41_may01_aidc01_contention.json')
    result=replay_jobs(f['jobs'],f['observations'],issue_time=issue_time('2025-05-01'),
        site_capacity={'AIDC01':64},racks=[Rack('AIDC01','AIDC01_LP01',64)])
    raw=result['raw_runtime_contention']; assert len(raw['intervals'])==1
    interval=raw['intervals'][0]
    assert interval['realized_GPU_occupancy']==65 and interval['GPU_capacity']==64 and interval['duration_seconds']==10
    assert interval['exact_start_AEST']=='2025-05-01T06:00:00+10:00'
    delayed=[r for r in result['job_ledger'] if r['START_DELAY_SECONDS']>0]
    assert [(r['job_id'],r['START_DELAY_SECONDS']) for r in delayed]==[(f['expected_delayed_job'],10.)]
    assert delayed[0]['ACTUAL_EXECUTION_START']=='2025-04-30T20:00:10+00:00'
    assert len(delayed[0]['BLOCKING_JOB_IDS'])==64 and result['GPU'].max()<=64
    assert result['exact_execution_feasibility']['violation_intervals']==0
