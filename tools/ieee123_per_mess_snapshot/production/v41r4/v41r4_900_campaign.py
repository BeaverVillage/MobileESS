"""Detached 4-day x 4-thread May campaign with running-worker adoption."""
import os, sys, time, json, traceback, subprocess, threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from v41r4_900_namespace import ROOT,RUN,OUT,LOGS,verify_release,bind
from dayahead.paper_analysis.storage import read,write_json
from v41r4_per_mess_budget import CONTRACT_SHA
import psutil

DAY_WORKERS = 4


def discover_workers():
    workers = {}
    target = (ROOT/'v41r4_900_final_worker.py').resolve()
    for process in psutil.process_iter(['pid', 'cmdline', 'create_time']):
        args = process.info['cmdline'] or []
        for index, arg in enumerate(args):
            if not arg.endswith('v41r4_900_final_worker.py'):
                continue
            if Path(arg).resolve() != target:
                continue
            assert len(args) == index + 3, ('UNEXPECTED_WORKER_ARGUMENTS', args)
            day, phase = args[-2:]
            assert day not in workers, ('DUPLICATE_DAY_WORKERS', day)
            workers[day] = dict(day=day, phase=phase, worker_pid=process.pid,
                started_at=process.info['create_time'], log=str(LOGS/day/(phase+'.log')),
                adopted=True, process=process)
    assert len(workers) <= DAY_WORKERS
    return workers


def main():
    verify_release();bind()
    from dayahead.v41.campaign import campaign_lock
    stop=threading.Event();lock=threading.Lock()
    adopted=discover_workers()
    active={day:{k:v for k,v in row.items() if k!='process'} for day,row in adopted.items()}
    completed=[];errors=[];started=time.time()
    previous=OUT/'MAY_CAMPAIGN_STATUS.json'
    if previous.exists():started=read(previous).get('started_at',started)
    write_json(OUT/'WORKER_ADOPTION.json',dict(at=time.time(),supervisor_pid=os.getpid(),
        day_workers=DAY_WORKERS,workers=list(active.values())))
    stop_file=RUN/'GRACEFUL_STOP.json'
    phases=['B1_DA','B2_DA','B3_DA','B0_AC','B1_AC','B2_AC','B3_AC']
    def snapshot():
        with lock:
            rows=[dict(r) for r in active.values()];done=list(completed);failed=list(errors)
        for row in rows:
            policy=row['phase'].split('_')[0]
            p=RUN/row['day']/policy/'search/PER_MESS_LIVE.json'
            if row['phase'].endswith('_DA') and policy in ('B2','B3') and p.exists():
                try:
                    row['mess']=read(p)
                    if row['mess']['stop_reason'] is None:
                        row['mess']['elapsed_seconds_live']=time.time()-row['mess']['started_at']
                except (OSError,ValueError):pass
        state='FAIL_CLOSED_DRAINING' if failed and rows else 'FAIL_CLOSED' if failed else 'COMPLETE' if len(done)==31*len(phases) else 'RUNNING'
        value=dict(status=state,supervisor_pid=os.getpid(),started_at=started,updated_at=time.time(),
            day_workers=DAY_WORKERS,solver_threads_per_day=4,active=rows,completed_phases=done,errors=failed,
            runtime_budget_contract_SHA=CONTRACT_SHA,output_namespace=str(RUN))
        write_json(OUT/'MAY_CAMPAIGN_STATUS.json',value)
        lines=[f'IEEE123 MAY | {state} | {DAY_WORKERS} workers x 4 Gurobi threads | 900s / MESS',
            'DAY         POLICY    PID    MESS   ELAPSED/15m   K       CERT   FULL   BEST P1']
        for r in rows:
            m=r.get('mess',{});elapsed=m.get('elapsed_seconds_live',m.get('elapsed_at_stop',0))
            best=m.get('best_certified_objective_at_stop')
            lines.append(f"{r['day']}  {r['phase']:7} {r['worker_pid']:6}  {str(m.get('mess_index','-')):4}   {elapsed/60:6.2f}/15m  {str(m.get('K_stage','-')):6}  {m.get('certified_candidate_count',0):5}  {str(m.get('FULL_entered',False)):5}  {best}")
        lines.append(f'Completed phases: {len(done)}/{31*len(phases)} | errors: {len(failed)}')
        (OUT/'LIVE_DASHBOARD.txt').write_text('\n'.join(lines),encoding='utf-8')
    def day_run(day):
        phase='QUEUED'
        try:
            for phase in phases:
                if stop.is_set() or stop_file.exists():return
                receipt=OUT/day/f'PHASE_{phase}.json'
                existing=adopted.get(day)
                if existing and existing['phase']==phase:
                    code=existing['process'].wait()
                    assert code==0,('ADOPTED_WORKER_FAILED',day,phase,code)
                    assert receipt.exists(),('ADOPTED_RECEIPT_MISSING',day,phase)
                    adopted.pop(day)
                if receipt.exists():
                    assert read(receipt)['status']=='PASS',('PREEXISTING_FAILED_PHASE',day,phase)
                    if phase.startswith(('B2','B3')):
                        assert read(receipt).get('runtime_budget_contract_SHA')==CONTRACT_SHA
                else:
                    verify_release()
                    env=os.environ.copy();env.pop('V41R3_MAY_DATE',None);env.pop('V41_FO_RECOVERY_PLAN',None)
                    tmp=RUN/'workers'/day/'temp';tmp.mkdir(parents=True,exist_ok=True)
                    env.update(V41R4_MAY_DATE=day,PYTHONPATH=str(ROOT/'v41r4_resume_bootstrap')+os.pathsep+str(ROOT),
                        TEMP=str(tmp),TMP=str(tmp),TMPDIR=str(tmp),PYTHONDONTWRITEBYTECODE='1',PYTHONUTF8='1',
                        OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',NUMEXPR_NUM_THREADS='1',
                        IEEE123_900_STOP_FILE=str(stop_file),GUROBI_LOG_PATH='D:/ieee123_grb/'+day.replace('-','')+'/per_mess900_'+phase+'/worker.log')
                    logpath=LOGS/day/(phase+'.log');logpath.parent.mkdir(parents=True,exist_ok=True)
                    with logpath.open('x',encoding='utf-8') as log:
                        process=subprocess.Popen([sys.executable,'-B','-u',str(ROOT/'v41r4_900_final_worker.py'),day,phase],
                            cwd=ROOT,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,
                            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                        with lock:active[day]=dict(day=day,phase=phase,worker_pid=process.pid,started_at=time.time(),log=str(logpath))
                        assert process.wait()==0,('WORKER_FAILED',day,phase,str(logpath))
                    assert read(receipt)['status']=='PASS'
                with lock:
                    if day in active and active[day]['phase']==phase:active.pop(day,None)
                    completed.append(dict(day=day,phase=phase))
                print('PHASE_COMPLETE',day,phase,flush=True)
        except BaseException as e:
            with lock:
                active.pop(day,None);errors.append(dict(day=day,phase=phase,error=repr(e),traceback=traceback.format_exc()))
            stop.set();print('TECHNICAL_FAILURE',day,phase,repr(e),flush=True)
    with campaign_lock(RUN):
        with ThreadPoolExecutor(max_workers=DAY_WORKERS) as pool:
            days=[*sorted(adopted),*[f'2025-05-{n:02}' for n in range(1,32) if f'2025-05-{n:02}' not in adopted]]
            futures=[pool.submit(day_run,day) for day in days]
            while not all(f.done() for f in futures):
                try:snapshot()
                except OSError as error:print('SNAPSHOT_IO_RETRY',repr(error),flush=True)
                time.sleep(3)
            for f in futures:f.result()
        snapshot()
        if not errors:
            import v41r4_loop_runtime as loop
            loop.install_reports()
            from v41r4_report import finalize
            result=finalize(complete=True)
            write_json(RUN/'CAMPAIGN_FINISHED.json',dict(status='COMPLETE',result=result,runtime_budget_contract_SHA=CONTRACT_SHA))
        else:raise RuntimeError(errors)


if __name__=='__main__':main()
