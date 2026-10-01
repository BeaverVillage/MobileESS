"""Sequential diagnostic decisions, then one immutable production invocation."""
import subprocess,sys,shutil,gzip
from v42_root.common import *
from .select import run as structural_selection

def execute(candidate,mode,threads=1,method=1):
    name=f'{mode}_{candidate}_T{threads}'
    with (LOCAL/(name+'.stdout.log')).open('w',encoding='utf8') as out,(LOCAL/(name+'.stderr.log')).open('w',encoding='utf8') as err:
        r=subprocess.run([sys.executable,'-u','-m','v42_m1_sparse.solve',candidate,mode,'--threads',str(threads),'--method',str(method)],cwd=ROOT,stdout=out,stderr=err)
    assert r.returncode==0,name
    return read(OUT/(name+'.json')) if mode!='production' else read(OUT/'M1_OPTIMIZATION.json')

def run():
    assert read(LOCAL/'STRUCTURAL_FINISHED.json')['PASS']
    structural_selection();selection=read(OUT/'FORMULATION_CANDIDATES.json');lp=[]
    logdir=OUT/'P1_LP_RELAXATION_LOGS';logdir.mkdir(exist_ok=True)
    sources=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for folder in ['v42_m1_sparse','v42_native','v42_bootstrap','v42_two'] for p in sorted((ROOT/folder).glob('*.py'))]
    dump('SOURCE_MANIFEST.json',dict(base_head='0360f9db7a27068dc53665b263a93adfd870250f',sources=sources,benchmark_sources_frozen=True))
    for candidate in selection['primary_LP_candidates']:
        atomic(LOCAL/'DIAGNOSTIC_PROGRESS.json',dict(phase='LP',candidate=candidate))
        result=execute(candidate,'lp');p=result['passes'][0];pres=p['presolved'] or {}
        row=dict(candidate=candidate,status=p['status'],LP_complete=p['quality_PASS'],Threads=1,Method=1,presolve_seconds=p['presolve_seconds'],presolved_rows=pres.get('rows'),presolved_columns=pres.get('columns'),presolved_nonzeros=pres.get('nonzeros'),iterations=p['iterations'],barrier_iterations=p['barrier_iterations'],solve_wall_seconds=p['solve_wall_seconds'],objective=p['incumbent'] if p['quality_PASS'] else None,warnings=json.dumps(p['warnings']),peak_RSS_bytes=result['peak_RSS_bytes'])
        lp.append(row);table('P1_LP_RELAXATION_COMPARISON.csv',lp)
        native=LOCAL/f'lp_{candidate}_T1/GUROBI.log';raw=native.read_bytes()
        (logdir/(candidate+'.raw.gz')).write_bytes(gzip.compress(raw,mtime=0))
        (logdir/(candidate+'.display.txt')).write_text('\n'.join(s.rstrip() for s in raw.decode('utf8').splitlines())+'\n',encoding='utf8')
        atomic(logdir/(candidate+'.receipt.json'),dict(native_sha256=sha(native),raw_bytes=len(raw),raw_gzip_sha256=sha(logdir/(candidate+'.raw.gz')),native_bytes_preserved=True))
    optimal=[r for r in lp if r['LP_complete']]
    assert optimal,'NO_COMPLETED_EXACT_LP'
    assert max(r['objective'] for r in optimal)-min(r['objective'] for r in optimal)<=1e-5,'LP_BOUND_DISAGREEMENT'
    assert len(optimal)==len(lp),'INCOMPLETE_SELECTED_LP_DIAGNOSTIC'
    best=min(optimal,key=lambda r:r['solve_wall_seconds']);candidate=best['candidate']
    atomic(LOCAL/'DIAGNOSTIC_PROGRESS.json',dict(phase='ROOT_CANARY',candidate=candidate,Threads=1))
    one=execute(candidate,'canary');canaries=[one];p=one['passes'][0]
    assert p['MIP_start_accepted'],'CANARY_MIP_START_NOT_ACCEPTED'
    thread=1;method=1;reason='Measured single-thread root processing <=300s; no four-thread diagnostic permitted.'
    if p['root_processing_wall_seconds']>300:
        atomic(LOCAL/'DIAGNOSTIC_PROGRESS.json',dict(phase='ONE_EXTRA_CPU_CANARY',candidate=candidate,Threads=4))
        four=execute(candidate,'canary',4,2);canaries.append(four);q=four['passes'][0]
        assert q['MIP_start_accepted'],'EXTRA_CANARY_MIP_START_NOT_ACCEPTED'
        if q['root_processing_complete'] and (not p['root_processing_complete'] or q['root_processing_wall_seconds']<p['root_processing_wall_seconds']):thread=4;method=2
        elif q['root'] and q['root']['LP_complete'] and (not p['root'] or not p['root']['LP_complete']):thread=4;method=2
        reason='Single-thread root processing exceeded 300s; exactly one same-formulation Threads=4 Method=2 diagnostic; select completed/faster root processing, otherwise retain Threads=1.'
    rows=[]
    for r in canaries:
        p=r['passes'][0];root=p['root'] or {};pres=p['presolved'] or {}
        rows.append(dict(candidate=candidate,Threads=r['settings']['Threads'],Method=r['settings']['Method'],NodeLimit=1,status=p['status'],wall_seconds=p['solve_wall_seconds'],presolve_seconds=p['presolve_seconds'],presolved_rows=pres.get('rows'),presolved_columns=pres.get('columns'),presolved_nonzeros=pres.get('nonzeros'),root_LP_seconds=root.get('seconds'),root_LP_complete=root.get('LP_complete'),root_processing_wall_seconds=p['root_processing_wall_seconds'],root_processing_complete=p['root_processing_complete'],root_bound=p['bound'],incumbent=p['incumbent'],gap=p['relative_gap'],MIP_start_accepted=p['MIP_start_accepted'],first_incumbent_seconds=p['first_incumbent_seconds'],cuts=json.dumps(p['cut_report']),peak_RSS_bytes=r['peak_RSS_bytes']))
    table('ROOT_NODE_CANARY.csv',rows)
    for src in sources:assert sha(ROOT/src['path'])==src['sha256'],'BENCHMARK_SOURCE_DRIFT:'+src['path']
    dump('FORMULATION_SELECTION.json',dict(frozen=True,candidate=candidate,threads=thread,method=method,LP_ranking=sorted(lp,key=lambda r:r['solve_wall_seconds']),LP_objective_agreement_PASS=True,LP_objective_tolerance=1e-5,LP_objective_spread=max(r['objective'] for r in optimal)-min(r['objective'] for r in optimal),root_canaries=rows,thread_reason=reason,extra_four_thread_diagnostics=len(canaries)-1,scaling=False,AIDC_ANCHOR_FOLDED_INTO_CONSTANTS=True,production_calls_allowed=1,production_start_sha256=sha(LOCAL/'PR106_M1_PLAN.json'),sources=sources))
    atomic(LOCAL/'DIAGNOSTIC_PROGRESS.json',dict(phase='ONE_PRODUCTION',candidate=candidate,Threads=thread,Method=method))
    execute(candidate,'production',thread,method)
    atomic(LOCAL/'DIAGNOSTICS_FINISHED.json',dict(PASS=True,one_production=True,STOP_before_A2=True))
if __name__=='__main__':run()
