"""Complete local pricing certificates over ORIGINAL binary64 couplings."""
from fractions import Fraction
from dataclasses import replace
import numpy as np
from v42_a_stage_domain_v2.fast_pricing import _transpose_exact,verify_dual
from .producer import price_snapshot
from .core import exact_local_bound


def corrected_certificate(snapshot,B,pi,local_pi):
    """Round-off in the solver pricing objective cannot invalidate a bound.

The solver's objective is saved. Reconstruct true -B.T*pi rationally and
minimize every coefficient discrepancy over the ORIGINAL finite local box.
"""
    priced=price_snapshot(snapshot,B,pi)
    result=exact_local_bound(priced,local_pi)
    exact=tuple(-x for x in _transpose_exact(B,tuple(Fraction(float(x)) for x in pi)))
    rounded=priced.objective('local_price').coefficients()
    correction=Fraction(0);changed=0
    for j,true in enumerate(exact):
        delta=true-rounded.get(j,Fraction(0))
        if delta:
            changed+=1
            correction+=delta*Fraction(float(snapshot.lower[j] if delta>0 else snapshot.upper[j]))
    bound=None if result['lower_bound'] is None else Fraction(result['lower_bound'])+correction
    return dict(PASS=result['PASS'] and bound is not None,exact_original_binary64_objective=True,
        rounded_solver_objective_sha256=priced.fingerprint(),native_local_snapshot_sha256=snapshot.fingerprint(),
        certificate=result,roundoff_coefficient_count=changed,exact_box_roundoff_correction=str(correction),
        exact_lower_bound=None if bound is None else str(bound),true_coefficients=exact)


def true_objective(B,pi,point):
    coefficients=_transpose_exact(B,tuple(Fraction(float(x)) for x in pi))
    return -sum((c*Fraction(float(x)) for c,x in zip(coefficients,point)),Fraction(0))


def validate_coverage(required,certificates,expected_global_pi):
    """A declared PASS/completeness flag cannot substitute for actual coverage."""
    ids=[r['class_id'] for r in certificates]
    if len(set(ids))!=len(ids) or set(ids)!=set(required):raise ValueError('COMPLETE_BLOCK_COVERAGE_REQUIRED')
    for receipt in certificates:
        want=required[receipt['class_id']]
        if (receipt['full_snapshot_sha256']!=want['complete_local_snapshot_sha256']
                or receipt['graph_sha256']!=want['complete_graph_sha256']
                or receipt['physical_STAY']!=want['full_physical_STAY']
                or receipt['physical_migration']!=want['full_physical_migration']
                or receipt['certificate']['PASS'] is not True
                or receipt['certificate']['exact_lower_bound'] is None):
            raise ValueError('INDEPENDENT_COMPLETE_BLOCK_CERTIFICATE_REQUIRED')
        if not np.array_equal(receipt['global_coupling_pi'],expected_global_pi):
            raise ValueError('GLOBAL_PRICING_DUAL_MUTATION')
        # Reconstruct from the SHA-verified original producer cache, never a
        # caller's bound/PASS/completeness field.
        import gzip,pickle
        from v42_pr134_b1.common import record
        cache_record=want['external_full_block_cache']
        if record(cache_record['path'])!=cache_record:raise ValueError('FULL_BLOCK_CACHE_DRIFT')
        with gzip.open(cache_record['path'],'rb') as stream:cache=pickle.load(stream)
        checked=corrected_certificate(cache['snapshot'],cache['B'],expected_global_pi,receipt['local_raw_pi'])
        if not checked['PASS'] or checked['exact_lower_bound']!=receipt['certificate']['exact_lower_bound']:
            raise ValueError('FALSE_COMPLETE_BLOCK_LOWER_BOUND')
    return True
