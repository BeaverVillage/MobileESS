"""Separate elastic master, native sign replay and exact bounded LP proofs.

Original columns/rows/bounds are copied byte for byte. Only explicitly global
rows receive auxiliary columns. Candidate-local rows and variable bounds stay
hard. Artificials are never part of an original-objective model.
"""
from dataclasses import dataclass, replace
from fractions import Fraction
import math
import numpy as np
import scipy.sparse as sp
from v42_a_stage_domain_v2.lexstage import Objective
from v42_a_stage_domain_v2.fast_pricing import verify_dual


@dataclass(frozen=True)
class ElasticMaster:
    original: object
    snapshot: object
    global_rows: tuple
    artificial_rows: tuple
    artificial_signs: tuple
    weights: tuple

    def verify(self):
        a, b = self.original.require(), self.snapshot.require()
        n = a.matrix.shape[1]
        d = b.matrix[:, :n] - a.matrix
        d.eliminate_zeros()
        if d.nnz or not all(np.array_equal(getattr(a, f), getattr(b, f)[:n])
                            for f in ('lower', 'upper', 'vtypes')):
            raise ValueError('ORIGINAL_SCIENTIFIC_COLUMNS_OR_BOUNDS_CHANGED')
        if not all(np.array_equal(getattr(a, f), getattr(b, f)) for f in ('senses', 'rhs')):
            raise ValueError('ORIGINAL_ROW_AUTHORITY_CHANGED')
        if len(set(self.global_rows)) != len(self.global_rows):
            raise ValueError('GLOBAL_ROW_DUPLICATE')
        if (len(self.weights) != len(self.artificial_rows)
                or any(Fraction(w) <= 0 for w in self.weights)):
            raise ValueError('STRICTLY_POSITIVE_RATIONAL_WEIGHTS_REQUIRED')
        expected = sp.csc_matrix((self.artificial_signs,
            (self.artificial_rows, np.arange(len(self.artificial_rows)))),
            shape=(a.matrix.shape[0], len(self.artificial_rows)))
        d = b.matrix[:, n:] - expected
        d.eliminate_zeros()
        if d.nnz or not set(self.artificial_rows) <= set(self.global_rows):
            raise ValueError('ARTIFICIAL_LOCAL_PHYSICS_OR_SIGN_MUTATION')
        if any(b.lower[n:] != 0) or any(b.upper[n:] < 1e100):
            raise ValueError('NONNEGATIVE_UNBOUNDED_ARTIFICIAL_REQUIRED')
        want = {n+i: Fraction(w) for i, w in enumerate(self.weights)}
        if b.objective('Phi').coefficients() != want:
            raise ValueError('PHASE1_OBJECTIVE_MUTATION')
        return True


def elastic_master(original, global_rows):
    """Fixed dyadic row normalization: 1/next power of two of native scale."""
    original.require()
    if any(original.lower > original.upper):
        raise ValueError('PHASE_I_IMPLEMENTATION_INVALID_BOUND_BOX')
    rows, signs, weights = [], [], []
    for row in sorted(global_rows):
        if type(row) is not int or not 0 <= row < original.matrix.shape[0]:
            raise ValueError('GLOBAL_ROW_AXIS')
        a = original.matrix.data[original.matrix.indptr[row]:original.matrix.indptr[row+1]]
        scale = max(1., abs(float(original.rhs[row])), float(np.max(abs(a), initial=0)))
        weight = Fraction(1, 2**max(0, math.ceil(math.log2(scale))))
        sense = original.senses[row]
        for sign in ((1., -1.) if sense == '=' else (-1.,) if sense == '<' else (1.,)):
            rows.append(row); signs.append(sign); weights.append(weight)
    n = original.matrix.shape[1]
    art = sp.csr_matrix((signs, (rows, np.arange(len(rows)))),
                       shape=(original.matrix.shape[0], len(rows)))
    snapshot = replace(original, matrix=sp.hstack((original.matrix, art), format='csr'),
        lower=np.r_[original.lower, np.zeros(len(rows))],
        upper=np.r_[original.upper, np.full(len(rows), np.inf)],
        vtypes=np.r_[original.vtypes, np.full(len(rows), 'C')],
        objectives=(Objective('Phi', tuple((n+i, w) for i, w in enumerate(weights)), Fraction(0)),))
    result = ElasticMaster(original, snapshot, tuple(sorted(global_rows)), tuple(rows), tuple(signs), tuple(weights))
    result.verify()
    return result


def reconstructed_reduced_cost(snapshot, pi):
    c = np.zeros(snapshot.matrix.shape[1])
    for j, value in snapshot.objectives[0].coefficients().items(): c[j] = float(value)
    return c - snapshot.matrix.T @ np.asarray(pi)


def verify_sign_convention(snapshot, pi, native_rc, *, absolute=1e-7, relative=1e-10):
    """Includes bound RC, not just interior stationarity; no RC sign shortcut."""
    pi, native_rc = np.asarray(pi), np.asarray(native_rc)
    if (pi.shape != (snapshot.matrix.shape[0],) or native_rc.shape != (snapshot.matrix.shape[1],)
            or not np.all(np.isfinite(pi)) or not np.all(np.isfinite(native_rc))):
        raise ValueError('FINITE_NATIVE_DUAL_RC_AXES_REQUIRED')
    rebuilt = reconstructed_reduced_cost(snapshot, pi)
    errors = abs(rebuilt-native_rc)
    allowed = absolute + relative*np.maximum(abs(rebuilt), abs(native_rc))
    bad = np.flatnonzero(errors > allowed)
    return dict(PASS=bool(len(bad) == 0), convention='min: RC=c-A.T@Pi; <=Pi<=0, >=Pi>=0; bounds retained',
        maximum_absolute_error=float(errors.max(initial=0)), rejected_columns=bad[:20].tolist(),
        absolute_tolerance=absolute, relative_tolerance=relative,
        every_native_column_reconstructed=True, raw_pi_or_primal_modified=False)


def primal_replay(snapshot, point, tolerance=1e-6):
    x = np.asarray(point)
    if x.shape != (snapshot.matrix.shape[1],) or not np.all(np.isfinite(x)):
        raise ValueError('FINITE_RAW_PRIMAL_REQUIRED')
    activity = snapshot.matrix @ x
    rows = np.maximum(0, np.where(snapshot.senses == '<', activity-snapshot.rhs,
        np.where(snapshot.senses == '>', snapshot.rhs-activity, abs(activity-snapshot.rhs))))
    bounds = np.maximum(0, np.maximum(snapshot.lower-x, x-snapshot.upper))
    return dict(PASS=bool(max(rows.max(initial=0), bounds.max(initial=0)) <= tolerance),
        max_row_violation=float(rows.max(initial=0)), max_bound_violation=float(bounds.max(initial=0)),
        tolerance=tolerance, rows=len(rows), columns=len(x), raw_point_rounded_or_clipped=False)


def exact_local_bound(snapshot, raw_pi):
    # A projected dual is an explicitly separate certificate attempt, never a
    # replacement for persisted solver Pi. Finite native boxes price every
    # residual exactly; changing signs to zero cannot manufacture an optimum.
    pi = np.asarray(raw_pi).copy()
    pi[(snapshot.senses == '<') & (pi > 0)] = 0
    pi[(snapshot.senses == '>') & (pi < 0)] = 0
    result = verify_dual(snapshot, pi, snapshot.objectives[0].name)
    result['raw_dual_preserved'] = True
    result['certificate_sign_projection_count'] = int(np.count_nonzero(pi != raw_pi))
    return result


def phase_objective(master, point):
    n = master.original.matrix.shape[1]
    return sum((w*Fraction(float(x)) for w, x in zip(master.weights, point[n:])), Fraction(0))


def verify_zero(master, point, *, zero_tolerance=Fraction(1, 100000000), scientific_tolerance=1e-6):
    master.verify()
    phi = phase_objective(master, point)
    original = primal_replay(master.original, point[:master.original.matrix.shape[1]], scientific_tolerance)
    return dict(PASS=bool(0 <= phi <= zero_tolerance and original['PASS']),
        replayed_phi=str(phi), certified_zero_tolerance=str(zero_tolerance), original_rows_and_bounds=original,
        artificial_free_original_point=True, exact_arithmetic_zero=phi == 0,
        INTEGER_DOMAIN_CLOSURE_PROVEN=False)


def interval_box_bound(matrix, c, pi, lower, upper, rhs, constant=0.):
    """Conservative IEEE754 interval Lagrangian bound, incl. infinite boxes.

Each sparse dot uses an upward error envelope gamma_(2*k+4), plus a
subnormal allowance. Endpoints and all scalar additions round outward.
This is a safe lower bound, not an assertion of exact native optimality.
"""
    a = matrix.tocsc()
    pi = np.asarray(pi, dtype=float)
    c = np.asarray(c, dtype=float)
    if not all(np.all(np.isfinite(v)) for v in (pi, c, rhs)):
        raise ValueError('FINITE_INTERVAL_CERTIFICATE_REQUIRED')
    eps = np.finfo(float).eps
    total = float(constant)
    for j in range(a.shape[1]):
        lo, hi = a.indptr[j:j+2]
        products = a.data[lo:hi]*pi[a.indices[lo:hi]]
        value = float(np.sum(products))
        k = 2*len(products)+4
        if k*eps >= .5: raise ValueError('INTERVAL_DOT_TOO_LARGE')
        error = np.nextafter(k*eps/(1-k*eps)*float(np.sum(abs(products))) + k*np.nextafter(0., 1.), np.inf)
        rlo = np.nextafter(c[j]-value-error, -np.inf)
        rhi = np.nextafter(c[j]-value+error, np.inf)
        if rlo < 0 and (not math.isfinite(upper[j]) or upper[j] >= 1e100): return None
        if rhi > 0 and (not math.isfinite(lower[j]) or lower[j] <= -1e100): return None
        candidates = [0.] if lower[j] <= 0 <= upper[j] else []
        for r in (rlo, rhi):
            for b in (lower[j], upper[j]):
                if math.isfinite(b) and abs(b) < 1e100:
                    candidates.append(np.nextafter(r*b, -np.inf))
        total = np.nextafter(total+min(candidates), -np.inf)
    # Exact rational dot for RHS is modest on the compact coupling axes.
    rhs_exact = sum((Fraction(float(x))*Fraction(float(y)) for x, y in zip(pi, rhs)), Fraction(0))
    rhs_float = float(rhs_exact)
    if Fraction(rhs_float) > rhs_exact: rhs_float = np.nextafter(rhs_float, -np.inf)
    return float(np.nextafter(total+rhs_float, -np.inf))
