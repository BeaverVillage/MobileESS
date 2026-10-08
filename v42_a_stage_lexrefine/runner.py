"""Full-domain integer P2 refinement with exhaustive objective partitions.

Uses the repository's current-native integer-bound authority after a separate
read-back proves the actual model equals the qualified FULL relevant matrix.
This scope is stronger than an active-only MILP bound: all STAY and retained
singleton flow are present, and EVERY migration is excluded only by the
already certified exact zero prior lock. Integer valid cuts are inherited.
"""
import gzip,pickle,math,traceback
from dataclasses import replace
from fractions import Fraction
from time import time
import numpy as np
from v42_pr134_b1.common import read,record,atomic,sha
from v42_a_stage_domain_v2.lexstage import LexLock,rebuild_locked_snapshot,integer_optimality_certificate,integer_objective_proof
from v42_a_stage_phase1.core import primal_replay
from v42_a_stage_practical.physical import Physical
from v42_a_stage_compact_rowgen.budget import Budget
from v42_a_stage_bnp.budget import Allocation
from v42_a_stage_lexfull.runner import objective_value
from .policy import OUT,STATIC,POLICY
from .native import Native
from .execution import verify
from .partition import split

def run():
    verify()
    if (OUT/'P2_REFINE_STARTED.json').exists():raise PermissionError('P2_REFINEMENT_ALREADY_STARTED')
    b=read(OUT/'LEX_FULL_BUILD_VERIFICATION.json')
    with gzip.open(b['state']['path'],'rb') as f:p=pickle.load(f)
    state,original=p['state'],p['snapshot'];physical=Physical(state,original)
    build=read(OUT/'LEX_REFINE_BUILD_VERIFICATION.json')
    with gzip.open(build['snapshot']['path'],'rb') as f:s=pickle.load(f)
    prior=OUT/'M19/P2/SHIFT_MAGNITUDE/CONTROL/NATIVE_RESULT.json';control=read(prior)
    warm=np.load(control['raw_attributes']['path'])['X']
    if not physical.verify(warm)['PASS']:raise ValueError('PRIOR_VALIDATED_INCUMBENT_DRIFT')
    P1=read(OUT/'VALIDATED_INTEGER_INCUMBENT.json');migration=read(OUT/'P2_MIGRATION_PROBE_RESULT.json')
    locks=[LexLock('rho',Fraction(P1['exact_UB']),True,sha(OUT/'P1_FULL_DOMAIN_INTEGER_GAP_CERTIFICATE.json'),Fraction(1e-7)),
        LexLock('migration_count',Fraction(0),True,migration['certificate']['sha256'])]
    budget=Budget();native=Native(budget);results=[];events=[];last_checkpoint=time();ledger=[];best=None;globalLB=None
    atomic(OUT/'P2_REFINE_STARTED.json',dict(PASS=True,source=record(OUT/'LEX_REFINE_SOURCE_FREEZE.json'),deadline=budget.record,
        previous_tree_preserved=record(OUT/'M19/P2/SHIFT_MAGNITUDE/BEST_BOUND_CHECKPOINT.json'),previous_result=record(OUT/'P2_FULL_RESULT.json')))
    def checkpoint():
        atomic(OUT/'P2_REFINE_CHECKPOINT.json',dict(stages=results,objective_partition_nodes=ledger,incumbent=best,
            valid_global_LB=globalLB,source=record(OUT/'LEX_REFINE_SOURCE_FREEZE.json'),deadline=budget.record,
            unix=time(),events=events))
    result=dict(A1_accepted=False,classification='A_PRACTICAL_SOLVER_P1_GAP_LE_0P5',stages=results)
    try:
        for name in ('shift_magnitude','prestart_relocation'):
            stage,lockproof=rebuild_locked_snapshot(s,locks);o=stage.objective(name)
            query=replace(stage,objectives=(o,)+tuple(v for v in stage.objectives if v.name!=name));integer_objective_proof(stage,name)
            folder=OUT/'M19/P2/REFINEMENT'/name.upper();folder.mkdir(parents=True,exist_ok=True)
            atomic(folder/'LOCK_REBUILD.json',lockproof)
            best=dict(value=float(objective_value(original,warm,name)),point=record(prior))
            right_bounds=[];serial=0;problem=query
            while True:
                budget.remaining();cfolder=folder/('N'+str(serial));serial+=1;native.warm_point=warm;native.warm_basis=None
                native.budget=Allocation(POLICY['control_allocation_seconds'])
                try:rec,raw=native.solve(problem,cfolder,'P2')
                finally:native.budget=budget
                actual=read(cfolder/'INDEPENDENT_COMPILED_MODEL_VERIFICATION.json')
                if not actual['PASS']:raise ValueError('INDEPENDENT_ACTUAL_MATRIX_READBACK_REQUIRED')
                primal=False
                if 'X' in raw:
                    x=raw['X'];physics=physical.verify(x);rows=primal_replay(problem,x)
                    atomic(cfolder/'FULL_ORIGINAL_A1_REPLAY.json',physics);atomic(cfolder/'LOCKED_STRENGTHENED_ROWS.json',rows)
                    primal=physics['PASS'] and rows['PASS']
                    if primal:
                        value=float(objective_value(original,x,name))
                        if value<=best['value']+1e-5:best=dict(value=value,point=rec['raw_attributes']);warm=x
                if rec['status']==3:
                    if not right_bounds:raise ValueError('FULL_STAGE_INFEASIBLE_DESPITE_PREVIOUS_VALID_POINT')
                    nodeLB=math.inf
                    atomic(cfolder/'CURRENT_FULL_INTEGER_INFEASIBILITY.json',dict(PASS=True,native_status=3,
                        actual_model_verification=record(cfolder/'INDEPENDENT_COMPILED_MODEL_VERIFICATION.json'),
                        domain=record(OUT/'LEX_FULL_BUILD_VERIFICATION.json'),source=record(OUT/'LEX_REFINE_SOURCE_FREEZE.json'),
                        kind='CURRENT_NATIVE_COMPLETE_RELEVANT_INTEGER_MODEL_INFEASIBLE',LP_Farkas_alone_not_integer_certificate=True))
                elif rec['status'] in (2,9) and rec['ObjBound'] is not None and math.isfinite(rec['ObjBound']):nodeLB=float(rec['ObjBound'])
                else:raise RuntimeError('CURRENT_FULL_INTEGER_NODE_NOT_CERTIFIABLY_BOUNDED')
                globalLB=min([nodeLB]+right_bounds)
                provenance=dict(PASS=True,component=name,current_actual_matrix_verified=True,
                    complete_relevant_integer_domain=record(OUT/'LEX_FULL_BUILD_VERIFICATION.json'),
                    original_integer_equivalence=record(OUT/'LEX_REFINE_BUILD_VERIFICATION.json'),
                    native_current_result=record(cfolder/'NATIVE_RESULT.json'),native_node_LB=None if not math.isfinite(nodeLB) else nodeLB,
                    native_infeasible=nodeLB==math.inf,analytic_right_bounds=right_bounds,full_domain_valid_LB=globalLB,
                    bound_authority='INHERITED_CURRENT_NATIVE_MATRIX_GLOBAL_BOUND_WITH_INDEPENDENT_FULL_DOMAIN_AND_ACTUAL_MATRIX_REPLAY',
                    LP_pricing_alone_not_integer_bound=True,restricted_active_bound_not_used=True)
                atomic(cfolder/'INDEPENDENT_INTEGER_BOUND_PROVENANCE.json',provenance)
                cert=integer_optimality_certificate(name,best['value'],globalLB,bound_independently_validated=True,
                    primal_independently_validated=True,integrality_proven=True)
                events.append(dict(component=name,node=serial-1,unix=time(),LB=globalLB,UB=best['value'],native_status=rec['status']))
                cert.update(scope='FULL_SCIENTIFIC_RELEVANT_INTEGER_DOMAIN_UNDER_CERTIFIED_PRIOR_LOCKS',integer_domain_closure_proven=cert['PASS'],
                    bound_provenance=record(cfolder/'INDEPENDENT_INTEGER_BOUND_PROVENANCE.json'))
                atomic(cfolder/'INTEGER_CERTIFICATE.json',cert);checkpoint()
                if cert['PASS']:
                    result_stage=dict(component=name,value=cert['incumbent_integer'],valid_LB=globalLB,
                        certificate=record(cfolder/'INTEGER_CERTIFICATE.json'),point=best['point'],partition_native_nodes=serial)
                    results.append(result_stage);locks.append(LexLock(name,Fraction(cert['incumbent_integer']),True,sha(cfolder/'INTEGER_CERTIFICATE.json')))
                    prior=__import__('pathlib').Path(best['point']['path'])
                    print('P2_EXACT_ACCEPTED',name,cert['incumbent_integer'],globalLB,flush=True);break
                if rec['status']==9:raise RuntimeError('MEASURED_FULL_INTEGER_NODE_1200S_LIMIT')
                problem,partition=split(query,name,best['value'])
                partition.update(parent_native_node=serial-1,incumbent=best)
                atomic(cfolder/'EXHAUSTIVE_INTEGER_OBJECTIVE_PARTITION.json',partition)
                right_bounds.append(partition['right']['valid_LB']);ledger.append(partition);checkpoint()
        result.update(A1_accepted=True,classification='A_PRACTICAL_SOLVER_A1_ACCEPTED',migration_count=0,
            shift_magnitude=results[0]['value'],prestart_relocation=results[1]['value'])
    except Exception as e:result.update(stop_reason=repr(e),traceback=traceback.format_exc())
    finally:
        checkpoint();result.update(native_seconds=native.native_seconds,Work=sum(c['Work'] or 0 for c in native.calls),
            elapsed_wall_seconds=budget.accounted(),peak_RSS_bytes=max((c.get('peak_RSS_bytes') or 0 for c in native.calls),default=0))
        atomic(OUT/'P2_REFINE_NATIVE_CALLS.json',dict(calls=native.calls));atomic(OUT/'P2_REFINE_RESULT.json',result)
        print('P2_REFINE_RESULT',result['classification'],result.get('stop_reason'),flush=True)
    return result
if __name__=='__main__':run()
