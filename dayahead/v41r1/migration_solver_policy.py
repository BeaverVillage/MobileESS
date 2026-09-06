"""User-approved 0.1% gaps for V41R1 P1/P2; no physical tolerance changes."""
import math
from gurobipy import GRB

RELATIVE_GAP = .001
BOUNDED_STAGES = ('PRIMARY_MIN_RHO', 'V41_SECONDARY_MIN_MEAN_H4_SHORTFALL')


def apply_gap(model, label, *, revision):
    base = label.removesuffix('_NUMERICAL_CAP_RECHECK')
    # A numerical cap retry can recurse more than once.
    while base.endswith('_NUMERICAL_CAP_RECHECK'):
        base = base.removesuffix('_NUMERICAL_CAP_RECHECK')
    model.Params.MIPGap = RELATIVE_GAP if revision and base in BOUNDED_STAGES else 0.
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
