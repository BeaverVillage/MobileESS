"""Continue completed LP evidence if an injection-only benchmark timed out.

Incomplete benchmarks are rejected for selection, never called equivalent
optimal objectives. The real-algebraic projection proof remains independent.
"""
import subprocess,sys
from v42_root.common import *
from .diagnostics import execute
from .thread_policy import extra_allowed,four_is_better
from .production import execute_production
def run():
    assert not (LOCAL/'M1/STARTED.json').exists()
    manifest=read(OUT/'SOURCE_MANIFEST.json')
    for r in manifest['sources']:assert sha(ROOT/r['path'])==r['sha256']
    candidates=read(OUT/'FORMULATION_CANDIDATES.json')['primary_LP_candidates'];lp=[]
    for n in candidates:
        r=read(OUT/f'lp_{n}_T1.json');p=r['passes'][0];pres=p['presolved'] or {}
        lp.append(dict(candidate=n,LP_complete=p['quality_PASS'],status=p['status'],Threads=1,Method=1,solve_wall_seconds=p['solve_wall_seconds'],objective=p['incumbent'] if p['quality_PASS'] else None,presolved=pres,warnings=p['warnings']))
    optimal=[r for r in lp if r['LP_complete']];assert optimal,'NO_COMPLETED_LP_REQUIRES_SEPARATE_BOUNDED_FALLBACK'
    assert max(r['objective'] for r in optimal)-min(r['objective'] for r in optimal)<=1e-5
    candidate=min(optimal,key=lambda r:r['solve_wall_seconds'])['candidate'];method=1;threads=1
    atomic(LOCAL/'DIAGNOSTIC_PROGRESS.json',dict(phase='ROOT_CANARY',candidate=candidate,Threads=1,Method=1))
    one=execute(candidate,'canary');canaries=[one];p=one['passes'][0];assert p['MIP_start_accepted']
    reason='Actual single-thread MIP root LP completed within 300s; four-thread diagnostic prohibited. Root cut/processing wall reported separately.'
    if extra_allowed(p):
        atomic(LOCAL/'DIAGNOSTIC_PROGRESS.json',dict(phase='ONE_EXTRA_CPU_CANARY',candidate=candidate,Threads=4,Method=2))
        four=execute(candidate,'canary',4,2);canaries.append(four);q=four['passes'][0];assert q['MIP_start_accepted']
        if four_is_better(p,q):threads=4;method=2
        reason='Actual single-thread MIP root LP exceeded 300s or was unfinished under the 600s root canary cap; exactly one same-formulation four-thread barrier diagnostic; select completed/faster root LP, otherwise retain one thread.'
    rows=[]
    for r in canaries:
        p=r['passes'][0];root=p['root'] or {};pres=p['presolved'] or {}
        rows.append(dict(candidate=candidate,Threads=r['settings']['Threads'],Method=r['settings']['Method'],NodeLimit=1,status=p['status'],wall_seconds=p['solve_wall_seconds'],presolve_seconds=p['presolve_seconds'],presolved_rows=pres.get('rows'),presolved_columns=pres.get('columns'),presolved_nonzeros=pres.get('nonzeros'),root_LP_seconds=root.get('seconds'),root_LP_complete=root.get('LP_complete'),root_processing_wall_seconds=p['root_processing_wall_seconds'],root_processing_complete=p['root_processing_complete'],root_bound=p['bound'],incumbent=p['incumbent'],gap=p['relative_gap'],MIP_start_accepted=p['MIP_start_accepted'],first_incumbent_seconds=p['first_incumbent_seconds'],cuts=json.dumps(p['cut_report']),peak_RSS_bytes=r['peak_RSS_bytes']))
    table('ROOT_NODE_CANARY.csv',rows)
    sources=manifest['sources']+[dict(path='v42_m1_sparse/'+n,sha256=sha(ROOT/'v42_m1_sparse'/n)) for n in ['finalize_diagnostics.py','thread_policy.py','production.py','quality.py']]
    for r in sources:assert sha(ROOT/r['path'])==r['sha256']
    manifest['sources']=sources;dump('SOURCE_MANIFEST.json',manifest)
    dump('FORMULATION_SELECTION.json',dict(frozen=True,candidate=candidate,threads=threads,method=method,LP_ranking=sorted(lp,key=lambda r:(not r['LP_complete'],r['solve_wall_seconds'])),LP_objective_agreement_PASS=True,LP_objective_agreement_scope='completed optima only; timed-out candidates rejected for selection; universal equal LP projection separately proven algebraically',LP_objective_spread=max(r['objective'] for r in optimal)-min(r['objective'] for r in optimal),LP_objective_tolerance=1e-5,rejected_incomplete_candidates=[r['candidate'] for r in lp if not r['LP_complete']],root_canaries=rows,thread_reason=reason,extra_four_thread_diagnostics=len(canaries)-1,scaling=False,AIDC_ANCHOR_FOLDED_INTO_CONSTANTS=True,production_calls_allowed=1,production_start_sha256=sha(LOCAL/'PR106_M1_PLAN.json'),sources=sources))
    atomic(LOCAL/'DIAGNOSTIC_PROGRESS.json',dict(phase='ONE_PRODUCTION',candidate=candidate,Threads=threads,Method=method))
    execute_production(candidate,threads,method)
    atomic(LOCAL/'DIAGNOSTICS_FINISHED.json',dict(PASS=True,one_production=True,incomplete_LP_candidates_rejected=True,STOP_before_A2=True))
if __name__=='__main__':run()
