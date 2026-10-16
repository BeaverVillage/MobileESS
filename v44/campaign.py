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
    from .daily import day_inputs
    row=day_inputs(case['day'])
    request=dict(case,stage=stage,root=str(root),output=str(root/'OUTPUT') if stage in ('A1','A2') else str(root),
        input_folder=row['native_folder'],Threads=1,Worker=1,P2_calls=0,native_budget_seconds=5400,
        wall_budget_seconds=None,target_gap=.005 if stage in ('A1','A2') else .03)
    return request


def _aidc(result):return str(Path(result['AIDC_reference']['path']).parent)


def stage_file(case,stage,name='RESULT.json'):
    pointer=Path(case['case_root'])/'RESTORED_COMPLETED_STAGES.json'
    restored=read(pointer) if pointer.exists() else {}
    return Path(restored[stage]['root'])/name if stage in restored else Path(case['case_root'])/stage/name


def stage_result(case,stage,function):
    """Re-use a sealed completed stage, or restore this M stage's binary case."""
    request=stage_request(case,stage)
    if case.get('resume_of'):
        from .checkpoints import load_completed,crash_admission,assert_dead
        parent=Path(case['resume_of'])/stage
        # A previous continuation may itself have consumed earlier stages.
        inherited=Path(case['resume_of'])/'RESTORED_COMPLETED_STAGES.json'
        old=read(inherited) if inherited.exists() else {}
        if stage in old:parent=Path(old[stage]['root'])
        if parent.exists():
            assert_dead(parent)
            if (parent/'COMPLETED_STAGE_CHECKPOINT.json').exists():
                result=load_completed(parent,request)
                pointer=Path(case['case_root'])/'RESTORED_COMPLETED_STAGES.json'
                saved=read(pointer) if pointer.exists() else {}
                saved[stage]=dict(root=str(parent),checkpoint=record(parent/'COMPLETED_STAGE_CHECKPOINT.json'),new_Native_calls=0)
                atomic(pointer,saved);return result
            if stage in ('M1','M2') and not (parent/'BINARY_STAGE_CHECKPOINT.json').exists():
                raise NotReady('RESUME_BINARY_CHECKPOINT_NOT_SUPPORTED:'+stage)
            if stage=='ACTUAL':
                request['actual_restart_from_independent_source']=True
                return function(request)
            admission=crash_admission(parent,request)
            if admission['status']!='RESTORABLE_M_BINARY':raise NotReady('RESUME_STAGE_NOT_SUPPORTED:'+stage+':'+admission['reason'])
            request['resume_parent']=str(parent)
    return function(request)


def run_case(request):
    """One fresh attempt; every stage's files/clocks live below this case."""
    from .execution import case_scope
    from . import worker
    from .daily import load_aidc,day_inputs
    from .stages import require_a2
    root=Path(request['case_root']);root.mkdir(parents=True,exist_ok=False)
    if request.get('resume_of'):
        from .checkpoints import assert_dead
        assert_dead(request['resume_of'])
    who=dict(**process_identity(),day=request['day'],arm=request['arm'],worker_slot=request['worker_slot'])
    atomic(root/'START.json',dict(who,UTC=now(),sources=request['sources'],source_sha=request['source_sha'],
        scientific_case_root=request.get('scientific_case_root',str(root))))
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
                    progress('A1');r=stage_result(request,'A1',worker.a_stage)
                    if not r.get('PASS'):raise NotReady('A1_NOT_ACCEPTED')
                else:
                    progress('A1_REUSE');r=read(campaign/'B1_A1'/f'{day}.json')
                    if r.get('day')!=day or not r.get('PASS'):raise NotReady('SAME_DATE_B1_A1_REQUIRED')
                    verify([r['AIDC_reference']]);atomic(root/'A1_REUSE.json',dict(r,new_optimization_calls=0,A2_certified=False))
                folder=Path(_aidc(r));aidc,_=load_aidc(folder,day)
                if arm=='B1':
                    atomic(campaign/'B1_A1'/f'{day}.json',r)
                    a1_request=stage_request(request,'A1')
                    restored=read(root/'RESTORED_COMPLETED_STAGES.json') if (root/'RESTORED_COMPLETED_STAGES.json').exists() else {}
                    a1_root=Path(restored['A1']['root']) if 'A1' in restored else Path(a1_request['root'])
                    a1_output=Path(r.get('accepted_cache_output',str(a1_root/'OUTPUT')))
                    cache=a1_output/'STATIC/DOMAIN'/day/'PHYSICAL_DOMAIN_CACHE.json'
                    domain=read(cache);prepared=read(a1_output/'A_PREPARE_RECEIPT.json')
                    proof=Path(a1_request['root'])/'ACCEPTED_A1_CACHE_PROOF.json'
                    atomic(proof,dict(schema='V44_ACCEPTED_A1_PHYSICAL_CACHE',day=day,result=record(a1_root/'RESULT.json'),
                        cache=record(cache),sources=request['sources'],inputs={n:record(Path(a1_request['input_folder'])/n)
                            for n in ('NATIVE_INPUT.json','WINDOWS.json')}))
                    a1_request.update(_current_date_physical_cache=str(a1_output),_physical_cache_identity=record(cache),
                        physical_cache_case_proof=record(proof),_expected_model_verification=prepared['verification'],
                        _expected_complete_domain_hashes=domain['complete_domain_hashes'])
                    atomic(campaign/'B1_A1'/f'{day}.request.json',a1_request)
            mess=None;mess_result=None
            if arm in ('B2','B3'):
                progress('M1');m=stage_result(request,'M1',lambda r:worker.m_stage(r,aidc))
                if not m['allow_downstream']:raise NotReady(m['status'])
                if arm=='B3':
                    progress('A2');a2=stage_request(request,'A2')
                    a1_request=read(campaign/'B1_A1'/f'{day}.request.json')
                    a2.update(physical_domain_request=a1_request,
                        physical_cache_case_proof=a1_request['physical_cache_case_proof'],M1_result=record(stage_file(request,'M1')))
                    r=stage_result(request,'A2',lambda r:worker.a_stage(dict(r,physical_domain_request=a2['physical_domain_request'],
                        physical_cache_case_proof=a2['physical_cache_case_proof'],M1_result=a2['M1_result']),m1=m));require_a2(r,day)
                    folder=Path(_aidc(r));aidc,_=load_aidc(folder,day)
                    progress('M2');m=stage_result(request,'M2',lambda r:worker.m_stage(r,aidc))
                    if not m['allow_downstream']:raise NotReady(m['status'])
                mess=m['MESS_plan'];mess_result=str(stage_file(request,'M2' if arm=='B3' else 'M1'))
            progress('ACTUAL_FRESH');a=stage_request(request,'ACTUAL');a['MESS_result']=mess_result
            result.update(stage_result(request,'ACTUAL',lambda r:worker.actual(dict(r,MESS_result=a['MESS_result']),folder,mess)))
            result['status']='COMPLETE' if result.get('PASS') else 'FAILED'
        except BaseException as error:
            result.update(status='BLOCKED' if isinstance(error,NotReady) else 'FAILED',error=repr(error),traceback=traceback.format_exc())
        finally:
            result.update(finished_UTC=now());atomic(root/'RESULT.json',result)
    return result


def run(root,permit,*,resume=False):
    certification=read(DOC/'PREEXECUTION_CERTIFICATION.json');require_execution_permit(permit,certification)
    freeze=read(DOC/'SCIENTIFIC_FREEZE_MANIFEST.json')
    sources=[r['V44'] for r in freeze['unchanged_source_rows']+freeze['unchanged_support_inputs']]+[r['source'] for r in freeze['inherited_external_M_algorithms']]+freeze['adapters']+freeze.get('physics_receipts',[])
    verify(sources);root=Path(root)
    if root.exists() and not resume:raise ValueError('NEW_CAMPAIGN_ROOT_OR_EXPLICIT_RESUME_REQUIRED')
    states={};running={};resume_sources={};attempt_numbers={}
    with coordinator(root) as lease:
        data=read(DOC/'SEVEN_DAY_INPUT_MANIFEST.json')
        for case in data['cases']:
            key=(case['day'],case['arm']);attempts=sorted((root/case['day']/case['arm']).glob('attempt[0-9][0-9][0-9]'))
            path=attempts[-1] if attempts else root/case['day']/case['arm']/'attempt001'
            attempt_numbers[key]=int(path.name[-3:])+1 if attempts else 1
            complete=(path/'RESULT.json').exists() and read(path/'RESULT.json')['status']=='COMPLETE'
            if complete:states[key]='COMPLETE'
            elif path.exists() and resume:
                from .checkpoints import assert_dead
                assert_dead(path)
                # Each stage performs its own completed/binary checkpoint and
                # Native reconciliation checks before any solver admission.
                states[key]='READY';resume_sources[key]=path
            elif path.exists():states[key]='BLOCKED'
            else:
                from .initial_states import READY_INPUT_STATES
                states[key]='READY' if case['status'] in READY_INPUT_STATES else 'INPUT_NOT_READY'
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
                task_key=(task['day'],task['arm'])
                case_root=root/task['day']/task['arm']/f'attempt{attempt_numbers[task_key]:03d}'
                dated=next(r for r in data['days'] if r['day']==task['day'])
                dated_sources=sources+list(dated['files'].values())
                case=dict(task,case_root=str(case_root),campaign_root=str(root),lease=lease,sources=dated_sources,source_sha=digest(dated_sources),
                    scientific_source_sha=freeze['source_sha'],axis=axis(task['day']),execution_permit=record(permit))
                if task_key in resume_sources:
                    parent=resume_sources[task_key];start=read(parent/'START.json')
                    if start['source_sha']!=case['source_sha']:
                        states[task_key]='BLOCKED'
                        atomic(root/'resume_audit'/f'{task["day"]}_{task["arm"]}.json',dict(
                            status='BLOCKED',reason='RESUME_SOURCE_OR_DATED_INPUT_SHA_DRIFT',parent=record(parent/'START.json'),UTC=now()))
                        continue
                    case.update(resume_of=str(parent),scientific_case_root=start.get('scientific_case_root',str(parent)))
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
