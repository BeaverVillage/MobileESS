"""Equal-budget UB comparison from one strict frozen incumbent.

Native calls are exclusively delegated to the new shared ledger. No production
backend or prior evidence is edited. Restricted bounds never certify global LB.
"""
import csv
import json
from pathlib import Path
from time import perf_counter
import numpy as np
import gurobipy as gp
from v42_m1_research.check_ub import validate_candidate, vector_sha
from v42_m1_research.check_joint import check_exact_integer_replay
from .neighborhood import select


def _write(path, value):
    def convert(v):
        if isinstance(v, np.ndarray):
            return v.tolist()
        if isinstance(v, np.generic):
            return v.item()
        raise TypeError(type(v).__name__)
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, default=convert)+'\n', encoding='utf-8')


def validate_strict(case, raw):
    try:
        replay = validate_candidate(case, raw)
        exact = check_exact_integer_replay(replay)
        return dict(PASS=bool(replay['PASS'] and exact), point_sha256=vector_sha(raw),
                    objective=replay.get('objective'), independent_replay=replay,
                    full_exact_integer_PASS=bool(exact), repairs=0, clipping=0, rounding=0)
    except Exception as exc:
        return dict(PASS=False, point_sha256=vector_sha(raw),
                    objective=float(case.d['objective']@raw+float(case.d['constant'])) if np.isfinite(raw).all() else None,
                    independent_replay=locals().get('replay'), full_exact_integer_PASS=False,
                    error=type(exc).__name__+': '+str(exc), repairs=0, clipping=0, rounding=0)


def build_model(case, point, method, reports, projection_path, *, start_replay=None):
    t = perf_counter(); reports = Path(reports).resolve()
    if reports.drive.upper() != 'D:':
        raise ValueError('HYBRID_UB_OUTPUTS_MUST_BE_ON_D')
    reports.mkdir(parents=True, exist_ok=True)
    start = start_replay or validate_strict(case, point)
    if not start['PASS'] or start['point_sha256'] != vector_sha(point):
        raise ValueError('STRICT_ORIGINAL_REPLAY_REQUIRED_BEFORE_MIP_START')
    spec = select(case, point, method, projection_path)
    lower, upper = case.d['lower'].copy(), case.d['upper'].copy()
    fixed, free = spec['fixed_binary_columns'], spec['free_binary_columns']
    lower[fixed] = point[fixed]; upper[fixed] = point[fixed]
    model = gp.Model('V42_M1_HYBRID_UB_'+method)
    try:
        model.Params.OutputFlag = 1
        model.Params.LogFile = str(reports/(method+'_NATIVE.log'))
        for name, value in dict(Threads=1, FeasibilityTol=1e-8, OptimalityTol=1e-8,
                               IntFeasTol=1e-8, MIPGap=.005, Method=2, MIPFocus=1).items():
            setattr(model.Params, name, value)
        variables = model.addMVar(case.A.shape[1], lb=lower, ub=upper,
                                   vtype=case.d['types'], obj=case.d['objective'])
        variables.VarName = case.d['names'].tolist(); model.ObjCon = float(case.d['constant'])
        rows = model.addMConstr(case.A, variables, case.d['sense'], case.d['rhs'])
        rows.ConstrName = case.d['row_names'].tolist()
        coefficients = np.where(point[free] == 1., -1., 1.)
        model.addConstr(coefficients@variables[free] <= spec['hamming_radius']-float(np.count_nonzero(point[free])),
                        name='HYBRID_UB_RESTRICTED_HAMMING_NOT_GLOBAL_CUT')
        variables.Start = point; model.update()
        delta = model.getA()[:case.A.shape[0]]-case.A; delta.eliminate_zeros()
        continuous = case.d['types'] == 'C'
        checks = dict(original_source_rows_exact=delta.nnz == 0,
            original_RHS_exact=np.array_equal(np.asarray(model.getAttr('RHS'))[:case.A.shape[0]], case.d['rhs']),
            original_senses_exact=np.array_equal(np.asarray(model.getAttr('Sense'))[:case.A.shape[0]], case.d['sense']),
            original_objective_exact=np.array_equal(np.asarray(model.getAttr('Obj')), case.d['objective']) and model.ObjCon == float(case.d['constant']),
            all_continuous_bounds_exact=np.array_equal(lower[continuous], case.d['lower'][continuous]) and np.array_equal(upper[continuous], case.d['upper'][continuous]),
            restricted_bounds_exact=np.array_equal(np.asarray(model.getAttr('LB')), lower) and np.array_equal(np.asarray(model.getAttr('UB')), upper),
            all_original_9322_binary_types_exact=np.array_equal(np.asarray(model.getAttr('VType')), case.d['types']),
            seed_satisfies_all_restricted_fixed_bounds=bool(np.all(point >= lower-1e-8) and np.all(point <= upper+1e-8)),
            seed_local_hamming_distance_zero=True)
        if not all(checks.values()):
            raise ValueError('HYBRID_UB_ORIGINAL_MODEL_IDENTITY_DRIFT')
        spec.update(PASS=True, source_checks=checks, original_rows=case.A.shape[0],
            rows=model.NumConstrs, columns=model.NumVars, free_binary_count=len(free),
            fixed_binary_count=len(fixed), start_vector_sha256=vector_sha(point),
            strict_full_original_start_PASS=True, build_wall_seconds=perf_counter()-t,
            solver_inner_MIPGap=.005, global_goal_not_used_as_inner_stop=True,
            finite_memory_limits=False)
        _write(reports/(method+'_NEIGHBORHOOD_IDENTITY.json'), spec)
        return model, variables, spec
    except BaseException:
        model.dispose(); raise


def _bound(model):
    try:
        return float(model.ObjBound)
    except (gp.GurobiError, AttributeError):
        return None


def run(case, ledger, reports, *, seconds_each=400., projection_path=None):
    reports = Path(reports).resolve()
    if reports.drive.upper() != 'D:' or seconds_each != 400.:
        raise ValueError('REGISTERED_EQUAL_A_B_C_400_SECOND_COMPARISON_REQUIRED')
    reports.mkdir(parents=True, exist_ok=True)
    projection_path = projection_path or Path(__file__).resolve().parents[1]/'docs/v42_m1_joint_gap_research/GRID_ROW_PQ_PROJECTION_PROOF.json'
    seed = np.asarray(case.point).copy()
    with ledger.cost('validation', 'HYBRID_UB_STRICT_COMMON_SEED', track='UB'):
        initial = validate_strict(case, seed)
    if not initial['PASS']:
        raise ValueError('HYBRID_COMMON_INCUMBENT_NOT_STRICT_ORIGINAL_INTEGER')
    _write(reports/'UB_COMMON_START_REPLAY.json', initial)
    np.savez_compressed(reports/'UB_COMMON_START.npz', point=seed)
    global_point, global_ub = seed.copy(), initial['objective']
    pool = [dict(source='COMMON_STRICT_SEED', objective=global_ub,
                 case_sha=case.case_sha, point_sha256=initial['point_sha256'],
                 stored_point=str(reports/'UB_COMMON_START.npz'), PASS=True,
                 strict_full_original_integer_physical_PASS=True)]
    results, validations = [], []
    for method in ('A', 'B', 'C'):
        # Equal starting incumbent; improved results from A never warm-start B/C.
        with ledger.cost('model_build', 'HYBRID_UB_'+method, track='UB'):
            model, variables, spec = build_model(case, seed, method, reports, projection_path, start_replay=initial)
        pending = []; captured_best = initial['objective']; capture_errors = []
        def callback(m, where):
            nonlocal captured_best
            if where == gp.GRB.Callback.MIPSOL:
                try:
                    objective = float(m.cbGet(gp.GRB.Callback.MIPSOL_OBJ))
                    if objective < captured_best-1e-10:
                        point = np.asarray(m.cbGetSolution(variables), dtype=np.float64).copy()
                        pending.append((objective, point)); pending.sort(key=lambda r: r[0]); del pending[3:]
                        captured_best = objective
                except Exception as exc:
                    capture_errors.append(type(exc).__name__+': '+str(exc))
        native, error = None, None
        try:
            try:
                native = ledger.optimize(model, track='UB', label='HYBRID_UB_'+method,
                    requested_seconds=seconds_each, callback=callback)
            except Exception as exc:
                error = type(exc).__name__+': '+str(exc)
            candidates = [(f'CAPTURE_{i:02d}', raw) for i, (_, raw) in enumerate(pending)]
            if model.SolCount:
                candidates.append(('RAW_FINAL', np.asarray(variables.X).copy()))
            local_point, local_ub = seed.copy(), initial['objective']
            accepted, rejected = 0, 0
            for label, raw in candidates:
                path = reports/(method+'_'+label+'.npz')
                np.savez_compressed(path, point=raw)
                with ledger.cost('validation', 'HYBRID_UB_'+method+'_'+label, track='UB'):
                    replay = validate_strict(case, raw)
                validations.append(dict(method=method, source=label, stored_point=str(path), **replay))
                _write(reports/(method+'_'+label+'_REPLAY.json'), replay)
                if not replay['PASS']:
                    rejected += 1; continue
                if replay['objective'] < local_ub-1e-10:
                    local_ub, local_point = replay['objective'], raw.copy(); accepted += 1
                if replay['objective'] < global_ub-1e-10:
                    global_ub, global_point = replay['objective'], raw.copy()
                    pool.append(dict(source=method+'_'+label, objective=global_ub, case_sha=case.case_sha,
                        point_sha256=replay['point_sha256'], stored_point=str(path), PASS=True,
                        strict_full_original_integer_physical_PASS=True))
            np.savez_compressed(reports/(method+'_STRICT_BEST.npz'), point=local_point)
            row = dict(method=method, case_sha=case.case_sha, common_start_UB=initial['objective'],
                common_start_SHA256=initial['point_sha256'], requested_seconds=seconds_each,
                native_Runtime=float(model.Runtime), native_Work=float(model.Work),
                native_status=int(model.Status), native_SolCount=int(model.SolCount), native_error=error,
                best_strict_UB=local_ub, strict_UB_gain=initial['objective']-local_ub,
                strict_improving_candidates=accepted, rejected_raw_candidates=rejected,
                free_binary_count=spec['free_binary_count'], fixed_binary_count=spec['fixed_binary_count'],
                radius=96, captured_raw_count=len(pending), capture_errors=capture_errors,
                restricted_native_ObjBound=_bound(model), Global_LB_candidate=None,
                bound_scope='RESTRICTED_NEIGHBORHOOD_ONLY_NEVER_GLOBAL_LB',
                strict_start_feasible_for_restricted_model=True, solver_inner_MIPGap=.005,
                global_goal=.05, Native_ledger_receipt=native,
                status='STRICT_UB_IMPROVED' if local_ub < initial['objective']-1e-10 else 'NO_STRICT_UB_IMPROVEMENT')
            results.append(row); _write(reports/(method+'_RESULT.json'), row)
        finally:
            model.dispose()
    with ledger.cost('validation', 'HYBRID_UB_FINAL_STRICT_GLOBAL_BEST', track='UB'):
        final = validate_strict(case, global_point)
    if not final['PASS']:
        raise ValueError('FINAL_STRICT_UB_POOL_POINT_REPLAY_FAILED')
    np.savez_compressed(reports/'HYBRID_STRICT_BEST_POINT.npz', point=global_point)
    _write(reports/'UB_INTEGER_PHYSICAL_REPLAY.json', dict(case_sha=case.case_sha, baseline=initial, final=final, candidates=validations))
    _write(reports/'UB_INCUMBENT_POOL.json', dict(case_sha=case.case_sha, entries=pool,
        best_validated_global_UB=global_ub, admission='independent original matrix and full exact integer physical PASS',
        restricted_bounds_promoted_as_Global_LB=False))
    fields = ('method', 'common_start_UB', 'requested_seconds', 'native_Runtime', 'native_Work',
              'native_status', 'best_strict_UB', 'strict_UB_gain', 'strict_improving_candidates',
              'rejected_raw_candidates', 'free_binary_count', 'radius', 'status')
    with (reports/'UB_METHOD_COMPARISON.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore'); writer.writeheader(); writer.writerows(results)
    return dict(PASS=True, case_sha=case.case_sha, baseline_validated_global_UB=initial['objective'],
        best_validated_global_UB=global_ub, UB_improved=global_ub < initial['objective']-1e-10,
        experiments=results, strict_final_replay=final, point=global_point,
        restricted_bounds_promoted_as_Global_LB=False)


compare = run
