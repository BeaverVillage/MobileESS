"""Small active LP diagnostics and proof-gated lexicographic execution.

The backend owns scientific membership, exact block pricing and physical replay.
This runner never interprets a restricted LP failure as scientific infeasibility,
never starts a MILP before verified full-pool LP closure, and charges every native
call once to the date's single cumulative budget. Import starts no work.
"""
from pathlib import Path
from time import perf_counter
from dataclasses import asdict,is_dataclass
from fractions import Fraction
import argparse
import errno
import importlib
import inspect
import json
import os
import subprocess
import sys
import traceback
import numpy as np
import gurobipy as gp
from v42_pr134_b1.common import atomic, table, now
from .execution import STRESS_RUN_ORDER, tag_model_for_day, guard_model_optimize, install_gurobi_backstop
from .fast_execution import (CANARY_DATES, FastRunPermit, fast_run_scope, fast_native_scope,
    canonical_hash, is_sha256, require_may19_tractable)
from .fast_status import (initial_fast_status, validate_fast_status, verified_pricing_certificate)
from .solver_policy import apply_policy, validate_frozen_policy
from .fast_telemetry import FastTelemetry
from .telemetry import ResourceObservation, native_scalar
from .stress_runner import (StageBuild, LEX_ORDER, expression_for, model_census,
    other_heavy_optimizers, GlobalScientificFailure)

TRACE_FIELDS = ('date', 'lex_stage', 'iteration', 'active_stay_before', 'inactive_stay_before',
    'active_migration_before', 'inactive_migration_representation', 'LP_status', 'Farkas_or_dual_mode',
    'candidates_scanned', 'improving_candidates', 'candidates_activated', 'rows_added', 'cols_added',
    'nnz_added', 'presolved_rows', 'presolved_cols', 'root_or_LP_runtime', 'valid_bound', 'classification',
    'minimum_reduced_cost', 'median_activated_reduced_cost')


def _rows(path, rows, fields=None):
    fields = fields or (sorted(set().union(*(row.keys() for row in rows))) if rows else ['status'])
    table(path, rows, fields)


def _receipt_value(value):
    """Serialize exact pricing evidence without mutating executable Options."""
    if is_dataclass(value):return _receipt_value(asdict(value))
    if isinstance(value,Fraction):return str(value)
    if isinstance(value,dict):return {str(k):_receipt_value(v) for k,v in value.items()}
    if isinstance(value,(tuple,list,np.ndarray)):return [_receipt_value(v) for v in value]
    if isinstance(value,np.generic):return _receipt_value(value.item())
    return value


def _require_build(build, component, phase):
    if not isinstance(build, StageBuild):
        raise GlobalScientificFailure('FAST_BACKEND_CANONICAL_STAGEBUILD_REQUIRED')
    model = build.model; model.update()
    if any(getattr(model, name) for name in ('NumQConstrs', 'NumQNZs', 'NumSOS', 'NumGenConstrs')):
        raise GlobalScientificFailure('UNCHANGED_LINEAR_MILP_AUTHORITY_REQUIRED')
    meta = build.metadata
    if meta.get('scientific_identity_PASS') is not True:
        raise GlobalScientificFailure('FAST_SCIENTIFIC_INPUT_IDENTITY_REQUIRED')
    partition = meta.get('pool_partition', {})
    if (partition.get('PASS') is not True or partition.get('active_subset_physical') is not True
            or partition.get('active_union_pool_equals_physical') is not True
            or partition.get('permanent_speed_deletion') is not False
            or partition.get('inactive_candidates_materialized') is not False):
        raise GlobalScientificFailure('FAST_COMPLETE_PHYSICAL_ACTIVE_POOL_PARTITION_REQUIRED')
    if not all(is_sha256(meta.get(key)) for key in ('physical_authority_sha256', 'objective_sha256')):
        raise GlobalScientificFailure('FAST_EXACT_AUTHORITY_IDENTITIES_REQUIRED')
    if phase == 'LP' and (model.NumIntVars != 0 or not is_sha256(meta.get('lp_snapshot_sha256'))):
        raise GlobalScientificFailure('FAST_ACTUAL_CONTINUOUS_LP_SNAPSHOT_REQUIRED')
    if component != 'rho' and meta.get('stage_equivalence', {}).get('PASS') is not True:
        raise GlobalScientificFailure('FAST_CURRENT_LEX_LOCK_EQUIVALENCE_REQUIRED')


def _build(backend_method, args, folder, day, component, phase, result, resources, census):
    folder.mkdir(parents=True, exist_ok=True)
    before = perf_counter(); observer = ResourceObservation(day=day, objective=component, phase='BUILD_' + phase)
    observer.start_resources()
    try:
        build = backend_method(*args)
    finally:
        observer.stop_resources(); resources.extend(observer.resources)
        atomic(folder/'BUILD_RESOURCE_TELEMETRY.json', observer.receipt())
        _rows(result['_output']/'RESOURCE_TELEMETRY.csv', resources)
    _require_build(build, component, phase)
    tag_model_for_day(build.model, day)
    row = model_census(build.model, component, perf_counter()-before) | dict(phase=phase, folder=str(folder))
    census.append(row); _rows(result['_output']/'BUILD_PROFILE.csv', census)
    atomic(folder/'BUILD_METADATA.json', build.metadata)
    if build.metadata.get('static_artifacts'):
        atomic(folder/'EXTERNAL_STATIC_ARTIFACTS.json', dict(static_artifacts=build.metadata['static_artifacts'],
            base_matrix_sha256=build.metadata.get('base_matrix_sha256'), written_before_optimize=True))
    return build, row


def _native_call(build, day, component, phase, folder, permit, policy, result, resources, *, pricing_proof=None):
    remaining = permit.document['native_budget_seconds'] - result['native_seconds']
    if remaining <= 0:
        return None
    model = build.model
    model.setObjective(expression_for(build, component), gp.GRB.MINIMIZE); model.update()
    effective = apply_policy(model, policy, gp)
    model.setParam('TimeLimit', remaining)
    if phase == 'LP':
        # Information retrieval only: no DualReductions change or re-solve.
        model.setParam('InfUnbdInfo', 1)
    model.setParam('OutputFlag', 1); model.setParam('LogToConsole', 0)
    model.setParam('LogFile', str(folder/'NATIVE_SOLVER.log'))
    atomic(folder/'SOLVER_PARAMETERS.json', dict(effective=effective, policy=policy, parameter_sweep=False,
        TimeLimit=remaining, phase=phase, information_only_settings={'InfUnbdInfo':1} if phase=='LP' else {}))
    telemetry = FastTelemetry(model, day=day, objective=component, group=phase, remaining_seconds=remaining)
    output = result['_output']; last_output = [-5.]
    def callback(native, where):
        try:
            telemetry.callback(native, where, gp.GRB)
            elapsed = perf_counter()-telemetry.started
            if elapsed-last_output[0] >= 5:
                last_output[0] = elapsed
                atomic(output/'LIVE_PROGRESS.json', dict(day=day, component=component, phase=phase,
                    native_seconds_before_call=result['native_seconds'], stage_wall_seconds=elapsed,
                    events=telemetry.events, scientific_full_domain_optimal=False, timestamp_UTC=now()))
        except Exception as error:
            telemetry.callback_errors.append(str(error)); native.terminate()
    permit.verify()
    print('FAST_NATIVE_START', day, component, phase, 'remaining', remaining, flush=True)
    entered_native = False
    failure = None
    telemetry.start_resources()
    try:
        with fast_native_scope(model, day, phase, pricing_proof=pricing_proof):
            guard_model_optimize(model)
            entered_native = True
            model.optimize(callback)
    except Exception as error:
        failure=type(error).__name__+': '+str(error)
        raise
    finally:
        telemetry.stop_resources()
        # A guard rejection did not enter native optimize and must not inherit
        # Runtime from an earlier model state. Every entered call is fresh.
        used = native_scalar(model, 'Runtime') if entered_native else 0.
        if entered_native and used is None:
            result['unrecorded_native_seconds'] = True
        elif entered_native:
            result['native_seconds'] += used
        telemetry.finish_objective(model)
        observation = telemetry.receipt(); atomic(folder/'NATIVE_TELEMETRY.json', observation)
        resources.extend(observation['resource_samples']); _rows(output/'RESOURCE_TELEMETRY.csv', resources)
        result['budget_overshoot_seconds'] = max(0., result['native_seconds']-permit.document['native_budget_seconds'])
        if entered_native and failure is not None:
            failed=dict(component=component,phase=phase,status=native_scalar(model,'Status'),
                native_seconds=used,cumulative_native_seconds=result['native_seconds'],
                native_error=failure,telemetry=str((folder/'NATIVE_TELEMETRY.json').resolve()))
            result['native_calls'].append(failed);atomic(folder/'NATIVE_RESULT.json',failed)
    if used is None:
        raise GlobalScientificFailure('FAST_SUCCESSFUL_NATIVE_RUNTIME_UNAVAILABLE')
    if telemetry.callback_errors:
        raise GlobalScientificFailure('FAST_CALLBACK_IMPLEMENTATION_FAIL:' + str(telemetry.callback_errors))
    record = dict(component=component, phase=phase, status=int(model.Status), native_seconds=used,
        cumulative_native_seconds=result['native_seconds'], objective=native_scalar(model, 'ObjVal') if model.SolCount else None,
        bound=native_scalar(model, 'ObjBound'), Work=native_scalar(model, 'Work'),
        gap=native_scalar(model, 'MIPGap') if phase == 'MILP' and model.SolCount else None,
        telemetry=str((folder/'NATIVE_TELEMETRY.json').resolve()),fill_in=observation['fill_in'],
        presolved_matrix=observation.get('presolved_matrix'),
        model_census={key:getattr(model,name) for key,name in [('rows','NumConstrs'),('cols','NumVars'),
            ('binaries','NumBinVars'),('integer_variables','NumIntVars'),('nnz','NumNZs')]})
    if phase == 'LP' and model.Status == gp.GRB.OPTIMAL:
        record['bound'] = record['objective']
    result['native_calls'].append(record)
    atomic(folder/'NATIVE_RESULT.json', record)
    return record, observation


def _pricing_trace(day, component, iteration, build, pricing, record, observation):
    meta = build.metadata; active = meta.get('active_counts', {})
    matrix = observation.get('presolved_matrix') or {}
    row = dict.fromkeys(TRACE_FIELDS)
    row.update(date=day, lex_stage=component, iteration=iteration,
        active_stay_before=active.get('stay'), inactive_stay_before=active.get('inactive_stay'),
        active_migration_before=active.get('migration'),
        inactive_migration_representation=meta.get('inactive_migration_representation', 'LAZY_MATRIX_FREE'),
        LP_status=record['status'], Farkas_or_dual_mode=pricing.get('mode'),
        root_or_LP_runtime=record['native_seconds'], valid_bound=record['bound'],
        presolved_rows=matrix.get('rows'), presolved_cols=matrix.get('columns'))
    for name in ('candidates_scanned', 'improving_candidates', 'candidates_activated', 'rows_added',
            'cols_added', 'nnz_added', 'classification', 'minimum_reduced_cost', 'median_activated_reduced_cost'):
        row[name] = pricing.get(name,pricing.get('trace',{}).get(name))
    if type(pricing.get('candidates_activated')) is int and pricing['candidates_activated']==0:
        row.update(rows_added=0,cols_added=0,nnz_added=0)
    return row


def run_fast_date(day, backend, permit, policy, output, *, may19_receipt=None, predecessor_receipt=None):
    """One isolated day; no native solve is authorized by a CLI switch alone."""
    permit.verify(); doc = permit.document; mode = doc['mode']
    if day not in doc['run_order']:
        raise PermissionError('FAST_DATE_NOT_AUTHORIZED')
    validate_frozen_policy(policy)
    if canonical_hash(policy) != canonical_hash(json.loads(Path(doc['solver_policy']['path']).read_text(encoding='utf-8-sig'))):
        raise PermissionError('FAST_FROZEN_POLICY_RECEIPT_DRIFT')
    activation_policy=json.loads(Path(doc['activation_policy']['path']).read_text(encoding='utf-8-sig'))
    iteration_cap=activation_policy.get('max_pricing_iterations',64)
    batch_cap=activation_policy.get('max_activation_batch',256)
    if (type(iteration_cap) is not int or not 1<=iteration_cap<=10000
            or type(batch_cap) is not int or batch_cap<=0):
        raise PermissionError('FAST_BOUNDED_PREREGISTERED_ACTIVATION_REQUIRED')
    if mode == 'PRODUCTION' and day != STRESS_RUN_ORDER[0]:
        expected = STRESS_RUN_ORDER[STRESS_RUN_ORDER.index(day)-1]
        if (not isinstance(predecessor_receipt, dict) or predecessor_receipt.get('day') != expected
                or predecessor_receipt.get('permit_sha256') != permit.identity
                or predecessor_receipt.get('mode') != 'PRODUCTION'
                or predecessor_receipt.get('global_scientific_stop') is True):
            raise PermissionError('FAST_SERIAL_PREDECESSOR_RECEIPT_REQUIRED')
    if mode == 'PRODUCTION' and day in ('2025-05-12', '2025-05-10'):
        require_may19_tractable(may19_receipt, permit)
    output = Path(output).resolve()
    if (output/'FAST_STARTED.json').exists() or (output/'FAST_RESULT.json').exists():
        raise PermissionError('NO_DUPLICATE_OR_PARTIAL_FAST_RUN')
    if other_heavy_optimizers():
        raise PermissionError('OTHER_HEAVY_NATIVE_OPTIMIZER_PRESENT')
    output.mkdir(parents=True, exist_ok=True)
    result = dict(day=day, mode=mode, classification='UNRESOLVED', native_seconds=0.,
        native_budget_seconds=doc['native_budget_seconds'], budget_overshoot_seconds=0.,
        permit_sha256=permit.identity, execution_sources_sha256=canonical_hash(doc['execution_sources']),
        solver_policy_sha256=doc['solver_policy']['sha256'], activation_policy_sha256=doc['activation_policy']['sha256'],
        native_calls=[], passes=[], domain_status=initial_fast_status(), root_completed=False,
        catastrophic_root_behavior=False, may19_tractability_PASS=False, global_scientific_stop=False,
        initial_LP_bound=None, final_LP_bound=None, incumbent_support=None,
        Planning_freeze=False, Actual=False, Fresh_OpenDSS=False, other_27_dates_run=0,
        Actual_reoptimization=0, _output=output)
    resources=[]; census=[]; traces=[]; locks=[]; previous=None; active_state=None; model=None; last_build=None
    stage_order = ('rho',) if mode == 'CANARY' and day == '2025-05-19' else LEX_ORDER
    with fast_run_scope(permit):
        install_gurobi_backstop(gp)
        atomic(output/'FAST_STARTED.json', dict(day=day, mode=mode, started_UTC=now(), permit=doc, process_id=os.getpid()))
        try:
            for component in stage_order:
                pricing_proof=None
                pending_growth=None
                result['domain_status']['LP_PRICING_CLOSED']=False
                result['domain_status']['lp_pricing_certificate']=None
                for iteration in range(iteration_cap):
                    if result['native_seconds'] >= doc['native_budget_seconds']:
                        result['classification']='LP_NATIVE_BUDGET_EXHAUSTED'; break
                    folder=output/component/('LP_%04d' % iteration)
                    build, row = _build(backend.build_lp, (day,folder,component,locks,active_state),
                        folder,day,component,'LP',result,resources,census)
                    if pending_growth is not None:
                        index,prior=pending_growth
                        traces[index].update(rows_added=row['rows']-prior['rows'],
                            cols_added=row['cols']-prior['cols'],nnz_added=row['nnz']-prior['nnz'])
                        _rows(output/'ACTIVATION_TRACE.csv',traces,TRACE_FIELDS)
                        _rows(output/'PRICING_TRACE.csv',traces,TRACE_FIELDS)
                        pending_growth=None
                    model=build.model; last_build=build
                    result['domain_status']['HARD_PHYSICAL_DOMAIN_DEFINED']=True
                    if result['incumbent_support'] is None:
                        result['incumbent_support']=build.metadata.get('incumbent_support')
                    native = _native_call(build,day,component,'LP',folder,permit,policy,result,resources)
                    if native is None:
                        result['classification']='LP_NATIVE_BUDGET_EXHAUSTED'; break
                    record, observation=native
                    feasible = model.Status == gp.GRB.OPTIMAL and model.SolCount > 0
                    if feasible:
                        point=np.asarray(model.getAttr('X'),dtype=float)
                        np.savez_compressed(folder/'RAW_LP_POINT.npz',values=point)
                        verification=backend.verify_lp(build,point)
                        atomic(folder/'INDEPENDENT_LP_ROW_REPLAY.json',verification)
                        if verification.get('PASS') is not True:
                            raise GlobalScientificFailure('FAST_RAW_LP_ROW_REPLAY_FAIL')
                        result['domain_status']['ACTIVE_DOMAIN_FEASIBLE']=True
                        if component=='rho':
                            result['root_completed']=True
                            if result['initial_LP_bound'] is None:
                                result['initial_LP_bound']=record['objective']
                                result['first_root_native_seconds']=result['native_seconds']
                            result['final_LP_bound']=record['objective']
                        pricing_mode='OPTIMALITY'
                    elif model.Status == gp.GRB.INFEASIBLE:
                        pricing_mode='FEASIBILITY'
                    else:
                        result['classification']='ROOT_LP_TIMEOUT' if model.Status==gp.GRB.TIME_LIMIT else 'LP_STATUS_UNRESOLVED'
                        result['catastrophic_root_behavior']=component=='rho' and not result['root_completed']; break
                    pricing_start=perf_counter()
                    pricing=backend.price(build,pricing_mode,iteration)
                    if not isinstance(pricing,dict):
                        raise GlobalScientificFailure('FAST_PRICING_RECEIPT_REQUIRED')
                    pricing['mode']=pricing_mode
                    check=backend.verify_pricing(build,pricing,pricing_mode)
                    pricing_wall=perf_counter()-pricing_start
                    pricing['pricing_and_independent_verification_wall_seconds']=pricing_wall
                    census.append(dict(stage=component,phase='PRICING_AND_INDEPENDENT_VERIFICATION',
                        build_seconds=None,pricing_wall_seconds=pricing_wall,folder=str(folder)))
                    _rows(output/'BUILD_PROFILE.csv',census)
                    atomic(folder/'PRICING_RESULT.json',_receipt_value(pricing)); atomic(folder/'INDEPENDENT_PRICING_REPLAY.json',_receipt_value(check))
                    traces.append(_pricing_trace(day,component,iteration,build,pricing,record,observation))
                    _rows(output/'ACTIVATION_TRACE.csv',traces,TRACE_FIELDS); _rows(output/'PRICING_TRACE.csv',traces,TRACE_FIELDS)
                    # Arithmetic/path witness PASS certifies those scores only.
                    # A distinct explicit full-native closure flag is required.
                    if pricing.get('LP_PRICING_CLOSED') is True and pricing_mode=='OPTIMALITY':
                        pricing_proof=verified_pricing_certificate(build,pricing,check,day=day,component=component,locks=locks)
                        result['domain_status'].update(LP_PRICING_CLOSED=True,lp_pricing_certificate=pricing_proof)
                        atomic(folder/'LP_PRICING_CLOSURE.json',pricing_proof); break
                    activated=pricing.get('candidates_activated',0)
                    if not isinstance(activated,int) or isinstance(activated,bool) or activated<0:
                        raise GlobalScientificFailure('FAST_DETERMINISTIC_ACTIVATION_COUNT_REQUIRED')
                    if activated>batch_cap:
                        raise GlobalScientificFailure('FAST_PREREGISTERED_ACTIVATION_BATCH_EXCEEDED')
                    if activated==0:
                        traces[-1].update(rows_added=0,cols_added=0,nnz_added=0)
                        _rows(output/'ACTIVATION_TRACE.csv',traces,TRACE_FIELDS)
                        _rows(output/'PRICING_TRACE.csv',traces,TRACE_FIELDS)
                        result['classification']='LP_PRICING_UNRESOLVED' if feasible else 'RESTRICTED_LP_INFEASIBLE_DOMAIN_UNRESOLVED'; break
                    if check.get('PASS') is not True or check.get('activated_candidates_hard_valid') is not True:
                        raise GlobalScientificFailure('FAST_INDEPENDENT_HARD_VALID_ACTIVATION_REQUIRED')
                    active_state=backend.activate(active_state,pricing)
                    pending_growth=(len(traces)-1,row)
                    model.dispose(); model=None
                else:
                    result['classification']='LP_PRICING_ITERATION_LIMIT_UNRESOLVED'
                if pricing_proof is None:
                    break
                if mode=='CANARY' and day=='2025-05-19':
                    result['classification']='CANARY_LP_PRICING_CLOSED'; break
                if result['native_seconds']>=doc['native_budget_seconds']:
                    result['classification']='LEX_NATIVE_BUDGET_EXHAUSTED';break
                model.dispose(); model=None
                folder=output/component/'MILP'
                build,row=_build(backend.build_milp,(day,folder,component,locks,previous,active_state),
                    folder,day,component,'MILP',result,resources,census)
                model=build.model; last_build=build
                if (build.metadata['physical_authority_sha256']!=pricing_proof['physical_authority_sha256']
                        or build.metadata['objective_sha256']!=pricing_proof['objective_sha256']
                        or build.metadata.get('relaxed_lp_snapshot_sha256')!=pricing_proof['lp_snapshot_sha256']):
                    raise GlobalScientificFailure('FAST_MILP_MUST_MATCH_PRICED_RELAXATION')
                native=_native_call(build,day,component,'MILP',folder,permit,policy,result,resources,pricing_proof=pricing_proof)
                if native is None:
                    result['classification']='LEX_NATIVE_BUDGET_EXHAUSTED'; break
                record,observation=native; verification=None; point=None
                record.update(independently_verified=False,active_domain_objective_proven=False,
                    scientific_full_domain_optimal=False)
                if model.SolCount:
                    point=np.asarray(model.getAttr('X'),dtype=float);np.savez_compressed(folder/'RAW_INTEGER_POINT.npz',values=point)
                    verification=backend.verify(build,point,component)
                    atomic(folder/'INDEPENDENT_ORIGINAL_AND_PHYSICAL_REPLAY.json',verification)
                    if verification.get('PASS') is not True:
                        raise GlobalScientificFailure('FAST_RAW_INTEGER_ORIGINAL_PHYSICAL_REPLAY_FAIL')
                    record['independently_verified']=True
                    result['domain_status'].update(ACTIVE_DOMAIN_FEASIBLE=True,ACTIVE_DOMAIN_SOLUTION_VALID=True,
                        independent_physical_PASS=True)
                    atomic(output/'ACTIVE_DOMAIN_FEASIBLE_SCHEDULE.json',dict(day=day,accepted=False,
                        selected_jobs=verification.get('selected_jobs'),controls=verification.get('controls'),physical=verification.get('physical')))
                if component=='rho':
                    record['active_domain_objective_proven']=bool(model.Status==gp.GRB.OPTIMAL and model.SolCount
                        and record['gap'] is not None and record['gap']<=policy['parameters']['MIPGap']+1e-12)
                elif model.SolCount:
                    certificate=backend.integer_certificate(component,record['objective'],record['bound'])
                    record['integer_objective_certificate']=certificate
                    record['active_domain_objective_proven']=certificate.get('PASS') is True
                result['passes'].append(record); atomic(folder/'PASS_RESULT.json',record)
                if not record['active_domain_objective_proven']:
                    result['classification']='ACTIVE_INTEGER_OPTIMALITY_UNRESOLVED'; break
                locks.append(dict(component=component,sense='<=' if component=='rho' else '=',
                    rhs=record['objective']+1e-7 if component=='rho' else int(round(record['objective'])),
                    optimum=record['objective'],active_domain_certificate=record.get('integer_objective_certificate'),
                    current_new_run_only=True,historical_lock_imported=False))
                atomic(output/'CURRENT_NEW_AUTHORITY_LEX_LOCKS.json',locks)
                previous=dict(stage=record,point=point,verification=verification,metadata=build.metadata,
                    objective_locks=list(locks),native_model=model,stage_build=build)
                # Each next stage is fresh. The backend may retain its snapshot,
                # point and descriptor, but no native model is needed for replay.
                model.dispose();model=None
            completed=len(result['passes'])==4 and all(p['active_domain_objective_proven'] for p in result['passes'])
            result['domain_status'].update(ACTIVE_INTEGER_SOLVED=completed,all_four_active_lex_objectives_certified=completed)
            if completed:
                result['classification']='ACTIVE_DOMAIN_SOLUTION_VALID_FULL_DOMAIN_OPTIMALITY_UNRESOLVED'
            # Integer/full closure remains explicitly false unless a separate
            # independent certificate API is implemented and qualified. No
            # downstream physical execution occurs in these qualification runs.
            result['domain_status']=validate_fast_status(result['domain_status'])
            result['may19_tractability_PASS']=bool(day=='2025-05-19' and result['root_completed']
                and result['domain_status']['LP_PRICING_CLOSED'] and not result['catastrophic_root_behavior']
                and result.get('first_root_native_seconds',float('inf'))<=1800)
        except GlobalScientificFailure as error:
            result.update(classification='FAST_ACTIVE_DOMAIN_SCIENTIFIC_FAIL',global_scientific_stop=True,error=str(error))
        except gp.GurobiError as error:
            result.update(classification='UNRESOLVED',native_solver_error=str(error),global_scientific_stop=False)
        except MemoryError as error:
            result.update(classification='UNRESOLVED',computational_resource_failure=True,error=str(error))
        except OSError as error:
            resource=error.errno in (errno.ENOMEM,errno.ENOSPC,10001) or getattr(error,'winerror',None) in (8,14,1450,1455)
            result.update(classification='UNRESOLVED' if resource else 'FAST_ACTIVE_DOMAIN_SCIENTIFIC_FAIL',
                computational_resource_failure=resource,global_scientific_stop=not resource,error=str(error))
        except Exception as error:
            result.update(classification='FAST_ACTIVE_DOMAIN_SCIENTIFIC_FAIL',global_scientific_stop=True,
                error=str(error),traceback=traceback.format_exc())
        finally:
            if model is not None:model.dispose()
            result['domain_status']['ACTIVE_INTEGER_SOLVED']=bool(len(result['passes'])==4
                and all(p['active_domain_objective_proven'] for p in result['passes']))
            result['domain_status']['FULL_DOMAIN_ACCEPTED']=False
            result['domain_status']['INTEGER_DOMAIN_CLOSURE_PROVEN']=False
            result.pop('_output',None); result['finished_UTC']=now()
            atomic(output/'FAST_RESULT.json',result);atomic(output/'DOMAIN_CLOSURE_RESULT.json',result['domain_status'])
            if not (output/'ACTIVATION_TRACE.csv').exists():_rows(output/'ACTIVATION_TRACE.csv',[],TRACE_FIELDS)
            if not (output/'PRICING_TRACE.csv').exists():_rows(output/'PRICING_TRACE.csv',[],TRACE_FIELDS)
    return result


# Explicit successor API, deliberately distinct from old stress_runner.run_date.
run_date = run_fast_date


def _backend(name,permit):
    # Import/factory construction is inside the scope too: it may build static
    # models, but even an untagged hidden optimize has no authorized phase.
    with fast_run_scope(permit):
        install_gurobi_backstop(gp)
        module,attribute=name.split(':');factory=getattr(importlib.import_module(module),attribute)
        source=str(Path(inspect.getsourcefile(factory)).resolve())
        if source not in permit.document['execution_sources']:
            raise PermissionError('FAST_SCIENTIFIC_BACKEND_SOURCE_NOT_FROZEN')
        return factory()


def run_fast_sequence(backend_name,permit_path,policy_path,output):
    root=Path(output).resolve();root.mkdir(parents=True,exist_ok=True)
    permit=FastRunPermit(Path(permit_path).read_text(encoding='utf-8-sig'));permit.verify()
    results=[]; may19=None; previous=None
    for day in permit.document['run_order']:
        permit.verify()
        if day in ('2025-05-12','2025-05-10'):
            try:require_may19_tractable(may19,permit)
            except PermissionError:
                atomic(root/('MAY'+day[-2:]+'_NOT_RUN.json'),dict(day=day,classification='NOT_RUN_MAY19_TRACTABILITY_GATE'))
                continue
        folder=root/('MAY'+day[-2:]+('_CANARY' if permit.document['mode']=='CANARY' else ''))
        command=[sys.executable,'-B','-m','v42_a_stage_domain_v2.fast_runner','--day',day,
            '--permit',str(Path(permit_path).resolve()),'--policy',str(Path(policy_path).resolve()),
            '--backend',backend_name,'--output',str(folder)]
        if previous is not None:command+=['--predecessor',str(previous)]
        if may19 is not None:command+=['--may19-receipt',str(root/'MAY19'/'FAST_RESULT.json')]
        folder.mkdir(parents=True,exist_ok=True)
        kwargs={'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}
        with (folder/'WORKER_CONSOLE.log').open('x',encoding='utf8') as stream:
            process=subprocess.Popen(command,stdout=stream,stderr=subprocess.STDOUT,**kwargs)
            atomic(root/'ACTIVE_FAST_CHILD.json',dict(day=day,pid=process.pid,command=command,started_UTC=now()))
            process.wait()
        path=folder/'FAST_RESULT.json'
        result=json.loads(path.read_text()) if path.exists() else dict(day=day,classification='UNRESOLVED',
            global_scientific_stop=False,error='ISOLATED_WORKER_FAILED_WITHOUT_RECEIPT',exit_code=process.returncode)
        results.append(result);atomic(root/'FAST_SEQUENCE_RESULTS.json',results)
        if result.get('global_scientific_stop'):break
        previous=path
        if day=='2025-05-19':may19=result
    return results


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--day',choices=STRESS_RUN_ORDER)
    parser.add_argument('--permit',required=True);parser.add_argument('--policy',required=True)
    parser.add_argument('--backend',required=True);parser.add_argument('--output',required=True)
    parser.add_argument('--may19-receipt');parser.add_argument('--predecessor')
    args=parser.parse_args()
    if not args.day:
        run_fast_sequence(args.backend,args.permit,args.policy,args.output);return 0
    permit=FastRunPermit(Path(args.permit).read_text(encoding='utf-8-sig'));permit.verify()
    if args.day not in permit.document['run_order']:raise PermissionError('FAST_DATE_NOT_AUTHORIZED')
    read=lambda p:json.loads(Path(p).read_text(encoding='utf-8-sig')) if p else None
    result=run_fast_date(args.day,_backend(args.backend,permit),permit,read(args.policy),args.output,
        may19_receipt=read(args.may19_receipt),predecessor_receipt=read(args.predecessor))
    return 2 if result.get('global_scientific_stop') else 0


if __name__=='__main__':
    sys.exit(importlib.import_module('v42_a_stage_domain_v2.fast_runner').main())
