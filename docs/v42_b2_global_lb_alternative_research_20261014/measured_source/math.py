"""Exact stored-binary64 algebra. Solver bounds are a separate trust layer."""
from collections import defaultdict
from fractions import Fraction as F
import hashlib
import json
import math

import numpy as np


def require(ok, why):
    if not ok:
        raise ValueError(why)


def directed(q, upper=False):
    q = F(q)
    v = float(q)
    require(math.isfinite(v), 'NONFINITE_EXACT_BOUND')
    if (F(v) < q) if upper else (F(v) > q):
        v = float(np.nextafter(v, np.inf if upper else -np.inf))
    return v


def signature(packet):
    return hashlib.sha256(json.dumps(packet, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def weight_packet(weights, mu):
    w = {str(k): str(F(v)) for k, v in weights.items() if F(v)}
    u = {str(k): str(F(v)) for k, v in mu.items() if F(v)}
    require(w and all(F(v) >= 0 for v in w.values()) and sum(map(F, w.values())) == 1,
            'EPIGRAPH_SIMPLEX_REQUIRED')
    require(all(0 <= F(v) <= 100 for v in u.values()), 'INVALID_COUPLING_MULTIPLIER')
    p = dict(weights=w, mu=u)
    return dict(**p, sha256=signature(p))


def normalize(values):
    values = {int(k): F(v) for k, v in values.items() if F(v)}
    require(values and all(v >= 0 for v in values.values()), 'NEGATIVE_WEIGHT')
    total = sum(values.values())
    return {k: v / total for k, v in values.items()}


def stabilized_step(weights, gradient, mu, mu_gradient, iteration, radius=.15):
    """Projected supergradient ascent. Caller labels approximate oracle points.

    Rounded proposed weights are exactly renormalized before certification.
    Trust radius bounds displacement from the current center, not from origin.
    """
    keys = sorted(set(weights) | set(gradient))
    center = np.array([float(weights.get(k, 0)) for k in keys])
    g = np.array([float(gradient.get(k, 0)) for k in keys])
    require(np.isfinite(g).all(), 'NONFINITE_GRADIENT')
    g -= g.mean()
    step = radius / math.sqrt(iteration + 1)
    trial = center + step * g / max(float(np.linalg.norm(g)), 1e-30)
    order = np.sort(trial)[::-1]
    sums = np.cumsum(order)
    active = np.flatnonzero(order - (sums - 1) / np.arange(1, len(keys) + 1) > 0)
    theta = (sums[active[-1]] - 1) / (active[-1] + 1)
    trial = np.maximum(trial - theta, 0)
    delta = trial - center
    trial = center + delta * min(1., radius / max(float(np.linalg.norm(delta)), 1e-30))
    w = normalize({k: F(float(v)) for k, v in zip(keys, trial) if v > 0})
    # Coupling rows have heterogeneous scales. The normalized update is only a
    # candidate generator; exact nonnegative multipliers certify each evaluation.
    u = {}
    for k in sorted(set(mu) | set(mu_gradient)):
        old = float(mu.get(k, 0))
        value = min(100., max(0., old + step * float(mu_gradient.get(k, 0))))
        if value:
            u[k] = F(value)
    return w, u


def objective(rows, weights, mu):
    packet = weight_packet(weights, mu)
    constant = F(0)
    terms = defaultdict(F)
    for k, v in list(packet['weights'].items()) + list(packet['mu'].items()):
        row, multiplier = rows[int(k)], F(v)
        constant += multiplier * F(row['constant'])
        for j, a in row['terms'].items():
            terms[int(j)] += multiplier * F(a)
    return constant, {j: a for j, a in terms.items() if a}


def rounding_error(exact, native, lower, upper, maximize=False):
    """min/max (exact-native)'x over ORIGINAL finite box."""
    require(len(native) == len(lower) == len(upper), 'BOX_AXIS_DRIFT')
    require(np.isfinite(lower).all() and np.isfinite(upper).all(), 'UNPROVEN_FINITE_BOX')
    answer = F(0)
    for j in set(exact) | set(map(int, np.flatnonzero(native))):
        delta = F(exact.get(j, 0)) - F(float(native[j]))
        lo, hi = delta * F(float(lower[j])), delta * F(float(upper[j]))
        answer += max(lo, hi) if maximize else min(lo, hi)
    return answer


def dot(terms, point):
    return sum((F(a) * F(float(point[int(j)])) for j, a in terms.items()), F(0))


def exact_dual(A, objective, rhs, senses, lower, upper, pi, constant=0):
    """For min: pi<=0 on <=, pi>=0 on >=, equality pi free.

    L=ObjCon+pi'b+min_box (c-A'pi)'x. Wrong signs are rejected.
    """
    require(len(pi) == A.shape[0] and np.isfinite(pi).all(), 'DUAL_AXIS_OR_NONFINITE')
    require(np.isfinite(lower).all() and np.isfinite(upper).all(), 'UNPROVEN_FINITE_BOX')
    residual = {int(j): F(float(objective[j])) for j in np.flatnonzero(objective)}
    row_sum = F(float(constant))
    for i, v in enumerate(pi):
        require(senses[i] in ('<', '>', '='), 'UNKNOWN_SENSE')
        require(not (senses[i] == '<' and v > 0 or senses[i] == '>' and v < 0), 'WRONG_DUAL_SIGN')
        if not v:
            continue
        p = F(float(v))
        row_sum += p * F(float(rhs[i]))
        begin, end = A.indptr[i:i+2]
        for j, a in zip(A.indices[begin:end], A.data[begin:end]):
            j = int(j)
            residual[j] = residual.get(j, F(0)) - p * F(float(a))
    box = sum((min(v * F(float(lower[j])), v * F(float(upper[j])))
               for j, v in residual.items()), F(0))
    return row_sum + box, dict(row_term=str(row_sum), box_term=str(box),
                              residual_max=str(max(map(abs, residual.values()), default=F(0))),
                              residual_nonzero=sum(bool(v) for v in residual.values()))


def transport_cut(terms, rhs, mapping, lower, upper):
    """Original exact support -> compact native <= row with outward RHS."""
    r, offset, compact = mapping.row(F(rhs), F(0), {int(j): F(a) for j, a in terms.items()})
    native = {int(j): float(v) for j, v in compact.items()}
    # native-exact must be bounded above, the reverse of objective transport.
    error = F(0)
    for j, v in compact.items():
        require(math.isfinite(float(lower[j])) and math.isfinite(float(upper[j])), 'CUT_UNPROVEN_BOX')
        delta = F(native[j]) - v
        error += max(delta * F(float(lower[j])), delta * F(float(upper[j])))
    native_rhs = directed(r + error, upper=True)
    return dict(original_terms={str(j): str(a) for j, a in terms.items()}, original_rhs=str(rhs),
                compact_terms={str(j): str(a) for j, a in compact.items()}, alias_offset=str(offset),
                compact_rhs=str(r), coefficient_error_upper=str(error), native_rhs=native_rhs,
                native_terms={str(j): v for j, v in native.items()})


def binding(stage, source_sha, case_sha, matrix_sha, domain_sha, objective_sha, anchor_sha):
    require(stage in ('B2', 'M1', 'M2'), 'UNKNOWN_STAGE')
    values = (source_sha, case_sha, matrix_sha, domain_sha, objective_sha, anchor_sha)
    require(all(isinstance(v, str) and len(v) == 64 for v in values), 'INCOMPLETE_STAGE_BINDING')
    return dict(stage=stage, source_sha=source_sha, case_sha=case_sha, matrix_sha=matrix_sha,
                domain_sha=domain_sha, objective_sha=objective_sha, anchor_sha=anchor_sha)


def combine(records, expected, ub):
    require(ub['binding'] == expected and ub['PASS'], 'CURRENT_FULL_UB_REQUIRED')
    admitted = []
    for record in records:
        if record.get('PASS'):
            require(record['binding'] == expected, 'FOREIGN_BOUND_BINDING')
            require(F(record['exact_LB']) <= F(ub['exact_UB']), 'LB_ABOVE_UB_FAIL_CLOSED')
            admitted.append(record)
    require(admitted, 'NO_CERTIFIED_BOUND')
    best = max(admitted, key=lambda x: F(x['exact_LB']))
    return dict(best=best['algorithm'], exact_LB=best['exact_LB'], LB=directed(F(best['exact_LB'])),
                gap_percent=100 * float((F(ub['exact_UB']) - F(best['exact_LB'])) / F(ub['exact_UB'])),
                binding=expected, admitted=[r['algorithm'] for r in admitted])
