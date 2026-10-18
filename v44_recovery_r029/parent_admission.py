"""Read-only, Native0 FULL replay of the completed M1 and same-day B1 A1."""
from pathlib import Path
from types import SimpleNamespace,MethodType
import numpy as np
from scipy import sparse
from v44.common import read,record,verify,atomic,now


def original_point(stage):
    """Reconstruct a completed original FULL point without changing its files."""
    from v44.checkpoints import checked
    from v44.daily import load_aidc
    from v44.planning import scope
    from v42_bootstrap.m1 import native_inputs
    from v42_supercompact.formulation import Compact
    from v42_supercompact.presolve import Presolve
    from .wall_resume import arrays
    from v44.stages import require_m1
    stage=Path(stage);request=read(stage/'request.json');result=read(stage/'RESULT.json')
    require_m1(result,request['day']);checked(stage/'COMPLETED_STAGE_CHECKPOINT.json',request,'COMPLETED')
    reference=result['fixed_AIDC'];payload,_=load_aidc(Path(reference['reference_folder']),request['day']) if 'reference_folder' in reference else (None,None)
    if payload is None:
        reuse=read(stage.parent/'A1_REUSE.json');verify([reuse['AIDC_reference']])
        payload,_=load_aidc(Path(reuse['AIDC_reference']['path']).parent,request['day'])
    with scope(request['day']):
        sites,initial,routes,battery,receipt=native_inputs(payload['bundle'])
        arcs=[(s,t,s,t+1,None) for s in sites for t in range(96)]+[(r.source,r.depart,r.destination,r.connect,r) for r in dict.fromkeys(routes)]
        data=arrays(stage/'FULL_DATA.npz');A=sparse.load_npz(stage/'FULL_A.npz')
        compact=Compact(A,data,arcs,initial,96);axes=arrays(stage/'CURRENT_C2_AXES.npz')
        inverse=SimpleNamespace(A=sparse.load_npz(stage/'C3A_A.npz'),d=arrays(stage/'C3A_DATA.npz'),
            col_ids=axes['columns'],row_ids=axes['rows'],initial_names=compact.d['names'],
            steps=read(stage/'CURRENT_C2_ALIASES.json'),rows=read(stage/'CURRENT_C2_ROW_PROOFS.json'),bound=read(stage/'CURRENT_C2_BOUND_PROOFS.json'))
        point=compact.inverse(Presolve.inverse(inverse,arrays(stage/'ACCEPTED_M_POINT.npz')['point']))
    return data['names'],point


def validate(parent,output,current_request=None):
    from v44.daily import load_aidc
    from v44.checkpoints import checked,ledger_state,assert_dead
    from v44.stages import require_m1
    from v44.planning import scope
    from v44.frozen.v43_mess.library import load,current_identity
    from v42_bootstrap.m1 import native_inputs
    from v42_supercompact.formulation import Compact
    from v42_supercompact.presolve import Presolve
    from v42_m1_research.check_ub import validate_candidate
    from v44.q250_m4_v2 import check_plan,overlay
    from .wall_resume import arrays
    parent=Path(parent);output=Path(output);output.mkdir(parents=True,exist_ok=True);stage=parent/'M1'
    assert_dead(parent);old=read(stage/'request.json')
    if (old['day'],old['arm'],old['stage'],parent.name)!=('2025-05-02','B3','M1','attempt001'):
        raise PermissionError('R029_EXACT_COMPLETED_PARENT_REQUIRED')
    checked(stage/'BINARY_STAGE_CHECKPOINT.json',old,'M_BINARY')
    checked(stage/'COMPLETED_STAGE_CHECKPOINT.json',old,'COMPLETED')
    result=read(stage/'RESULT.json');plan=require_m1(result,old['day'])
    if old['Q250_M4_overlay']!=overlay():raise PermissionError('R029_Q250_SOURCE_POLICY_DRIFT')
    if current_request is not None and old['scientific_source_sha']!=current_request['scientific_source_sha']:
        raise PermissionError('R029_PARENT_SCIENTIFIC_FREEZE_INCOMPATIBLE')
    a1=read(parent/'A1_REUSE.json');verify([a1['AIDC_reference']])
    a1root=Path(a1['AIDC_reference']['path']).parent.parent
    original_a1=read(a1root/'RESULT.json')
    if not original_a1.get('PASS') or not original_a1.get('FULL_feasible') or not 0<=original_a1.get('certified_gap',1)<=.005:
        raise PermissionError('R029_SAME_DAY_ORIGINAL_A1_NOT_CERTIFIED')
    payload,_=load_aidc(Path(a1['AIDC_reference']['path']).parent,old['day']);modules=load()
    with scope(old['day']):
        sites,initial,routes,battery,receipt=native_inputs(payload['bundle'])
        arcs=[(s,t,s,t+1,None) for s in sites for t in range(96)]+[(r.source,r.depart,r.destination,r.connect,r) for r in dict.fromkeys(routes)]
        A=sparse.load_npz(stage/'FULL_A.npz');B=sparse.load_npz(stage/'C3A_A.npz')
        data=arrays(stage/'FULL_DATA.npz');selected=arrays(stage/'C3A_DATA.npz');axes=arrays(stage/'CURRENT_C2_AXES.npz')
        identity=read(stage/'SCIENTIFIC_CASE_IDENTITY.json');case_sha=identity.pop('case_sha')
        if (case_sha!=result['case_sha'] or identity['aidc_anchor']!=payload['identity']['aidc_anchor']
                or identity['source_sha']!=old['source_sha'] or identity['Q_operating_limit_kvar']!=250.
                or identity['slots']!=96):raise PermissionError('R029_M1_CASE_AXIS_Q250_ANCHOR_DRIFT')
        compact=Compact(A,data,arcs,initial,96)
        inverse=SimpleNamespace(A=B,d=selected,col_ids=axes['columns'],row_ids=axes['rows'],initial_names=compact.d['names'],
            steps=read(stage/'CURRENT_C2_ALIASES.json'),rows=read(stage/'CURRENT_C2_ROW_PROOFS.json'),bound=read(stage/'CURRENT_C2_BOUND_PROOFS.json'))
        inverse.inverse=MethodType(Presolve.inverse,inverse)
        case=SimpleNamespace(original_A=A,original_d=data,A=B,d=selected,graph=(sites,initial,arcs,battery,receipt),
            case_sha=case_sha,identity=identity,bundle=payload['bundle'],output=output,
            lift=lambda point:compact.inverse(inverse.inverse(point)))
        current_identity(case);point=arrays(stage/'ACCEPTED_M_POINT.npz')['point'];replay=validate_candidate(case,point)
        if not replay['PASS']:raise PermissionError('R029_M1_ORIGINAL_FULL_REPLAY_FAILED')
        exported=modules['m_engine'].export_plan(case,point)
        if exported!=plan:raise PermissionError('R029_FROZEN_M1_ROUTE_P_Q_SOC_PLAN_DRIFT')
        q=check_plan(plan)
    physical=read(parent/'A2/request.json')['physical_cache_case_proof'];verify([physical]);proof=read(physical['path'])
    verify(proof['sources']+[proof['result'],proof['cache']]+list(proof['inputs'].values()))
    output_receipt=dict(UTC=now(),PASS=True,parent=record(stage/'RESULT.json'),M1_case_sha=case_sha,M1_source_sha=old['source_sha'],
        M1_plan_sha=plan['plan_sha'],M1_FULL_original_replay=replay,Q250=q,Q250_source_policy=overlay(),
        original_A1=record(a1root/'RESULT.json'),original_AIDC_reference=a1['AIDC_reference'],physical_domain=physical,
        hardware=read(stage/'COMPLETED_STAGE_CHECKPOINT.json')['hardware'],time_axis=plan['time_axis'],
        K48=ledger_state(stage/'K48_NATIVE_LEDGER.json',ceiling=300.),Joint=ledger_state(stage/'JOINT_NATIVE_LEDGER.json',ceiling=900.),
        independent_stage_source_compatibility='ORIGINAL_FULL_MATRICES_DOMAINS_HARDWARE_Q250_SOURCE_AND_EXPORTED_PLAN_REVALIDATED',
        new_A1_M1_Native_calls=0,original_stage_files_modified=False)
    atomic(output/'R029_PARENT_COMPATIBILITY.json',output_receipt)
    return output_receipt
