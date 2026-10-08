"""One inherited-lock migration query; only universal zero proves closure."""
import gzip,pickle,traceback
from dataclasses import replace
from fractions import Fraction
import numpy as np
from v42_pr134_b1.common import read,record,atomic,sha
from v42_a_stage_domain_v2.lexstage import LexLock,rebuild_locked_snapshot,integer_objective_proof,integer_optimality_certificate
from v42_a_stage_domain_v2.stress_backend import row_replay
from v42_a_stage_practical.physical import Physical
from v42_a_stage_bnp.budget import Allocation
from .policy import OUT,STATIC,POLICY
from .native import Native
from .execution import verify

def entry():
    i=read(OUT/'INTEGER_RESULT.json');p=read(OUT/'P1_FULL_DOMAIN_INTEGER_GAP_CERTIFICATE.json')
    if not i['P1_accepted'] or not p['PASS']:raise PermissionError('P1_ACCEPTANCE_REQUIRED')
    atomic(OUT/'LEX_ENTRY_GATE.json',dict(PASS=True,P1=record(OUT/'P1_FULL_DOMAIN_INTEGER_GAP_CERTIFICATE.json'),
        rho_lock_epsilon=1e-7,integer_lock_epsilon=0,global_migration_lower_bound=0,
        active_native_bound_is_not_global=True,partial_active_positive_optimum_not_accepted=True))

def run():
    verify()
    if (OUT/'P2_MIGRATION_PROBE_STARTED.json').exists():raise PermissionError('MIGRATION_PROBE_ALREADY_STARTED')
    b=read(OUT/'INTEGER_BUILD_VERIFICATION.json')
    with gzip.open(b['state']['path'],'rb') as f:p=pickle.load(f)
    state,s=p['state'],p['typed'];inc=read(OUT/'VALIDATED_INTEGER_INCUMBENT.json')
    warm=np.load(inc['candidate']['path'])['X'];physical=Physical(state,s)
    lock=LexLock('rho',Fraction(inc['exact_UB']),True,sha(OUT/'P1_FULL_DOMAIN_INTEGER_GAP_CERTIFICATE.json'),Fraction(1e-7))
    locked,receipt=rebuild_locked_snapshot(s,[lock]);integer_objective_proof(locked,'migration_count')
    obj=locked.objective('migration_count')
    if obj.constant<0 or any(c<0 or locked.lower[j]<0 for j,c in obj.coefficients().items()):raise ValueError('GLOBAL_NONNEGATIVITY_REQUIRED')
    query=replace(locked,objectives=(obj,)+tuple(o for o in locked.objectives if o.name!=obj.name))
    folder=OUT/'M19/P2/MIGRATION_ACTIVE_PROBE';folder.mkdir(parents=True,exist_ok=True)
    atomic(folder/'LOCK_REBUILD.json',receipt)
    atomic(OUT/'P2_MIGRATION_PROBE_STARTED.json',dict(PASS=True,source=record(OUT/'LEX_SOURCE_FREEZE.json')))
    native=Native(Allocation(POLICY['migration_probe_seconds']));native.warm_point=warm
    result=dict(PASS=False,accepted=False,full_domain_bound=0,active_bound_not_used=True)
    try:
        rec,raw=native.solve(query,folder,'P2')
        if 'X' in raw:
            x=raw['X'];v=physical.verify(x);r=row_replay(locked,x)
            value=float(obj.constant)+sum(float(c)*x[j] for j,c in obj.coefficients().items())
            proof=integer_optimality_certificate('migration_count',value,0,bound_independently_validated=True,
                primal_independently_validated=v['PASS'] and r['PASS'],integrality_proven=True)
            proof.update(scope='FULL_SCIENTIFIC_DOMAIN',integer_domain_closure_proven=proof['PASS'],
                universal_nonnegative_objective_lower_bound=True)
            atomic(folder/'PHYSICAL_REPLAY.json',v);atomic(folder/'LOCKED_ROW_REPLAY.json',r)
            atomic(folder/'INTEGER_CERTIFICATE.json',proof)
            result.update(PASS=proof['PASS'],accepted=proof['PASS'],value=value,certificate=record(folder/'INTEGER_CERTIFICATE.json'),
                native_status=rec['status'],native_bound=rec['ObjBound'],candidate=rec['raw_attributes'])
            if proof['PASS']:
                path=STATIC/'P2_MIGRATION_ZERO_POINT.npz';np.savez_compressed(path,X=x)
                result['validated_point']=record(path)
        else:result.update(native_status=rec['status'],no_primal=True)
    except Exception as e:result.update(error=repr(e),traceback=traceback.format_exc())
    result.update(native_seconds=native.native_seconds,Work=sum(c['Work'] or 0 for c in native.calls))
    atomic(OUT/'P2_MIGRATION_PROBE_RESULT.json',result)
    print('P2_MIGRATION_PROBE',result,flush=True)
    return result
if __name__=='__main__':run()
