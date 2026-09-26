"""Continue the approved campaign after a pre-search path-alias failure."""
import os,sys,time,traceback
from pathlib import Path
import b3_resume_supervisor as c
from b3_detached_supervisor import in_job
H=c.H
R=H/'a1_alias_recovery_20260914'
def main():
    assert not in_job(),'NOT_CODEX_INDEPENDENT'
    assert not(H/'SEARCH_CLOCK.json').exists(),'SEARCH_ALREADY_STARTED'
    assert not(R/'STARTED.json').exists(),'DUPLICATE_START'
    assert c.read(R/'PREFLIGHT.json')['status']=='PASS'
    for r in c.read(R/'SOURCE_FREEZE.json')['files']:assert c.sha(r['path'])==r['sha256'],r['path']
    m1=c.read(H/'B3_M1/COMPLETE.json');assert m1['status']=='PASS'
    assert c.sha(m1['result']['path'])==m1['result']['sha256']
    c.save(str((R/'STARTED.json').relative_to(H)),dict(pid=os.getpid(),unix=time.time(),in_windows_job=False,M1_reused=m1,A1_continuous_wall_seconds=14400))
    c.run('a1_alias_supervisor.py')
    c.run('mf_worker.py')
    c.run('b3_actual_shell.py')
    c.run('finalize_campaign_shell.py')
    for r in c.read(R/'SOURCE_FREEZE.json')['files']:assert c.sha(r['path'])==r['sha256'],r['path']
    c.save('SUPERVISOR_STATUS.json',dict(status='COMPLETE',updated_unix=time.time(),pid=os.getpid(),codex_independent=True))
if __name__=='__main__':
    sys.stdout=open(R/'supervisor.log','a',encoding='utf-8',buffering=1)
    sys.stderr=open(R/'supervisor.stderr.log','a',encoding='utf-8',buffering=1)
    try:main()
    except BaseException as error:
        c.save('B3_CONTINUATION_FAILURE.json',dict(error=repr(error),traceback=traceback.format_exc()))
        c.save('SUPERVISOR_STATUS.json',dict(status='FAILED',error=repr(error),updated_unix=time.time(),pid=os.getpid()))
        raise
