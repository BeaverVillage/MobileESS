from .common import *
import subprocess
import psutil
from v42_m1_accel_vnext.native_state import inspect_live
from v42_dw_continuation.resources import WindowsCounters

def run():
    assert not (OUT/'PREREGISTRATION_AUTHORITY.json').exists(),'Do not recreate an existing grant'
    OUT.mkdir(parents=True,exist_ok=True)
    head=subprocess.check_output(['git','rev-parse','HEAD'],text=True,cwd=ROOT).strip()
    assert subprocess.check_output(['git','merge-base',PR154,'HEAD'],text=True,cwd=ROOT).strip()==PR154
    observed,heavy=inspect_live();c=WindowsCounters();telemetry=c.sample();c.close()
    admission=dict(processes=observed,heavy=heavy,available_RAM=psutil.virtual_memory().available,
        pagefile=psutil.swap_memory()._asdict(),**telemetry)
    assert not heavy and admission['available_RAM']>=1024**3 and admission['commit_percent']<95
    write('INITIAL_RESOURCE_ADMISSION.json',admission)
    cp=read(SCI/'DW_CHECKPOINT_LATEST.json')
    assert len(cp['pool'])==cp['total_retained_columns']==1604
    assert cp['best_interval']==[0.5687115725336208,0.5741861223241257]
    paths=[p for p in SCI.rglob('*') if p.is_file() and p.name!='.gitattributes']
    frozen={p.relative_to(ROOT).as_posix():sha(p) for p in paths}
    for h in cp['pool']:assert sha(ROOT/h['file'])==h['file_SHA']
    write('PR152_BYTE_FREEZE.json',dict(authority=PR152,files=frozen))
    write('ROOT1604_RESUME_AUTHORITY.json',dict(PR152=PR152,PR154=PR154,development_head=head,
        branch=subprocess.check_output(['git','branch','--show-current'],text=True,cwd=ROOT).strip(),
        worktree=str(ROOT),status=subprocess.check_output(['git','status','--short'],text=True,cwd=ROOT),
        retained_columns=1604,pool_SHA=cp['pool_SHA'],true_dual_SHA=cp['RMP']['dual_SHA'],
        LB=cp['best_interval'][0],RMP_upper=cp['best_interval'][1],exact_CG_convergence=False,
        materiality='INCONCLUSIVE',historical_PR149_native=cp['historical_PR149_optimize'],
        historical_PR152_native=cp['elapsed_budget'],historical_total_native=cp['cumulative_optimize'],
        ROOT_DEV_GRANT=1800,checkpoint_role='DEVELOPMENT_CERTIFICATION_ONLY',fresh_runtime_warm_start=False))
    write('PREREGISTRATION_AUTHORITY.json',dict(ROOT_DEV_GRANT=1800,BAP_DEV_GRANT=1800,
        benchmark_continuous_wall_cap=600,each_fresh_canary_total_native=3600,
        workers=4,Threads=1,EPS=EPS,pricing_speed_improvement_required=.20,
        initial_columns=1604,automatic_budget_extension=False,May_campaigns_authorized=False))
    (OUT/'M_STAGE_REMAINING_WORK_PREREGISTRATION.md').write_text('''# V42 M-stage remaining work preregistration

Scientific authority: PR152 63e81dc3b6d236549f566e65e07dcd05ac0a160c.
Development base: PR154 0f1dc549487759818ba8a2481b73c46085c2f9da.

1. Compare original exact MILP and PR154 LP-valued binary-label Hybrid on each of four MESS at the identical frozen true dual. All original local rows, movement, continuous SOC/P/Q and master projection are retained. Each backend gets at most 60 wall seconds per unit, within one 600 continuous-wall-second benchmark. The inherited Hybrid is a coverage prototype: incomplete search cannot certify pricing. Select only with four globally certified equivalent optima, physical/original-row/column/RC audits and at least 20% reduction in total practical wall time. Otherwise retain ORIGINAL_GUROBI_EXACT.
2. Freeze the decision. Restore exactly the PR152 1,604-column pool and completed true-dual point without reoptimization of completed calls. Create a separate 1,800 native optimize second ROOT_DEV_GRANT. The accepted historical accounting is union of concurrent optimize intervals, with the per-model sum reported separately. Build, audit, wait and preparation are separate. Keep four isolated pricing workers and Threads=1.
3. Discovery stabilization and exact validation may find columns. Only full-domain pricing at the same true RMP dual with four valid global nonnegative certificates at the existing 1e-8 numerical authority can converge root CG. Materiality never substitutes for CG convergence. No threshold-driven root stop. Append-only pool, no heuristic replacement or new tolerance.
4. Finish the last feasible native block and STOP when the new grant is exhausted or cannot admit a complete safe native block. No extra grant. Preserve final pool, dual, primal, bounds and receipts. If the root is not converged, mark M1_ROOT_NOT_CONVERGED; B&P, P2, fresh M1/M2 canaries and production are NOT_RUN_PREREQUISITE.
5. Only after converged root and required independent bound/pool/primal/matrix audits, selectively port PR145 exact B&P, rerun its exact regressions, and use its separate 1,800 native second development grant. P1 global gap <=0.005 or exact optimum; then exact movement-energy and movement-count locks.
6. Only after complete development acceptance, freeze the final source/algorithm and run ONE fresh M1 canary from the production initial-column policy, with one cumulative 3,600 native second budget. Inject no result-derived May-11 checkpoint columns. Only after M1 PASS, establish current compatible A2 and run ONE current-formulation M2 canary with one 3,600 native second budget. No tuning or budget extension from canary results.

Resource guards: available physical RAM >=1 GiB, commit <95%, no OOM, no catastrophic sustained paging, no solver/license failure. A confirmed other heavy native solve causes WAIT_RESOURCE; unrelated processes are never controlled.

Ledgers remain separate: historical development, Hybrid benchmark, root development, B&P development, fresh M1 and fresh M2. No full May B2/B3 or L1-L4 campaign is launched.
''',encoding='utf8')
    print('PREREGISTERED',head,'1604',flush=True)

if __name__=='__main__':run()
