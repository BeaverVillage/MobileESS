"""Execute the explicitly requested B2-only staged May campaign, one worker."""
import os
for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[name]='1'
import argparse
import gc
import json
from pathlib import Path
import shutil
import sys
import threading
from time import time
import traceback
import uuid
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))

from v42_integration.table_v_b2_solo import (read,write_new,prepare_date,make_launch,approve_completed,
    check_integrity,reuse_planning_actual96,summarize,case_binding,B2_SCOPES,REPRESENTATIVES,MAY_DATES)
from v42_integration.m_engine import _write,file_record
from v42_integration.table_v_launch import release_identity
from v42_integration.table_v_run import run_arm
from v42_integration.table_v_memory import memory_sample
from v42_integration.table_v_launch_evidence import validate_arm_full96,REFERENCE_POLICY
from v42_integration.a_engine import digest


def run(output,request,*,execute=False):
    output=Path(output).resolve();request=Path(request).resolve()
    # A dry run reports intent only. It cannot create approval or start models.
    if not execute:
        return dict(status='INSPECTION_ONLY_NO_NATIVE',request=file_record(request),run_arms=['B2'],
            stages=[B2_SCOPES[0]],M1_per_day=1800,K48_separate_per_day=300,Worker=1,Threads=1,P2_calls=0)
    if output.exists():raise FileExistsError('B2_SOLO_EXISTING_RUN_REQUIRES_EXACT_CHECKPOINT_REVIEW_NO_AUTORETRY')
    from v42_integration.table_v_control import require_running,stop_request
    from v42_integration.table_v_resources import admit_resources
    from types import SimpleNamespace
    worker_lock=Path('D:/V42_B2_SOLO_CAMPAIGN.lock')
    owner=json.dumps(dict(pid=os.getpid(),output=str(output),nonce=uuid.uuid4().hex)).encode()
    fd=os.open(worker_lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    try:os.write(fd,owner);os.fsync(fd)
    finally:os.close(fd)
    stop=threading.Event();active=dict(day=None,phase='PREPARATION',execution=None)
    sources=release_identity();results=[];executions={};counter=[0]
    def heartbeat():
        import psutil
        process=psutil.Process()
        while not stop.is_set():
            try:
                if (output/'CAMPAIGN_STOP_REQUEST.json').exists() and active['execution']:
                    stop_request(Path(active['execution']),reason='B2_SOLO_USER_STOP')
                _write(output/'RUN_HEARTBEAT.json',dict(pid=os.getpid(),epoch_seconds=time(),**active,
                    CPU_percent=process.cpu_percent(),memory=memory_sample(),Worker=1,Threads=1))
            except Exception:pass
            stop.wait(5.)
    observer=None
    def event(kind,**fields):
        record=dict(kind=kind,epoch_seconds=time(),**fields)
        with (output/'RUN_EVENTS.jsonl').open('a',encoding='utf8') as stream:stream.write(json.dumps(record)+'\n')
        print(json.dumps(record),flush=True)
    def safe():
        require_running(output)
        if release_identity()!=sources:raise RuntimeError('B2_FROZEN_PRODUCTION_RELEASE_OR_GIT_DRIFT')
        admit_resources(SimpleNamespace(path=output/'WORKER.json',worker_lock=Path('D:/V42_UNIFIED_HEAVY_WORKER.lock'),authorization={}),phase='B2_SOLO_SAFE_BOUNDARY')
    def prepare(day):
        safe();root=output/'EXECUTIONS'/day;active.update(day=day,execution=str(root),phase='PUBLIC_INPUTS_AND_REFERENCE')
        event('DATE_PREPARATION_STARTED',day=day)
        prepare_date(day,root,authority);executions[day]=root
        event('DATE_PREPARATION_VALIDATED',day=day)
    def launch(scope,dates,may01=None,representatives=None):
        safe();counter[0]+=1
        return make_launch(scope,dates,executions,authority,output/'LAUNCHES'/f'{counter[0]:03d}_{scope}',
            may01_approval=may01,representative_approvals=representatives)
    def record(day,phase,outcome,folder):
        check_integrity(executions[day],outcome)
        result=dict(day=day,phase=phase,status=outcome['status'],outcome=file_record(Path(folder)/'ARM_OUTCOME.json'),error=outcome.get('error'))
        results.append(result);event('DATE_STAGE_COMPLETED',**result)
        summarize(executions,results,output)
        return result
    def boundary(reason):
        event('STOPPED_AT_REQUIRED_EVIDENCE_BOUNDARY',reason=reason)
        _write(output/'CAMPAIGN_RESULT.json',dict(status='BLOCKED_AT_B2_EVIDENCE_BOUNDARY',reason=reason,results=results,
            B1_failure_is_not_a_B2_blocker=True,Native_budget_reset=False))
        return dict(status='BLOCKED_AT_B2_EVIDENCE_BOUNDARY',reason=reason)
    try:
        output.mkdir(parents=True)
        shutil.copy2(request,output/'USER_REQUEST.txt')
        write_new(output/'LATEST_USER_SCOPE_OVERRIDE.json',dict(authority='DIRECT_USER_LATEST_MESSAGE',
            request='B2 5월 1일만 우선 실행. B0 B1 B3와 대표일 및 나머지 5월은 보류',days=['2025-05-01'],run_arms=['B2']))
        authority=dict(authority='DIRECT_HUMAN_REQUEST_IN_THIS_CHAT',request=file_record(output/'USER_REQUEST.txt'),
            requested_track='LATEST_USER_OVERRIDE_MAY01_B2_ONLY_PRIORITIZE_EXECUTION',
            run_arms=['B2'],approved_new_dates=['2025-05-01'],M1_native_stage_cap=1800,K48_separate_native_stage_cap=300,
            existing_May01_costs_carried_forward=True,new_cycle_or_reset=False,Worker=1,Threads=1,P2_calls=0,R2='HOLD')
        write_new(output/'USER_AUTHORITY.json',authority)
        write_new(output/'RUN_SOURCE_FREEZE.json',sources)
        write_new(output/'WORKER_OWNER.json',json.loads(owner))
        observer=threading.Thread(target=heartbeat,daemon=True);observer.start()
        event('B2_SOLO_STARTED',release_git_sha=sources['release_git_sha'],release_sha=sources['release_sha'])
        prepare('2025-05-01');plan,gate=launch(B2_SCOPES[0],['2025-05-01'])
        active['phase']='MAY01_FULL96_M1_K48_ACTUAL_FRESH';event('REAL_B2_MAY01_FULL96_STARTED')
        outcome=run_arm('B2',executions['2025-05-01'],actual_slots=96,launch_authority=dict(plan=plan,gate=gate))
        record('2025-05-01','MAY01_FULL96',outcome,executions['2025-05-01']/'B2')
        if outcome['status']!='FULL_PASS':return boundary('B2_MAY01_FULL96_NOT_ACCEPTED')
        may01=approve_completed(executions['2025-05-01'],executions['2025-05-01']/'B2',plan,authority,slots=96)
        result=dict(status='B2_MAY01_FULL96_COMPLETED',results=results,
            date_summary=summarize(executions,results,output),full96_approval=may01,
            other_days_executed=False,other_arms_executed=False,Native_budget_reset=False)
        write_new(output/'CAMPAIGN_RESULT.json',result)
        event('B2_MAY01_EXECUTION_FINISHED_NO_OTHER_DATE_OR_ARM')
        return result
    except BaseException as error:
        if output.exists():
            event('HALTED_AT_INTEGRITY_OR_AUTHORITY_BOUNDARY',error=repr(error))
            summarize(executions,results,output)
            _write(output/'CAMPAIGN_RESULT.json',dict(status='HALTED_AT_INTEGRITY_OR_AUTHORITY_BOUNDARY',error=repr(error),
                traceback=traceback.format_exc(),results=results,old_Raw_preserved=True,automatic_retry=False))
        raise
    finally:
        stop.set()
        if observer is not None:observer.join(timeout=2.)
        if worker_lock.read_bytes()!=owner:raise RuntimeError('B2_CAMPAIGN_WORKER_OWNERSHIP_DRIFT')
        worker_lock.unlink()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--user-request',type=Path,required=True);parser.add_argument('--execute',action='store_true')
    args=parser.parse_args();answer=run(args.output,args.user_request,execute=args.execute)
    print(json.dumps({'status':answer['status']}),flush=True)
