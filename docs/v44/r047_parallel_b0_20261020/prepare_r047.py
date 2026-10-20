import sys
sys.path.insert(0,'D:/v44_r022_rowgen_20261017')
from v44_recovery_r047 import operations as op
from v44.common import read,atomic,record,verify,now
from v44_recovery_r045.reference import project
from v44.daily import day_inputs
from v44.campaign import stage_request

with op.core.week.bindings():
    op.parent.authority();op.core.authority()
    assert not op.AUTH.exists()
    state=read(op.STATE);rows=[]
    assert state['phase']=='MAIN_ACTUAL_PARALLEL' and op.alive(state['lease'])
    assert not op.core.seq.STOP.exists()
    for j in state['jobs']:
        if j['arm'] not in ('B0','B2'):continue
        assert j['status']=='BASELINE_QUEUED'
        assert not op.Path(j['case_root']).exists()
        plan=next(p for p in op.parent.authority()['plan'] if op.core.seq.key(p)==op.core.seq.key(j))
        r=read(plan['original_request']);verify(r['sources'])
        assert (r['day'],r['arm'])==op.core.seq.key(j)
        assert op.Path(j['case_root'])==op.Path(plan['case_root'])
        stage=stage_request(r,'ACTUAL');inputs=day_inputs(j['day'])
        assert stage['input_folder']==inputs['native_folder']
        rows.append(dict(day=j['day'],arm=j['arm'],case_root=j['case_root'],input_folder=stage['input_folder']))
    # Exercise the exact reference projection for all seven dates, Native0.
    projections=[]
    for day in op.core.week.DAYS:
        inputs=day_inputs(day);native=read(op.Path(inputs['native_folder'])/'NATIVE_INPUT.json')
        assert native['day']==day
        result=project(native)
        projections.append(dict(day=day,native_jobs=len(native['known_population']),projection_type=type(result).__name__))
    validation=op.OPS/'R047_VALIDATION.json'
    atomic(validation,dict(PASS=True,UTC=now(),Native_calls=0,regression=record(op.OPS/'R047_REGRESSION.xml'),axes=rows,reference_projections=projections,main_actual_preserved=True,B0_workers=1,B2_parallel=False))
    user=op.OPS/'R047_USER_B0_PARALLEL_REQUEST.json'
    atomic(user,dict(UTC=now(),explicit_user_approved=True,text='지금 ram 사용량 남네. B0들만 1worker로 추가해서 지금 actual과 병렬로 실행해도 될 것 같아.',interpretation='Add one serial B0 full-case worker for May08-14 beside current Actual. Preserve current main workers. Prevent duplicate B0 dispatch, merge terminal results, then continue B2 serially.'))
    atomic(op.AUTH,dict(UTC=now(),explicit_user_approved=True,sources=op.sources(),previous_authorization=record(op.parent.AUTH),validation=record(validation),user_request=record(user),days=list(op.core.week.DAYS),parallel_arms=['B0'],B0_workers=1,B2_workers_after_main=1,parent_lease=state['lease'],unchanged_scientific_execution_permit=record(op.core.week.PERMIT),shared_resource_policy='Separate live auxiliary lease and case/slot locks; borrow exact live parent global resource ownership, then transfer global OS locks after all parent workers drain. Merge state only with no active case.'))
    op.authority()
    atomic(op.OPS/'R047_SOURCE_SNAPSHOT.json',dict(UTC=now(),sources=op.sources(),authorization=record(op.AUTH),tests=record('D:/v44_r022_rowgen_20261017/tests/test_v44_recovery_r047.py')))
    print({'PASS':True,'Native_calls':0,'axes':len(rows),'reference_dates':len(projections),'main_lease':state['lease']['pid']})
