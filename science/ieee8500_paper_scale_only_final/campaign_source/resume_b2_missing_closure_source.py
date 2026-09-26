"""Recover a hash-identical missing frozen dependency; resume post-selection AC."""
import hashlib,json,time,sys,subprocess,shutil
from pathlib import Path
import psutil
H=Path(__file__).absolute().parent
ROOT=Path(r'C:\codex_mobileess_workspace\MobileESS_v41r3_scale_rebalance')
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):
    tmp=p.with_suffix(p.suffix+'.tmp');tmp.write_text(json.dumps(v,indent=2),encoding='utf-8');tmp.replace(p)
def main():
    assert not psutil.pid_exists(118380) and not psutil.pid_exists(109304)
    failure=read(H/'B2_FAILURE.json');assert 'selective_actual_revision_v1.py' in failure['traceback']
    d=H/'diagnostic_attempts'/('B2_CLOSURE_MISSING_SOURCE_'+time.strftime('%Y%m%d_%H%M%S'));d.mkdir(exist_ok=False)
    for name in ['B2_FAILURE.json','CAMPAIGN_STATUS.json','STATUS.json','ACTIVE_CAMPAIGN_CONTINUATION_STATUS.json',
                 'B2/ORIGINAL_SELECTED_BEFORE_EXACT.json','B2/final_exact/AC_VALIDATION.json',
                 'B2_PAPER_TERMINATION_RUN_20260921/LAUNCH.json','B2_PAPER_TERMINATION_RUN_20260921/WATCHER.json']:
        shutil.copy2(H/name,d/name.replace('/','__'))
    rule=read(ROOT/'frozen_artifacts/v41r4_restoration_revision_v1/RULE_FREEZE.json')
    source=H.parents[1]/'v41r4_final_results_pr/tools/v41r4_final_snapshot/runtime/selective_actual_revision_v1.py'
    target=ROOT/'selective_actual_revision_v1.py'
    expected=next(x for x in rule['code'] if Path(x['path'])==target)['sha256']
    assert sha(source)==expected=='870abf7ac6ab4cb34a128c714a9bf71c934492b908a79a0ba619df79cc05face'
    assert not target.exists()
    with target.open('xb') as stream:stream.write(source.read_bytes())
    checks=[]
    for row in rule['code']+[rule['local_margin']]:
        assert sha(Path(row['path']))==row['sha256'],row['path']
        checks.append(row)
    empty=H/'B2/physical_closure'
    assert empty.is_dir() and not list(empty.iterdir())
    destination=d/'empty_physical_closure_before_source_check'
    assert empty.resolve().is_relative_to(H.resolve()) and destination.resolve().is_relative_to(d.resolve())
    empty.rename(destination)
    selected=H/'B2/ORIGINAL_SELECTED_BEFORE_EXACT.json'
    authority=dict(status='PASS',restored_expected_path=str(target),source=str(source),sha256=expected,
        frozen_rule_source_checks=checks,source_content_changed=False,
        beam_search_complete=True,selected_sha256=sha(selected),resume_scope='POST_SELECTION_PHYSICAL_CLOSURE_ONLY',
        no_route_or_AIDC_reoptimization=True,original_AC_limits_unchanged=True,
        original_primary_AC=read(H/'B2/final_exact/AC_VALIDATION.json')['metrics'],
        failure_preserved=str(d),unix=time.time())
    save(H/'B2_CLOSURE_SOURCE_RESTORE_AUTHORITY.json',authority)
    logs=H/'logs';run=H/'B2_CLOSURE_SOURCE_RESTORE_RUN_20260921';run.mkdir(exist_ok=False)
    log=logs/f'B2_CLOSURE_SOURCE_RESTORE_{time.time_ns()}.log'
    with log.open('x',encoding='utf-8') as f:
        worker=subprocess.Popen([sys.executable,'-B','-u','mess_worker.py','B2','--resume-paper-repair'],cwd=H,
            stdout=f,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
    launch=dict(PID=worker.pid,Python=sys.executable,Started=time.time(),Run=str(run),log=str(log),
        resume_scope='POST_SELECTION_PHYSICAL_CLOSURE_ONLY',authority=str(H/'B2_CLOSURE_SOURCE_RESTORE_AUTHORITY.json'))
    save(run/'LAUNCH.json',launch);save(H/'B2_PAPER_TERMINATION_RUN_20260921/LAUNCH.json',launch)
    save(H/'STATUS.json',dict(status='RUNNING',stage='B2:RESTORED_SOURCE_CLOSURE_RESUME',pid=worker.pid,
        updated_unix=time.time(),source_restore_authority=str(H/'B2_CLOSURE_SOURCE_RESTORE_AUTHORITY.json')))
    watcher_log=logs/f'B2_CLOSURE_SOURCE_WATCHER_{time.time_ns()}.log'
    with watcher_log.open('x',encoding='utf-8') as f:
        watcher=subprocess.Popen([sys.executable,'-B','-u','campaign_resume_after_sparse_b2.py'],cwd=H,
            stdout=f,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
    w=dict(PID=watcher.pid,worker_pid=worker.pid,started_unix=time.time(),log=str(watcher_log))
    save(run/'WATCHER.json',w);save(H/'B2_PAPER_TERMINATION_RUN_20260921/WATCHER.json',w)
    save(H/'CAMPAIGN_STATUS.json',dict(status='RUNNING',stage='B2_POST_SELECTION_AC_CLOSURE',policy='B2',
        worker_pid=worker.pid,supervisor_pid=watcher.pid,started_unix=time.time(),log=str(log),
        order=['B0','B2','B1','B3'],source_restore_authority=str(H/'B2_CLOSURE_SOURCE_RESTORE_AUTHORITY.json')))
    print('CLOSURE_RESUMED',worker.pid,'WATCHER',watcher.pid,'RESTORED_SHA',expected,flush=True)
if __name__=='__main__':main()
