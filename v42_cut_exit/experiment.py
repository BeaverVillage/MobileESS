"""Exactly two primary canaries and gated optional/production execution."""
import subprocess
from .context import *
from .policy import isolation_allowed,select
def execute(label,cp,h0=False):
    command=[sys.executable,'-u','-m','v42_cut_exit.solve',label,'--cutpasses',str(cp)]
    if h0:command+=['--heuristics','0']
    atomic(LOCAL/'EXPERIMENT_PROGRESS.json',dict(phase=label,CutPasses=cp,Heuristics=0 if h0 else 'default'))
    with (LOCAL/(label+'.stdout.log')).open('w',encoding='utf8') as out,(LOCAL/(label+'.stderr.log')).open('w',encoding='utf8') as err:
        code=subprocess.run(command,cwd=ROOT,stdout=out,stderr=err).returncode
    assert code==0,label
    return read(OUT/(('M1_PRODUCTION' if label=='M1' else label)+'_OPTIMIZATION.json'))
def run():
    check_sources();a=execute('CP0',0);b=execute('CP1',1)
    permitted=isolation_allowed(a,b)
    dump('OPTIONAL_HEURISTIC_ISOLATION.json',dict(authorized=permitted,run=False,production_eligible=False,reason='Both primary canaries remain at root for >=80% wall without confirmed non-root entry by 450s.' if permitted else 'At least one primary leaves root or does not meet the root-stuck gate.'))
    if permitted:
        extra=execute('CP0_H0',0,True)
        dump('OPTIONAL_HEURISTIC_ISOLATION.json',dict(authorized=True,run=True,production_eligible=False,optimization=extra))
    policy=select(a,b);policy.update(Method=2,Threads=1,Seed=20260929,MIPGap=.005,formulation='M1-F3',ranking_rule=read(OUT/'CUTPASS_EXPERIMENT_CONTRACT.json')['selection'])
    dump('SOLVER_POLICY_SELECTION.json',policy)
    if policy['production_authorized']:execute('M1',policy['CutPasses'])
    else:
        dump('M1_PRODUCTION_OPTIMIZATION.json',dict(run=False,authorized=False,reason='Neither primary canary meets the preregistered meaningful-improvement gate.',optimize_calls=0,accepted=False))
        (OUT/'M1_PRODUCTION_PROGRESS.csv').write_text('component,seconds,incumbent,bound,nodes\n',encoding='utf8')
        (OUT/'M1_PRODUCTION_SOLVER.display.txt').write_text('NOT RUN: production improvement gate failed.\n',encoding='utf8')
        import gzip
        (OUT/'M1_PRODUCTION_SOLVER.raw.gz').write_bytes(gzip.compress(b'',mtime=0))
    check_sources();atomic(LOCAL/'EXPERIMENT_FINISHED.json',dict(PASS=True,CP0=True,CP1=True,H0=permitted,production=policy['production_authorized'],STOP_before_A2=True));print('EXPERIMENT FINISHED',policy,flush=True)
if __name__=='__main__':run()
