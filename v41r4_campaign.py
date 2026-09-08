"""Durable four-day campaign with independent processes and automatic reports."""
from fast_prepare import *
from v41r4_runtime import MAY_RUN,MAY_OUT,HELPERS
from v41r4_io import install
install()
import subprocess,sys,os,time,traceback,threading
from concurrent.futures import ThreadPoolExecutor
from dayahead.paper_analysis.storage import write_json

LOGS=ROOT/'logs/v41r4_may'
PHASES=['electrical','domain']+[p+'_DA' for p in ('B0','B1','B2','B3')]+[p+'_AC' for p in ('B0','B1','B2','B3')]

def release():
    from dayahead.v41.execution import science
    from dayahead.v40h.identity import manifest,verify_manifest
    source=manifest([Path(r['path']) for r in science()['files']]+[ROOT/p for p in HELPERS],ROOT)
    target=MAY_OUT/'MAY_CAMPAIGN_RELEASE.json'
    if target.exists():
        value=read(target);assert value['source']==source;verify_manifest(source);return value
    assert read(MAY_OUT/'INPUT_PREPARATION_PROGRESS.json')['status']=='PASS'
    assert read(MAY_OUT/'V41R3_BACKGROUND_SCALE_AUTHORITY.json')['selected_alpha_BG']==1.15
    value=dict(status='FROZEN',version='V41R4_FINAL_115',alpha_BG=1.15,source=source,
        days=[f'2025-05-{n:02}' for n in range(1,32)],policies=['B0','B1','B2','B3'],phases=PHASES,
        AIDC_GPU=780,MESS_vehicles=4,MESS_kW=300,MESS_kVA=400,MESS_kWh=1200,
        solver_threads=4,day_workers=4,budget_seconds_per_policy_day=1800,
        separate_May21_preflight=False,alpha_tests=0,robust_S0_S1_S2=False,quantile_grid_security_margin=False,
        forecast_error_correction=False,Actual_optimization=False,native_RegControl_Actual=True,
        frozen_Q90_runtime_H4_ML_contract='RETAINED; no additional grid security margin',
        candidate_universe='Existing complete temporal/spatial/checkpoint universe; same compound 2/3 prefixes',
        compound_ordering_audit=record(MAY_OUT/'V41R4_COMPOUND_RANKING_COMPLETION_AUDIT.json'),
        uncertainty='DA nominal D-1; fixed-decision realized D-day replay',
        information_barrier='All four DA decisions on each date are frozen before any Actual input is opened',
        independent_dates=True,rolling_information=False,
        stop_contract='Code, authority, convergence or DA physics-contract failure only; unfavorable Actual values never cause rerun or retuning',
        outputs=str(MAY_RUN),logs=str(LOGS),automatic_final_report=True,
        source_change_policy='No producer edits during active campaign')
    save(target,value);return value

def main():
    from dayahead.v41.campaign import campaign_lock
    from v41r4_report import finalize
    with campaign_lock(MAY_RUN):
        config=release();started=time.time();lock=threading.Lock();stop=threading.Event()
        active={};completed=[];errors=[]
        units={d+'|'+p:dict(day=d,policy=p,status='WAITING',phase='queued',worker_pid=None) for d in config['days'] for p in config['policies']}
        def snapshot():
            with lock:
                rows={k:dict(v) for k,v in units.items()};running=[dict(v) for v in active.values()];done=list(completed);failed=list(errors)
            status='FAIL_CLOSED_DRAINING' if failed and running else 'FAIL_CLOSED' if failed else 'COMPLETE' if len(done)==310 else 'RUNNING'
            value=dict(status=status,supervisor_pid=os.getpid(),active=running,completed_phases=done,errors=failed,
                updated_at=time.time(),started_at=started,day_workers=4,solver_threads_per_day=4,alpha_BG=1.15)
            write_json(MAY_OUT/'MAY_CAMPAIGN_STATUS.json',value)
            write_json(MAY_RUN/'campaign_state.json',dict(units=rows,status=status,source='V41R4_DETACHED_SUPERVISOR'))
            write_json(MAY_RUN/'campaign_progress.json',value)
        def day_run(day):
            phase='queued'
            try:
                for phase in PHASES:
                    if stop.is_set():return
                    receipt=MAY_OUT/day/f'PHASE_{phase}.json';method=phase.split('_')[0] if phase[0]=='B' else 'B0'
                    if receipt.exists():
                        assert read(receipt)['status']=='PASS',('EXISTING_FAILED_PHASE_REQUIRES_REVIEW',day,phase)
                    else:
                        logpath=LOGS/day/f'{phase}.log';logpath.parent.mkdir(parents=True,exist_ok=True)
                        env=os.environ.copy();env.pop('V41R3_MAY_DATE',None);env.pop('V41_FO_RECOVERY_PLAN',None)
                        env['V41R4_MAY_DATE']=day;env['PYTHONPATH']=str(ROOT/'v41r4_bootstrap')+os.pathsep+str(ROOT)
                        with logpath.open('x',encoding='utf-8') as log:
                            proc=subprocess.Popen([sys.executable,'-u',str(ROOT/'v41r4_worker.py'),day,phase],cwd=ROOT,env=env,
                                stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
                            with lock:
                                active[day]=dict(day=day,phase=phase,worker_pid=proc.pid,log=str(logpath),started_at=time.time())
                                units[day+'|'+method].update(status='RUNNING',phase={'electrical':'ELECTRICAL_GENERATION','domain':'DOMAIN_PREPARATION'}.get(phase,'actual' if phase.endswith('_AC') else 'dayahead'),worker_pid=proc.pid,log=str(logpath))
                            proc.wait()
                            assert proc.returncode==0,('WORKER_FAILED',proc.returncode,str(logpath))
                        assert read(receipt)['status']=='PASS'
                    with lock:
                        completed.append(dict(day=day,phase=phase));active.pop(day,None)
                        units[day+'|'+method].update(status='COMPLETE' if phase.endswith('_AC') else 'DA_COMPLETE' if phase.endswith('_DA') else 'WAITING',
                            phase='complete' if phase.endswith('_AC') else 'Actual 대기' if phase.endswith('_DA') else 'queued',worker_pid=None)
                    print('PHASE_COMPLETE',day,phase,flush=True)
            except BaseException as e:
                with lock:
                    active.pop(day,None);errors.append(dict(day=day,phase=phase,error=repr(e),traceback=traceback.format_exc()))
                    method=phase.split('_')[0] if phase.startswith('B') else 'B0'
                    units[day+'|'+method].update(status='FAILED',phase=phase,worker_pid=None,error=repr(e))
                stop.set();print('TECHNICAL_FAILURE',day,phase,repr(e),flush=True)
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures=[pool.submit(day_run,d) for d in config['days']]
            while not all(f.done() for f in futures):
                try:snapshot()
                except PermissionError as e:print('STATUS_SHARING_RETRY_NEXT_HEARTBEAT',repr(e),flush=True)
                time.sleep(3)
            for f in futures:f.result()
        snapshot()
        result=finalize(complete=not errors)
        write_json(MAY_RUN/'CAMPAIGN_FINISHED.json',dict(status='TECHNICAL_FAILURE' if errors else 'COMPLETE',
            completed_units=result['units'],errors=errors,finished_at=time.time(),summary=record(MAY_RUN/'V41R4_FULL_MAY_SUMMARY.json')))
        if errors:raise RuntimeError('V41R4_TECHNICAL_FAILURE:'+str(errors))
        print('FULL_MAY_COMPLETE_124_UNITS',flush=True)

if __name__=='__main__':main()

