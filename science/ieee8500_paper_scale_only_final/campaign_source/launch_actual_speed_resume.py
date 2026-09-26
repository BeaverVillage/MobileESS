"""Preserve the original slow attempt, then resume from accepted Actual slots."""
import json,time,hashlib,shutil,subprocess,sys,ast
from pathlib import Path
import psutil
H=Path(__file__).absolute().parent
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):
    t=p.with_suffix(p.suffix+'.tmp');t.write_text(json.dumps(v,indent=2),encoding='utf-8');t.replace(p)
def main():
    bench=read(H/'ACTUAL_SPEED_PREFLIGHT_20260922/BENCHMARK_PASS.json')
    memo=read(H/'ACTUAL_SPEED_PREFLIGHT_20260922/CACHE_EQUIVALENCE_PASS.json')
    assert bench['status']==memo['status']=='PASS'
    assert bench['source_sha256']==sha(H/'actual_electrical_speed.py')
    assert memo['runner_sha256']==sha(H/'actual_speed_runner.py')
    for n in ('actual_resume_fast.py','actual_fresh_fast.py','actual_speed_runner.py'):ast.parse((H/n).read_text(encoding='utf-8'))
    current=read(H/'CAMPAIGN_STATUS.json')
    if current['status']=='FAILED':
        assert 'PermissionError' in current['error']
        current=dict(current,worker_pid=read(H/'Actual/B2/STATUS.json')['pid'],log=str(max((H/'logs').glob('B2_ACTUAL_*.log'))))
    else:assert current['stage']=='B2_ACTUAL' and current['status']=='RUNNING'
    old_worker=psutil.Process(current['worker_pid'])
    old_supervisor=psutil.Process(current['supervisor_pid']) if psutil.pid_exists(current['supervisor_pid']) else None
    assert old_worker.cmdline()[-2:]==['actual_worker.py','B2']
    if old_supervisor is not None:assert old_supervisor.cmdline()[-1]=='campaign_resume_after_sparse_b2.py'
    stamp=time.strftime('%Y%m%d_%H%M%S');d=H/'diagnostic_attempts'/('B2_ACTUAL_SLOW_PREFIX_'+stamp);d.mkdir(exist_ok=False)
    if old_supervisor is not None:old_supervisor.suspend()
    old_worker.suspend()
    try:
        for n in ('CAMPAIGN_STATUS.json','STATUS.json','ACTIVE_CAMPAIGN_CONTINUATION_STATUS.json','campaign_resume_after_sparse_b2.py','B2_ACTUAL_STAGE_RUNTIME.json'):
            if (H/n).exists():shutil.copy2(H/n,d/n)
        checkpoint=read(H/'Actual/B2/B2/Q_ACCEPTED_CHECKPOINT.json')
        assert len(read(H/'Actual/B2/B2/Q_CONTROL_EVENTS.json'))==checkpoint['slots']
        source=(H/'Actual/B2').resolve();dest=(d/'Actual_B2').resolve()
        assert source.is_relative_to(H.resolve()) and dest.is_relative_to(d.resolve())
        shutil.copytree(source,dest)
        shutil.copy2(current['log'],d/'original_worker.log')
        save(d/'PROCESS_SNAPSHOT.json',dict(campaign=current,actual_status=read(source/'STATUS.json'),accepted_slots=checkpoint['slots'],unix=time.time()))
    except BaseException:
        old_worker.resume()
        if old_supervisor is not None:old_supervisor.resume()
        raise
    old_worker.terminate();old_worker.wait(15)
    if old_supervisor is not None:old_supervisor.terminate();old_supervisor.wait(15)
    authority=dict(status='PASS',accepted_slots=checkpoint['slots'],actual_inputs_sha256=sha(H/'Actual/B2/B2/ACTUAL_INPUTS.npz'),
        original_rule_sha256=sha(H/'Actual/B2/RULE_FREEZE.json'),preserved_slow_attempt=str(d),
        original_controller_candidate_domain_order_cap_unchanged=True,final_selected_Q_fresh_revalidation=True,
        final_independent_original_engine=True,source_files={n:sha(H/n) for n in ('actual_electrical_speed.py','actual_speed_runner.py','actual_resume_fast.py','actual_fresh_fast.py')},
        native_state_reuse=False,static_metadata_cache_only=True,exact_electrical_input_cache=True,unix=time.time())
    save(H/'ACTUAL_SPEED_RESUME_AUTHORITY.json',authority)
    supervisor=H/'campaign_resume_after_sparse_b2.py';text=supervisor.read_text(encoding='utf-8')
    marker='    campaign.run(label,script,*args,policy=policy)'
    replacement="    if actual and (H/'ACTUAL_SPEED_RESUME_AUTHORITY.json').exists():\n        if policy=='B2':script='actual_resume_fast.py'\n        elif policy=='B3':script='actual_fresh_fast.py'\n    campaign.run(label,script,*args,policy=policy)"
    assert text.count(marker)==1;text=text.replace(marker,replacement);ast.parse(text);supervisor.write_text(text,encoding='utf-8')
    log=H/'logs'/f'ACTUAL_SPEED_SUPERVISOR_{stamp}.log'
    with log.open('x',encoding='utf-8') as f:
        p=subprocess.Popen([sys.executable,'-B','-u',supervisor.name],cwd=H,stdout=f,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
    record=dict(PID=p.pid,started_unix=time.time(),log=str(log),resume_scope='B2_ACTUAL_ACCEPTED_PREFIX_THEN_B1_B3')
    save(H/'ACTUAL_SPEED_SUPERVISOR.json',record)
    save(H/'B2_PAPER_TERMINATION_RUN_20260921/WATCHER.json',record)
    print(json.dumps(record),flush=True)
if __name__=='__main__':main()
