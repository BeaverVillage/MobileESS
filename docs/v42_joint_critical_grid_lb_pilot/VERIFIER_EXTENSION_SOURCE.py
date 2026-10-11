"""Independent Native0/final audit of the four-MESS critical-grid pilot.

No production builder import, Gurobi import, model regeneration, or optimization
is performed. Exact arithmetic interprets all stored binary64 data as dyadics.
The exact domain/rounding certificate is separate from the native solver's
numerical branch-and-bound contract; no exact B&B trace is claimed.
"""
from __future__ import annotations

import argparse
from collections import Counter
from fractions import Fraction
import gc
import hashlib
import json
import math
from pathlib import Path
import re
import time
import traceback

import numpy as np
from scipy import sparse

ROOT = Path(__file__).resolve().parents[2]
SOURCE = Path(r'D:\v42_dense_response_development_repair_20261011\dates\B2\2025-05-01\attempts\native0_restored\output')
OUT = ROOT / 'docs/v42_joint_critical_grid_lb_pilot'
PREVIOUS = ROOT / 'docs/v42_physical_global_lb_pilot'
SOURCE18R = '497609b46faa14ea7e32a9483a333ab32fd264ef'
PARENT = '9383a99f1bdcabbd49c79b3ad9f9ee36d523868a'
CASE = '34c0efffa9c05397552fb167667c0bbfe2f35cec89801a3169c00c64fe77f292'
C3A_MATRIX = 'd67a073fc06a7537fd585de8ff786a01a854df5ee4f52be17f39fa66da6292a9'
C3A_DOMAIN = '821842e0ef3a83df4bb9a6466a1f7a5e952710dd2f695801b1de168becd4d6e5'
WEIGHTS = '61c84c4bb36b1a35b7f8fd1ad7fec5669cf34b082a3a24cc5069b535d2edde62'
UB = 0.6760534504652341
PR209_LB = 0.11666465693783702
FULL_BOUND = 0.28940049108548904
UNITS = ('MESS01', 'MESS02', 'MESS03', 'MESS04')
COL_FAMILIES = {'route_flow', 'node_activity', 'charge_mode', 'SOC', 'Pch', 'Pdis', 'Q'}
ROW_FAMILIES = {'flow', 'node_activity_link', 'energy_balance', 'PCS16',
                'connected_Pch', 'connected_Pdis', 'no_simultaneous_charge',
                'no_simultaneous_discharge'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def save_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2,
                                   allow_nan=False) + '\n', encoding='utf-8')
    temporary.replace(path)


def sha_file(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        while block := stream.read(1024 * 1024):
            result.update(block)
    return result.hexdigest()


def load_npz(path):
    with np.load(path, allow_pickle=False) as packet:
        return {key: packet[key].copy() for key in packet.files}


def digests(matrix, data):
    matrix_hash = hashlib.sha256(np.asarray(matrix.shape, dtype='<i8').tobytes())
    for value in (matrix.indptr, matrix.indices, matrix.data):
        matrix_hash.update(value.dtype.str.encode('ascii'))
        matrix_hash.update(np.ascontiguousarray(value).tobytes())
    data_hash = hashlib.sha256()
    for key in sorted(data):
        value = np.asarray(data[key])
        data_hash.update(key.encode())
        data_hash.update(value.dtype.str.encode())
        data_hash.update(np.asarray(value.shape, dtype='<i8').tobytes())
        data_hash.update(value.tobytes())
    return matrix_hash.hexdigest(), data_hash.hexdigest()


def canonical_data(data):
    """Accept the independent export's explicit or original Source key names."""
    alternatives = {'c': ('c', 'objective'), 'lb': ('lb', 'lower'),
                    'ub': ('ub', 'upper'), 'vtypes': ('vtypes', 'types'),
                    'senses': ('senses', 'sense')}
    answer = dict(data)
    for target, choices in alternatives.items():
        found = [key for key in choices if key in data]
        require(len(found) == 1, f'MISSING_OR_AMBIGUOUS_DATA_KEY_{target}')
        answer[target] = data[found[0]]
    return answer


def axis(name):
    match = re.fullmatch(r'([^\[]+)(?:\[([^\]]+)\])?', str(name))
    require(match is not None, 'INVALID_AXIS_NAME')
    return match[1], [] if match[2] is None else match[2].split(',')


def dyadic(value):
    value = float(value)
    require(math.isfinite(value), 'NONFINITE_DYADIC')
    return Fraction(value)


def upwards(value):
    answer = float(value)
    require(math.isfinite(answer), 'NONFINITE_OUTWARD_RHS')
    if Fraction(answer) < value:
        answer = float(np.nextafter(answer, np.inf))
    return answer


def provenance(source, previous):
    identity = load_json(source / 'SCIENTIFIC_CASE_IDENTITY.json')
    require(identity['case_sha'] == CASE, 'SCIENTIFIC_CASE_IDENTITY_CHANGED')
    require(identity['arm'] == 'B2' and identity['day'] == '2025-05-01', 'WRONG_CASE')
    equivalence = load_json(source / 'ORIGINAL_DOMAIN_EQUIVALENCE.json')
    exact = load_json(source / 'CURRENT_EXACT_C3A_PROOF.json')
    require(equivalence['PASS'] and equivalence['integer_and_full_LP_domains_identical'],
            'SAVED_ORIGINAL_COMPACT_EQUIVALENCE_FAILED')
    require(exact['PASS'] and exact['integer_and_full_LP_domains_identical'],
            'SAVED_EXACT_C3A_EQUIVALENCE_FAILED')
    require(exact['selected_matrix_SHA256'] == C3A_MATRIX, 'SAVED_C3A_PROOF_WRONG_MATRIX')
    require(exact['columns_eliminated'] == 0, 'UNEXPECTED_C3A_COLUMN_ELIMINATION')
    require(equivalence['exact_aliases_checked'] == 14618, 'STATIC_ALIAS_PROOF_CHANGED')
    source_records = identity['transport_authority']['sources']
    for record in source_records.values():
        require(sha_file(record['path']) == record['sha256'], 'SOURCE18R_SOURCE_BYTE_CHANGE')
    old = load_json(previous / 'INDEPENDENT_CERTIFICATE.json')
    require(old['PASS'] and old['case_sha'] == CASE and old['base_commit'] == SOURCE18R,
            'PR209_INDEPENDENT_PROOF_FAILED')
    for key in ('exact_selected_row_substitution',
                'original_response_injection_signs_RHS_and_constants',
                'original_objective_is_rho_with_zero_constant',
                'exact_nonnegative_simplex', 'all_single_owner_physical_rows_bounds_and_integer_types_retained',
                'full_feasible_projection_subset_product'):
        require(old[key], f'PR209_PROOF_FLAG_FAILED_{key}')
    grid = load_json(previous / 'GRID_PROVENANCE_AUDIT.json')
    require(grid['PASS'] and grid['case_sha'] == CASE and grid['source18r'] == SOURCE18R,
            'PR209_GRID_PROVENANCE_CHANGED')
    require(grid['fixed_AIDC_PCC_controls_exact'] and
            grid['stored_FULL_and_exact_WEIGHTS_are_authority'], 'K16_FIXED_CONTROLS_PROOF_FAILED')
    require(sha_file(previous / 'WEIGHTS.json') == WEIGHTS, 'PR209_K16_WEIGHTS_BYTES_CHANGED')
    return {'case_sha': CASE, 'source18r': SOURCE18R, 'parent_PR209': PARENT,
            'source_records_verified': len(source_records),
            'weights_sha256': WEIGHTS,
            'reused_saved_exact_proofs': {name: sha_file(source / name) for name in (
                'ORIGINAL_DOMAIN_EQUIVALENCE.json', 'CURRENT_EXACT_C3A_PROOF.json',
                'CURRENT_C2_ALIASES.json', 'CURRENT_C2_ROW_PROOFS.json',
                'CURRENT_SECURITY_PRE_C2_BOUND_CERTIFICATES.json')},
            'PR209_independent_certificate_sha256': sha_file(previous / 'INDEPENDENT_CERTIFICATE.json'),
            'PR209_grid_provenance_sha256': sha_file(previous / 'GRID_PROVENANCE_AUDIT.json'),
            'full_model_regenerations': 0, 'FULL_matrix_loaded': False}


def native0(source, previous, out):
    result = {'schema': 'V42_JOINT_CRITICAL_GRID_INDEPENDENT_V1', 'phase': 'Native0',
              'Native_optimize_calls': 0, 'Gurobi_imported': False,
              'provenance': provenance(source, previous)}
    relation = load_json(out/'PHYSICAL_RELATION_AUDIT.json')
    require(relation['PASS'] and relation['native_optimize_calls'] == 0 and
            relation['full_matrix_loaded'] is False, 'INDEPENDENT_PHYSICAL_RELATION_AUDIT_FAILED')
    require(relation['retained_original_physical_rows_exactly_replayed'] == 134514 and
            relation['retained_node_activity_links_exactly_replayed'] == 8746 and
            relation['all_96_slots_retained'] and
            sum(unit['original_energy_slots_exactly_replayed'] for unit in relation['per_unit']) == 384,
            'ORIGINAL_COMPACT_PHYSICAL_TRANSPORT_CENSUS_MISMATCH')
    require(relation['C3A_deleted_physical_rows_exact_Farkas_or_flow_sum_replayed'] == 71540 and
            relation['C2_deleted_original_physical_definitions_exact_tautologies'] == 8 and
            relation['C2_deleted_node_links_exact_tautologies'] == 288 and
            relation['C2_deleted_node_links_exact_retained_flow_implications'] == 4,
            'DELETED_PHYSICAL_ROW_EXACT_PROOF_CENSUS_MISMATCH')
    result['physical_relation_audit_sha256'] = sha_file(out/'PHYSICAL_RELATION_AUDIT.json')
    A = sparse.load_npz(source / 'C3A_A.npz').tocsr()
    raw = load_npz(source / 'C3A_DATA.npz')
    matrix_sha, domain_sha = digests(A, raw)
    require((matrix_sha, domain_sha) == (C3A_MATRIX, C3A_DOMAIN), 'SOURCE18R_C3A_DIGEST_MISMATCH')
    d = canonical_data(raw)
    row_families = [axis(value)[0] for value in d['row_names']]
    col_families = [axis(value)[0] for value in d['names']]
    expected_rows = np.flatnonzero(np.isin(row_families, list(ROW_FAMILIES)))
    physical_cols = np.flatnonzero(np.isin(col_families, list(COL_FAMILIES)))
    source_rho = np.flatnonzero(d['names'] == 'rho_max')
    require(len(source_rho) == 1, 'RHO_NOT_UNIQUE')
    expected_cols = np.concatenate((physical_cols, source_rho))
    exported_axes = load_npz(out / 'JOINT_AXES.npz')
    require(np.array_equal(exported_axes['rows'], expected_rows), 'PHYSICAL_ROW_SELECTION_MISMATCH')
    require(np.array_equal(exported_axes['columns'], expected_cols), 'PHYSICAL_COLUMN_SELECTION_MISMATCH')
    require(len(expected_rows) == 143260 and len(physical_cols) == 244264, 'PHYSICAL_CENSUS_CHANGED')
    require(relation['physical_rows'] == len(expected_rows) and
            relation['physical_columns'] == len(physical_cols) and
            relation['physical_binary'] == 9322, 'RELATION_PHYSICAL_CENSUS_MISMATCH')
    source_physics = A[expected_rows][:, expected_cols].tocsr()
    del A
    gc.collect()
    J = sparse.load_npz(out / 'JOINT_A.npz').tocsr()
    raw_joint = load_npz(out / 'JOINT_DATA.npz')
    j = canonical_data(raw_joint)
    require(J.shape == (143276, 244265), 'JOINT_DIMENSIONS_CHANGED')
    p = len(expected_rows)
    actual_physics = J[:p]
    require(np.array_equal(actual_physics.indptr, source_physics.indptr) and
            np.array_equal(actual_physics.indices, source_physics.indices) and
            np.array_equal(actual_physics.data, source_physics.data), 'PHYSICAL_CSR_NOT_EXACT')
    for key in ('names', 'lb', 'ub', 'vtypes'):
        require(np.array_equal(j[key], d[key][expected_cols]), f'PHYSICAL_{key.upper()}_CHANGED')
    for key in ('rhs', 'senses', 'row_names'):
        require(np.array_equal(j[key][:p], d[key][expected_rows]), f'PHYSICAL_{key.upper()}_CHANGED')
    rho = len(physical_cols)
    require(j['names'][rho] == 'rho_max' and j['lb'][rho] == 0 and
            j['ub'][rho] == 1 and j['vtypes'][rho] == 'C', 'RHO_DOMAIN_CHANGED')
    objective = np.zeros(J.shape[1]); objective[rho] = 1.
    require(np.array_equal(j['c'], objective) and float(j['constant']) == 0,
            'JOINT_OBJECTIVE_NOT_MIN_RHO_ZERO_CONSTANT')
    require(np.all(np.isfinite(j['lb'])) and np.all(np.isfinite(j['ub'])) and
            np.all(j['lb'] <= j['ub']), 'INVALID_FINITE_PHYSICAL_BOUNDS')
    binaries = int(np.count_nonzero(j['vtypes'] == 'B'))
    require(binaries == 9322 and binaries <= 10000 and J.shape[0] <= 300000 and J.nnz <= 3000000,
            'SIZE_GATE_FAILED')
    physical_set = set(physical_cols.tolist())
    owner = []
    for value in j['names'][:rho]:
        family, coordinates = axis(value)
        require(coordinates[0] in UNITS, 'INVALID_PHYSICAL_OWNER')
        owner.append(UNITS.index(coordinates[0]))
        if family == 'route_flow':
            require(j['vtypes'][len(owner)-1] == 'C', 'UNEXPECTED_CONTINUOUS_ROUTE_TYPE')
    owner = np.asarray(owner)
    for row in range(p):
        columns = actual_physics.indices[actual_physics.indptr[row]:actual_physics.indptr[row+1]]
        require(rho not in columns and len(np.unique(owner[columns])) == 1,
                'PHYSICAL_ROW_HAS_CROSS_VEHICLE_OR_GRID_COUPLING')
    aliases = load_json(source / 'CURRENT_C2_ALIASES.json')
    fixed_soc = [item for item in aliases if axis(item['name'])[0] == 'SOC']
    require(len(fixed_soc) == 8 and all(item['kind'] == 'FIXED_CONSTANT' and
            item['constant'] == 760. and not item['terms'] for item in fixed_soc),
            'INITIAL_TERMINAL_SOC_ALIAS_CHANGED')
    for unit in UNITS:
        unit_columns = [axis(value) for value in j['names'][:rho] if f'[{unit},' in str(value)]
        modes = [int(coordinates[-1]) for family, coordinates in unit_columns if family == 'charge_mode']
        soc = [int(coordinates[-1]) for family, coordinates in unit_columns if family == 'SOC']
        require(sorted(modes) == list(range(96)) and sorted(soc) == list(range(1, 96)),
                'FULL_96_SLOT_MODES_OR_SOC_REMOVED')
    c2_axes = load_npz(source / 'CURRENT_C2_AXES.npz')['columns']
    c3a_axes = load_npz(source / 'CURRENT_C3A_AXES.npz')['columns']
    require(np.array_equal(c3a_axes, np.arange(len(c2_axes))), 'C3A_IS_NOT_SAME_C2_COLUMN_AXIS')
    original_to_joint = {int(c2_axes[c]): local for local, c in enumerate(expected_cols)}
    original_names = None
    with np.load(source / 'FULL_DATA.npz', allow_pickle=False) as packet:
        original_names = packet['names']
    k16 = load_json(out / 'K16_EXACT_ROWS.json')
    old_rows = load_json(previous / 'WEIGHTS.json')['rows']
    require(k16['physicalrowcount'] == p and len(k16['rows']) == len(old_rows) == 16,
            'K16_ROWS_NOT_SEPARATE_SIXTEEN')
    rounding_rows, maximum_loss = [], Fraction(0)
    for k, (record, original) in enumerate(zip(k16['rows'], old_rows)):
        require(record['original_row'] == original['row'] and record['name'] == original['name'],
                'K16_ORIGINAL_ROW_IDENTITY_CHANGED')
        require(record['rho_column'] == rho and Fraction(record['b']) == Fraction(original['b']),
                'K16_RHO_OR_FIXED_TERM_CHANGED')
        expected_terms = {}
        for original_column, value in original['terms'].items():
            column = int(original_column)
            require(column in original_to_joint, 'K16_ORIGINAL_COLUMN_ELIMINATED')
            target = original_to_joint[column]
            require(j['names'][target] == original_names[column] and
                    axis(j['names'][target])[0] in {'Pch', 'Pdis', 'Q'}, 'K16_PQ_AXIS_MISMATCH')
            expected_terms[target] = Fraction(value)
        exported_terms = {int(c): Fraction(value) for c, value in record['terms'].items()}
        require(exported_terms == expected_terms, 'K16_EXACT_COEFFICIENT_CHANGED')
        native = J.getrow(p+k)
        actual = dict(zip(map(int, native.indices), map(float, native.data)))
        require(set(actual) == set(expected_terms) | {rho} and actual[rho] == -1.,
                'K16_NATIVE_COEFFICIENT_SUPPORT_OR_RHO_CHANGED')
        error, reverse_error = Fraction(0), Fraction(0)
        for column, coefficient in expected_terms.items():
            stored = actual[column]
            require(stored == float(coefficient) and stored != 0., 'K16_TINY_COEFFICIENT_DROPPED_OR_CHANGED')
            difference = Fraction(stored) - coefficient
            error += max(difference * dyadic(j['lb'][column]), difference * dyadic(j['ub'][column]))
            reverse_error += max(-difference * dyadic(j['lb'][column]), -difference * dyadic(j['ub'][column]))
        target_rhs = -Fraction(original['b']) + error
        rhs = dyadic(j['rhs'][p+k])
        require(j['senses'][p+k] == '<' and j['row_names'][p+k] == original['name'],
                'K16_NATIVE_SENSE_OR_NAME_CHANGED')
        require(rhs >= target_rhs and float(rhs) == upwards(target_rhs), 'K16_RHS_NOT_MINIMAL_OUTWARD')
        require(float(record['native_rhs']) == float(rhs) and
                Fraction(record['error_upper_bound']) == error and
                Fraction(record['rhs_outward_extra']) == rhs - target_rhs,
                'K16_ROUNDING_CERTIFICATE_MISMATCH')
        loss = rhs + Fraction(original['b']) + reverse_error
        maximum_loss = max(maximum_loss, abs(loss))
        rounding_rows.append({'name': original['name'], 'terms': len(expected_terms),
                              'error_upper_bound': str(error), 'rhs_outward_extra': str(rhs-target_rhs),
                              'exact_FULL_feasible_points_remain_native_feasible': True})
    require(sum(Fraction(item['weight']) for item in old_rows) == 1 and
            all(Fraction(item['weight']) == Fraction(1, 16) for item in old_rows),
            'PR209_WEIGHT_SIMPLEX_CHANGED')
    start = load_npz(out / 'JOINT_START.npz')
    require(set(start) == {'x'}, 'JOINT_START_SCHEMA')
    saved_start = load_npz(source / 'FRESH_U4/RAW_00.npz')['point']
    require(np.array_equal(start['x'], saved_start[expected_cols]), 'JOINT_START_NOT_UNMODIFIED_U4_PROJECTION')
    replay = load_json(source / 'FRESH_U4/RAW_00.REPLAY.json')
    require(replay['PASS'] and replay['case_sha'] == CASE and
            replay['strict_raw_C3A_and_FULL_integer_and_binary_pattern_exact'] and
            sha_file(source / 'FRESH_U4/RAW_00.npz') == replay['point_file_sha256'], 'U4_SAVED_FULL_REPLAY_FAILED')
    require(float(saved_start[int(source_rho[0])]) == UB, 'U4_RHO_OR_UB_CHANGED')
    residual = J @ start['x'] - j['rhs']
    violation = np.where(j['senses'] == '=', abs(residual),
                         np.where(j['senses'] == '<', residual, -residual))
    row_violation = float(max(0., np.max(violation)))
    bound_violation = float(max(0., np.max(j['lb']-start['x']), np.max(start['x']-j['ub'])))
    integer = np.flatnonzero(j['vtypes'] == 'B')
    integer_violation = float(np.max(abs(start['x'][integer]-np.rint(start['x'][integer]))))
    require(row_violation <= 1e-8 and bound_violation <= 1e-8 and integer_violation == 0.,
            'JOINT_U4_PROJECTED_REPLAY_FAILED')
    joint_matrix_sha, joint_domain_sha = digests(J, raw_joint)
    result.update({'PASS': True, 'saved_C3A_actual_matrix_sha256': matrix_sha,
                   'saved_C3A_actual_domain_sha256': domain_sha,
                   'joint_actual_matrix_sha256': joint_matrix_sha,
                   'joint_actual_domain_sha256': joint_domain_sha,
                   'all_physical_C3A_rows_and_columns_retained_exactly': True,
                   'C3A_deleted_physical_rows_exact_Farkas_or_flow_sum_replayed': 71540,
                   'C2_deleted_original_physical_definitions_exact_tautologies': 8,
                   'C2_deleted_node_links_exact_tautologies': 288,
                   'C2_deleted_node_links_exact_retained_flow_implications': 4,
                   'full_C3A_CSR_disposed_before_Joint_CSR_load': True,
                   'all_physical_bounds_and_types_unchanged_from_certified_C3A': True,
                   'physical_rows_are_single_vehicle': True,
                   'new_binaries_added': 0, 'routes_arbitrarily_fixed_or_removed': False,
                   'horizon': 96, 'SOC_points': '95 retained + 2 exact endpoint aliases per MESS',
                   'PCS16': '10 retained faces per block; 6 exact C3A Farkas redundancies removed',
                   'K16_are_separate_same_rho_constraints': True,
                   'FULL_projection_subset_exact_Joint_subset_native_rounded_Joint': True,
                   'exact_PR209_weighted_optimum_le_exact_Joint_optimum': True,
                   'TIME_LIMIT_solver_bound_may_be_below_PR209_LB': True,
                   'terminal_return_origin_condition_added': False,
                   'rounding_rows': rounding_rows,
                   'maximum_native_rounding_loss_conservative_diagnostic': str(maximum_loss),
                   'dimensions': {'rows': J.shape[0], 'columns': J.shape[1],
                                  'binaries': binaries, 'nnz': int(J.nnz)},
                   'physical_row_families': dict(Counter(np.asarray(row_families)[expected_rows])),
                   'physical_column_families': dict(Counter(np.asarray(col_families)[physical_cols])),
                   'U4_replay': {'row_violation': row_violation, 'bound_violation': bound_violation,
                                 'binary_violation': integer_violation, 'rho': UB},
                   'file_sha256': {name: sha_file(out/name) for name in (
                       'JOINT_A.npz', 'JOINT_DATA.npz', 'JOINT_AXES.npz',
                       'JOINT_START.npz', 'K16_EXACT_ROWS.json')},
                   'exact_BB_trace_certificate': False,
                   'proof_scope': 'Exact stored-data inclusion and conservative floating coefficient transport; numerical U4 replay only.'})
    del raw, d, source_physics, J, actual_physics, raw_joint, j, original_names
    gc.collect()
    return result


def final(out):
    """Audit the one numerical solver bound against the frozen exact domain."""
    prior = load_json(out / 'INDEPENDENT_NATIVE0.json')
    require(prior['PASS'] and prior['phase'] == 'Native0', 'INDEPENDENT_NATIVE0_NOT_PASS')
    relation = load_json(out/'PHYSICAL_RELATION_AUDIT.json')
    require(relation['PASS'] and sha_file(out/'PHYSICAL_RELATION_AUDIT.json') ==
            prior['physical_relation_audit_sha256'], 'PHYSICAL_RELATION_PROOF_CHANGED_AFTER_NATIVE0')
    native0_record = load_json(out / 'NATIVE0.json')
    require(native0_record['PASS'], 'BUILDER_NATIVE0_NOT_PASS')
    for name, expected in prior['file_sha256'].items():
        require(sha_file(out/name) == expected, 'MODEL_ARTIFACT_CHANGED_SINCE_INDEPENDENT_NATIVE0')
        require(native0_record['files'][name] == expected, 'BUILDER_INDEPENDENT_ARTIFACT_SHA_MISMATCH')
    result = load_json(out / 'RESULT.json')
    if result['classification'] == 'JOINT_MEMORY_OR_SIZE_GATE_STOP':
        require(result['Native_optimize_calls'] == 0 and not (out/'PILOT_STARTED.json').exists(),
                'STOP_CLASSIFICATION_WITH_NATIVE_CALL')
        return {'PASS': False, 'phase': 'Final',
                'classification': 'JOINT_MEMORY_OR_SIZE_GATE_STOP',
                'Native_calls_audited': 0, 'Global_LB': None,
                'reason': result.get('reason'),
                'exact_model_and_rounding_audit_PASS': True,
                'independent_native0_sha256': sha_file(out/'INDEPENDENT_NATIVE0.json')}
    hold = load_json(out/'PRE_RUN_RESOURCE_HOLD.json')
    require(hold['PASS'] and all(hold['checks'].values()), 'PRE_RUN_HOLD_OR_OTHER_WORKER_GATE_FAILED')
    peers = load_json(out/'PRE_OPTIMIZE_PEERS.json')
    require(peers['PASS'] and not peers['errors'] and not peers['heavy_peers'],
            'FRESH_PRE_OPTIMIZE_CONCURRENT_WORKER_GATE_FAILED')
    readback = load_json(out/'NATIVE_READBACK.json')
    require(readback['PASS'] and all(readback['checks'].values()), 'NATIVE_MODEL_READBACK_FAILED')
    checks = {'matrix', 'rhs', 'senses', 'lower', 'upper', 'types', 'objective',
              'ObjCon', 'ModelSense', 'Rows', 'Columns', 'Binary', 'NNZ'}
    require(checks <= set(readback['checks']), 'NATIVE_READBACK_REQUIRED_CHECK_ABSENT')
    require(readback['matrix_sha'] == prior['joint_actual_matrix_sha256'], 'NATIVE_ACTUAL_MATRIX_SHA_MISMATCH')
    parameters = {'Threads': 1, 'TimeLimit': 90., 'MIPGap': .03, 'MIPFocus': 3,
                  'FeasibilityTol': 1e-8, 'IntFeasTol': 1e-8, 'OptimalityTol': 1e-8}
    for key, expected in parameters.items():
        require(readback['parameters'][key] == expected, f'NATIVE_PARAMETER_DRIFT_{key}')
    latch = load_json(out/'PILOT_STARTED.json')
    require(latch['Native_optimize_max'] == 1 and
            result['Native_optimize_calls'] == 1 and
            latch['parameters'] == readback['parameters'], 'EXCLUSIVE_SINGLE_NATIVE_CALL_LATCH_FAILED')
    require(latch['files'] == native0_record['files'], 'LATCH_FROZEN_MODEL_ARTIFACT_DRIFT')
    for key in ('full_MILP_calls', 'separate_LP_calls', 'campaign_calls'):
        require(result[key] == 0, f'UNAUTHORIZED_EXTRA_SOLVER_OR_CAMPAIGN_{key}')
    require(result['exact_numeric_BB_certificate'] is False and result['incumbent_is_full_UB'] is False,
            'NUMERICAL_BOUND_OR_REDUCED_INCUMBENT_SCOPE_MISLABELLED')
    admission = load_json(out/'MEMORY_ADMISSION.json')
    require(admission['PASS'], 'POST_BUILD_MEMORY_ADMISSION_FAILED')
    require(admission['RAM_reserve_bytes'] == 4*1024**3 and
            admission['commit_reserve_bytes'] == 6*1024**3 and
            admission['estimated_additional_bytes'] == max(2*1024**3,
                4*admission['observed_model_build_private_growth_bytes']),
            'POST_BUILD_MEMORY_RESERVES_CHANGED')
    sample = admission['sample']['system']
    require(sample['RAM_available'] >= admission['RAM_reserve_bytes'] + admission['estimated_additional_bytes'] and
            sample['Commit_available'] >= admission['commit_reserve_bytes'] + admission['estimated_additional_bytes'],
            'POST_BUILD_AVAILABLE_MEMORY_HEADROOM_FAILED')
    trace = load_json(out/'MEMORY_TRACE.json')
    samples = trace['samples']
    require(len(samples) >= 2, 'NO_NATIVE_MEMORY_MONITOR_TRACE')
    for key, field, reducer in (
        ('minimum_RAM_available', 'RAM_available', min),
        ('minimum_commit_available', 'Commit_available', min)):
        require(result[key] == reducer(item['system'][field] for item in samples),
                'NATIVE_SYSTEM_MEMORY_REDUCTION_MISMATCH')
    require(result['peak_process_RSS_bytes'] == max(item['Peak_RSS_bytes'] for item in samples) and
            result['peak_private_commit_bytes'] == max(item['Peak_Private_Commit_bytes'] or
                item['Private_Commit_bytes'] for item in samples) and
            result['peak_sampled_private_commit_bytes'] == max(item['Private_Commit_bytes'] for item in samples),
            'NATIVE_PROCESS_MEMORY_REDUCTION_MISMATCH')
    require(bool(trace['unsafe_samples']) == result['memory_stop'], 'MEMORY_STOP_TRACE_MISMATCH')
    runtime = float(result['Runtime'])
    require(math.isfinite(runtime) and runtime >= 0, 'NATIVE_RUNTIME_INVALID')
    log = (out/'NATIVE.log').read_text(encoding='utf-8', errors='replace')
    completed = any(line.startswith('Root relaxation:') and 'objective' in line
                    for line in log.splitlines())
    require(completed == result['root_relaxation_completed'], 'ROOT_COMPLETION_REPORT_MISMATCH')
    summaries = [line for line in log.splitlines() if line.startswith((
        'Presolve removed', 'Presolved:', 'Root relaxation:', 'Explored ', 'User MIP start'))]
    require(summaries == result['presolve_summary'], 'PRESOLVE_OR_ROOT_LOG_SUMMARY_MISMATCH')
    numeric_failure = any(message.lower() in log.lower() for message in (
        'Numerical trouble', 'Out of memory', 'Numeric error'))
    bound = result.get('ObjBound')
    valid = (result['Status'] in (2, 9, 11) and bound is not None and
             math.isfinite(float(bound)) and abs(float(bound)) < 1e100 and
             not result['callback_errors'] and result['optimize_error'] is None and
             not numeric_failure)
    require(result['numerical_bound_candidate_valid'] == valid, 'SOLVER_BOUND_VALIDITY_MISMATCH')
    if not valid:
        require(result['classification'] == 'JOINT_LB_NOT_CERTIFIED', 'INVALID_BOUND_CLASSIFICATION')
        return {'PASS': False, 'phase': 'Final', 'classification': 'JOINT_LB_NOT_CERTIFIED',
                'Global_LB': None, 'Native_calls_audited': 1,
                'exact_model_and_rounding_audit_PASS': True,
                'solver_bound_valid': False, 'numeric_failure_in_log': numeric_failure,
                'solver_status': result['Status'], 'reported_ObjBound': bound,
                'independent_native0_sha256': sha_file(out/'INDEPENDENT_NATIVE0.json')}
    bound = float(bound)
    require(bound <= UB + 1e-8, 'SOLVER_BOUND_EXCEEDS_VERIFIED_FULL_UB')
    classification = ('JOINT_LB_VALID_MATERIAL' if bound >= FULL_BOUND+.001
                      else 'JOINT_LB_VALID_NONMATERIAL')
    require(result['classification'] == classification, 'MATERIAL_CLASSIFICATION_THRESHOLD_MISMATCH')
    require(result['UB'] == UB and result['PR209_LB'] == PR209_LB and
            result['Source18r_Full_ObjBound'] == FULL_BOUND and result['goal_LB'] == UB*.97,
            'COMPARISON_REFERENCE_CHANGED')
    gap = (UB-bound)/UB
    require(result['global_gap'] == gap and result['delta_PR209'] == bound-PR209_LB and
            result['delta_Source18r_Full'] == bound-FULL_BOUND and
            result['goal_3percent'] == (bound >= UB*.97), 'GLOBAL_GAP_OR_COMPARISON_MISMATCH')
    incumbent_replay = None
    if result['SolCount']:
        require(result['ObjVal'] is not None and math.isfinite(result['ObjVal']) and
                result['ObjVal'] >= bound-1e-8, 'INCUMBENT_AND_BOUND_ORDER_INVALID')
        require(result['incumbent_joint_replay']['full_feasibility_tested'] is False and
                result['incumbent_joint_replay']['promoted_to_UB'] is False, 'REDUCED_INCUMBENT_USED_AS_FULL_UB')
        J = sparse.load_npz(out/'JOINT_A.npz').tocsr()
        d = canonical_data(load_npz(out/'JOINT_DATA.npz'))
        point = load_npz(out/'JOINT_INCUMBENT.npz')['x']
        require(len(point) == J.shape[1] and np.all(np.isfinite(point)), 'REDUCED_INCUMBENT_INVALID_VECTOR')
        residual = J@point-d['rhs']
        violation = np.where(d['senses'] == '=', abs(residual),
                             np.where(d['senses'] == '<', residual, -residual))
        row_error = float(max(0., np.max(violation)))
        bounds_error = float(max(0., np.max(d['lb']-point), np.max(point-d['ub'])))
        binaries = d['vtypes'] == 'B'
        integer_error = float(np.max(abs(point[binaries]-np.rint(point[binaries]))))
        require(row_error <= 1e-6 and bounds_error <= 1e-8 and integer_error <= 1e-8,
                'REDUCED_INCUMBENT_REPLAY_FAILED')
        require(float(point[-1]) == result['incumbent_joint_replay']['rho'] and
                abs(float(point[-1])-result['ObjVal']) <= 1e-12, 'INCUMBENT_OBJECTIVE_CONSTANT_MISMATCH')
        incumbent_replay = {'row_error': row_error, 'bounds_error': bounds_error,
                            'integer_error': integer_error, 'rho': float(point[-1]),
                            'FULL_feasibility_certified': False, 'new_UB': False}
        del J, d, point
        gc.collect()
    return {'PASS': True, 'schema': 'V42_JOINT_CRITICAL_GRID_INDEPENDENT_V1',
            'phase': 'Final', 'classification': classification, 'Global_LB': bound,
            'native_source_attribute': 'ObjBound', 'Native_calls_audited': 1,
            'verifier_Native_optimize_calls': 0, 'Full_MILP_calls': 0, 'separate_LP_calls': 0,
            'exact_model_and_rounding_audit_PASS': True,
            'actual_Gurobi_CSR_rhs_bounds_types_objective_readback_PASS': True,
            'post_build_memory_admission_PASS': True, 'continuous_memory_monitor_audited': True,
            'solver_status': result['Status'], 'Native_Runtime': runtime,
            'root_relaxation_completed': completed, 'NodeCount': result['NodeCount'],
            'ObjVal_reduced_model_only': result.get('ObjVal'),
            'incumbent_replay': incumbent_replay, 'UB': UB, 'Gap_percent': 100*gap,
            'delta_PR209': bound-PR209_LB, 'delta_Source18r_Full': bound-FULL_BOUND,
            'material_threshold': FULL_BOUND+.001, 'goal_LB': UB*.97,
            'goal_3percent': bound >= UB*.97,
            'exact_numeric_BB_trace_certificate': False,
            'proof_scope': 'Exact FULL→Compact→Joint inclusion and conservative binary64 row transport, plus the native minimization numerical global-bound contract.',
            'mathematical_statement': 'For each original FULL-feasible x, its preserved physical projection y satisfies every outward Joint16 row with the same rho. Thus ObjBound(native rounded Joint16) <= min(native rounded Joint16) <= min(FULL).',
            'exact_weighted_dominance_scope': 'PR209 exact weighted physical optimum <= exact Joint16 optimum. This is an optimum inequality; an unfinished solver bound need not exceed PR209 LB. Outward floating rows are separately certified as a relaxation.',
            'solver_bound_contract': 'Gurobi numerical minimization B&B ObjBound is trusted; no independent exact rational B&B trace or new LP solve is claimed.',
            'file_sha256': {name: sha_file(out/name) for name in (
                'INDEPENDENT_NATIVE0.json', 'NATIVE0.json', 'NATIVE_READBACK.json',
                'PHYSICAL_RELATION_AUDIT.json', 'PRE_OPTIMIZE_PEERS.json',
                'MEMORY_ADMISSION.json', 'PILOT_STARTED.json', 'RESULT.json',
                'MEMORY_TRACE.json', 'NATIVE_EVENTS.json', 'NATIVE.log')}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=('native0', 'final'), required=True)
    parser.add_argument('--source', type=Path, default=SOURCE)
    parser.add_argument('--previous', type=Path, default=PREVIOUS)
    parser.add_argument('--out', type=Path, default=OUT)
    args = parser.parse_args()
    start = time.perf_counter()
    output = args.out / ('INDEPENDENT_NATIVE0.json' if args.mode == 'native0' else 'INDEPENDENT_CERTIFICATE.json')
    try:
        if args.mode == 'native0':
            answer = native0(args.source, args.previous, args.out)
        else:
            answer = final(args.out)
        answer['wall_seconds'] = time.perf_counter() - start
        save_json(output, answer)
        print(json.dumps({key: answer.get(key) for key in ('PASS', 'phase', 'classification', 'Global_LB', 'wall_seconds')}, ensure_ascii=False))
    except Exception as exc:
        save_json(output, {'PASS': False, 'phase': args.mode, 'Native_optimize_calls': 0,
                          'error': str(exc), 'traceback': traceback.format_exc(),
                          'wall_seconds': time.perf_counter()-start})
        raise


if __name__ == '__main__':
    main()
