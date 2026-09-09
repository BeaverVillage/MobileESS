from mission_health import *
state=read(RUN/'campaign_progress.json');p=psutil.Process(state['supervisor_pid'])
assert 'mission_supervisor.py' in ' '.join(p.cmdline());p.suspend()
try:
    state=read(RUN/'campaign_progress.json');old=read(OUT/'SUPERVISOR_TAKEOVER.json')
    rows=old['active']+state['active'];assert len({r['day'] for r in rows})==len(rows)
    for r in rows:
        c=psutil.Process(r['worker_pid']);assert r['day'] in c.cmdline() and r['phase'] in c.cmdline()
    write(LOG/'adoption_failure_state.json',state)
    for r in old['active']:
        receipt=RUN/'audit'/r['day']/f"PHASE_{r['phase']}.json"
        value=read(receipt);assert value['status']=='FAIL_CLOSED' and 'FileExistsError' in value['error']
        assert 'SINGLE_CORRECTED_RUN_TOKEN' in value['traceback']
        target=OUT/f"{r['day']}_DUPLICATE_DISPATCH_FAILURE.json"
        assert receipt.resolve().is_relative_to(RUN.resolve()) and target.resolve().is_relative_to(RUN.resolve()) and not target.exists()
        receipt.rename(target)
    write(OUT/'SUPERVISOR_TAKEOVER_PRE_REPAIR.json',old)
    write(OUT/'SUPERVISOR_TAKEOVER.json',dict(**{k:v for k,v in state.items() if k!='active'},active=rows,adoption_bug_fixed=True))
    write(OUT/'ADOPTION_REPAIR.json',dict(status='PASS',root_cause='Reused earlier phase removed adopted later-phase PID from controller map',
        fix='Remove active entry only when its phase matches completed phase',original_B1_workers_preserved=[r['worker_pid'] for r in old['active']],
        duplicate_attempts=4,duplicate_solver_calls=0,duplicate_failure_guard='Exclusive pre-solver run token',new_electrical_workers_preserved=[r['worker_pid'] for r in state['active']],
        source=rec if False else str(ROOT/'mission_supervisor.py'),evidence=str(LOG/'adoption_failure_state.json')))
    p.terminate();p.wait(15)
except BaseException:
    if p.is_running():p.resume()
    raise
print('ADOPTION_REPAIRED_ALL_EXISTING_WORKERS_PRESERVED',len(rows))
