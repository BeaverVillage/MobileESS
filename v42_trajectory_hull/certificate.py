"""Independent exact checker of pricing partitions and original grid weak duality.

No native objective, MIP bound, incumbent or master closure flag is evidence.
This module imports neither the pricing tree producer nor its node evaluator.
"""
from fractions import Fraction as F
from time import perf_counter
import numpy as np
from v42_m1_research.check_lb import check_rational_dual_certificate
from v42_m1_hybrid.bound import rational_dual, check_signs


def rounded_down(q):
    value = float(q)
    return float(np.nextafter(value, -np.inf)) if F(value) > q else value


def endpoints(block, fixes):
    lower, upper = block.d['lower'].copy(), block.d['upper'].copy()
    for key, value in fixes.items():
        j = int(key)
        if str(j) != str(key) or not 0 <= j < len(lower) or block.d['types'][j] != 'B':
            raise ValueError('PRICING_SPLIT_NOT_ORIGINAL_BINARY')
        if value not in (0, 1) or not lower[j] <= value <= upper[j]:
            raise ValueError('PRICING_SPLIT_OUTSIDE_ORIGINAL_BOX')
        lower[j] = upper[j] = value
    return lower, upper


def node_bound(block, exact_price, fixes, packet):
    lo, hi = endpoints(block, fixes)
    d = dict(block.d)
    d['objective'] = np.zeros(block.A.shape[1]) if packet['kind'] == 'FARKAS' else np.array(
        [float(F(exact_price.get(str(j), '0'))) for j in range(block.A.shape[1])])
    cert = check_rational_dual_certificate(block.A, d, packet['dual'], lower=lo, upper=hi)
    bound = F(cert['exact_bound'])
    if packet['kind'] == 'FARKAS':
        if bound <= 0:
            raise ValueError('EXACT_INFEASIBILITY_NOT_PROVEN')
        return None  # +infinity, proved empty leaf; never inferred from status.
    if packet['kind'] != 'DUAL':
        raise ValueError('UNKNOWN_PRICING_PROOF_KIND')
    # Native coefficients were rounded for search. Independently correct their error.
    for key, q in exact_price.items():
        j = int(key)
        delta = F(q)-F(float(d['objective'][j]))
        bound += delta*F(float(lo[j] if delta >= 0 else hi[j]))
    return bound


def check_cover(block, exact_price, tree):
    visited = set()

    def visit(key, fixes, inherited=None):
        if key in visited or key not in tree:
            raise ValueError('PRICING_COVER_CYCLE_DUPLICATE_OR_MISSING')
        visited.add(key)
        node = tree[key]
        if node['fixes'] != fixes:
            raise ValueError('PRICING_CHILD_REGION_DRIFT')
        floor = inherited
        if node.get('proof') is not None:
            value = node_bound(block, exact_price, fixes, node['proof'])
            if value is None:
                if node.get('split') is not None:
                    raise ValueError('EMPTY_NODE_HAS_CHILDREN')
                return None
            floor = value if floor is None else max(floor, value)
        if floor is None:
            raise ValueError('UNCERTIFIED_PRICING_REGION')
        if node.get('split') is None:
            return floor
        j = int(node['split'])
        if str(j) in fixes or block.d['types'][j] != 'B' or not (
                block.d['lower'][j] == 0 and block.d['upper'][j] == 1):
            raise ValueError('INVALID_EXHAUSTIVE_BINARY_PARTITION')
        values = []
        for bit in (0, 1):
            child = dict(fixes, **{str(j): bit})
            value = visit(key+str(bit), child, floor)
            if value is not None:
                values.append(value)
        return min(values) if values else None

    value = visit('r', {})
    if visited != set(tree) or value is None:
        raise ValueError('UNCOVERED_EXTRA_REGION_OR_ORIGINAL_DOMAIN_EMPTY')
    return value


def check_global(case, decomp, packet):
    begin = perf_counter()
    if packet['case_sha'] != case.case_sha or set(packet['units']) != set(decomp.units):
        raise ValueError('GLOBAL_PRICING_CASE_OR_UNIT_DRIFT')
    # Rebuild prices directly from original mixed rows; producer prices are not trusted.
    y = rational_dual(packet['coupling_dual'], len(decomp.coupling_rows))
    check_signs(y, case.d['sense'][decomp.coupling_rows])
    q = {int(j):F(float(v)) for j, v in enumerate(case.d['objective']) if v}
    total = F(float(case.d['constant']))
    for k, value in y.items():
        i = int(decomp.coupling_rows[k])
        total += value*F(float(case.d['rhs'][i]))
        a, b = case.A.indptr[i:i+2]
        for j, coefficient in zip(case.A.indices[a:b], case.A.data[a:b]):
            q[int(j)] = q.get(int(j), F(0))-value*F(float(coefficient))
    unit_bounds = {}
    for unit, block in decomp.units.items():
        price = {str(k):str(q[int(j)]) for k, j in enumerate(block.original_columns)
                 if q.get(int(j), F(0))}
        if price != packet['units'][unit]['exact_price']:
            raise ValueError('ORIGINAL_UNROUNDED_PRICE_DRIFT')
        beta = check_cover(block, price, packet['units'][unit]['tree'])
        unit_bounds[unit] = str(beta)
        total += beta
    block = decomp.nonunit_block
    lo, hi = case.lower[block.original_columns], case.upper[block.original_columns]
    d = dict(block.d, lower=lo, upper=hi)
    # A proved envelope is used only by certification, never by native models.
    from types import SimpleNamespace
    nonunit = SimpleNamespace(A=block.A, d=d)
    price = {str(k):str(q[int(j)]) for k, j in enumerate(block.original_columns)
             if q.get(int(j), F(0))}
    total += node_bound(nonunit, price, {}, dict(kind='DUAL', dual=packet['nonunit_dual']))
    return dict(PASS=True, exact_bound=str(total), independently_certified_LB=rounded_down(total),
                exact_integer_price_bounds=unit_bounds, native_MIP_bound_used=False,
                restricted_master_objective_used=False, full_original_integer_domain_preserved=True,
                theorem='SIGNED_ORIGINAL_COUPLING_PLUS_NONUNIT_DUAL_PLUS_EXHAUSTIVE_INTEGER_PRICING_COVERS',
                independent_certificate_seconds=perf_counter()-begin)
