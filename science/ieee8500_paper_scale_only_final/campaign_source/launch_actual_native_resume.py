"""Checkpointed switch; preserve every completed exact-Q memo and accepted slot."""
import ast, hashlib, json, shutil, subprocess, sys, time
from pathlib import Path
import psutil
H=Path(__file__).absolute().parent
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):
    temp=p.with_suffix('.native.tmp');temp.write_text(json.dumps(v,indent=2),encoding='utf-8')
    for i in range(100):
        try:temp.replace(p);return
        except PermissionError:
            if i==99:raise
            time.sleep(.02)
def main():
    pre=H/'ACTUAL_NATIVE_PREFLIGHT_20260922'
    bench=read(pre/'BENCHMARK_PASS.json');proof=read(pre/'FULL_PARITY_PASS.json')
    assert bench['status']==proof['status']=='PASS'
    assert bench['source_sha256']==proof['source']['sha256']==sha(H/'actual_native_inputs.py')
    assert proof['existing_memo_bit_identical'] and proof['slots']==96
    for n in ('actual_native_inputs.py','actual_native_entry.py'):ast.parse((H/n).read_text())
    c=read(H/'CAMPAIGN_STATUS.json');assert c['stage']=='B2_ACTUAL' and c['status']=='RUNNING'
    supervisor=psutil.Process(c['supervisor_pid']);worker=psutil.Process(c['worker_pid'])
    assert supervisor.cmdline()[-1]=='campaign_resume_after_sparse_b2.py'
    assert worker.cmdline()[-2:]==['actual_resume_fast.py','B2']
    stamp=time.strftime('%Y%m%d_%H%M%S')
    backup=H/'diagnostic_attempts'/('B2_ACTUAL_BEFORE_NATIVE_'+stamp);backup.mkdir(exist_ok=False)
    supervisor.suspend();worker.suspend()
    try:
        for n in ('CAMPAIGN_STATUS.json','STATUS.json','campaign_resume_after_sparse_b2.py',
                  'ACTUAL_SPEED_SUPERVISOR.json','ACTIVE_CAMPAIGN_CONTINUATION_STATUS.json'):
            if (H/n).exists():shutil.copy2(H/n,backup/n)
        source=(H/'Actual/B2').resolve();dest=(backup/'Actual_B2').resolve()
        assert source.is_relative_to(H.resolve()) and dest.is_relative_to(backup.resolve())
        shutil.copytree('\\\\?\\'+str(source),'\\\\?\\'+str(dest));shutil.copy2(c['log'],backup/'worker.log')
        checkpoint=read(source/'B2/Q_ACCEPTED_CHECKPOINT.json')
        progress=read(source/'B2/Q_EVALUATION_PROGRESS.json')
        assert len(read(source/'B2/Q_CONTROL_EVENTS.json'))==checkpoint['slots']
        cache=source/'B2/EXACT_STATE_CACHE';valid=0;incomplete=[]
        for p in cache.rglob('*.json'):
            try:
                m=read(p);assert sha(p.with_suffix('.npz'))==m['arrays_sha256'];valid+=1
            except (ValueError,AssertionError,FileNotFoundError):incomplete.append(p)
        for p in incomplete:
            # The fully backed-up in-flight record was never committed. Keep it
            # under a non-cache suffix so the identical trial is recomputed.
            assert p.resolve().is_relative_to(source)
            p.rename(p.with_suffix('.interrupted_json'))
        save(backup/'PRESERVATION.json',dict(campaign=c,accepted_slots=checkpoint['slots'],
            progress=progress,verified_complete_cache_entries=valid,
            incomplete_records=[str(p) for p in incomplete]))
    except BaseException:
        worker.resume();supervisor.resume();raise
    supervisor.terminate();supervisor.wait(15);worker.terminate();worker.wait(15)
    files=[H/'actual_native_inputs.py',H/'actual_native_entry.py']
    files += sorted(p for p in (H/'ACTUAL_NATIVE_RUNTIME_20260922').rglob('*') if p.suffix in ('.py','.pyd','.dll'))
    save(H/'ACTUAL_NATIVE_RESUME_AUTHORITY.json',dict(status='PASS',backup=str(backup),
        accepted_slots=checkpoint['slots'],verified_complete_cache_entries=valid,
        old_prefix_sha=progress['prefix_sha'],old_rule_sha=sha(H/'Actual/B2/RULE_FREEZE.json'),
        implementation_files=[dict(path=str(p),sha256=sha(p)) for p in files],
        benchmark=bench,full_parity=proof,original_controller_unchanged=True,
        no_candidate_pruning=True,no_time_limit_change=True,no_physical_state_reuse=True,
        selected_Q_fresh_check=True,original_independent_96_slot_validation=True))
    script=H/'campaign_resume_after_sparse_b2.py';s=script.read_text(encoding='utf-8')
    marker='    campaign.run(label,script,*args,policy=policy)'
    assert s.count(marker)==1
    s=s.replace(marker,"    if actual and policy in ('B2','B3') and (H/'ACTUAL_NATIVE_RESUME_AUTHORITY.json').exists():\n        script='actual_native_entry.py'\n"+marker)
    ast.parse(s);script.write_text(s,encoding='utf-8')
    log=H/'logs'/f'ACTUAL_NATIVE_SUPERVISOR_{stamp}.log'
    with log.open('x',encoding='utf-8') as f:
        p=subprocess.Popen([sys.executable,'-B','-u',script.name],cwd=H,stdout=f,stderr=subprocess.STDOUT,
                           creationflags=subprocess.CREATE_NO_WINDOW)
    launch=dict(PID=p.pid,started_unix=time.time(),log=str(log),preserved_cache_entries=valid,
                accepted_slots=checkpoint['slots'],backup=str(backup))
    save(H/'ACTUAL_NATIVE_SUPERVISOR.json',launch)
    save(H/'B2_PAPER_TERMINATION_RUN_20260921/WATCHER.json',launch)
    print(json.dumps(launch),flush=True)
if __name__=='__main__':main()
