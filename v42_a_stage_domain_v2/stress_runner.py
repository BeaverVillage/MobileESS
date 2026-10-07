"""Isolated sequential four-date qualification; import never starts a solve.

The backend owns scientific model assembly, exact stage projection/lifting and
independent original-row/physical replay. This module owns the immutable permit,
one cumulative native budget, frozen solver policy, observations and honest
active/full-domain classification. A child process handles exactly one date.
"""
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
import argparse
import importlib
import inspect
import json
import os
import errno
import subprocess
import sys
import traceback
import numpy as np
import psutil
import gurobipy as gp
from v42_pr134_b1.common import atomic, table, clean, now
from .execution import (STRESS_DATES,STRESS_RUN_ORDER,StressRunPermit,stress_run_scope,
    require_action_authorized,tag_model_for_day,accepted_pipeline_scope)
from .solver_policy import apply_policy
from .status import initial_domain_status,close_feasibility,validate_domain_status
from .telemetry import StressTelemetry,ResourceObservation,native_scalar


LEX_ORDER=('rho','migration_count','shift_magnitude','prestart_relocation')
OBJECTIVE_ALIASES={'rho':('rho',),'migration_count':('migration_count',),
    'shift_magnitude':('shift_magnitude','shift_slots'),
    'prestart_relocation':('prestart_relocation','prestart_changes')}


class GlobalScientificFailure(RuntimeError):
    pass


@dataclass
class StageBuild:
    model: object
    units: object
    objectives: list
    controls: object
    bindings: object
    data: tuple
    coeff: object
    metadata: dict


def expression_for(build,component):
    matches=[expr for name,expr in build.objectives if name in OBJECTIVE_ALIASES[component]]
    if len(matches)!=1:raise GlobalScientificFailure('FOUR_OBJECTIVE_SCIENTIFIC_AXIS_MISMATCH:'+component)
    return matches[0]


def model_census(model,stage,build_seconds):
    return dict(stage=stage,build_seconds=build_seconds,rows=model.NumConstrs,cols=model.NumVars,
        binaries=model.NumBinVars,integer_counts=model.NumIntVars-model.NumBinVars,
        continuous=model.NumVars-model.NumIntVars,nnz=model.NumNZs)


def other_heavy_optimizers():
    own={os.getpid()}|{p.pid for p in psutil.Process().parents()}
    names=('v42_pr134_b1.worker','v42_pr134_adaptive.solve_snapshot','v42_pr134_adaptive.minimum_probe',
        'v42_pr134_adaptive.capacity_master','v42_pr134_may19.solve','v42_pr134_may19.production',
        'v42_root.worker','v42_exact.worker','v42_single_thread.a1','v42_a_stage_domain_v2.stress_runner')
    rows=[]
    for process in psutil.process_iter(['pid','name','cmdline']):
        try:
            if process.pid in own:continue
            command=' '.join(process.info['cmdline'] or [])
            executable=str(process.info['name'] or '').lower()
            if any(name in command for name in names) or executable.startswith(('gurobi_cl','cplex','scip')):
                rows.append(dict(pid=process.pid,command=command))
        except psutil.Error:continue
    return rows


def _write_rows(path,rows):
    fields=sorted(set().union(*(row.keys() for row in rows))) if rows else ['status']
    table(path,rows,fields)


def run_date(day,backend,permit,policy,output,*,budget_seconds=3600.):
    """Run one date only after root freezes all independent PASS gate receipts."""
    if day not in STRESS_DATES:raise PermissionError('OTHER_27_MAY_DATES_NOT_AUTHORIZED')
    if budget_seconds!=3600.:raise PermissionError('FROZEN_CUMULATIVE_A1_BUDGET_REQUIRED')
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    if (output/'A1_RESULT.json').exists() or (output/'A1_STARTED.json').exists():
        raise PermissionError('NO_DUPLICATE_OR_PARTIAL_STRESS_DATE_RUN')
    permit.verify()
    contention=other_heavy_optimizers()
    if contention:raise PermissionError('OTHER_HEAVY_NATIVE_OPTIMIZER_PRESENT:'+str(contention))
    result=dict(day=day,classification='UNRESOLVED',passes=[],native_seconds=0.,
        native_budget_seconds=budget_seconds,A1_active_domain_feasible=False,
        A1_full_domain_accepted=False,Planning_freeze=False,Actual=False,Fresh_OpenDSS=False,
        physical_PASS=False,other_27_dates_run=0,Actual_reoptimization=0,PQ_repair=0,
        integer_domain_closure_proven=False,migration_pricing_closed=False,
        domain_status=initial_domain_status(hard_physical_domain_defined=True,authority='AIDC_A_STAGE_DOMAIN_AUTHORITY_V2'))
    result['domain_status'].update(ACTIVE_DOMAIN_SOLVED=False,STAY_DOMAIN_COMPLETE=False,MIGRATION_PRICING_CLOSED=False)
    census=[];progress=[];resources=[];locks=[];previous=None;model=None;last_build=None
    with stress_run_scope(permit):
        require_action_authorized(day,'A1')
        atomic(output/'A1_STARTED.json',dict(day=day,started_UTC=now(),budget_seconds=budget_seconds,
            permit=permit.document,solver_policy=policy,process_id=os.getpid(),parameter_sweep=False))
        try:
            for component in LEX_ORDER:
                permit.verify()
                remaining=budget_seconds-result['native_seconds']
                if remaining<=0:
                    result['classification']='LEX_P2_TIMEOUT' if component!='rho' else 'ROOT_LP_TIMEOUT'
                    break
                folder=output/component;folder.mkdir(exist_ok=True)
                before=perf_counter()
                build_resources=ResourceObservation(day=day,objective=component,phase='BUILD')
                build_resources.start_resources()
                try:build=backend.build(day,folder,component,locks,previous)
                finally:
                    build_resources.stop_resources()
                    resources.extend(build_resources.resources)
                    atomic(folder/'BUILD_RESOURCE_TELEMETRY.json',build_resources.receipt())
                    _write_rows(output/'RESOURCE_TELEMETRY.csv',resources)
                permit.verify()
                if not isinstance(build,StageBuild):raise GlobalScientificFailure('STRESS_BACKEND_STAGEBUILD_REQUIRED')
                model=build.model;last_build=build;tag_model_for_day(model,day);model.update()
                if model.NumQConstrs or model.NumQNZs or model.NumSOS or model.NumGenConstrs:
                    raise GlobalScientificFailure('UNCHANGED_LINEAR_MILP_AUTHORITY_REQUIRED')
                if build.metadata.get('scientific_identity_PASS') is not True:
                    raise GlobalScientificFailure('SCIENTIFIC_INPUT_OR_MODEL_IDENTITY_FAIL')
                if component!='rho' and build.metadata.get('stage_equivalence',{}).get('PASS') is not True:
                    raise GlobalScientificFailure('CURRENT_LOCKED_STAGE_EXACT_EQUIVALENCE_REQUIRED')
                if component=='rho':
                    atomic(output/'INPUT_IDENTITY.json',build.metadata['input_identity'])
                    atomic(output/'DOMAIN_CENSUS.json',build.metadata['domain_census'])
                    if not build.metadata.get('static_artifacts') or not build.metadata.get('base_matrix_sha256'):
                        raise GlobalScientificFailure('EXTERNAL_STATIC_MATRIX_BYTE_ATTESTATION_REQUIRED')
                    atomic(output/'EXTERNAL_STATIC_ARTIFACTS.json',dict(day=day,
                        static_artifacts=build.metadata['static_artifacts'],
                        base_matrix_sha256=build.metadata['base_matrix_sha256'],
                        written_before_optimize=True))
                result['domain_status']['STAY_DOMAIN_COMPLETE']=build.metadata.get('STAY_DOMAIN_COMPLETE') is True
                if not result['domain_status']['STAY_DOMAIN_COMPLETE']:
                    raise GlobalScientificFailure('EXACT_COMPLETE_STAY_SUPPORT_REQUIRED')
                row=model_census(model,component,perf_counter()-before);census.append(row)
                _write_rows(output/'MODEL_CENSUS_BY_LEX_STAGE.csv',census)
                expression=expression_for(build,component);model.setObjective(expression,gp.GRB.MINIMIZE);model.update()
                effective=apply_policy(model,policy,gp)
                model.Params.TimeLimit=remaining
                model.Params.OutputFlag=1;model.Params.LogToConsole=0;model.Params.LogFile=str(folder/'NATIVE_SOLVER.log')
                atomic(output/'SOLVER_PARAMETERS.json',dict(policy=policy,effective=effective,parameter_sweep=False))
                diagnostics=StressTelemetry(model,day=day,objective=component,
                    group='P1' if component=='rho' else 'P2',remaining_seconds=remaining)
                last_output=[-1.]
                def callback(native,where):
                    try:
                        diagnostics.callback(native,where,gp.GRB)
                        runtime=native_scalar(native,'Runtime')
                        elapsed=perf_counter()-diagnostics.started
                        if elapsed-last_output[0]>=5.:
                            last_output[0]=elapsed
                            atomic(output/'LIVE_PROGRESS.json',dict(day=day,stage=component,
                                cumulative_native_seconds_before_pass=result['native_seconds'],
                                stage_wall_seconds=elapsed,events=diagnostics.events,
                                latest=diagnostics.history[-1] if diagnostics.history else None,
                                scientific_full_domain_optimal=False,timestamp_UTC=now()))
                    except Exception as error:
                        diagnostics.callback_errors.append(str(error));native.terminate()
                print('STRESS_NATIVE_PASS_START',day,component,'remaining',remaining,'model',row,flush=True)
                diagnostics.start_resources()
                try:model.optimize(callback)
                finally:
                    diagnostics.stop_resources()
                    # Runtime belongs only to the current native optimize call.
                    # Account it once, including a call that raises GurobiError.
                    used=native_scalar(model,'Runtime')
                    if used is None:result['unrecorded_native_seconds']=True
                    else:result['native_seconds']+=used
                    diagnostics.finish_objective(model)
                    observation=diagnostics.receipt();atomic(folder/'NATIVE_TELEMETRY.json',observation)
                    progress.extend(observation['incumbent_and_bound_history']);resources.extend(observation['resource_samples'])
                    _write_rows(output/'A1_PROGRESS.csv',progress);_write_rows(output/'RESOURCE_TELEMETRY.csv',resources)
                if used is None:raise GlobalScientificFailure('SUCCESSFUL_NATIVE_RUNTIME_UNAVAILABLE')
                stage=dict(component=component,status=int(model.Status),native_seconds=used,
                    cumulative_native_seconds=result['native_seconds'],Work=native_scalar(model,'Work'),
                    node_count=native_scalar(model,'NodeCount'),objective=native_scalar(model,'ObjVal') if model.SolCount else None,
                    active_domain_global_bound=native_scalar(model,'ObjBound'),gap=native_scalar(model,'MIPGap') if model.SolCount else None,
                    model_census=row,telemetry=str((folder/'NATIVE_TELEMETRY.json').resolve()),
                    independently_verified=False,active_domain_objective_proven=False,
                    scientific_full_domain_optimal=False)
                verification=None;point=None
                if model.SolCount:
                    point=np.asarray(model.getAttr('X'),dtype=float)
                    np.savez_compressed(folder/'RAW_ACTIVE_DOMAIN_POINT.npz',values=point)
                    verification=backend.verify(build,point,component)
                    atomic(folder/'INDEPENDENT_ORIGINAL_AND_PHYSICAL_REPLAY.json',verification)
                    if verification.get('PASS') is not True:
                        raise GlobalScientificFailure('NEW_AUTHORITY_ORIGINAL_PHYSICAL_POINT_REPLAY_FAIL')
                    stage['independently_verified']=True;result['A1_active_domain_feasible']=True
                    result['domain_status']=close_feasibility(result['domain_status'],verification['physical'])
                    atomic(output/'ACTIVE_DOMAIN_FEASIBLE_SCHEDULE.json',dict(day=day,selected_jobs=verification['selected_jobs'],
                        controls=verification.get('controls'),independent_physical=verification['physical'],accepted=False))
                if component=='rho':
                    stage['active_domain_objective_proven']=bool(model.Status==gp.GRB.OPTIMAL and model.SolCount
                        and stage['gap'] is not None and stage['gap']<=policy['parameters']['MIPGap']+1e-12)
                    stage['certificate']='Frozen continuous rho native-gap convention; active domain only'
                elif model.SolCount:
                    proof=backend.integer_certificate(component,stage['objective'],stage['active_domain_global_bound'])
                    stage['integer_objective_certificate']=proof
                    stage['active_domain_objective_proven']=proof.get('PASS') is True
                result['passes'].append(stage);atomic(folder/'PASS_RESULT.json',stage)
                result['domain_status']['ACTIVE_DOMAIN_SOLVED']=all(p['active_domain_objective_proven'] for p in result['passes'])
                atomic(output/'A1_RESULT.json',result)
                if diagnostics.callback_errors:
                    raise GlobalScientificFailure('CALLBACK_IMPLEMENTATION_OR_TELEMETRY_FAILURE:'+str(diagnostics.callback_errors))
                if not stage['active_domain_objective_proven']:
                    if model.Status==gp.GRB.TIME_LIMIT:
                        root_completed=observation['events'].get('root_completion_observed_native_seconds') is not None or observation.get('root_relaxation') is not None
                        result['classification']='ROOT_LP_TIMEOUT' if component=='rho' and not root_completed else 'LEX_P2_TIMEOUT' if component!='rho' else 'UNRESOLVED'
                    else:result['classification']='UNRESOLVED'
                    break
                rhs=stage['objective']+1e-7 if component=='rho' else int(round(stage['objective']))
                locks.append(dict(component=component,sense='<=' if component=='rho' else '=',rhs=rhs,
                    optimum=stage['objective'],active_domain_certificate=stage.get('integer_objective_certificate'),
                    current_new_run_only=True,historical_lock_imported=False))
                atomic(output/'CURRENT_NEW_AUTHORITY_LEX_LOCKS.json',locks)
                previous=dict(stage=stage,point=point,verification=verification,metadata=build.metadata,
                    objective_locks=list(locks),native_model=model,stage_build=build)
                # The backend may reuse a model or build a fresh exact projection;
                # it must dispose replaced models and provide projection evidence.
            completed=len(result['passes'])==4 and all(p['active_domain_objective_proven'] for p in result['passes'])
            result['domain_status']['ACTIVE_DOMAIN_SOLVED']=completed
            if completed:
                result['classification']='A1_ACTIVE_DOMAIN_SOLVED_DOMAIN_CLOSURE_UNRESOLVED'
                result['domain_status']['ACTIVE_DOMAIN_SOLVED']=True
            closure=backend.domain_closure(last_build,result) if last_build is not None and hasattr(backend,'domain_closure') else None
            if closure is not None:
                result['domain_status']=validate_domain_status(closure)
                result['migration_pricing_closed']=closure.get('MIGRATION_PRICING_CLOSED',closure['LP_PRICING_CLOSED'])
                result['integer_domain_closure_proven']=closure['INTEGER_DOMAIN_CLOSURE_PROVEN']
                result['A1_full_domain_accepted']=closure['PRODUCTION_DOMAIN_ACCEPTED']
            atomic(output/'DOMAIN_CLOSURE_RESULT.json',dict(result['domain_status'],
                root_LP_pricing_is_not_integer_domain_closure=True))
            if result['A1_full_domain_accepted']:
                if not completed or not result['A1_active_domain_feasible']:
                    raise GlobalScientificFailure('INCOMPLETE_LEX_SEQUENCE_CANNOT_ACCEPT_PRODUCTION_DOMAIN')
                with accepted_pipeline_scope(day,result['domain_status']):
                    pipeline=backend.production_pipeline(day,output,result,previous)
                result.update(pipeline)
                result['classification']='STRESS_DATE_FULL_PASS' if pipeline.get('physical_PASS') is True else 'PHYSICAL_VALIDATION_FAIL'
            if day=='2025-05-12':
                phases=[json.loads(Path(p['telemetry']).read_text()) for p in result['passes']]
                atomic(output/'ROOT_PHASE_TIMELINE.json',dict(day=day,passes=phases,missing_values_inferred=False))
                atomic(output/'ROOT_NUMERICAL_AUDIT.json',dict(day=day,solver_policy=policy,
                    numerical=[dict(component=p['component'],quality=t['objective_stage_timings'],warnings=t['numerical_warnings'])
                        for p,t in zip(result['passes'],phases)],parameter_sweep=False))
            if day=='2025-05-10':
                atomic(output/'SHIFT_STAGE_FORENSIC.json',dict(day=day,new_passes=result['passes'],
                    actual_new_migration_optimum=next((p['objective'] for p in result['passes'] if p['component']=='migration_count'),None),
                    projection_evidence=previous['metadata'] if previous else None,historical_locks_reused=False))
                _write_rows(output/'SHIFT_STAGE_BEFORE_AFTER.csv',census)
        except GlobalScientificFailure as error:
            result.update(classification='SCIENTIFIC_IDENTITY_FAIL',global_scientific_stop=True,error=str(error))
        except gp.GurobiError as error:
            result.update(classification='UNRESOLVED',native_solver_error=str(error),global_scientific_stop=False)
        except MemoryError as error:
            result.update(classification='UNRESOLVED',computational_resource_failure=True,
                global_scientific_stop=False,error=str(error) or 'PYTHON_NATIVE_MEMORY_EXHAUSTION')
        except OSError as error:
            resource=getattr(error,'errno',None) in (errno.ENOMEM,errno.ENOSPC,10001) or getattr(error,'winerror',None) in (8,14,1450,1455)
            result.update(classification='UNRESOLVED' if resource else 'SCIENTIFIC_IDENTITY_FAIL',
                computational_resource_failure=resource,global_scientific_stop=not resource,error=str(error))
        except Exception as error:
            result.update(classification='SCIENTIFIC_IDENTITY_FAIL',global_scientific_stop=True,
                error=str(error),traceback=traceback.format_exc())
        finally:
            if model is not None:model.dispose()
            atomic(output/'A1_RESULT.json',dict(result,finished_UTC=now()))
            if not (output/'DOMAIN_CLOSURE_RESULT.json').exists():atomic(output/'DOMAIN_CLOSURE_RESULT.json',result['domain_status'])
    return result


def _backend(name,permit):
    module,attribute=name.split(':');factory=getattr(importlib.import_module(module),attribute)
    source=str(Path(inspect.getsourcefile(factory)).resolve())
    if source not in permit.document['execution_sources']:
        raise PermissionError('STRESS4_SCIENTIFIC_BACKEND_SOURCE_NOT_FROZEN')
    return factory()


def run_four_dates(backend_name,permit_path,policy_path,output):
    """Serial child isolation also protects B1's date-routed global namespaces."""
    root=Path(output).resolve();root.mkdir(parents=True,exist_ok=True)
    permit=StressRunPermit(Path(permit_path).read_text(encoding='utf8'));permit.verify()
    summaries=[]
    for day in STRESS_RUN_ORDER:
        permit.verify()
        folder=root/('MAY'+day[-2:]);folder.mkdir(exist_ok=True)
        command=[sys.executable,'-B','-m','v42_a_stage_domain_v2.stress_runner','--day',day,
            '--permit',str(Path(permit_path).resolve()),'--policy',str(Path(policy_path).resolve()),
            '--backend',backend_name,'--output',str(folder)]
        kwargs={'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}
        with (folder/'WORKER_CONSOLE.log').open('x',encoding='utf8') as stream:
            process=subprocess.Popen(command,stdout=stream,stderr=subprocess.STDOUT,**kwargs)
            atomic(root/'ACTIVE_STRESS_CHILD.json',dict(day=day,pid=process.pid,command=command,started_UTC=now()))
            process.wait()
        path=folder/'A1_RESULT.json'
        result=json.loads(path.read_text()) if path.exists() else dict(day=day,classification='UNRESOLVED',
            error='ISOLATED_WORKER_FAILED_WITHOUT_RECEIPT',global_scientific_stop=False,
            unrecorded_worker_failure=True,exit_code=process.returncode,
            note='An unrecorded native/process failure is not proof of a global scientific defect; continue remaining preregistered dates without retry.')
        summaries.append(result)
        atomic(root/'STRESS4_RESULTS.json',summaries)
        if result.get('global_scientific_stop'):break
    return summaries


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--day',choices=STRESS_RUN_ORDER)
    parser.add_argument('--permit',required=True);parser.add_argument('--policy',required=True)
    parser.add_argument('--backend',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args()
    if args.day:
        permit=StressRunPermit(Path(args.permit).read_text(encoding='utf8'))
        permit.verify()
        result=run_date(args.day,_backend(args.backend,permit),permit,json.loads(Path(args.policy).read_text()),args.output)
        return 2 if result.get('global_scientific_stop') else 0
    run_four_dates(args.backend,args.permit,args.policy,args.output);return 0


if __name__=='__main__':sys.exit(main())
