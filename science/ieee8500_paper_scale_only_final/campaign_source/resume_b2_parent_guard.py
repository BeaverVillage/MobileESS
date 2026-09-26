"""Resume this fresh paper-termination run after restoring its original guard."""
import json,time,sys,subprocess,shutil
from pathlib import Path
import psutil
H=Path(__file__).absolute().parent
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def save(p,v):
    tmp=p.with_suffix(p.suffix+'.tmp');tmp.write_text(json.dumps(v,indent=2),encoding='utf-8');tmp.replace(p)
def main():
    assert not psutil.pid_exists(103248) and not psutil.pid_exists(117104)
    auth=read(H/'PAPER_PARENT_GUARD_REPAIR_AUTHORITY.json');assert auth['status']=='PASS'
    assert not (H/'B2/COMPLETE.json').exists()
    run=H/'B2_PAPER_PARENT_GUARD_RUN_20260921';run.mkdir(exist_ok=False)
    logs=H/'logs';logs.mkdir(exist_ok=True)
    output=logs/f'B2_PARENT_GUARD_{time.time_ns()}.log'
    with output.open('x',encoding='utf-8') as f:
        worker=subprocess.Popen([sys.executable,'-B','-u','mess_worker.py','B2','--resume-paper-repair'],cwd=H,
            stdout=f,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
    launch=dict(PID=worker.pid,Python=sys.executable,Started=time.time(),Run=str(run),log=str(output),
        resume_this_fresh_paper_run=True,prior_diagnostic_results_reused=False,
        authority=str(H/'PAPER_PARENT_GUARD_REPAIR_AUTHORITY.json'))
    save(run/'LAUNCH.json',launch)
    target=H/'B2_PAPER_TERMINATION_RUN_20260921'
    shutil.copy2(target/'LAUNCH.json',run/'PREVIOUS_LAUNCH.json')
    shutil.copy2(target/'WATCHER.json',run/'PREVIOUS_WATCHER.json')
    save(target/'LAUNCH.json',launch)
    save(H/'STATUS.json',dict(status='RUNNING',stage='B2:RESUME_PAPER_PARENT_GUARD',pid=worker.pid,
        updated_unix=time.time(),termination_authority='PAPER_SOLVER_TERMINATION',
        repair_authority=str(H/'PAPER_PARENT_GUARD_REPAIR_AUTHORITY.json')))
    watcher_log=logs/f'B2_PARENT_GUARD_WATCHER_{time.time_ns()}.log'
    with watcher_log.open('x',encoding='utf-8') as f:
        watcher=subprocess.Popen([sys.executable,'-B','-u','campaign_resume_after_sparse_b2.py'],cwd=H,
            stdout=f,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
    save(target/'WATCHER.json',dict(PID=watcher.pid,worker_pid=worker.pid,started_unix=time.time(),log=str(watcher_log)))
    save(run/'WATCHER.json',read(target/'WATCHER.json'))
    save(H/'CAMPAIGN_STATUS.json',dict(status='RUNNING',stage='B2_PAPER_PARENT_GUARD_REPAIR_RESUME',policy='B2',
        worker_pid=worker.pid,supervisor_pid=watcher.pid,started_unix=time.time(),log=str(output),
        order=['B0','B2','B1','B3'],termination_authority='PAPER_SOLVER_TERMINATION',
        repair_authority=str(H/'PAPER_PARENT_GUARD_REPAIR_AUTHORITY.json')))
    print('RESUMED',worker.pid,'WATCHER',watcher.pid,'LOG',output,flush=True)
if __name__=='__main__':main()
