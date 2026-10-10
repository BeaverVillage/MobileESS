"""Measured 1800-second primal-only production MESS optimizer.

No pricing, DW, CG, Benders, full-LP bound solve or LB strengthening is called.
Restricted BestBound is persisted only as a native diagnostic.
"""
from fractions import Fraction as F
from copy import deepcopy
from pathlib import Path
from time import perf_counter
import json
import math
import numpy as np

from . import VERSION, NATIVE_LIMIT_SECONDS
from .budget import StageBudget
from .fixed_pattern import integer_representatives, stationary_paths, values_for
from .model import build
from .neighborhood import current_grid, select, inventory
from .storage import write, record


def _strict(case, path, evidence):
    from v42_m1_hybrid.final_verify import _strict_ub
    return _strict_ub(case, path, evidence)


def _validate(case, point, path, validator, budget, label):
    from v42_m1_research.check_ub import vector_sha
    if point is None:
        return None
    point = np.asarray(point, dtype=np.float64)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, point=point)
    try:
        with budget.cost('integer_physical_validation', label):
            strict = validator(case, path, {})
        replay = strict.get('original_matrix_and_96_slot_physical_replay', {})
        if (strict.get('PASS') is not True
                or strict.get('strict_raw_C3A_and_FULL_integer_and_binary_pattern_exact') is not True
                or replay.get('PASS') is not True or replay.get('case_sha') != case.case_sha
                or strict.get('point_vector_sha256') != vector_sha(point)):
            raise ValueError('COMMON_M_STRICT_ORIGINAL_FULL_REPLAY_REQUIRED')
        strict = dict(strict, case_sha=case.case_sha, scientific_case_sha=case.case_sha,
            original_matrix_sha=case.identity.get('original_matrix_sha'),
            original_domain_sha=case.identity.get('original_domain_sha'),
            engine_version=VERSION, point_rounding=False, point_clipping=False)
        write(path.with_suffix('.REPLAY.json'), strict)
        return strict
    except ValueError as error:
        write(path.with_suffix('.REPLAY.json'), dict(PASS=False, case_sha=case.case_sha,
            error=str(error), invalid_point_not_admitted=True, repairs=0, rounding=0))
        return None


def _attr(model, name):
    try:
        value = getattr(model, name)
        return value if not isinstance(value, float) or math.isfinite(value) else None
    except Exception:
        return None


def _completed_native_receipt(budget, before_count, before_used, *, component,
                              track, label, requested_seconds):
    """Recover only the exact measured call persisted by a no-return ledger."""
    if len(budget.calls) != before_count + 1:
        return None
    parent = getattr(budget, 'parent', budget)
    if getattr(parent, 'inflight', None) is not None:
        return None
    row = budget.calls[-1]
    if (not isinstance(row, dict) or row.get('status') not in ('FINISHED', 'FAILED')
            or row.get('entered_native') is not True or row.get('runtime_unavailable') is not False
            or any(row.get(key) != value for key, value in
                (('component', component), ('track', track), ('label', label),
                 ('requested_seconds', requested_seconds), ('effective_TimeLimit', requested_seconds)))):
        return None
    try:
        runtime = float(row['Native_Runtime'])
    except (KeyError, TypeError, ValueError):
        return None
    consumed = budget.used() - before_used
    if (not math.isfinite(runtime) or runtime < 0
            or not math.isclose(runtime, consumed, rel_tol=1e-12, abs_tol=1e-9)):
        return None
    return deepcopy(row)


def _trial(case, budget, path, *, validator, seconds, lower=None, upper=None,
           point=None, strict=None, continuous=False, spec=None, initialization=False,
           numeric_parameters=None):
    """Extract final/callback incumbents even after a native budget exception."""
    import gurobipy as gp
    from v42_m1_research.check_ub import vector_sha
    path.mkdir(parents=True, exist_ok=False)
    with budget.cost('model_build', path.name):
        model, variables, identity = build(case, path, lower=lower, upper=upper,
            continuous=continuous, start=point, spec=spec, numeric_parameters=numeric_parameters)
    if initialization and not continuous:
        model.Params.MIPFocus = 1
        model.Params.SolutionLimit = 1
    pending, capture_errors = [], []
    discovered = float(F(strict['exact_Global_UB'])) if strict else float('inf')
    before = budget.used()
    before_count = len(budget.calls)
    component = 'FEASIBILITY_LP' if continuous else 'FEASIBILITY_MIP' if initialization else 'UB'
    track = 'M_START' if initialization else 'M_' + (spec['method'] if spec else 'FIXED_ROUTE')
    effective_seconds = min(float(seconds), budget.remaining())
    def capture(m, where):
        nonlocal discovered
        if where != gp.GRB.Callback.MIPSOL:
            return # POLLING has no supported scientific attributes.
        try:
            objective = float(m.cbGet(gp.GRB.Callback.MIPSOL_OBJ))
            if objective < discovered - 1e-11:
                raw = np.asarray(m.cbGetSolution(variables), dtype=np.float64).copy()
                pending.append((objective, raw))
                pending.sort(key=lambda item: item[0]); del pending[5:]
                discovered = objective
        except Exception as error:
            capture_errors.append(type(error).__name__ + ': ' + str(error))
    error, native, native_failure = None, None, None
    try:
        try:
            native = budget.native_optimize(model, capture,
                component=component, track=track,
                label=path.name, requested_seconds=seconds)
        except Exception as failure:
            native_failure = failure
            error = type(failure).__name__ + ': ' + str(failure)
        if native is None:
            native = _completed_native_receipt(budget, before_count, before,
                component=component, track=track, label=path.name,
                requested_seconds=effective_seconds)
        if _attr(model, 'SolCount'):
            pending.append((float(model.ObjVal), np.asarray(variables.X, dtype=np.float64).copy()))
        best = None if point is None else point.copy()
        best_strict = strict
        admitted, rejected, seen = [], [], set()
        for ordinal, (_, raw) in enumerate(pending):
            sha = vector_sha(raw)
            if sha in seen:
                continue
            seen.add(sha)
            packet = path / f'RAW_{ordinal:02d}.npz'
            certificate = _validate(case, raw, packet, validator, budget, path.name + '_FULL')
            if certificate is None:
                rejected.append(dict(point_vector_sha256=sha, packet=record(packet)))
                continue
            admitted.append(dict(packet=record(packet), exact_Global_UB=certificate['exact_Global_UB']))
            if best_strict is None or F(certificate['exact_Global_UB']) < F(best_strict['exact_Global_UB']):
                best, best_strict = raw.copy(), certificate
        row = dict(case_sha=case.case_sha, label=path.name,
            method=spec['method'] if spec else 'INITIALIZATION' if initialization else 'FIXED_ROUTE',
            requested_seconds=seconds, native_receipt=native,
            Native_Runtime=budget.used() - before, Native_Work=_attr(model, 'Work'),
            Native_status=_attr(model, 'Status'), Native_SolCount=_attr(model, 'SolCount'),
            native_best_bound_diagnostic=_attr(model, 'ObjBound'),
            restricted_BestBound_is_Global_LB=False, Global_LB_candidate=None,
            start_UB=None if strict is None else strict['Global_UB'],
            best_validated_UB=None if best_strict is None else best_strict['Global_UB'],
            certified_gain=0. if strict is None or best_strict is None else
                float(F(strict['exact_Global_UB']) - F(best_strict['exact_Global_UB'])),
            accepted_candidates=admitted, rejected_candidates=rejected,
            capture_errors=capture_errors, native_error=error,
            cumulative_native_runtime_seconds=budget.used(),
            native_budget_overshoot_seconds=max(0., budget.used() - NATIVE_LIMIT_SECONDS))
        write(path / 'RESULT.json', row)
        if any(r.get('runtime_unavailable') for r in budget.calls):
            raise RuntimeError('COMMON_M_NATIVE_RUNTIME_UNAVAILABLE_QUARANTINE')
        from v42_svr11.anytime import enabled,normal_budget_exception
        if enabled() and native_failure is not None and not normal_budget_exception(native_failure):
            raise native_failure
        if isinstance(native_failure, (PermissionError, ValueError)) or error and (
                'ADMISSION' in error or 'SOURCE' in error or 'DRIFT' in error):
            raise RuntimeError(error)
        return best, best_strict, row
    finally:
        model.dispose()


def _initialize(case, budget, validator, progress, numeric_parameters):
    """Current-stage LP, bounded mode/route recovery, then unrestricted seed."""
    point = getattr(case, 'point', None)
    strict = _validate(case, point, case.output / 'REUSABLE_STAGE_POINT.npz', validator,
        budget, 'REUSABLE_STAGE_FULL_REPLAY')
    if strict is not None:
        write(case.output / 'SEED_BYPASS_CERTIFIED_DISPATCH.json', dict(PASS=True,
            case_sha=case.case_sha, source='CURRENT_STAGE_REPLAYED_POINT',
            M_SEED_optimize_calls=0, original_FULL_replay=record(case.output / 'REUSABLE_STAGE_POINT.REPLAY.json')))
        return point.copy(), strict, []
    paths = stationary_paths(case)
    peak = 48
    receipt = case.output / 'SAME_DAY_STATIONARY_CANDIDATE.json'
    if receipt.exists():
        observation = json.loads(receipt.read_text(encoding='utf-8-sig'))
        rows = observation.get('replay', {}).get('C3A', {}).get('failing_rows', [])
        slots = [int(str(case.d['row_names'][i]).split('[', 1)[1].split(',')[0])
            for i in rows if str(case.d['row_names'][i]).startswith(('voltage_lower[', 'voltage_upper['))]
        if slots:
            peak = sorted(slots)[len(slots) // 2]
    history = []
    for label, charge, seconds in (
        ('F1_STATIONARY_FULL_REPRESENTATIVES', lambda u, t: False, 120.),
        ('F1_TERMINAL_REPAIRED_BEFORE_PEAK', lambda u, t: t < peak, 60.),
        ('F1_TERMINAL_REPAIRED_AFTER_PEAK', lambda u, t: t >= peak, 60.)):
        if budget.remaining() <= 0:
            break
        ids, values = values_for(case, paths, charge)
        low, high = case.d['lower'].copy(), case.d['upper'].copy()
        low[ids] = values; high[ids] = values
        if progress:
            progress(dict(phase='M_' + label, remaining_native_seconds=budget.remaining()))
        point, strict, row = _trial(case, budget, case.output / 'INITIALIZATION' / label,
            validator=validator, seconds=min(seconds, budget.remaining()), lower=low, upper=high,
            continuous=True, initialization=True, numeric_parameters=numeric_parameters)
        history.append(row)
        if strict is not None:
            write(case.output / 'SEED_BYPASS_CERTIFIED_DISPATCH.json', dict(PASS=True,
                case_sha=case.case_sha, source=label, M_SEED_optimize_calls=0,
                terminal_slot_occupancy_and_FULL_route_representatives_verified=True,
                exact_Global_UB=strict['exact_Global_UB'], initialization_native_seconds=budget.used()))
            return point, strict, history
    # One stationary free-mode MILP, then one current-day route-site MILP.
    # These preserve minimize rho_max and every original physical row.
    ids, values = values_for(case, paths, lambda u, t: False)
    route_ids = [int(j) for j in ids if not str(case.d['names'][j]).startswith('charge_mode[')]
    stationary_values = dict(zip(map(int, ids), values))
    stages = [('F2_STATIONARY_FREE_MODES', 180., True), ('F3_CURRENT_DAY_ROUTE', 240., False),
              ('F5_UNRESTRICTED_ORIGINAL_MILP', None, None)]
    for label, seconds, stationary in stages:
        if budget.remaining() <= 0:
            break
        low, high = case.d['lower'].copy(), case.d['upper'].copy()
        if stationary:
            for j in route_ids:
                low[j] = high[j] = stationary_values[j]
        elif stationary is False:
            # Existing same-day voltage sensitivity candidate ranking. Only
            # this bounded seed restriction uses it; U4 restores full domains.
            from v42_b2_seed_recovery_v18.initialization import sensitivity
            failing = []
            if receipt.exists():
                observation = json.loads(receipt.read_text(encoding='utf-8-sig'))
                for i in observation.get('replay', {}).get('C3A', {}).get('failing_rows', []):
                    failing.append(dict(domain='C3A', name=str(case.d['row_names'][i])))
            scores, _, _ = sensitivity(case, failing)
            allowed = set(sorted(case.graph[0], key=lambda site: (-scores[site], site))[:8])
            allowed.update(case.graph[1].values())
            for j in integer_representatives(case):
                name = str(case.d['names'][j])
                if name.startswith(('arc[', 'route_flow[')):
                    arc = case.graph[2][int(name.split(',')[-1][:-1])]
                    if arc[0] not in allowed or arc[2] not in allowed:
                        low[j] = high[j] = 0.
                elif name.startswith('node_activity[') and name[14:-1].split(',')[1] not in allowed:
                    low[j] = high[j] = 0.
        if progress:
            progress(dict(phase='M_' + label, remaining_native_seconds=budget.remaining()))
        point, strict, row = _trial(case, budget, case.output / 'INITIALIZATION' / label,
            validator=validator, seconds=budget.remaining() if seconds is None else min(seconds, budget.remaining()), lower=low, upper=high,
            initialization=True, numeric_parameters=numeric_parameters)
        history.append(row)
        if strict is not None:
            return point, strict, history
    return None, None, history


def fixed_route_diagnostic(case, point, grid):
    """One inexpensive opportunity screen, not a claim of attainable gain."""
    targets, _ = grid
    connected = {(r['unit'], r['site'], r['slot']) for r in inventory(case)
        if r['family'] == 'node_activity' and point[r['column']] == 1. and r['slot'] < 96}
    charges = [(str(name), float(point[j])) for j, name in enumerate(case.d['names'])
        if str(name).startswith('Pch[') and point[j] > 1e-6]
    charging_near_target = any(abs(int(name[4:-1].split(',')[-1]) - r['slot']) <= 8
        and name[4:-1].split(',')[1] == r['site'] for name, _ in charges for r in targets[:16])
    idle_dispatch = not any(abs(point[j]) > 1e-6 for j, name in enumerate(case.d['names'])
        if str(name).startswith(('Pch[', 'Pdis[')))
    current_site_opportunity = any((r['unit'], r['site'], r['slot']) in connected
        and r['numeric_score'] > 0 for r in targets[:16])
    return dict(run_once=charging_near_target or idle_dispatch and current_site_opportunity,
        current_charging_near_active_constraint=charging_near_target,
        idle_P_dispatch_with_current_site_grid_sensitivity=idle_dispatch and current_site_opportunity,
        attainable_gain_claimed=False, maximum_calls=1, requested_seconds=60.)


def _same_case_lb(case, evidence):
    if evidence is None:
        return None
    # An existing exact dual is replayed independently; metadata alone never
    # turns a restricted solver bound into a global certificate.
    if not isinstance(evidence, dict) or evidence.get('case_sha') != case.case_sha:
        raise ValueError('COMMON_M_LB_SCIENTIFIC_CASE_MISMATCH')
    dual = evidence.get('exact_original_dual')
    if not isinstance(dual, dict):
        raise ValueError('COMMON_M_EXISTING_LB_REQUIRES_ORIGINAL_DUAL')
    from v42_b2_seed_recovery_v18.certificate_box import check
    checked = check(case.A, case.d, dual, case_sha=case.case_sha)
    if checked.get('PASS') is not True:
        raise ValueError('COMMON_M_EXISTING_LB_INDEPENDENT_CHECK_FAILED')
    write(case.output / 'BEST_EXACT_ORIGINAL_DUAL.json', dual)
    write(case.output / 'BEST_EXACT_LB_CERTIFICATE.json', dict(checked,
        exact_Global_LB=checked['exact_bound'], existing_same_case_evidence_only=True,
        Native_optimize_calls=0, no_LB_optimizer_called=True))
    return F(checked['exact_bound'])


def optimize_case(case, budget, progress=None, *, stage_identity=None, initial_point=None,
                  strict_validator=None, plan_exporter=None, numeric_parameters=None,
                  certified_global_lb=None):
    """Return (result, point); stage identity never branches algorithm policy."""
    started = perf_counter()
    case.output = Path(case.output).resolve()
    case.output.mkdir(parents=True, exist_ok=True)
    stage_identity = dict(stage_identity or {})
    validator = strict_validator or _strict
    ledger = StageBudget(budget)
    if initial_point is not None:
        case.point = np.asarray(initial_point, dtype=np.float64).copy()
    point, strict, history, error = None, None, [], None
    termination = 'OPTIONAL_PRIMAL_SEARCH_EXHAUSTED'
    lb = _same_case_lb(case, certified_global_lb)
    write(case.output / 'COMMON_MESS_POLICY.json', dict(engine_version=VERSION,
        stage_identity=stage_identity, scientific_case_sha=case.case_sha,
        native_runtime_limit_seconds=NATIVE_LIMIT_SECONDS, budget_basis='MEASURED_NATIVE_RUNTIME_ONLY',
        initial_budget_used_seconds=ledger.used(), LB_optimizer_calls=0, DW_CG_Benders_calls=0,
        objective='minimize rho_max', solver_threads=1, global_gap_required_for_feasibility=False))
    try:
        point, strict, initialization = _initialize(case, ledger, validator, progress, numeric_parameters)
        history.extend(initialization)
        if point is None:
            termination = 'M_NO_VALID_FEASIBLE_WITHIN_BOUNDED_INITIALIZATION'
        else:
            initial_ub = strict['Global_UB']
            grid_cache, tried, centre_round, stagnation, auxiliary_used = {}, set(), 0, 0, False
            key = strict['point_vector_sha256']
            with ledger.cost('current_grid_bottleneck_projection', 'INITIAL_U4_GRID'):
                grid_cache[key] = current_grid(case, point, case.output / 'INITIAL_U4_GRID_PROJECTION.json')
            diagnosis = fixed_route_diagnostic(case, point, grid_cache[key])
            write(case.output / 'FIXED_ROUTE_DIAGNOSTIC.json', diagnosis)
            if diagnosis['run_once'] and ledger.remaining() >= 60:
                ids = [j for j in integer_representatives(case)
                    if not str(case.d['names'][j]).startswith('charge_mode[')]
                low, high = case.d['lower'].copy(), case.d['upper'].copy()
                low[ids] = point[ids]; high[ids] = point[ids]
                point, strict, row = _trial(case, ledger, case.output / 'FIXED_ROUTE_DISPATCH',
                    validator=validator, seconds=60., lower=low, upper=high,
                    point=point, strict=strict, numeric_parameters=numeric_parameters)
                history.append(row)
            for iteration in range(128):
                if ledger.remaining() <= 0:
                    termination = 'NATIVE_1800_SECONDS_EXHAUSTED'; break
                if lb is not None and (F(strict['exact_Global_UB']) - lb) / abs(F(strict['exact_Global_UB'])) <= F(3, 100):
                    termination = 'INDEPENDENT_GLOBAL_GAP_3_PERCENT_CERTIFIED'; break
                key = strict['point_vector_sha256']
                if key not in grid_cache:
                    with ledger.cost('current_grid_bottleneck_projection', f'U4_GRID_{iteration:03d}'):
                        grid_cache[key] = current_grid(case, point, case.output / f'U4_GRID_{iteration:03d}.json')
                method = 'U4'
                if stagnation >= 2:
                    if auxiliary_used or ledger.remaining() < 60:
                        break
                    method, auxiliary_used = 'U1', True
                spec = select(case, point, method, centre_round, grid_cache[key])
                trial_key = (key, spec['neighborhood_signature'])
                if trial_key in tried or not spec['route_openness']['PASS']:
                    write(case.output / f'{iteration:03d}_{method}_SKIPPED.json', dict(spec,
                        skipped=True, reason='SAME_FAILED_SEARCH_NOT_REPEATED' if trial_key in tried else 'ROUTE_CLOSED_BINARY_BOX'))
                    termination = 'NO_NEW_ROUTE_OPEN_NEIGHBORHOOD'; break
                tried.add(trial_key)
                if progress:
                    progress(dict(phase='M_COMMON_' + method, engine_version=VERSION,
                        verified_UB=strict['Global_UB'], native_runtime_seconds=ledger.used(),
                        remaining_native_seconds=ledger.remaining(), hamming_radius=spec['hamming_radius']))
                low, high = case.d['lower'].copy(), case.d['upper'].copy()
                fixed = spec['fixed_binary_columns']
                low[fixed] = point[fixed]; high[fixed] = point[fixed]
                seconds = 90. if iteration == 0 else 300. if stagnation == 0 else 180.
                point, strict, row = _trial(case, ledger, case.output / f'{iteration:03d}_{method}',
                    validator=validator, seconds=min(seconds, ledger.remaining()), lower=low, upper=high,
                    point=point, strict=strict, spec=spec, numeric_parameters=numeric_parameters)
                history.append(row)
                if row['certified_gain'] > 1e-11:
                    stagnation, centre_round = 0, 0
                else:
                    stagnation += 1
                    centre_round = min(centre_round + 1, 2)
                write(case.output / 'PRIMAL_SCHEDULER_AUDIT.json', dict(engine_version=VERSION,
                    case_sha=case.case_sha, history=history, no_LB_research_calls=True,
                    repeated_failed_neighborhoods=False, cumulative_native_runtime_seconds=ledger.used()))
    except Exception as failure:
        from v42_svr11.anytime import enabled,normal_budget_exception
        if enabled() and normal_budget_exception(failure):
            termination = 'NATIVE_1800_SECONDS_EXHAUSTED'
        else:
            error = type(failure).__name__ + ': ' + str(failure)
            termination = 'INPUT_OR_IMPLEMENTATION_FAILURE'
            write(case.output / 'COMMON_MESS_ERROR.json', dict(error=error, case_sha=case.case_sha))
    if point is not None:
        strict = _validate(case, point, case.output / 'BEST_STRICT_UB_POINT.npz', validator,
            ledger, 'COMMON_M_FINAL_FULL_LITERAL_INTEGER_PHYSICAL_REPLAY')
        if strict is None:
            point = None; termination = 'M_FINAL_ORIGINAL_FULL_REPLAY_FAILED'
        else:
            write(case.output / 'BEST_STRICT_UB_CERTIFICATE.json', strict)
            case.point = point.copy()
    ub = None if strict is None else F(strict['exact_Global_UB'])
    if lb is not None and (ub is None or lb > ub):
        raise ValueError('COMMON_M_EXISTING_LB_EXCEEDS_VERIFIED_UB')
    gap = None if lb is None or ub is None else F(0) if ub == 0 else (ub - lb) / abs(ub)
    certified = gap is not None and gap <= F(3, 100)
    feasible = point is not None and error is None
    plan = None
    if feasible:
        if plan_exporter is None:
            from v42_may_campaign_native90.m_stage import _plan
            plan_exporter = _plan
        plan = plan_exporter(case, point)
    time_limited = ledger.remaining() <= 0 or any(r.get('Native_status') == 9 for r in history)
    status = 'GLOBAL_GAP_CERTIFIED' if feasible and certified else (
        'TIME_LIMIT_FEASIBLE' if time_limited else 'FEASIBLE_ACCEPTED') if feasible else (
        'INPUT_OR_SOURCE_FAILURE' if error else 'M_NO_VALID_FEASIBLE')
    from v42_svr11.anytime import enabled
    if enabled() and time_limited and error is None:
        status='TIME_LIMIT_FEASIBLE_ACCEPTED' if feasible else 'TIME_LIMIT_NO_FEASIBLE'
    result = dict(engine_version=VERSION, algorithm_version=VERSION,
        day=case.bundle['day'], arm=stage_identity.get('arm', case.identity.get('arm', 'B2')),
        stage=stage_identity.get('stage', 'M'), stage_identity=stage_identity,
        case_sha=case.case_sha, scientific_case_sha=case.case_sha,
        matrix_sha=case.identity.get('original_matrix_sha'),
        domain_sha=case.identity.get('original_domain_sha'),
        C3A_matrix_sha=case.identity.get('selected_matrix_sha'),
        C3A_domain_sha=case.identity.get('selected_domain_sha'),
        fixed_input_sha=stage_identity.get('fixed_input_sha'),
        source_SHA=stage_identity.get('source_SHA', stage_identity.get('implementation_SHA',
            stage_identity.get('source_sha'))),
        accepted=feasible, feasible_accepted=feasible, PASS=feasible,
        global_gap_certified=bool(feasible and certified), verified_UB=None if ub is None else strict['Global_UB'],
        UB=None if ub is None else strict['Global_UB'], exact_Global_UB=None if ub is None else str(ub),
        certified_Global_LB=None if lb is None else float(lb), global_LB=None if lb is None else float(lb),
        LB=None if lb is None else float(lb), exact_Global_LB=None if lb is None else str(lb),
        gap=None if gap is None else float(gap), certified_gap=None if gap is None else float(gap),
        exact_gap=None if gap is None else str(gap), target_gap=.03,
        native_best_bound_diagnostic=next((r['native_best_bound_diagnostic'] for r in reversed(history)
            if r.get('native_best_bound_diagnostic') is not None), None),
        termination_reason=termination, termination=termination, status=status, classification=status,
        Native_Runtime=ledger.used(), native_seconds=ledger.used(), native_runtime_seconds=ledger.used(),
        native_calls=len(ledger.calls), native_runtime_limit_seconds=NATIVE_LIMIT_SECONDS,
        native_budget_overshoot_seconds=max(0., ledger.used() - NATIVE_LIMIT_SECONDS),
        deadline_PASS=ledger.used() <= NATIVE_LIMIT_SECONDS,
        stage_wall_seconds=perf_counter() - started, wall_seconds=perf_counter() - started,
        initial_verified_UB=locals().get('initial_ub'), error=error, planning=case.planning, mess=plan,
        P2_calls=0, AIDC_optimization_calls=0, LB_optimizer_calls=0, DW_CG_Benders_calls=0,
        historical_bounds_points_columns_read=0,
        certificate=dict(strict_UB=record(case.output / 'BEST_STRICT_UB_CERTIFICATE.json') if point is not None else None,
            exact_LB=record(case.output / 'BEST_EXACT_LB_CERTIFICATE.json') if lb is not None else None,
            original_domain_equivalence=case.identity.get('transport')),
        output=str(case.output))
    if feasible:
        result['mess_plan'] = record(case.output / 'OPTIMIZED_MESS_PLAN.json')
    write(case.output / 'M_STAGE_RESULT.json', result)
    return result, point
