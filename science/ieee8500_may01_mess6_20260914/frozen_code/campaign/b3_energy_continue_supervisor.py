import os,sys,time,subprocess,traceback
from pathlib import Path
import b3_resume_supervisor as c
from b3_detached_supervisor import in_job
H=c.H
R=H/'actual_B3_energy_exception_20260914'
P=H/'b3_energy_continue_preflight_20260914'
def main():
    assert not in_job(),'NOT_CODEX_INDEPENDENT'
    assert c.read(P/'PREFLIGHT.json')['status']=='PASS'
    assert not R.exists(),'NEW_NAMESPACE_REQUIRED'
    with (P/'actual.log').open('x',encoding='utf-8') as log:
        child=subprocess.Popen([sys.executable,'-X','utf8','-B','b3_actual_energy_continue.py'],cwd=H,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
        state=dict(status='RUNNING',pid=os.getpid(),worker_pid=child.pid,namespace=str(R),started_unix=time.time(),stage='B3_ACTUAL_USER_ACCEPTED_ENERGY_EXCEPTION',no_new_optimization=True)
        c.save('ENERGY_EXCEPTION_RUN.json',state)
        code=child.wait()
    assert code==0,('ACTUAL_WORKER_EXIT',code)
    accepted=c.read(R/'USER_ACCEPTED_COMPLETE.json')
    assert accepted['AC_feasible'] and accepted['independent_replay_PASS']
    base=H.parent/'IEEE8500_MAY01_AIDC2X_HOST_REMAP_FULL4H_20260913'
    comparison={}
    for policy in ('B0','B1','B2','B3'):
        da=c.read(base/'DA_RESULT.json')[policy] if policy in ('B0','B1') else c.read(H/policy/'FINAL_AUTHORITY.json')['AC']
        actual_path=(base/'actual'/policy/'COMPLETE.json') if policy in ('B0','B1') else (c.F/'B2/COMPLETE.json' if policy=='B2' else R/'B3/COMPLETE.json')
        ac=c.read(actual_path)
        comparison[policy]=dict(DA=da,Actual=ac['summary'],AC_feasible=ac['AC_feasible'],Actual_source=dict(path=str(actual_path),sha256=c.sha(actual_path)))
    result=dict(status=accepted['status'],date='2025-05-01',policies=comparison,B3_energy_exception=accepted,completed_unix=time.time(),new_optimization_calls=0)
    c.save('RESULT_WITH_ENERGY_EXCEPTION.json',result)
    c.save('ENERGY_EXCEPTION_RUN.json',dict(state,status=accepted['status'],completed_unix=time.time(),worker_pid=None))
if __name__=='__main__':
    sys.stdout=open(P/'supervisor.log','a',encoding='utf-8',buffering=1)
    sys.stderr=open(P/'supervisor.stderr.log','a',encoding='utf-8',buffering=1)
    try:main()
    except BaseException as error:
        c.save('ENERGY_EXCEPTION_RUN.json',dict(status='FAILED',pid=os.getpid(),namespace=str(R),stage='B3_ACTUAL_USER_ACCEPTED_ENERGY_EXCEPTION',error=repr(error),traceback=traceback.format_exc()))
        raise
