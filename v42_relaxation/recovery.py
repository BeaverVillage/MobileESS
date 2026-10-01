"""One representation repair after observed S3 crossover instability."""
import re
import time
from .base import *

def prepare():
    assert not (OUT/'S3_NUMERICAL_RECOVERY.json').exists()
    assert not (OUT/'S3_ROOT_LP_OPTIMIZATION.json').exists()
    matches=[]
    for process in psutil.process_iter(['pid','cmdline','cwd']):
        command=process.info['cmdline'] or []
        if command[-3:]==['-m','v42_relaxation.lp','S3'] and Path(process.info['cwd']).resolve()==ROOT:
            matches.append(process)
    assert len(matches)==1, 'EXACT_S3_PROCESS_REQUIRED'
    log=(LOCAL/'S3_ROOT.log').read_text(encoding='utf8')
    iterates=[]
    for line in log.splitlines():
        match=re.fullmatch(r'\s*(\d+)\s+([\deE+.-]+)\s+([\deE+.-]+)\s+([\deE+.-]+)\s+(\d+)s\s*',line)
        if match:
            k,obj,primal,dual,seconds=match.groups()
            iterates.append(dict(iteration=int(k),objective=float(obj),primal_infeasibility=float(primal),
                dual_infeasibility=float(dual),solver_seconds=int(seconds)))
    assert len(iterates)>=10 and all(r['primal_infeasibility']>1e6 and r['objective']>UB for r in iterates[-10:])
    assert 'Barrier solved model' in log
    wall=time.time()-(LOCAL/'S3_LP_STARTED.json').stat().st_mtime
    snapshot=OUT/'S3_INITIAL_SOURCE.zip';assert snapshot.is_file()
    process=matches[0]
    receipt=dict(aborted=False,candidate='S3',reason='Repeated very large primal infeasibility during crossover cleanup after converged barrier; no valid optimal S3 point available',
        wall_estimate_seconds=wall,wall_clock_source='system clock minus pre-optimize marker mtime; approximate interrupted wall',
        last_iterates=iterates[-10:],original_source_snapshot=snapshot.name,original_source_sha256=sha(snapshot),
        process_PID=process.pid,completed_OPTIMAL_result=False,retained_solution=False,
        repair='Explicitly infer 0 <= G <= Emax from 0 <= x <= 1 and retained Emin*x <= G <= Emax*x',
        LP_projection_identical=True,integer_physical_projection_identical=True,no_solver_parameter_change=True,
        settings=dict(Method=2,Threads=1),maximum_repairs=1,additional_strengthening_family=False,
        proof='For Emin >= 0 and x >= 0, G >= Emin*x >= 0. For Emax >= 0 and x <= 1, G <= Emax*x <= Emax. Both bounds are consequences of existing rows and domains; neither excludes any feasible extended LP or integer point.')
    dump('S3_NUMERICAL_RECOVERY.json',receipt)
    process.terminate();process.wait(timeout=15)
    log=(LOCAL/'S3_ROOT.log').read_text(encoding='utf8')
    (OUT/'S3_ABORTED_ROOT_LP_SOLVER.display.txt').write_text(log,encoding='utf8')
    (OUT/'S3_ABORTED_ROOT_LP_SOLVER.raw.gz').write_bytes(gzip.compress(log.encode(),mtime=0))
    receipt['aborted']=True;receipt['original_log_sha256']=sha(OUT/'S3_ABORTED_ROOT_LP_SOLVER.display.txt')
    dump('S3_NUMERICAL_RECOVERY.json',receipt)
    print('S3 equivalent representation recovery prepared',receipt,flush=True)

def prepare_interior():
    assert read(OUT/'S3_NUMERICAL_RECOVERY.json')['aborted']
    assert not (OUT/'S3_INTERIOR_RECOVERY.json').exists()
    assert not (OUT/'S3_ROOT_LP_OPTIMIZATION.json').exists()
    matches=[]
    for process in psutil.process_iter(['pid','cmdline','cwd']):
        command=process.info['cmdline'] or []
        if command[-4:]==['-m','v42_relaxation.lp','S3','--recover-implied-G-bounds'] and Path(process.info['cwd']).resolve()==ROOT:
            matches.append(process)
    assert len(matches)==1
    log=(LOCAL/'S3_ROOT.log').read_text(encoding='utf8')
    rows=[]
    for line in log.splitlines():
        match=re.fullmatch(r'\s*(\d+)\s+([\deE+.-]+)\s+([\deE+.-]+)\s+([\deE+.-]+)\s+(\d+)s\s*',line)
        if match:
            k,obj,primal,dual,seconds=match.groups()
            rows.append(dict(iteration=int(k),objective=float(obj),primal_infeasibility=float(primal),dual_infeasibility=float(dual),solver_seconds=int(seconds)))
    assert len(rows)>=10 and all(r['dual_infeasibility']>1e6 for r in rows[-10:])
    marker=LOCAL/'S3_COMPACT_LP_STARTED.json'
    receipt=dict(aborted=False,reason='Repeated very large dual infeasibility in compact-bound S3 crossover cleanup; no certified final S3 optimum',
        compact_attempt_wall_estimate_seconds=time.time()-marker.stat().st_mtime,
        wall_clock_source='system clock minus pre-optimize marker mtime; approximate interrupted wall',last_iterates=rows[-10:],
        next_LP_settings=dict(Method=2,Threads=1,Crossover=0),model_changed=False,LP_projection_identical=True,
        fixed_MIP_policy_changed=False,solver_parameter_search=False,maximum_interior_fallbacks=1,
        final_validation_required='Gurobi OPTIMAL plus finite full solution, original matrix residual <=1e-5 and DualVio <=1e-5',
        official_reference='https://docs.gurobi.com/projects/optimizer/en/current/reference/parameters.html#crossover',
        source_snapshot='S3_PRE_INTERIOR_SOURCE.zip',source_sha256=sha(OUT/'S3_PRE_INTERIOR_SOURCE.zip'))
    dump('S3_INTERIOR_RECOVERY.json',receipt)
    process=matches[0];process.terminate();process.wait(timeout=15)
    log=(LOCAL/'S3_ROOT.log').read_text(encoding='utf8')
    (OUT/'S3_COMPACT_ABORTED_ROOT_LP_SOLVER.display.txt').write_text(log,encoding='utf8')
    (OUT/'S3_COMPACT_ABORTED_ROOT_LP_SOLVER.raw.gz').write_bytes(gzip.compress(log.encode(),mtime=0))
    receipt['aborted']=True;receipt['log_sha256']=sha(OUT/'S3_COMPACT_ABORTED_ROOT_LP_SOLVER.display.txt')
    dump('S3_INTERIOR_RECOVERY.json',receipt);print('Single interior fallback prepared',receipt,flush=True)

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--interior',action='store_true');a=p.parse_args()
    prepare_interior() if a.interior else prepare()
