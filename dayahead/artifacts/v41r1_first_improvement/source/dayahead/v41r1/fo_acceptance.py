"""Isolated computational acceptance, then unchanged Fresh and Actual consumers."""
import argparse
import os
import time
import threading
from pathlib import Path
import psutil
from dayahead.paper_analysis.storage import read,write_json
from dayahead.v41.data import RUNTIME
from dayahead.v41.preflight import record


def components(tag):
    from dayahead.v41.electrical import load
    from dayahead.v41.reserve import bind
    from dayahead.v40g_segments.canonical import import_frozen,planning_power
    from dayahead.v40h.feedback import solve_feedback
    from dayahead.v40h.recourse import solve_fixed_route
    from .bounded_solver import PolicyBudget
    from .bounded_mess import run
    root=RUNTIME/'bounded_compute'/tag
    if root.exists():raise ValueError('PRESERVE_COMPONENT_ATTEMPT')
    root.mkdir(parents=True);ctx=load('2025-05-04')
    try:
        path=RUNTIME/'inputs/2025-05-04/V41_ML_SNAPSHOT_2025-05-04.json';bind(ctx,path,record(path)['sha256'])
        jobs=import_frozen(read(RUNTIME/'inputs/2025-05-04/common_q90_v3/COMMON_B0_REFERENCE_JOBS.json'))
        ctx.v41_policy='B3';ctx.v41_bounded_compute={'total_seconds':120};ctx.v41_policy_budget=PolicyBudget(120)
        ctx.v41_a1_output=root/'A1';ctx.v41_mf_output=root/'MF'
        # Check that the inherited MESS subprocess can return a verified seed
        # at an intentionally short component deadline.
        ctx.v41_policy_budget=PolicyBudget(40)
        mess,m1=run(ctx.day,jobs,ctx,root/'M1');print('M1_COMPONENT_PASS',flush=True)
        ctx.v41_policy_budget=PolicyBudget(120)
        a1=solve_feedback(jobs,mess,ctx);write_json(root/'A1_RESULT.json',a1)
        assert a1['status']=='PASS';print('A1_COMPONENT_PASS',flush=True)
        ctx.v41_current_jobs=a1['jobs'];ctx.v41_policy_budget=PolicyBudget(60)
        mf=solve_fixed_route(planning_power(a1['jobs'],ctx)['pcc'],mess,ctx)
        from dayahead.v41.scientific_archive import document
        document(root/'MF_RESULT.json',mf);assert mf['status']=='PASS';print('MF_COMPONENT_PASS',flush=True)
        write_json(root/'COMPONENT_GATE.json',dict(status='PASS',day=ctx.day,scope='B3_M1_A1_MF_FULL_SIZE_COMPONENT_SMOKE',
            independent_component_budgets=True,production_shared_budget_not_overridden=True,
            M1=record(root/'M1/M1_RESULT.json'),A1=record(root/'A1_RESULT.json'),MF=record(root/'MF_RESULT.json')))
    finally:ctx.electrical.voltage.close();ctx.electrical.current.close()


def coordinated(tag):
    from copy import deepcopy
    import numpy as np
    from dayahead.v41.electrical import load
    from dayahead.v41.reserve import bind
    from dayahead.v40g_segments.canonical import import_frozen,planning_power,identities
    from dayahead.v40g_segments.b3 import coordinate_segments
    from dayahead.v40h.feedback import solve_feedback
    from dayahead.v40h.recourse import solve_fixed_route
    from dayahead.v41.scientific_archive import document
    from .bounded_solver import PolicyBudget
    from .bounded_mess import run
    from dayahead.v41.execution import science
    source=science()
    root=RUNTIME/'bounded_compute'/tag
    if root.exists():raise ValueError('PRESERVE_COORDINATED_ATTEMPT')
    root.mkdir(parents=True);ctx=load('2025-05-04')
    try:
        path=RUNTIME/'inputs/2025-05-04/V41_ML_SNAPSHOT_2025-05-04.json';bind(ctx,path,record(path)['sha256'])
        jobs=import_frozen(read(RUNTIME/'inputs/2025-05-04/common_q90_v3/COMMON_B0_REFERENCE_JOBS.json'))
        ctx.v41_policy='B3';ctx.v41_bounded_compute={'total_seconds':300};ctx.v41_policy_budget=PolicyBudget(300)
        ctx.v41_a1_output=root/'A1';ctx.v41_mf_output=root/'MF';candidates=[]
        def search(pcc,cert):return run(ctx.day,jobs,ctx,root/'M1')
        def feedback(current,mess):
            result=solve_feedback(current,mess,ctx)
            candidates.extend((deepcopy(current),deepcopy(result['jobs'])));return result
        def recourse(pcc,mess,certificate):
            matches=[rows for rows in candidates if np.array_equal(planning_power(rows,ctx)['pcc'],pcc) and all(certificate.get(k)==v for k,v in identities(rows).items())]
            assert matches;ctx.v41_current_jobs=matches[-1]
            return solve_fixed_route(pcc,mess,ctx)
        result=coordinate_segments(jobs,ctx,search,feedback,recourse,{'COMPONENT_ACCEPTANCE':'CURRENT_FULL_Q90_REFERENCE'})
        document(root/'COORDINATION_RESULT.json',result)
        assert ctx.v41_policy_budget.used<=305 and source==science()
        write_json(root/'COMPONENT_GATE.json',dict(status='PASS',day=ctx.day,scope='B3_FULL_SIZE_COORDINATION_SHARED_BUDGET',
            source=source,
            shared_budget_seconds=300,optimization_seconds=ctx.v41_policy_budget.used,calls=ctx.v41_policy_budget.calls,
            production_budget_seconds=1800,result=record(root/'COORDINATION_RESULT.json')))
        print('COORDINATED_SHARED_BUDGET_PASS',ctx.v41_policy_budget.used,flush=True)
    finally:ctx.electrical.voltage.close();ctx.electrical.current.close()


def full(tag):
    from dayahead.v41 import execution
    from dayahead.v41.campaign import verify_receipt
    root=RUNTIME/'fa'/tag
    if root.exists():raise ValueError('PRESERVE_FORMAL_ACCEPTANCE_ATTEMPT')
    root.mkdir(parents=True);execution.RUNS=root
    # Provision storage before generating any hashed/persisted policy artifact.
    import subprocess
    target=Path('D:/MobileESS_FO_acceptance')/tag/'2025-05-04/B1'
    target.resolve().relative_to(Path('D:/MobileESS_FO_acceptance').resolve())
    if target.exists():raise ValueError('PRESERVE_ACCEPTANCE_STORAGE')
    target.mkdir(parents=True);unit=root/'2025-05-04/B1';unit.parent.mkdir(parents=True)
    made=subprocess.run(['cmd.exe','/d','/c','mklink','/J',str(unit),str(target)],capture_output=True,text=True)
    if made.returncode or unit.resolve()!=target.resolve():raise RuntimeError('ACCEPTANCE_STORAGE_JUNCTION')
    write_json(root/'STORAGE.json',dict(logical=str(unit),physical=str(target),created_before_generation=True))
    os.environ['V41_FO_ACCEPTANCE']='1';os.environ.setdefault('V41_FO_ACCEPTANCE_SECONDS','1800')
    cap=float(os.environ['V41_FO_ACCEPTANCE_SECONDS'])
    source=execution.science();started=time.perf_counter();stop=threading.Event();samples=[]
    def sample():
        p=psutil.Process()
        while not stop.wait(1):
            samples.append(dict(seconds=time.perf_counter()-started,rss=p.memory_info().rss,
                available=psutil.virtual_memory().available))
    thread=threading.Thread(target=sample,daemon=True);thread.start()
    write_json(root/'ACCEPTANCE_STARTED.json',dict(day='2025-05-04',policy='B1',source=source,
        source_commit=execution.commit(),working_tree_validation=True,total_optimization_budget_seconds=cap))
    write_json(RUNTIME/'F_AND_O_ACCEPTANCE_PROGRESS.json',dict(status='RUNNING',day='2025-05-04',policy='B1',pid=os.getpid(),folder=str(root)))
    try:
        execution.dayahead('2025-05-04','B1');print('DAYAHEAD_AND_FRESH_PASS',flush=True)
        execution.actual('2025-05-04','B1');print('ACTUAL_PASS',flush=True)
        unit=root/'2025-05-04/B1';da=unit/'dayahead';a0=da/'A0'
        for phase in ('dayahead','actual'):verify_receipt(unit/phase/(phase.upper()+'_RECEIPT.json'))
        seed=read(a0/'POLICY_FEASIBLE_SEED_AUDIT.json');compute=read(da/'POLICY_DAY_COMPUTE_REPORT.json')
        solver=read(a0/'BOUNDED_SOLVER_REPORT.json');coverage=read(a0/'CANDIDATE_COVERAGE_REPORT.json')
        candidates=read(a0/'V41R1_FULL_CANDIDATE_MANIFEST.json')
        assert source==execution.science() and seed['status']=='PASS' and compute['optimization_seconds']<=1805
        assert candidates['top_K_pruning']==candidates['sensitivity_pruning']==candidates['hard_infeasible_removals']==0
        from .early_stop import VERSION
        if VERSION.startswith('V41R1_FIRST_IMPROVEMENT_CRITICAL_SEARCH_'):
            from .first_gate import acceptance_checks,compare
        else:
            from .early_gate import acceptance_checks,compare
        early=acceptance_checks(root,seed,compute,solver,candidates,coverage)
        write_json(root/'EARLY_STOP_ACCEPTANCE_GATE.json',early)
        refs={name:record(path) for name,path in dict(early_stop=root/'EARLY_STOP_ACCEPTANCE_GATE.json',seed=a0/'POLICY_FEASIBLE_SEED_AUDIT.json',
            compute=da/'POLICY_DAY_COMPUTE_REPORT.json',solver=a0/'BOUNDED_SOLVER_REPORT.json',
            candidates=a0/'V41R1_FULL_CANDIDATE_MANIFEST.json',coverage=a0/'CANDIDATE_COVERAGE_REPORT.json',
            dayahead=da/'DAYAHEAD_RECEIPT.json',actual=unit/'actual/ACTUAL_RECEIPT.json').items()}
        write_json(root/'ACCEPTANCE_RESULT.json',dict(status='PASS',day='2025-05-04',policy='B1',source=source,
            source_commit=execution.commit(),working_tree_validation=True,checks_A_through_O='PASS',compute_control_version=early['compute_control_version'],
            optimization_seconds=compute['optimization_seconds'],total_wall_seconds=time.perf_counter()-started,
            seed_objective_vector=seed['seed_objective_vector'],final_objective_vector=solver['stages'][-1]['accepted_objective_vector'],
            first_incumbent_seconds=next((s['first_incumbent_seconds'] for s in solver['stages'] if s['first_incumbent_seconds'] is not None),None),
            candidate_count=candidates['final_authoritative_candidates'],coverage_fraction=coverage['fraction_candidates_visited'],
            iterations=len(read(a0/'IMPROVEMENT_TRACE.json')),global_bound=None,global_gap=None,
            classification=solver['classification'],Fresh='PASS',Actual='PASS',artifacts=refs))
        compare(root/'ACCEPTANCE_RESULT.json')
        print('FORMAL_ACCEPTANCE_PASS',flush=True)
        write_json(RUNTIME/'F_AND_O_ACCEPTANCE_PROGRESS.json',dict(status='PASS',folder=str(root),result=record(root/'ACCEPTANCE_RESULT.json')))
    except BaseException as error:
        write_json(root/'ACCEPTANCE_ERROR.json',dict(error=repr(error),elapsed_seconds=time.perf_counter()-started))
        write_json(RUNTIME/'F_AND_O_ACCEPTANCE_PROGRESS.json',dict(status='FAILED',folder=str(root),error=repr(error)))
        raise
    finally:
        stop.set();thread.join()
        write_json(root/'MEMORY_SAMPLES.json',dict(samples=samples,peak_rss=max((x['rss'] for x in samples),default=0)))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['components','coordinated','full']);p.add_argument('--tag',required=True)
    a=p.parse_args();{'components':components,'coordinated':coordinated,'full':full}[a.mode](a.tag)
