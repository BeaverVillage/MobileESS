"""Future explicit-permit dispatcher. Default CLI never launches a worker."""
import argparse
from pathlib import Path
import os
import subprocess
import sys
import time
import traceback

from .common import ROOT,DOC,RUNTIME,read,record,verify,atomic,digest,now,NotReady
from .config import DAYS,ARMS,axis
from .locks import coordinator,worker_slot,process_identity,alive
from .scheduler import assignments
from .prepare import require_execution_permit


def stage_request(case,stage):
    root=Path(case['case_root'])/stage
    row=next(r for r in read(DOC/'SEVEN_DAY_INPUT_MANIFEST.json')['days'] if r['day']==case['day'])
    request=dict(case,stage=stage,root=str(root),output=str(root/'OUTPUT') if stage in ('A1','A2') else str(root),
        input_folder=row['native_folder'],Threads=1,Worker=1,P2_calls=0,native_budget_seconds=5400,
        wall_budget_seconds=None,target_gap=.005 if stage in ('A1','A2') else .03)
    if stage=='ACTUAL' and case['arm'] in ('B1','B3'):
        request['correction_proof']=row['files'].get('C1_correction_proof_'+case['arm'])
    return request


def _aidc(result):return str(Path(result['AIDC_reference']['path']).parent)


def run_case(request):
    """One fresh attempt; every stage's files/clocks live below this case."""
    from .execution import case_scope
    from . import worker
    from .daily import load_aidc,day_inputs
    from .stages import require_a2
    root=Path(request['case_root']);root.mkdir(parents=True,exist_ok=False)
    who=dict(**process_identity(),day=request['day'],arm=request['arm'],worker_slot=request['worker_slot'])
    atomic(root/'START.json',dict(who,UTC=now(),sources=request['sources'],source_sha=request['source_sha']))
    result=dict(day=request['day'],arm=request['arm'],status='FAILED',PASS=False)
    with worker_slot(request['day'],request['arm'],request['worker_slot'],root=request['campaign_root'],lease=request['lease']),case_scope(request,request['lease'],who):
        try:
            day_inputs(request['day']);arm=request['arm'];day=request['day'];campaign=Path(request['campaign_root'])
            def progress(stage):atomic(root/'progress.json',dict(day=day,arm=arm,stage=stage,status='RUNNING',pid=who['pid'],UTC=now()))
            if arm in ('B0','B2'):
                progress('REFERENCE');folder=campaign/'references'/day
                aidc=worker.reference(day,folder)
            else:
                if arm=='B1':
                    progress('A1');r=worker.a_stage(stage_request(request,'A1'))
                    if not r.get('PASS'):raise NotReady('A1_NOT_ACCEPTED')
                else:
                    progress('A1_REUSE');r=read(campaign/'B1_A1'/f'{day}.json')
                    if r.get('day')!=day or not r.get('PASS'):raise NotReady('SAME_DATE_B1_A1_REQUIRED')
                    verify([r['AIDC_reference']]);atomic(root/'A1_REUSE.json',dict(r,new_optimization_calls=0,A2_certified=False))
                folder=Path(_aidc(r));aidc,_=load_aidc(folder,day)
                if arm=='B1':
                    atomic(campaign/'B1_A1'/f'{day}.json',r)
                    a1_request=stage_request(request,'A1')
                    if day=='2025-05-01':
                        historical=read(DOC/'../v43/GOLDEN_REQUEST_ATTEMPT003.json')
                        for key in ('_current_date_physical_cache','_physical_cache_identity','physical_cache_case_proof',
                            '_expected_model_verification','_expected_complete_domain_hashes'):
                            a1_request[key]=historical[key]
                    else:
                        cache=Path(a1_request['output'])/'STATIC/DOMAIN'/day/'PHYSICAL_DOMAIN_CACHE.json'
                        domain=read(cache);prepared=read(Path(a1_request['output'])/'A_PREPARE_RECEIPT.json')
                        proof=Path(a1_request['root'])/'ACCEPTED_A1_CACHE_PROOF.json'
                        atomic(proof,dict(schema='V44_ACCEPTED_A1_PHYSICAL_CACHE',day=day,result=record(Path(a1_request['root'])/'RESULT.json'),
                            cache=record(cache),sources=request['sources'],inputs={n:record(Path(a1_request['input_folder'])/n)
                                for n in ('NATIVE_INPUT.json','WINDOWS.json')}))
                        a1_request.update(_current_date_physical_cache=a1_request['output'],_physical_cache_identity=record(cache),
                            physical_cache_case_proof=record(proof),_expected_model_verification=prepared['verification'],
                            _expected_complete_domain_hashes=domain['complete_domain_hashes'])
                    atomic(campaign/'B1_A1'/f'{day}.request.json',a1_request)
            mess=None;mess_result=None
            if arm in ('B2','B3'):
                progress('M1');m=worker.m_stage(stage_request(request,'M1'),aidc)
                if not m['allow_downstream']:raise NotReady(m['status'])
                if arm=='B3':
                    progress('A2');a2=stage_request(request,'A2')
                    a1_request=read(campaign/'B1_A1'/f'{day}.request.json')
                    a2.update(physical_domain_request=a1_request,
                        physical_cache_case_proof=a1_request['physical_cache_case_proof'],M1_result=record(root/'M1/RESULT.json'))
                    r=worker.a_stage(a2,m1=m);require_a2(r,day)
                    folder=Path(_aidc(r));aidc,_=load_aidc(folder,day)
                    progress('M2');m=worker.m_stage(stage_request(request,'M2'),aidc)
                    if not m['allow_downstream']:raise NotReady(m['status'])
                mess=m['MESS_plan'];mess_result=str(root/('M2' if arm=='B3' else 'M1')/'RESULT.json')
            progress('ACTUAL_FRESH');a=stage_request(request,'ACTUAL');a['MESS_result']=mess_result
            result.update(worker.actual(a,folder,mess))
            result['status']='COMPLETE' if result.get('PASS') else 'FAILED'
        except BaseException as error:
            result.update(status='BLOCKED' if isinstance(error,NotReady) else 'FAILED',error=repr(error),traceback=traceback.format_exc())
        finally:
            result.update(finished_UTC=now());atomic(root/'RESULT.json',result)
    return result


def run(root,permit,*,resume=False):
    certification=read(DOC/'PREEXECUTION_CERTIFICATION.json');require_execution_permit(permit,certification)
    freeze=read(DOC/'SCIENTIFIC_FREEZE_MANIFEST.json')
    sources=[r['V44'] for r in freeze['unchanged_source_rows']+freeze['unchanged_support_inputs']]+[r['source'] for r in freeze['inherited_external_M_algorithms']]+freeze['adapters']
    verify(sources);root=Path(root)
    if root.exists() and not resume:raise ValueError('NEW_CAMPAIGN_ROOT_OR_EXPLICIT_RESUME_REQUIRED')
    states={};running={}
    with coordinator(root) as lease:
        data=read(DOC/'SEVEN_DAY_INPUT_MANIFEST.json')
        for case in data['cases']:
            key=(case['day'],case['arm']);path=root/case['day']/case['arm']/'attempt001'
            if (path/'RESULT.json').exists():states[key]=read(path/'RESULT.json')['status']
            elif path.exists():
                # Do not reset a crashed stage's clock. Unknown in-flight Native
                # time needs a reconciled checkpoint before that case can resume.
                start=read(path/'START.json')
                if alive(start):raise NotReady('RESUME_OLD_WORKER_STILL_LIVE')
                states[key]='BLOCKED'
                atomic(path/'RESUME_BLOCKED.json',dict(UTC=now(),reason='RECONCILED_STAGE_CHECKPOINT_REQUIRED_NO_NATIVE_CLOCK_RESET',
                    ledgers=[record(p) for p in path.rglob('*LEDGER.json')]))
            else:states[key]='READY' if case['status']=='INPUT_READY' else 'INPUT_NOT_READY'
        while True:
            for pid,item in list(running.items()):
                if item['process'].poll() is not None:
                    path=Path(item['case']['case_root'])/'RESULT.json'
                    states[(item['case']['day'],item['case']['arm'])]=read(path)['status'] if path.exists() else 'BLOCKED'
                    atomic(Path(item['case']['case_root']).with_suffix('.PROCESS_EXIT.json'),dict(exit_code=item['process'].returncode,UTC=now()))
                    del running[pid]
            active=[item['case'] for item in running.values()]
            tasks=assignments(states,active)
            for task in tasks:
                atomic(root/'PHASE.json',dict(lane=task['lane'],UTC=now()))
                case_root=root/task['day']/task['arm']/'attempt001'
                dated=next(r for r in data['days'] if r['day']==task['day'])
                dated_sources=sources+list(dated['files'].values())
                case=dict(task,case_root=str(case_root),campaign_root=str(root),lease=lease,sources=dated_sources,source_sha=digest(dated_sources),
                    scientific_source_sha=freeze['source_sha'],axis=axis(task['day']),execution_permit=record(permit))
                pointer=root/'requests'/f"{task['day']}_{task['arm']}.json";atomic(pointer,case)
                command=[sys.executable,'-u','-m','v44.campaign','--worker',str(pointer)]
                env=dict(os.environ,OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',NUMEXPR_NUM_THREADS='1')
                log=root/'launcher_logs';log.mkdir(exist_ok=True)
                with (log/(pointer.stem+'.stdout.log')).open('ab') as out,(log/(pointer.stem+'.stderr.log')).open('ab') as err:
                    process=subprocess.Popen(command,cwd=ROOT,env=env,stdout=out,stderr=err,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                running[process.pid]=dict(process=process,case=case);states[(task['day'],task['arm'])]='RUNNING'
            atomic(root/'CAMPAIGN_STATUS.json',dict(UTC=now(),cases=[dict(day=d,arm=a,status=s) for (d,a),s in states.items()],
                workers=[dict(pid=pid,day=r['case']['day'],arm=r['case']['arm'],worker_slot=r['case']['worker_slot']) for pid,r in running.items()]))
            if not running and not tasks:break
            time.sleep(.25)


def main():
    p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');p.add_argument('--permit',type=Path)
    p.add_argument('--root',type=Path,default=RUNTIME/'campaign001');p.add_argument('--resume',action='store_true')
    p.add_argument('--worker',type=Path);a=p.parse_args()
    if a.worker:
        # A fabricated request cannot acquire slot/case locks without the live
        # coordinator PID, creation time and external OS lease.
        run_case(read(a.worker));return
    if not a.execute:
        print(dict(mode='PREPARE_ONLY',status=read(DOC/'PREEXECUTION_CERTIFICATION.json')['status'],workers_started=0));return
    run(a.root,a.permit,resume=a.resume)


if __name__=='__main__':main()
