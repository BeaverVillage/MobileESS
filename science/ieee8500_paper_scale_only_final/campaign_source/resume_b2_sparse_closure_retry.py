"""Preserve the failed closure and resume only its post-selection correction."""
import ast, hashlib, json, time, sys, subprocess, shutil
from pathlib import Path
import psutil
H=Path(__file__).absolute().parent
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):
    tmp=p.with_suffix(p.suffix+'.tmp');tmp.write_text(json.dumps(v,indent=2),encoding='utf-8');tmp.replace(p)
def main():
    launch_path=H/'B2_PAPER_TERMINATION_RUN_20260921/LAUNCH.json'
    watcher_path=H/'B2_PAPER_TERMINATION_RUN_20260921/WATCHER.json'
    assert not psutil.pid_exists(read(launch_path)['PID'])
    assert not psutil.pid_exists(read(watcher_path)['PID'])
    assert 'closure_sparse_grid.py' in read(H/'B2_FAILURE.json')['traceback']
    assert not (H/'B2/COMPLETE.json').exists()
    for name in ('closure_numeric_entry.py','closure_sparse_grid.py','physical_closure.py'):
        ast.parse((H/name).read_text(encoding='utf-8'))
    selected=H/'B2/ORIGINAL_SELECTED_BEFORE_EXACT.json'
    assert sha(selected)=='e403e4bf153829ded2e92f644a84334de8f21fe3ece0f2e45ce0c5a21b8ca99e'
    assert read(H/'B2_SPARSE_CLOSURE_CACHE_PREFLIGHT/RESULT.json')['status']=='PASS'
    stamp=time.strftime('%Y%m%d_%H%M%S')
    d=H/'diagnostic_attempts'/('B2_SPARSE_CLOSURE_'+stamp);d.mkdir(exist_ok=False)
    for name in ('B2_FAILURE.json','STATUS.json','CAMPAIGN_STATUS.json','ACTIVE_CAMPAIGN_CONTINUATION_STATUS.json','B2_SPARSE_CLOSURE_REPAIR_AUTHORITY.json',
                 'B2_PAPER_TERMINATION_RUN_20260921/LAUNCH.json','B2_PAPER_TERMINATION_RUN_20260921/WATCHER.json'):
        shutil.copy2(H/name,d/name.replace('/','__'))
    old=H/'B2/physical_closure';dest=d/'physical_closure'
    assert old.resolve().is_relative_to(H.resolve()) and dest.resolve().is_relative_to(d.resolve())
    old.rename(dest)
    authority=dict(status='BOUND_FOR_RUNTIME_FULL_ROW_AUDIT',selected_sha256=sha(selected),
        original_selected_unchanged=True,beam_search_restarted=False,route_or_AIDC_search_calls=0,
        original_entry_failure=read(d/'B2_FAILURE.json'),failure_preserved=str(d),
        repair_scope='SPARSE_RESTORATION_WITH_FULL_ELECTRICAL_SEPARATION',
        maximum_admissible_entry_residual=1e-6,entry_is_not_final_acceptance=True,
        final_acceptance_tolerance=1e-9,physical_limits_unchanged=True,
        objective_domain_constraints_unchanged=True,paper_termination_unchanged=True,
        files={name:sha(H/name) for name in ('closure_numeric_entry.py','closure_sparse_grid.py','physical_closure.py')},unix=time.time())
    save(H/'B2_SPARSE_CLOSURE_REPAIR_AUTHORITY.json',authority)
    run=H/('B2_SPARSE_CLOSURE_RUN_'+stamp);run.mkdir(exist_ok=False)
    log=H/'logs'/f'B2_SPARSE_CLOSURE_{stamp}.log'
    with log.open('x',encoding='utf-8') as f:
        worker=subprocess.Popen([sys.executable,'-B','-u','mess_worker.py','B2','--resume-paper-repair'],cwd=H,
            stdout=f,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
    launch=dict(PID=worker.pid,Python=sys.executable,Started=time.time(),Run=str(run),log=str(log),
        resume_scope='POST_SELECTION_PHYSICAL_CLOSURE_ONLY',authority=str(H/'B2_SPARSE_CLOSURE_REPAIR_AUTHORITY.json'))
    save(run/'LAUNCH.json',launch);save(launch_path,launch)
    save(H/'STATUS.json',dict(status='RUNNING',stage='B2:NUMERICAL_ENTRY_CLOSURE_RESUME',pid=worker.pid,updated_unix=time.time()))
    watcher_log=H/'logs'/f'B2_SPARSE_CLOSURE_WATCHER_{stamp}.log'
    with watcher_log.open('x',encoding='utf-8') as f:
        watcher=subprocess.Popen([sys.executable,'-B','-u','campaign_resume_after_sparse_b2.py'],cwd=H,
            stdout=f,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
    w=dict(PID=watcher.pid,worker_pid=worker.pid,started_unix=time.time(),log=str(watcher_log))
    save(run/'WATCHER.json',w);save(watcher_path,w)
    save(H/'CAMPAIGN_STATUS.json',dict(status='RUNNING',stage='B2_POST_SELECTION_AC_CLOSURE',policy='B2',
        worker_pid=worker.pid,supervisor_pid=watcher.pid,started_unix=time.time(),log=str(log),
        order=['B0','B2','B1','B3'],repair_authority=str(H/'B2_SPARSE_CLOSURE_REPAIR_AUTHORITY.json')))
    print(json.dumps(dict(worker=worker.pid,watcher=watcher.pid,log=str(log),run=str(run))),flush=True)
if __name__=='__main__':main()
