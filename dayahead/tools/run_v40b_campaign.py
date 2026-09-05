"""Independent May supervisor and one-date workers. Launched via Task Scheduler."""
from pathlib import Path
import argparse,sys,os,subprocess,threading,time,traceback
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from dayahead.v40b.common import *
from dayahead.v40b.supervision import instance,verify_freeze,launch_gate,TOKENS
from dayahead.v39l.infrastructure import current_process_identity

def run_missing(day,case,progress):
    from dayahead.v39e.campaign_adapter import configure_v37_runner,build_day
    from dayahead.v39e.runtime import install_runtime
    from dayahead.tools.run_v39e_may_day import _install_windows_safe_k_archive
    from dayahead.v40b.reuse import validate_case_files
    install_runtime();_install_windows_safe_k_archive()
    # Keep nested beam checkpoint filenames below the Windows path limit.
    runner=configure_v37_runner();runner.PASS_ID='V40B'
    runner.STATUS_ROOT=ROOT/'baseline_status';runner.DATE_RESULT_ROOT=ROOT/'baseline_dates'
    aidc=build_day(REPO,day,'B0' if case=='B2' else case)
    fp=runner.case_execution_fingerprint(REPO,day,case,aidc);beam=None
    progress({'case':case,'current_stage':'M1_ROUTE_PQ' if case=='B2' else 'FRESH'})
    if case=='B2':beam,_=runner._beam_case(REPO,day,case,aidc,aidc,fp)
    result=runner._run_frozen_case(REPO,day,case,aidc,beam)
    runner._write_case_checkpoint(REPO,day,case,result,fp)
    cp=runner._checkpoint_path(REPO,day,case);case_root=runner._case_root(REPO,day,case)
    validated=validate_case_files(day,case,cp,case_root)
    certificate={'status':'PASS','day':day,'case':case,'checkpoint':str(cp),'checkpoint_SHA':sha(cp),
        'case_root':str(case_root),'files':validated['files'],'execution_fingerprint':fp}
    write(ROOT/'days'/day/case/'CASE_CERTIFICATE.json',certificate);return certificate

def day_worker(day):
    method,_=verify_freeze()
    from dayahead.v40b.windows_paths import install_beam_paths
    install_beam_paths()
    identity=current_process_identity();output=ROOT/'days'/day
    output.mkdir(parents=True,exist_ok=True);stop=threading.Event();lock=threading.RLock()
    state={'day':day,'status':'RUNNING','case':'B3','current_stage':'A0','completed_units':0,'total_units':10,
           'worker_pid':os.getpid(),'worker_creation_time_utc':identity['creation_time_utc'],'method_SHA':method['method_SHA'],
           'windows_path_policy':'EXTENDED_LENGTH_BEAM_CHECKPOINTS'}
    def emit(value=None):
        with lock:
            if value:
                if 'current_stage' in value and value['current_stage']!=state.get('current_stage'):state['solver_detail']={}
                state.update(value)
                phase=state.get('current_stage')
                base={'A0':3,'M1_ROUTE_PQ':4,'A1_FEEDBACK':8,'MF_FIXED_ROUTE_PQ':9,'FRESH':9,'AC_RESTORATION':9,'COMPLETE':10}
                if 'current_stage' in value and state.get('case')=='B3':
                    units=base.get(phase,state['completed_units'])
                    if phase=='M1_ROUTE_PQ':units=4+max(0,int(state.get('solver_detail',{}).get('mess_index',1))-1)
                    state['completed_units']=units
            state['heartbeat_timestamp_utc']=now_utc();write(ROOT/'status'/f'{day}.json',state)
    def heartbeat():
        while not stop.wait(10):emit()
    emit();threading.Thread(target=heartbeat,daemon=True).start()
    try:
        rows=[r for r in read(ROOT/'V40B_MAY_EXECUTION_MATRIX.json')['rows'] if r['day']==day];completed={}
        for row in rows:
            case=row['case']
            if row['status']=='REUSE_CERTIFIED':
                cert=read(Path(row['certificate']))
                from dayahead.v40b.reuse import validate_case_files
                if cert['case']=='B3' or sha(Path(cert['historical_checkpoint']))!=cert['historical_checkpoint_SHA']:raise RuntimeError('INVALID_REUSE_CERTIFICATE')
                validate_case_files(day,case,Path(cert['historical_checkpoint']),Path(cert['historical_case_root']))
                completed[case]={'status':'REUSE_CERTIFIED','certificate':row['certificate'],'certificate_SHA':sha(Path(row['certificate']))}
            else:
                from dayahead.v40b.recovery import completed_case
                saved=completed_case(day,case,method['method_SHA'])
                if saved is None:
                    if case=='B3':
                        from dayahead.v40b.b3 import run
                        run(day,emit)
                    else:run_missing(day,case,emit)
                p=output/case/'CASE_CERTIFICATE.json'
                completed[case]={'status':'COMPLETE_NEW_V40A','certificate':str(p),'certificate_SHA':sha(p)}
            write(output/'CASE_COMPLETION.json',{'day':day,'cases':completed})
            emit({'completed_units':len(completed) if case!='B3' else 10})
        if set(completed)!=set(CASES) or completed['B3']['status']!='COMPLETE_NEW_V40A':raise RuntimeError('DAY_INCOMPLETE')
        write(output/'DAY_CERTIFICATE.json',{'status':'PASS','day':day,'cases':completed,'method_SHA':method['method_SHA']})
        emit({'status':'PASS','case':'B3','current_stage':'COMPLETE','completed_units':10})
    except BaseException as error:
        write(output/'FAILURE.json',{'status':'FAIL','day':day,'error':repr(error),'traceback':traceback.format_exc()})
        emit({'status':'FAIL','error':repr(error)})
        raise
    finally:stop.set()

def orchestrate():
    method,execution=launch_gate()
    with instance() as own:
        pending=list(DAYS);active={};completed=[];failed=[];sequence=0
        rows=read(ROOT/'V40B_MAY_EXECUTION_MATRIX.json')['rows']
        state={'orchestrator_pid':os.getpid(),'orchestrator_parent_pid':own['parent_pid'],
          'orchestrator_creation_time_utc':own['creation_time_utc'],'orchestrator_command_match_tokens':list(TOKENS),
          'method_SHA':method['method_SHA'],'execution_SHA':execution['execution_SHA'],'total_days':31}
        while pending or active:
            for day,worker in list(active.items()):
                if worker['process'].poll() is None:continue
                certificate=ROOT/'days'/day/'DAY_CERTIFICATE.json';good=False
                if worker['process'].returncode==0 and certificate.exists():
                    result=read(certificate)
                    good=result['status']=='PASS' and set(result['cases'])==set(CASES) and result['cases']['B3']['status']=='COMPLETE_NEW_V40A'
                    good=good and all(sha(Path(c['certificate']))==c['certificate_SHA'] for c in result['cases'].values())
                if good:completed.append(day)
                else:failed.append(day)
                partial=ROOT/'days'/day/'CASE_COMPLETION.json';cases=read(partial).get('cases',{}) if partial.exists() else {}
                for row in rows:
                    if row['day']==day:
                        if row['case'] in cases:row.update(cases[row['case']])
                        elif not good:row['status']='FAILED'
                worker['log'].close();del active[day]
                from dayahead.v40b.reuse import write_matrix
                write_matrix(rows)
            while pending and len(active)<4:
                day=pending.pop(0);log_path=ROOT/'logs'/f'{day}.log';log_path.parent.mkdir(parents=True,exist_ok=True)
                log=log_path.open('ab',buffering=0)
                process=subprocess.Popen([sys.executable,'-u',str(Path(__file__).resolve()),'--day',day],cwd=REPO,
                   stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
                active[day]={'process':process,'log':log}
            sequence+=1;now=now_utc()
            state.update(status='RUNNING' if active else 'FAIL' if failed else 'PASS',running_days=list(active),completed_days=completed,
              failed_days=failed,active_worker_PIDs=[w['process'].pid for w in active.values()],worker_PIDs={d:w['process'].pid for d,w in active.items()},
              heartbeat_timestamp_utc=now,last_update=now,heartbeat_sequence=sequence)
            write(ROOT/'V40A_MAY_PROGRESS.json',state)
            time.sleep(10)
        complete=len(completed)==31 and not failed and all(r['status'] in ('REUSE_CERTIFIED','COMPLETE_NEW_V40A') for r in rows)
        write(ROOT/'CAMPAIGN_COMPLETION.json',{'status':'PASS' if complete else 'FAIL','completed_days':completed,'failed_days':failed,
          'case_count':sum(r['status'] in ('REUSE_CERTIFIED','COMPLETE_NEW_V40A') for r in rows),
          'new_B3_count':sum(r['case']=='B3' and r['status']=='COMPLETE_NEW_V40A' for r in rows)})

def main():
    p=argparse.ArgumentParser();g=p.add_mutually_exclusive_group(required=True);g.add_argument('--orchestrate',action='store_true');g.add_argument('--day',choices=DAYS)
    p.add_argument('--resume',action='store_true')
    p.add_argument('--repair-id',choices=['02_windows_baseline_path','04_windows_long_paths'])
    a=p.parse_args();os.chdir(REPO)
    if a.repair_id and not a.resume:p.error('--repair-id requires --resume')
    if a.resume and not a.orchestrate:p.error('--resume requires --orchestrate')
    if a.resume:
        from dayahead.v40b import recovery
        if a.repair_id:recovery.REPAIR=ROOT/'repairs'/a.repair_id
        recovery.orchestrate_recovery()
    elif a.orchestrate:orchestrate()
    else:day_worker(a.day)

if __name__=='__main__':main()
