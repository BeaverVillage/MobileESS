"""Exercise the production evidence writer with frozen April stage fixtures.

This test is not a May scientific result: optimization and AC are test doubles.
It checks integration and authoritative serialization before detached launch.
"""
from contextlib import nullcontext
from copy import deepcopy
from types import SimpleNamespace
from dayahead.v40b.common import REPO,V40A,read,write,sha

def test_production_b3_evidence_pipeline(tmp_path,monkeypatch):
    from dayahead.v40b import b3
    from dayahead.v40a import context,feedback,mobility,recourse,postfreeze
    from dayahead.v40a.invariants import validate_joint,digest
    from dayahead.v33m.mess_trajectory import MessTrajectory
    from dayahead.tools.run_v35r3e_r1_beam import _restore_slots
    source=V40A/'days/2025-04-01';checkpoint=read(source/'COOPT_PLANNING_CHECKPOINT.json')
    beam=read(source/'M1_FULL_SEARCH_RESULT.json')
    final=MessTrajectory(tuple(_restore_slots(checkpoint['mf'])))
    original_context=context.load_planning_context
    calls={'M1':0,'A1':0,'MF':0,'Fresh':0}
    def search(*args,**kwargs):calls['M1']+=1;return deepcopy(beam)
    def a1(*args,**kwargs):calls['A1']+=1;return {'jobs':deepcopy(checkpoint['a1']),'status':'PASS'}
    def mf(*args,**kwargs):calls['MF']+=1;return {'trajectory':deepcopy(final),'status':'PASS'}
    def verify(repo,day,jobs,trajectory,authority,context,output,writer,progress):
        def fresh(_jobs,_mess,joint_sha,_out):
            calls['Fresh']+=1
            return SimpleNamespace(schedule_sha256=joint_sha,summary={'physical_violation':False,'convergence_count':96})
        return postfreeze.verify_after_freeze(jobs,trajectory,authority,output,fresh_call=fresh,
           restore_call=lambda *a:(_ for _ in ()).throw(AssertionError('UNEXPECTED_RESTORATION')),
           validate_trajectory=lambda *a:None,max_rounds=0,write=writer)
    monkeypatch.setattr(b3,'ROOT',tmp_path)
    monkeypatch.setattr(b3,'admit_day',lambda d:nullcontext())
    monkeypatch.setattr(b3,'traffic_authority',lambda d:{'day':d,'test_fixture':True})
    monkeypatch.setattr(b3,'accepted_a0',lambda d,c:{'jobs':deepcopy(checkpoint['a0']),
       'source_SHAs':{},'RSP_base_materialization_seconds':0})
    monkeypatch.setattr(context,'load_planning_context',lambda r,d:original_context(r,'2025-04-01'))
    monkeypatch.setattr(mobility,'search_once',search)
    monkeypatch.setattr(feedback,'solve_feedback',a1)
    monkeypatch.setattr(recourse,'solve_fixed_route',mf)
    monkeypatch.setattr(postfreeze,'production_verification',verify)
    write(tmp_path/'V40B_V40A_METHOD_FREEZE.json',read(b3.REPO/'dayahead/artifacts/v40b_v40a_may_launch/V40B_V40A_METHOD_FREEZE.json'))
    write(tmp_path/'V40B_EXECUTION_FREEZE.json',{'execution_SHA':'TEST_DOUBLE_NOT_PRODUCTION'})
    certificate=b3.run('2025-05-01',lambda p:None)
    assert certificate['status']=='PASS' and calls=={'M1':1,'A1':1,'MF':1,'Fresh':1}
    root=tmp_path/'days/2025-05-01/B3'
    required=['AIDC_PASS0_DECISION.parquet','MESS_PASS1_TRAJECTORY.parquet','MESS_PASS1_GRID_FEEDBACK.json',
      'AIDC_FEEDBACK_PASS1_DECISION.parquet','AIDC_FEEDBACK_DELTA.csv','AIDC_FEEDBACK_GRID_RESULT.json',
      'MESS_FINAL_PQ_RECOURSE.parquet','COOPT_STAGE_OBJECTIVES.json','COOPT_RUNTIME_PROFILE.json',
      'COOPT_TERMINAL_AUDIT.json','COOPT_COUPLING_SUMMARY.json','FINAL_JOINT_DECISION.json',
      'FINAL_JOINT_DECISION_SHA256.json','PLANNING_PHYSICAL_GATES.json','FRESH_AC_RESULT.json']
    assert all((root/name).is_file() for name in required)
    final_sha=validate_joint(read(root/'FINAL_JOINT_DECISION.json'))
    assert final_sha==certificate['FINAL_JOINT_DECISION_SHA']
    assert final_sha==read(root/'FRESH_AC_RESULT.json')['Fresh_schedule_sha256']
    assert final_sha==read(root/'ACTUAL_FIXED_REPLAY.json')['FINAL_JOINT_DECISION_SHA']
    assert all(sha(root/name)==expected for name,expected in certificate['files'].items())
