"""Node restrictions on existing D-W objects; no production builder or runner."""

from copy import copy
from fractions import Fraction as F
import math
import numpy as np

from v42_dw_root.models import build, Master, hash_column
from v42_dw_root.run import exact_rc
from v42_dw_bound.certificate import global_dual, corrected
from v42_disjunctive.certificate import down


def native_projections(blocks):
    """Location means occupancy of a time-network node at DEPARTURE.

    It is the sum of outgoing stay/travel arcs at (site,t). In transit that
    sum is zero. It does not mean connected-PQ or destination-before-arrival.
    Arc reachability constants absent from the native matrix contribute zero.
    """
    from .state import BinaryProjection
    result = []
    for m, b in enumerate(blocks):
        names = {str(n): j for j, n in enumerate(b.d['names'])}
        for s in b.sites:
            for t in range(96):
                terms = tuple((names[f'arc[{b.unit},{k}]'], 1.) for k, a in enumerate(b.arcs)
                              if a[:2] == (s, t) and f'arc[{b.unit},{k}]' in names)
                if terms:
                    result.append(BinaryProjection('location', m, t, str(s), terms))
        for k, a in enumerate(b.arcs):
            name = f'arc[{b.unit},{k}]'
            if a[-1] is not None and name in names:
                result.append(BinaryProjection('movement', m, a[1], f'{k:09d}', ((names[name], 1.),)))
        # Cover EVERY original binary, including stay arcs and charge modes.
        # Integral location alone does not imply original integer feasibility.
        for j in np.flatnonzero(b.d['types'] == 'B'):
            name = str(b.d['names'][j])
            t = int(name.rsplit(',', 1)[-1][:-1]) if name.startswith('charge_mode[') else b.arcs[int(name.rsplit(',', 1)[-1][:-1])][1]
            result.append(BinaryProjection('original_binary', m, t, name, ((int(j), 1.),)))
    return tuple(result)


def restrict_pricing(block, mess, decisions, guard):
    """Copy ALL original local rows/domain, append only branch equalities."""
    import gurobipy as gp
    guard.check(block.model)  # reject large objects before copy
    proxy = copy(block)
    block.model.update()
    proxy.model = block.model.copy()
    try:
        proxy.vars = proxy.model.getVars()
        for i, d in enumerate(decisions):
            if d.variable.mess == mess:
                proxy.model.addConstr(gp.LinExpr([w for _, w in d.variable.terms],
                                               [proxy.vars[j] for j, _ in d.variable.terms]) == d.value,
                                      name=f'BAP_branch[{i},{d.variable.family}]')
        proxy.model.update()
        guard.check(proxy.model)
        return proxy
    except BaseException:
        proxy.model.dispose()
        raise


def node_master(factory, registry, node):
    """Reuses Master.add. Incompatible columns stay in the global registry."""
    master = factory()
    active, _ = registry.partition(node.column_ids, node.decisions)
    for key in active:
        c = registry.columns[key]
        master.add(c.mess, np.asarray(c.x), np.asarray(c.a), c.c, key)
    return master


def accept_column(original, mess, proxy, x, decisions, pi, alpha, reported_rc, registry, node_id):
    """Physical validation remains the existing full local Block validator."""
    if not original.validate(x, True)['PASS'] or not all(d.compatible(mess, x) for d in decisions):
        raise ValueError('NEW_COLUMN_ORIGINAL_OR_BRANCH_VALIDATION_FAILED')
    rc = exact_rc(proxy, x, pi, alpha)
    if not math.isfinite(reported_rc) or abs(float(rc) - reported_rc) > 1e-8:
        raise ValueError('NEW_COLUMN_REDUCED_COST_MISMATCH')
    a, c, sha = original.column(x)
    _, error = original.exact_coupling(x, a)
    if error > 1e-12 or sha != hash_column(x, a, c):
        raise ValueError('NEW_COLUMN_COUPLING_TRANSPORT_FAILED')
    return registry.add(mess, x, a, c, node_id), float(rc)


def node_bound(global_matrix, global_data, pi, alpha, pricing_bounds):
    """PR143 exact global residual-box theorem, including 1e-8 bound safety.

    The existing corrected implementation is called unchanged for four MESS.
    Tiny one/two-MESS fixtures use its identical algebra over their real units.
    """
    if len(alpha) != len(pricing_bounds) or not all(math.isfinite(float(v)) for v in pricing_bounds):
        raise ValueError('SAME_DUAL_ALL_MESS_BOUNDS_REQUIRED')
    value, proof = global_dual(global_matrix, global_data, pi, global_data['lower'], global_data['upper'])
    if len(alpha) == 4:
        lb, exact, beta, delta = corrected(value, alpha, pricing_bounds)
    else:
        beta = [F(down(F(float(v)) - F(1e-8))) for v in pricing_bounds]
        delta = [min(F(0), b) for b in beta]
        exact = value + sum((F(float(a)) + d for a, d in zip(alpha, delta)), F(0))
        lb = down(exact)
    return lb, dict(PASS=True, global_dual=proof, numerator=str(exact.numerator), denominator=str(exact.denominator),
                    beta_safe=list(map(float, beta)), delta=list(map(float, delta)), rmp_objective_used_as_bound=False)
