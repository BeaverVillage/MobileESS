"""Bounded UB research only. Restricted bounds never become global LB.

All original C3A rows and continuous bounds stay present, including 96-slot
route/SOC coupling. The runner provides the shared cumulative native ledger.
"""
import csv
import json
from pathlib import Path
from time import perf_counter
import numpy as np
import gurobipy as gp
from .check_ub import validate_candidate, dispatch_difference, vector_sha


def _write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def _restricted_bound(model):
    try:
        return float(model.ObjBound)
    except (gp.GurobiError, AttributeError):
        return None


def binary_inventory(d, *, expected_count=9322):
    columns = np.flatnonzero(d['types'] != 'C')
    inventory = []
    for j in columns:
        name = str(d['names'][j])
        family, rest = name.split('[', 1)
        fields = rest[:-1].split(',')
        if family not in ('charge_mode', 'node_activity'):
            raise ValueError('UNKNOWN_C3A_BINARY_FAMILY:'+name)
        inventory.append(dict(column=int(j), name=name, family=family, unit=fields[0],
                              site=fields[1] if family == 'node_activity' else None,
                              slot=int(fields[-1])))
    if type(expected_count) is not int or expected_count < 0:
        raise ValueError('C3A_ORIGINAL_BINARY_COUNT_AUTHORITY_INVALID')
    if len(inventory) != expected_count:
        raise ValueError('C3A_ORIGINAL_BINARY_MAPPING_COUNT_DRIFT')
    return inventory


def unit_burden(d, point, inventory):
    units = sorted({r['unit'] for r in inventory})
    result = {u: 0. for u in units}
    for j, name in enumerate(map(str, d['names'])):
        if not name.startswith(('Pch[', 'Pdis[', 'Q[')):
            continue
        fields = name.split('[', 1)[1][:-1].split(',')
        if 66 <= int(fields[-1]) <= 95:
            result[fields[0]] += abs(float(point[j]))
    return result


def select_neighborhood(case, point, label):
    inventory = binary_inventory(case.d)
    units = sorted({r['unit'] for r in inventory})
    burden = unit_burden(case.d, point, inventory)
    if label == 'U1':
        active_units = sorted(units, key=lambda u: (-burden[u], u))[:2]
        # Full locations for two interacting vehicles. Modes remain free too.
        free = [r['column'] for r in inventory
                if r['unit'] in active_units and 66 <= r['slot'] <= 95]
        allowed_sites = None
        radius = 48
        description = 'two highest critical-dispatch units; all reachable sites and modes in slots66..95'
    elif label == 'U2':
        active_units = units
        occupied = {r['site'] for r in inventory if r['family'] == 'node_activity'
                    and 66 <= r['slot'] <= 95 and point[r['column']] > .5}
        # Four vehicles can reassign every incumbent late-window service role.
        # One additional pilot site may come from an independently frozen root
        # diagnosis; otherwise all incumbent role sites remain available.
        extras = list(getattr(case, 'critical_sites', ()))
        allowed_sites = sorted(occupied | set(extras[:1]))
        free = [r['column'] for r in inventory if 66 <= r['slot'] <= 95 and
                (r['family'] == 'charge_mode' or r['site'] in allowed_sites)]
        radius = 96
        description = 'all four units jointly exchange incumbent service roles plus one frozen critical site'
    else:
        raise ValueError('LIMITED_REGISTERED_UB_NEIGHBORHOODS_ONLY')
    free = np.asarray(sorted(free), dtype=np.int64)
    fixed = np.setdiff1d(np.asarray([r['column'] for r in inventory]), free)
    return dict(label=label, free_binary_columns=free, fixed_binary_columns=fixed,
                active_units=active_units, allowed_sites=allowed_sites, hamming_radius=radius,
                critical_window=[66, 95], full_horizon=96, burden=burden,
                all_binary_count=len(inventory), description=description,
                entire_96_slot_route_SOC_rows_preserved=True, all_charge_modes_forced_zero=False,
                bound_scope='RESTRICTED_NEIGHBORHOOD_ONLY_NOT_GLOBAL_LB')


def build_model(case, point, label, output_dir, *, start_validation=None):
    """Build and audit exact rows before the shared ledger permits optimize."""
    started = perf_counter()
    if Path(output_dir).resolve().drive.upper() != 'D:':
        raise ValueError('UB_BUILD_OUTPUTS_MUST_STAY_ON_D_DRIVE')
    start_validation = start_validation or validate_candidate(case, point)
    if not start_validation['PASS'] or start_validation.get('point_sha256') != vector_sha(point):
        raise ValueError('INDEPENDENT_ORIGINAL_REPLAY_REQUIRED_BEFORE_ANY_MIP_START')
    inventory = binary_inventory(case.d)
    all_binary = np.asarray([r['column'] for r in inventory], dtype=np.int64)
    lower, upper = case.d['lower'].copy(), case.d['upper'].copy()
    types = case.d['types'].copy()
    if label == 'FIXED_RECOURSE':
        free = np.array([], dtype=np.int64)
        fixed = all_binary
        types[:] = 'C'
        spec = dict(label=label, free_binary_columns=free, fixed_binary_columns=fixed,
                    hamming_radius=None, all_binary_count=9322, full_horizon=96,
                    bound_scope='FIXED_DISCRETE_RECOURSE_ONLY_NOT_GLOBAL_LB',
                    entire_96_slot_route_SOC_rows_preserved=True,
                    all_charge_modes_forced_zero=False)
    else:
        spec = select_neighborhood(case, point, label)
        free, fixed = spec['free_binary_columns'], spec['fixed_binary_columns']
    if not np.isin(point[all_binary], (0., 1.)).all():
        raise ValueError('RAW_VALIDATED_BINARY_PATTERN_NOT_EXACT_FOR_FIXING_NO_ROUNDING_ALLOWED')
    lower[fixed] = point[fixed]
    upper[fixed] = point[fixed]
    model = gp.Model('V42_M1_RESEARCH_UB_'+label)
    try:
        model.Params.OutputFlag = 1
        model.Params.LogFile = str(Path(output_dir)/(label+'_NATIVE.log'))
        for key, value in dict(Threads=1, FeasibilityTol=1e-8, OptimalityTol=1e-8,
                               IntFeasTol=1e-8, MIPGap=.005).items():
            setattr(model.Params, key, value)
        if label == 'FIXED_RECOURSE':
            model.Params.Method = 1
        else:
            model.Params.Method = 2
            model.Params.MIPFocus = 1
        variables = model.addMVar(case.A.shape[1], lb=lower, ub=upper, vtype=types,
                                  obj=case.d['objective'])
        variables.VarName = case.d['names'].tolist()
        model.ObjCon = float(case.d['constant'])
        rows = model.addMConstr(case.A, variables, case.d['sense'], case.d['rhs'])
        rows.ConstrName = case.d['row_names'].tolist()
        if len(free):
            coefficients = np.where(point[free] == 1., -1., 1.)
            rhs = spec['hamming_radius']-float(np.count_nonzero(point[free]))
            model.addConstr(coefficients @ variables[free] <= rhs,
                            name='UB_RESTRICTED_LOCAL_HAMMING_ONLY')
        variables.Start = point
        model.update()
        # Rows, objective and unmodified continuous domains are byte-equivalent.
        source = model.getA()[:case.A.shape[0]]
        difference = source-case.A
        difference.eliminate_zeros()
        objective = np.asarray(model.getAttr('Obj'))
        bounds_ok = np.array_equal(np.asarray(model.getAttr('LB')), lower) and np.array_equal(np.asarray(model.getAttr('UB')), upper)
        continuous = case.d['types'] == 'C'
        exact_rows = difference.nnz == 0 and np.array_equal(np.asarray(model.getAttr('RHS'))[:case.A.shape[0]], case.d['rhs'])
        exact_rows = exact_rows and np.array_equal(np.asarray(model.getAttr('Sense'))[:case.A.shape[0]], case.d['sense'])
        exact_objective = np.array_equal(objective, case.d['objective']) and model.ObjCon == float(case.d['constant'])
        if not exact_rows or not exact_objective or not bounds_ok:
            raise ValueError('UB_MODEL_BUILD_ORIGINAL_SCIENTIFIC_PAYLOAD_DRIFT')
        spec.update(PASS=True, case_sha=case.case_sha, original_rows=case.A.shape[0],
                    model_rows=model.NumConstrs, model_columns=model.NumVars,
                    original_9322_binary_map_complete=True,
                    original_rows_RHS_senses_exact=bool(exact_rows),
                    objective_exact=bool(exact_objective),
                    original_continuous_bounds_exact=bool(np.array_equal(lower[continuous], case.d['lower'][continuous]) and np.array_equal(upper[continuous], case.d['upper'][continuous])),
                    fixed_binary_count=len(fixed), free_binary_count=len(free),
                    start_sha256=vector_sha(point), scientific_tolerances=dict(FeasibilityTol=1e-8, OptimalityTol=1e-8, IntFeasTol=1e-8),
                    independent_start_original_replay_PASS=True,
                    build_wall_seconds=perf_counter()-started, finite_memory_limits=False,
                    all_96_slot_energy_rows=int(sum(str(n).startswith('energy_balance') for n in case.d['row_names'])))
        serial = {k: v.tolist() if isinstance(v, np.ndarray) else v for k, v in spec.items()}
        _write(Path(output_dir)/(label+'_MODEL_IDENTITY.json'), serial)
        return model, variables, spec
    except BaseException:
        model.dispose()
        raise


def run(case, ledger, output_dir, *, limits=None):
    """Three bounded calls: fixed recourse and exactly one U1 / one U2 pilot."""
    output = Path(output_dir).resolve()
    if output.drive.upper() != 'D:':
        raise ValueError('UB_OUTPUTS_MUST_STAY_ON_D_DRIVE')
    output.mkdir(parents=True, exist_ok=True)
    limits = limits or dict(FIXED_RECOURSE=120., U1=700., U2=980.)
    if set(limits) != {'FIXED_RECOURSE', 'U1', 'U2'} or sum(limits.values()) > 1800.:
        raise ValueError('REGISTERED_UB_LIMITS_MUST_SUM_TO_AT_MOST_1800_SECONDS')
    baseline = np.asarray(case.point).copy()
    incumbent = baseline.copy()
    with ledger.cost('validation', 'UB_BASELINE_FULL_REPLAY', track='UB'):
        initial = validate_candidate(case, incumbent)
    _write(output/'BASELINE_INTEGER_PHYSICAL_REPLAY.json', initial)
    if not initial['PASS']:
        raise ValueError('UNVERIFIED_UB_SOURCE_MUST_NOT_ENTER_MIP_START')
    np.savez_compressed(output/'BEST_VALID_POINT.npz', point=incumbent)
    history = []
    pool = [dict(source='COMPLETED_PR188_BEST', objective=initial['objective'],
                 case_sha=case.case_sha, point_sha256=initial['point_sha256'], PASS=True)]
    replays = [dict(label='COMPLETED_PR188_BEST', **initial)]
    best = initial['objective']
    for label in ('FIXED_RECOURSE', 'U1', 'U2'):
        # Validate again before each new model's start, including latest updates.
        with ledger.cost('validation', label+'_MIP_START_FULL_REPLAY', track='UB'):
            start_replay = validate_candidate(case, incumbent)
        if not start_replay['PASS']:
            raise ValueError('LATEST_UB_INCUMBENT_MIP_START_ADMISSION_FAILED')
        with ledger.cost('model_build', label, track='UB'):
            model, variables, spec = build_model(case, incumbent, label, output,
                                                start_validation=start_replay)
        run_start = perf_counter()
        captured = []
        checker_errors = []
        local_best = best
        captured_raw = []
        capture_best = best
        native = None
        track_native_before = ledger.used('UB')

        def admit(point, source):
            nonlocal incumbent, best, local_best
            raw = np.asarray(point, dtype=np.float64)
            objective = float(case.d['objective'] @ raw+float(case.d['constant']))
            if objective >= local_best-1e-10:
                return None
            with ledger.cost('validation', label+'_'+source+'_FULL_REPLAY', track='UB'):
                replay = validate_candidate(case, raw)
            replays.append(dict(label=label, source=source, **replay))
            if not replay['PASS']:
                return replay
            captured.append(replay)
            local_best = objective
            if objective < best-1e-10:
                best, incumbent = objective, raw.copy()
                np.savez_compressed(output/'BEST_VALID_POINT.npz', point=incumbent)
                pool.append(dict(source=label+'_'+source, objective=best, case_sha=case.case_sha,
                                 point_sha256=replay['point_sha256'], PASS=True,
                                 full_original_integer_physical_replay_PASS=True))
            return replay

        def callback(m, where):
            nonlocal capture_best
            if where != gp.GRB.Callback.MIPSOL:
                return
            try:
                native_objective = float(m.cbGet(gp.GRB.Callback.MIPSOL_OBJ))
                if native_objective < capture_best-1e-10:
                    raw = np.asarray(m.cbGetSolution(variables), dtype=np.float64).copy()
                    capture_best = native_objective
                    captured_raw.append((native_objective, raw))
                    captured_raw.sort(key=lambda r: r[0])
                    del captured_raw[3:]
            except BaseException as exc:
                # Capture never admits a raw point to the pool. Expensive exact
                # and physical replay occurs after optimize and is separately timed.
                checker_errors.append(type(exc).__name__+': '+str(exc))

        try:
            native_error = None
            try:
                native = ledger.optimize(model, track='UB', label=label,
                                         requested_seconds=float(limits[label]), callback=callback)
            except Exception as exc:
                native_error = type(exc).__name__+': '+str(exc)
            sol_count = int(model.SolCount)
            final_replay = None
            for capture_id, (_, raw) in enumerate(captured_raw):
                np.savez_compressed(output/(label+f'_CAPTURE_{capture_id:02d}.npz'), point=raw)
                admit(raw, f'MIPSOL_CAPTURE_{capture_id:02d}')
            if sol_count:
                raw = np.asarray(variables.X).copy()
                # Always replay the final raw result, even when it has no gain.
                with ledger.cost('validation', label+'_FINAL_RAW_FULL_REPLAY', track='UB'):
                    final_replay = validate_candidate(case, raw)
                replays.append(dict(label=label, source='FINAL_NATIVE_RAW', **final_replay))
                np.savez_compressed(output/(label+'_RAW_POINT.npz'), point=raw)
                if final_replay['PASS']:
                    admit(raw, 'FINAL_NATIVE_RAW')
            row = dict(label=label, case_sha=case.case_sha, native_status=int(model.Status),
                       native_Runtime=float(model.Runtime), native_Work=float(model.Work),
                       native_solution_count=sol_count, original_rows=case.A.shape[0],
                       free_binary_count=spec['free_binary_count'], fixed_binary_count=spec['fixed_binary_count'],
                       restricted_neighborhood_ObjBound=_restricted_bound(model),
                       bound_scope='RESTRICTED_ONLY_NEVER_GLOBAL_LB',
                       global_LB_candidate=None, before_validated_UB=start_replay['objective'],
                       best_validated_UB=best, UB_improvement=start_replay['objective']-best,
                       final_original_replay_PASS=bool(final_replay and final_replay['PASS']),
                       admitted_improved_candidates=len(captured), checker_errors=checker_errors,
                       captured_unvalidated_raw_points=len(captured_raw),
                       physical_validation_during_native_optimize=False,
                       native_error=native_error,
                       native_ledger_receipt=native, build_wall_seconds=spec['build_wall_seconds'],
                       optimize_and_replay_wall_seconds=perf_counter()-run_start,
                       track_native_before=track_native_before,
                       track_native_after=ledger.used('UB'),
                       status='NATIVE_CALL_FAILED' if native_error else 'UB_IMPROVED' if best < start_replay['objective']-1e-10 else 'NO_VALIDATED_UB_IMPROVEMENT')
            _write(output/(label+'_RESULT.json'), row)
            history.append(row)
        finally:
            model.dispose()
    with ledger.cost('validation', 'UB_FINAL_BEST_FULL_REPLAY', track='UB'):
        final = validate_candidate(case, incumbent)
    _write(output/'UB_INTEGER_PHYSICAL_REPLAY.json', dict(PASS=bool(final['PASS']),
           case_sha=case.case_sha, baseline=initial, best=final, candidates=replays,
           dispatch_change=dispatch_difference(case, baseline, incumbent), raw_repairs=0))
    _write(output/'UB_INCUMBENT_POOL.json', dict(case_sha=case.case_sha, entries=pool,
           best_validated_global_UB=best, pool_admission='independent original full matrix and physical PASS before admission',
           saved_best_point=str(output/'BEST_VALID_POINT.npz'),
           restricted_neighborhood_bounds_used_as_global_LB=False))
    columns = ['label', 'native_status', 'native_Runtime', 'native_Work', 'native_solution_count',
               'free_binary_count', 'fixed_binary_count', 'before_validated_UB', 'best_validated_UB',
               'UB_improvement', 'final_original_replay_PASS', 'admitted_improved_candidates',
               'bound_scope', 'global_LB_candidate', 'status']
    with (output/'UB_NEIGHBORHOOD_RESULTS.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(history)
    return dict(PASS=bool(final['PASS']), case_sha=case.case_sha,
                baseline_validated_global_UB=initial['objective'], best_validated_global_UB=best,
                UB_improved=best < initial['objective']-1e-10,
                restricted_neighborhood_bounds_used_as_global_LB=False, experiments=history,
                incumbent_pool=pool, final_replay=final, point=incumbent)
