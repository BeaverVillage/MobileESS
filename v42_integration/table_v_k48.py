"""Source-parameterized representation of the original K16 -> K32 -> K48 LB.

The physical coordinates are the literal original FULL coordinates. Thus no
historical Compact alias census, case, incumbent, or lower bound is imported.
The original row selector and independent symbolic verifier are reused. This
module never changes the UB engine or blocks a feasible physical handoff when
the numerical global-bound target is missed.
"""
from copy import deepcopy
from fractions import Fraction as F
import gc
import math
from pathlib import Path
from time import perf_counter

import numpy as np
from scipy import sparse

from .a_engine import digest
from .m_engine import _write, file_record, vector_sha
from .table_v_gap_contract import MESS_GLOBAL_GAP_TARGET
from .table_v_dates import require_day
from v42_m1_hybrid.blocks import matrix_sha
from v42_may_campaign_native90.m_model import _domain_sha
from tools.critical_grid_cg import oracle as original_oracle
from tools.critical_grid_cg import verify as independent


PHYSICAL = frozenset(('arc', 'charge_mode', 'SOC', 'Pch', 'Pdis', 'Q', 'node_activity'))
FAMILIES = tuple(original_oracle.FAMILIES)
QUOTAS = dict(original_oracle.QUOTAS)
ORIGINAL_NATIVE_PARAMETERS = dict(Threads=1, MIPGap=.03, MIPFocus=3,
    FeasibilityTol=1e-8, IntFeasTol=1e-8, OptimalityTol=1e-8, Seed=42)
ORIGINAL_CALL_CAP = {16: 90., 32: 180., 48: 180.}
NATIVE_COEFFICIENT_FLOOR = 2.**-39


def require(value, reason):
    if not value:
        raise ValueError(reason)


def family(name):
    return str(name).split('[', 1)[0]


def identity(case):
    """Bind actual numeric source bytes, not manually supplied SHA strings."""
    require(digest(case.identity) == case.case_sha, 'K48_CURRENT_STAGE_CASE_IDENTITY_DRIFT')
    day = require_day(case.identity['day'])
    require(case.bundle['day'] == day, 'K48_CURRENT_DATE_NATIVE_SOURCE_DRIFT')
    A, d = case.original_A, case.original_d
    actual = dict(matrix_sha=matrix_sha(A), domain_sha=_domain_sha(d))
    require(actual['matrix_sha'] == case.identity['original_matrix_sha'], 'K48_CURRENT_FULL_MATRIX_DRIFT')
    require(actual['domain_sha'] == case.identity['original_domain_sha'], 'K48_CURRENT_FULL_DOMAIN_DRIFT')
    return dict(day=day, stage_case_sha=case.case_sha, source_sha=case.identity['D0_source_sha'],
        parent_case_sha=case.identity['D0_parent_case_sha'], arm=case.identity['arm'],
        stage=case.identity['stage'], aidc_anchor=case.identity['aidc_anchor'], **actual)


def replay(A, d, x, *, integer=True):
    x = np.asarray(x)
    require(x.dtype == np.dtype('float64') and x.shape == (A.shape[1],)
            and np.isfinite(x).all(), 'K48_LITERAL_POINT_AXIS_OR_FINITE_DRIFT')
    residual = np.asarray(A @ x).ravel() - d['rhs']
    violation = np.where(d['sense'] == '=', abs(residual),
                         np.where(d['sense'] == '<', residual, -residual))
    maximum = max(0., float(violation.max(initial=0)),
        float(np.max(d['lower'] - x, initial=0)), float(np.max(x - d['upper'], initial=0)))
    discrete = x[d['types'] != 'C']
    literal = bool(np.all(discrete == np.rint(discrete))
        and np.isin(x[d['types'] == 'B'], (0., 1.)).all())
    return dict(PASS=maximum <= 1e-6 and (literal or not integer), maximum_violation=maximum,
        raw_integer_pattern_exact=literal, point_sha=vector_sha(x),
        objective=float(np.dot(d['objective'], x) + float(d['constant'])))


def physical_axes(A, d):
    physical = np.array([family(n) in PHYSICAL for n in d['names']], dtype=bool)
    rho_ids = np.flatnonzero(np.asarray(d['names']) == 'rho_max')
    require(len(rho_ids) == 1, 'K48_RHO_AXIS')
    rho = int(rho_ids[0])
    require(d['objective'][rho] == 1 and np.count_nonzero(d['objective']) == 1
            and float(d['constant']) == 0 and d['types'][rho] == 'C', 'K48_ORIGINAL_P1_OBJECTIVE')
    # A physical-only row has every nonzero supported on a physical variable.
    counts = np.diff(A.indptr)
    occupied = np.flatnonzero(counts)
    nonphysical = np.zeros(A.shape[0], dtype=np.int8)
    nonphysical[occupied] = np.maximum.reduceat((~physical[A.indices]).astype(np.int8), A.indptr[occupied])
    rows = np.flatnonzero((counts > 0) & (nonphysical == 0)).astype(np.int64)
    cols = np.r_[np.flatnonzero(physical), rho].astype(np.int64)
    require(len(set(map(int, cols))) == len(cols), 'K48_DUPLICATE_PHYSICAL_COORDINATE')
    require(np.isfinite(d['lower'][cols]).all() and np.isfinite(d['upper'][cols]).all(),
            'K48_FINITE_ORIGINAL_PHYSICAL_BOX_REQUIRED')
    return rows, cols


def exact_cut(A, d, row, columns, geometry=None):
    """Original exact helper elimination and original outward-box rounding."""
    geometry = geometry or original_oracle.Geometry(A, d)
    terms, rhs, constant, dependencies = geometry.project(int(row))
    require(all(family(d['names'][j]) in {'Pch', 'Pdis', 'Q'}
                or str(d['names'][j]) == 'rho_max' for j in terms), 'K48_RESIDUAL_NONPQ_COORDINATE')
    inverse = {int(j): k for k, j in enumerate(columns)}
    require(set(terms) <= set(inverse), 'K48_PROJECTED_COLUMN_OUTSIDE_PHYSICAL_DOMAIN')
    local = {inverse[j]: coefficient for j, coefficient in terms.items()}
    error, values = F(0), {}
    for j, coefficient in local.items():
        native = float(coefficient)
        require(math.isfinite(native) and native != 0, 'K48_COEFFICIENT_OVERFLOW_OR_UNDERFLOW')
        delta = F(native) - coefficient
        original_j = int(columns[j])
        error += max(delta * F(float(d['lower'][original_j])),
                     delta * F(float(d['upper'][original_j])))
        values[j] = native
    native_rhs = original_oracle.upward(rhs + error)
    # Helper elimination can create tiny nonzero coefficients that Gurobi
    # silently omits. Exact powers of two retain every coefficient and the
    # same inequality; neither physical rows nor bounds are relaxed.
    exponent=max(0,-39-(math.frexp(min(abs(v) for v in values.values()))[1]-1))
    scale=math.ldexp(1.,exponent)
    scaled={j:v*scale for j,v in values.items()}
    require(all(math.isfinite(v) and F(v)==F(values[j])*F(scale) for j,v in scaled.items())
        and math.isfinite(native_rhs*scale) and F(native_rhs*scale)==F(native_rhs)*F(scale),
        'K48_EXACT_NATIVE_ROW_SCALING_NOT_REPRESENTABLE')
    return dict(original_row=int(row), name=str(d['row_names'][row]),
        source_row_sha=original_oracle.row_sha(A, d, int(row)),
        original_terms={str(j): str(c) for j, c in sorted(terms.items())},
        terms={str(j): str(c) for j, c in sorted(local.items())},
        native_terms={str(j): c for j, c in sorted(scaled.items())},
        exact_rhs=str(rhs), helper_constant=str(constant), coefficient_box_error=str(error),
        native_rhs=native_rhs*scale, native_row_scale=scale,
        helper_rows=[dict(row=int(i), source_row_sha=original_oracle.row_sha(A, d, i))
                                          for i in sorted(dependencies)])


def _data(d, rows, columns, cuts):
    rho = len(columns) - 1
    objective = np.zeros(len(columns)); objective[rho] = 1.
    return dict(names=d['names'][columns].copy(), lower=d['lower'][columns].copy(),
        upper=d['upper'][columns].copy(), types=d['types'][columns].copy(), objective=objective,
        constant=np.asarray(0.), rhs=np.r_[d['rhs'][rows], [c['native_rhs'] for c in cuts]],
        sense=np.r_[d['sense'][rows], np.full(len(cuts), '<')],
        row_names=np.r_[d['row_names'][rows], [c['name'] for c in cuts]])


def _matrix(A, rows, columns, cuts):
    ii, jj, vv = [], [], []
    for k, cut in enumerate(cuts):
        for j, value in cut['native_terms'].items():
            ii.append(k); jj.append(int(j)); vv.append(float(value))
    grid = sparse.coo_matrix((vv, (ii, jj)), shape=(len(cuts), len(columns))).tocsr()
    return sparse.vstack((A[rows][:, columns], grid), format='csr')


def prepare_k16(case, selected_full_point, output):
    """Native0; call only in the supervisor's admitted current-case window."""
    began = perf_counter()
    source = identity(case)
    A, d = case.original_A, case.original_d
    full = None if selected_full_point is None else np.asarray(case.lift(selected_full_point), dtype=np.float64)
    original_replay = None if full is None else replay(A, d, full)
    require(original_replay is None or original_replay['PASS'], 'K48_CURRENT_FULL_INTEGER_POINT_REPLAY_FAILED')
    rows, columns = physical_axes(A, d)
    rho = int(columns[-1])
    # With no UB, zero dispatch is only a row-ranking reference. Exact helper
    # elimination includes fixed AIDC/grid constants; no FULL point is asserted.
    reference = np.zeros(A.shape[1]) if full is None else full
    geometry = original_oracle.Geometry(A, d)
    if full is None:
        geometry.numerical(reference, np.zeros_like(reference))
    activity = np.asarray(A @ reference).ravel()
    best = {}
    import re
    for i, name in enumerate(d['row_names']):
        if not str(name).startswith('line_thermal_face['):
            continue
        match = re.fullmatch(r'line_thermal_face\[(\d+),(\d+),(\d+)\]', str(name))
        require(match is not None, 'K48_ORIGINAL_THERMAL_ROW_AXIS')
        slot = int(match[1])
        value = float(activity[i] - d['rhs'][i] + reference[rho])
        if slot not in best or (value, -i) > (best[slot][0], -best[slot][1]):
            best[slot] = value, i
    require(len(best) == 96, 'K48_ORIGINAL_FULL_96_SLOT_SELECTION_REQUIRED')
    selected = sorted(best.values(), key=lambda p: (-p[0], p[1]))[:16]
    cuts = [exact_cut(A, d, row, columns, geometry) for _, row in selected]
    packet = dict(A=_matrix(A, rows, columns, cuts), d=_data(d, rows, columns, cuts),
        rows=rows, columns=columns, cuts=cuts, start=None if full is None else full[columns].copy(), full_start=full,
        source=source, original_replay=original_replay, K=16,
        selection='TOP16_DISTINCT_SLOT_MAX_FACETS_FROM_BASE_GRID' if full is None else 'TOP16_DISTINCT_SLOT_MAX_FACETS_FROM_CURRENT_FULL',
        historical_point_or_bound_read=False, build_wall_seconds=perf_counter()-began)
    certificate = verify_packet(case, packet)
    save_packet(packet, certificate, output)
    return packet, certificate


def verify_packet(case, packet):
    """Independent original verify.Geometry, literal rows/domain and box proof."""
    source = identity(case)
    require(packet['source'] == source, 'K48_PACKET_SOURCE_CASE_ANCHOR_DRIFT')
    A, d = case.original_A, case.original_d
    rows, columns = physical_axes(A, d)
    require(np.array_equal(rows, packet['rows']) and np.array_equal(columns, packet['columns']),
            'K48_PHYSICAL_FULL_DOMAIN_AXES_DRIFT')
    B, e, cuts = packet['A'], packet['d'], packet['cuts']
    physical = A[rows][:, columns].tocsr()
    prefix = B[:len(rows)].tocsr()
    require(physical.shape == prefix.shape and matrix_sha(physical) == matrix_sha(prefix),
            'K48_LITERAL_PHYSICAL_ROWS_DRIFT')
    expected_data = _data(d, rows, columns, cuts)
    require(set(e) == set(expected_data) and all(np.array_equal(e[k], v) for k, v in expected_data.items()),
            'K48_ORIGINAL_BOUND_TYPE_OBJECTIVE_OR_RHS_DRIFT')
    require(B.shape == (len(rows) + len(cuts), len(columns)), 'K48_PACKET_DIMENSION_DRIFT')
    geometry = independent.Geometry(A, independent.canonical_data(d))
    direct = {int(j): k for k, j in enumerate(columns)}
    for k, cut in enumerate(cuts):
        i = cut['original_row']
        rhs, constant, terms = geometry.security(i)
        require(cut['source_row_sha'] == independent.original_row_sha(A, independent.canonical_data(d), i),
                'K48_ORIGINAL_SECURITY_ROW_BYTES_DRIFT')
        require(cut['exact_rhs'] == str(rhs) and cut['helper_constant'] == str(constant)
                and cut['original_terms'] == {str(j): str(v) for j, v in sorted(terms.items())},
                'K48_INDEPENDENT_EXACT_ELIMINATION_FAILED')
        local = {direct[j]: value for j, value in terms.items()}
        require(cut['terms'] == {str(j): str(v) for j, v in sorted(local.items())},
                'K48_IDENTITY_COORDINATE_PROJECTION_FAILED')
        error = F(0)
        expected_terms = {}
        for j, value in local.items():
            native = float(value); expected_terms[j] = native
            delta = F(native) - value
            error += max(delta * F(float(e['lower'][j])), delta * F(float(e['upper'][j])))
        # Independent exact-rational derivation of the positive row scale.
        scale=F(1)
        while min(abs(F(v)) for v in expected_terms.values())*scale < F(1,2**39):
            scale*=2
        require(F(cut.get('native_row_scale',1.))==scale,'K48_EXACT_NATIVE_ROW_SCALE_DRIFT')
        expected_terms={j:float(F(v)*scale) for j,v in expected_terms.items()}
        expected_rhs=float(F(independent.upward(rhs+error))*scale)
        require(cut['coefficient_box_error'] == str(error)
                and F(cut['native_rhs']) == F(expected_rhs), 'K48_OUTWARD_ROUNDING_FAILED')
        begin, end = B.indptr[len(rows) + k:len(rows) + k + 2]
        observed = {int(j): float(v) for j, v in zip(B.indices[begin:end], B.data[begin:end])}
        require(observed == expected_terms and e['rhs'][len(rows)+k] == cut['native_rhs'],
                'K48_NATIVE_CUT_ROW_DRIFT')
        for helper in cut['helper_rows']:
            require(helper['source_row_sha'] == independent.original_row_sha(A, independent.canonical_data(d), helper['row']),
                    'K48_HELPER_ROW_BYTES_DRIFT')
    require(len(set(c['original_row'] for c in cuts)) == len(cuts), 'K48_DUPLICATE_ORIGINAL_GRID_ROW')
    original = projected = None
    if packet['full_start'] is not None:
        original = replay(A, d, packet['full_start'])
        projected = replay(B, e, packet['start'])
        require(original['PASS'] and projected['PASS'] and np.array_equal(packet['start'], packet['full_start'][columns])
                and original['objective'] == projected['objective'], 'K48_CURRENT_FULL_POINT_INCLUSION_FAILED')
    else:
        require(packet['start'] is None, 'K48_SEEDLESS_CANNOT_CLAIM_MIP_START')
    certificate = dict(schema='TABLE_V_CURRENT_K48_PROJECTION_CERTIFICATE_V1', PASS=True, source=source,
        original_matrix_sha=source['matrix_sha'], original_domain_sha=source['domain_sha'],
        packet_matrix_sha=matrix_sha(B), packet_domain_sha=_domain_sha(e),
        original_objective='min rho_max', objective_preserved_exact=True,
        original_domain_projection_included=True,
        proof='Literal original physical rows/bounds/types + exact original grid inequalities; outward rounding only relaxes rows',
        coordinate_representation='IDENTITY_ON_ORIGINAL_FULL_PHYSICAL_COLUMNS_AND_RHO',
        independent_original_geometry_replayed=True, historical_LB_or_UB_transferred=False,
        positive_dyadic_native_row_scaling_exact=True, source_coefficients_not_deleted=True,
        original_FULL_start_replay=original, projected_start_replay=projected,
        K=len(cuts), physical_rows=len(rows), columns=len(columns), nnz=B.nnz,
        current_FULL_UB=None if original is None else original['objective'], Native_optimize_calls=0,
        builder_source=file_record(__file__), original_oracle_source=file_record(original_oracle.__file__),
        independent_verifier_source=file_record(independent.__file__))
    certificate['certificate_sha'] = digest(certificate)
    return certificate


def save_packet(packet, certificate, output):
    output = Path(output); output.mkdir(parents=True, exist_ok=False)
    sparse.save_npz(output / 'JOINT_A.npz', packet['A'])
    np.savez_compressed(output / 'JOINT_DATA.npz', **packet['d'])
    np.savez_compressed(output / 'JOINT_AXES.npz', rows=packet['rows'], columns=packet['columns'])
    if packet['start'] is not None:
        np.savez_compressed(output / 'JOINT_START.npz', point=packet['start'])
    _write(output / 'EXACT_CUTS.json', packet['cuts'])
    _write(output / 'CURRENT_SOURCE_PROJECTION_CERTIFICATE.json', certificate)
    _write(output / 'NATIVE0_MANIFEST.json', dict(source=packet['source'], K=packet['K'],
        selection=packet['selection'], build_wall_seconds=packet['build_wall_seconds'],
        historical_point_or_bound_read=False, Native_optimize_calls=0,
        files=[file_record(p) for p in sorted(output.iterdir()) if p.is_file()]))


def _coefficient_metadata(case):
    c = case.coefficients[0]
    if hasattr(c, 'node_names'):
        return dict(node_names=np.asarray(c.node_names), branch_names=np.asarray(c.branch_names),
                    transformer_ratings=np.asarray(c.transformer_ratings))
    import json
    certificate_record = case.bundle['electrical_certificate']
    require(file_record(certificate_record['path']) == certificate_record, 'K48_ELECTRICAL_CERTIFICATE_BYTES_DRIFT')
    certificate = json.loads(Path(certificate_record['path']).read_text(encoding='utf-8-sig'))
    record = certificate['outputs']['planning_coefficients']
    require(file_record(record['path']) == record and record['sha256'] == c.coefficient_sha256,
            'K48_CURRENT_COEFFICIENT_METADATA_BYTES_DRIFT')
    with np.load(record['path'], allow_pickle=False) as z:
        return {key: z[key].copy() for key in ('node_names', 'branch_names', 'transformer_ratings')}


def separate(case, packet, relaxed_point):
    """Original fixed-family quota/diversity/refill selection on current rows."""
    A, d = case.original_A, case.original_d
    point = np.asarray(relaxed_point, dtype=np.float64)
    require(point.shape == (len(packet['columns']),) and np.isfinite(point).all(), 'K48_LB_SEARCH_POINT_AXIS')
    x = np.zeros(A.shape[1]); errors = np.zeros_like(x)
    x[packet['columns']] = point
    geometry = original_oracle.Geometry(A, d)
    geometry.numerical(x, errors)
    activity = A @ x
    residual = activity - d['rhs']
    violation = np.where(d['sense'] == '<', residual, np.where(d['sense'] == '>', -residual, abs(residual)))
    absolute = abs(A)
    n = np.diff(A.indptr) + 4
    eps = np.finfo(float).eps
    envelope = np.nextafter(4 * (n * eps / (1 - n * eps)) * (absolute @ abs(x) + abs(d['rhs']))
                           + 2 * (absolute @ errors), np.inf)
    del absolute
    metadata = _coefficient_metadata(case)
    existing = {cut['original_row'] for cut in packet['cuts']}
    signatures = {digest(dict(rhs=cut['exact_rhs'], terms=cut['original_terms'])) for cut in packet['cuts']}
    candidates = []
    for i, name in enumerate(d['row_names']):
        f = family(name)
        if f not in FAMILIES or i in existing or violation[i] - envelope[i] <= 1e-8:
            continue
        meta = original_oracle.metadata(str(name), metadata)
        candidates.append(dict(row=i, metadata=meta, rank=float(violation[i] / meta['scale'])))
    pools = {f: sorted([c for c in candidates if c['metadata']['family'] == f],
                       key=lambda c: (-c['rank'], c['row'])) for f in FAMILIES}
    selected, represented, attempted, failures = [], set(), set(), []
    def admit(candidate, diversity=True):
        i, meta = candidate['row'], candidate['metadata']
        key = meta['family'], meta['asset'], meta['phase'], meta['slot']
        if i in attempted or diversity and key in represented:
            return False
        attempted.add(i)
        try:
            cut = exact_cut(A, d, i, packet['columns'], geometry)
            signature = digest(dict(rhs=cut['exact_rhs'], terms=cut['original_terms']))
            if signature in signatures:
                return False
            exact_v = sum((F(v) * F(float(point[int(j)])) for j, v in cut['terms'].items()), F(0)) - F(cut['exact_rhs'])
            native_v = sum((F(float(v)) * F(float(point[int(j)])) for j, v in cut['native_terms'].items()), F(0)) - F(cut['native_rhs'])
            require(exact_v > 0 and native_v > 0, 'K48_EXACT_OR_OUTWARD_CUT_DOES_NOT_EXCLUDE_SEARCH_POINT')
            cut.update(metadata=meta, exact_search_violation=str(exact_v), native_search_violation=str(native_v))
            selected.append(cut); represented.add(key); signatures.add(signature)
            return True
        except ValueError as error:
            failures.append(dict(row=i, error=str(error)))
            return False
    for f in FAMILIES:
        count = 0
        for candidate in pools[f]:
            if count >= QUOTAS[f]:
                break
            count += int(admit(candidate))
    for diversity in (True, False):
        for f in FAMILIES:
            for candidate in pools[f]:
                if len(selected) >= 16:
                    break
                admit(candidate, diversity)
            if len(selected) >= 16:
                break
        if len(selected) >= 16:
            break
    return selected, dict(candidate_count=len(candidates), selected_count=len(selected), failures=failures,
        fixed_family_quotas=QUOTAS, exact_completeness_claim=False, Native_optimize_calls=0)


def append_cuts(case, packet, cuts, output):
    require(0 < len(cuts) <= 16 and len(packet['cuts']) + len(cuts) <= 48, 'K48_NEW_CUT_COUNT')
    all_cuts = deepcopy(packet['cuts']) + deepcopy(cuts)
    began = perf_counter()
    next_packet = dict(packet, cuts=all_cuts, K=len(all_cuts),
        A=_matrix(case.original_A, packet['rows'], packet['columns'], all_cuts),
        d=_data(case.original_d, packet['rows'], packet['columns'], all_cuts),
        selection='ORIGINAL_FIXED_FAMILY_QUOTA_REPRESENTATIVE_REFILL', build_wall_seconds=perf_counter()-began)
    certificate = verify_packet(case, next_packet)
    save_packet(next_packet, certificate, output)
    return next_packet, certificate


def solve_packet(packet, certificate, budget, output):
    """Only the supervisor invokes this within current arm/K48 phase/capture."""
    require(certificate.get('PASS') is True and certificate.get('source') == packet['source']
        and certificate['certificate_sha'] == digest({k: v for k, v in certificate.items() if k != 'certificate_sha'})
        and certificate['packet_matrix_sha'] == matrix_sha(packet['A'])
        and certificate['packet_domain_sha'] == _domain_sha(packet['d']), 'K48_CERTIFIED_PACKET_REQUIRED_BEFORE_NATIVE')
    from .table_v_mess import require_real_budget
    require_real_budget(budget, 'K48_SEPARATE')
    require(budget.context is not None and budget.context['stage'] == 'K48_'+packet['source']['stage']
        and budget.context['arm'] == packet['source']['arm']
        and budget.context['stage_case_sha'] == packet['source']['stage_case_sha']
        and budget.context['source_sha'] == packet['source']['source_sha'],
        'K48_SEPARATE_CURRENT_ARM_STAGE_BUDGET_BINDING_REQUIRED')
    import gurobipy as gp
    output = Path(output); output.mkdir(parents=True, exist_ok=True)
    A, d = packet['A'], packet['d']
    model = gp.Model('TABLE_V_CURRENT_ORIGINAL_K48')
    try:
        for key, value in ORIGINAL_NATIVE_PARAMETERS.items():
            setattr(model.Params, key, value)
        model.Params.LogFile = str(output / 'NATIVE_GUROBI.log')
        x = model.addMVar(A.shape[1], lb=d['lower'], ub=d['upper'], vtype=d['types'], obj=d['objective'])
        x.VarName = d['names'].tolist()
        if packet['start'] is not None:
            x.Start = packet['start']
        model.ObjCon = float(d['constant'])
        rows = model.addMConstr(A, x, d['sense'], d['rhs']); rows.ConstrName = d['row_names'].tolist()
        model.update()
        checks = dict(matrix=matrix_sha(model.getA().tocsr()) == matrix_sha(A),
            rhs=np.array_equal(model.getAttr('RHS'), d['rhs']),
            senses=np.array_equal(model.getAttr('Sense'), d['sense']),
            names=np.array_equal(x.VarName, d['names']), rows=np.array_equal(rows.ConstrName, d['row_names']),
            lower=np.array_equal(x.LB, d['lower']), upper=np.array_equal(x.UB, d['upper']),
            types=np.array_equal(x.VType, d['types']), objective=np.array_equal(x.Obj, d['objective']),
            start=np.all(np.asarray(x.Start) == gp.GRB.UNDEFINED) if packet['start'] is None else np.array_equal(x.Start, packet['start']), objective_constant=model.ObjCon == 0.)
        require(all(checks.values()), 'K48_NATIVE_PACKET_READBACK_FAILED')
        _write(output / 'NATIVE_READBACK.json', dict(PASS=True, checks=checks, Native_optimize_calls=0))
        cap = min(ORIGINAL_CALL_CAP[packet['K']], float(budget.remaining()))
        require(math.isfinite(cap) and cap > 0, 'K48_SEPARATE_STAGE_NATIVE_BUDGET_EXHAUSTED')
        model.Params.TimeLimit = cap
        numeric_errors = []
        def callback(m, where):
            try:
                if where == gp.GRB.Callback.MESSAGE:
                    message = m.cbGet(gp.GRB.Callback.MSG_STRING)
                    if any(s in message for s in ('Numerical trouble', 'Out of memory', 'Numeric error')):
                        numeric_errors.append(message.strip()); m.terminate()
            except Exception as error:
                numeric_errors.append(repr(error)); m.terminate()
        call = budget.solve(model, label='RELEASE_P1:'+budget.context['stage']+':K'+str(packet['K']), cap=cap, callback=callback)
        bound = float(model.ObjBound)
        valid = int(model.Status) in (2, 9, 11) and math.isfinite(bound) and abs(bound) < gp.GRB.INFINITY and not numeric_errors
        result = dict(status=int(model.Status), Native_Runtime=float(model.Runtime), Native_call=call,
            Global_LB=bound if valid else None, numerical_global_bound_contract=valid,
            exact_rational_BB_certificate=False, source=packet['source'], K=packet['K'],
            certificate_sha=certificate['certificate_sha'], SolCount=int(model.SolCount),
            current_FULL_UB=certificate['current_FULL_UB'], UB_from_relaxation_not_promoted=True,
            numeric_callback_errors=numeric_errors)
        point = None
        if model.SolCount:
            point = np.asarray(x.X, dtype=np.float64)
            np.savez_compressed(output / 'RELAXATION_INCUMBENT.npz', point=point)
            result['relaxation_ObjVal'] = float(model.ObjVal)
        _write(output / 'K48_NATIVE_RESULT.json', result)
        return result, point
    finally:
        model.dispose()


def summarize_current_k48(packet, certificate, history):
    """Report each bound at its solved K; packet construction is not a solve.

    Any certified member of the nested relaxation sequence bounds the same
    current original FULL problem. A valid K16/K32 bound is never relabelled as
    a solved or certified K48 bound.
    """
    ub = certificate['current_FULL_UB']
    valid = [r for r in history if r.get('numerical_global_bound_contract') is True
             and type(r.get('Global_LB')) in (int, float) and math.isfinite(r['Global_LB'])]
    for result in history:
        require(result.get('source') == packet['source'], 'K48_HISTORY_CURRENT_CASE_DRIFT')
    best = max((r['Global_LB'] for r in valid), default=None)
    if best is not None and ub is not None:
        require(best <= ub + 1e-6, 'K48_BOUND_EXCEEDS_CURRENT_ORIGINAL_FULL_UB')
    gap = None if best is None or ub is None else max(0., (ub-best) / max(abs(ub), 1e-10))
    completed = any(r['K'] == 48 for r in history)
    valid_k48 = [r for r in valid if r['K'] == 48]
    target_met = gap is not None and gap <= MESS_GLOBAL_GAP_TARGET
    return dict(schema='TABLE_V_CURRENT_K48_RESULT_V1', source=packet['source'],
        status='K48_EXECUTED' if completed else 'PARTIAL_ORIGINAL_K_SEQUENCE',
        K_reached=packet['K'], K_solved=max((r['K'] for r in history), default=None),
        K48_completed=completed, K48_cuts_reached=packet['K'] == 48, history=history,
        current_FULL_UB=ub, Global_LB=best, Global_LB_valid=best is not None,
        Global_LB_valid_K=sorted({r['K'] for r in valid}),
        Global_LB_best_K=sorted({r['K'] for r in valid if r['Global_LB'] == best}),
        Global_LB_scope='CURRENT_ORIGINAL_FULL_WITH_FIXED_AIDC_ANCHOR' if valid else 'NOT_CERTIFIED',
        K48_Global_LB=max((r['Global_LB'] for r in valid_k48), default=None),
        K48_Global_LB_valid=bool(valid_k48), relative_global_gap=gap,
        global_gap_target=MESS_GLOBAL_GAP_TARGET, global_gap_target_percent=100*MESS_GLOBAL_GAP_TARGET,
        global_gap_certified=target_met,
        optimality_status='TARGET_MET' if target_met else 'OPTIMALITY_TARGET_UNMET' if valid else 'NOT_CERTIFIED',
        physical_evaluation_allowed=True, missed_gap_blocks_FULL_feasible_Actual=False,
        historical_bounds_transferred=False, restricted_pool_bound_used=False,
        solver_algorithm='ORIGINAL_K16_THEN_K32_THEN_K48', coordinate_representation='ORIGINAL_FULL_PHYSICAL_IDENTITY')


def run_current_k48(case, selected_full_point, budget, output):
    """Original iterative order, with one separately authorized cumulative cap.

    Caller owns arm_context + phase(K48_M*) + capture_native_methods and RAM
    admission. Original nominal90/180/180s calls are clipped to stage allowance;
    no invented equal splitting, retries, historical bounds, or UB admission.
    """
    output = Path(output); output.mkdir(parents=True, exist_ok=False)
    packet, certificate = prepare_k16(case, selected_full_point, output / 'K16')
    history = []
    control=getattr(case,'global_gap_control',None)
    for iteration in range(3):
        if budget.remaining() <= 0:
            break
        result, point = solve_packet(packet, certificate, budget, output / ('K'+str(packet['K'])) / 'SOLVE')
        history.append(result)
        if control is not None:
            from .table_v_global_control import mess_lower
            mess_lower(control,case,result,Native_Runtime=result['Native_Runtime'],Native_remaining=budget.remaining())
            if control.target_met():break
        if packet['K'] == 48:
            break
        if point is None or iteration == 2 or budget.remaining() <= 0:
            break
        cuts, separation = separate(case, packet, point)
        _write(output / ('SEPARATION_'+str(packet['K'])+'.json'), separation)
        if len(cuts) != 16:
            break
        packet, certificate = append_cuts(case, packet, cuts, output / ('K'+str(packet['K']+16)))
        gc.collect()
    summary = summarize_current_k48(packet, certificate, history)
    _write(output / 'CURRENT_K48_RESULT.json', summary)
    return summary
