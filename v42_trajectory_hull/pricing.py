"""Full96 integer column search plus a bounded exhaustive region-cover certificate.

The MILP locates physical trajectories. Its best bound is never a certificate.
LP node duals certify a disjoint binary partition of *all* missing trajectories.
An incomplete tree remains a conservative integer-pricing lower bound.
"""
from fractions import Fraction as F
from time import perf_counter
from types import SimpleNamespace
import numpy as np
from v42_m1_hybrid.pricing import build_pricing_model
from v42_m1_hybrid.bound import local_exact_price_bound
from v42_m1_research.check_ub import matrix_replay
from .certificate import endpoints, check_cover
from .budget import write
from .case import file_sha


def signed_packet(model, block, attr='Pi'):
    try:
        raw = np.asarray(model.getAttr(attr), dtype=float)
    except Exception:
        return None
    if raw.shape != (block.A.shape[0],) or not np.isfinite(raw).all():
        return None
    if attr == 'FarkasDual':
        raw = -raw
    bad = ((block.d['sense'] == '<') & (raw > 0)) | ((block.d['sense'] == '>') & (raw < 0))
    if bad.any():
        return None  # Strict rejection; no sign clipping or equality repair.
    return {str(int(i)):str(F(float(raw[i]))) for i in np.flatnonzero(raw)}


def integer_price(block, exact_price, seed_dual, seed_point, budget, folder,
                  *, label, node_limit=7, node_seconds=8., mip_seconds=25.):
    folder.mkdir(parents=True, exist_ok=True)
    q = {int(j):F(v) for j, v in exact_price.items()}
    native = np.array([float(q.get(j, 0)) for j in range(block.A.shape[1])])
    columns = []
    begin = perf_counter()
    model, variables, build = build_pricing_model(block, native, 'MILP', seed_point)
    budget.build_seconds += perf_counter()-begin
    try:
        model.Params.MIPGap = 0.
        record = budget.optimize(model, label+'_INTEGER_COLUMN', mip_seconds)
        if model.SolCount:
            point = np.asarray(variables.X)
            admission = matrix_replay(block.A, block.d, point)
            if admission['PASS'] and admission['integer_pattern_exact'] and admission['exact_binary_0_1']:
                path = folder/'INTEGER_COLUMN.npz'
                np.savez_compressed(path, point=point, original_columns=block.original_columns)
                columns.append(dict(path=str(path), sha256=file_sha(path), admission=admission,
                                    source='FULL96_NATIVE_INTEGER_SEARCH_NUMERICAL_LOCAL_REPLAY'))
        write(folder/'INTEGER_SEARCH.json', dict(native=record, build=build, columns=columns,
                                               Native_ObjBound_certificate_authority=False))
    finally:
        model.dispose()
    tree = {'r':dict(fixes={}, proof=dict(kind='DUAL', dual=seed_dual), split=None)}
    floors = {'r':F(local_exact_price_bound(block, q, seed_dual)['exact_bound'])}
    points = {}
    pending = ['r']
    begin = perf_counter()
    model, variables, build = build_pricing_model(block, native, 'LP')
    budget.build_seconds += perf_counter()-begin
    model.Params.Method = 1
    model.Params.InfUnbdInfo = 1
    binaries = np.flatnonzero(block.d['types'] == 'B')
    calls = 0
    try:
        while pending and calls < node_limit and budget.used < 599:
            key = pending.pop(0)
            lo, hi = endpoints(block, tree[key]['fixes'])
            variables.LB, variables.UB = lo, hi
            budget.optimize(model, label+'_REGION_'+key, node_seconds)
            calls += 1
            if int(model.Status) == 3:
                ray = signed_packet(model, block, 'FarkasDual')
                if ray is not None:
                    from .certificate import node_bound
                    packet = dict(kind='FARKAS', dual=ray)
                    try:
                        node_bound(block, exact_price, tree[key]['fixes'], packet)
                    except ValueError:
                        pass
                    else:
                        tree[key]['proof'] = packet
                        floors.pop(key, None)
                        continue
            dual = signed_packet(model, block)
            if dual is not None:
                data = dict(block.d, lower=lo, upper=hi)
                value = F(local_exact_price_bound(SimpleNamespace(A=block.A, d=data), q, dual)['exact_bound'])
                if value > floors[key]:
                    tree[key]['proof'] = dict(kind='DUAL', dual=dual)
                    floors[key] = value
            try:
                point = np.asarray(variables.X)
            except Exception:
                continue
            points[key] = point
            available = [int(j) for j in binaries if str(int(j)) not in tree[key]['fixes']]
            fractional = [j for j in available if 1e-8 < point[j] < 1-1e-8]
            # Both children are immediately covered by the parent's proof; no lost frontier.
            if fractional and calls+len(pending)+2 <= node_limit:
                j = max(fractional, key=lambda k:min(point[k], 1-point[k]))
                tree[key]['split'] = j
                for bit in (0, 1):
                    child = key+str(bit)
                    fixes = dict(tree[key]['fixes'], **{str(j):bit})
                    tree[child] = dict(fixes=fixes, proof=None, split=None)
                    floors[child] = floors[key]
                    pending.append(child)
                floors.pop(key)
    finally:
        model.dispose()
    beta = check_cover(block, exact_price, tree)
    result = dict(exact_price=exact_price, tree=tree, exact_price_lower_bound=str(beta),
                  missing_trajectory_coverage='PASS', integer_optimum='NOT_PROVEN',
                  pricing_node_calls=calls, columns=columns)
    write(folder/'INTEGER_PRICE_COVER.json', result)
    return result
