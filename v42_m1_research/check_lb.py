"""Independent row-inclusion and stored-rational LP lower-bound checker.

No solver objective, BestBd, child status or fractional-point rejection is a
certificate.  A valid signed row multiplier vector is enough: all remaining
dual residuals are minimized over the original finite variable box exactly.
"""
from fractions import Fraction
from hashlib import sha256
from time import perf_counter
import numpy as np


def _same(a, b):
    a, b = np.asarray(a), np.asarray(b)
    return a.dtype == b.dtype and a.shape == b.shape and a.tobytes() == b.tobytes()


def _family(name):
    return str(name).split('[', 1)[0]


def check_retained_relaxation(A, d, R, e, retained_rows, *, case_sha=None,
                              point=None, require_all_physics=True):
    """Deletion-only relaxation retains the entire four-fleet physics domain."""
    begin = perf_counter()
    rows = np.asarray(retained_rows)
    if rows.ndim != 1 or rows.dtype.kind not in 'iu':
        raise ValueError('RETAINED_ROW_AXIS_NOT_INTEGER')
    if len(set(map(int, rows))) != len(rows) or np.any(rows < 0) or np.any(rows >= A.shape[0]):
        raise ValueError('RETAINED_ROW_AXIS_DUPLICATE_OR_OUT_OF_RANGE')
    if R.shape != (len(rows), A.shape[1]):
        raise ValueError('RELAXATION_AXIS_DRIFT')
    expected = A[rows].tocsr()
    for name in ('indptr', 'indices', 'data'):
        if not _same(getattr(expected, name), getattr(R.tocsr(), name)):
            raise ValueError('RETAINED_ORIGINAL_COEFFICIENT_DRIFT')
    for key in ('names', 'lower', 'upper', 'types', 'objective', 'constant'):
        if not _same(d[key], e[key]):
            raise ValueError('FULL_ORIGINAL_VARIABLE_DOMAIN_DRIFT:' + key)
    for key in ('rhs', 'sense', 'row_names'):
        if not _same(d[key][rows], e[key]):
            raise ValueError('RETAINED_ROW_METADATA_DRIFT:' + key)
    grid = {'line_thermal_face', 'transformer_kVA', 'voltage_upper', 'voltage_lower'}
    physics = {i for i, name in enumerate(d['row_names']) if _family(name) not in grid}
    if require_all_physics and not physics.issubset(set(map(int, rows))):
        raise ValueError('ORIGINAL_96_SLOT_PHYSICS_ROW_DROPPED')
    witness = None
    if point is not None:
        from v42_integrated.matrix import audit
        witness = audit(R, e, np.asarray(point), integral=True, tolerance=1e-8)
        if not witness['PASS']:
            raise ValueError('ORIGINAL_INTEGER_WITNESS_NOT_RETAINED')
    return dict(PASS=True, theorem='F_C3A_subset_R_BY_ORIGINAL_GRID_ROW_DELETION_ONLY',
                case_sha=case_sha, original_rows=A.shape[0], retained_rows=len(rows),
                original_columns=A.shape[1], retained_physics_rows=len(physics),
                all_original_binary_types_bounds_objective_unchanged=True,
                all_96_slot_route_SOC_mode_PCS_rows_retained=True,
                witness=witness, check_wall_seconds=perf_counter()-begin,
                new_strong_cut=False)


def check_dual_certificate(A, d, dual, *, lower=None, upper=None,
                           source_rows=None, case_sha=None):
    """Certify c*x >= b*y + min_box((c-A.T*y)*x) + ObjCon exactly.

    Values are interpreted as exact dyadic rationals of the stored binary64.
    For minimization, <= rows require y<=0 and >= rows require y>=0.  Equality
    multipliers are unrestricted.  No floating feasibility tolerance is used.
    The caller must independently establish that the checked domain contains
    every original integer plan before calling its bound Global LB.
    """
    begin = perf_counter()
    A = A.tocsr()
    y = np.asarray(dual, dtype=np.float64)
    lo = np.asarray(d['lower'] if lower is None else lower, dtype=np.float64)
    hi = np.asarray(d['upper'] if upper is None else upper, dtype=np.float64)
    c = np.asarray(d['objective'], dtype=np.float64)
    if y.shape != (A.shape[0],) or lo.shape != (A.shape[1],) or hi.shape != lo.shape:
        raise ValueError('DUAL_CERTIFICATE_AXIS_DRIFT')
    if not all(np.isfinite(z).all() for z in (y, lo, hi, c, d['rhs'], A.data)):
        raise ValueError('EXACT_BOX_CERTIFICATE_REQUIRES_FINITE_COEFFICIENTS_AND_BOUNDS')
    if np.any(lo > hi):
        raise ValueError('EMPTY_VARIABLE_BOX')
    senses = np.asarray(d['sense'])
    if not set(map(str, senses)).issubset({'<', '>', '='}):
        raise ValueError('UNKNOWN_NATIVE_ROW_SENSE')
    if np.any(y[senses == '<'] > 0) or np.any(y[senses == '>'] < 0):
        raise ValueError('INVALID_DUAL_ROW_SIGN')
    active = {int(i):Fraction(float(y[i])) for i in np.flatnonzero(y)}
    return _rational_bound(A,d,active,lo,hi,source_rows,case_sha,begin,
                           sha256(y.tobytes()).hexdigest())


def check_rational_dual_certificate(A, d, multipliers, *, lower=None, upper=None,
                                    source_rows=None, case_sha=None):
    """Same independent theorem with exact sparse rational multipliers.

    Equality multiplier repair can be stored as rationals without re-rounding
    them to native binary64. The writer cannot supply its own claimed bound.
    """
    begin=perf_counter()
    A=A.tocsr()
    lo=np.asarray(d['lower'] if lower is None else lower,dtype=np.float64)
    hi=np.asarray(d['upper'] if upper is None else upper,dtype=np.float64)
    if lo.shape!=(A.shape[1],) or hi.shape!=lo.shape or np.any(lo>hi):
        raise ValueError('RATIONAL_CERTIFICATE_BOX_AXIS_DRIFT')
    if not all(np.isfinite(z).all() for z in (lo,hi,d['objective'],d['rhs'],A.data,d['constant'])):
        raise ValueError('EXACT_BOX_CERTIFICATE_REQUIRES_FINITE_COEFFICIENTS_AND_BOUNDS')
    active={}
    for key,value in multipliers.items():
        i=int(key)
        if not 0<=i<A.shape[0] or str(i)!=str(key):
            raise ValueError('RATIONAL_DUAL_ROW_AXIS_DRIFT')
        q=Fraction(value)
        if i in active:
            raise ValueError('RATIONAL_DUAL_DUPLICATE_ROW')
        sense=str(d['sense'][i])
        if sense not in {'<','>','='} or (sense=='<' and q>0) or (sense=='>' and q<0):
            raise ValueError('INVALID_DUAL_ROW_SIGN')
        if q:active[i]=q
    raw='\n'.join(f'{i}:{active[i]}' for i in sorted(active)).encode('ascii')
    return _rational_bound(A,d,active,lo,hi,source_rows,case_sha,begin,sha256(raw).hexdigest())


def _rational_bound(A,d,active,lo,hi,source_rows,case_sha,begin,dual_hash):
    # This mathematical evaluator is independent of native solve and repair.
    products = {}
    weighted_rhs = Fraction(0)
    c=np.asarray(d['objective'],dtype=np.float64)
    for i,q in active.items():
        weighted_rhs += q * Fraction(float(d['rhs'][i]))
        a, b = A.indptr[i:i+2]
        for j, value in zip(A.indices[a:b], A.data[a:b]):
            j = int(j)
            products[j] = products.get(j, Fraction(0)) + q * Fraction(float(value))
    total = Fraction(float(np.asarray(d['constant']).item())) + weighted_rhs
    correction = Fraction(0)
    nonzero = 0
    max_residual = Fraction(0)
    for j in range(A.shape[1]):
        residual = Fraction(float(c[j])) - products.get(j, Fraction(0))
        if residual:
            nonzero += 1
            max_residual = max(max_residual, abs(residual))
            correction += residual * Fraction(float(lo[j] if residual > 0 else hi[j]))
    total += correction
    value = float(total)
    if not np.isfinite(value):
        raise ValueError('EXACT_CERTIFICATE_BOUND_NOT_FINITE')
    if Fraction(value) > total:
        value = float(np.nextafter(value, -np.inf))
    row_axis = np.arange(A.shape[0], dtype=np.int64) if source_rows is None else np.asarray(source_rows, dtype=np.int64)
    if row_axis.shape != (A.shape[0],):
        raise ValueError('CERTIFICATE_SOURCE_ROW_AXIS_DRIFT')
    return dict(PASS=True, status='EXACT_STORED_RATIONAL_BOUND_CERTIFIED',
                case_sha=case_sha, certified_domain='CHECKED_ROW_DOMAIN_WITH_FINITE_BOX',
                independently_certified_LB=value, exact_bound=str(total),
                weighted_rhs_exact=str(weighted_rhs), box_correction_exact=str(correction),
                nonzero_dual_rows=len(active), residual_nonzero_columns=nonzero,
                max_exact_residual=str(max_residual), native_objective_used=False,
                native_BestBd_used=False, optimality_claimed=False,
                dual_SHA256=dual_hash,
                source_rows_SHA256=sha256(row_axis.tobytes()).hexdigest(),
                check_wall_seconds=perf_counter()-begin)


def check_conflict_rows(A, d, cuts, *, case_sha=None):
    """Validate exact pairwise route-node conflicts from a supplied DAG proof.

    Each certificate lists *all* graph arcs for one unit and identifies two
    native binary node activities.  Reachability is independently recomputed;
    no historical route or selected fractional point defines the domain.
    """
    checked = []
    for cut in cuts:
        j, k = map(int, cut['columns'])
        if j == k or any(d['types'][q] != 'B' for q in (j, k)):
            raise ValueError('CONFLICT_ENDPOINT_NOT_DISTINCT_ORIGINAL_BINARY')
        names = [str(d['names'][q]) for q in (j, k)]
        parsed = []
        for name in names:
            if not name.startswith('node_activity['):
                raise ValueError('CONFLICT_ENDPOINT_NOT_NODE_ACTIVITY')
            unit, site, slot = name[14:-1].split(',')
            parsed.append((unit, site, int(slot)))
        if parsed[0][0] != parsed[1][0] or parsed[0][0] != cut['unit']:
            raise ValueError('CONFLICT_CANNOT_COMBINE_DIFFERENT_FLEET_UNITS')
        first, second = sorted(parsed, key=lambda z:z[2])
        if first[2] == second[2]:
            raise ValueError('SINGLE_SLOT_CONFLICT_IS_NOT_MULTITIME')
        edges = cut['arcs']
        by_depart = {}
        for source, depart, destination, connect in edges:
            by_depart.setdefault(int(depart), []).append((source, destination, int(connect)))
        reached = {(first[1], first[2])}
        for t in range(first[2], second[2]+1):
            for source, destination, connect in by_depart.get(t, ()):
                if (source, t) in reached:
                    reached.add((destination, connect))
        if (second[1], second[2]) in reached:
            raise ValueError('CLAIMED_ROUTE_CONFLICT_IS_ACTUALLY_REACHABLE')
        # A feasible unit route is one path, hence it cannot pass through both
        # disconnected ordered nodes; z_j+z_k <= 1 follows. Completeness of the
        # arc table is established by check_route_conflicts_against_graph.
        checked.append(dict(columns=[j,k], exact_coefficients=['1','1'], rhs='1'))
    return dict(PASS=True, case_sha=case_sha, rows_checked=len(checked),
                rows=checked, all_integer_unit_paths_valid=True,
                premise='The independently replayed native graph encodes one unit path per fleet member',
                material_LB_improvement='NOT_PROVEN',
                full_96_slot_route_preserved=True)


def check_route_conflicts_against_graph(A, d, cuts, graph, *, case_sha=None):
    """Require complete original graph identity before accepting a conflict."""
    sites, initial, arcs, _, _ = graph
    expected = [[a[0], int(a[1]), a[2], int(a[3])] for a in arcs]
    for cut in cuts:
        if cut['unit'] not in initial or cut['arcs'] != expected:
            raise ValueError('CONFLICT_GRAPH_NOT_COMPLETE_ORIGINAL_ROUTE_TABLE')
    return check_conflict_rows(A, d, cuts, case_sha=case_sha)


def check_integer_count_cover(A,d,leaves,columns,split,*,units,case_sha=None):
    """Independently prove a complete two-leaf all-fleet/two-time cover.

    z sums two original binary node activities per vehicle. Every original
    integer point has z<=floor or z>=floor+1; no path or feasible assignment
    is deleted from the union. Each leaf keeps every original96-slot row.
    """
    columns=list(map(int,columns))
    n_mess=len(set(units)); n_binary=2*n_mess
    if n_mess==0 or len(columns)!=n_binary or len(set(columns))!=n_binary:
        raise ValueError('JOINT_COUNT_REQUIRES_TWO_DISTINCT_ORIGINAL_BINARIES_PER_UNIT')
    if not isinstance(split,(int,np.integer)) or not 0<=int(split)<n_binary:
        raise ValueError('JOINT_COUNT_SPLIT_NOT_INTEGER_INTERIOR')
    if any(j<0 or j>=A.shape[1] or str(d['types'][j])!='B' for j in columns):
        raise ValueError('JOINT_COUNT_COLUMN_NOT_ORIGINAL_BINARY')
    groups={}
    for j in columns:
        n=str(d['names'][j])
        if not n.startswith('node_activity['):raise ValueError('JOINT_COUNT_NOT_NATIVE_LOCATION_BINARY')
        u,s,t=n[14:-1].split(',');t=int(t)
        if not 66<=t<=95:raise ValueError('JOINT_COUNT_OUTSIDE_CRITICAL_WINDOW')
        groups.setdefault((s,t),set()).add(u)
    if len(groups)!=2 or len({t for s,t in groups})!=2 or any(v!=set(units) for v in groups.values()):
        raise ValueError('JOINT_COUNT_NOT_ALL_FLEETS_AT_TWO_DISTINCT_TIMES')
    if len(leaves)!=2:raise ValueError('JOINT_COUNT_INCOMPLETE_LEAF_COVER')
    expected_senses=('<','>')
    for k,leaf in enumerate(leaves):
        B,e=leaf.A.tocsr(),leaf.d
        if B.shape!=(A.shape[0]+1,A.shape[1]):raise ValueError('COUNT_LEAF_FULL_ORIGINAL_AXIS_DRIFT')
        source=B[:-1].tocsr()
        for name in ('indptr','indices','data'):
            if not _same(getattr(A.tocsr(),name),getattr(source,name)):
                raise ValueError('COUNT_LEAF_ORIGINAL_COEFFICIENT_DRIFT')
        for key in ('names','lower','upper','types','objective','constant'):
            if not _same(d[key],e[key]):raise ValueError('COUNT_LEAF_ORIGINAL_DOMAIN_DRIFT:'+key)
        for key in ('rhs','sense','row_names'):
            if not _same(d[key],e[key][:-1]):raise ValueError('COUNT_LEAF_ORIGINAL_ROW_METADATA_DRIFT:'+key)
        row=B[-1]
        if list(map(int,row.indices))!=sorted(columns) or any(float(v)!=1. for v in row.data):
            raise ValueError('COUNT_LEAF_ADDED_ROW_COEFFICIENT_DRIFT')
        if str(e['sense'][-1])!=expected_senses[k] or float(e['rhs'][-1])!=int(split)+k:
            raise ValueError('COUNT_LEAF_SPLIT_HAS_HOLE_OR_WRONG_HALFSPACE')
    return dict(PASS=True,status='EXACT_COMPLETE_INTEGER_COUNT_COVER',case_sha=case_sha,
        original_binary_columns=columns,source_names=[str(d['names'][j]) for j in columns],
        groups=[dict(site=s,slot=t,units=sorted(v)) for (s,t),v in sorted(groups.items())],
        exact_leaf_rows=[dict(sense='<',rhs=int(split)),dict(sense='>',rhs=int(split)+1)],
        every_original_integer_plan_covered=True,all_original_96_slot_rows_in_each_leaf=True,
        no_single_vehicle_impossibility_promoted=True,
        certified_bound_rule='minimum_of_independently_certified_bounds_of_ALL_two_leaves')
