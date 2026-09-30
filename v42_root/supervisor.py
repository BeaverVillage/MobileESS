"""External process-tree wall on each active slice of the one A1 budget."""
import subprocess
from v42_native.supervision import ProcessTree
from .common import *
def main():
    if (LOCAL/'PRIMARY_STARTED.json').exists():raise ValueError('NO_PRIMARY_RETRY')
    frozen();dump('SOURCE_MANIFEST.json',dict(base=BASE,sources=[dict(path=str(p.relative_to(ROOT)).replace('\\','/'),sha256=sha(p)) for p in sorted((ROOT/'v42_root').glob('*.py'))],preregistration_sha256=sha(OUT/'PREREGISTRATION.json'),before_primary_optimization=True))
    with (LOCAL/'A1_WORKER.log').open('w',encoding='utf8') as log:
        p=subprocess.Popen([sys.executable,'-B','-m','v42_root.worker'],cwd=ROOT,env=dict(os.environ,PYTHONUTF8='1'),stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
        tree=ProcessTree(p);reason='COMPLETED'
        try:
            while p.poll() is None:
                path=LOCAL/'ACTIVE_OPTIMIZATION.json'
                if path.exists():
                    state=read(path)
                    if state['active'] and time.monotonic()>=state['started_monotonic']+state['remaining_budget_seconds']+5:reason='EXTERNAL_HARD_WALL';tree.close();p.wait(timeout=10);break
                time.sleep(.25)
        finally:tree.close()
    atomic(LOCAL/'SUPERVISOR.json',dict(reason=reason,exit_code=p.returncode,external_process_tree=True,optimization_only_budget_seconds=3600,return_publication_grace_seconds=5,build_validation_and_start_generation_charged=False))
    if p.returncode:raise SystemExit(p.returncode)
if __name__=='__main__':main()
