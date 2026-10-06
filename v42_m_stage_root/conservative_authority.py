"""Numerical consistency and exact lower-bound authority are separate gates.

Numerical zero never supplies a mathematical proof at an infinite bound.
Exact support arithmetic must still pay or eliminate every residual.
"""
import numpy as np
from fractions import Fraction as F

TAU_DUAL = 1e-8

def numerical_zero_sign(pi, sense):
    pi = np.asarray(pi, dtype=float).copy()
    sense = np.asarray(sense)
    if not np.isfinite(pi).all() or not np.isin(sense, ['<', '>', '=']).all():
        raise ValueError('INVALID_DUAL_OR_SENSE')
    bad = ((sense == '<') & (pi > 0)) | ((sense == '>') & (pi < 0))
    if np.any(abs(pi[bad]) > TAU_DUAL):
        raise ValueError('SIGN_VIOLATION_EXCEEDS_TAU_DUAL')
    trace = dict(canonicalized_Pi_count=int(bad.sum()),
                 maximum_canonicalized_absolute_Pi=float(np.max(abs(pi[bad]), initial=0)),
                 TAU_DUAL=TAU_DUAL)
    pi[bad] = 0.
    return pi, trace

def free_rc_consistency(rc, lower, upper):
    rc = np.asarray(rc, dtype=float)
    free = (~np.isfinite(lower) | (abs(np.asarray(lower)) >= 1e90)) & (~np.isfinite(upper) | (abs(np.asarray(upper)) >= 1e90))
    maximum = float(np.max(abs(rc[free]), initial=0))
    if not np.isfinite(rc).all() or maximum > TAU_DUAL:
        raise ValueError('FREE_RC_EXCEEDS_TAU_DUAL')
    return dict(numerical_consistency_PASS=True, maximum_free_absolute_RC=maximum,
                free_coordinates=int(free.sum()), exact_support_proof_still_required=True)

def split_gates(primal, dual, *, exact_signs, exact_columns, exact_bounds,
                independent_identity, corrected_formula, rational_verification):
    p, d = F(primal), F(dual)
    weak = d <= p
    conservative = all((exact_signs, exact_columns, exact_bounds, independent_identity,
                        corrected_formula, rational_verification, weak))
    return dict(OPTIMAL_DUAL_IDENTITY=abs(p-d) <= F(TAU_DUAL),
                CONSERVATIVE_DUAL_LB_CERTIFICATE=conservative,
                EXACT_DUAL_AUTHORITY_FOR_BAP=conservative,
                weak_duality_PASS=weak, strong_duality_difference=float(p-d),
                TAU_DUAL=TAU_DUAL)
