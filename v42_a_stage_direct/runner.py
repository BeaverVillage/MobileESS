"""Nested original integer objective cutoffs, with exhaustive sibling ledgers."""
import gzip,pickle,math,traceback
from dataclasses import replace
from fractions import Fraction
from time import time
from pathlib import Path
import numpy as np
from v42_pr134_b1.common import read,record,atomic,sha
from v42_a_stage_lexcases.policy import OUT,STATIC
from v42_a_stage_compact_rowgen.budget import Budget
from v42_a_stage_bnp.budget import Allocation
from v42_a_stage_compact_rowgen.resources import sample
from v42_a_stage_domain_v2.lexstage import LexLock,rebuild_locked_snapshot,integer_optimality_certificate
from v42_a_stage_lexrefine.partition import split
from v42_a_stage_lexfull.runner import objective_value
from v42_a_stage_phase1.core import primal_replay
from v42_a_stage_practical.physical import Physical
from .freeze import verify
from .native import Native

def run():
    verify();budget=Budget();budget.remaining()
    if (OUT/'DIRECT_STARTED.json').exists():raise PermissionError('DIRECT_ALREADY_STARTED')
    prior=read(OUT/'PRIMAL_REPAIR_V2_RESULT.json')
    build=read(OUT/'LEX_FULL_BUILD_VERIFICATION.json')
    with gzip.open(build['state']['path'],'rb') as f:p=pickle.load(f)
    original=p['snapshot'];physical=Physical(p['state'],original)
    cg=read(OUT/'WEIGHTED_CG_BUILD_VERIFICATION.json')
    if record(cg['snapshot']['path'])!=cg['snapshot']:raise ValueError('QUALIFIED_WEIGHTED_INTEGER_SNAPSHOT_DRIFT')
    with gzip.open(cg['snapshot']['path'],'rb') as f:s=pickle.load(f)
    previous=read(OUT/'P2_CG_CHECKPOINT.json');bestpoint=previous['incumbent']['point'];stages=[]
    if prior.get('accepted'):
        bestpoint=prior['point'];stages.append({k:prior[k] for k in ('component','value','valid_LB','certificate','point')})
    if record(bestpoint['path'])!=bestpoint:raise ValueError('PRESERVED_FULL_PHYSICAL_POINT_DRIFT')
    warm=np.load(bestpoint['path'])['X']
    if not physical.verify(warm)['PASS']:raise ValueError('FULL_ORIGINAL_PRIOR_PRIMAL_REQUIRED')
    inc=read(OUT/'VALIDATED_INTEGER_INCUMBENT.json');mig=read(OUT/'P2_MIGRATION_PROBE_RESULT.json')
    locks=[LexLock('rho',Fraction(inc['exact_UB']),True,sha(OUT/'P1_FULL_DOMAIN_INTEGER_GAP_CERTIFICATE.json'),Fraction(1e-7)),
        LexLock('migration_count',Fraction(0),True,mig['certificate']['sha256'])]
    for stage in stages:locks.append(LexLock(stage['component'],Fraction(stage['value']),True,stage['certificate']['sha256']))
    native=Native(budget);ledger=[];events=[];LB=None;best=None;result=dict(A1_accepted=False,classification='A_PRACTICAL_SOLVER_P1_GAP_LE_0P5',stages=stages)
    atomic(OUT/'DIRECT_STARTED.json',dict(PASS=True,source=record(OUT/'DIRECT_SOURCE_FREEZE.json'),deadline=budget.record,
        native_processes=1,prior_closed_or_open_models_preserved=True,prior_stage_queue=record(OUT/'P2_CG_CHECKPOINT.json')))
    def checkpoint():
        atomic(OUT/'DIRECT_CHECKPOINT.json',dict(stages=stages,queue=ledger,events=events,valid_global_LB=LB,incumbent=best,
            unix=time(),deadline=budget.record,source=record(OUT/'DIRECT_SOURCE_FREEZE.json')))
    try:
        for name in ('shift_magnitude','prestart_relocation'):
            if any(t['component']==name for t in stages):continue
            locked,lockproof=rebuild_locked_snapshot(s,locks);obj=locked.objective(name)
            query=replace(locked,objectives=(obj,)+tuple(o for o in locked.objectives if o.name!=name))
            folder=OUT/'M19/P2/DIRECT'/name.upper();folder.mkdir(parents=True,exist_ok=True);atomic(folder/'LOCK_REBUILD.json',lockproof)
            if not primal_replay(locked,warm)['PASS']:raise ValueError('PRIOR_LOCKED_PRIMAL_INCLUSION_REQUIRED')
            best=dict(value=float(objective_value(original,warm,name)),point=bestpoint)
            LB=previous['valid_global_LB'] if name=='shift_magnitude' else 0.;serial=0
            while True:
                checkpoint();cert=integer_optimality_certificate(name,best['value'],LB,bound_independently_validated=True,
                    primal_independently_validated=True,integrality_proven=True)
                if cert['PASS']:
                    cp=folder/'INTEGER_CERTIFICATE.json';cert.update(scope='FULL_SCIENTIFIC_RELEVANT_INTEGER_DOMAIN_UNDER_CERTIFIED_PRIOR_LOCKS',
                        source=record(OUT/'DIRECT_SOURCE_FREEZE.json'),ledger=record(OUT/'DIRECT_CHECKPOINT.json'),
                        independent_rational_MIP_dual_certificate=False)
                    atomic(cp,cert);stage=dict(component=name,value=cert['incumbent_integer'],valid_LB=LB,certificate=record(cp),point=best['point'])
                    stages.append(stage);locks.append(LexLock(name,Fraction(stage['value']),True,sha(cp)));bestpoint=best['point']
                    print('DIRECT_STAGE_ACCEPTED',name,best['value'],LB,flush=True);break
                remaining=budget.remaining()
                if remaining<=180:raise RuntimeError('IMMUTABLE_BUDGET_FINALIZATION_RESERVE')
                resources=sample()
                if resources['unsafe']:raise RuntimeError('ONE_NATIVE_RESOURCE_GUARD_WAIT_REQUIRED')
                problem,partition=split(query,name,best['value']);f=folder/('N'+str(serial));serial+=1;f.mkdir(parents=True,exist_ok=True)
                atomic(f/'EXHAUSTIVE_OBJECTIVE_PARTITION.json',partition)
                node=dict(id=serial-1,component=name,status='OPEN',partition=partition,prior_global_LB=LB,incumbent=best)
                ledger.append(node);checkpoint();callback_points=[]
                def candidate(x,value):
                    nonlocal warm,best
                    rows=primal_replay(problem,x);integer=np.max(abs(x[original.vtypes!='C']-np.rint(x[original.vtypes!='C'])))<=1e-5
                    phys=dict(PASS=False,reason='RAW_ROW_BOUND_INTEGER_GATE_FAILED')
                    if rows['PASS'] and integer:
                        try:phys=physical.verify(x)
                        except Exception as e:phys=dict(PASS=False,reason=repr(e))
                    accepted=rows['PASS'] and integer and phys['PASS'];val=float(objective_value(original,x,name))
                    cf=f/'CANDIDATES'/('C'+str(len(callback_points)));cf.mkdir(parents=True,exist_ok=True)
                    atomic(cf/'CURRENT_QUERY_ROWS_REPLAY.json',rows);atomic(cf/'FULL_ORIGINAL_A1_REPLAY.json',phys)
                    if accepted and val<best['value']-1e-5:
                        path=STATIC/cf.relative_to(OUT)/'VALIDATED_POINT.npz';path.parent.mkdir(parents=True,exist_ok=True);np.savez_compressed(path,X=x)
                        best=dict(value=val,point=record(path));warm=x.copy();checkpoint()
                        if math.ceil(LB-1e-6)>=round(val) and native.live_model is not None:native.live_model.terminate()
                    callback_points.append(dict(value=val,accepted=bool(accepted),rows=record(cf/'CURRENT_QUERY_ROWS_REPLAY.json'),physical=record(cf/'FULL_ORIGINAL_A1_REPLAY.json')))
                    atomic(f/'CALLBACK_PRIMALS.json',dict(points=callback_points,callback_bound_is_not_domain_authority=True))
                native.incumbent_callback=candidate;native.hint_point=warm;native.hint_record=best['point'];native.warm_point=None;native.warm_basis=None
                native.queue_checkpoint=record(OUT/'DIRECT_CHECKPOINT.json');native.budget=Allocation(remaining-180)
                try:rec,raw=native.solve(problem,f,'P2')
                finally:native.budget=budget;native.incumbent_callback=None
                if not read(f/'INDEPENDENT_COMPILED_MODEL_VERIFICATION.json')['PASS']:raise ValueError('CURRENT_COMPLETE_NATIVE_MODEL_REQUIRED')
                if 'X' in raw:candidate(raw['X'],rec['objective'])
                if rec['status']==3:
                    LB=partition['right']['valid_LB'];node['status']='LEFT_PROVEN_INFEASIBLE_RIGHT_BOUND_CLOSED'
                elif rec['status'] in (2,9,11) and rec['native_error'] is None and rec['ObjBound'] is not None and math.isfinite(rec['ObjBound']):
                    LB=max(LB,min(float(rec['ObjBound']),partition['right']['valid_LB']));node['status']='OPEN_CURRENT_NATIVE_BOUND'
                else:raise RuntimeError('DIRECT_CURRENT_INTEGER_BOUND_NOT_VALID')
                provenance=dict(PASS=True,current_result=record(f/'NATIVE_RESULT.json'),actual_model=record(f/'INDEPENDENT_COMPILED_MODEL_VERIFICATION.json'),
                    full_relevant_domain=record(OUT/'LEX_FULL_BUILD_VERIFICATION.json'),integer_valid_strengthening=record(OUT/'WEIGHTED_CG_BUILD_VERIFICATION.json'),
                    partition=record(f/'EXHAUSTIVE_OBJECTIVE_PARTITION.json'),valid_global_LB=LB,validated_UB=best['value'],
                    independent_rational_MIP_dual_certificate=False,hints_not_bound_authority=True,interrupted_not_infeasible=True)
                atomic(f/'FULL_DOMAIN_INTEGER_BOUND_PROVENANCE.json',provenance);events.append(dict(component=name,LB=LB,UB=best['value'],status=rec['status'],unix=time()));checkpoint()
                if rec['status']==2 and 'X' in raw and not any(c['accepted'] for c in callback_points):raise RuntimeError('NATIVE_OPTIMAL_CANDIDATE_FAILS_ORIGINAL_PHYSICS')
        result.update(A1_accepted=True,classification='A_PRACTICAL_SOLVER_A1_ACCEPTED',migration_count=0,
            shift_magnitude=stages[0]['value'],prestart_relocation=stages[1]['value'])
    except Exception as e:result.update(stop_reason=repr(e),traceback=traceback.format_exc())
    finally:
        checkpoint();result.update(native_seconds=native.native_seconds,Work=sum(c.get('Work') or 0 for c in native.calls),
            elapsed_wall_seconds=budget.accounted(),peak_RSS_bytes=max((c.get('peak_RSS_bytes') or 0 for c in native.calls),default=0))
        atomic(OUT/'DIRECT_NATIVE_CALLS.json',dict(calls=native.calls));atomic(OUT/'DIRECT_RESULT.json',result)
        print('DIRECT_RESULT',result['classification'],result.get('stop_reason'),flush=True)
    return result
if __name__=='__main__':run()
