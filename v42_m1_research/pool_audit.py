"""Independent saved-pool audit, without importing the UB writer or its checker.

Producer PASS fields are ignored. Actual raw vectors are linked by SHA256,
then independently replayed against both source matrices and original physics.
No optimize, presolve, solver parameters, ledger edits or candidate repair.
"""
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import struct
from time import perf_counter
import numpy as np
from v42_unified.audit import ROOT, write
from v42_unified.storage import sha
from v42_native.contracts import digest


FACT_KEYS = ('schema', 'day', 'jobs', 'units', 'slots', 'services', 'binary', 'objective',
             'scientific_C3A_head', 'completed_M_head', 'integrated_A_head',
             'C3A_matrix_sha256', 'C3A_data_sha256', 'original_matrix_sha256',
             'original_data_sha256', 'frozen_bundle_sha256', 'route_table_sha256',
             'C3A_start_sha256', 'C1_columns', 'alias_sha256',
             'retained_columns_sha256', 'common_physics_sha256')


def point_sha(point):
    return hashlib.sha256(np.ascontiguousarray(point, dtype='<f8').tobytes()).hexdigest()


def double_bits(value):
    return struct.pack('<d', float(value)).hex()


def matrix_replay(A, data, raw, *, full_original=False):
    if raw.dtype != np.float64 or raw.shape != (A.shape[1],) or not np.isfinite(raw).all():
        return dict(PASS=False, reason='WRONG_RAW_DTYPE_AXIS_OR_NONFINITE')
    A = A.tocsr()
    residual = A@raw-data['rhs']
    senses = data['sense']
    observed = np.where(senses == '=', abs(residual), np.where(senses == '<', residual, -residual))
    tolerance = np.full(A.shape[0], 1e-6 if full_original else 1e-8)
    if full_original:
        tight = {'flow', 'terminal_location', 'NormalAmps', 'voltage_lower',
                 'voltage_upper', 'line_thermal_face', 'transformer_kVA'}
        for i, name in enumerate(data['row_names']):
            if str(name).split('[', 1)[0] in tight:
                tolerance[i] = 1e-8
    # Enclose all floating sparse dots; evaluate uncertain decisions with
    # exact dyadic arithmetic rather than changing the candidate's values.
    eps = np.finfo(np.float64).eps
    n = np.diff(A.indptr)
    gamma = (2*n+4)*eps/(1-(2*n+4)*eps)
    absolute_sum = abs(A)@abs(raw)
    error = np.nextafter(gamma*(absolute_sum/(1-gamma)+abs(data['rhs'])), np.inf)
    upper = np.nextafter(observed+error, np.inf)
    possibly_fail = np.flatnonzero(upper > tolerance)
    failures, exact_count = [], 0
    for i in possibly_fail:
        if observed[i]-error[i] > tolerance[i]:
            failures.append(int(i))
            continue
        exact_count += 1
        a, b = A.indptr[i:i+2]
        r = sum((Fraction(float(c))*Fraction(float(raw[j]))
                 for j, c in zip(A.indices[a:b], A.data[a:b])), Fraction(0))
        r -= Fraction(float(data['rhs'][i]))
        violation = abs(r) if senses[i] == '=' else r if senses[i] == '<' else -r
        if violation > Fraction(float(tolerance[i])):
            failures.append(int(i))
    bounds = max(0., float(np.max(data['lower']-raw, initial=0.)),
                 float(np.max(raw-data['upper'], initial=0.)))
    discrete = data['types'] != 'C'
    binary = data['types'] == 'B'
    error_integer = float(np.max(abs(raw[discrete]-np.rint(raw[discrete])), initial=0.))
    exact_integer = bool(np.array_equal(raw[discrete], np.rint(raw[discrete])))
    exact_binary = bool(np.logical_or(raw[binary] == 0., raw[binary] == 1.).all())
    scientific = not failures and bounds <= 1e-8 and error_integer <= 1e-8
    passed = scientific and exact_integer and exact_binary
    near_integer_rows = np.flatnonzero(discrete & (raw != np.rint(raw)))
    objective = float(data['objective']@raw+float(data['constant']))
    return dict(PASS=bool(passed), rows=A.shape[0], columns=A.shape[1],
        source_scientific_tolerance_PASS=bool(scientific),
        affine_tolerance_default=float(1e-6 if full_original else 1e-8),
        original_route_and_grid_tolerance=1e-8, bound_tolerance=1e-8,
        original_scientific_integrality_tolerance=1e-8,
        strict_postrun_exact_integer_pattern=exact_integer,
        strict_postrun_exact_binary_0_1=exact_binary,
        nonexact_integer_coordinates=[dict(column=int(j), name=str(data['names'][j]),
            raw_value=float(raw[j]), raw_binary64_bits=double_bits(raw[j]),
            integrality_distance=float(abs(raw[j]-np.rint(raw[j])))) for j in near_integer_rows[:20]],
        checked_discrete_columns=int(np.count_nonzero(discrete)),
        checked_binary_columns=int(np.count_nonzero(binary)),
        max_integrality_violation=error_integer, max_bound_violation=bounds,
        max_observed_row_violation=max(0., float(observed.max(initial=0.))),
        max_outward_row_upper=max(0., float(upper.max(initial=0.))),
        exact_dyadic_threshold_checks=exact_count, failing_rows=failures[:20],
        objective=objective, objective_binary64_bits=double_bits(objective))


def original_physics(case, raw):
    from v42_native.mess import validate
    from v42_bootstrap.attribution import supplemental_physical
    sites, initial, arcs, battery, _ = case.graph
    values = dict(zip(map(str, case.original_d['names']), map(float, raw)))
    for u in initial:
        for j in range(len(arcs)):
            values.setdefault(f'arc[{u},{j}]', 0.)
        for s in sites:
            for t in range(96):
                for family in ('Pch', 'Pdis', 'Q'):
                    values.setdefault(f'{family}[{u},{s},{t}]', 0.)
    chosen = {u: [j for j in range(len(arcs)) if values[f'arc[{u},{j}]'] > .5] for u in initial}
    plan = dict(values=values, initial_sites=initial, chosen_arcs=chosen, mode='MILP')
    physical = validate(plan, sites, [a[-1] for a in arcs if a[-1] is not None], battery, 96)
    mode = supplemental_physical(plan, sites, battery)
    return dict(PASS=bool(physical['PASS'] and mode['charge_mode_and_connection_PASS']),
                unchanged_original_route_SOC_PCS_checker=physical,
                unchanged_original_mode_connection_checker=mode,
                graph_horizon=96, units=len(initial), sites=len(sites), repairs=0)


def scientific_identity(case):
    facts = {k: case.identity[k] for k in FACT_KEYS}
    computed = digest(facts)
    files = [(ROOT/'docs/v42_m1_ultracompact_exact_20261006/C3A_A.npz', facts['C3A_matrix_sha256']),
             (ROOT/'docs/v42_m1_ultracompact_exact_20261006/C3A_DATA.npz', facts['C3A_data_sha256'])]
    for row in case.identity['D_frozen_copies']:
        files.append((Path(row['local_path']), row['sha256']))
    for relative, expected in facts['common_physics_sha256'].items():
        files.append((ROOT/relative, expected))
    checked = []
    for path, expected in files:
        if path.resolve().drive.upper() != 'D:':
            raise ValueError('POOL_AUDIT_SOURCE_FILES_MUST_BE_ON_D')
        actual = sha(path)
        checked.append(dict(path=str(path), expected_SHA256=expected,
                            measured_SHA256=actual, exact_identity=actual == expected))
    return dict(PASS=bool(computed == case.case_sha and all(r['exact_identity'] for r in checked)),
                recomputed_case_sha=computed, declared_case_sha=case.case_sha,
                case_sha_bit_identity=computed == case.case_sha,
                frozen_day=facts['day'], frozen_jobs=facts['jobs'], files=checked)


def audit(case, runpath):
    started = perf_counter()
    runpath = Path(runpath).resolve()
    if runpath.drive.upper() != 'D:' or not runpath.is_relative_to(ROOT.resolve()):
        raise ValueError('D_V42_POOL_AUDIT_REQUIRED')
    reports = ROOT/'docs/v42_m1_joint_gap_research'
    pool_path = reports/'UB_INCUMBENT_POOL.json'
    pool_bytes = pool_path.read_bytes()
    pool = json.loads(pool_bytes)
    identity = scientific_identity(case)
    sources = [Path(case.identity['committed_best_UB_sources'][0]['local_path'])]
    sources += sorted(reports.glob('U[12]_CAPTURE_*.npz'))
    sources += [reports/(n+'_RAW_POINT.npz') for n in ('FIXED_RECOURSE', 'U1', 'U2')]
    sources += [reports/'BEST_VALID_POINT.npz', runpath/'FINAL_VALID_UB_POINT.npz']
    vectors, source_errors = {}, []
    for path in dict.fromkeys(sources):
        if not path.exists():
            continue
        try:
            with np.load(path, allow_pickle=False) as z:
                key = 'point' if 'point' in z.files else 'x'
                raw = z[key].copy()
            if raw.dtype != np.float64 or raw.shape != (case.A.shape[1],):
                raise ValueError('RAW_POINT_DTYPE_OR_AXIS_DRIFT')
            fingerprint = point_sha(raw)
            meta = dict(path=str(path), npz_key=key, file_SHA256=sha(path),
                        raw_vector_SHA256=fingerprint, raw_dtype=str(raw.dtype), shape=list(raw.shape))
            if fingerprint not in vectors:
                vectors[fingerprint] = dict(raw=raw, sources=[])
            vectors[fingerprint]['sources'].append(meta)
        except Exception as exc:
            source_errors.append(dict(path=str(path), error=type(exc).__name__+': '+str(exc)))
    entries = []
    for entry in pool['entries']:
        claimed = entry['point_sha256']
        found = vectors.get(claimed)
        if found is None:
            entries.append(dict(source=entry['source'], claimed_vector_SHA256=claimed,
                status='NOT_PROVEN', PASS=False, reason='APPROVED_VECTOR_NOT_SAVED',
                producer_PASS_ignored=True, additional_Native_Runtime=0.))
            continue
        raw = found['raw']
        original = case.lift(raw)
        c3 = matrix_replay(case.A, case.d, raw)
        full = matrix_replay(case.original_A, case.original_d, original, full_original=True)
        physical = original_physics(case, original)
        objective_equal = double_bits(c3['objective']) == double_bits(entry['objective']) == double_bits(full['objective'])
        cases_equal = entry['case_sha'] == pool['case_sha'] == case.case_sha == identity['recomputed_case_sha']
        raw_equal = point_sha(raw) == claimed
        binaries = c3['checked_binary_columns'] == 9322 and full['checked_binary_columns'] == 208312
        passed = identity['PASS'] and c3['PASS'] and full['PASS'] and physical['PASS']
        passed = passed and objective_equal and cases_equal and raw_equal and binaries
        scientific = identity['PASS'] and c3['source_scientific_tolerance_PASS'] and full['source_scientific_tolerance_PASS'] and physical['PASS']
        scientific = scientific and objective_equal and cases_equal and raw_equal and binaries
        entries.append(dict(source=entry['source'], status='INDEPENDENT_REPLAY_PASS' if passed else 'INDEPENDENT_REPLAY_FAIL',
            PASS=bool(passed), case_sha=case.case_sha, case_sha_bit_identity=cases_equal,
            original_registered_scientific_tolerance_replay_PASS=bool(scientific),
            claimed_vector_SHA256=claimed, matched_vector_SHA256=point_sha(raw),
            raw_vector_identity=raw_equal, saved_raw_sources=found['sources'],
            declared_pool_objective=entry['objective'], independently_replayed_objective=full['objective'],
            objective_binary64_bits=double_bits(full['objective']),
            declared_pool_objective_bits=double_bits(entry['objective']), objective_bit_identity=objective_equal,
            C3A_all_rows_bounds_types=c3, original_all_rows_bounds_types=full,
            original_physical=physical, producer_PASS_ignored=True,
            historical_source_PASS_receipts_not_used_for_admission=True,
            sourcepoint_repairs=0, sourcepoint_clipping=0, sourcepoint_rounding=0,
            additional_Native_Runtime=0.))
    passed_entries = [r for r in entries if r['PASS']]
    actual_best = min((r['independently_replayed_objective'] for r in passed_entries), default=None)
    best_equal = actual_best is not None and double_bits(actual_best) == double_bits(pool['best_validated_global_UB'])
    pool_unchanged = pool_path.read_bytes() == pool_bytes
    all_pass = len(passed_entries) == len(entries) and bool(entries) and best_equal and pool_unchanged
    result = dict(schema='V42_UB_POOL_INDEPENDENT_AUDIT_V1', performed=True,
        status='POOL_INDEPENDENT_REPLAY_PASS' if all_pass else 'POOL_NOT_FULLY_PROVEN', PASS=bool(all_pass),
        scientific_identity=identity, case_sha=case.case_sha,
        pool_file=str(pool_path), pool_file_SHA256=hashlib.sha256(pool_bytes).hexdigest(),
        approved_entries_count=len(entries), independently_replayed_PASS_count=len(passed_entries),
        registered_scientific_tolerance_replay_PASS_count=sum(r.get('original_registered_scientific_tolerance_replay_PASS', False) for r in entries),
        entries=entries, nonapproved_source_parse_errors=source_errors,
        independently_validated_global_UB=actual_best, best_UB_binary64_bit_identity=best_equal,
        producer_PASS_values_ignored=True, source_archive_receipts_not_substituted_for_replay=True,
        original_all_9322_C3A_and_208312_FULL_binary_exact_0_1_checked=True,
        recorded_pool_unchanged=pool_unchanged, prior_ledgers_or_results_modified=False,
        registered_experiment_criteria_changed=False,
        stricter_integer_bit_check_is_additional_postrun_audit=True,
        additional_Native_optimize_calls=0, additional_Native_Runtime=0., additional_Native_Work=0.,
        original_frozen_May01_case_only=True, May12_anchor_consumed=False,
        analysis_wall_seconds=perf_counter()-started)
    write(reports/'UB_POOL_INDEPENDENT_AUDIT.json', result)
    return result


def create_strict_addendum(case, runpath, source_path=None):
    """Explicit new packet from an already saved RAW; original pool untouched."""
    started = perf_counter()
    runpath = Path(runpath).resolve()
    reports = ROOT/'docs/v42_m1_joint_gap_research'
    source_path = Path(source_path or reports/'U2_RAW_POINT.npz').resolve()
    if any(p.drive.upper() != 'D:' or not p.is_relative_to(ROOT.resolve()) for p in (runpath, source_path)):
        raise ValueError('STRICT_ADDENDUM_REQUIRES_EXISTING_D_RAW_POINT')
    pool_path = reports/'UB_INCUMBENT_POOL.json'
    pool_before = pool_path.read_bytes()
    pool = json.loads(pool_before)
    checkpoint = runpath/'FINAL_VALID_UB_POINT.npz'
    checkpoint_before = sha(checkpoint) if checkpoint.exists() else None
    original_source_bytes = source_path.read_bytes()
    with np.load(source_path, allow_pickle=False) as z:
        if z.files != ['point']:
            raise ValueError('SOURCE_RAW_POINT_PACKET_AXIS_DRIFT')
        point = z['point'].copy()
    identity = scientific_identity(case)
    c3 = matrix_replay(case.A, case.d, point)
    full = matrix_replay(case.original_A, case.original_d, case.lift(point), full_original=True)
    physical = original_physics(case, case.lift(point))
    objective_equal = double_bits(c3['objective']) == double_bits(full['objective']) == double_bits(pool['best_validated_global_UB'])
    count_equal = c3['checked_binary_columns'] == 9322 and full['checked_binary_columns'] == 208312
    passed = identity['PASS'] and c3['PASS'] and full['PASS'] and physical['PASS'] and objective_equal and count_equal
    if not passed:
        raise ValueError('SOURCE_RAW_POINT_NOT_INDEPENDENT_STRICT_ORIGINAL_WITNESS')
    packet = reports/'FINAL_STRICT_ADMITTED_UB_POINT.npz'
    if packet.exists() and packet.read_bytes() != original_source_bytes:
        raise ValueError('EXISTING_STRICT_PACKET_MUST_NOT_BE_REPLACED')
    if not packet.exists():
        packet.write_bytes(original_source_bytes)
    with np.load(packet, allow_pickle=False) as z:
        delivered = z['point'].copy()
    packet_identity = packet.read_bytes() == original_source_bytes and point_sha(delivered) == point_sha(point)
    pool_unchanged = pool_path.read_bytes() == pool_before
    checkpoint_after = sha(checkpoint) if checkpoint.exists() else None
    checkpoint_unchanged = checkpoint_after == checkpoint_before
    raw_source_unchanged = source_path.read_bytes() == original_source_bytes
    prior_audit_path = reports/'UB_POOL_INDEPENDENT_AUDIT.json'
    prior_audit = json.loads(prior_audit_path.read_text(encoding='utf-8')) if prior_audit_path.exists() else None
    result = dict(schema='V42_UB_STRICT_RAW_WITNESS_ADDENDUM_V1', PASS=bool(packet_identity and pool_unchanged and checkpoint_unchanged and raw_source_unchanged),
        case_sha=case.case_sha, scientific_identity=identity,
        source_raw_packet=str(source_path), source_raw_file_SHA256=hashlib.sha256(original_source_bytes).hexdigest(),
        new_packet=str(packet), new_packet_file_SHA256=sha(packet),
        source_raw_vector_SHA256=point_sha(point), delivered_raw_vector_SHA256=point_sha(delivered),
        packet_file_bytes_identical_to_already_saved_raw=packet_identity,
        original_C3A_all_rows_and_9322_exact_binary=c3,
        original_FULL_all_rows_and_208312_exact_binary=full,
        original_96_slot_4_unit_physical_replay=physical,
        source_objective=full['objective'], objective_binary64_bits=double_bits(full['objective']),
        pool_objective=pool['best_validated_global_UB'], objective_bit_identity=objective_equal,
        pool_best_vector_SHA256=pool['entries'][-1]['point_sha256'],
        source_is_a_distinct_stored_vector_from_pool_capture=point_sha(point) != pool['entries'][-1]['point_sha256'],
        old_pool_strict_admission_audit=dict(path=str(prior_audit_path),
            SHA256=sha(prior_audit_path) if prior_audit_path.exists() else None,
            strict_PASS_count=prior_audit['independently_replayed_PASS_count'] if prior_audit else None,
            entry_count=prior_audit['approved_entries_count'] if prior_audit else None,
            registered_tolerance_PASS_count=prior_audit['registered_scientific_tolerance_replay_PASS_count'] if prior_audit else None),
        pool_file_unchanged=pool_unchanged, original_checkpoint_unchanged=checkpoint_unchanged,
        original_checkpoint_SHA256_before=checkpoint_before, original_checkpoint_SHA256_after=checkpoint_after,
        source_raw_file_unchanged=raw_source_unchanged,
        existing_pool_or_FINAL_VALID_packet_not_replaced=True,
        explicit_later_independent_checker_must_receive_this_new_packet=True,
        source_point_repairs=0, source_point_rounding=0, source_point_clipping=0,
        registered_experiment_criteria_changed=False,
        Native_optimize_calls=0, additional_Native_Runtime=0., additional_Native_Work=0.,
        analysis_wall_seconds=perf_counter()-started)
    write(reports/'UB_STRICT_ADMISSION_ADDENDUM.json', result)
    return result
