"""User-approved 3% B1/B3 P1/P2 gaps; no physical tolerance changes."""
import math
from gurobipy import GRB

RELATIVE_GAP = .03
GAP_POLICIES = ('B1', 'B3')
BOUNDED_STAGES = (
    'PRIMARY_MIN_RHO',
    'V41_SECONDARY_MIN_MEAN_H4_SHORTFALL',
    'rho_max',
    'V41_mean_H4_shortfall_GPUh',
)


def apply_gap(model, label, *, revision, policy):
    if policy not in ('B0', 'B1', 'B2', 'B3'):
        raise ValueError('UNKNOWN_GAP_POLICY:' + str(policy))
    base = label.removesuffix('_NUMERICAL_CAP_RECHECK')
    # A numerical cap retry can recurse more than once.
    while base.endswith('_NUMERICAL_CAP_RECHECK'):
        base = base.removesuffix('_NUMERICAL_CAP_RECHECK')
    model.Params.MIPGap = RELATIVE_GAP if revision and policy in GAP_POLICIES and base in BOUNDED_STAGES else 0.
    model.Params.MIPGapAbs = 0.


def certificate(model):
    gap = float(model.MIPGap) if model.IsMIP and model.SolCount else None
    if gap is not None and not math.isfinite(gap):
        gap = None
    accepted = model.Status == GRB.OPTIMAL
    exact = accepted and (not model.IsMIP or gap == 0.)
    tolerance = float(model.Params.MIPGap)
    if accepted and model.IsMIP and (gap is None or gap > tolerance + 1e-12):
        raise RuntimeError('SOLVER_GAP_CERTIFICATE_OUTSIDE_REGISTERED_LIMIT')
    return dict(requested_relative_gap=tolerance, requested_absolute_gap=float(model.Params.MIPGapAbs),
        achieved_relative_gap=gap, accepted_within_registered_gap=accepted,
        exact_optimum_certified=exact,
        optimality_certificate=('EXACT_WITHIN_SOLVER_TOLERANCES' if exact else
            'WITHIN_REGISTERED_RELATIVE_GAP' if accepted else 'NOT_ACCEPTED'))
