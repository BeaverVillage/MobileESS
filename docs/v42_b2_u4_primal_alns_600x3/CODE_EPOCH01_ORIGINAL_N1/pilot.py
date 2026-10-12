"""One sequential restricted primal worker, with independent post-exit replay.

No call to common engine.optimize_case (its unrestricted fallback is forbidden).
Original source modules remain byte-identical. Every new bound is diagnostic.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from fractions import Fraction
import gc
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import shutil
import sys
import time
import traceback

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
DOCS = ROOT / 'docs/v42_b2_u4_primal_alns_600x3'
UB = .6760534504652341
GLOBAL_LB = .46498486997548166
SAVED = Path(r'D:\v42_dense_response_development_repair_20261011\dates\B2\2025-05-01\attempts\native0_restored\output')
PARAMS = dict(Threads=1, FeasibilityTol=1e-9, OptimalityTol=1e-9,
              IntFeasTol=1e-8, MIPGap=.005, Method=2, MIPFocus=1,
              NumericFocus=3, ScaleFlag=2, Seed=0, MIPGapAbs=1e-10)

from v42_common_mess.storage import write, record
from v42_m1_research.check_ub import vector_sha
from tools.u4_primal_alns import resources


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def point(path):
    with np.load(path, allow_pickle=False) as z:
        return z['point'].copy()


def finite_attr(model, name):
    try:
        value = getattr(model, name)
        return value if not isinstance(value, float) or math.isfinite(value) else None
    except Exception:
        return None


def restriction(case, center, spec):
    """Fix exactly declared Binary and unselected routes; leave power/SOC free."""
    free = np.asarray(spec['free_binary_columns'], dtype=np.int64)
    fixed = np.asarray(spec['fixed_binary_columns'], dtype=np.int64)
    route = np.asarray(spec.get('fixed_route_columns', []), dtype=np.int64)
    binary = np.flatnonzero(case.d['types'] != 'C')
    require(np.array_equal(np.sort(np.r_[free, fixed]), binary), 'BINARY_PARTITION')
    require(len(np.unique(np.r_[free, fixed])) == len(binary), 'BINARY_PARTITION_DUPLICATE')
    require(np.array_equal(center[binary], np.rint(center[binary])), 'LITERAL_INTEGER_CENTER')
    require(all(str(case.d['names'][j]).startswith('route_flow[') for j in route), 'ONLY_ROUTE_FLOW_CONTINUOUS_FIX')
    require(np.all(case.d['types'][route] == 'C'), 'ROUTE_FLOW_TYPE')
    lower, upper = case.d['lower'].copy(), case.d['upper'].copy()
    fix = np.r_[fixed, route]
    lower[fix] = center[fix]
    upper[fix] = center[fix]
    require(np.all(lower >= case.d['lower']) and np.all(upper <= case.d['upper']), 'FIX_INSIDE_SOURCE_BOUNDS')
    require(np.all(center >= lower) and np.all(center <= upper), 'CENTER_EXCLUDED_BY_FIX')
    coefficients = np.where(center[free] == 1., -1., 1.)
    radius = float(spec['hamming_radius'])
    rhs = radius - float(np.count_nonzero(center[free]))
    require(radius >= 0 and float(coefficients @ center[free]) <= rhs, 'CENTER_EXCLUDED_BY_HAMMING')
    changed = np.flatnonzero((lower != case.d['lower']) | (upper != case.d['upper']))
    continuous = np.flatnonzero(case.d['types'] == 'C')
    continuous_changes = np.intersect1d(changed, continuous)
    require(set(map(int, continuous_changes)) <= set(map(int, route)), 'UNDECLARED_CONTINUOUS_RESTRICTION')
    receipt = dict(PASS=True, free_binary_count=len(free), fixed_binary_count=len(fixed),
                   fixed_continuous_route_count=len(route), hamming_radius=radius,
                   hamming_rhs=rhs, hamming_center_activity=float(coefficients @ center[free]),
                   center_point_vector_sha256=vector_sha(center), center_always_included=True,
                   original_power_SOC_and_all_nonroute_continuous_bounds_exact=True,
                   route_fix_is_primal_restriction=True, Global_LB_admissible=False)
    return lower, upper, free, coefficients, rhs, receipt


def native(args):
    """Worker exits before any FULL CSR validation is loaded."""
    from tools.u4_primal_alns.verify import load_native_case, audit_neighborhood
    from v42_common_mess.model import build
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    began = time.perf_counter()
    spec = read(args.spec)
    center = point(args.center)
    require(0 < args.seconds <= 600, 'FINITE_CUMULATIVE_TIMELIMIT_REQUIRED')
    require(read(DOCS / 'HISTORICAL_PRIMAL_ALNS_AUDIT.json')['PASS'], 'PRIMARY_HISTORY_REQUIRED')
    verify_code()
    pre = resources.audit('PRE_NATIVE_BUILD')
    write(out / 'PRE_BUILD_GATE.json', pre)
    require(pre['PASS'], 'PRE_BUILD_RESOURCE_OR_SOURCE_GATE')
    case = load_native_case()
    pre_build = resources.memory()
    lower, upper, free, coefficients, rhs, restrictions = restriction(case, center, spec)
    proof = audit_neighborhood(case, center, spec, lower, upper, output=out/'INDEPENDENT_RESTRICTION_NATIVE0.json')
    require(proof['PASS'], 'INDEPENDENT_NEIGHBORHOOD_NATIVE0')
    write(out / 'RESTRICTION_NATIVE0.json', restrictions)
    write(out / 'NEIGHBORHOOD.json', spec)
    model = None
    entered = False
    ledger = dict(schema='V42_PRIMAL_RESTRICTED_NATIVE_CALL_V1', method=args.method,
                  entered_native=False, requested_seconds=args.seconds, effective_TimeLimit=args.seconds,
                  Native_Runtime=None, runtime_unavailable=True, Native_worker=1, Threads=1,
                  initial_point=record(args.center), center_vector_sha256=vector_sha(center),
                  restricted_ObjBound_is_Global_LB=False, existing_Global_LB=GLOBAL_LB,
                  unrestricted_Full_global_BB_calls=0, captures=[], resource_samples=[],
                  callback_errors=[], source_parameters=PARAMS, ACTUAL='ACTUAL_NOT_RUN')
    write(out / 'NATIVE_CALL.json', ledger)
    try:
        # Common build spec=None permits exact continuous route fixation. Its
        # spec=None continuous-bound check is vacuous; the adapter's separate
        # restriction receipt above proves every continuous change explicitly.
        model, variables, common_identity = build(case, out, lower=lower, upper=upper,
                                                  start=center, spec=None,
                                                  numeric_parameters=PARAMS)
        require(not common_identity['unrestricted_original_C3A_MILP'], 'FORBIDDEN_UNRESTRICTED_MODEL')
        hamming = model.addConstr(coefficients @ variables[free] <= rhs,
                                 name='ALNS_PRIMAL_HAMMING_NEVER_GLOBAL_CUT')
        model.Params.TimeLimit = args.seconds
        model.update()
        import gurobipy as gp
        row = model.getRow(hamming)
        actual = {int(row.getVar(i).index): float(row.getCoeff(i)) for i in range(row.size())}
        expected = {int(j): float(c) for j, c in zip(free, coefficients)}
        require(actual == expected and hamming.RHS == rhs and hamming.Sense == '<', 'HAMMING_NATIVE_READBACK')
        params = {key: getattr(model.Params, key) for key in PARAMS}
        params['TimeLimit'] = model.Params.TimeLimit
        require(all(params[key] == value for key, value in PARAMS.items()), 'PARAMETER_READBACK_DRIFT')
        identity = dict(PASS=True, common_model_identity=record(out/'MODEL_IDENTITY.json'),
                        common_builder_reused_unchanged=True, original_Dense_rows_exact=True,
                        added_rows=1, model_rows=model.NumConstrs, model_columns=model.NumVars,
                        total_binary=int(np.count_nonzero(case.d['types'] != 'C')),
                        restrictions=restrictions, actual_parameter_readback=params,
                        native_hamming_exact=True, unrestricted_global_BB=False,
                        common_spec_None_continuous_check_vacuous=True,
                        continuous_bound_changes_certified_by_adapter=True)
        write(out / 'ADAPTER_MODEL_IDENTITY.json', identity)
        post_build = resources.memory()
        gate = resources.admit(pre_build, post_build)
        write(out / 'POST_BUILD_NATIVE_ADMISSION.json', gate)
        require(gate['PASS'], 'POST_BUILD_NATIVE_ADMISSION_REJECTED')
        ledger['model_build_wall_seconds'] = time.perf_counter() - began
        ledger['parameter_readback'] = params
        ledger['build_memory_before'] = pre_build
        ledger['build_memory_after'] = post_build
        next_gate = 0.
        best_seen = float(case.d['objective'] @ center + float(case.d['constant']))
        root_complete = None
        stop_reason = None
        def capture(m, where):
            nonlocal next_gate, best_seen, root_complete, stop_reason
            try:
                if where == gp.GRB.Callback.POLLING:
                    return
                runtime = float(m.cbGet(gp.GRB.Callback.RUNTIME))
                if runtime >= next_gate:
                    next_gate = runtime + 10.
                    sample = resources.memory()
                    safety = resources.callbackcheck()
                    ledger['resource_samples'].append(dict(Native_elapsed=runtime, sample=sample, safety=safety))
                    if not safety['PASS']:
                        stop_reason = 'RESOURCE_OR_SOURCE_CALLBACK_GATE'
                        m.terminate()
                        return
                    write(out / 'LIVE_NATIVE.json', dict(method=args.method, Native_elapsed=runtime,
                          observed_incumbent=best_seen, validated_new_UB=False, memory=sample))
                if where == gp.GRB.Callback.MESSAGE:
                    text = m.cbGet(gp.GRB.Callback.MSG_STRING)
                    if text.lstrip().startswith('Root relaxation: objective') and not any(
                            token in text.lower() for token in ('interrupted','time limit','infeasible','unbounded')):
                        root_complete = runtime
                if where == gp.GRB.Callback.MIPSOL:
                    objective = float(m.cbGet(gp.GRB.Callback.MIPSOL_OBJ))
                    if objective < best_seen:
                        raw = np.asarray(m.cbGetSolution(variables), dtype=np.float64)
                        path = out / f'RAW_{len(ledger["captures"]):03d}.npz'
                        np.savez_compressed(path, point=raw)
                        ledger['captures'].append(dict(file=record(path), Solver_ObjVal=objective,
                              discovered_Native_seconds=runtime, vector_sha256=vector_sha(raw), validated=False))
                        best_seen = objective
                        write(out / 'NATIVE_CALL.json', ledger)
            except Exception as exc:
                ledger['callback_errors'].append(repr(exc))
                stop_reason = 'CALLBACK_ERROR'
                m.terminate()
        entered = True
        ledger['entered_native'] = True
        ledger['status'] = 'INFLIGHT'
        write(out / 'NATIVE_CALL.json', ledger)
        optimize_start = time.perf_counter()
        try:
            model.optimize(capture)
            ledger['status'] = 'FINISHED'
        except Exception as exc:
            ledger.update(status='FAILED', error=repr(exc), traceback=traceback.format_exc())
        finally:
            ledger['Optimize_return_wall_seconds'] = time.perf_counter() - optimize_start
            runtime = finite_attr(model, 'Runtime')
            ledger['Native_Runtime'] = runtime
            ledger['runtime_unavailable'] = runtime is None
            ledger['Solver_return_overhead_seconds'] = None if runtime is None else max(0., ledger['Optimize_return_wall_seconds'] - runtime)
            ledger['actual_TimeLimit_overrun_seconds'] = None if runtime is None else max(0., runtime - args.seconds)
            for key in ('Status','SolCount','ObjVal','ObjBound','MIPGap','NodeCount','IterCount','BarIterCount','MemUsed','MaxMemUsed'):
                ledger[key] = finite_attr(model, key)
            ledger['root_completed_Native_seconds'] = root_complete
            ledger['callback_stop_reason'] = stop_reason
            if finite_attr(model, 'SolCount'):
                raw = np.asarray(variables.X, dtype=np.float64)
                path = out / 'FINAL_RAW.npz'
                np.savez_compressed(path, point=raw)
                ledger['captures'].append(dict(file=record(path), Solver_ObjVal=finite_attr(model,'ObjVal'),
                      discovered_Native_seconds=finite_attr(model,'Runtime'), vector_sha256=vector_sha(raw), validated=False))
            ledger['after_native_memory'] = resources.memory()
    except Exception as exc:
        ledger.update(status='FAILED' if entered else 'PRE_NATIVE_REJECTED', error=repr(exc), traceback=traceback.format_exc())
        if entered and model is not None:
            ledger['Native_Runtime'] = finite_attr(model, 'Runtime')
            ledger['runtime_unavailable'] = ledger['Native_Runtime'] is None
    finally:
        write(out / 'NATIVE_CALL.json', ledger)
        if model is not None:
            model.dispose()
        del case
        gc.collect()
        ledger['worker_wall_seconds'] = time.perf_counter() - began
        ledger['Native_Model_disposed_before_FULL_replay'] = True
        write(out / 'NATIVE_CALL.json', ledger)
    print(json.dumps(dict(output=str(out), status=ledger.get('status'), Native_Runtime=ledger.get('Native_Runtime'),
                         ObjVal=ledger.get('ObjVal'), restricted_ObjBound=ledger.get('ObjBound')), ensure_ascii=False))
    return 0 if ledger.get('status') == 'FINISHED' else 2


class ValidationBudget:
    def __init__(self):
        self.wall = []

    @contextmanager
    def cost(self, kind, label):
        began = time.perf_counter()
        try:
            yield
        finally:
            self.wall.append(dict(kind=kind, label=label, wall_seconds=time.perf_counter()-began))


def invoke(module, arguments, output):
    began = time.perf_counter()
    completed = subprocess.run([sys.executable, '-m', module, *map(str, arguments)], cwd=ROOT,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace')
    output.write_text(completed.stdout, encoding='utf-8')
    return completed.returncode, time.perf_counter()-began


def code_identity():
    paths = list((ROOT/'tools/u4_primal_alns').glob('*.py'))
    paths += [ROOT/f'v42_common_mess/{name}.py' for name in ('model','neighborhood','engine','storage')]
    paths += [ROOT/'v42_m1_research/check_ub.py', ROOT/'v42_m1_hybrid/final_verify.py']
    paths += [DOCS/name for name in ('CANDIDATE_PREREGISTRATION.json','SIGNED_SELECTION_CONTEXT.json',
              'APPROVED_SOURCE18R_NATIVE_PARAMETERS.json','INITIAL_U4_POINT.npz',
              'INITIAL_U4_FULL_REPLAY.json','INDEPENDENT_REGRESSION_TESTS.json')]
    return {str(path.relative_to(ROOT)): record(path)['sha256'] for path in sorted(paths)}


def verify_code():
    frozen = read(DOCS/'EXECUTED_SOURCE_HASHES.json')
    require(all(record(ROOT/name)['sha256'] == expected for name, expected in frozen.items()), 'EXECUTED_CODE_CHANGED')


def run(args):
    """No solver loaded in orchestrator; every Native child exits before replay."""
    from tools.u4_primal_alns.verify import load_native_case, audit_neighborhood
    from tools.u4_primal_alns.neighborhood import candidate_queue, make_spec
    methods = (args.method,) if args.method else ('N1','N2','N3')
    require(not (DOCS/'COMPARISON.json').exists(), 'SEALED_EXPERIMENT_NO_REEXECUTION')
    require(read(DOCS/'HISTORICAL_PRIMAL_ALNS_AUDIT.json')['PASS'], 'PRIMARY_HISTORY_SEAL')
    overall_began = time.perf_counter()
    original = DOCS/'INITIAL_U4_POINT.npz'
    if original.exists():
        require(record(original)['sha256'] == record(SAVED/'FINAL_FULL_POINT.npz')['sha256'], 'FROZEN_INITIAL_POINT_BYTES')
    else:
        shutil.copyfile(SAVED/'FINAL_FULL_POINT.npz', original)
    rc, initial_wall = invoke('tools.u4_primal_alns.verify',
                             ['--point',original,'--output',DOCS/'INITIAL_U4_FULL_REPLAY.json','--solver-objective',UB],
                             DOCS/'INITIAL_U4_VERIFY.log')
    initial = read(DOCS/'INITIAL_U4_FULL_REPLAY.json')
    require(rc == 0 and initial['PASS'], 'ORIGINAL_U4_FULL_NATIVE0_FAILED')
    require(float(Fraction(initial['exact_Global_UB'])) == UB, 'INITIAL_OBJECTIVE_DRIFT')
    initial_vector_sha = vector_sha(point(original))
    # Audit every finite candidate policy at the common U4 before any Optimize,
    # then audit again at the actual own-algorithm center before each call.
    native0_began = time.perf_counter()
    case = load_native_case()
    original_point = point(original)
    policy_proofs = []
    for method in methods:
        for number,candidate in enumerate(candidate_queue(method)):
            spec = make_spec(case, original_point, method, candidate)
            spec['center_full_replay'] = record(DOCS/'INITIAL_U4_FULL_REPLAY.json')
            lower,upper,*_ = restriction(case, original_point, spec)
            proof = audit_neighborhood(case, original_point, spec, lower, upper)
            require(proof['PASS'], 'PREREGISTERED_NEIGHBORHOOD_NATIVE0')
            policy_proofs.append(dict(method=method, candidate_index=number, candidate=candidate, proof=proof))
    del case, original_point, lower, upper
    gc.collect()
    write(DOCS/'PREREGISTERED_NATIVE0_POLICY.json', dict(PASS=True, candidates=policy_proofs,
                Native_optimize_calls=0, wall_seconds=time.perf_counter()-native0_began))
    write(DOCS/'EXECUTED_SOURCE_HASHES.json', code_identity())
    with (DOCS/'RUN_STARTED.json').open('x', encoding='utf-8') as stream:
        json.dump(dict(initial=record(original), initial_vector_sha256=initial_vector_sha,
                  methods=methods, per_algorithm_Native_limit=600., actual_return_reserve_seconds=1.,
                  Native_worker=1, Threads=1, source_case=initial.get('case_sha'),
                  initial_FULL_replay=record(DOCS/'INITIAL_U4_FULL_REPLAY.json'),
                  independent_initial_replay_wall_seconds=initial_wall, Global_LB=GLOBAL_LB), stream, indent=2)
    comparison = dict(schema='V42_U4_PRIMAL_ALNS_600X3_COMPARISON_V1', methods={},
                      initial_UB=UB, initial_point_vector_sha256=initial_vector_sha,
                      existing_Global_LB=GLOBAL_LB, K32_default_LB=.46497617639758426,
                      new_Global_LB_optimization_calls=0, ACTUAL='ACTUAL_NOT_RUN',
                      Native_workers=1, Threads=1, total_wall_seconds=None)
    common_integrity_stop = False
    for method in methods:
        if common_integrity_stop:
            comparison['methods'][method] = dict(method=method, initial_UB=UB, final_verified_UB=UB,
                 best_point=record(original), requested_Native_sum=0., actual_Native_sum=0., calls=[], iterations=[],
                 classification='NOT_RUN_COMMON_SOURCE_OR_MODEL_INTEGRITY', stopped_reason='COMMON_INTEGRITY_STOP')
            continue
        verify_code()
        algo_began = time.perf_counter()
        root = DOCS/method
        root.mkdir(exist_ok=False)
        candidates = candidate_queue(method)
        write(root/'FINITE_CANDIDATE_POLICY.json', candidates)
        algo = dict(method=method, initial_UB=UB, initial_point_vector_sha256=initial_vector_sha,
                    final_verified_UB=UB, best_point=record(original), calls=[], iterations=[],
                    requested_Native_sum=0., actual_Native_sum=0., Native_limit=600.,
                    improvement_count=0, first_improvement_Native_seconds=None,
                    best_acquired_Native_seconds=None, stopped_reason=None, ACTUAL='ACTUAL_NOT_RUN')
        center_path, best = original, UB
        center_replay = DOCS/'INITIAL_U4_FULL_REPLAY.json'
        seen_specs = set()
        for index, candidate in enumerate(candidates):
            actual_used = algo['actual_Native_sum']
            if actual_used is None:
                algo['stopped_reason'] = 'UNKNOWN_RUNTIME_BUDGET_QUARANTINED'
                break
            # Consumption is measured Optimize Runtime; the unused portion of
            # an early-OPTIMAL TimeLimit is not consumed. Requested totals are
            # retained separately, while the actual budget never resets.
            remaining = 600.-actual_used
            # Leave one second of measured budget for native TimeLimit return
            # granularity. It is never added to another call or algorithm.
            seconds = min(float(candidate.get('requested_cap_seconds',600.)), max(0.,remaining-1.))
            if seconds < 1.:
                algo['stopped_reason'] = 'CUMULATIVE_NATIVE_BUDGET_EXHAUSTED'
                break
            prep = root/f'iteration{index+1:02d}'
            prep.mkdir(exist_ok=False)
            iteration = dict(index=index+1, candidate=candidate, center_point=record(center_path),
                             center_UB=best, requested_seconds=seconds, Native_used_before=actual_used)
            prepare_began = time.perf_counter()
            case = None
            try:
                case = load_native_case()
                center = point(center_path)
                spec = make_spec(case, center, method, candidate)
                spec['center_full_replay'] = record(center_replay)
                lower, upper, *_ = restriction(case, center, spec)
                proof = audit_neighborhood(case, center, spec, lower, upper, output=prep/'INDEPENDENT_NATIVE0.json')
                require(proof['PASS'], 'INDEPENDENT_NEIGHBORHOOD_NATIVE0_FAILED')
                signature = hashlib.sha256(json.dumps(dict(free=sorted(spec['free_binary_columns']),
                         fixed_route=sorted(spec.get('fixed_route_columns',[])),radius=spec['hamming_radius'],
                         center=vector_sha(center)),sort_keys=True).encode()).hexdigest()
                require(signature not in seen_specs, 'REPEATED_NEIGHBORHOOD_FORBIDDEN')
                seen_specs.add(signature)
                spec['adapter_signature'] = signature
                spec['independent_native0'] = record(prep/'INDEPENDENT_NATIVE0.json')
                write(prep/'SPEC.json', spec)
                del case, center, lower, upper
                case = None
                gc.collect()
                iteration['preparation_wall_seconds'] = time.perf_counter()-prepare_began
                verify_code()
                rc, worker_wall = invoke('tools.u4_primal_alns.pilot',
                       ['--mode','native','--method',method,'--output',prep/'native',
                        '--center',center_path,'--spec',prep/'SPEC.json','--seconds',seconds], prep/'NATIVE_WORKER.log')
                call = read(prep/'native/NATIVE_CALL.json')
                iteration['worker_return_code'] = rc
                iteration['worker_process_wall_seconds'] = worker_wall
                iteration['native_receipt'] = record(prep/'native/NATIVE_CALL.json')
                algo['calls'].append(call)
                if call['entered_native']:
                    algo['requested_Native_sum'] += seconds
                    if call['runtime_unavailable']:
                        algo['actual_Native_sum'] = None
                        common_integrity_stop = True
                    else:
                        algo['actual_Native_sum'] += call['Native_Runtime']
                # Worker exit, rather than merely model.dispose(), releases all
                # native DLL/model/CSR allocations before original FULL replay.
                iteration['Native_worker_exited_before_original_FULL_replay'] = True
                validated = []
                seen_points = set()
                for number, captured in enumerate(call.get('captures',[])):
                    raw_path = Path(captured['file']['path'])
                    if captured['vector_sha256'] in seen_points:
                        continue
                    seen_points.add(captured['vector_sha256'])
                    replay_path = prep/f'REPLAY_{number:03d}.json'
                    vrc, wall = invoke('tools.u4_primal_alns.verify',
                         ['--point',raw_path,'--output',replay_path,'--solver-objective',captured['Solver_ObjVal']],
                         prep/f'VERIFY_{number:03d}.log')
                    replay = read(replay_path)
                    result = dict(raw=record(raw_path), replay=record(replay_path), PASS=vrc==0 and replay['PASS'],
                                  discovery_Native_seconds=actual_used+captured['discovered_Native_seconds'],
                                  validation_wall_seconds=wall, Solver_ObjVal=captured['Solver_ObjVal'])
                    if result['PASS']:
                        objective = float(Fraction(replay['exact_Global_UB']))
                        result['verified_UB'] = objective
                        if objective < best:
                            best = objective
                            center_path = raw_path
                            center_replay = replay_path
                            algo['improvement_count'] += 1
                            if algo['first_improvement_Native_seconds'] is None:
                                algo['first_improvement_Native_seconds'] = result['discovery_Native_seconds']
                            algo['best_acquired_Native_seconds'] = result['discovery_Native_seconds']
                    validated.append(result)
                    # Persist each accepted or rejected independent replay now.
                    write(prep/'VALIDATED_CANDIDATES.json', validated)
                iteration['validated_candidates'] = validated
                iteration['ending_verified_UB'] = best
                if call.get('callback_stop_reason') or rc != 0 or call.get('Status') == 12:
                    algo['stopped_reason'] = 'NUMERIC_OR_RESOURCE_STOP'
                if call['entered_native'] and call['runtime_unavailable']:
                    algo['stopped_reason'] = 'UNKNOWN_RUNTIME_BUDGET_QUARANTINED'
                if call.get('Status') in (3,4,5):
                    common_integrity_stop = True
                    algo['stopped_reason'] = 'COMMON_MODEL_INTEGRITY_CONTRADICTS_VERIFIED_CENTER'
                common_markers = ('SOURCE_FILE_SHA_DRIFT','SOURCE_DOMAIN_SHA_DRIFT','SOURCE_CSR_SHA_DRIFT',
                                  'EXECUTED_CODE_CHANGED','COMMON_M_ORIGINAL_MODEL_IDENTITY_DRIFT')
                if any(marker in call.get('error','') for marker in common_markers):
                    common_integrity_stop = True
                    algo['stopped_reason'] = 'COMMON_SOURCE_OR_MODEL_INTEGRITY'
                if method == 'N1' and call.get('Status') == 2 and not call.get('callback_stop_reason'):
                    algo['stopped_reason'] = 'WHOLE_96_SLOT_MODE_MODEL_OPTIMAL_WITH_APPROVED_MIPGAP'
            except Exception as exc:
                iteration['error'] = repr(exc)
                iteration['traceback'] = traceback.format_exc()
                algo['stopped_reason'] = 'NATIVE0_OR_EXECUTION_REJECTED'
                if any(marker in repr(exc) for marker in ('SOURCE','MODEL_IDENTITY','EXECUTED_CODE','DENSE_MODEL_IDENTITY')):
                    common_integrity_stop = True
                    algo['stopped_reason'] = 'COMMON_SOURCE_OR_MODEL_INTEGRITY'
            finally:
                # Also release a rejected preparatory model before moving to
                # the next independent algorithm; no hidden CSR survives.
                case = None
                gc.collect()
            algo['iterations'].append(iteration)
            algo['final_verified_UB'] = best
            algo['best_point'] = record(center_path)
            write(root/'ALGORITHM_LEDGER.json', algo)
            print(json.dumps(dict(method=method, iteration=index+1, verified_UB=best,
                         actual_Native_sum=algo['actual_Native_sum'], requested_Native_sum=algo['requested_Native_sum'],
                         stopped_reason=algo['stopped_reason']), ensure_ascii=False), flush=True)
            if algo['stopped_reason']:
                break
        if algo['stopped_reason'] is None:
            algo['stopped_reason'] = 'FINITE_NONREPEATING_CANDIDATE_POLICY_EXHAUSTED'
        gain = UB-best
        algo.update(absolute_UB_gain=gain, relative_UB_gain_percent=100*gain/UB,
                    Global_gap_percent=100*(best-GLOBAL_LB)/best, overall_wall_seconds=time.perf_counter()-algo_began)
        algo['classification'] = ('NUMERIC_OR_RESOURCE_STOP' if algo['stopped_reason'] in (
                'NUMERIC_OR_RESOURCE_STOP','NATIVE0_OR_EXECUTION_REJECTED','UNKNOWN_RUNTIME_BUDGET_QUARANTINED',
                'COMMON_MODEL_INTEGRITY_CONTRADICTS_VERIFIED_CENTER','COMMON_SOURCE_OR_MODEL_INTEGRITY') else
                'UB_GAIN_STRONG' if gain >= .010 else 'UB_GAIN_MATERIAL' if gain >= .005 else
                'UB_NONMATERIAL' if gain > 0 else 'NO_VALID_IMPROVEMENT')
        write(root/'ALGORITHM_LEDGER.json', algo)
        comparison['methods'][method] = algo
        write(DOCS/'LIVE_COMPARISON.json', comparison)
    comparison['total_wall_seconds'] = time.perf_counter()-overall_began
    comparison['total_requested_Native_seconds'] = sum(a['requested_Native_sum'] for a in comparison['methods'].values())
    runtimes = [a['actual_Native_sum'] for a in comparison['methods'].values()]
    comparison['total_actual_Native_seconds'] = None if None in runtimes else sum(runtimes)
    comparison['best_verified_UB'] = min([UB]+[a['final_verified_UB'] for a in comparison['methods'].values()])
    comparison['winner'] = [name for name,a in comparison['methods'].items() if a['final_verified_UB']==comparison['best_verified_UB']]
    comparison['Global_gap_percent'] = 100*(comparison['best_verified_UB']-GLOBAL_LB)/comparison['best_verified_UB']
    write(DOCS/'COMPARISON.json', comparison)
    print(json.dumps(dict(output=str(DOCS/'COMPARISON.json'), best_verified_UB=comparison['best_verified_UB'],
                         winner=comparison['winner'], Native_seconds=comparison['total_actual_Native_seconds']), ensure_ascii=False),flush=True)
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=('native','run'), required=True)
    parser.add_argument('--method', choices=('N1','N2','N3'))
    parser.add_argument('--output', type=Path)
    parser.add_argument('--center', type=Path)
    parser.add_argument('--spec', type=Path)
    parser.add_argument('--seconds', type=float)
    args = parser.parse_args()
    if args.mode == 'native':
        return native(args)
    return run(args)


if __name__ == '__main__':
    raise SystemExit(main())
