"""Native worker derived from PR219; separate source and research outputs."""
from __future__ import annotations
import argparse,gc,math,subprocess,sys,time,traceback
from pathlib import Path
import numpy as np
from tools.global_local_multistart1800.adapter_v2 import *
from tools.u4_primal_alns.pilot import PARAMS as PR216_PARAMS, finite_attr
from v42_m1_research.check_ub import vector_sha
require=v.require
GLOBAL_LB=.46498486997548166
def native(args):
    """Worker exits before any FULL CSR validation is loaded."""
    load_native_case, audit_neighborhood = v.load_native_case, audit
    from v42_common_mess.model import build
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    began = time.perf_counter()
    spec = read(args.spec)
    center = None if args.center is None else v.load_point(args.center)
    PARAMS = dict(PR216_PARAMS, Method=1 if args.method == "INITIALIZE" else 2)
    require(0 < args.seconds <= 300, 'FINITE_CUMULATIVE_TIMELIMIT_REQUIRED')
    require(read(DOCS/'PR220_WARM_START_CERTIFICATE.json')['PASS'], 'WARM_AUTHORITY_REQUIRED')
    guard()
    pre = r.audit('PRE_NATIVE_BUILD')
    write(out / 'PRE_BUILD_GATE.json', pre)
    require(pre['PASS'], 'PRE_BUILD_RESOURCE_OR_SOURCE_GATE')
    case = load_native_case()
    case.point = None # Only explicit independently FULL-verified center may be a start.
    if center is not None:
        require(args.center.resolve().is_relative_to((DOCS/"calls").resolve()) or (args.center.resolve()==(ROOT/RAW_REL).resolve() and v.file_sha(args.center)==RAW_SHA), "ONLY_PR220_OR_THIS_CANARY_VERIFIED_START")
    pre_build = r.memory()
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
                  initial_point=None if center is None else record(args.center), center_vector_sha256=None if center is None else vector_sha(center),
                  PR220_verified_warm_start=center is not None, stage=spec['stage'],
                  restricted_ObjBound_is_Global_LB=False, existing_Global_LB=GLOBAL_LB,
                  unrestricted_Full_global_BB_calls=0, captures=[], resource_samples=[],
                  callback_errors=[], source_parameters=PARAMS, ACTUAL='ACTUAL_NOT_RUN')
    ledger['execution_source_seal'] = record(DOCS/'EXECUTED_SOURCE_HASHES.json')
    ledger['specification_input'] = record(args.spec)
    write(out / 'NATIVE_CALL.json', ledger)
    try:
        # Common build spec=None permits exact continuous route fixation. Its
        # spec=None continuous-bound check is vacuous; the adapter's separate
        # restriction receipt above proves every continuous change explicitly.
        model, variables, common_identity = build(case, out, lower=lower, upper=upper,
                                                  start=center, spec=None,
                                                  numeric_parameters=PARAMS)
        require(not common_identity['unrestricted_original_C3A_MILP'], 'FORBIDDEN_UNRESTRICTED_MODEL')
        hamming = None if args.method == 'ROUTE_FIXED' else model.addConstr(coefficients @ variables[free] <= rhs,
                                 name='INTEGRATED_ROUTE_ONLY_HAMMING_NEVER_GLOBAL_CUT')
        model.Params.TimeLimit = args.seconds
        model.update()
        import gurobipy as gp
        if hamming is not None:
            row = model.getRow(hamming)
            actual = {int(row.getVar(i).index): float(row.getCoeff(i)) for i in range(row.size())}
            expected = {int(j): float(c) for j,c in zip(free,coefficients)}
            require(actual == expected and hamming.RHS == rhs and hamming.Sense == '<', 'HAMMING_NATIVE_READBACK')
        if center is None:
            require(model.NumStart == 0, 'COLD_MUST_HAVE_NO_MIP_START')
        ledger['actual_NumStart'] = model.NumStart
        goal = spec.get('improvement_goal')
        require(goal is None,'CENTER_EXCLUDING_OBJECTIVE_CAP_FORBIDDEN_IN_THIS_WARM_STUDY')
        if goal is not None:
            rho = int(np.flatnonzero(case.d['names']=='rho_max')[0])
            goalrow = model.addConstr(variables[rho] <= goal, name='RESTRICTED_IMPROVEMENT_GOAL_NEVER_GLOBAL')
            model.update()
            actual_goal=model.getRow(goalrow)
            require(actual_goal.size()==1 and actual_goal.getVar(0).index==rho and actual_goal.getCoeff(0)==1. and goalrow.RHS==goal and goalrow.Sense=='<', 'IMPROVEMENT_GOAL_NATIVE_READBACK')
        ledger['improvement_goal']=goal
        ledger['stationary_control']=bool(spec.get('stationary_control'))
        if args.method == 'ROUTE_LOCAL_BRANCHING':
            modes=np.flatnonzero(np.char.startswith(case.d['names'],'charge_mode['))
            nonroute=(case.d['types']=='C') & ~np.char.startswith(case.d['names'],'route_flow[')
            local_checks=dict(original_rows_RHS_sense_objective_types_exact=all(common_identity['checks'].values()),
                all384_modes_free=len(modes)==384 and np.array_equal(np.asarray(variables.LB)[modes],case.d['lower'][modes]) and np.array_equal(np.asarray(variables.UB)[modes],case.d['upper'][modes]),
                power_SOC_helpers_bounds_unchanged=np.array_equal(lower[nonroute],case.d['lower'][nonroute]) and np.array_equal(upper[nonroute],case.d['upper'][nonroute]),
                center_and_different_moving_witness=proof['PASS'] and len(proof['witnesses'])>0,
                Hamming_excludes_all_Modes=not set(free)&set(modes),
                one_route_only_Hamming_row=model.NumConstrs==case.A.shape[0]+1 and hamming is not None,
                unchanged_raw_Start=model.NumStart==1 and np.array_equal(np.asarray(variables.Start),center),
                actual_Start_vector_SHA=vector_sha(np.asarray(variables.Start))==vector_sha(center))
            require(all(local_checks.values()),'LOCAL_BRANCHING_NATIVE_READBACK_FAILED')
            write(out/'ROUTE_LOCAL_BRANCHING_NATIVE_READBACK.json',dict(PASS=True,checks=local_checks,
                radius=spec['hamming_radius'],Hamming_columns=len(free),source_binary_count=9322,
                actual_free_binary=spec['actual_free_binary'],actual_fixed_binary=spec['actual_fixed_binary'],
                native_Start_vector_SHA=vector_sha(np.asarray(variables.Start)),center_box_residual=proof['center_box_residual']))
        if args.method == 'ROUTE_FIXED':
            ids=np.asarray(spec['route_fixed_columns'],dtype=int)
            vals=np.asarray(spec['route_fixed_values'],dtype=float)
            modes=np.flatnonzero(np.char.startswith(case.d['names'],'charge_mode['))
            route_checks=dict(
                MOVE_arc_count_positive_or_explicit_control=spec['moves']>=1 or bool(spec.get('stationary_control')),
                new_route_differs_from_original_N1_or_explicit_control=spec['paths']!=stationary_paths(case) or bool(spec.get('stationary_control')),
                all_Node_Arc_Flow_bounds_match_new_route=np.array_equal(np.asarray(variables.LB)[ids],vals) and np.array_equal(np.asarray(variables.UB)[ids],vals),
                all384_modes_free=len(modes)==384 and np.array_equal(np.asarray(variables.LB)[modes],case.d['lower'][modes]) and np.array_equal(np.asarray(variables.UB)[modes],case.d['upper'][modes]),
                original_ETA_energy_aliases_PASS=proof['PASS'],
                full_original_SOC_PCS_Grid_rows_unchanged=common_identity['checks']['original_source_rows_exact'],
                no_incompatible_N1_Start=model.NumStart==0,
                no_added_route_mixing_or_hamming=model.NumConstrs==case.A.shape[0]+int(goal is not None))
            require(all(route_checks.values()),'MOVING_ROUTE_NATIVE_READBACK_FAILED')
            write(out/'MOVING_ROUTE_NATIVE_READBACK.json',dict(PASS=True,checks=route_checks,
                candidate_id=spec['candidate_id'],moves=spec['moves'],paths=spec['paths']))
        params = {key: getattr(model.Params, key) for key in PARAMS}
        params['TimeLimit'] = model.Params.TimeLimit
        require(all(params[key] == value for key, value in PARAMS.items()), 'PARAMETER_READBACK_DRIFT')
        identity = dict(PASS=True, common_model_identity=record(out/'MODEL_IDENTITY.json'),
                        common_builder_reused_unchanged=True, original_Dense_rows_exact=True,
                        added_rows=int(hamming is not None)+int(goal is not None), model_rows=model.NumConstrs, model_columns=model.NumVars,
                        total_binary=int(np.count_nonzero(case.d['types'] != 'C')),
                        restrictions=restrictions, actual_parameter_readback=params,
                        native_hamming_exact=True, unrestricted_global_BB=False,
                        common_spec_None_continuous_check_vacuous=True,
                        continuous_bound_changes_certified_by_adapter=True)
        write(out / 'ADAPTER_MODEL_IDENTITY.json', identity)
        post_build = r.memory()
        gate = r.admit(pre_build, post_build)
        write(out / 'POST_BUILD_NATIVE_ADMISSION.json', gate)
        require(gate['PASS'], 'POST_BUILD_NATIVE_ADMISSION_REJECTED')
        # Close the entry/build race: verify the sealed code and policy again
        # immediately before the immutable model's single Optimize call.
        guard()
        ledger['model_build_wall_seconds'] = time.perf_counter() - began
        ledger['parameter_readback'] = params
        ledger['build_memory_before'] = pre_build
        ledger['build_memory_after'] = post_build
        next_gate = 0.
        best_seen = math.inf if center is None else float(case.d['objective'] @ center + float(case.d['constant']))
        center_UB = best_seen
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
                    sample = r.memory()
                    guard()
                    safety = r.callbackcheck()
                    ledger['resource_samples'].append(dict(Native_elapsed=runtime, sample=sample, safety=safety))
                    if not safety['PASS']:
                        stop_reason = 'RESOURCE_OR_SOURCE_CALLBACK_GATE'
                        m.terminate()
                        return
                    write(out / 'LIVE_NATIVE.json', dict(method=args.method, Native_elapsed=runtime,
                          observed_incumbent=None if not math.isfinite(best_seen) else best_seen, validated_new_UB=False, memory=sample))
                if where == gp.GRB.Callback.MESSAGE:
                    text = m.cbGet(gp.GRB.Callback.MSG_STRING)
                    if text.lstrip().startswith('Root relaxation: objective') and not any(
                            token in text.lower() for token in ('interrupted','time limit','infeasible','unbounded')):
                        root_complete = runtime
                if where == gp.GRB.Callback.MIPSOL:
                    objective = float(m.cbGet(gp.GRB.Callback.MIPSOL_OBJ))
                    if objective < best_seen - 1e-8:
                        raw = np.asarray(m.cbGetSolution(variables), dtype=np.float64)
                        path = out / f'RAW_{len(ledger["captures"]):03d}.npz'
                        np.savez_compressed(path, point=raw)
                        ledger['captures'].append(dict(file=record(path), Solver_ObjVal=objective,
                              discovered_Native_seconds=runtime, vector_sha256=vector_sha(raw), validated=False))
                        best_seen = objective
                        write(out / 'NATIVE_CALL.json', ledger)
                        if center is not None and objective <= center_UB - DELTA:
                            stop_reason = 'FIRST_STRICT_IMPROVEMENT_RAW_EXIT_FOR_FULL_REPLAY'
                            m.terminate()
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
            ledger['after_native_memory'] = r.memory()
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



if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--mode',choices=['native','validate'],required=True)
    parser.add_argument('--method');parser.add_argument('--spec',type=Path);parser.add_argument('--center',type=Path)
    parser.add_argument('--output',type=Path);parser.add_argument('--seconds',type=float);parser.add_argument('--point',type=Path)
    parser.add_argument('--solver-objective',type=float);parser.add_argument('--replay',type=Path)
    args=parser.parse_args()
    if args.mode=='native':sys.exit(native(args))
    elif args.mode=='selector':
        case=v.load_native_case();x=v.load_point(args.center)
        spec=make_spec(case,x,'U4',{},args.replay)
        low,high,*_=restriction(case,x,spec);assert audit(case,x,spec,low,high)['PASS']
        write(args.output,spec)
    else:
        try:result=v.validate(args.point,solver_objective=args.solver_objective,output=args.output)
        except Exception as exc:
            write(args.output,dict(PASS=False,error=repr(exc),traceback=traceback.format_exc(),Raw_not_repaired=True));raise
        sys.exit(0 if result['PASS'] else 2)
