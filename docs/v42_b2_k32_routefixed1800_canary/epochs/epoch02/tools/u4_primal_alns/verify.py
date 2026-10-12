"""Independent Source18r Primal restrictions and original-FULL replay.

No solver is imported or constructed here. Stored Dense and FULL CSR matrices
are loaded in succession by the unchanged original validator. Native raw
packets are never rounded, clipped, repaired or overwritten.
"""
from __future__ import annotations

import argparse
import ast
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from fractions import Fraction as F
import gc
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
from time import perf_counter
from types import ModuleType, SimpleNamespace

import numpy as np
from scipy import sparse

ROOT = Path(__file__).resolve().parents[2]
SOURCE = Path(r'D:\v42_dense_response_development_repair_20261011\dates\B2\2025-05-01\attempts\native0_restored\output')
DOCS = ROOT / 'docs/v42_b2_u4_primal_alns_600x3'
SOURCE_SHA = '497609b46faa14ea7e32a9483a333ab32fd264ef'
CASE_SHA = '34c0efffa9c05397552fb167667c0bbfe2f35cec89801a3169c00c64fe77f292'
INITIAL_FILE_SHA = '2e4407a775ec3b10167baa05fc5aa45c2bcfd0f55ea6c5a0b921311338c1d290'
INITIAL_VECTOR_SHA = 'c9d63854a3ec0747a65d2c6724a5d413585f9a4f6754107fc593ba69ea4eda0d'
MATRIX_SHA = 'ed9fd6db73bf47948505cca3a616edf88c7caebdacce8f1dd1007617d6660ef0'
DOMAIN_SHA = '6fd03585e9544f759d4001754a7f28ff04958b078f1959c25f9b397bd45b84f4'
FULL_MATRIX_SHA = '0eca025d99a24d2ae91117cdfe3ae48dade189336ada61b3f8234d9bf99f3cec'
FULL_DOMAIN_SHA = '9247e42b8119f60ef149d0963e31dd8a697af5426a5aaeec9450b2a2f246481e'
INITIAL_EXACT_UB = F('6089348135195533/9007199254740992')


def require(value, message):
    if not value:
        raise ValueError(message)


def file_sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def vector_sha(x):
    return hashlib.sha256(np.ascontiguousarray(x, dtype='<f8').tobytes()).hexdigest()


def write(path, value):
    p = Path(path).resolve()
    require(p.is_relative_to(DOCS.resolve()), 'NEW_RESEARCH_OUTPUT_ONLY')
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def matrix_sha(A):
    h = hashlib.sha256(np.asarray(A.shape, dtype='<i8').tobytes())
    for a in (A.indptr, A.indices, A.data):
        h.update(a.dtype.str.encode('ascii'))
        h.update(np.ascontiguousarray(a).tobytes())
    return h.hexdigest()


def domain_sha(d):
    h = hashlib.sha256()
    for key in sorted(d):
        a = np.asarray(d[key])
        h.update(key.encode())
        h.update(a.dtype.str.encode())
        h.update(np.asarray(a.shape, dtype='<i8').tobytes())
        h.update(a.tobytes())
    return h.hexdigest()


def metadata(path, expected):
    with np.load(path, allow_pickle=False) as z:
        d = {k: z[k].copy() for k in z.files}
    require(domain_sha(d) == expected, 'FROZEN_SOURCE_DOMAIN_SHA_DRIFT:'+Path(path).name)
    return d


class LazyCSR:
    """No cache: check_ub.matrix_replay releases each loaded CSR on return."""
    def __init__(self, path, shape, expected):
        self.path, self.shape, self.expected = Path(path), shape, expected

    def tocsr(self):
        A = sparse.load_npz(self.path).tocsr()
        require(A.shape == self.shape and matrix_sha(A) == self.expected,
                'FROZEN_SOURCE_CSR_SHA_DRIFT:'+self.path.name)
        return A


def authority():
    inherited = read(ROOT/'docs/v42_physical_global_lb_pilot/NATIVE0.json')
    require(inherited.get('PASS') is True and inherited['base_commit'] == SOURCE_SHA
            and inherited['case_sha'] == CASE_SHA, 'INHERITED_ORIGINAL_SOURCE_CASE_AUTHORITY')
    hashes = {}
    for name, expected in inherited['source_records'].items():
        p = Path(name)
        require(p.is_file() and file_sha(p) == expected, 'FROZEN_SOURCE_FILE_SHA_DRIFT:'+p.name)
        hashes[str(p)] = expected
    identity = read(SOURCE/'SCIENTIFIC_CASE_IDENTITY.json')
    require(identity['case_sha'] == CASE_SHA and identity['day'] == '2025-05-01'
            and identity['arm'] == 'B2' and identity['slots'] == 96
            and identity['selected_matrix_sha'] == MATRIX_SHA
            and identity['selected_domain_sha'] == DOMAIN_SHA
            and identity['original_matrix_sha'] == FULL_MATRIX_SHA
            and identity['original_domain_sha'] == FULL_DOMAIN_SHA
            and identity['binary_count'] == 9322, 'CURRENT_DENSE_SOURCE_IDENTITY_DRIFT')
    for key in ('transport_authority', 'response_authority'):
        record = identity[key]['certificate']
        p = Path(record['path'])
        require(file_sha(p) == record['sha256'], 'ORIGINAL_EQUIVALENCE_PACKET_SHA_DRIFT')
        proof = read(p)
        require(proof.get('PASS') is True and proof.get('integer_and_full_LP_domains_identical') is True,
                'CURRENT_ORIGINAL_FULL_EQUIVALENCE_REQUIRED')
        hashes[str(p)] = record['sha256']
    p = SOURCE/'FINAL_FULL_POINT.npz'
    require(file_sha(p) == INITIAL_FILE_SHA, 'SAME_U4_INITIAL_FILE_SHA_DRIFT')
    x = load_point(p)
    require(vector_sha(x) == INITIAL_VECTOR_SHA, 'SAME_U4_INITIAL_VECTOR_SHA_DRIFT')
    replay = read(SOURCE/'FINAL_FULL_POINT.REPLAY.json')
    require(replay.get('PASS') is True and replay.get('strict_raw_C3A_and_FULL_integer_and_binary_pattern_exact') is True
            and replay.get('point_vector_sha256') == INITIAL_VECTOR_SHA
            and F(replay['exact_Global_UB']) == INITIAL_EXACT_UB, 'INITIAL_ORIGINAL_FULL_U4_REPLAY_AUTHORITY')
    hashes[str(p)] = INITIAL_FILE_SHA
    return identity, x, hashes


def pure_original_validators():
    """Execute unchanged Source18r pure functions, omitting GP-only imports.

    The original modules import gurobipy at module scope. AST extraction keeps
    the original validation function and dataclass bodies byte-authorized while
    preventing a validator process from loading any Native solver library.
    """
    receipts = {}
    for relative, wanted, module_name in (
        ('v42_native/mess.py', ('RouteArc', 'Battery', 'validate'), 'v42_native.mess'),
        ('v42_bootstrap/attribution.py', ('supplemental_physical',), 'v42_bootstrap.attribution')):
        path = ROOT/relative
        raw = path.read_bytes()
        old = subprocess.run(['git', 'show', SOURCE_SHA+':'+relative], cwd=ROOT,
                             capture_output=True, check=True).stdout
        require(raw.replace(b'\r\n', b'\n') == old.replace(b'\r\n', b'\n'),
                'UNCHANGED_SOURCE18R_VALIDATOR_BODY_REQUIRED:'+relative)
        tree = ast.parse(raw.decode('utf-8-sig'))
        selected = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.ClassDef))
                    and node.name in wanted]
        require(tuple(n.name for n in selected) == wanted, 'ORIGINAL_PURE_AST_FUNCTION_AXIS_DRIFT')
        module = ModuleType(module_name)
        module.__dict__.update(dataclass=dataclass, asdict=asdict, require=require,
            isfinite=math.isfinite, cos=math.cos, sin=math.sin, pi=math.pi, hypot=math.hypot)
        sys.modules[module_name] = module
        block = ast.Module(body=selected, type_ignores=[])
        exec(compile(block, str(path), 'exec'), module.__dict__)
        receipts[relative] = dict(source_sha=SOURCE_SHA, source_file_sha256=hashlib.sha256(raw).hexdigest(),
            function_names=list(wanted), unchanged_AST_sha256=hashlib.sha256(ast.dump(block).encode()).hexdigest(),
            original_function_bodies_unchanged=True, Native_imports_executed=False)
    return sys.modules['v42_native.mess'], receipts


def load_point(path):
    with np.load(path, allow_pickle=False) as z:
        require(z.files == ['point'], 'RAW_POINT_PACKET_AXIS_DRIFT')
        x = z['point'].copy()
    require(x.dtype == np.dtype('float64') and x.shape == (354277,) and np.isfinite(x).all(),
            'RAW_POINT_NONFINITE_DTYPE_OR_DENSE_AXIS')
    return x


def load_case(*, native=False):
    identity, initial, evidence = authority()
    d = metadata(SOURCE/'DENSE_RESPONSE_DATA.npz', DOMAIN_SHA)
    original_d = metadata(SOURCE/'FULL_DATA.npz', FULL_DOMAIN_SHA)
    with np.load(SOURCE/'CURRENT_C2_AXES.npz', allow_pickle=False) as z:
        columns = z['columns'].copy()
    with np.load(SOURCE/'CURRENT_C3A_AXES.npz', allow_pickle=False) as z:
        require(np.array_equal(z['columns'], np.arange(339387)), 'C3A_COLUMN_TRANSPORT_AXIS_DRIFT')
    with np.load(SOURCE/'DENSE_RESPONSE_AXES.npz', allow_pickle=False) as z:
        require(np.array_equal(z['columns'][:339387], np.arange(339387))
                and np.all(z['columns'][339387:] == -1), 'DENSE_INVERSE_COLUMN_TRANSPORT_DRIFT')
    aliases = read(SOURCE/'CURRENT_C2_ALIASES.json')
    require(len(aliases) == 14618 and len(columns) == 339387, 'EXACT_ALIAS_CENSUS_DRIFT')
    known = set(map(int, columns))
    require(len(known) == len(columns) and min(known) >= 0 and max(known) < 354005, 'PRESOLVE_RETAINED_AXIS_DRIFT')
    for a in reversed(aliases):
        j = int(a['column'])
        require(j not in known and 0 <= j < 354005 and math.isfinite(float(a['constant']))
                and all(int(k) in known and math.isfinite(float(w)) for k, w in a['terms'].items()),
                'EXACT_ALIAS_REVERSE_TOPOLOGY_OR_FINITE_DRIFT')
        known.add(j)
    require(known == set(range(354005)), 'EXACT_ALIAS_INVERSE_INCOMPLETE')

    def lift(point):
        x = np.asarray(point)
        require(x.shape == (354277,) and np.isfinite(x).all(), 'DENSE_POINT_AXIS_DRIFT')
        y = np.zeros(354005, dtype=np.float64)
        y[columns] = x[:339387]
        # The arithmetic order is identical to unchanged Presolve.inverse.
        for a in reversed(aliases):
            y[a['column']] = a['constant']+sum(w*y[int(k)] for k, w in a['terms'].items())
        return y[:344967].copy()

    pure, ast_receipt = pure_original_validators()
    proof = identity['physical_prescreen_authority']['proof']
    require(proof.get('PASS') is True and proof['horizon'] == 96, 'ORIGINAL_PHYSICAL_GRAPH_AUTHORITY')
    sites = tuple(proof['sites'])
    origins = dict(proof['initial'])
    arcs = tuple((s, int(t), dest, int(eta), None if r is None else pure.RouteArc(**r))
                 for s, t, dest, eta, r in proof['arcs'])
    battery = pure.Battery(**proof['battery'])
    battery.validate()
    require(len(sites) == 24 and len(origins) == 4 and len(arcs) == 53626, 'FULL_96_ORIGINAL_GRAPH_CENSUS')
    require(all(a[:4] == (sites[k//96], k % 96, sites[k//96], k % 96+1)
                and a[-1] is None for k, a in enumerate(arcs[:2304])), 'ORIGINAL_STAY_ORDER_DRIFT')
    for arc in arcs[2304:]:
        require(arc[-1] is not None, 'ORIGINAL_ROUTE_ORDER_DRIFT')
        arc[-1].validate(96)
        require(arc[:4] == (arc[-1].source, arc[-1].depart, arc[-1].destination, arc[-1].connect),
                'ORIGINAL_ROUTE_ETA_AXIS_DRIFT')
    selected = LazyCSR(SOURCE/'DENSE_RESPONSE_A.npz', (715596, 354277), MATRIX_SHA)
    A = selected.tocsr() if native else selected
    minimal = {k: identity[k] for k in ('case_sha', 'day', 'arm', 'bundle_sha', 'anchor_sha', 'route_table_sha',
              'original_matrix_sha', 'original_domain_sha', 'selected_matrix_sha', 'selected_domain_sha',
              'binary_count', 'slots', 'units', 'sites', 'objective', 'C3A_policy')}
    minimal['transport'] = identity.get('transport', {})
    minimal['transport_authority'] = identity['transport_authority']['certificate']
    minimal['response_authority'] = identity['response_authority']['certificate']
    case = SimpleNamespace(A=A, d=d, original_A=LazyCSR(SOURCE/'FULL_A.npz', (1130336, 344967), FULL_MATRIX_SHA),
        original_d=original_d, lift=lift, graph=(sites, origins, arcs, battery, dict(PASS=True, source_sha=SOURCE_SHA,
        route_table_sha=identity['route_table_sha'])), point=initial, case_sha=CASE_SHA, identity=minimal,
        bundle=dict(day='2025-05-01'), coefficients=None, source_evidence=evidence, validator_AST=ast_receipt,
        aliases=aliases, selected_columns=columns)
    return case


def load_native_case():
    """Actual Dense CSR only; original_A remains an uncached lazy reader."""
    return load_case(native=True)


initial_case = load_native_case


def exact_objective(d, x):
    return F(float(d['constant']))+sum((F(float(d['objective'][j]))*F(float(x[j]))
        for j in np.flatnonzero(d['objective'])), F(0))


def strict_validator(case, path, evidence):
    """Signature required by unchanged common engine._validate."""
    from v42_m1_research.check_ub import validate_candidate
    x = load_point(path)
    original = case.lift(x)
    faults = {}
    for label, d, v in (('DENSE_C3A', case.d, x), ('ORIGINAL_FULL', case.original_d, original)):
        discrete = np.flatnonzero(d['types'] != 'C')
        binary = np.flatnonzero(d['types'] == 'B')
        noninteger = discrete[v[discrete] != np.rint(v[discrete])]
        nonbinary = binary[~np.isin(v[binary], (0., 1.))]
        if len(noninteger) or len(nonbinary):
            faults[label] = dict(noninteger_count=len(noninteger), nonbinary_count=len(nonbinary),
                examples=[dict(column=int(j), name=str(d['names'][j]), value=float(v[j]))
                          for j in np.unique(np.r_[noninteger[:10], nonbinary[:10]])])
    if faults:
        return dict(PASS=False, error='STRICT_LITERAL_INTEGER_GATE_FAILED', raw_integrality_faults=faults,
            point_vector_sha256=vector_sha(x), raw_point_unchanged=True, repairs=0, rounding=0, clipping=0)
    replay = validate_candidate(case, x)
    exact = exact_objective(case.d, x)
    require(exact == exact_objective(case.original_d, original), 'EXACT_ORIGINAL_OBJECTIVE_TRANSPORT_DRIFT')
    ub = float(exact)
    if F(ub) < exact:
        ub = float(np.nextafter(ub, np.inf))
    stats = {}
    names = list(map(str, case.original_d['names']))
    for unit in sorted(case.graph[1]):
        columns = {prefix: [j for j, name in enumerate(names) if name.startswith(prefix+'['+unit+',')]
                   for prefix in ('Pch', 'Pdis', 'Q', 'SOC', 'charge_mode')}
        stats[unit] = dict(charge_modes_1=int(np.count_nonzero(original[columns['charge_mode']])),
            charging_kWh=float(original[columns['Pch']].sum()*case.graph[3].dt_hours),
            discharging_kWh=float(original[columns['Pdis']].sum()*case.graph[3].dt_hours),
            Q_absolute_kvar_slot_sum=float(abs(original[columns['Q']]).sum()),
            Q_max_absolute_kvar=float(abs(original[columns['Q']]).max(initial=0.)),
            SOC_min_kWh=float(original[columns['SOC']].min()), SOC_max_kWh=float(original[columns['SOC']].max()),
            SOC_boundary_count=len(columns['SOC']))
    return dict(PASS=bool(replay.get('PASS')), case_sha=CASE_SHA, source_sha=SOURCE_SHA,
        exact_Global_UB=str(exact), Global_UB=ub, point_path=str(path), point_file_sha256=file_sha(path),
        point_vector_sha256=vector_sha(x), strict_raw_C3A_and_FULL_integer_and_binary_pattern_exact=True,
        original_matrix_and_96_slot_physical_replay=replay, Native_optimize_calls=0,
        raw_point_unchanged=True, repairs=0, rounding=0, clipping=0, vehicle_operating_statistics=stats,
        Actual='ACTUAL_NOT_RUN')


class ValidationBudget:
    def __init__(self):
        self.costs = []

    @contextmanager
    def cost(self, category, label):
        began = perf_counter()
        try:
            yield
        finally:
            self.costs.append(dict(category=category, label=label, wall_seconds=perf_counter()-began))


def validate(path, evidence=None, solver_objective=None, output=None):
    """Fresh-process entry; outputs failures with their original replay details."""
    began = perf_counter()
    import psutil
    memory_before = psutil.Process().memory_info()._asdict()
    require('gurobipy' not in sys.modules, 'INDEPENDENT_VALIDATION_MUST_NOT_LOAD_GUROBI')
    case = load_case(native=False)
    x = load_point(path)
    raw_sha = file_sha(path)
    evidence = {} if evidence is None else evidence
    result = strict_validator(case, path, evidence)
    if solver_objective is not None:
        require(math.isfinite(float(solver_objective)), 'SOLVER_OBJECTIVE_NONFINITE')
        result['solver_objective'] = float(solver_objective)
        result['solver_and_original_objective_bit_equal'] = bool(float(solver_objective) == float(exact_objective(case.d, x)))
        result['PASS'] = bool(result['PASS'] and result['solver_and_original_objective_bit_equal'])
    # Reuse the unchanged U4 admission contract on a new exact-vector copy.
    # The original RAW packet is never rewritten by engine._validate.
    if result.get('PASS'):
        from v42_common_mess.engine import _validate
        target = Path(output or (DOCS/'VALIDATED_POINT.REPLAY.json'))
        copied = target.with_name(target.stem+'.COMMON_VALIDATE_POINT.npz')
        budget = ValidationBudget()
        admitted = _validate(case, x, copied, lambda _case, _path, _evidence: result,
                             budget, 'FRESH_ORIGINAL_FULL_ADMISSION')
        require(admitted is not None, 'UNCHANGED_COMMON_ENGINE_ADMISSION_FAILED')
        require(vector_sha(load_point(copied)) == vector_sha(x), 'COMMON_ENGINE_COPY_VECTOR_DRIFT')
        result.update(common_engine_validate_reused_unchanged=True, common_engine_admission_copy_path=str(copied),
                      common_engine_admission_copy_sha256=file_sha(copied), common_engine_validation_costs=budget.costs)
    require(file_sha(path) == raw_sha and vector_sha(x) == vector_sha(load_point(path)), 'RAW_NATIVE_POINT_MUTATED')
    require('gurobipy' not in sys.modules, 'INDEPENDENT_VALIDATOR_GUROBI_IMPORT_FORBIDDEN')
    result.update(point_path=str(Path(path).resolve()), point_file_sha256=raw_sha,
        source_sha=SOURCE_SHA, case_sha=CASE_SHA, original_matrix_sha=FULL_MATRIX_SHA,
        original_domain_sha=FULL_DOMAIN_SHA, selected_matrix_sha=MATRIX_SHA, selected_domain_sha=DOMAIN_SHA,
        source_evidence=case.source_evidence, original_validator_AST=case.validator_AST,
        Dense_and_FULL_CSR_not_simultaneously_retained=True, Native_optimize_calls=0,
        validator_memory_before=memory_before, validator_memory_after=psutil.Process().memory_info()._asdict(),
        validation_total_wall_seconds=perf_counter()-began, restricted_ObjBound_is_Global_LB=False,
        Actual='ACTUAL_NOT_RUN')
    if output:
        write(output, result)
    return result


def audit_hamming(center, free, radius, coefficients, rhs):
    x = np.asarray(center)
    free = np.asarray(free, dtype=np.int64)
    coefficients = np.asarray(coefficients)
    require(np.isin(x[free], (0., 1.)).all(), 'HAMMING_LITERAL_CENTER_REQUIRED')
    expected = np.where(x[free] == 1., -1., 1.)
    expected_rhs = float(radius)-float(np.count_nonzero(x[free]))
    require(np.array_equal(coefficients, expected) and float(rhs) == expected_rhs,
            'HAMMING_COEFFICIENT_OR_RHS_DRIFT')
    require(float(coefficients @ x[free]) <= float(rhs), 'ORIGINAL_CENTER_EXCLUDED_BY_HAMMING')
    return dict(PASS=True, center_Hamming_distance=0, rhs=expected_rhs,
                center_activity=float(coefficients @ x[free]))


def verified_center(case, x, spec):
    digest = vector_sha(x)
    if digest == INITIAL_VECTOR_SHA:
        path = DOCS/'INITIAL_U4_INDEPENDENT_REPLAY.json'
        expected = file_sha(path)
    else:
        record = spec.get('center_full_replay')
        require(isinstance(record, dict) and set(record) >= {'path', 'sha256'},
                'ADOPTED_CENTER_EXPLICIT_FULL_REPLAY_RECORD_REQUIRED')
        path, expected = Path(record['path']), record['sha256']
        require(path.resolve().is_relative_to(DOCS.resolve()), 'CURRENT_CENTER_FULL_REPLAY_PATH_REQUIRED')
    require(file_sha(path) == expected, 'CENTER_FULL_REPLAY_FILE_SHA_DRIFT')
    receipt = read(path)
    require(receipt.get('PASS') is True and receipt.get('case_sha') == CASE_SHA
            and receipt.get('source_sha') == SOURCE_SHA and receipt.get('point_vector_sha256') == digest
            and receipt.get('strict_raw_C3A_and_FULL_integer_and_binary_pattern_exact') is True
            and receipt.get('original_matrix_and_96_slot_physical_replay', {}).get('PASS') is True,
            'CENTER_ORIGINAL_FULL_VERIFICATION_BINDING_DRIFT')
    return dict(path=str(path), sha256=expected, point_vector_sha256=digest, Global_UB=receipt['Global_UB'])


def audit_neighborhood(case, center, spec, lower, upper, output=None):
    """Independent exact fixing and Hamming audit, with full Alias protection."""
    x = np.asarray(center)
    lb, ub = np.asarray(lower), np.asarray(upper)
    require(case.case_sha == CASE_SHA and x.dtype == np.dtype('float64') and x.shape == (354277,)
            and np.isfinite(x).all(), 'SOURCE_CASE_OR_CENTER_AXIS_DRIFT')
    d = case.d
    center_receipt = verified_center(case, x, spec)
    require(domain_sha(d) == DOMAIN_SHA and matrix_sha(case.A) == MATRIX_SHA, 'NATIVE0_DENSE_MODEL_IDENTITY_DRIFT')
    binary = np.flatnonzero(d['types'] != 'C')
    require(np.isin(x[binary], (0., 1.)).all(), 'LITERAL_BINARY_CENTER_REQUIRED')
    free = np.asarray(spec['free_binary_columns'], dtype=np.int64)
    fixed = np.asarray(spec['fixed_binary_columns'], dtype=np.int64)
    route = np.asarray(spec.get('fixed_route_columns', []), dtype=np.int64)
    require(np.array_equal(np.sort(np.r_[free, fixed]), binary)
            and len(np.unique(np.r_[free, fixed])) == len(binary), 'NEIGHBORHOOD_BINARY_PARTITION_DRIFT')
    require(len(np.unique(route)) == len(route) and all(str(d['names'][j]).startswith('route_flow[')
            and d['types'][j] == 'C' for j in route), 'CONTINUOUS_FIX_ONLY_DECLARED_ORIGINAL_ROUTE_FLOW')
    expected_l, expected_u = d['lower'].copy(), d['upper'].copy()
    fix = np.r_[fixed, route]
    expected_l[fix], expected_u[fix] = x[fix], x[fix]
    require(np.array_equal(lb, expected_l) and np.array_equal(ub, expected_u), 'UNDECLARED_BOUND_RESTRICTION_OR_CENTER_DRIFT')
    require(np.all(lb >= d['lower']) and np.all(ub <= d['upper']) and np.all(lb <= ub), 'SOURCE_BOX_RESTRICTION_DRIFT')
    require(np.all(x >= lb) and np.all(x <= ub), 'ORIGINAL_CENTER_EXCLUDED_BY_FIXING')
    radius = spec['hamming_radius']
    require(not isinstance(radius, bool) and math.isfinite(float(radius)) and float(radius) >= 0,
            'PREREGISTERED_HAMMING_RADIUS_REQUIRED')
    coefficients = np.where(x[free] == 1., -1., 1.)
    rhs = float(radius)-float(np.count_nonzero(x[free]))
    activity = float(coefficients @ x[free])
    audit_hamming(x, free, radius, coefficients, rhs)
    require(activity == -float(np.count_nonzero(x[free])), 'ORIGINAL_CENTER_EXCLUDED_BY_HAMMING')
    method = str(spec['method'])
    selected = spec.get('selected_units', spec.get('units', []))
    # Accept the selection schema only as an explicit unit list, never infer a
    # selected vehicle merely from a free mode which could hide a partition bug.
    if isinstance(selected, str):
        selected = [selected]
    selected = list(selected)
    if method == 'N1':
        selected = []
        require(all(str(d['names'][j]).startswith('charge_mode[') for j in free)
                and len(free) == 384, 'N1_MUST_FREE_ALL_384_MODES_AND_FIX_ALL_NODES')
    else:
        require(method in ('N2', 'N3') and len(set(selected)) == (1 if method == 'N2' else 2)
                and set(selected) <= set(case.graph[1]), 'SELECTED_VEHICLE_COUNT_OR_SCHEMA_DRIFT')
        for j in free:
            name = str(d['names'][j])
            require(name.split('[', 1)[1].split(',', 1)[0] in selected, 'OTHER_VEHICLE_BINARY_RELEASED')
        for unit in selected:
            modes = np.flatnonzero(np.char.startswith(d['names'], 'charge_mode['+unit+','))
            require(len(modes) == 96 and set(map(int, modes)) <= set(map(int, free)), 'SELECTED_UNIT_ALL_96_MODES_REQUIRED')
    unselected = set(case.graph[1])-set(selected)
    expected_route = np.array([j for j, name in enumerate(d['names']) if str(name).startswith('route_flow[')
        and str(name).split('[', 1)[1].split(',', 1)[0] in unselected], dtype=np.int64)
    require(np.array_equal(np.sort(route), expected_route), 'UNSELECTED_CONTINUOUS_ROUTE_FIX_INCOMPLETE')
    # Exact Alias dependence proof: every original arc and node of an
    # unselected vehicle depends only on retained fixed coordinates/constants.
    # selected_columns are C1 indices; remap fixed Dense column IDs first.
    fixed_set = set(map(int, fix))
    known = {int(old): bool(new in fixed_set) for new, old in enumerate(case.selected_columns)}
    for a in reversed(case.aliases):
        known[int(a['column'])] = all(known[int(k)] for k, w in a['terms'].items() if w)
    original = case.lift(x)
    alias_counts = {}
    for unit in sorted(unselected):
        columns = [j for j, n in enumerate(case.original_d['names']) if str(n).startswith('arc['+unit+',')]
        require(all(known[j] for j in columns), 'UNSELECTED_ORIGINAL_ARC_ALIAS_NOT_FIXED:'+unit)
        require(np.isin(original[columns], (0., 1.)).all(), 'UNSELECTED_ORIGINAL_ROUTE_NOT_LITERAL_INTEGER')
        alias_counts[unit] = len(columns)
    continuous = d['types'] == 'C'
    nonroute = continuous & ~np.char.startswith(d['names'], 'route_flow[')
    result = dict(PASS=True, case_sha=CASE_SHA, source_sha=SOURCE_SHA, method=method,
        center_point_vector_sha256=vector_sha(x), same_initial_point_vector_sha256=INITIAL_VECTOR_SHA,
        verified_center_full_replay=center_receipt,
        selected_units=selected, free_binary_count=len(free), fixed_binary_count=len(fixed),
        fixed_continuous_route_count=len(route), original_unselected_arc_aliases_fixed=alias_counts,
        exact_alias_inverse_complete_and_acyclic=True, hamming_radius=float(radius), hamming_rhs=rhs,
        hamming_center_activity=activity, center_Hamming_distance=0, center_always_included=True,
        original_power_SOC_and_all_nonroute_continuous_bounds_exact=bool(np.array_equal(lb[nonroute], d['lower'][nonroute])
            and np.array_equal(ub[nonroute], d['upper'][nonroute])),
        original_Dense_CSR_RHS_senses_types_objective_exact=True,
        original_96_slot_full_domain_constraints_preserved_by_certified_transport=True,
        common_builder_spec_None_continuous_bound_check_is_vacuous=True,
        explicit_continuous_route_restriction_audited_here=True,
        feasibility_relation='Restricted neighborhood is a subset of the Source18r original FULL domain under exact inverse transport; its verified center is included.',
        restricted_ObjBound_is_Global_LB=False, Native_optimize_calls=0, Actual='ACTUAL_NOT_RUN')
    if output:
        write(output, result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--point', type=Path, default=SOURCE/'FINAL_FULL_POINT.npz')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--solver-objective', type=float)
    args = parser.parse_args()
    try:
        result = validate(args.point, solver_objective=args.solver_objective, output=args.output)
    except Exception as exc:
        result = dict(PASS=False, error=repr(exc), point_path=str(args.point), invalid_point_not_admitted=True,
            Native_optimize_calls=0, repairs=0, rounding=0, clipping=0, Actual='ACTUAL_NOT_RUN')
        write(args.output, result)
    print(json.dumps({k: result.get(k) for k in ('PASS', 'Global_UB', 'error', 'validation_total_wall_seconds')}))
    return 0 if result.get('PASS') is True else 2


if __name__ == '__main__':
    raise SystemExit(main())
