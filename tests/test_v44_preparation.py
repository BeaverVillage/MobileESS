"""Offline fixtures only: no model, optimize, Actual or OpenDSS is called."""
import ast
from copy import deepcopy
from datetime import datetime
import multiprocessing as mp
from pathlib import Path
from types import SimpleNamespace

import pytest

from v44.common import atomic,read,digest
from v44.config import DAYS,MAIN_ORDER,axis,KNOWN_POLICY
from v44.scheduler import assignments
from v44.stages import require_m1,require_a2,m_outcome,next_stage
from v44.budget import StageBudget,resume
from v44.locks import coordinator,worker_slot,alive,new_attempt


def case(day='2025-05-01',arm='B2',stage='M1'):
    identity=dict(day=day,arm=arm,stage=stage,source_sha=digest('fixture'))
    return SimpleNamespace(identity=identity,case_sha=digest(identity))


def m1(day='2025-05-01',**updates):
    c=digest(dict(day=day,case='fixture'))
    plan=dict(case_sha=c,P_sign='POSITIVE_GRID_INJECTION_Pdis_MINUS_Pch',time_axis=list(range(96)),
        P_by_site={'STA01':[3.]*96},Q_by_site={'STA01':[-2.]*96},
        P_kW={u:[3.]*96 for u in ('MESS01','MESS02','MESS03','MESS04')},
        Q_kvar={u:[-2.]*96 for u in ('MESS01','MESS02','MESS03','MESS04')},
        case_binding=dict(case_sha=c,arm='B3',stage='M1',day=day))
    plan['plan_sha']=digest(plan)
    return dict(day=day,arm='B3',stage='M1',case_sha=c,finished_UTC='fixture',error=None,
        M_stage_execution_PASS=True,FULL_feasible=True,upper=dict(FULL_validated=True),MESS_plan=plan,
        fixed_AIDC=dict(day=day,arm='B1',stage='A1',reused_exact_A1=True),timeout=True,
        global_LB=.4,global_UB=.6,independent_Global_LB_validated=True,LB_origin='K48_INDEPENDENT_GLOBAL',**updates)


@pytest.mark.parametrize('day',DAYS)
def test_seven_axes(day):
    a=axis(day)
    assert a['day_start_seconds']-a['issue_seconds']==21600
    assert a['end_seconds']-a['issue_seconds']==120*900
    assert a['end_seconds']-a['day_start_seconds']==96*900
    assert datetime.fromisoformat(a['issue_UTC']).timestamp()==datetime.fromisoformat(a['issue_KST']).timestamp()==a['issue_seconds']
    assert a['begin_AEST'].startswith(day)


def test_scheduler_keeps_two_distinct_b2_and_delays_main():
    first=assignments({},[])
    assert [(r['day'],r['arm'],r['worker_slot']) for r in first]==[(DAYS[0],'B2',1),(DAYS[1],'B2',2)]
    second=assignments({(DAYS[0],'B2'):'COMPLETE'},[first[1]])
    assert len(second)==1 and second[0]['day']==DAYS[2] and second[0]['worker_slot']==1
    assert assignments({(d,'B2'):'BLOCKED' for d in DAYS},[])==[dict(day=DAYS[0],arm='B0',worker_slot=1,lane='MAIN')]
    assert assignments({},[dict(day=DAYS[0],arm='B1',worker_slot=1)])==[]


def test_independent_failure_does_not_kill_other_days():
    pending=assignments({(DAYS[0],'B2'):'FAILED',(DAYS[1],'B2'):'INPUT_NOT_READY'},[])
    assert [p['day'] for p in pending]==list(DAYS[2:4])
    assert len(MAIN_ORDER)==21


@pytest.mark.parametrize('arm,stage',[('B2','M1'),('B3','M1'),('B3','M2')])
def test_900_300_separate_measured_native_clocks(tmp_path,arm,stage):
    c=case(arm=arm,stage=stage)
    k=StageBudget(tmp_path/'K.json',case=c,kind='K48_SEPARATE')
    j=StageBudget(tmp_path/'J.json',case=c,kind='PLANNING_NATIVE')
    assert (k.native_limit,j.native_limit)==(300,900)
    k.charge(300.07);j.charge(899)
    assert k.remaining()==0 and j.remaining()==1
    j._call_cap=140
    assert j.remaining()==1
    j.charge(1.05)
    assert j.remaining()==0
    receipt=read(tmp_path/'J_MEASURED_CEILING_OVERRUN.json')
    assert receipt['overrun_seconds']==pytest.approx(.05) and not receipt['next_native_call_permitted']


def test_resume_keeps_same_stage_native_once_and_rejects_inflight(tmp_path):
    c=case();j=StageBudget(tmp_path/'old.json',case=c,kind='PLANNING_NATIVE')
    j.calls=[dict(Native_Runtime=123.,status='FINISHED')];j.charge(123.)
    restored=resume(j.path,case=c,kind=j.kind,destination=tmp_path/'resume.json')
    assert restored.used()==123 and restored.remaining()==777
    with pytest.raises(ValueError,match='CROSS_CASE'):resume(j.path,case=case(stage='M2'),kind=j.kind,destination=tmp_path/'bad.json')
    old=read(j.path);old['inflight']=dict(status='IN_FLIGHT');atomic(j.path,old)
    with pytest.raises(ValueError,match='INFLIGHT'):resume(j.path,case=c,kind=j.kind,destination=tmp_path/'bad2.json')


@pytest.mark.parametrize('day',DAYS)
def test_m1_full_timeout_transfers_without_global_gap_claim(day):
    r=m1(day);out=m_outcome(r)
    assert out['status']=='TIME_LIMIT_FULL_FEASIBLE_GAP_NOT_CERTIFIED'
    assert out['allow_downstream'] and not out['global_gap_certified']
    assert require_m1(r,day)['plan_sha']==r['MESS_plan']['plan_sha']


@pytest.mark.parametrize('field,value',[('FULL_feasible',False),('M_stage_execution_PASS',False),('error','crash'),
    ('finished_UTC',None),('implementation_errors',['failure'])])
def test_failed_or_incomplete_m1_cannot_be_a2_parent(field,value):
    r=m1();r[field]=value
    with pytest.raises(ValueError):require_m1(r,DAYS[0])


def test_bound_origin_cannot_promote_restricted_or_nan_lb():
    r=m1();r['LB_origin']='BEAM_RESTRICTED_OBJBOUND'
    out=m_outcome(r)
    assert out['allow_downstream'] and out['LB_status']=='GLOBAL_LB_NOT_CERTIFIED' and out['Global_Gap'] is None
    r['LB_origin']='K48_INDEPENDENT_GLOBAL';r['global_LB']=float('nan')
    assert m_outcome(r)['LB_status']=='GLOBAL_LB_NOT_CERTIFIED'


def test_no_full_incumbent_blocks_only_current_descendants():
    r=m1();r.update(FULL_feasible=False,upper=dict(FULL_validated=False))
    assert m_outcome(r)['status']=='TIME_LIMIT_NO_FULL_FEASIBLE_INCUMBENT'
    completed={s:dict(PASS=True) for s in ('A1_REUSE','K48_M1')};completed['M1']=r
    assert next_stage(DAYS[0],'B3',completed)['status']=='BLOCKED_DEPENDENCY'
    assert next_stage(DAYS[1],'B3',{},b1_a1={'same_day':True})['status']=='READY'


def test_cross_day_or_tampered_m1_plan_rejected():
    with pytest.raises(ValueError,match='CROSS_DATE'):require_m1(m1(),DAYS[1])
    r=m1();r['MESS_plan']['P_by_site']['STA01'][0]=99
    with pytest.raises(ValueError,match='SHA_OR_CASE'):require_m1(r,DAYS[0])


def test_a2_gap_half_percent_cannot_use_m_timeout_policy():
    r=dict(day=DAYS[0],arm='B3',stage='A2',finished_UTC='fixture',PASS=True,
        FULL_feasible=True,P2_calls=0,certified_gap=.005,independent_Global_LB_validated=True)
    assert require_a2(r,DAYS[0]) is r
    for key,value in [('certified_gap',.00501),('independent_Global_LB_validated',False),('P2_calls',1)]:
        with pytest.raises(ValueError):require_a2(dict(r,**{key:value}),DAYS[0])


def test_m2_stage_adapter_is_only_stage_and_profiling_boundary():
    from v42_may_campaign_native90.m_model import build_case
    from v44.frozen.v43_mess.performance import profiled_build
    routed=profiled_build(build_case,stage='M2')
    assert routed._v43_stage_route==dict(M_authority=2,A_parent=1,native_stage=1,deadline=1)
    source=ast.parse(__import__('textwrap').dedent(__import__('inspect').getsource(build_case)))
    def rows(tree):
        return [ast.dump(n) for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)
            and n.func.attr in ('addVar','addConstr','addMConstr','setObjective')]
    assert rows(source)==rows(routed._v43_profiled_ast)


def test_a2_paths_accept_exact_seven_days_and_b3():
    import v42_may_campaign_native90.a_stage as original
    from v44.a2 import routed_function
    for day in DAYS:
        ns=dict(original.__dict__);f,_=routed_function(original,'_paths',ns,m1(day)['MESS_plan'],day)
        request=dict(day=day,arm='B3',input_folder='D:/fixture_input',output='D:/fixture_output')
        assert f(request)[0]==day
        with pytest.raises(ValueError):f(dict(request,day='2025-05-08'))
        with pytest.raises(ValueError):f(dict(request,arm='B1'))


def test_a2_acceptance_arithmetic_same_and_proofs_do_not_claim_a1():
    from v44.frozen.v43_a2.adapter import a2_contract,routed_function
    import v42_may_campaign_native90.a_stage as original
    decision=lambda x:dict(A1_P1_ONLY_ACCEPTED=x<=.005,A1_ACCEPTED=False,gap=x,UB=.67,LB=.669)
    receipt=a2_contract(decision)(.005)
    assert receipt==dict(A2_P1_ONLY_ACCEPTED=True,A2_full_hierarchy_accepted=False,gap=.005,UB=.67,LB=.669,stage='A2')
    ns=dict(original.__dict__)
    f,_=routed_function(original,'run',ns,m1()['MESS_plan'])
    assert '_v43_A2_contract' in f.__code__.co_names
    assert '_v43_A2_bind_proof' in f.__code__.co_names


def test_known_unknown_baseline_method_identity():
    from v44.actual_policy import controller_class,B3RelaxedKnownController,research_assumption
    from v43_corrective.known_window import RelaxedKnownController
    from v43_baseline.worker import BaselineController
    assert controller_class('B0') is controller_class('B2') is BaselineController
    assert controller_class('B1',KNOWN_POLICY) is RelaxedKnownController
    assert controller_class('B3',KNOWN_POLICY) is B3RelaxedKnownController
    for name in ('_known_decision','admit','completion','_measure','migration'):
        assert getattr(B3RelaxedKnownController,name) is getattr(RelaxedKnownController,name)
    assert B3RelaxedKnownController.submit.__code__ is RelaxedKnownController.submit.__code__
    assert not research_assumption()['Source_authority_promoted']
    with pytest.raises(ValueError):controller_class('B2',KNOWN_POLICY)


def _slot_child(root,lease,day,slot,entered,release,queue):
    try:
        with worker_slot(day,'B2',slot,root=Path(root),lease=lease):
            entered.set();release.wait(15);queue.put('OK')
    except Exception as exc:queue.put(repr(exc))


def test_real_two_process_os_slots_duplicate_prevention_and_crash_release(tmp_path):
    ctx=mp.get_context('spawn');release=[ctx.Event(),ctx.Event()];queue=ctx.Queue();events=[ctx.Event(),ctx.Event()]
    with coordinator(tmp_path,external=[]) as lease:
        atomic(tmp_path/'PHASE.json',dict(lane='B2'))
        workers=[ctx.Process(target=_slot_child,args=(str(tmp_path),lease,DAYS[i],i+1,events[i],release[i],queue)) for i in range(2)]
        try:
            for p in workers:p.start()
            entered=[e.wait(12) for e in events]
            assert all(entered),[queue.get(timeout=2) for ok in entered if not ok]
            assert len({p.pid for p in workers})==2
            with pytest.raises(Exception):
                with worker_slot(DAYS[0],'B2',2,root=tmp_path,lease=lease):pytest.fail('duplicate entered')
            with pytest.raises(Exception):
                with worker_slot(DAYS[2],'B2',1,root=tmp_path,lease=lease):pytest.fail('duplicate slot entered')
            workers[0].terminate();workers[0].join(10)
            import time
            from v42_may_campaign.common import LockBusy
            deadline=time.monotonic()+3
            while True:
                try:
                    with worker_slot(DAYS[0],'B2',1,root=tmp_path,lease=lease):pass
                    break
                except LockBusy:
                    if time.monotonic()>=deadline:raise
                    time.sleep(.025)
            assert not alive(dict(pid=workers[1].pid,process_created=0.))
            release[1].set();workers[1].join(10)
            assert queue.get(timeout=5)=='OK'
        finally:
            for i,p in enumerate(workers):
                if p.is_alive():
                    release[i].set();p.join(2)
                    if p.is_alive():p.terminate()
                p.join(10)


def test_new_attempt_no_overwrite_and_slot_file_isolation(tmp_path):
    first=new_attempt(DAYS[0],'B2','M1',1,root=tmp_path)
    second=new_attempt(DAYS[1],'B2','M1',1,root=tmp_path)
    assert first!=second and (first/'nodefiles').is_dir() and (second/'tmp').is_dir()
    with pytest.raises(FileExistsError):new_attempt(DAYS[0],'B2','M1',1,root=tmp_path)


def test_monitor_all_stage_fields_and_28_case_visibility():
    from v44.monitor import rows,render,FIELDS
    from v44.config import ARMS
    manifest=dict(cases=[dict(day=d,arm=a,status='INPUT_NOT_READY',blockers=['missing']) for d in DAYS for a in ARMS])
    data=rows(manifest,Path('D:/fixture_not_created'))
    assert len({(r['day'],r['arm']) for r in data})==28
    assert all(set(FIELDS)<=set(r) and r['Native_used'] is None for r in data)
    html=render(manifest,Path('D:/fixture_not_created'))
    assert 'PREPARE ONLY' in html and '900' in html and '2025-05-07' in html


def test_execute_needs_separate_permit_and_blocks_missing_inputs(tmp_path):
    from v44.prepare import require_execution_permit
    from v44.common import NotReady
    with pytest.raises(PermissionError):require_execution_permit(None,{})
    p=tmp_path/'permit.json';atomic(p,dict(explicit_user_approved=True,mode='EXECUTE'))
    with pytest.raises(NotReady):require_execution_permit(p,dict(status='V44_PRESTART_BLOCKED'))
