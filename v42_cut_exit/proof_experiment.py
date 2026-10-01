"""One proof primary, at most one conditional DG0, then bound-gated production."""
import subprocess,gzip
from .context import *
from .proof_context import check_proof_sources
from .proof_policy import degen_diagnostic_allowed,select
def execute(label,moves):
    atomic(LOCAL/'PROOF_EXPERIMENT_PROGRESS.json',dict(phase=label,Heuristics=0,MIPFocus=3,CutPasses='AUTO',DegenMoves=moves))
    with (LOCAL/(label+'.stdout.log')).open('w',encoding='utf8') as out,(LOCAL/(label+'.stderr.log')).open('w',encoding='utf8') as err:
        code=subprocess.run([sys.executable,'-u','-m','v42_cut_exit.proof_solve',label,'--degenmoves',str(moves)],cwd=ROOT,stdout=out,stderr=err).returncode
    assert code==0,label
    return read(OUT/(('M1_PRODUCTION' if label=='M1_PROOF' else label)+'_OPTIMIZATION.json'))
def run():
    check_proof_sources();primary=execute('PROOF_AUTO',-1);permitted=degen_diagnostic_allowed(primary)
    dump('PROOF_DEGEN_DIAGNOSTIC_AUTHORIZATION.json',dict(authorized=permitted,root_delay_threshold_seconds=120,root_completed=primary['passes'][0]['root_relaxation']['complete'],only_changed_parameter='DegenMoves',complete_internal_isolation=False))
    results=[primary]
    if permitted:results.append(execute('PROOF_DG0',0))
    policy=select(results);policy.update(Method=2,Threads=1,Seed=20260929,MIPGap=.005,formulation='M1-F3',primal_heuristic_improvement_not_acceptance=True)
    dump('SOLVER_POLICY_SELECTION.json',policy)
    if policy['production_authorized']:execute('M1_PROOF',policy['DegenMoves'])
    else:
        dump('M1_PRODUCTION_OPTIMIZATION.json',dict(run=False,authorized=False,optimize_calls=0,accepted=False,reason='Selected proof canary has no >=1e-4 global-bound gain or certified P1 quality; branch/primal improvement cannot authorize production.'))
        (OUT/'M1_PRODUCTION_PROGRESS.csv').write_text('component,seconds,incumbent,bound,nodes\n',encoding='utf8');(OUT/'M1_PRODUCTION_SOLVER.display.txt').write_text('NOT RUN: global-bound-proof gate failed.\n',encoding='utf8');(OUT/'M1_PRODUCTION_SOLVER.raw.gz').write_bytes(gzip.compress(b'',mtime=0))
    check_proof_sources();atomic(LOCAL/'PROOF_EXPERIMENT_FINISHED.json',dict(PASS=True,primary=True,DG0=permitted,production=policy['production_authorized'],CP1=False,STOP_before_A2=True));print('PROOF EXPERIMENT FINISHED',policy,flush=True)
if __name__=='__main__':run()
