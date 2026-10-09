"""Original-matrix exact signed-dual proof for trajectory Lagrangian prices.

Native local objectives/ObjBound and restricted-master objectives are never
promoted to a Global LB.  Actual binary64 price rounding is diagnostic only;
all certificates reassemble multipliers on the original unrounded matrix.
"""
from fractions import Fraction
from time import perf_counter
import numpy as np
from v42_m1_research.check_lb import check_rational_dual_certificate


def rational_dual(dual, size):
    if isinstance(dual, dict):
        result = {}
        for key, value in dual.items():
            i = int(key)
            if str(i) != str(key) or not 0 <= i < size:
                raise ValueError('SPARSE_DUAL_AXIS_DRIFT')
            q = Fraction(value)
            if q:
                result[i] = q
        return result
    y = np.asarray(dual, dtype=np.float64)
    if y.shape != (size,) or not np.isfinite(y).all():
        raise ValueError('DUAL_AXIS_OR_FINITE_DRIFT')
    return {int(i):Fraction(float(y[i])) for i in np.flatnonzero(y)}


def check_signs(dual, senses):
    for i,q in dual.items():
        s = str(senses[i])
        if s not in ('<','>','=') or (s == '<' and q > 0) or (s == '>' and q < 0):
            raise ValueError('INVALID_LAGRANGIAN_DUAL_SIGN')


def assemble_full_dual(case, decomp, coupling_dual, unit_duals, nonunit_dual):
    """Embed all block/coupling signed multipliers on original row axes."""
    from .blocks import verify_decomposition
    verify_decomposition(case, decomp)
    if set(unit_duals) != set(decomp.units):
        raise ValueError('ALL_FOUR_UNIT_DUALS_REQUIRED')
    pieces = [(decomp.coupling_rows, coupling_dual)]
    pieces += [(b.original_rows, unit_duals[u]) for u,b in decomp.units.items()]
    pieces.append((decomp.nonunit_block.original_rows, nonunit_dual))
    result = {}
    for rows, dual in pieces:
        active = rational_dual(dual, len(rows))
        check_signs(active, case.d['sense'][rows])
        for i,q in active.items():
            original = int(rows[i])
            if original in result:
                raise ValueError('FULL_DUAL_ROW_ASSIGNED_TWICE')
            result[original] = str(q)
    return result


def certify_global(case, decomp, coupling_dual, unit_duals, nonunit_dual):
    """Finite-box weak duality: valid even with incomplete/time-limited pricing."""
    full = assemble_full_dual(case, decomp, coupling_dual, unit_duals, nonunit_dual)
    certificate = check_rational_dual_certificate(case.A, case.d, full, case_sha=case.case_sha)
    certificate.update(certified_domain='FULL_ORIGINAL_C3A_INTEGER_DOMAIN',
        theorem='SIGNED_COUPLING_PLUS_LOCAL_PLUS_NONUNIT_DUALS_AND_EXACT_ORIGINAL_RESIDUAL_BOX',
        all_four_trajectory_blocks_included=len(decomp.units)==4, nonunit_original_domain_included=True,
        native_local_MIP_ObjBound_used=False, rounded_pricing_objective_used=False,
        restricted_master_objective_used=False, pricing_closure_required_for_this_LB=False,
        structural_integer_block_improvement_proven=False)
    if len(decomp.units)!=4:
        certificate.update(all_trajectory_blocks_included=True,unit_count=len(decomp.units))
    return certificate


def local_exact_price_bound(block, exact_objective, dual):
    """A local LP dual proves a lower bound for the unchanged integer domain.

    exact_objective is sparse local-column→Fraction, including original c.
    This routine records the equivalent decomposition sum; the authoritative
    global proof always rechecks the original full CSR independently.
    """
    begin=perf_counter()
    y = rational_dual(dual, block.A.shape[0])
    check_signs(y, block.d['sense'])
    residual = {int(j):Fraction(q) for j,q in exact_objective.items() if q}
    weighted = Fraction(0)
    A = block.A.tocsr()
    for i,q in y.items():
        weighted += q*Fraction(float(block.d['rhs'][i]))
        for j,a in zip(A.indices[A.indptr[i]:A.indptr[i+1]], A.data[A.indptr[i]:A.indptr[i+1]]):
            j = int(j)
            residual[j] = residual.get(j,Fraction(0))-q*Fraction(float(a))
    correction = sum((q*Fraction(float(block.d['lower'][j] if q > 0 else block.d['upper'][j]))
                      for j,q in residual.items() if q), Fraction(0))
    total = weighted+correction
    value = float(total)
    if Fraction(value) > total:
        value = float(np.nextafter(value,-np.inf))
    return dict(PASS=True, exact_bound=str(total), independently_certified_LB=value,
                weighted_rhs_exact=str(weighted), box_correction_exact=str(correction),
                residual_nonzero_columns=sum(bool(q) for q in residual.values()),
                native_ObjBound_used=False, integer_pricing_closure=False,
                check_wall_seconds=perf_counter()-begin)


def compare_dw_lagrangian(*, rmp_objective=None, pricing_closed=False,
                          exact_lagrangian_certificate=None):
    return dict(restricted_master_objective=rmp_objective,
        restricted_master_is_global_LB=False,
        restricted_master_is_global_UB=False,
        pricing_closure_independently_proven=bool(pricing_closed),
        independently_certified_global_LB=(None if exact_lagrangian_certificate is None
            else exact_lagrangian_certificate.get('independently_certified_LB')),
        same_price_relation='DW full pricing and Lagrangian minimization use the same signed coupling prices; a finite restricted master has no global-bound authority',
        integer_block_strengthening='NOT_PROVEN')
