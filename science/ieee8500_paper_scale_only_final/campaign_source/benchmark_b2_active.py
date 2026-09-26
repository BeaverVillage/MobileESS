"""Two restricted MIP iterations with exact full electrical-row separation.

This is a diagnostic benchmark. It never writes a B2 production result and
never uses a solver TimeLimit, WorkLimit, NodeLimit, or active-row cap.
"""
from bootstrap import *
from types import SimpleNamespace
import math
import re
import traceback
import gurobipy as gp
import mess_runtime
import mess_grid8500_active

OUT=H/'B2_ACTIVE_SET_DIAGNOSTIC'
SEED=H/'B2/beam/2025-05-01/B2/B2/s1/B2-ROOT/SEEDS.json'


def finite(value):
    try:
        number=float(value)
        return number if math.isfinite(number) and abs(number)<1e90 else None
    except (TypeError,ValueError,AttributeError,gp.GurobiError):
        return None


def log_metrics(path):
    body=path.read_text(encoding='utf-8',errors='replace') if path.exists() else ''
    presolve=re.search(r'Presolve time:\s*([\d.]+)s',body)
    presolved=re.search(r'Presolved:\s*([\d,]+) rows,\s*([\d,]+) columns,\s*([\d,]+) nonzeros',body)
    root=re.search(r'Root relaxation: objective\s+\S+,\s*([\d,]+) iterations,\s*([\d.]+) seconds',body)
    return dict(presolve_seconds=float(presolve.group(1)) if presolve else None,
        presolved_rows=int(presolved.group(1).replace(',','')) if presolved else None,
        presolved_columns=int(presolved.group(2).replace(',','')) if presolved else None,
        presolved_nonzeros=int(presolved.group(3).replace(',','')) if presolved else None,
        root_relaxation_iterations=int(root.group(1).replace(',','')) if root else None,
        root_relaxation_seconds=float(root.group(2)) if root else None,
        log_sha256=sha(path) if path.exists() else None)


def solve_iteration(model,index):
    assert model.Params.MIPGap==.001 and model.Params.MIPFocus==1
    assert model.Params.Threads==4
    assert model.Params.TimeLimit>=gp.GRB.INFINITY
    assert model.Params.WorkLimit>=gp.GRB.INFINITY
    assert model.Params.NodeLimit>=gp.GRB.INFINITY
    model.Params.LogToConsole=0
    model.Params.OutputFlag=1
    model.Params.DisplayInterval=30
    log=OUT/f'ITERATION_{index:02}.log'
    model.Params.LogFile=str(log)
    model.update()
    before=dict(rows=int(model.NumConstrs),columns=int(model.NumVars),
        binaries=int(model.NumBinVars),nonzeros=int(model.NumNZs),
        quadratic_constraints=int(model.NumQConstrs))
    begin_unix=time.time()
    save(OUT/f'ITERATION_{index:02}_START.json',dict(status='RUNNING',iteration=index,
        begin_unix=begin_unix,model=before,mip_gap_tolerance=.001,
        no_time_work_node_limit=True,no_active_set_cap=True,diagnostic_only=True))
    began=time.perf_counter()
    last=[0.]
    def progress(m,where):
        if where!=gp.GRB.Callback.MIP:return
        elapsed=time.perf_counter()-began
        if elapsed-last[0]<60:return
        last[0]=elapsed
        incumbent=finite(m.cbGet(gp.GRB.Callback.MIP_OBJBST))
        bound=finite(m.cbGet(gp.GRB.Callback.MIP_OBJBND))
        record=dict(status='RUNNING',iteration=index,elapsed_seconds=elapsed,
            incumbent=incumbent,best_bound=bound,
            gap=(abs(incumbent-bound)/max(abs(incumbent),1e-12)
                 if incumbent is not None and bound is not None else None),
            explored_nodes=finite(m.cbGet(gp.GRB.Callback.MIP_NODCNT)),unix=time.time())
        save(OUT/f'ITERATION_{index:02}_CURRENT.json',record)
    model.optimize(progress)
    elapsed=time.perf_counter()-began
    assert model.SolCount>0,('NO_RESTRICTED_SOLUTION',model.Status)
    restricted=dict(status=int(model.Status),seconds=elapsed,
        incumbent=float(model.ObjVal),best_bound=float(model.ObjBound),
        mip_gap=float(model.MIPGap),nodes=float(model.NodeCount),
        simplex_iterations=float(model.IterCount),barrier_iterations=float(model.BarIterCount),
        solution_count=int(model.SolCount))
    if model.Status!=gp.GRB.OPTIMAL:
        save(OUT/f'ITERATION_{index:02}_NONCLOSURE.json',restricted)
        raise RuntimeError(f'RESTRICTED_MIP_NOT_CLOSED:{model.Status}')
    separated=mess_grid8500_active.ACTIVE.separate()
    after=dict(rows=int(model.NumConstrs),columns=int(model.NumVars),
        binaries=int(model.NumBinVars),nonzeros=int(model.NumNZs),
        quadratic_constraints=int(model.NumQConstrs))
    report=dict(status='DIAGNOSTIC_ITERATION_COMPLETE',iteration=index,
        before=before,after=after,restricted=restricted,separation=separated,
        log=str(log),**log_metrics(log),diagnostic_only=True,
        no_production_result_reused=True)
    save(OUT/f'ITERATION_{index:02}_RESULT.json',report)
    print('ACTIVE_ITERATION',index,report,flush=True)
    return report


def main():
    assert read(H/'CAMPAIGN_STATUS.json')['status']=='PAUSED_FOR_ROOT_PROFILE'
    assert not (H/'B2/COMPLETE.json').exists()
    OUT.mkdir(parents=True,exist_ok=True)
    from dayahead.v34 import integrated_mess as module
    from dayahead.v35.execution import MESS_INITIAL
    with np.load(H/'MAY01_B0_AIDC_POWER.npz') as z:aidc=z['pcc'].copy()
    seed=read(SEED)[0]['dispatch']
    coefficients=mess_runtime.coefficients()
    route_table=mess_runtime.traffic()[2]
    mapping={r['service']:r['PCC'] for r in read(H/'MESS_24_SERVICE_PCC_COLUMN_BINDING.json')['services']}
    voltage=mess_runtime.Authority(control_names=np.array(NAMES),node_names=np.array(AX['nodes']))
    electrical=SimpleNamespace(legacy_context=None,voltage=voltage,current=mess_runtime.Authority())
    save(OUT/'INPUT_AUTHORITY.json',dict(status='PASS',date='2025-05-01',BG=.552,AIDC=2.4,MESS=2.,
        paper_overlay_sha256=sha(H/'IEEE8500_PCC_Overlay.dss'),
        pcc_input_sha256=sha(H/'MAY01_B0_AIDC_POWER.npz'),
        seed_sha256=sha(SEED),active_seed_sha256=sha(H/'COMPACT_B0_ACTIVE_SEED.json'),
        coefficient_shas=[c.coefficient_sha256 for c in coefficients],
        route_table_sha256=route_table.canonical_sha256,
        objective_domain_tolerance_unchanged=True,diagnostic_only=True))
    previous=module.WORK_LIMIT_TIERS
    try:
        module.WORK_LIMIT_TIERS=(gp.GRB.INFINITY,)
        solve=mess_runtime.integrated_adapter('B2_ACTIVE_SET_DIAGNOSTIC',
            profile_mode=True,grid_mode='active_seed')
        try:
            solve(case='B2',aidc_pcc_kw_96x12=aidc,electrical_context=electrical.legacy_context,
                voltage_authority=electrical.voltage,current_authority=electrical.current,
                route_table=route_table,service_to_pcc=mapping,
                initial_service_by_mess={'MESS01':MESS_INITIAL['MESS01']},
                fixed_mess_p_by_service={},fixed_mess_q_by_service={},
                grid_coefficients=coefficients,preferred_restricted_start=seed)
        except mess_runtime.FullModelCaptured:pass
        else:raise AssertionError('ACTIVE_FULL_MODEL_CAPTURE_HOOK_NOT_REACHED')
        model=mess_runtime.PROFILE_CAPTURE['model']
        assert mess_grid8500_active.ACTIVE is not None
        assert mess_runtime.PROFILE_CAPTURE['preferred_loaded']
        assert abs(mess_runtime.PROFILE_CAPTURE['quality_bound']-0.9271435999326019)<1e-8
        initial=dict(rows=int(model.NumConstrs),columns=int(model.NumVars),
            binaries=int(model.NumBinVars),nonzeros=int(model.NumNZs),
            quadratic_constraints=int(model.NumQConstrs))
        save(OUT/'INITIAL_MODEL.json',dict(status='PASS',model=initial,
            grid_seed=read(OUT/'SEED_BUILD.json'),
            build=read(OUT/'solver_trace/BUILD.json'),
            preparation=read(OUT/'solver_trace/ENTER.json')))
        iterations=[]
        for index in (1,2):
            current=solve_iteration(model,index)
            iterations.append(current)
            if current['separation']['new_rows']==0:break
        summary=dict(status='BENCHMARK_COMPLETE',initial_model=initial,
            iterations=iterations,full_separation_closed=iterations[-1]['separation']['new_rows']==0,
            production_restarted=False,production_result_reused=False)
        save(OUT/'BENCHMARK.json',summary)
        model.dispose()
        print('B2_ACTIVE_BENCHMARK_COMPLETE',flush=True)
    finally:module.WORK_LIMIT_TIERS=previous


if __name__=='__main__':
    try:main()
    except BaseException as error:
        save(OUT/'FAILURE.json',dict(error=repr(error),traceback=traceback.format_exc(),unix=time.time()))
        raise
