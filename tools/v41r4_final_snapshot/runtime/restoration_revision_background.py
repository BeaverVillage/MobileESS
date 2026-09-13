"""Detached handoff: adopt live NEW May31 B3, close Fresh, run selective Actual, audit."""
from pathlib import Path
import os,sys,json,time,subprocess,ctypes,traceback,shutil
import restoration_revision_v1 as r
OUT=r.OUT/'background';VIEW=r.ROOT/'frozen_artifacts/v41r4_revision_monitor_view'
DAY='2025-05-31';POLICY='B3';INITIAL_PID=93460

def atomic(p,value):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    temp=p.with_name(p.name+f'.{os.getpid()}.tmp')
    temp.write_text(json.dumps(value,indent=2,ensure_ascii=False),encoding='utf-8')
    for k in range(50):
        try:os.replace(temp,p);return
        except PermissionError:time.sleep(.1)
    raise RuntimeError('STATE_WRITE_RETRY_EXHAUSTED')
def alive(pid):
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.restype=ctypes.c_void_p;kernel.GetExitCodeProcess.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_ulong)];kernel.CloseHandle.argtypes=[ctypes.c_void_p]
    h=kernel.OpenProcess(0x1000,False,int(pid))
    if not h:return False
    exitcode=ctypes.c_ulong();ok=kernel.GetExitCodeProcess(h,ctypes.byref(exitcode));kernel.CloseHandle(h)
    return bool(ok and exitcode.value==259)
def launch(args,label):
    env=os.environ.copy();env.pop('V41R4_MAY_DATE',None);env.pop('V41R3_MAY_DATE',None);env['PYTHONPATH']=str(r.ROOT);env['PYTHONDONTWRITEBYTECODE']='1'
    log=OUT/(label+'.log');f=log.open('w',encoding='utf-8')
    child=subprocess.Popen([sys.executable,'-u',*args],cwd=r.ROOT,env=env,stdin=subprocess.DEVNULL,stdout=f,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
    f.close();return child,str(log)
def publish(stage,pid,log,errors,started):
    complete=0;units={}
    for n in range(1,32):
        day=f'2025-05-{n:02d}'
        for policy in ('B0','B1','B2','B3'):
            done=(VIEW/'replays'/day/policy/'CANDIDATE_RECEIPT.json').exists()
            complete+=int(done)
            units[day+'|'+policy]=dict(day=day,policy=policy,status='COMPLETE' if done else 'WAITING',phase='complete' if done else 'queued',worker_pid=None)
    active=[]
    if pid and alive(pid):
        phase={'DA':'B3_DA','FRESH':'RESTORATION_FRESH','ACTUAL':'B3_ETA95_QSAFE_AC','AUDIT':'FINAL_AUDIT'}[stage]
        active=[dict(day=DAY,policy=POLICY,phase=phase,worker_pid=pid,started_at=started,log=log,kind='DA_FRESH' if stage in ('DA','FRESH') else 'ACTUAL_ONLY' if stage=='ACTUAL' else 'AUDIT')]
        units[DAY+'|'+POLICY].update(status='RUNNING',phase=phase,worker_pid=pid)
    status='COMPLETE' if stage=='COMPLETE' else 'NEEDS_ATTENTION' if errors else 'RUNNING'
    state=dict(status=status,supervisor_pid=os.getpid(),active=active,errors=errors,updated_at=time.time(),started_at=started,day_workers=4,resource_mode='NORMAL_4',
        Actual_completed_units=complete,Actual_total_units=124,restoration_version='restoration_revision_v1',existing_DA_reused=123,new_required_DA='2025-05-31 B3',
        Actual_method='V41R4_ACTUAL_ETA95_QSAFE_ROBUST_V2',stage=stage,common_active_workers=len(active))
    atomic(OUT/'DISPATCHER_STATE.json',state)
    atomic(r.RUN/'campaign_state.json',dict(status=status,units=units,updated_at=time.time(),source='RESTORATION_REVISION_V1'))
    atomic(r.RUN/'campaign_progress.json',state)
    atomic(OUT/'HEARTBEAT.json',dict(pid=os.getpid(),stage=stage,worker_pid=pid,updated_at=time.time(),status=status))

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    from dayahead.v41.campaign import campaign_lock
    with campaign_lock(OUT/'lock'):
        stage='DA';pid=INITIAL_PID;child=None;errors=[];started=time.time();log=str(r.ROOT/'diagnostics/may31_b3_new_required_da_bootstrapped.log')
        atomic(OUT/'HANDOFF_RECEIPT.json',dict(status='ADOPTED',pid=os.getpid(),adopted_B3_worker=pid,adopted_worker_alive=alive(pid),source=r.record(__file__),created_at=started,existing_workers_restarted=0))
        while True:
            try:
                publish(stage,pid,log,errors,started)
                if errors:return
                running=child.poll() is None if child is not None else alive(pid)
                if running:time.sleep(5);continue
                if child is not None and child.returncode!=0:raise RuntimeError((stage,'WORKER_FAILED',child.returncode,log))
                if stage=='DA':
                    da=r.RUN/DAY/POLICY/'dayahead'
                    assert (da/'FROZEN_JOINT_DECISION.json').exists() and (da/'FRESH_RESULT.json').exists(),'NEW_B3_DA_NO_FROZEN_RESULT'
                    child,log=launch(['restoration_revision_reader_r1.py',DAY],'B3_revised_fresh');stage='FRESH'
                elif stage=='FRESH':
                    u=r.read(r.OUT/DAY/POLICY/'ACCEPTANCE.json');assert u['status']=='PASS'
                    assert u['actual_disposition']=='NEW_ACTUAL_REQUIRED'
                    child,log=launch(['selective_actual_revision_v1.py',DAY,POLICY],'B3_new_actual_v2');stage='ACTUAL'
                elif stage=='ACTUAL':
                    done=r.read(r.NEWAC/'replays'/DAY/POLICY/'COMPLETE.json')
                    assert done['status']=='PASS' and not done['ETA95_QSAFE_ACTUAL']['physical_violation']
                    child,log=launch(['restoration_revision_final_audit.py','--final'],'final_124_audit');stage='AUDIT'
                elif stage=='AUDIT':
                    result=r.read(r.OUT/'FINAL_AUDIT.json');assert result['status']=='COMPLETE' and result['counts']['total_accepted']==124
                    stage='COMPLETE';pid=None;child=None
                    atomic(OUT/'CAMPAIGN_FINISHED.json',dict(status='COMPLETE',finished_at=time.time(),final_audit=r.record(r.OUT/'FINAL_AUDIT.json'),counts=result['counts']))
                    publish(stage,pid,log,errors,started);return
                pid=child.pid
            except Exception as e:
                errors=[dict(day=DAY,phase='B3_'+stage,error=repr(e),traceback=traceback.format_exc(),log=log)]
                atomic(OUT/'FAILURE.json',errors[0]);publish(stage,None,log,errors,started);raise

if __name__=='__main__':main()
