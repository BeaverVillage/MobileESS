"""One approved 120s D0 A1 P1; never runs P2 or downstream stages."""
from pathlib import Path
from time import perf_counter
import json
import math
import os
import sys
import threading
import traceback

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import numpy as np
from v42_integration.m_engine import _write,file_record,vector_sha
from v42_integration.unified_contract import digest
from v42_integration.partial_canary import resource_snapshot
from v42_integration.release_budget import ReleaseP1Budget

OUT=ROOT/'docs/v42_unified_aidc_mess_research_20261014/RELEASE_RECOVERY_20261015/RC01/A1_P1_120'
OLD=ROOT/'docs/v42_unified_aidc_mess_research_20261014'
AUTH=Path('C:/Users/kjw39/.codex/attachments/00dc4f00-c478-408d-9074-095c4ee67dac/붙여넣은 텍스트.txt')


def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def main():
    if OUT.exists():raise FileExistsError('ONE_P1_ATTEMPT_DIRECTORY_ALREADY_EXISTS_NO_AUTOMATIC_RETRY')
    OUT.mkdir(parents=True)
    import psutil
    import gurobipy as gp
    from v42_integration.d0_case import build_planning_inputs,require_case
    from v42_integration.d0_a_planning import build_d0_native_model,_export_d0_point
    from v42_integration.d0_resource import native_binding
    from v42_integration.a_seed import full_replay
    from v42_root.native import reconstruct
    from v42_a_stage_domain_v2.solver_policy import solver_policy,apply_policy
    from v42_b3_joint.numerical_policy import apply_native_precision
    reference=read(OLD/'D0_STATE_CONDITIONED_PLANNING_20261015/FINAL_NATIVE0/EXACT_P1_MATRIX_DOMAIN_EQUIVALENCE.json')
    expected=read(OLD/'ISOLATED_UNKNOWN_C0_C1_20261015/D0_A1_NATIVE0_REGENERATION_PROOF.json')
    canonical=OLD/'UNIFIED_NATIVE_RUNTIME_LEDGER.json';before=file_record(canonical)
    resource=resource_snapshot();_write(OUT/'RESOURCE_BEFORE_BUILD.json',resource)
    if resource['memory']['AvailableMBytes']<8192 or resource['memory']['PercentCommittedBytesInUse']>=75:
        raise RuntimeError('P1_PREBUILD_RESOURCE_GATE')
    sources=[file_record(r['path']) for r in expected['exact_source13_preservation']]
    assert sources==expected['exact_source13_preservation']
    records=[file_record(ROOT/n) for n in ('tools/run_v42_release_p1.py','v42_integration/release_budget.py')]
    _write(OUT/'EXECUTED_ADAPTER_SOURCE.json',dict(files=records,frozen_planning_Source13=sources,user_authorization=file_record(AUTH)))
    process=psutil.Process();peak=dict(RSS_bytes=process.memory_info().rss,private_commit_bytes=0,available_RAM_min=psutil.virtual_memory().available)
    stop=threading.Event()
    def sample():
        while not stop.wait(.2):
            mem=process.memory_info();peak['RSS_bytes']=max(peak['RSS_bytes'],mem.rss)
            peak['private_commit_bytes']=max(peak['private_commit_bytes'],getattr(mem,'private',mem.vms))
            peak['available_RAM_min']=min(peak['available_RAM_min'],psutil.virtual_memory().available)
    thread=threading.Thread(target=sample,daemon=True);thread.start();began=perf_counter();built=None
    result=dict(status='NOT_RUN',Native_calls=0,P2='NOT_RUN',M1='NOT_RUN',A2='NOT_RUN',M2='NOT_RUN',K48='NOT_RUN',
        Actual96='NOT_RUN',Fresh96='NOT_RUN',old_results_reused=False)
    original_native={n:getattr(gp.Model,n) for n in ('optimize','presolve','computeIIS')};attempts=[]
    def forbidden(*a,**k):attempts.append('FORBIDDEN_NATIVE_ENTRYPOINT');raise RuntimeError('ONLY_ONE_ADMITTED_P1_OPTIMIZE_ALLOWED')
    try:
        for n in original_native:setattr(gp.Model,n,forbidden)
        context=build_planning_inputs(output=OUT/'CASE',call_cap=120.)
        case=context['make_a_case']('A1',folder=OUT/'SOLVE');require_case(context['manifest'])
        built=build_d0_native_model(case,build_admission=dict(status='PASS',operation='D0_A_NATIVE0_BUILD',case_sha=case.case_sha,concurrent_heavy_solver=False))
        model=built[0];model.Params.Threads=1;model.setObjective(dict(built[2])['rho'],gp.GRB.MINIMIZE);model.update()
        binding=native_binding(model)
        assert binding==reference['current_binding']
        assert context['manifest']['identity']==reference['current_identity']
        objective=dict(coefficients_vector_sha=vector_sha(np.asarray(model.getAttr('Obj'),float)),constant=float(model.ObjCon),sense=int(model.ModelSense),
            nonzero_name='rho_max',nonzero_coefficient=1.)
        objective['objective_sha']=digest(objective);assert objective==expected['objective']
        _write(OUT/'PREOPTIMIZE_EXACT_MODEL_CERTIFICATE.json',dict(status='PASS',native_binding=binding,objective=objective,
            identity=context['manifest']['identity'],stage_case_sha=case.case_sha,source_sha=context['manifest']['source_sha'],
            Source13=sources,mathematical_problem_changed=False,Actual_adapter_in_planning_model=False,
            original_domain_rows_and_objective=True,build_wall_seconds=perf_counter()-began,Native_calls=0))
        authorization=dict(scope='D0_A1_P1_EXACTLY_ONE_CALL',limit_seconds=180.,call_cap_seconds=120.,return_reserve_seconds=30.,
            overshoot_buffer_seconds=30.,max_optimize_calls=1,Threads=1,Worker=1,user_attachment=file_record(AUTH),
            native_binding=binding,source_case_identity=context['manifest']['identity'],stage_case_sha=case.case_sha,
            P2_M1_A2_M2_K48_not_authorized=True)
        _write(OUT/'USER_NATIVE_AUTHORIZATION.json',authorization)
        budget=ReleaseP1Budget(OUT/'SEPARATE_NATIVE_LEDGER_180.json',authorization=authorization,canonical_ledger=canonical)
        policy=solver_policy(gp);apply_policy(model,policy,gp)
        numerical=apply_native_precision(model,day='2025-05-01',stage='A1',component='ORIGINAL_P1')
        model.Params.LogFile=str(OUT/'SOLVE/NATIVE_SOLVER.log');model.Params.OutputFlag=1
        # Restore only the admitted optimize body. presolve/IIS remain blocked;
        # the durable ledger consumes authorization before the first entry.
        entered=[]
        def admitted(this,*a,**k):
            if this is not model or entered:raise RuntimeError('SECOND_OR_FOREIGN_NATIVE_CALL_FORBIDDEN')
            entered.append(True);return original_native['optimize'](this,*a,**k)
        gp.Model.optimize=admitted
        wall_begin=perf_counter()
        last_memory_check=[0.]
        def callback(m,where):
            now=perf_counter()
            if now-last_memory_check[0]>=1.:
                last_memory_check[0]=now
                if psutil.virtual_memory().available<4*1024**3:m.terminate()
        call=budget.solve(model,label='D0_A1_P1_RELEASE_120_20261015',cap=120.,callback=callback)
        assert len(entered)==1
        gp.Model.optimize=forbidden
        full=None;exported={}
        if model.SolCount:
            point=np.asarray(model.getAttr('X'),float);full=full_replay(model,point)
            np.savez_compressed(OUT/'SOLVE/POINT.npz',point=point)
            if full['PASS']:exported=_export_d0_point(case,built,point,reconstruct(built[1],built[5]))
        certified=bool(full and full['PASS'] and model.Status==gp.GRB.OPTIMAL)
        finite=lambda v:float(v) if math.isfinite(float(v)) else None
        result.update(status='P1_CERTIFIED_FULL_FEASIBLE' if certified else 'FEASIBLE_OPTIMALITY_TARGET_UNMET' if exported
            else 'INFEASIBLE_CERTIFIED' if model.Status==gp.GRB.INFEASIBLE else 'TIME_LIMIT_NO_FEASIBLE' if model.Status==gp.GRB.TIME_LIMIT else 'NOT_CERTIFIED',
            Native_calls=1,SolCount=int(model.SolCount),Gurobi_status=int(model.Status),P1_acceptance=certified,
            FULL_feasible=bool(exported),FULL_point_replay=full,objective=finite(model.ObjVal) if model.SolCount else None,
            bound=finite(model.ObjBound),gap=finite(model.MIPGap) if model.SolCount else None,Native_Runtime=float(model.Runtime),
            optimize_wall_seconds=perf_counter()-wall_begin,Native_call=call,native_binding=binding,source_identity=context['manifest']['identity'],
            stage_case_sha=case.case_sha,solver_policy=policy,numerical_policy=numerical,
            bound_scope='SAME_CURRENT_COMPLETE_D0_FIXED_MESS_A1_MATRIX_ONLY_NOT_JOINT_GLOBAL',
            P2_M1_A2_M2_K48_HOLD_reason='NO_FURTHER_NATIVE_AUTHORIZATION')
        result.update(exported)
    except BaseException as exc:
        result.update(error_type=type(exc).__name__,error=str(exc),traceback=traceback.format_exc())
        _write(OUT/'FAILURE_RECEIPT.json',result);raise
    finally:
        for n,method in original_native.items():setattr(gp.Model,n,method)
        if built is not None:built[0].dispose()
        stop.set();thread.join(timeout=2)
        assert file_record(canonical)==before
        assert all(file_record(r['path'])==r for r in sources+records)
        result.update(total_build_solve_audit_wall_seconds=perf_counter()-began,resource_peak=peak,
            canonical_before=before,canonical_after=file_record(canonical),canonical_byte_identical=True,forbidden_native_attempts=attempts)
        _write(OUT/'A1_P1_RESULT.json',result)
    print(json.dumps({k:result.get(k) for k in ('status','Native_calls','SolCount','P1_acceptance','FULL_feasible','objective','bound','gap','Native_Runtime','resource_peak')},indent=2))


if __name__=='__main__':main()
