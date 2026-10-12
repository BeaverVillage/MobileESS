"""Separate rational certificates over the unchanged full local domain.

Never changes persisted Pi/X or lowers a tolerance. A zero dual is an
independent certificate candidate, not a claim that a missing improving
direction is impossible. Active upper bounds require a checked witness.
"""
from fractions import Fraction
import numpy as np
from v42_a_stage_domain_v2.fast_pricing import _transpose_exact, _box_minimum


def true_coefficients(B, global_pi):
    return tuple(-v for v in _transpose_exact(
        B, tuple(Fraction(float(v)) for v in global_pi)))


def direct_bound(snapshot, coefficients, multipliers):
    """One exact box minimization, without splitting coefficient corrections."""
    if len(coefficients) != snapshot.matrix.shape[1] or len(multipliers) != snapshot.matrix.shape[0]:
        raise ValueError('CERTIFICATE_AXIS')
    pi = tuple(Fraction(v) for v in multipliers)
    if any((s == '<' and p > 0) or (s == '>' and p < 0)
           for s, p in zip(snapshot.senses, pi)):
        raise ValueError('CERTIFICATE_DUAL_SIGN')
    weighted = _transpose_exact(snapshot.matrix, pi)
    residual = tuple(c-v for c, v in zip(coefficients, weighted))
    box, unbounded = _box_minimum(residual, snapshot.lower, snapshot.upper)
    if unbounded:
        return None
    return box + sum((p*Fraction(float(r)) for p, r in zip(pi, snapshot.rhs)), Fraction(0))


def strengthened_bound(snapshot, B, global_pi, raw_local_pi):
    coefficients = true_coefficients(B, global_pi)
    pi = [Fraction(float(v)) for v in raw_local_pi]
    for j, sense in enumerate(snapshot.senses):
        if (sense == '<' and pi[j] > 0) or (sense == '>' and pi[j] < 0):
            pi[j] = Fraction(0)
    candidates = [('DIRECT_TRUE_OBJECTIVE', direct_bound(snapshot, coefficients, pi)),
                  ('SEPARATE_ZERO_DUAL', direct_bound(snapshot, coefficients, [Fraction(0)]*len(pi)))]
    valid = [(name, value) for name, value in candidates if value is not None]
    if not valid:
        raise ValueError('NO_FINITE_EXACT_LOWER_BOUND')
    name, value = max(valid, key=lambda item: item[1])
    return dict(PASS=True, method=name, exact_lower_bound=str(value),
                candidates={n: None if v is None else str(v) for n, v in candidates},
                full_domain_unchanged=True, raw_dual_modified=False,
                approximate_negative_support_absence_is_not_a_proof=True)


def single_column_witness(snapshot, coefficients, mass):
    """Exact feasible active endpoint, useful for pure STAY histogram blocks.

    No rounding or optimizer. Every row and bound is checked rationally;
    failure returns None. The original point is not changed.
    """
    mass = Fraction(mass)
    if mass <= 0 or len(coefficients) != snapshot.matrix.shape[1]:
        raise ValueError('WITNESS_AXIS_OR_MASS')
    if np.any(snapshot.lower > 0) or np.any(snapshot.upper < 0):
        return None
    csc = snapshot.matrix.tocsc()
    for column, coefficient in enumerate(coefficients):
        if coefficient != 0 or not ((not np.isfinite(snapshot.lower[column]) or Fraction(float(snapshot.lower[column])) <= mass)
                and (not np.isfinite(snapshot.upper[column]) or mass <= Fraction(float(snapshot.upper[column])))):
            continue
        activity = {}
        for k in range(csc.indptr[column], csc.indptr[column+1]):
            row = int(csc.indices[k])
            activity[row] = activity.get(row, Fraction(0)) + Fraction(float(csc.data[k]))*mass
        good = True
        for row, (sense, rhs) in enumerate(zip(snapshot.senses, snapshot.rhs)):
            value = activity.get(row, Fraction(0)); rhs = Fraction(float(rhs))
            if ((sense == '=' and value != rhs) or (sense == '<' and value > rhs)
                    or (sense == '>' and value < rhs)):
                good = False; break
        if good:
            return dict(PASS=True, column=column, exact_mass=str(mass), exact_objective='0',
                        rows_checked=snapshot.matrix.shape[0], bounds_checked=snapshot.matrix.shape[1],
                        original_point_modified=False, new_local_witness_only=True)
    return None
