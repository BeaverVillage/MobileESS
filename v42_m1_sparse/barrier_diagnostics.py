"""Single method fallback after all fixed dual-simplex diagnostics fail."""
import subprocess,sys,shutil,gzip
from v42_root.common import *
from .diagnostics import execute
from .thread_policy import extra_allowed,four_is_better
from .production import execute_production
def run():
    assert not (LOCAL/'M1/STARTED.json').exists()
    initial=read(OUT/'SOURCE_MANIFEST.json')
    for r in initial['sources']:assert sha(ROOT/r['path'])==r['sha256']
    candidates=read(OUT/'FORMULATION_CANDIDATES.json')['primary_LP_candidates']
    previous={n:read(OUT/f'lp_{n}_T1.json') for n in candidates}
    assert not any(r['passes'][0]['quality_PASS'] for r in previous.values()),'FALLBACK_ONLY_IF_NO_LP_COMPLETED'
    assert len(candidates)<=3
    shutil.copyfile(OUT/'P1_LP_RELAXATION_COMPARISON.csv',OUT/'P1_LP_RELAXATION_METHOD1_ATTEMPTS.csv')
    logdir=OUT/'P1_LP_RELAXATION_LOGS';backup=logdir/'METHOD1';backup.mkdir(exist_ok=True)
    for p in logdir.iterdir():
        if p.is_file():shutil.copyfile(p,backup/p.name)
    dump('LP_METHOD_FALLBACK_RECEIPT.json',dict(initial_method=1,fallback_method=2,Threads=1,candidates=candidates,reason='All three exact compressed LPs stopped without a completed optimum under the same 600s dual-simplex cap; coefficient-range/Markowitz warnings preserved. One fixed barrier configuration is the secondary numerical diagnostic, after structural compression, not a parameter grid.',previous_results=previous,initial_sources=initial['sources'],scientific_model_code_changed=False,scaling=False,additional_GPU_or_four_thread_LP=False))
    lp=[]
    for n in candidates:
        name=f'barrier_lp_{n}'
        atomic(LOCAL/'DIAGNOSTIC_PROGRESS.json',dict(phase='ONE_FIXED_BARRIER_LP_COHORT',candidate=n,Threads=1,Method=2))
        with (LOCAL/(name+'.stdout.log')).open('w',encoding='utf8') as out,(LOCAL/(name+'.stderr.log')).open('w',encoding='utf8') as err:
            code=subprocess.run([sys.executable,'-u','-m','v42_m1_sparse.alternate_lp',n],cwd=ROOT,stdout=out,stderr=err).returncode
        assert code==0,name
        r=read(OUT/'METHOD2_LP'/f'lp_{n}_T1.json');p=r['passes'][0];pres=p['presolved'] or {}
        lp.append(dict(candidate=n,status=p['status'],LP_complete=p['quality_PASS'],Threads=1,Method=2,presolve_seconds=p['presolve_seconds'],presolved_rows=pres.get('rows'),presolved_columns=pres.get('columns'),presolved_nonzeros=pres.get('nonzeros'),iterations=p['iterations'],barrier_iterations=p['barrier_iterations'],solve_wall_seconds=p['solve_wall_seconds'],objective=p['incumbent'] if p['quality_PASS'] else None,warnings=json.dumps(p['warnings']),peak_RSS_bytes=r['peak_RSS_bytes']))
        table('P1_LP_RELAXATION_COMPARISON.csv',lp)
        native=LOCAL/'METHOD2_LP'/f'lp_{n}_T1/GUROBI.log';raw=native.read_bytes()
        (logdir/(n+'.raw.gz')).write_bytes(gzip.compress(raw,mtime=0));(logdir/(n+'.display.txt')).write_text('\n'.join(x.rstrip() for x in raw.decode('utf8').splitlines())+'\n',encoding='utf8')
        atomic(logdir/(n+'.receipt.json'),dict(native_path=str(native),native_sha256=sha(native),raw_bytes=len(raw),raw_gzip_sha256=sha(logdir/(n+'.raw.gz')),native_bytes_preserved=True,Method=2))
    good=[r for r in lp if r['LP_complete']];assert len(good)>=2,'NEED_TWO_COMPLETED_LP_OPTIMA_FOR_NUMERICAL_AGREEMENT'
    spread=max(r['objective'] for r in good)-min(r['objective'] for r in good);assert spread<=1e-7,'P1_LP_OBJECTIVE_DISAGREEMENT'
    candidate=min(good,key=lambda r:r['solve_wall_seconds'])['candidate'];threads=1;method=2
    atomic(LOCAL/'DIAGNOSTIC_PROGRESS.json',dict(phase='ROOT_CANARY',candidate=candidate,Threads=1,Method=2))
    one=execute(candidate,'canary',1,2);canaries=[one];p=one['passes'][0];assert p['MIP_start_accepted']
    reason='Actual single-thread MIP root LP completed within 300s; no four-thread test. Root cut/processing wall reported separately.'
    if extra_allowed(p):
        atomic(LOCAL/'DIAGNOSTIC_PROGRESS.json',dict(phase='ONE_EXTRA_CPU_CANARY',candidate=candidate,Threads=4,Method=2))
        four=execute(candidate,'canary',4,2);canaries.append(four);q=four['passes'][0];assert q['MIP_start_accepted']
        if four_is_better(p,q):threads=4
        reason='Actual single-thread MIP root LP exceeded 300s or was unfinished under the 600s cap; exactly one same-formulation four-thread barrier canary; retain one thread unless four-thread root LP completes or is faster.'
    rows=[]
    for r in canaries:
        p=r['passes'][0];root=p['root'] or {};pres=p['presolved'] or {}
        rows.append(dict(candidate=candidate,Threads=r['settings']['Threads'],Method=2,NodeLimit=1,status=p['status'],wall_seconds=p['solve_wall_seconds'],presolve_seconds=p['presolve_seconds'],presolved_rows=pres.get('rows'),presolved_columns=pres.get('columns'),presolved_nonzeros=pres.get('nonzeros'),root_LP_seconds=root.get('seconds'),root_LP_complete=root.get('LP_complete'),root_processing_wall_seconds=p['root_processing_wall_seconds'],root_processing_complete=p['root_processing_complete'],root_bound=p['bound'],incumbent=p['incumbent'],gap=p['relative_gap'],MIP_start_accepted=p['MIP_start_accepted'],first_incumbent_seconds=p['first_incumbent_seconds'],cuts=json.dumps(p['cut_report']),peak_RSS_bytes=r['peak_RSS_bytes']))
    table('ROOT_NODE_CANARY.csv',rows)
    sources=initial['sources']+[dict(path='v42_m1_sparse/'+n,sha256=sha(ROOT/'v42_m1_sparse'/n)) for n in ['alternate_lp.py','barrier_diagnostics.py','thread_policy.py','production.py','quality.py']]
    for r in sources:assert sha(ROOT/r['path'])==r['sha256']
    initial['sources']=sources;initial['bounded_single_method_fallback']=True;dump('SOURCE_MANIFEST.json',initial)
    dump('FORMULATION_SELECTION.json',dict(frozen=True,candidate=candidate,threads=threads,method=2,LP_ranking=sorted(lp,key=lambda r:(not r['LP_complete'],r['solve_wall_seconds'])),LP_objective_agreement_PASS=True,LP_objective_agreement_scope='completed optima under one identical barrier configuration; method1 incomplete attempts retained',LP_objective_spread=spread,LP_objective_tolerance=1e-7,rejected_incomplete_candidates=[r['candidate'] for r in lp if not r['LP_complete']],root_canaries=rows,thread_reason=reason,extra_four_thread_diagnostics=len(canaries)-1,scaling=False,AIDC_ANCHOR_FOLDED_INTO_CONSTANTS=True,production_calls_allowed=1,production_start_sha256=sha(LOCAL/'PR106_M1_PLAN.json'),sources=sources))
    atomic(LOCAL/'DIAGNOSTIC_PROGRESS.json',dict(phase='ONE_PRODUCTION',candidate=candidate,Threads=threads,Method=2))
    execute_production(candidate,threads,2)
    atomic(LOCAL/'DIAGNOSTICS_FINISHED.json',dict(PASS=True,one_production=True,single_method_fallback=True,STOP_before_A2=True))
if __name__=='__main__':run()
