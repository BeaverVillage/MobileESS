"""Reconstruct PR180 Shift authority without calling optimize."""
import gzip,pickle
from dataclasses import replace
from fractions import Fraction
from time import perf_counter
import numpy as np
import scipy.sparse as sp
from v42_pr134_b1.common import read,record,atomic,sha
from v42_a_stage_domain_v2.lexstage import LexLock,rebuild_locked_snapshot,integer_optimality_certificate
from v42_a_stage_domain_v2.strengthening import strengthen_histogram_capacity
from v42_a_stage_cg.cuts import strengthen
from v42_a_stage_lexrefine.partition import split
from v42_a_stage_lexfull.runner import objective_value
from v42_a_stage_phase1.core import primal_replay
from .gap import global_gap_acceptance
from .physical import Physical
from .policy import OUT,OLD,ROOT,STATIC

def checked(r):
    if record(r['path'])!=r:raise ValueError('HISTORICAL_EVIDENCE_DRIFT:'+r['path'])
    return r

def run():
    t=perf_counter();f=OUT/'2025-05-19';f.mkdir(parents=True,exist_ok=True)
    build=read(OLD/'LEX_FULL_BUILD_VERIFICATION.json');checked(build['state'])
    with gzip.open(build['state']['path'],'rb') as stream:p=pickle.load(stream)
    state,original=p['state'],p['snapshot']
    if original.fingerprint()!=build['snapshot_sha256']:raise ValueError('ORIGINAL_FULL_DOMAIN_STATE_DRIFT')
    roster=read(ROOT/'docs/v42_a_stage_phase1_pricing_20261007/BLOCK_PRICING_ORACLE_VERIFICATION.json')['records']
    if {r['class_id'] for r in roster}!=set(state['data'][7]['classes']):raise ValueError('ALL_CLASS_COVERAGE_REQUIRED')
    for r in roster:checked(r['external_full_block_cache'])
    # Re-run every native local projection proof, including full STAY membership,
    # then reconstruct ALL global and local rows on original variable types.
    import v42_a_stage_canary.zero as zero
    zero.OUT=OUT
    atomic(f/'BLOCK_PRICING_ORACLE_VERIFICATION.json',dict(PASS=True,records=roster))
    rebuilt_state,rebuilt=zero.build(state,original,'2025-05-19')
    if rebuilt.fingerprint()!=original.fingerprint():raise ValueError('INDEPENDENT_COMPLETE_ZERO_DOMAIN_REBUILD_MISMATCH')
    del rebuilt,rebuilt_state
    physical=Physical(state,original)
    hist,histproof=strengthen_histogram_capacity(original,original,physical.descriptor,state['data'],
        np.arange(original.matrix.shape[1],dtype=np.int64))
    strong,cgproof=strengthen(original,hist,histproof)
    cg=read(OLD/'WEIGHTED_CG_BUILD_VERIFICATION.json');checked(cg['snapshot'])
    with gzip.open(cg['snapshot']['path'],'rb') as stream:prior_strong=pickle.load(stream)
    if strong.fingerprint()!=prior_strong.fingerprint():raise ValueError('INDEPENDENT_INTEGER_STRENGTHENING_REBUILD_MISMATCH')
    del prior_strong
    inc=read(OLD/'VALIDATED_INTEGER_INCUMBENT.json');p1=read(OLD/'P1_FULL_DOMAIN_INTEGER_GAP_CERTIFICATE.json')
    mig=read(OLD/'P2_MIGRATION_PROBE_RESULT.json');checked(mig['certificate'])
    if not p1['PASS'] or inc['gap']>.005 or not mig['accepted'] or mig['value']!=0 or mig['full_domain_bound']!=0:
        raise ValueError('INHERITED_P1_AND_GLOBAL_MIGRATION_ZERO_REQUIRED')
    locks=[LexLock('rho',Fraction(inc['exact_UB']),True,sha(OLD/'P1_FULL_DOMAIN_INTEGER_GAP_CERTIFICATE.json'),Fraction(1e-7)),
           LexLock('migration_count',Fraction(0),True,mig['certificate']['sha256'])]
    locked,lockproof=rebuild_locked_snapshot(strong,locks);obj=locked.objective('shift_magnitude')
    query=replace(locked,objectives=(obj,)+tuple(o for o in locked.objectives if o.name!=obj.name))
    left,partition=split(query,'shift_magnitude',950)
    nf=OLD/'M19/P2/DIRECT/SHIFT_MAGNITUDE/N0'
    priorpartition=read(nf/'EXHAUSTIVE_OBJECTIVE_PARTITION.json')
    if partition!=priorpartition:raise ValueError('COMPLETE_OBJECTIVE_PARTITION_REBUILD_MISMATCH')
    identity=read(nf/'MODEL_IDENTITY.json');checked(identity['matrix']);checked(identity['attributes'])
    A=sp.load_npz(identity['matrix']['path']);delta=A-left.matrix;delta.eliminate_zeros()
    if delta.nnz or identity['original_snapshot_sha256']!=left.fingerprint():raise ValueError('ACTUAL_EXECUTED_QUERY_MATRIX_MISMATCH')
    del A,delta
    attrs=np.load(identity['attributes']['path'])
    for a in ('lower','upper','senses','rhs','vtypes'):
        if not np.array_equal(attrs[a],getattr(left,a)):raise ValueError('ACTUAL_EXECUTED_QUERY_ATTRIBUTE_MISMATCH:'+a)
    coefficients=np.zeros(left.matrix.shape[1])
    for j,c in obj.coefficients().items():coefficients[j]=float(c)
    if not np.array_equal(attrs['objective'],coefficients):raise ValueError('ACTUAL_ORIGINAL_SHIFT_OBJECTIVE_MISMATCH')
    attrs.close()
    rec=read(nf/'NATIVE_RESULT.json');provenance=read(nf/'FULL_DOMAIN_INTEGER_BOUND_PROVENANCE.json')
    for k in ('current_result','actual_model','full_relevant_domain','integer_valid_strengthening','partition'):checked(provenance[k])
    if rec['status'] not in (2,9,11) or rec['native_error'] is not None or rec['ObjBound']!=948:
        raise ValueError('FINAL_CURRENT_SOLVER_BOUND_NOT_VALID')
    queue=read(OLD/'DIRECT_CHECKPOINT.json')
    if len(queue['queue'])!=1 or queue['queue'][0]['partition']!=partition or queue['valid_global_LB']!=948:
        raise ValueError('UNRESOLVED_FULL_DOMAIN_BRANCH_LEDGER_MISMATCH')
    checked(queue['incumbent']['point']);warm=np.load(queue['incumbent']['point']['path'])['X']
    replay=physical.verify(warm);rows=primal_replay(locked,warm)
    values={name:objective_value(original,warm,name) for name in ('rho','migration_count','shift_magnitude','prestart_relocation')}
    if not replay['PASS'] or not rows['PASS'] or values['migration_count']!=0 or values['shift_magnitude']!=950:
        raise ValueError('ORIGINAL_PHYSICAL_INCUMBENT_AND_LOCKS_REPLAY_FAILED')
    atomic(f/'SHIFT_ORIGINAL_PHYSICAL_REPLAY.json',replay);atomic(f/'SHIFT_LOCKED_ROW_REPLAY.json',rows)
    audit=dict(PASS=True,full_domain=True,all_classes=len(roster),original_snapshot=original.fingerprint(),
        strengthened_snapshot=strong.fingerprint(),actual_left_snapshot=left.fingerprint(),
        full_domain_independently_rebuilt=True,integer_strengthening_independently_rebuilt=True,
        partitions=[dict(status='OPEN',restriction='shift <= 949',valid_LB=rec['ObjBound'],
            native_result=record(nf/'NATIVE_RESULT.json'),includes_all_native_open_nodes=True),
            dict(status='BOUND_PRUNED',restriction='shift >= 950',valid_LB=950)],
        prior_external_branch_queues_subsumed_by_complete_current_left_query=True,
        LB=min(rec['ObjBound'],950),UB=950,locks=lockproof,incumbent=queue['incumbent']['point'],
        independent_rational_MIP_dual_certificate=False,authority='FINAL_POSTSOLVE_NATIVE_OBJBOUND_ON_VERIFIED_COMPLETE_QUERY',
        interrupted_not_infeasible=True,original_native_status=rec['status'],historical_35082_nodes_not_rerun=True,
        audit_seconds=perf_counter()-t,objective_values={k:str(v) for k,v in values.items()},
        official_bound_contract='https://docs.gurobi.com/projects/optimizer/en/current/reference/attributes/model.html#objbound',
        PR134_shift_gap=2/727,PR134_prestart_gap=1/231,PR134_exact_integer_optima_not_claimed=True)
    atomic(f/'SHIFT_FULL_DOMAIN_BOUND_AUDIT.json',audit)
    cert=global_gap_acceptance('shift_magnitude',948,950,full_domain_verified=True,bound_verified=True,
        primal_verified=True,locks_verified=True,native_status=rec['status'])
    cert.update(audit=record(f/'SHIFT_FULL_DOMAIN_BOUND_AUDIT.json'),incumbent=queue['incumbent']['point'],
        acceptance_lock_value=950,exact_optimality_certificate=integer_optimality_certificate('shift_magnitude',950,948,
            bound_independently_validated=True,primal_independently_validated=True,integrality_proven=True))
    atomic(f/'SHIFT_GLOBAL_GAP_ACCEPTANCE.json',cert)
    if not cert['PASS'] or cert['exact_optimality_certificate']['PASS']:raise ValueError('GAP_AND_EXACT_PROOF_SEPARATION_FAILED')
    point=STATIC/'2025-05-19/SHIFT_REPLAY_PASS_POINT.npz';point.parent.mkdir(parents=True,exist_ok=True)
    np.savez_compressed(point,X=warm)
    atomic(f/'SHIFT_ACCEPTED_STATE.json',dict(PASS=True,point=record(point),build=record(OLD/'LEX_FULL_BUILD_VERIFICATION.json'),
        gap_certificate=record(f/'SHIFT_GLOBAL_GAP_ACCEPTANCE.json'),accepted_shift=950))
    print('MAY19_SHIFT_AUDIT_PASS',cert['gap'],flush=True)
    return state,original,strong,warm,locks,physical

if __name__=='__main__':run()
