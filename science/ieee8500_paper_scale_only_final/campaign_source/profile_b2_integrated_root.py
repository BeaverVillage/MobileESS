"""Same-model B2 root/presolve diagnostic with polished MESS01 start ON/OFF."""
from bootstrap import *
from types import SimpleNamespace
import math
import re
import traceback
import gurobipy as gp
import mess_runtime


OUT=H/'B2_ROOT_PROFILE'
SEED=H/'B2/beam/2025-05-01/B2/B2/s1/B2-ROOT/SEEDS.json'


def value(model,name):
    try:return float(getattr(model,name))
    except (AttributeError,gp.GurobiError):return None


def parse_log(path):
    body=path.read_text(encoding='utf-8',errors='replace') if path.exists() else ''
    match=re.search(r'Presolved:\s+([\d,]+) rows,\s+([\d,]+) columns,\s+([\d,]+) nonzeros',body)
    root=re.search(r'Root relaxation: objective\s+\S+,\s+([\d,]+) iterations,\s+([\d.]+) seconds',body)
    return dict(presolved_rows=int(match.group(1).replace(',','')) if match else None,
        presolved_columns=int(match.group(2).replace(',','')) if match else None,
        presolved_nonzeros=int(match.group(3).replace(',','')) if match else None,
        root_relaxation_iterations=int(root.group(1).replace(',','')) if root else None,
        root_relaxation_seconds=float(root.group(2)) if root else None,
        log_sha256=sha(path) if path.exists() else None)


def run_root(model,variables,starts,label):
    model.reset()
    for variable,start in zip(variables,starts,strict=True):
        variable.Start=start if label=='ON' else gp.GRB.UNDEFINED
    model.Params.NodeLimit=1
    # Profile the same root/presolve window for both starts. This limit is
    # diagnostic only; production retains infinite TimeLimit and WorkLimit.
    model.Params.TimeLimit=330
    model.Params.LogToConsole=0
    model.Params.OutputFlag=1
    log=OUT/f'ROOT_{label}.log'
    model.Params.LogFile=str(log)
    model.Params.DisplayInterval=30
    assert model.Params.MIPFocus==1 and model.Params.Threads==4
    assert model.Params.MIPGap==.001
    save(OUT/f'ROOT_{label}_START.json',dict(status='RUNNING',label=label,
        unix=time.time(),node_limit=1,time_limit_seconds=330,diagnostic_only=True,
        model_vars=int(model.NumVars),model_rows=int(model.NumConstrs),
        warm_start_values=sum(float(v)<1e100 for v in starts) if label=='ON' else 0))
    began=time.perf_counter();model.optimize();elapsed=time.perf_counter()-began
    incumbent=value(model,'ObjVal') if model.SolCount else None
    bound=value(model,'ObjBound')
    report=dict(status='DIAGNOSTIC_ROOT_COMPLETE',label=label,
        gurobi_status=int(model.Status),node_limit=1,time_limit_seconds=330,
        diagnostic_only=True,
        elapsed_seconds=elapsed,rows=int(model.NumConstrs),columns=int(model.NumVars),
        binaries=int(model.NumBinVars),quadratic_constraints=int(model.NumQConstrs),
        incumbent_objective=incumbent,best_bound=bound,
        mip_gap=value(model,'MIPGap') if model.SolCount else None,
        explored_nodes=value(model,'NodeCount'),simplex_iterations=value(model,'IterCount'),
        barrier_iterations=value(model,'BarIterCount'),solution_count=int(model.SolCount),
        log=str(log),**parse_log(log))
    save(OUT/f'ROOT_{label}_RESULT.json',report)
    print('ROOT_'+label,report,flush=True)
    return report


def main():
    assert not (H/'B2/COMPLETE.json').exists()
    assert read(H/'CAMPAIGN_STATUS.json')['status']=='PAUSED_FOR_ROOT_PROFILE'
    OUT.mkdir(parents=True,exist_ok=True)
    from dayahead.v34 import integrated_mess as module
    from dayahead.v35.execution import MESS_INITIAL
    with np.load(H/'MAY01_B0_AIDC_POWER.npz') as z:aidc=z['pcc'].copy()
    seed=read(SEED)[0]['dispatch']
    cc=mess_runtime.coefficients()
    route_table=mess_runtime.traffic()[2]
    mapping={r['service']:r['PCC'] for r in read(H/'MESS_24_SERVICE_PCC_COLUMN_BINDING.json')['services']}
    voltage=mess_runtime.Authority(control_names=np.array(NAMES),node_names=np.array(AX['nodes']))
    electrical=SimpleNamespace(legacy_context=None,voltage=voltage,current=mess_runtime.Authority())
    save(OUT/'INPUT_AUTHORITY.json',dict(status='PASS',date='2025-05-01',BG=.552,AIDC=2.4,MESS=2.,
        paper_overlay_sha256=sha(H/'IEEE8500_PCC_Overlay.dss'),pcc_input_sha256=sha(H/'MAY01_B0_AIDC_POWER.npz'),
        seed_sha256=sha(SEED),coefficient_count=len(cc),coefficient_shas=[c.coefficient_sha256 for c in cc],
        route_table_sha256=route_table.canonical_sha256,model_problem_same_as_production=True,
        diagnostic_node_limit_only=True))
    previous=module.WORK_LIMIT_TIERS
    try:
        module.WORK_LIMIT_TIERS=(gp.GRB.INFINITY,)
        solve=mess_runtime.integrated_adapter('B2_ROOT_PROFILE',profile_mode=True)
        try:
            solve(case='B2',aidc_pcc_kw_96x12=aidc,electrical_context=electrical.legacy_context,
                voltage_authority=electrical.voltage,current_authority=electrical.current,
                route_table=route_table,service_to_pcc=mapping,
                initial_service_by_mess={'MESS01':MESS_INITIAL['MESS01']},
                fixed_mess_p_by_service={},fixed_mess_q_by_service={},
                grid_coefficients=cc,preferred_restricted_start=seed)
        except mess_runtime.FullModelCaptured:pass
        else:raise AssertionError('FULL_MODEL_CAPTURE_HOOK_NOT_REACHED')
        model=mess_runtime.PROFILE_CAPTURE['model']
        variables=model.getVars();starts=[variable.Start for variable in variables]
        assert any(float(value)<1e100 for value in starts)
        on=run_root(model,variables,starts,'ON')
        off=run_root(model,variables,starts,'OFF')
        result=dict(status='PASS',same_model_object_id=id(model),
            same_problem_and_tolerances=True,production_result_reused=False,
            model_build=read(OUT/'solver_trace/BUILD.json'),
            optimize_entry=read(OUT/'solver_trace/ENTER.json'),
            ON=on,OFF=off)
        save(OUT/'COMPARISON.json',result)
        model.dispose()
        print('ROOT_PROFILE_COMPLETE',flush=True)
    finally:module.WORK_LIMIT_TIERS=previous


if __name__=='__main__':
    try:main()
    except BaseException as error:
        save(OUT/'FAILURE.json',dict(error=repr(error),traceback=traceback.format_exc(),unix=time.time()))
        raise
