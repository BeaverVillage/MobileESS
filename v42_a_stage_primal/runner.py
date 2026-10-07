"""Primal repairs over original rows and fixed original integer assignments."""
import gzip,pickle,traceback
from fractions import Fraction
import numpy as np
from v42_pr134_b1.common import read,record,atomic,sha
from v42_a_stage_lexcases.policy import OUT,STATIC
from v42_a_stage_cg.native import Native as CGNative
from v42_a_stage_compact_rowgen.budget import Budget
from v42_a_stage_compact_rowgen.resources import sample
from v42_a_stage_bnp.budget import Allocation
from v42_a_stage_domain_v2.lexstage import LexLock,rebuild_locked_snapshot,integer_optimality_certificate
from v42_a_stage_phase1.core import primal_replay
from v42_a_stage_practical.physical import Physical
from v42_a_stage_lexfull.runner import objective_value
from .query import fixed_query
from .freeze import verify

class Native(CGNative):
    def __init__(self,budget):
        super().__init__(budget);self.freeze_path=OUT/'PRIMAL_SOURCE_FREEZE.json'
    def verify(self):return verify()

def run():
    verify();budget=Budget();budget.remaining()
    if (OUT/'PRIMAL_REPAIR_STARTED.json').exists():raise PermissionError('PRIMAL_REPAIR_ALREADY_STARTED')
    atomic(OUT/'PRIMAL_REPAIR_STARTED.json',dict(PASS=True,source=record(OUT/'PRIMAL_SOURCE_FREEZE.json'),deadline=budget.record,
        primal_only=True,domain_bound_from_queries=False))
    build=read(OUT/'LEX_FULL_BUILD_VERIFICATION.json')
    with gzip.open(build['state']['path'],'rb') as f:p=pickle.load(f)
    s=p['snapshot'];physical=Physical(p['state'],s);prepared=read(OUT/'PRIMAL_PROPOSALS.json')
    x=np.load(prepared['preserved_incumbent']['path'])['X']
    old=physical.verify(x)
    if not old['PASS']:raise ValueError('PREVIOUS_FULL_ORIGINAL_POINT_REQUIRED')
    atomic(OUT/'PRIMAL_PRIOR_POINT_REPLAY.json',old)
    inc=read(OUT/'VALIDATED_INTEGER_INCUMBENT.json');mig=read(OUT/'P2_MIGRATION_PROBE_RESULT.json')
    locks=[LexLock('rho',Fraction(inc['exact_UB']),True,sha(OUT/'P1_FULL_DOMAIN_INTEGER_GAP_CERTIFICATE.json'),Fraction(1e-7)),
        LexLock('migration_count',Fraction(0),True,mig['certificate']['sha256'])]
    locked,lockproof=rebuild_locked_snapshot(s,locks);native=Native(budget);attempts=[];result=dict(accepted=False,primal_only=True)
    try:
        for i,proposal in enumerate(prepared['proposals']):
            budget.remaining();resources=sample()
            if resources['unsafe']:raise RuntimeError('SYSTEM_RESOURCE_RESERVE_REQUIRED')
            f=OUT/'M19/P2/PRIMAL_REPAIR'/('C'+str(i));f.mkdir(parents=True,exist_ok=True)
            q,proof=fixed_query(locked,x,proposal);atomic(f/'PRIMAL_QUERY_PROOF.json',proof);atomic(f/'LOCK_REBUILD.json',lockproof)
            native.budget=Allocation(90);native.warm_point=None;native.warm_basis=None
            try:r,raw=native.solve(q,f,'NODE_LP')
            finally:native.budget=budget
            attempt=dict(candidate=i,native_status=r['status'],scientifically_accepted=False)
            if 'X' in raw:
                y=raw['X'];row=primal_replay(locked,y);phys=physical.verify(y)
                integral=np.max(abs(y[s.vtypes!='C']-np.rint(y[s.vtypes!='C'])))<=1e-5
                val=objective_value(s,y,'shift_magnitude')
                accepted=row['PASS'] and phys['PASS'] and integral and abs(float(val)-proposal['proposed_shift'])<=1e-5
                atomic(f/'ORIGINAL_LOCKED_ROWS_REPLAY.json',row);atomic(f/'FULL_ORIGINAL_A1_REPLAY.json',phys)
                attempt.update(scientifically_accepted=accepted,shift=float(val),integral=bool(integral))
                if accepted:
                    path=STATIC/f.relative_to(OUT)/'VALIDATED_PRIMAL.npz';np.savez_compressed(path,X=y)
                    cert=integer_optimality_certificate('shift_magnitude',float(val),prepared['prior_valid_global_LB'],
                        bound_independently_validated=True,primal_independently_validated=True,integrality_proven=True)
                    cert.update(scope='FULL_SCIENTIFIC_RELEVANT_INTEGER_DOMAIN_UNDER_CERTIFIED_PRIOR_LOCKS',
                        prior_full_domain_bound=record(OUT/'INTERRUPTED_BOUND_RECOVERY.json'),original_full_primal=record(f/'FULL_ORIGINAL_A1_REPLAY.json'),
                        repair_query_bound_used=False,independent_rational_MIP_dual_certificate=False)
                    if not cert['PASS']:raise ValueError('NEW_PRIMAL_DOES_NOT_CLOSE_SHIFT')
                    cp=f/'INTEGER_CERTIFICATE.json';atomic(cp,cert)
                    result.update(accepted=True,component='shift_magnitude',value=cert['incumbent_integer'],valid_LB=prepared['prior_valid_global_LB'],
                        certificate=record(cp),point=record(path),repair_query_bound_used=False)
            attempts.append(attempt);atomic(OUT/'PRIMAL_REPAIR_CHECKPOINT.json',dict(attempts=attempts,result=result,deadline=budget.record))
            print('PRIMAL_REPAIR',i,attempt,flush=True)
            if result['accepted']:break
    except Exception as e:result.update(stop_reason=repr(e),traceback=traceback.format_exc())
    finally:
        result.update(attempts=attempts,native_seconds=native.native_seconds,Work=sum(c.get('Work') or 0 for c in native.calls),
            peak_RSS_bytes=max((c.get('peak_RSS_bytes') or 0 for c in native.calls),default=0))
        atomic(OUT/'PRIMAL_REPAIR_NATIVE_CALLS.json',dict(calls=native.calls));atomic(OUT/'PRIMAL_REPAIR_RESULT.json',result)
        print('PRIMAL_REPAIR_RESULT',result.get('accepted'),result.get('stop_reason'),flush=True)
    return result
if __name__=='__main__':run()
