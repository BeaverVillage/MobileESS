"""Solver-free exact bounded-Lagrangian audit of the captured barrier dual.

All stored binary64 inputs are interpreted as exact dyadic rationals.  The
certificate uses Python integer accumulation, not native optimization, an LP
model change, decimal rounding, or a guessed dual feasibility tolerance.
"""
import os
os.environ.update(OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1',
                  MKL_NUM_THREADS='1', NUMEXPR_NUM_THREADS='1')
import hashlib
import json
import math
import re
import time
from collections import defaultdict
from fractions import Fraction
from pathlib import Path

import numpy as np
from scipy import sparse

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
PARENT = ROOT / 'docs/v42_m1_ultracompact_exact_20261006'
MODEL_DOC = 'https://docs.gurobi.com/projects/optimizer/en/current/reference/attributes/model.html#objbound'
PI_DOC = 'https://docs.gurobi.com/projects/optimizer/en/current/reference/attributes/constraintlinear.html#pi'


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def dyadic(value):
    numerator, denominator = float(value).as_integer_ratio()
    return numerator, denominator.bit_length()-1


def denominator_upper(values):
    values = np.asarray(values)
    nonzero = values[values != 0]
    if not len(nonzero):
        return 0
    assert np.isfinite(nonzero).all()
    # binary64 v = m*2**e, with at most 53 significant bits in m.
    return max(0, 53-int(np.frexp(nonzero)[1].min()))


def exact_bounded_lagrangian(A, d, dual):
    """Valid for every feasible continuous point, without primal feasibility.

    For min c'x+c0, choose pi<=0 on <= rows, pi>=0 on >= rows, pi free
    on equalities.  Then c'x+c0 >= pi'b+c0 + sum_j min_{L_j<=z<=U_j}
    (c-A'pi)_j*z.  No reduced-cost sign/equality condition is needed because
    every selected variable has finite original bounds.
    """
    assert np.isfinite(d['lower']).all() and np.isfinite(d['upper']).all()
    assert np.isfinite(dual).all()
    pi = np.where(d['sense'] == '<', np.minimum(dual, 0),
                  np.where(d['sense'] == '>', np.maximum(dual, 0), dual))
    assert np.all(pi[d['sense'] == '<'] <= 0)
    assert np.all(pi[d['sense'] == '>'] >= 0)
    parts = [dyadic(value) for value in pi]
    p_exp = max((e for n,e in parts if n), default=0)
    base_exp = max(denominator_upper(A.data)+p_exp,
                   denominator_upper(d['rhs'])+p_exp,
                   denominator_upper(d['objective']),
                   dyadic(d['constant'])[1])
    bound_exp = max(denominator_upper(d['lower']), denominator_upper(d['upper']))
    total_exp = base_exp+bound_exp
    B = A.tocsc()
    objective_rhs_integer = 0
    for (p_num,p_den), rhs in zip(parts, d['rhs']):
        if not p_num or not rhs:
            continue
        b_num,b_den = dyadic(rhs)
        assert base_exp >= p_den+b_den
        objective_rhs_integer += (p_num*b_num) << (base_exp-p_den-b_den)
    c_num,c_den = dyadic(d['constant'])
    objective_rhs_integer += c_num << (base_exp-c_den)
    all_terms_integer = 0
    exact_terms_float = np.empty(A.shape[1])
    exact_residual_float = np.empty(A.shape[1])
    products = 0
    for column in range(A.shape[1]):
        dot_integer = 0
        for index in range(B.indptr[column], B.indptr[column+1]):
            p_num,p_den = parts[int(B.indices[index])]
            if not p_num:
                continue
            a_num,a_den = dyadic(B.data[index])
            assert base_exp >= a_den+p_den
            dot_integer += (a_num*p_num) << (base_exp-a_den-p_den)
            products += 1
        c_num,c_den = dyadic(d['objective'][column])
        residual_integer = (c_num << (base_exp-c_den))-dot_integer
        bound = d['lower'][column] if residual_integer >= 0 else d['upper'][column]
        b_num,b_den = dyadic(bound)
        assert bound_exp >= b_den
        term_integer = (residual_integer*b_num) << (bound_exp-b_den)
        all_terms_integer += term_integer
        exact_terms_float[column] = float(Fraction(term_integer, 1 << total_exp))
        exact_residual_float[column] = float(Fraction(residual_integer, 1 << base_exp))
    total_integer = (objective_rhs_integer << bound_exp)+all_terms_integer
    certificate = Fraction(total_integer, 1 << total_exp)
    lower = float(certificate)
    if Fraction.from_float(lower) > certificate:
        lower = float(np.nextafter(lower, -np.inf))
    assert Fraction.from_float(lower) <= certificate
    return dict(lower_bound=lower, exact_rational=str(certificate),
                dyadic_accumulation_exponent=total_exp,
                matrix_nonzeros=A.nnz, nonzero_dual_products_evaluated=products,
                columns_with_exact_residual_and_bound_min=A.shape[1],
                exact_pi_rhs_and_constant=float(Fraction(objective_rhs_integer, 1 << base_exp)),
                exact_bound_correction=float(Fraction(all_terms_integer, 1 << total_exp)),
                valid_for_all_supplied_matrix_relaxed_feasible_points=True,
                valid_for_original_integer_points_if_all_added_rows_independently_valid=True,
                precision='Exact Python integer dyadic products/sums and Fraction final ratio; lower float outward-rounded'), pi, exact_residual_float, exact_terms_float


def main():
    started = time.perf_counter()
    paths = [PARENT/'C3A_A.npz', PARENT/'C3A_DATA.npz',
             OUT/'PURE_LP_POINT.npz', OUT/'PURE_LP_RESULT.json']
    before = {str(path): sha(path) for path in paths}
    assert before[str(PARENT/'C3A_A.npz')] == '45cd48423b8d7f19fed376b71e181277f559c9e71527c17f9322d0100f7f0df8'
    assert before[str(PARENT/'C3A_DATA.npz')] == '20aba68ffb3c4e29b0c9644d05e10ef33417ab92f6083edfb8906d6be8cb0467'
    A = sparse.load_npz(PARENT/'C3A_A.npz')
    with np.load(PARENT/'C3A_DATA.npz') as archive:
        d = {key: archive[key] for key in archive.files}
    with np.load(OUT/'PURE_LP_POINT.npz') as archive:
        x = archive['x']; pi = archive['dual']; rc = archive['reduced_cost']
    native = json.loads((OUT/'PURE_LP_RESULT.json').read_text())
    residual = d['objective']-A.T@pi
    uncorrected_terms = np.where(residual >= 0, residual*d['lower'], residual*d['upper'])
    rc_terms = np.where(rc >= 0, rc*d['lower'], rc*d['upper'])
    certificate, clipped, exact_residual, exact_terms = exact_bounded_lagrangian(A, d, pi)
    wrong = abs(pi-clipped)
    signs_by_family = defaultdict(lambda: dict(count=0, max_violation=0., sum_abs_violation=0.))
    for row in np.flatnonzero(wrong):
        family = str(d['row_names'][row]).split('[')[0]
        signs_by_family[family]['count'] += 1
        signs_by_family[family]['max_violation'] = max(signs_by_family[family]['max_violation'], float(wrong[row]))
        signs_by_family[family]['sum_abs_violation'] += float(wrong[row])
    bound_by_family = defaultdict(float)
    for column, term in enumerate(exact_terms):
        bound_by_family[str(d['names'][column]).split('[')[0]] += float(term)
    critical_columns = [dict(column=int(column), name=str(d['names'][column]),
        lower=float(d['lower'][column]), upper=float(d['upper'][column]),
        X=float(x[column]), exact_residual_rounded=float(exact_residual[column]),
        exact_bound_term_rounded=float(exact_terms[column]))
        for column in np.argsort(exact_terms)[:20]]
    native_bound = float(native['native_global_LP_LB'])
    matching_log = []
    for line in (OUT/'PURE_LP.log').read_text().splitlines():
        match = re.fullmatch(r'\s*(\d+)\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)\s+(\d+)s\s*', line)
        if match and abs(float(match[3])-native_bound) <= 5e-7:
            matching_log.append(dict(iteration=int(match[1]), primal_printed=float(match[2]),
                dual_printed=float(match[3]), primal_residual_printed=float(match[4]),
                dual_residual_printed=float(match[5]), time_printed=int(match[7]), raw_line=line))
    after = {str(path): sha(path) for path in paths}
    assert before == after
    report = dict(
        classification='CAPTURED_BARRIER_POINT_HAS_RAW_NUMERICAL_RESIDUALS_AND_A_WEAK_NATIVE_LP_BOUND',
        PASS=True, optimize_calls=0, native_model_build_calls=0,
        source_hashes=before, all_input_hashes_unchanged=True,
        native_status=int(native['Status']), native_primal_objective=float(native['objective']),
        native_ObjBound=native_bound, independent_raw_point_replay=native['independent_relaxed_matrix_replay'],
        native_LP_bound_not_relabelled_as_primal_objective=True,
        native_bound_matching_barrier_log_iterations=matching_log,
        bound_retention_inference='Native ObjBound matches printed barrier iteration 8 dual objective. '
            'The final captured Pi has inequality-sign violations. Retention of an earlier conservative '
            'dual bound is supported; the internal bound-update threshold is not observed or asserted.',
        internal_attribute_bug_not_assumed=True,
        finite_bounds=dict(all_finite=True, minimum_lower=float(d['lower'].min()),
            maximum_upper=float(d['upper'].max()), absolute_bound_max=float(max(abs(d['lower']).max(), abs(d['upper']).max())),
            free_or_native_infinity_bounds=0),
        captured_dual=dict(wrong_sign_inequality_duals=int((wrong > 0).sum()),
            maximum_wrong_sign=float(wrong.max()), by_row_family=dict(signs_by_family),
            c_minus_ATPi_vs_reported_RC_max=float(abs(residual-rc).max()),
            Pi_rhs_plus_constant=float(pi@d['rhs']+float(d['constant'])),
            uncorrected_lagrangian_float=float(pi@d['rhs']+float(d['constant'])+uncorrected_terms.sum()),
            reported_RC_bound_expression_float=float(pi@d['rhs']+float(d['constant'])+rc_terms.sum()),
            those_uncorrected_values_are_not_valid_dual_certificates=True),
        independently_valid_exact_certificate=certificate,
        exact_bound_correction_by_column_family_float=dict(bound_by_family),
        top20_negative_bound_corrections=critical_columns,
        derivation='For clipped row multipliers with correct inequality signs, '
            'LB=ObjCon+pi^T rhs+sum_j min_{lower_j<=z<=upper_j}(c-A^T pi)_j z. '
            'All products, sums, residual signs and bound choices are computed exactly as dyadic '
            'rationals. This supplies a global continuous LP lower bound without primal feasibility '
            'or a solve. Clipping changes only the mathematical certificate, never the model or native solver.',
        best_existing_C3A_valid_native_LB=0.5687116003498334,
        certificate_improves_existing_valid_LB=certificate['lower_bound'] > 0.5687116003498334,
        recommended_reporting='Retain all three separate: approximate barrier ObjVal, actual native '
            'LP ObjBound, and independent exact Lagrangian certificate. For any integer-set-preserving '
            'C3S, existing C3A native valid LB remains valid. Numerical raw FAIL remains explicit. '
            'Do not claim material LB improvement from the barrier primal objective.',
        future_round_certificate_inputs='Augmented immutable CSR/RHS/senses/bounds/objective and '
            'captured Pi for every added row are sufficient; no new optimization or parameter change.',
        primary_documentation=[dict(title='Gurobi 13 Model Attributes: ObjBound', url=MODEL_DOC,
            support='ObjBound is the best known objective bound; LP ObjBound/ObjBoundC coincide; available after solve.'),
            dict(title='Gurobi 13 Linear Constraint Attributes: Pi', url=PI_DOC,
            support='For minimization, <= row duals are nonpositive and >= row duals nonnegative.')],
        runtime_seconds=time.perf_counter()-started,
    )
    (OUT/'NUMERICAL_LP_BOUND_AUDIT.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    print('EXACT_BOUND_AUDIT_DONE', certificate['lower_bound'],
          'native', native_bound, 'seconds', report['runtime_seconds'], flush=True)


if __name__ == '__main__':
    main()
