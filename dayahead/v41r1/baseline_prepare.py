"""Four independent causal snapshot preparation workers, with durable progress."""
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
import json,os,subprocess,sys,threading,time
from dayahead.paper_analysis.storage import write_json
from dayahead.v41.preflight import ROOT
from dayahead.v41.data import RUNTIME


def snapshots():
    from dayahead.tools.v41_detached_launcher import provision_git
    provision_git(sys.argv[1])
    state=dict(status='RUNNING',stage='CAUSAL_ML_PERSISTENCE',workers=4,days={},pid=os.getpid())
    lock=threading.RLock()
    def save():
        state['updated_at']=time.time()
        write_json(RUNTIME/'BASELINE_PREPARATION_PROGRESS.json',state)
    def run(day):
        log=ROOT/'logs/v41r1_migration/baseline_prepare'/f'{day}.log';log.parent.mkdir(parents=True,exist_ok=True)
        code=("from dayahead.v41.snapshot import create,capacity_authority; "
              "from dayahead.v41r1.migration_persistence import pre_solve; "
              f"p,s=create('{day}'); pre_solve('{day}',p,capacity_authority()[0]); print('SNAPSHOT_PERSISTENCE_PASS',flush=True)")
        with log.open('a',encoding='utf-8') as stream:
            proc=subprocess.Popen([sys.executable,'-u','-c',code],cwd=ROOT,stdin=subprocess.DEVNULL,stdout=stream,stderr=subprocess.STDOUT)
            with lock:state['days'][day]=dict(status='RUNNING',pid=proc.pid,log=str(log));save()
            result=proc.wait()
        with lock:state['days'][day].update(status='PASS' if result==0 else 'FAIL',returncode=result);save()
        return result
    with ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(run,[f'2025-05-{d:02}' for d in range(1,32)]))
    with lock:state['status']='PASS' if not any(results) else 'FAIL';save()
    print(state['status'],flush=True)


if __name__=='__main__':snapshots()
