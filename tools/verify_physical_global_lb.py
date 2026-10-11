"""Independent exact audit of the Source18r physical Global LB pilot.

This module does not import the pilot or Gurobi and never optimizes.  Original
stored doubles are interpreted as exact dyadic rationals.  A successful final
certificate relies on the native solver's global-bound numerical contract, as
distinct from the exact model, inclusion, substitution, and transport proofs.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import re
import time
import traceback

import numpy as np
from scipy import sparse

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = Path(r'D:\v42_dense_response_development_repair_20261011\dates\B2\2025-05-01\attempts\native0_restored\output')
DEFAULT_PILOT = ROOT / 'docs/v42_physical_global_lb_pilot'
UNITS = ('MESS01', 'MESS02', 'MESS03', 'MESS04')
PHYSICAL_VARIABLES = {'arc', 'charge_mode', 'SOC', 'Pch', 'Pdis', 'Q'}
PHYSICAL_ROWS = {'flow', 'terminal_location', 'initial_SOC', 'terminal_SOC',
                 'energy_balance', 'connected_Pch', 'connected_Pdis',
                 'no_simultaneous_charge', 'no_simultaneous_discharge',
                 'connected_Qmax', 'connected_Qmin', 'PCS16'}
BASE = '497609b46faa14ea7e32a9483a333ab32fd264ef'
CASE = '34c0efffa9c05397552fb167667c0bbfe2f35cec89801a3169c00c64fe77f292'
ORIGINAL_MATRIX = '0eca025d99a24d2ae91117cdfe3ae48dade189336ada61b3f8234d9bf99f3cec'
ORIGINAL_DOMAIN = '9247e42b8119f60ef149d0963e31dd8a697af5426a5aaeec9450b2a2f246481e'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    tmp.replace(path)


def sha_file(path):
    answer = hashlib.sha256()
    with path.open('rb') as stream:
        while data := stream.read(1024 * 1024):
            answer.update(data)
    return answer.hexdigest()


def original_digests(matrix, data):
    """Implement identity packet byte convention without importing the builder."""
    matrix_hash = hashlib.sha256(np.asarray(matrix.shape, dtype='<i8').tobytes())
    for array in (matrix.indptr, matrix.indices, matrix.data):
        matrix_hash.update(array.dtype.str.encode('ascii'))
        matrix_hash.update(np.ascontiguousarray(array).tobytes())
    domain_hash = hashlib.sha256()
    for key in sorted(data):
        array = np.asarray(data[key])
        domain_hash.update(key.encode())
        domain_hash.update(array.dtype.str.encode())
        domain_hash.update(np.asarray(array.shape, dtype='<i8').tobytes())
        domain_hash.update(array.tobytes())
    return matrix_hash.hexdigest(), domain_hash.hexdigest()


def dyadic(value):
    require(math.isfinite(float(value)), 'NONFINITE_EXACT_ARITHMETIC_INPUT')
    return Fraction(float(value))


def downward(value):
    result = float(value)
    require(math.isfinite(result), 'EXACT_VALUE_NOT_FINITE_FLOAT')
    return float(np.nextafter(result, -np.inf)) if Fraction(result) > value else result


def axis(name):
    match = re.fullmatch(r'([^\[]+)(?:\[([^\]]+)\])?', str(name))
    require(match is not None, 'INVALID_ORIGINAL_NAME')
    return match.group(1), [] if match.group(2) is None else match.group(2).split(',')


def vehicle(name):
    family, coordinates = axis(name)
    if family not in PHYSICAL_VARIABLES:
        return 0
    require(coordinates and coordinates[0] in UNITS, 'UNKNOWN_PHYSICAL_OWNER')
    return UNITS.index(coordinates[0]) + 1


def load_npz(path):
    with np.load(path, allow_pickle=False) as packet:
        return {key: packet[key].copy() for key in packet.files}


class OriginalGeometry:
    """Find pivots from original equality rows, independent of export terms."""

    def __init__(self, matrix, data):
        self.A, self.d = matrix, data
        self.definitions = {}
        self.expanded = {}
        self.used_definitions = set()
        for row, label in enumerate(data['row_names']):
            family, coordinates = axis(label)
            if not family.endswith('_binding') or not family.startswith(('response_', 'injection_')):
                continue
            require(data['sense'][row] == '=', 'BINDING_MUST_BE_EQUALITY')
            start, end = matrix.indptr[row:row + 2]
            candidates = []
            for col, coefficient in zip(matrix.indices[start:end], matrix.data[start:end]):
                var_family, var_coordinates = axis(data['names'][col])
                if var_family + '_binding' == family and coefficient == 1.:
                    candidates.append((int(col), var_coordinates))
            require(len(candidates) == 1, 'BINDING_PIVOT_MUST_BE_UNIQUE_POSITIVE_ONE')
            col, var_coordinates = candidates[0]
            if family.startswith('response_'):
                require(coordinates == var_coordinates, 'RESPONSE_BINDING_TIME_BRANCH_AXIS_MISMATCH')
            else:
                # Original injection bindings are unnamed.  Ownership is given
                # by their unique +1 injection column, never row order.
                require(not coordinates or coordinates == var_coordinates, 'INJECTION_BINDING_AXIS_MISMATCH')
                expected_vars = {'Pch', 'Pdis'} if family == 'injection_P_binding' else {'Q'}
                require(family in {'injection_P_binding', 'injection_Q_binding'}, 'UNKNOWN_INJECTION_BINDING')
                for other, value in zip(matrix.indices[start:end], matrix.data[start:end]):
                    if int(other) == col:
                        continue
                    other_family, other_axis = axis(data['names'][other])
                    require(other_family in expected_vars and other_axis[1:] == var_coordinates,
                            'INJECTION_PHYSICAL_SITE_SLOT_MISMATCH')
                    expected = 1. if other_family == 'Pch' else -1.
                    require(value == expected, 'INJECTION_CHARGE_DISCHARGE_SIGN_MISMATCH')
                require(data['rhs'][row] == 0., 'INJECTION_UNEXPECTED_CONSTANT')
            require(col not in self.definitions, 'DUPLICATE_ORIGINAL_HELPER_DEFINITION')
            self.definitions[col] = row

    def expand(self, col, stack=()):
        if col in self.expanded:
            return self.expanded[col]
        require(col not in stack, 'ORIGINAL_BINDING_CYCLE')
        if col not in self.definitions:
            # Preserving literal physical coordinates allows their original
            # finite bounds and all integer types to be checked separately.
            require(vehicle(self.d['names'][col]) != 0 or str(self.d['names'][col]) == 'rho_max',
                    'UNELIMINATED_NONPHYSICAL_COORDINATE')
            result = Fraction(0), {col: Fraction(1)}
        else:
            row = self.definitions[col]
            self.used_definitions.add(row)
            start, end = self.A.indptr[row:row + 2]
            constant = dyadic(self.d['rhs'][row])
            terms = defaultdict(Fraction)
            for other, value in zip(self.A.indices[start:end], self.A.data[start:end]):
                other = int(other)
                if other == col:
                    continue
                offset, leaves = self.expand(other, stack + (col,))
                coefficient = -dyadic(value)
                constant += coefficient * offset
                for leaf, weight in leaves.items():
                    terms[leaf] += coefficient * weight
            result = constant, {leaf: weight for leaf, weight in terms.items() if weight}
        self.expanded[col] = result
        return result

    def thermal(self, row, rho):
        require(axis(self.d['row_names'][row])[0] == 'line_thermal_face', 'SELECTED_ROW_NOT_ORIGINAL_THERMAL')
        require(self.d['sense'][row] == '<', 'ORIGINAL_THERMAL_SENSE_MISMATCH')
        start, end = self.A.indptr[row:row + 2]
        constant = -dyadic(self.d['rhs'][row])
        terms = defaultdict(Fraction)
        for col, value in zip(self.A.indices[start:end], self.A.data[start:end]):
            offset, leaves = self.expand(int(col))
            coefficient = dyadic(value)
            constant += coefficient * offset
            for leaf, weight in leaves.items():
                terms[leaf] += coefficient * weight
        require(terms.pop(rho, Fraction(0)) == -1, 'ORIGINAL_THERMAL_RHO_SIGN_OR_SCALE_MISMATCH')
        answer = {col: value for col, value in terms.items() if value}
        require(all(vehicle(self.d['names'][col]) for col in answer), 'THERMAL_HAS_RESIDUAL_COUPLED_VARIABLE')
        return constant, answer


def independently_lift_u4(source, data):
    raw = load_npz(source / 'FRESH_U4/RAW_00.npz')['point']
    columns = load_npz(source / 'CURRENT_C2_AXES.npz')['columns']
    aliases = load_json(source / 'CURRENT_C2_ALIASES.json')
    require(len(set(map(int, columns))) == len(columns), 'C2_DUPLICATE_COLUMNS')
    positions = {int(col): pos for pos, col in enumerate(columns)}
    definitions = {int(item['column']): item for item in aliases}
    require(len(definitions) == len(aliases) and not set(positions) & set(definitions), 'C2_ALIAS_AXIS_DUPLICATE')
    cache = {}

    def coordinate(col, stack=()):
        if col in cache:
            return cache[col]
        require(col not in stack, 'C2_U4_ALIAS_CYCLE')
        if col in positions:
            value = float(raw[positions[col]])
        else:
            require(col in definitions, 'U4_ORIGINAL_COORDINATE_MISSING')
            item = definitions[col]
            value = float(item['constant']) + sum(float(weight) * coordinate(int(other), stack + (col,))
                                                   for other, weight in item['terms'].items())
        require(math.isfinite(value), 'U4_LIFT_NONFINITE')
        cache[col] = value
        return value

    return np.array([coordinate(col) for col in range(len(data['names']))])


def support_partition(matrix, data):
    owner = np.array([vehicle(name) for name in data['names']], dtype=np.int8)
    occupied = np.flatnonzero(np.diff(matrix.indptr))
    low, high = np.zeros(matrix.shape[0], dtype=np.int8), np.zeros(matrix.shape[0], dtype=np.int8)
    support = owner[matrix.indices]
    if len(occupied):
        low[occupied] = np.minimum.reduceat(support, matrix.indptr[occupied])
        high[occupied] = np.maximum.reduceat(support, matrix.indptr[occupied])
    family = np.array([axis(name)[0] for name in data['row_names']])
    named_physical = np.isin(family, list(PHYSICAL_ROWS))
    require(np.all((low[occupied[named_physical[occupied]]] == high[occupied[named_physical[occupied]]]) &
                   (low[occupied[named_physical[occupied]]] > 0)), 'PHYSICAL_ORIGINAL_ROW_NOT_SINGLE_OWNER')
    empty_physical = np.flatnonzero(named_physical & (np.diff(matrix.indptr) == 0))
    for row in empty_physical:
        rhs, sense = data['rhs'][row], data['sense'][row]
        require(rhs == 0. if sense == '=' else rhs >= 0. if sense == '<' else rhs <= 0.,
                'EMPTY_PHYSICAL_ROW_NOT_TAUTOLOGY')
    return owner, low, high, family, empty_physical


def compare_sparse(expected, observed):
    require(expected.shape == observed.shape and all(np.array_equal(getattr(expected, key), getattr(observed, key))
            for key in ('indptr', 'indices', 'data')), 'UNIT_MATRIX_NOT_LITERAL_ORIGINAL_SLICE')


def replay_local_incumbent(pilot, unit, receipt):
    """Check saved native local point, without making a global UB claim."""
    path = pilot / unit / 'INCUMBENT.npz'
    if receipt['SolCount'] == 0:
        require(receipt['incumbent'] is None and not path.exists(), 'UNIT_MISSING_OR_UNEXPECTED_INCUMBENT_PACKET')
        return dict(available=False, scope='LOCAL_DIAGNOSTIC_ONLY', Global_UB_claim=False, original_planning_feasibility_claim=False)
    require(receipt['SolCount'] > 0 and receipt['incumbent'] is not None and path.exists(), 'UNIT_INCUMBENT_PACKET_MISSING')
    point = load_npz(path)['point']
    matrix = sparse.load_npz(pilot / f'UNIT_{unit}_A.npz').tocsr()
    data = load_npz(pilot / f'UNIT_{unit}_DATA.npz')
    require(point.shape == (matrix.shape[1],) and np.isfinite(point).all(), 'UNIT_INCUMBENT_AXIS_OR_FINITE_MISMATCH')
    residual = matrix @ point - data['rhs']
    violation = np.maximum(0., np.where(data['sense'] == '=', abs(residual),
                                       np.where(data['sense'] == '<', residual, -residual)))
    row_error = float(violation.max(initial=0.))
    bound_error = max(0., float(np.max(data['lower'] - point)), float(np.max(point - data['upper'])))
    integer = point[data['types'] != 'C']
    integer_error = float(np.max(abs(integer - np.rint(integer)), initial=0.))
    require(row_error <= 1e-6 and bound_error <= 1e-8 and integer_error <= 1e-8, 'UNIT_INCUMBENT_LOCAL_PHYSICAL_REPLAY_FAILED')
    objective = sum((dyadic(data['objective'][col]) * dyadic(point[col])
                     for col in np.flatnonzero(data['objective'])), Fraction(0)) + dyadic(data['constant'])
    objective_error = abs(float(objective) - receipt['incumbent'])
    require(objective_error <= 1e-8, 'UNIT_INCUMBENT_NATIVE_OBJECTIVE_REPLAY_MISMATCH')
    bound_gap = None
    if receipt['valid_solver_bound'] and objective != 0:
        bound_gap = float(abs(objective - dyadic(receipt['selected_solver_bound'])) / abs(objective))
    return dict(available=True, PASS=True, scope='LOCAL_PHYSICAL_NUMERICAL_REPLAY_ONLY',
                Global_UB_claim=False, original_planning_feasibility_claim=False,
                maximum_row_violation=row_error, maximum_bound_violation=bound_error,
                maximum_integrality_violation=integer_error, exact_integer_pattern=bool(np.all(integer == np.rint(integer))),
                objective_exact=str(objective), objective=float(objective), objective_difference=objective_error,
                selected_bound_local_relative_gap=bound_gap,
                row_tolerance=1e-6, bound_tolerance=1e-8, integrality_tolerance=1e-8,
                point_sha=sha_file(path), point_rounding=False, point_clipping=False)


def native0_certificate(source, pilot):
    started = time.perf_counter()
    zero, weights = load_json(pilot / 'NATIVE0.json'), load_json(pilot / 'WEIGHTS.json')
    require(zero['PASS'] is True and zero['base_commit'] == BASE and zero['case_sha'] == CASE, 'NATIVE0_SOURCE_CASE_MISMATCH')
    require(zero['Native_calls'] == zero['full_MILP_calls'] == zero['campaign_calls'] == 0, 'NATIVE0_MUST_HAVE_NO_OPTIMIZE')
    require(zero['workers'] == zero['threads'] == 1 and zero['native_limit_per_unit'] <= 30.
            and zero['native_hard_budget'] <= 120., 'PILOT_BUDGET_DRIFT')
    records = zero['source_records']
    expected_names = ('FULL_A.npz', 'FULL_DATA.npz', 'FIXED_AIDC_ANCHOR.json', 'SCIENTIFIC_CASE_IDENTITY.json',
                      'FRESH_U4/RAW_00.npz', 'FRESH_U4/RAW_00.REPLAY.json', 'CURRENT_C2_AXES.npz', 'CURRENT_C2_ALIASES.json')
    require({Path(name).resolve() for name in records} == {(source / name).resolve() for name in expected_names},
            'SOURCE_RECORD_COVER_MISMATCH')
    for name, expected in records.items():
        require(sha_file(Path(name)) == expected, 'FROZEN_SOURCE_FILE_SHA_MISMATCH:' + name)
    A, d = sparse.load_npz(source / 'FULL_A.npz').tocsr(), load_npz(source / 'FULL_DATA.npz')
    require(A.has_canonical_format and np.all(A.data != 0) and np.isfinite(A.data).all(), 'ORIGINAL_CSR_NOT_CANONICAL_FINITE')
    require(A.shape == (len(d['rhs']), len(d['names'])) and len(set(map(str, d['names']))) == A.shape[1], 'ORIGINAL_AXIS_MISMATCH')
    require(zero['full_rows'] == A.shape[0] and zero['full_columns'] == A.shape[1], 'ORIGINAL_SIZE_MISMATCH')
    identity = load_json(source / 'SCIENTIFIC_CASE_IDENTITY.json')
    matrix_digest, domain_digest = original_digests(A, d)
    require(identity['case_sha'] == CASE and matrix_digest == identity['original_matrix_sha'] == zero['original_matrix_sha'] == ORIGINAL_MATRIX
            and domain_digest == identity['original_domain_sha'] == zero['original_domain_sha'] == ORIGINAL_DOMAIN,
            'INDEPENDENT_ORIGINAL_MATRIX_DOMAIN_IDENTITY_MISMATCH')
    rho_candidates = np.flatnonzero(d['names'] == 'rho_max')
    require(len(rho_candidates) == 1, 'ORIGINAL_RHO_MISSING_OR_DUPLICATE')
    rho = int(rho_candidates[0])
    require(d['constant'] == 0. and d['objective'][rho] == 1. and np.count_nonzero(d['objective']) == 1,
            'ORIGINAL_OBJECTIVE_CONSTANT_OR_COEFFICIENT_MISMATCH')
    require(d['lower'][rho] == 0. and d['upper'][rho] == 1. and d['types'][rho] == 'C', 'ORIGINAL_RHO_DOMAIN_MISMATCH')
    replay = load_json(source / 'FRESH_U4/RAW_00.REPLAY.json')
    require(replay['PASS'] is True and replay['case_sha'] == CASE and replay['Native_optimize_calls'] == 0,
            'SAVED_U4_NOT_CERTIFIED_CURRENT_CASE')
    x = independently_lift_u4(source, d)
    residual = A @ x - d['rhs']
    violation = np.maximum(0., np.where(d['sense'] == '=', abs(residual), np.where(d['sense'] == '<', residual, -residual)))
    require(violation.max(initial=0.) <= 1e-6 and np.all(x >= d['lower'] - 1e-8)
            and np.all(x <= d['upper'] + 1e-8), 'CURRENT_U4_ORIGINAL_REPLAY_FAILED')
    require(np.all(x[d['types'] != 'C'] == np.rint(x[d['types'] != 'C'])), 'CURRENT_U4_INTEGER_PATTERN_DRIFT')
    require(dyadic(x[rho]) == Fraction(replay['exact_Global_UB']) == dyadic(zero['UB']), 'CERTIFIED_UB_MISMATCH')
    require(weights['generated_vectors'] == 1 and weights['weight_iterations'] == 0, 'ONE_FIXED_WEIGHT_VECTOR_REQUIRED')
    require(weights['selection'] == 'TOP16_DISTINCT_SLOT_MAX_FACETS_FROM_FROZEN_U4', 'UNKNOWN_WEIGHT_SELECTION')
    selected = weights['rows']
    require(len(selected) == 16 and len({int(item['row']) for item in selected}) == 16, 'WEIGHT_ROW_COVER_MISMATCH')
    values, best = A @ x, {}
    for row, name in enumerate(d['row_names']):
        match = re.fullmatch(r'line_thermal_face\[(\d+),(\d+),(\d+)\]', str(name))
        if match is None:
            continue
        slot = int(match.group(1))
        value = float(values[row] - d['rhs'][row] + x[rho])
        if slot not in best or (value, -row) > (best[slot][0], -best[slot][1]):
            best[slot] = value, row
    require(set(best) == set(range(96)), 'ORIGINAL_THERMAL_96_SLOT_AXIS_MISSING')
    expected_selection = [row for _, row in sorted(best.values(), key=lambda item: (-item[0], item[1]))[:16]]
    require([int(item['row']) for item in selected] == expected_selection, 'WEIGHTS_NOT_SELECTED_FROM_FROZEN_U4')
    geometry = OriginalGeometry(A, d)
    fixed, coefficient, weight_sum = Fraction(0), defaultdict(Fraction), Fraction(0)
    for item in selected:
        row, weight = int(item['row']), Fraction(item['weight'])
        require(weight >= 0 and weight == Fraction(1, 16), 'INVALID_NONNEGATIVE_WEIGHT')
        require(item['name'] == str(d['row_names'][row]), 'SELECTED_ORIGINAL_NAME_MISMATCH')
        b, terms = geometry.thermal(row, rho)
        require(b == Fraction(item['b']) and terms == {int(col): Fraction(value) for col, value in item['terms'].items()},
                'INDEPENDENT_ORIGINAL_THERMAL_AFFINE_RECONSTRUCTION_MISMATCH')
        require(item['original_RHS'] == d['rhs'][row] and item['original_rho_coefficient'] == -1.
                and item['normalized_sense'] == '<', 'SELECTED_ORIGINAL_RHS_SIGN_MISMATCH')
        fixed += weight * b
        weight_sum += weight
        for col, value in terms.items():
            coefficient[col] += weight * value
    coefficient = {col: value for col, value in coefficient.items() if value}
    require(weight_sum == 1 and fixed == Fraction(weights['fixed_term']) == Fraction(zero['fixed_term']), 'WEIGHT_SIMPLEX_OR_FIXED_TERM_MISMATCH')
    require(coefficient == {int(col): Fraction(value) for col, value in weights['exact_objective'].items()}, 'WEIGHTED_EXACT_OBJECTIVE_MISMATCH')
    owners, low, high, families, empty_physical = support_partition(A, d)
    require(zero['mixed_rows'] == np.count_nonzero(low != high), 'OMITTED_MIXED_ROW_CENSUS_MISMATCH')
    mixed = np.flatnonzero(low != high)
    nonunit = np.flatnonzero((low == 0) & (high == 0))
    require(zero['mixed_families'] == dict(Counter(map(str, families[mixed])))
            and zero['dropped_nonunit_rows'] == len(nonunit)
            and zero['dropped_nonunit_families'] == dict(Counter(map(str, families[nonunit]))), 'OMITTED_COUPLING_FAMILY_CENSUS_MISMATCH')
    models = {}
    for code, unit in enumerate(UNITS, 1):
        spec = zero['models'][unit]
        axes_packet = load_npz(pilot / f'UNIT_{unit}_AXES.npz')
        rows, columns = axes_packet['rows'], axes_packet['columns']
        expected_rows = np.flatnonzero((low == code) & (high == code))
        expected_columns = np.flatnonzero(owners == code)
        require(np.array_equal(rows, expected_rows) and np.array_equal(columns, expected_columns), 'UNIT_LITERAL_ROW_COLUMN_COVER_MISMATCH:' + unit)
        B = sparse.load_npz(pilot / f'UNIT_{unit}_A.npz').tocsr()
        e = load_npz(pilot / f'UNIT_{unit}_DATA.npz')
        compare_sparse(A[rows][:, columns].tocsr(), B)
        for key in ('names', 'lower', 'upper', 'types'):
            require(np.array_equal(e[key], d[key][columns]), 'UNIT_ORIGINAL_COLUMN_DOMAIN_MISMATCH:' + key)
        for key in ('rhs', 'sense', 'row_names'):
            require(np.array_equal(e[key], d[key][rows]), 'UNIT_ORIGINAL_ROW_MISMATCH:' + key)
        require(e['constant'] == 0. and np.isfinite(e['lower']).all() and np.isfinite(e['upper']).all(), 'UNIT_CONSTANT_OR_FINITE_BOX_MISMATCH')
        exact = [coefficient.get(int(col), Fraction(0)) for col in columns]
        require(np.array_equal(e['objective'], np.array([float(value) for value in exact])), 'UNIT_NATIVE_OBJECTIVE_COEFFICIENT_MISMATCH')
        correction, box = Fraction(0), Fraction(0)
        for local, value in enumerate(exact):
            lo, hi = dyadic(e['lower'][local]), dyadic(e['upper'][local])
            require(lo <= hi, 'UNIT_INVALID_ORIGINAL_BOUND')
            delta = value - dyadic(e['objective'][local])
            correction += min(delta * lo, delta * hi)
            box += min(value * lo, value * hi)
        require(correction == Fraction(spec['coefficient_rounding_box_correction']) and box == Fraction(spec['exact_box_fallback']), 'EXACT_OBJECTIVE_BOX_TRANSPORT_MISMATCH')
        column_count = Counter(axis(name)[0] for name in e['names'])
        row_count = Counter(axis(name)[0] for name in e['row_names'])
        require(spec['column_families'] == dict(column_count) and spec['row_families'] == dict(Counter(map(str, e['row_names']))),
                'UNIT_REPORTED_FAMILY_CENSUS_MISMATCH')
        require(row_count['energy_balance'] == 96 and row_count['initial_SOC'] == row_count['terminal_SOC'] == row_count['terminal_location'] == 1,
                'UNIT_FULL_HORIZON_PHYSICAL_ROWS_MISSING')
        require({int(axis(name)[1][-1]) for name in e['names'] if axis(name)[0] == 'SOC'} == set(range(97)), 'UNIT_SOC_0_TO_96_MISSING')
        require({int(axis(name)[1][-1]) for name in e['names'] if axis(name)[0] == 'charge_mode'} == set(range(96)), 'UNIT_MODE_96_SLOTS_MISSING')
        for variable_family in ('Pch', 'Pdis', 'Q'):
            require({int(axis(name)[1][-1]) for name in e['names'] if axis(name)[0] == variable_family} == set(range(96)), 'UNIT_PQ_96_SLOTS_MISSING')
        arc_mask = np.char.startswith(e['names'], 'arc[')
        mode_mask = np.char.startswith(e['names'], 'charge_mode[')
        require(np.all(e['types'][arc_mask | mode_mask] == 'B'), 'INTEGER_ROUTE_OR_MODE_FRACTIONALIZED')
        require(row_count['PCS16'] == 16 * column_count['Pch'] and column_count['Pch'] == column_count['Pdis'] == column_count['Q'], 'UNIT_PCS16_CONNECTIVITY_COVER_MISMATCH')
        require(spec['rows'] == B.shape[0] and spec['columns'] == B.shape[1] and spec['binaries'] == np.sum(e['types'] == 'B')
                and spec['nnz'] == B.nnz, 'UNIT_MODEL_SIZE_MISMATCH')
        for suffix, field in (('AXES', 'axes_sha'), ('A', 'matrix_sha'), ('DATA', 'data_sha')):
            require(sha_file(pilot / f'UNIT_{unit}_{suffix}.npz') == spec[field], 'UNIT_SEALED_FILE_SHA_MISMATCH')
        start = load_npz(pilot / f'UNIT_{unit}_START.npz')['point']
        require(np.array_equal(start, x[columns]), 'UNIT_START_NOT_ORIGINAL_U4_PROJECTION')
        models[unit] = dict(PASS=True, rows=B.shape[0], columns=B.shape[1], binaries=int(np.sum(e['types'] == 'B')),
                            nnz=B.nnz, row_families=dict(row_count), column_families=dict(column_count),
                            integer_original_arcs=int(np.sum(arc_mask)), horizon=96, SOC_slots=97,
                            coefficient_rounding_box_correction=str(correction), exact_box_fallback=str(box))
    return dict(PASS=True, schema='SOURCE18R_PHYSICAL_GLOBAL_LB_INDEPENDENT_V1', phase='Native0',
                Native_optimize_calls=0, Full_MILP_calls=0, base_commit=BASE, case_sha=CASE,
                exact_selected_row_substitution=True, original_response_injection_signs_RHS_and_constants=True,
                original_objective_is_rho_with_zero_constant=True, exact_nonnegative_simplex=True,
                all_single_owner_physical_rows_bounds_and_integer_types_retained=True,
                full_feasible_projection_subset_product=True, removed_coupled_rows_only_enlarge_domain=True,
                terminal_return_origin_condition_added=False, empty_physical_tautologies_checked=len(empty_physical),
                helper_equalities_checked=len(geometry.definitions), selected_helper_equalities_used=len(geometry.used_definitions),
                models=models, fixed_term=str(fixed), UB=float(x[rho]),
                U4_original_maximum_row_violation=float(violation.max(initial=0.)),
                source_records_verified=len(records), weights_sha=sha_file(pilot / 'WEIGHTS.json'),
                independently_recomputed_original_matrix_sha=matrix_digest,
                independently_recomputed_original_domain_sha=domain_digest,
                native0_sha=sha_file(pilot / 'NATIVE0.json'), wall_seconds=time.perf_counter() - started)


def final_certificate(source, pilot):
    proof = native0_certificate(source, pilot)
    previous = load_json(pilot / 'INDEPENDENT_NATIVE0.json')
    require(previous['PASS'] is True and previous['weights_sha'] == proof['weights_sha']
            and previous['native0_sha'] == proof['native0_sha'], 'NATIVE0_APPROVAL_PACKET_DRIFT')
    result = load_json(pilot / 'RESULT.json')
    started = load_json(pilot / 'PILOT_STARTED.json')
    require(started['base'] == BASE and started['runner_sha'] == sha_file(ROOT / 'tools/physical_global_lb_pilot.py')
            and started['verifier_sha'] == sha_file(Path(__file__)), 'PRE_NATIVE_CODE_FREEZE_MISMATCH')
    require(started['units'] == list(UNITS) and started['weights_sha'] == proof['weights_sha']
            and started['workers'] == started['Threads'] == 1 and started['per_unit_TimeLimit'] <= 30.
            and started['cumulative_budget'] <= 120. and started['full_MILP_calls'] == started['weight_iterations'] == started['campaign_calls'] == 0,
            'NATIVE_PILOT_SCOPE_MISMATCH')
    require(not (pilot / 'STOP.json').exists(), 'STOP_LATCH_PRESENT')
    exact_lb, runtime, units = Fraction(proof['fixed_term']), 0., []
    incumbent_replays = {}
    for unit in UNITS:
        directory = pilot / unit
        require(not (directory / 'ERROR.json').exists(), 'UNIT_ERROR_PACKET_PRESENT')
        item, readback = load_json(directory / 'RESULT.json'), load_json(directory / 'READBACK.json')
        begun = load_json(directory / 'STARTED.json')
        require(item['PASS'] is True and item['unit'] == unit and item['optimize_calls'] == 1
                and begun['optimize_calls'] == 1 and begun['Threads'] == 1 and begun['TimeLimit'] <= 30., 'UNIT_RUN_SCOPE_MISMATCH')
        expected_checks = {'CSR_exact', 'RHS_exact', 'senses_exact', 'bounds_exact', 'types_exact',
                           'objective_exact', 'original_minimization', 'ObjCon_exact', 'Threads1', 'TimeLimit'}
        require(readback['PASS'] is True and set(readback['checks']) == expected_checks
                and all(value is True for value in readback['checks'].values()), 'NATIVE_LITERAL_MODEL_READBACK_FAILED')
        require(readback['rows'] == proof['models'][unit]['rows'] and readback['columns'] == proof['models'][unit]['columns']
                and readback['binaries'] == proof['models'][unit]['binaries'], 'NATIVE_MODEL_SIZE_READBACK_MISMATCH')
        require(item['resource_failure'] == [] and item['status'] in (2, 9, 11), 'NATIVE_RESOURCE_OR_UNEXPECTED_STATUS_FAILURE')
        correction = Fraction(proof['models'][unit]['coefficient_rounding_box_correction'])
        require(correction == Fraction(item['coefficient_rounding_box_correction']), 'RESULT_OBJECTIVE_CORRECTION_DRIFT')
        if item['valid_solver_bound']:
            require(item['status'] in (2, 9, 11) and item['bound_source'] == 'CURRENT_NATIVE_GLOBAL_SOLVER_BOUND', 'INVALID_NATIVE_BOUND_STATUS')
            bound, continuous = item['ObjBound'], item['ObjBoundC']
            require(bound is not None and continuous is not None and math.isfinite(bound) and math.isfinite(continuous), 'NATIVE_BOUND_MISSING_OR_NONFINITE')
            selected = min(bound, continuous)
            require(selected == item['selected_solver_bound'] and abs(selected) < 1e100, 'NATIVE_CONSERVATIVE_BOUND_OR_INFINITY_SENTINEL_MISMATCH')
            if item['incumbent'] is not None:
                require(math.isfinite(item['incumbent']) and selected <= item['incumbent'] + 1e-7, 'NATIVE_BOUND_EXCEEDS_INCUMBENT')
            certified = dyadic(selected) + correction
        else:
            require(item['bound_source'] == 'PROVEN_LITERAL_FINITE_BOX_FALLBACK' and item['selected_solver_bound'] is None,
                    'UNKNOWN_OR_UNPROVEN_FALLBACK_BOUND')
            certified = Fraction(proof['models'][unit]['exact_box_fallback'])
        require(certified == Fraction(item['certified_LB_exact']) and item['certified_LB'] == downward(certified), 'UNIT_EXACT_CERTIFIED_BOUND_MISMATCH')
        require(0. <= item['Native_Runtime'] <= 30. and item['peak_RSS_bytes'] > 0 and item['peak_private_commit_bytes'] > 0,
                'NATIVE_RESOURCE_LEDGER_INVALID')
        incumbent_replays[unit] = replay_local_incumbent(pilot, unit, item)
        runtime += item['Native_Runtime']
        exact_lb += certified
        units.append(item)
    require(runtime <= 120. and result['Native_Runtime'] == runtime and result['Native_calls'] == 4
            and result['Full_MILP_calls'] == result['weight_iterations'] == 0 and result['weight_vectors'] == 1,
            'TOTAL_NATIVE_SCOPE_OR_BUDGET_MISMATCH')
    require(result['units'] == units and Fraction(result['Global_LB_exact']) == exact_lb and result['Global_LB'] == downward(exact_lb),
            'GLOBAL_EXACT_AGGREGATION_MISMATCH')
    require(result['fixed_term'] == proof['fixed_term'] and result['peak_RSS_bytes'] == max(item['peak_RSS_bytes'] for item in units)
            and result['peak_private_commit_bytes'] == max(item['peak_private_commit_bytes'] for item in units), 'GLOBAL_FIXED_TERM_OR_MEMORY_LEDGER_MISMATCH')
    ub = dyadic(proof['UB'])
    require(exact_lb <= ub and dyadic(result['UB']) == ub, 'GLOBAL_BOUND_OR_UB_ORDER_MISMATCH')
    gap = (ub - exact_lb) / ub
    require(result['Gap_percent'] == float(100 * gap) and Fraction(result['target_LB_exact']) == Fraction(97, 100) * ub,
            'GLOBAL_GAP_OR_TARGET_MISMATCH')
    verdict = 'VALID_GLOBAL_LB_MATERIAL' if gap <= Fraction(3, 100) else 'VALID_GLOBAL_LB_NONMATERIAL'
    require(result['classification'] == verdict, 'GLOBAL_MATERIALITY_CLASSIFICATION_MISMATCH')
    ledger = load_json(pilot / 'NATIVE_LEDGER.json')
    require(ledger['Units'] == units and ledger['Native_Runtime'] == runtime and ledger['optimize_calls'] == 4
            and ledger['workers'] == ledger['Threads'] == 1 and ledger['full_MILP_calls'] == 0, 'NATIVE_LEDGER_MISMATCH')
    proof.update(phase='Final', classification=verdict, Global_LB_exact=str(exact_lb), Global_LB=downward(exact_lb),
                 Gap_percent=float(100 * gap), Native_Runtime=runtime, Native_calls_audited=4,
                 local_incumbent_replays=incumbent_replays,
                 independently_aggregated_native_global_bounds=True,
                 mathematical_statement='For each FULL-feasible x, rho(x) >= sum_k w_k b_k + sum_m c_m^T x_m >= fixed_term + sum_m certified_LB_m.',
                 solver_bound_contract='Native minimization B&B global bounds are trusted under Gurobi numerical contract; all model coefficients, objective transport, omitted constraints, and sum are independently checked exactly.',
                 proof_scope='Original Source18r stored FULL model; original feasible projection is included in the product of literal single-owner physical domains.')
    return proof


def self_test():
    """Small semantic corruption tests, without a solver or source artifacts."""
    d = dict(names=np.array(['Pch[MESS01,IDC01,0]', 'Pdis[MESS01,IDC01,0]', 'injection_P[IDC01,0]',
                             'response_line_P[0,3]', 'rho_max']),
             row_names=np.array(['injection_P_binding', 'response_line_P_binding[0,3]', 'line_thermal_face[0,3,0]']),
             rhs=np.array([0., 7., -2.]), sense=np.array(['=', '=', '<']))
    A = sparse.csr_matrix(np.array([[1., -1., 1., 0., 0.], [0., 0., -.25, 1., 0.], [0., 0., 0., .5, -1.]]))
    geometry = OriginalGeometry(A, d)
    constant, terms = geometry.thermal(2, 4)
    require(constant == Fraction(11, 2) and terms == {0: Fraction(-1, 8), 1: Fraction(1, 8)}, 'SELF_TEST_EXACT_SUBSTITUTION_FAILED')
    corruptions = []
    wrong_axis = {key: value.copy() for key, value in d.items()}
    wrong_axis['row_names'][1] = 'response_line_P_binding[1,3]'
    corruptions.append((A, wrong_axis))
    wrong_sign = A.copy()
    wrong_sign[0, 0] = -1.
    corruptions.append((wrong_sign, d))
    wrong_rhs = {key: value.copy() for key, value in d.items()}
    wrong_rhs['rhs'][0] = 1.
    corruptions.append((A, wrong_rhs))
    for matrix, packet in corruptions:
        try:
            OriginalGeometry(matrix, packet)
        except ValueError:
            continue
        raise ValueError('SELF_TEST_CORRUPTION_WAS_NOT_REJECTED')
    print('Independent verifier self-test PASS: exact signs/constants and three corruptions rejected.', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--native0', action='store_true')
    mode.add_argument('--final', action='store_true')
    mode.add_argument('--self-test', action='store_true')
    parser.add_argument('--source', type=Path, default=DEFAULT_SOURCE)
    parser.add_argument('--pilot', type=Path, default=DEFAULT_PILOT)
    args = parser.parse_args()
    if args.self_test:
        self_test()
    else:
        output = args.pilot / ('INDEPENDENT_CERTIFICATE.json' if args.final else 'INDEPENDENT_NATIVE0.json')
        try:
            certificate = final_certificate(args.source, args.pilot) if args.final else native0_certificate(args.source, args.pilot)
        except BaseException as error:
            save_json(output, dict(PASS=False, classification='GLOBAL_LB_NOT_CERTIFIED', Native_optimize_calls=0,
                                   error=repr(error), traceback=traceback.format_exc()))
            raise
        save_json(output, certificate)
        print('Independent ' + certificate['phase'] + ' PASS', certificate.get('classification', ''), flush=True)
