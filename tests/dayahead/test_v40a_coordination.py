from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
import pytest
from dayahead.v33m.mess_trajectory import MessTrajectory,MessTrajectorySlot
from dayahead.v40a.coordination import coordinate
from dayahead.v40a.invariants import validate_joint


def job():return dict(job_uid='a',state_at_issue='PENDING',qos='standby',requested_GPU=4,safe_duration_slots=10,
                     start_slot=30,end_slot=40,AIDC_site='AIDC01',post_H_site=None,migration_selected=False,migration_destination=None)


def trajectory(p=0,service='STA01'):
    return MessTrajectory((MessTrajectorySlot('MESS01',0,'CONNECTED',service,None,None,(),None,0,0,0,0,0,None,0,0,p,0,100,.5),))


def run(a1_status='PASS',mf_status='PASS',mf_route='STA01',bad_a1=False):
    calls=[]
    def evaluate(jobs,mess):
        j=1 if mess is None else .8-.01*mess.slots[0].p_kw
        if jobs[0]['start_slot']==31:j-=.1
        return {'status':'PASS','rho_max':j}
    def search(jobs):calls.append('M1');return trajectory(),{}
    def feedback(jobs,mess):
        calls.append('A1');assert mess.slots[0].service_id=='STA01'
        jobs[0]['start_slot']+=1;jobs[0]['end_slot']+=1
        if bad_a1:jobs[0].update(start_slot=115,end_slot=125,post_H_site='AIDC01')
        return {'status':a1_status,'jobs':jobs}
    def recourse(jobs,mess):calls.append('MF');return {'status':mf_status,'trajectory':trajectory(1,mf_route)}
    result=coordinate([job()],search,feedback,recourse,evaluate,{'inputs':'a'*64})
    return result,calls


def test_exactly_one_route_search_and_one_feedback():
    result,calls=run();assert calls==['M1','A1','MF']
    assert result['counts']['MESS_FULL_DISCRETE_ROUTE_SEARCH_CALLS']==1
    assert result['counts']['SECOND_MESS_FULL_ROUTE_SEARCH_CALLS']==0
    assert result['counts']['FRESH_CALLS_INSIDE_COOPT_LOOP']==0


def test_a1_infeasible_reverts_to_a0():
    r,_=run(a1_status='INFEASIBLE');assert not r['AIDC_FEEDBACK_ACCEPTED'] and r['a1']==r['a0']


def test_a1_terminal_violation_reverts_to_a0():
    r,_=run(bad_a1=True);assert not r['AIDC_FEEDBACK_ACCEPTED']


def test_mf_route_change_is_rejected():
    r,_=run(mf_route='STA02');assert not r['FINAL_PQ_RECOURSE_ACCEPTED'] and r['mf']==r['m1']


def test_mf_failure_retains_feasible_m1():
    r,_=run(mf_status='FAIL');assert not r['FINAL_PQ_RECOURSE_ACCEPTED'] and r['mf']==r['m1']


def test_objective_runtime_ledgers_complete_and_freeze_valid():
    r,_=run()
    assert set(r['objectives'])=={'J_A0','J_M1','J_A1','J_FINAL','DELTA_J_MESS','DELTA_J_AIDC_FEEDBACK','DELTA_J_FINAL_PQ','DELTA_J_TOTAL'}
    assert all(r['runtime'][k]>=0 for k in ('M1','A1','MF'))
    assert validate_joint(r['joint'])==r['joint']['FINAL_JOINT_DECISION_SHA']


@pytest.mark.parametrize('stage',['A1','MF'])
def test_input_trajectory_mutation_is_detected(stage):
    def evaluate(jobs,mess):return {'status':'PASS','rho_max':.5}
    def search(jobs):return trajectory(),{}
    def feedback(jobs,mess):
        if stage=='A1':object.__setattr__(mess.slots[0],'destination_service_id','STA99')
        return {'status':'PASS','jobs':jobs}
    def recourse(jobs,mess):
        object.__setattr__(mess.slots[0],'departure_slot',55)
        return {'status':'PASS','trajectory':mess}
    with pytest.raises(RuntimeError,match='MUTATED'):
        coordinate([job()],search,feedback,recourse,evaluate,{'inputs':'a'*64})
