"""Current full-domain DW Phase I/P1, original integer UB and FULL replay."""
from copy import deepcopy
import math
from pathlib import Path
from time import perf_counter

import numpy as np

from .a_engine import digest
from .m_engine import _write, vector_sha, file_record
from .release_p1_acceptance import SCHEMA, prohibit_p2, require_acceptance
from .table_v_flex_planning import require_flex_context, build_flex_native_model
from .table_v_mess import require_m_acceptance
from .table_v_dw import execute_current_dw, attach_global_bounds, objective_identity
from .table_v_dw_reuse import replay_same_problem_dw
from .table_v_status import classify_a_result
from .table_v_gap_contract import AIDC_GLOBAL_GAP_TARGET


def accept_current_a(result, *, context, case, binding, point, full, parent=None):
    """Same original A acceptance obligations, with the Table V M parent."""
    prohibit_p2(result)
    if case.stage == 'A2':
        require_m_acceptance(parent, identity=context['manifest']['identity'], arm='B3', stage='M1')
        if parent['MESS_anchor'] != result['input_MESS_anchor']:
            raise ValueError('TABLE_V_A2_CURRENT_M1_ANCHOR_REQUIRED')
    point_sha=vector_sha(point)
    if (result.get('stage')!=case.stage or result.get('arm')!=case.arm
            or result.get('case_sha')!=case.case_sha
            or result.get('source_identity')!=context['manifest']['identity']
            or result.get('D0_input_sha')!=context['input_audit']['a_input_sha']
            or result.get('input_MESS_anchor')!=case.grid.fixed_mess['plan_sha']
            or result.get('native_binding')!=binding
            or full.get('PASS') is not True or not math.isfinite(full['FULL_max_residual'])
            or not 0 <= full['FULL_max_residual'] <= 1e-5
            or full.get('point_sha256') != point_sha
            or result.get('FULL_feasible') is not True
            or result.get('FULL_point_replay', {}).get('PASS') is not True
            or result.get('FULL_point_replay', {}).get('point_sha256') != point_sha
            or binding['rows'] != full['rows'] or binding['columns'] != full['columns']
            or binding['objective_sense'] != 1):
        raise ValueError('TABLE_V_ORIGINAL_FULL_A_POINT_REPLAY_REQUIRED')
    from .coordinator import _full_a
    _full_a(result)
    gap=result['gap']
    closed=type(gap) in (int,float) and math.isfinite(gap) and 0 <= gap <= .005
    receipt=dict(schema=SCHEMA,status='FULL_PASS',stage=case.stage,arm=case.arm,
        stage_case_sha=case.case_sha,source_identity=deepcopy(context['manifest']['identity']),
        source_sha=context['manifest']['source_sha'],D0_input_sha=context['input_audit']['a_input_sha'],
        AIDC_anchor=result['aidc_anchor'],MESS_anchor=result['input_MESS_anchor'],result_sha=digest(result),
        native_binding=binding,point_sha256=point_sha,Original_FULL=deepcopy(full),
        P1_only=True,P2_calls=0,P2_optimized=False,original_P1_objective='MIN_MAXIMUM_PHASE_LINE_LOADING',
        native_matrix_objective=result['objective'],native_matrix_bound=result['bound'],native_matrix_gap=gap,
        native_matrix_target_met=closed,optimality_status='CURRENT_MATRIX_TARGET_MET' if closed else 'OPTIMALITY_TARGET_UNMET',
        whole_original_unpriced_domain_global_optimality=False,
        AIDC_MESS_joint_Global_LB=None,K48_Global_LB=None,
        minimum_control_timeshift_migration_cost_claimed=False,
        parent_acceptance_sha=None if parent is None else parent['acceptance_sha'],
        domain_scope='ORIGINAL_SOURCE_AUTHORIZED_E1_FLEX30_FULL_DOMAIN',
        evidence_scope='REAL_PRODUCTION',fixture=False)
    receipt.update(AIDC_Global_LB=result.get('AIDC_Global_LB'),AIDC_Global_UB=result.get('AIDC_Global_UB',result['objective']),
        AIDC_Global_Gap=result.get('AIDC_Global_Gap'),AIDC_Global_Gap_percent=result.get('AIDC_Global_Gap_percent'),
        AIDC_Global_Gap_target=AIDC_GLOBAL_GAP_TARGET,DW=deepcopy(result.get('DW')),stage_status=classify_a_result(result),
        objective_sha=result.get('objective_sha'),DW_status=result.get('DW_status'))
    receipt['acceptance_sha']=digest(receipt)
    require_acceptance(receipt,stage=case.stage,source_identity=context['manifest']['identity'],result=result)
    return receipt


def execute_current_a(context,budget,*,arm,stage,output,parent_result=None,parent_acceptance=None,progress=None,reuse_a1=None):
    require_flex_context(context)
    if arm not in ('B1','B3') or stage not in ('A1','A2') or arm=='B1' and stage!='A1':
        raise ValueError('TABLE_V_EXACT_A_ARM_STAGE_REQUIRED')
    from .coordinator import _full_m
    fixed=None
    if stage=='A2':
        require_m_acceptance(parent_acceptance,result=parent_result,identity=context['manifest']['identity'],arm=arm,stage='M1')
        fixed=_full_m(parent_result)
    case=context['make_a_case'](stage,fixed_mess=fixed,folder=output,upstream_m_result=parent_result,arm=arm)
    case.table_v_day=context['manifest']['day']
    case.progress=progress
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    if (output/'P1_ONLY_RESULT.json').exists():
        raise FileExistsError('TABLE_V_A_ATTEMPT_ALREADY_EXISTS_NO_AUTOMATIC_RETRY')
    parent=parent_result if stage=='A2' else context['manifest']
    budget.bind_table_v_case(arm=arm,stage=stage,stage_case_sha=case.case_sha,
        source_sha=context['manifest']['source_sha'],parent_result=parent,
        source_identity=context['manifest']['identity'],parent_acceptance=parent_acceptance,
        case_certificate=context['manifest'])
    built=None
    started=perf_counter()
    with budget.arm_context(arm),budget.phase(stage,case.case_sha,context['manifest']['source_sha'],digest(parent)):
        with budget.capture_native_methods():
            try:
                import gurobipy as gp
                from .d0_a_planning import _export_d0_point
                from .d0_resource import native_binding
                from .a_seed import full_replay
                from v42_root.native import reconstruct
                from v42_a_stage_domain_v2.solver_policy import solver_policy,apply_policy
                from v42_b3_joint.numerical_policy import apply_native_precision
                from .partial_canary import resource_snapshot
                from .table_v_resources import admit_resources
                admit_resources(budget,phase='PRE_ORIGINAL_AIDC_INTEGER_MODEL_BUILD:'+stage)
                resources=resource_snapshot()
                if budget.worker_lock.exists():
                    raise RuntimeError('TABLE_V_FULL_FLEX_BUILD_CONCURRENT_HEAVY_GATE')
                admission=dict(status='PASS',operation='TABLE_V_FULL_FLEX_A_NATIVE0_BUILD',
                    case_sha=case.case_sha,concurrent_heavy_solver=False,resource_snapshot=resources)
                _write(output/'MODEL_BUILD_ADMISSION.json',admission)
                began=perf_counter()
                built=build_flex_native_model(case,build_admission=admission)
                model=built[0]
                model.setObjective(dict(built[2])['rho'],gp.GRB.MINIMIZE);model.update()
                policy=solver_policy(gp);apply_policy(model,policy,gp)
                numeric=apply_native_precision(model,day=case.table_v_day,stage=stage,component='ORIGINAL_P1')
                model.Params.Threads=1
                model.Params.LogFile=str(output/'NATIVE_GUROBI.log')
                binding=native_binding(model)
                built[6]['native_binding']=deepcopy(binding)
                objective_sha=objective_identity(model)
                build_seconds=perf_counter()-began
                _write(output/'NATIVE0_FULL_FLEX_MODEL_CERTIFICATE.json',dict(built[6],native_binding=binding,
                    objective_sha=objective_sha,model_build_seconds=build_seconds,executed_source=[file_record(__file__),file_record(budget.__class__.__module__.replace('.','/')+'.py')]))
                budget.record_external('RELEASE_P1:'+stage+':MODEL_BUILD',build_seconds,solver='BUILD')
                if reuse_a1 is not None and arm=='B3' and stage=='A1':
                    import json
                    candidates=(reuse_a1,) if isinstance(reuse_a1,(str,Path)) else tuple(reuse_a1)
                    reuse_audits=[]
                    for candidate in candidates:
                        old_folder=Path(candidate)
                        try:
                            old=json.loads((old_folder/'P1_ONLY_RESULT.json').read_text(encoding='utf8'))
                            old_receipt=json.loads((old_folder/'P1_ONLY_ACCEPTANCE.json').read_text(encoding='utf8'))
                            require_acceptance(old_receipt,stage='A1',source_identity=context['manifest']['identity'],result=old)
                            exact=(old.get('arm')=='B1' and old.get('case_sha')==case.case_sha
                                and old.get('native_binding')==binding and old.get('D0_input_sha')==context['input_audit']['a_input_sha']
                                and old.get('input_MESS_anchor')==case.grid.fixed_mess['plan_sha']
                                and old_receipt.get('evidence_scope')=='REAL_PRODUCTION'
                                and old.get('objective_sha',objective_sha)==objective_sha)
                            reuse_audits.append(dict(exact_identity_equal=exact,current_native_binding=binding,
                                previous_native_binding=old.get('native_binding'),objective_sha=objective_sha,
                                prior_result=file_record(old_folder/'P1_ONLY_RESULT.json'),
                                prior_acceptance=file_record(old_folder/'P1_ONLY_ACCEPTANCE.json'),
                                prior_point=file_record(old_folder/'P1_ONLY_POINT.npz'),
                                prior_source_sha=old_receipt.get('source_sha'),current_source_sha=context['manifest']['source_sha']))
                        except (ValueError,KeyError,OSError) as error:
                            reuse_audits.append(dict(folder=str(old_folder),exact_identity_equal=False,error=str(error)))
                            continue
                        if not exact: continue
                        with np.load(old_folder/'P1_ONLY_POINT.npz',allow_pickle=False) as packet:
                            point=packet['point'].copy()
                        full=full_replay(model,point)
                        if not full['PASS'] or vector_sha(point)!=old_receipt['point_sha256']:
                            raise ValueError('TABLE_V_REUSED_A1_LITERAL_CURRENT_FULL_REPLAY_FAILED')
                        objective=float(np.dot(np.asarray(model.getAttr('Obj'),float),point)+model.ObjCon)
                        if abs(objective-old['objective'])>1e-7:
                            raise ValueError('TABLE_V_REUSED_A1_CURRENT_OBJECTIVE_DRIFT')
                        result=deepcopy(old)
                        # A different Arm does not inherit a Native-bound
                        # certificate. DW/full pricing is independently replayed.
                        result.pop('Original_Integer_Bound_Certificate',None)
                        result.pop('Global_Gap_Control',None)
                        result.update(arm=arm,Native_call=None,reused_native_call=old.get('Native_call'),
                            Native_optimize_calls_this_stage=0,reused_A1_result=file_record(old_folder/'P1_ONLY_RESULT.json'),
                            model_build_seconds=build_seconds,stage_wall_seconds=perf_counter()-started,
                            objective_sha=objective_sha,source_lineage=dict(prior_source_sha=old_receipt.get('source_sha'),
                                current_source_sha=context['manifest']['source_sha'],same_mathematical_problem=True))
                        # The new model has no optimized X attributes. The
                        # literal same-case selected options were already
                        # exported from this exact matrix/point; revalidate
                        # them against current original service and GPU rows.
                        result.update(_export_d0_point(case,built,point,deepcopy(old['selected_jobs'])))
                        # A reused UB never turns an old/incomplete restricted
                        # master objective into a current DW lower bound.
                        dw=replay_same_problem_dw(context,case,built,old.get('DW'),output/'DW_REUSE')
                        if dw is None:dw=execute_current_dw(context,case,built,budget,output/'DW')
                        result['Native_optimize_calls_this_stage']=dw.get('native_calls',0)
                        attach_global_bounds(result,dw);result['status']=classify_a_result(result)
                        np.savez_compressed(output/'P1_ONLY_POINT.npz',point=point)
                        receipt=accept_current_a(result,context=context,case=case,binding=binding,point=point,full=full)
                        _write(output/'P1_ONLY_RESULT.json',result);_write(output/'P1_ONLY_ACCEPTANCE.json',receipt)
                        _write(output/'A1_REUSE_MATH_MATRIX_DOMAIN_OBJECTIVE_AUDIT.json',dict(candidates=reuse_audits,reused=True))
                        return result,receipt
                    _write(output/'A1_REUSE_MATH_MATRIX_DOMAIN_OBJECTIVE_AUDIT.json',dict(candidates=reuse_audits,reused=False))
                dw=execute_current_dw(context,case,built,budget,output/'DW')
                from .table_v_a_control import solve_original
                call,integer_certificate,gap_control=(solve_original(model,budget,case,context,binding,objective_sha,dw,output)
                    if not dw.get('structural_adapter_failure') else (None,None,None))
                result=dict(stage=stage,arm=arm,case_sha=case.case_sha,source_identity=deepcopy(context['manifest']['identity']),
                    D0_input_sha=context['input_audit']['a_input_sha'],D0_source_sha=context['manifest']['source_sha'],input_MESS_anchor=case.grid.fixed_mess['plan_sha'],
                    D0_issue_seconds=context['input_audit']['issue_seconds'],P2_calls=0,P2='NOT_RUN',
                    objective=float(model.ObjVal) if call and model.SolCount else None,
                    bound=float(model.ObjBound) if call and math.isfinite(float(model.ObjBound)) and abs(float(model.ObjBound))<gp.GRB.INFINITY else None,
                    gap=float(model.MIPGap) if call and model.SolCount else None,Native_call=call,FULL_feasible=False,
                    Original_Integer_Bound_Certificate=integer_certificate,Global_Gap_Control=gap_control,
                    Gurobi_Status=int(model.Status) if call else None,SolCount=int(model.SolCount) if call else 0,
                    Native_Runtime=float(model.Runtime) if call else 0.,objective_sha=objective_sha,
                    native_binding=binding,solver_policy=policy,numerical_policy=numeric,
                    model_build_seconds=build_seconds,domain_scope='ORIGINAL_SOURCE_AUTHORIZED_E1_FLEX30_FULL_DOMAIN',
                    unrestricted_original_migration_global_optimality=False)
                if not call or not model.SolCount:
                    attach_global_bounds(result,dw)
                    result['status']=classify_a_result(result)
                    result['stage_wall_seconds']=perf_counter()-started
                    _write(output/'P1_ONLY_RESULT.json',result)
                    return result,None
                point=np.asarray(model.getAttr('X'),float)
                full=full_replay(model,point)
                if not full['PASS']:raise ValueError('TABLE_V_ORIGINAL_FULL_A_REPLAY_FAILED')
                result.update(_export_d0_point(case,built,point,reconstruct(built[1],built[5])))
                attach_global_bounds(result,dw);result['status']=classify_a_result(result)
                result['stage_wall_seconds']=perf_counter()-started
                np.savez_compressed(output/'P1_ONLY_POINT.npz',point=point)
                receipt=accept_current_a(result,context=context,case=case,binding=binding,point=point,
                                         full=full,parent=parent_acceptance)
                _write(output/'P1_ONLY_RESULT.json',result)
                _write(output/'P1_ONLY_ACCEPTANCE.json',receipt)
                return result,receipt
            finally:
                if built is not None:built[0].dispose()
