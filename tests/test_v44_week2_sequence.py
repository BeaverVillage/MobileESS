from copy import deepcopy
from pathlib import Path
import pytest
import v44_week2_sequence as seq

def jobs():
    return [dict(day=d,arm=a,status='PREPARED' if (d,a) in seq.MAIN else 'BASELINE_QUEUED') for d in seq.old.DAYS for a in seq.old.ARMS]

def barrier():
    return dict(ready=[dict(day=d,arm=a,handoff={'sha256':'sealed'}) for d,a in seq.MAIN],excluded=[],
        all_preparations_resolved=True,Actual_started_before_barrier=False,cpu_placement=dict(slots=list(range(7))))

def test_main_barrier_covers_14_main_cases_and_does_not_wait_for_baselines():
    assert len(seq.validate_main_barrier(barrier())['ready'])==14

def test_baseline_case_cannot_replace_unresolved_main_case():
    b=barrier();b['ready'][-1].update(day='2025-05-14',arm='B2')
    with pytest.raises(PermissionError,match='ALL_14_MAIN'):seq.validate_main_barrier(b)

def test_one_main_failure_does_not_block_other_main_actuals():
    b=barrier();j=b['ready'].pop();j.pop('handoff');j['exclusion_reason']='Native limit'
    b['excluded'].append(j);assert len(seq.validate_main_barrier(b)['ready'])==13

def test_baseline_is_blocked_until_every_main_actual_is_terminal(monkeypatch):
    state=dict(jobs=jobs());state['jobs'][1]['status']='ACTUAL_RUNNING'
    monkeypatch.setattr(seq,'publish',lambda *a:None)
    with pytest.raises(PermissionError,match='MAIN_NOT_FINISHED'):seq.baseline_serial(state,{})

def test_baseline_one_full_worker_finishes_before_next_day_arm(monkeypatch,tmp_path):
    rows=jobs()
    for j in rows:
        if seq.key(j) in seq.MAIN:j['status']='PASS'
    # The old failed reference remains excluded, without a duplicate attempt.
    rows[0]['status']='EXCLUDED'
    state=dict(jobs=rows);events=[];active=[]
    monkeypatch.setattr(seq,'CAMPAIGN',tmp_path)
    monkeypatch.setattr(seq,'STOP',tmp_path/'STOP.json')
    monkeypatch.setattr(seq,'publish',lambda *a:None)
    def request(job,lease,mode):
        assert not active and mode=='BASELINE_FULL';events.append(('plan_then_actual',seq.key(job)))
        job['status']='BASELINE_RUNNING';return Path(job['day']+'_'+job['arm'])
    class Process:
        returncode=0
        def poll(self):return 0
    def launch(path,label):
        assert not active and label=='full_case';p=Process();active.append(p);return p
    def collect(process,job,planning=False,baseline=False):
        assert not planning and baseline and active==[process]
        events.append(('actual_finished',seq.key(job)));active.clear();job['status']='PASS'
    monkeypatch.setattr(seq,'new_request',request);monkeypatch.setattr(seq,'launch',launch);monkeypatch.setattr(seq,'collect',collect)
    seq.baseline_serial(state,{'pid':1})
    expected=list(seq.BASELINE)[1:]
    assert events==[(event,k) for k in expected for event in ('plan_then_actual','actual_finished')]
    assert rows[0]['status']=='EXCLUDED' and all(j['status']=='PASS' for j in rows[1:])

def test_baseline_pending_does_not_prevent_main_group_terminal():
    rows=jobs()
    for j in rows:
        if seq.key(j) in seq.MAIN:j['status']='EXCLUDED' if j['day']=='2025-05-08' else 'PASS'
    assert seq.main_resolved(rows)
