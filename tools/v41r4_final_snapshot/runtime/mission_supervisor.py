"""Independent-day controller adopting live work without restarting workers."""
import sys,os,time,subprocess,threading,traceback
from concurrent.futures import ThreadPoolExecutor
from fast_prepare import ROOT,read,record
from mission_health import write,OUT,RUN,LOG
import psutil
PHASES=['electrical','domain']+[p+'_DA' for p in ('B0','B1','B2','B3')]+[p+'_AC' for p in ('B0','B1','B2','B3')]
def main():
    from dayahead.v41.campaign import campaign_lock
    from v41r4_search_runtime import install_reports
    install_reports()
    with campaign_lock(RUN):
        old=read(OUT/'SUPERVISOR_TAKEOVER.json');release=read(RUN/'audit/MAY_CAMPAIGN_RELEASE_V3.json')
        active={r['day']:r for r in old['active']};completed=[];errors=[];guard=threading.Lock();started=time.time()
        def snapshot():
            with guard:value=dict(status='RUNNING',supervisor_pid=os.getpid(),active=list(active.values()),completed_phases=list(completed),errors=list(errors),updated_at=time.time(),started_at=started,day_workers=4,solver_threads_per_day=4,alpha_BG=1.15)
            write(RUN/'campaign_progress.json',value);write(RUN/'audit/MAY_CAMPAIGN_STATUS.json',value)
        def day_run(day):
            phase='queued'
            try:
                for phase in PHASES:
                    receipt=RUN/'audit'/day/f'PHASE_{phase}.json'
                    adopted=active.get(day)
                    if adopted and adopted['phase']==phase:
                        try:
                            p=psutil.Process(adopted['worker_pid'])
                            assert day in p.cmdline() and phase in p.cmdline(),'ADOPT_PID_REUSED'
                            while p.is_running():time.sleep(3)
                        except psutil.NoSuchProcess:pass
                        assert receipt.exists(),'ADOPTED_WORKER_EXIT_WITHOUT_RECEIPT'
                    if not receipt.exists():
                        script='mission_actual_worker.py' if phase.endswith('_AC') else ('mission_worker.py' if phase.startswith('B3_') else 'v41r4_search_worker.py')
                        folder=ROOT/'logs/v41r4_may/search_time_v3'/day;folder.mkdir(parents=True,exist_ok=True)
                        log=folder/f'{phase}.log'
                        if log.exists():log=folder/f'{phase}.mission_{int(time.time())}.log'
                        env=os.environ.copy();env.pop('V41R3_MAY_DATE',None);env.pop('V41_FO_RECOVERY_PLAN',None)
                        env['V41R4_MAY_DATE']=day;env['PYTHONPATH']=str(ROOT/'v41r4_search_bootstrap')+os.pathsep+str(ROOT)
                        with log.open('x',encoding='utf-8') as f:
                            proc=subprocess.Popen([sys.executable,'-u',str(ROOT/script),day,phase],cwd=ROOT,env=env,stdin=subprocess.DEVNULL,stdout=f,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
                            with guard:active[day]=dict(day=day,phase=phase,worker_pid=proc.pid,log=str(log),started_at=time.time())
                            proc.wait();assert proc.returncode==0,('WORKER_FAILED',proc.returncode,str(log))
                    assert read(receipt)['status']=='PASS',('FAILED_RECEIPT_REQUIRES_DIAGNOSIS',str(receipt))
                    with guard:
                        if active.get(day,{}).get('phase')==phase:active.pop(day,None)
                        completed.append(dict(day=day,phase=phase))
                    print('PHASE_COMPLETE',day,phase,flush=True)
            except BaseException as e:
                with guard:active.pop(day,None);errors.append(dict(day=day,phase=phase,error=repr(e),traceback=traceback.format_exc()))
                print('ISOLATED_DAY_FAILURE',day,phase,repr(e),flush=True)
        with ThreadPoolExecutor(max_workers=4) as pool:
            ordered=list(active)+[d for d in release['days'] if d not in active]
            futures=[pool.submit(day_run,d) for d in ordered]
            while not all(f.done() for f in futures):
                try:snapshot()
                except OSError:print('STATUS_WRITE_RETRY_NEXT_TICK',traceback.format_exc(),flush=True)
                time.sleep(3)
            for f in futures:f.result()
        snapshot()
        from v41r4_report import finalize
        summary=finalize(complete=not errors)
        write(RUN/'CAMPAIGN_FINISHED.json',dict(status='TECHNICAL_FAILURE' if errors else 'COMPLETE',errors=errors,completed_units=summary['units'],finished_at=time.time()))
        print('MISSION_CONTROLLER_FINISHED',summary['units'],len(errors),flush=True)
if __name__=='__main__':
    import v41r4_detached as base
    from v41r4_search_budget import adapted
    base.MAY_RUN=RUN;base.MAY_OUT=RUN/'audit';base.LOGS=ROOT/'logs/v41r4_may/search_time_v3'
    if sys.argv[1]=='spawn':
        spawn=adapted(base.spawn,[("str(ROOT/'v41r4_detached.py')","str(ROOT/'mission_supervisor.py')")]);spawn('campaign')
    elif sys.argv[1]=='worker':
        worker=adapted(base.worker,[("    if kind=='campaign_v2':\n        from v41r4_campaign_v2 import main\n    else:\n        from v41r4_campaign import main",'    from mission_supervisor import main')]);worker(sys.argv[2],sys.argv[3])
