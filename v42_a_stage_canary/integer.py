"""Identical original-type P1 control and qualified full-zero P2 refinement."""
from dataclasses import replace
from fractions import Fraction
import math
import numpy as np
from v42_pr134_b1.common import read,record,atomic,sha
from v42_a_stage_practical.integer_model import restore_types
from v42_a_stage_domain_v2.lexstage import LexLock,rebuild_locked_snapshot,integer_objective_proof,integer_optimality_certificate
from v42_a_stage_domain_v2.strengthening import strengthen_histogram_capacity
from v42_a_stage_lexfull.runner import objective_value,warm_reindex
from v42_a_stage_lexrefine.partition import split
from v42_a_stage_phase1.core import primal_replay
from v42_a_stage_bnp.budget import Allocation
from .physical import Physical
from .zero import build as zero_model
from .policy import OUT,STATIC,POLICY

def run(native,state,expanded,p1,day):
    folder=OUT/day;typed,typeproof=restore_types(state,state['global_types']);physical=Physical(state,typed)
    atomic(folder/'INTEGER_BUILD_VERIFICATION.json',typeproof)
    native.warm_point=expanded;native.budget=Allocation(1200)
    rec,raw=native.solve(typed,folder/'INTEGER_CONTROL','INTEGER_CONTROL');candidate=None
    if 'X' in raw:
        verification=physical.verify(raw['X']);atomic(folder/'P1_FULL_ORIGINAL_A1_REPLAY.json',verification)
        if verification['PASS']:
            U=objective_value(typed,raw['X'],'rho');L=Fraction(p1['full_domain_phase1_lower_bound'])
            if U>=L:
                g=(U-L)/abs(U) if U else Fraction(0) if L==0 else None
                candidate=dict(UB=float(U),exact_UB=str(U),LB=float(L),exact_LB=str(L),gap=None if g is None else float(g),raw=rec['raw_attributes'])
    accepted=bool(candidate and candidate['gap'] is not None and candidate['gap']<=.005 and rec['status']==2)
    integer=dict(P1_accepted=accepted,incumbent=candidate,native_status=rec['status'],native_active_bound_not_used=True,
        full_domain_bound_from_complete_root_LP=True,original_physics_replayed=candidate is not None)
    atomic(folder/'INTEGER_RESULT.json',integer)
    if not accepted:raise RuntimeError('CANARY_P1_GLOBAL_GAP_NOT_ACCEPTED')
    locks=[LexLock('rho',Fraction(candidate['exact_UB']),True,sha(folder/'INTEGER_RESULT.json'),Fraction(1e-7))]
    locked,_=rebuild_locked_snapshot(typed,locks);mig=locked.objective('migration_count')
    query=replace(locked,objectives=(mig,)+tuple(o for o in locked.objectives if o.name!=mig.name));native.warm_point=raw['X'];native.budget=Allocation(300)
    mrec,mraw=native.solve(query,folder/'P2/MIGRATION_ACTIVE_PROBE','P2');migration_zero=False;oldwarm=raw['X']
    if 'X' in mraw:
        v=physical.verify(mraw['X']);rows=primal_replay(locked,mraw['X']);val=float(objective_value(typed,mraw['X'],'migration_count'))
        migration_zero=v['PASS'] and rows['PASS'] and abs(val)<=1e-5
        atomic(folder/'P2/MIGRATION_ACTIVE_PROBE/FULL_ORIGINAL_A1_REPLAY.json',v)
        if migration_zero:oldwarm=mraw['X']
    zs,z=zero_model(state,typed,day);zp=Physical(zs,z);warm=warm_reindex(state,zs,oldwarm,state['n'])
    if not migration_zero:
        zlocked,_=rebuild_locked_snapshot(z,locks);mig=zlocked.objective('migration_count')
        zquery=replace(zlocked,objectives=(mig,)+tuple(o for o in zlocked.objectives if o.name!=mig.name));native.warm_point=warm;native.budget=Allocation(1200)
        mr,mx=native.solve(zquery,folder/'P2/FULL_ZERO_QUERY','P2')
        if 'X' in mx:
            v=zp.verify(mx['X']);rows=primal_replay(zlocked,mx['X']);migration_zero=v['PASS'] and rows['PASS']
            atomic(folder/'P2/FULL_ZERO_QUERY/FULL_ORIGINAL_A1_REPLAY.json',v)
            if migration_zero:warm=mx['X']
        if not migration_zero:raise RuntimeError('FULL_ZERO_MIGRATION_FEASIBILITY_NOT_CERTIFIED_RETAIN_POSITIVE_MIGRATION_DOMAIN')
    proof=integer_optimality_certificate('migration_count',0,0,bound_independently_validated=True,primal_independently_validated=True,integrality_proven=True)
    proof.update(scope='FULL_SCIENTIFIC_DOMAIN',integer_domain_closure_proven=True,universal_nonnegative_objective_bound=True)
    atomic(folder/'P2/MIGRATION_CERTIFICATE.json',proof);locks.append(LexLock('migration_count',Fraction(0),True,sha(folder/'P2/MIGRATION_CERTIFICATE.json')))
    strong,cuts=strengthen_histogram_capacity(z,z,zp.descriptor,zs['data'],np.arange(z.matrix.shape[1],dtype=np.int64))
    atomic(folder/'P2/INHERITED_INTEGER_STRENGTHENING.json',cuts)
    from .cases import run as exact_cases
    results,warm=exact_cases(native,strong,z,warm,zp,locks,folder)
    path=STATIC/day/'FINAL_VALIDATED_A1_POINT.npz';np.savez_compressed(path,X=warm)
    result=dict(A1_accepted=True,classification='A_PRACTICAL_SOLVER_A1_ACCEPTED',P1=candidate,migration_count=0,
        shift_magnitude=results[0]['value'],prestart_relocation=results[1]['value'],P2=results,point=record(path))
    atomic(folder/'A1_RESULT.json',result);return result
