"""Exact implications; no solver calls, empirical cuts, or tolerance changes."""
from fractions import Fraction


def rational(value):
    return value if isinstance(value, Fraction) else Fraction(value.item() if hasattr(value, 'item') else value)


def shift_count_bounds(coefficients, rhs, lower, upper, vtypes):
    """For nonnegative a*x<=b, integer x_j<=floor(b/a_j).

    The supplied row must be the independently matched original SHIFT lock.
    All row terms have nonnegative coefficients and nonnegative original lower
    bounds. Continuous lanes remain continuous and receive no integer bound.
    """
    budget = rational(rhs)
    if budget < 0:
        raise ValueError('NONNEGATIVE_SHIFT_BUDGET_REQUIRED')
    coefficients = {int(j): rational(a) for j, a in coefficients.items() if a}
    if any(a < 0 or rational(lower[j]) < 0 for j, a in coefficients.items()):
        raise ValueError('NONNEGATIVE_ORIGINAL_ROW_TERMS_REQUIRED')
    bounds, proofs = {}, []
    for j, coefficient in coefficients.items():
        if vtypes[j] not in ('I', 'B'):
            continue
        implied = budget // coefficient
        if implied < rational(lower[j]):
            # Do not convert this into an infeasibility status or silently
            # accept a wrong row axis. Preserve the original model instead.
            raise ValueError('SHIFT_IMPLICATION_CONFLICTS_WITH_ORIGINAL_LOWER')
        if upper[j] == float('inf') or implied < rational(upper[j]):
            bounds[j] = int(implied)
            proofs.append(dict(column=j, coefficient=str(coefficient), rhs=str(budget),
                upper=int(implied), proof='a_j*x_j <= sum(a*x) <= b; integer x_j'))
    return bounds, proofs


def relocation_window_bound(groups, capacity, shift_budget):
    """Integer resource-window/shift implication over complete start choices.

    Each group supplies *all* legal reference-site starts as (shift, resource)
    and all legal other-site starts. At this resource window, a reference-site
    start either occupies >=g resource or escapes at shift cost >=delta.
    N reference jobs = occupying + escaping + relocating. Thus relocation
    >= N-floor(C/g)-floor(S/delta). Missing domains invalidate the proof.
    """
    C, S = rational(capacity), rational(shift_budget)
    if C < 0 or S < 0 or not groups:
        raise ValueError('NONNEGATIVE_COMPLETE_WINDOW_INPUT_REQUIRED')
    occupying, escaping, population = [], [], 0
    identities = set()
    for group in groups:
        if group['class_id'] in identities or not group.get('complete_domain'):
            raise ValueError('COMPLETE_UNIQUE_CLASS_DOMAIN_REQUIRED')
        identities.add(group['class_id'])
        if type(group['cardinality']) is not int or group['cardinality'] <= 0:
            raise ValueError('ORIGINAL_INTEGER_CLASS_CARDINALITY_REQUIRED')
        population += group['cardinality']
        reference = group['reference_choices']
        remote = group['remote_choices']
        if not reference and not remote:
            raise ValueError('ORIGINAL_JOB_HAS_NO_LEGAL_START')
        for shift, resource in reference:
            shift, resource = rational(shift), rational(resource)
            if shift < 0 or resource < 0:
                raise ValueError('NONNEGATIVE_ORIGINAL_START_COEFFICIENT_REQUIRED')
            if resource:
                occupying.append(resource)
            else:
                escaping.append(shift)
        if any(rational(s) < 0 for s in remote):
            raise ValueError('NONNEGATIVE_REMOTE_SHIFT_REQUIRED')
    occupied_max = int(C // min(occupying)) if occupying else 0
    escaped_max = population if escaping and min(escaping) == 0 else int(S // min(escaping)) if escaping else 0
    lower = max(0, population - occupied_max - escaped_max)
    return dict(PASS=True, lower=lower, population=population,
        occupying_min_resource=str(min(occupying)) if occupying else None,
        escaping_min_shift=str(min(escaping)) if escaping else None,
        occupying_max=occupied_max, escaping_max=escaped_max,
        capacity=str(C), shift_budget=str(S), class_ids=sorted(identities),
        proof='N=occupying+escaping+relocating; integer counts; complete legal choices',
        native_optimization_calls=0)


def cutoff_global_bound(ub, cutoff, subquery_lb, *, complete_domain, objective_integral,
                        subquery_infeasible=False):
    """Combine PRE<=k with its complementary PRE>=k+1 partition."""
    if not complete_domain or not objective_integral:
        raise ValueError('COMPLETE_ORIGINAL_INTEGER_PARTITION_REQUIRED')
    U, k = rational(ub), rational(cutoff)
    if k.denominator != 1 or U.denominator != 1 or U != k + 1:
        raise ValueError('VALIDATED_INTEGER_UB_AND_STRICT_PREDECESSOR_REQUIRED')
    if subquery_infeasible:
        return U
    if subquery_lb is None:
        return None
    L = rational(subquery_lb)
    if L > U:
        raise ValueError('SUBQUERY_BOUND_CONFLICTS_WITH_VALIDATED_UB')
    return min(U, L)


def integer_bound_review(ub, raw_lb):
    """Inherited ceil(LB-1e-6) policy, without changing any native tolerance."""
    import math
    if raw_lb > ub + 1e-5:
        raise ValueError('GLOBAL_BOUND_CONFLICTS_WITH_ORIGINAL_VALIDATED_UB')
    lower=min(ub,math.ceil(raw_lb-1e-6))
    gap=(ub-lower)/max(abs(ub),1e-12)
    return dict(global_LB=lower,global_gap=gap,accepted=gap<=.005,
        exact_integer_optimality=lower==ub)
