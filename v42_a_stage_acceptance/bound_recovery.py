"""Re-certify the same day's saved root and full pricing; no native rerun."""
from fractions import Fraction
from time import perf_counter
import numpy as np
from v42_pr134_b1.common import read,atomic,record
from v42_a_stage_phase1.core import primal_replay,verify_sign_convention,elastic_master,verify_zero
from v42_a_stage_phase1.backend import artificial_point
from v42_a_stage_phase1.runner import block_folder,serial
from v42_a_stage_phase1.oracle import validate_coverage
from v42_a_stage_compact_rowgen.lift import expanded_point
from .global_box import certify
from .policy import OUT

def recover(state,day):
    before=perf_counter();f=OUT/day;s=state['compact'];nr=read(f/'P1/S0/NATIVE_RESULT.json')
    if record(nr['raw_attributes']['path'])!=nr['raw_attributes']:raise ValueError('SAVED_P1_ROOT_BYTES_CHANGED')
    if read(nr['model_identity']['path'])['original_snapshot_sha256']!=s.fingerprint():raise ValueError('SAVED_P1_MODEL_CHANGED')
    with np.load(nr['raw_attributes']['path']) as z:raw={k:z[k].copy() for k in ('X','Pi','RC')}
    if not primal_replay(s,raw['X'])['PASS'] or not verify_sign_convention(s,raw['Pi'],raw['RC'])['PASS']:
        raise ValueError('SAVED_ROOT_INDEPENDENT_REPLAY_FAILED')
    expanded=expanded_point(state,raw['X']);original=primal_replay(state['reference'],expanded)
    if not original['PASS']:raise ValueError('SAVED_ROOT_ORIGINAL_ROWS_FAILED')
    master=elastic_master(s,state['grows']);point,replay=artificial_point(master,raw['X'])
    if not replay['PASS'] or not verify_zero(master,point)['PASS']:raise ValueError('SAVED_ROOT_NOT_ARTIFICIAL_FREE')
    pi=raw['Pi'].copy();pi[(s.senses=='<')&(pi>0)]=0;pi[(s.senses=='>')&(pi<0)]=0
    c=np.zeros(state['n'])
    for j,v in s.objective('rho').coefficients().items():
        if j<state['n']:c[j]=float(v)
    bound,proof=certify(s,state['grows'],state['n'],pi,c,state['axes'].values())
    atomic(f/'P1/GLOBAL_ORIGINAL_ROW_BOX_CERTIFICATE.json',proof)
    if bound is None or not proof['PASS']:raise ValueError('ORIGINAL_ROW_GLOBAL_BOUND_RECOVERY_FAILED')
    qualified=read(f/'BLOCK_PRICING_ORACLE_VERIFICATION.json');required={r['class_id']:r for r in qualified['records']}
    price=f/'P1/S0/PRICE';prior=read(price/'FULL_PRICING_RESULT.json')
    if not prior['no_negative_omitted_block_certified'] or prior['classes']!=len(required):raise ValueError('SAVED_FULL_PRICING_NOT_CLOSED')
    receipts=[read(block_folder(price,key)/'EXACT_COMPLETE_BLOCK_CERTIFICATE.json') for key in sorted(required)]
    coupling=np.asarray([pi[row] for row in state['axes'].values()])
    validate_coverage(required,receipts,coupling)
    lower=Fraction(bound)+sum((Fraction(r['certificate']['exact_lower_bound']) for r in receipts),Fraction())
    upper=sum((v*Fraction(float(raw['X'][j])) for j,v in s.objective('rho').coefficients().items()),Fraction(s.objective('rho').constant))
    if lower>upper:raise ValueError('REPAIRED_GLOBAL_BOUND_ABOVE_ORIGINAL_ROOT_POINT')
    repaired=dict(prior);repaired.update(global_bound=bound,full_domain_phase1_lower_bound=str(lower),
        full_bound_gap=str(upper-lower),full_bound_closes_active_LP=upper-lower<=Fraction(1,10000000),
        original_failed_pricing=record(price/'FULL_PRICING_RESULT.json'),global_box_certificate=record(f/'P1/GLOBAL_ORIGINAL_ROW_BOX_CERTIFICATE.json'),
        recovery_wall_seconds=perf_counter()-before,all_local_bounds_independently_replayed=True,native_reoptimization_calls=0)
    path=f/'P1/FULL_PRICING_RECERTIFIED_GLOBAL_BOUND.json';atomic(path,serial(repaired))
    atomic(f/'P1_RESULT.json',dict(PASS=True,P1_LP_closure=True,valid_LB=float(lower),exact_valid_LB=str(lower),P1_LP_value=float(upper),
        full_pricing=record(path),row_replay=original,own_date_checkpoint_recertified=True,native_reoptimization_calls=0))
    print('ORIGINAL_ROW_GLOBAL_BOUND_RECOVERED',day,float(lower),float(upper),len(proof['proofs']),len(receipts),flush=True)
    return expanded,repaired
