"""External Windows process tree; construction excluded from A1 clock."""
import os,subprocess,sys,time
from .common import *
from v42_native.supervision import ProcessTree

def main():
    LOCAL.mkdir(parents=True,exist_ok=True)
    if (LOCAL/'OPTIMIZER_STARTED.json').exists():raise ValueError('NO_OPTIMIZATION_RETRY')
    sources=[dict(path=str(p.relative_to(ROOT)).replace('\\','/'),sha256=sha(p)) for p in sorted((ROOT/'v42_exact').glob('*.py'))]
    dump('SOURCE_MANIFEST.json',dict(base=BASE,sources=sources,preregistration_sha256=sha(OUT/'PREREGISTRATION.json')))
    environment=dict(os.environ,PYTHONUTF8='1')
    with (LOCAL/'worker.log').open('w',encoding='utf8') as log:
        kwargs={'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {'start_new_session':True}
        p=subprocess.Popen([sys.executable,'-B','-m','v42_exact.worker'],cwd=ROOT,env=environment,stdout=log,stderr=subprocess.STDOUT,**kwargs)
        tree=ProcessTree(p);reason='COMPLETED';deadline=None
        try:
            while p.poll() is None:
                if deadline is None and (LOCAL/'OPTIMIZER_STARTED.json').exists():deadline=read(LOCAL/'OPTIMIZER_STARTED.json')['started_monotonic']+3600
                if deadline is not None and not (LOCAL/'OPTIMIZATION_FINISHED.json').exists() and time.monotonic()>=deadline:
                    # Gurobi has its exact TimeLimit; allow a bounded 5-second
                    # return/publication grace, then enforce process-tree wall.
                    if time.monotonic()>=deadline+5:reason='EXTERNAL_HARD_WALL';tree.close();p.wait(timeout=10);break
                time.sleep(.25)
        finally:tree.close()
    atomic(LOCAL/'SUPERVISOR.json',dict(reason=reason,exit_code=p.returncode,external_process_tree=True,optimization_only_budget_seconds=3600,return_publication_grace_seconds=5,build_charged_to_budget=False))
    if p.returncode:raise SystemExit(p.returncode)

if __name__=='__main__':main()
