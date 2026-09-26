"""Preserve the entire previous B2 attempt, then launch fresh B2 and its gates."""
import json, os, sys, time, subprocess
from pathlib import Path
import psutil
H=Path(__file__).absolute().parent
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def save(p,v):
    p.write_text(json.dumps(v,indent=2,ensure_ascii=False),encoding='utf-8')
def main():
    assert str(H).isascii()
    auth=read(H/'PAPER_SOLVER_TERMINATION_AUTHORITY.json')
    assert auth['status']=='PASS' and auth['B2_restart_from_scratch']
    assert not psutil.pid_exists(87296) and not psutil.pid_exists(86024)
    assert read(H/'B0/COMPLETE.json')['status']=='PASS'
    assert read(H/'Actual/B0/COMPLETE.json')['AC_feasible']
    diagnostic=H/'diagnostic_attempts'/('B2_UNLIMITED_SUPERSEDED_'+time.strftime('%Y%m%d_%H%M%S'))
    diagnostic.mkdir(parents=True,exist_ok=False)
    preserved=[]
    for name in ['B2','MESS_grid_certificates','B2_FAILURE.json','CAMPAIGN_FAILURE.json',
                 'STATUS.json','CAMPAIGN_STATUS.json','ACTIVE_CAMPAIGN_CONTINUATION_STATUS.json',
                 'B2_ROUTE_PQ_STAGE_RUNTIME.json']:
        p=H/name
        if not p.exists():continue
        target=diagnostic/name
        assert p.resolve().is_relative_to(H.resolve()) and target.resolve().is_relative_to(diagnostic.resolve())
        assert not target.exists()
        p.rename(target)
        preserved.append(dict(original=str(p),preserved=str(target)))
    save(diagnostic/'PRESERVATION_MANIFEST.json',dict(unix=time.time(),entries=preserved,
        reason='User requested paper termination and fresh B2; prior B2 results are diagnostic only'))
    assert not (H/'B2').exists()
    run=H/'B2_PAPER_TERMINATION_RUN_20260921';run.mkdir(exist_ok=False)
    save(H/'STATUS.json',dict(status='RUNNING',stage='B2:FRESH_PAPER_TERMINATION_START',
        termination_authority='PAPER_SOLVER_TERMINATION',B2_restart_from_scratch=True,
        prior_B2_preserved=str(diagnostic),updated_unix=time.time()))
    with (run/'stdout.log').open('x',encoding='utf-8') as out,(run/'stderr.log').open('x',encoding='utf-8') as err:
        worker=subprocess.Popen([sys.executable,'-B','-u','mess_worker.py','B2'],cwd=H,
            stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
    save(run/'LAUNCH.json',dict(PID=worker.pid,Python=sys.executable,Started=time.time(),Run=str(run),
        B2_restart_from_scratch=True,checkpoint_reuse=False,candidate_cache_reuse=False,
        previous_attempt=str(diagnostic),termination_authority=str(H/'PAPER_SOLVER_TERMINATION_AUTHORITY.json')))
    with (run/'watcher_stdout.log').open('x',encoding='utf-8') as out,(run/'watcher_stderr.log').open('x',encoding='utf-8') as err:
        watcher=subprocess.Popen([sys.executable,'-B','-u','campaign_resume_after_sparse_b2.py'],cwd=H,
            stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
    save(run/'WATCHER.json',dict(PID=watcher.pid,worker_pid=worker.pid,started_unix=time.time()))
    save(H/'CAMPAIGN_STATUS.json',dict(status='RUNNING',stage='B2_FRESH_PAPER_TERMINATION',policy='B2',
        worker_pid=worker.pid,supervisor_pid=watcher.pid,started_unix=time.time(),
        termination_authority='PAPER_SOLVER_TERMINATION',order=['B0','B2','B3','B1'],
        prior_attempt=str(diagnostic),B2_restart_from_scratch=True,
        MESS_TimeLimit=600,MESS_WorkLimit_tiers=[60,180,300],MESS_MIPGap_target=.001))
    print('FRESH_B2_STARTED',worker.pid,'WATCHER',watcher.pid,'PRESERVED',diagnostic,flush=True)
if __name__=='__main__':main()
