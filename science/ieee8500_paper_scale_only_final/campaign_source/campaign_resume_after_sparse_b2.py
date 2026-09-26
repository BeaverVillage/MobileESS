"""Continue B0→B2→B1→B3 only after sparse B2 exact AC and Actual gates."""
from __future__ import annotations
import json
import os
import sys
import time
import traceback
from pathlib import Path
import psutil
import campaign_final as campaign

H=Path(__file__).absolute().parent
STATUS=H/'ACTIVE_CAMPAIGN_CONTINUATION_STATUS.json'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def save(path,value):
    campaign.save(str(Path(path).relative_to(H)),value)


def wait_for_b2():
    paper_launch=H/'B2_PAPER_TERMINATION_RUN_20260921/LAUNCH.json'
    repair_launch=H/'B2_PREFERRED_BOUND_REPAIR_RUN_20260921/LAUNCH.json'
    launch=read(paper_launch if paper_launch.exists() else repair_launch if repair_launch.exists() else
                H/'B2_ACTIVE_PRODUCTION_RUN_20260921/LAUNCH.json')
    pid=int(launch['PID'])
    if paper_launch.exists():
        authority=read(H/'PAPER_SOLVER_TERMINATION_AUTHORITY.json')
        assert authority['status']=='PASS' and authority['B2_restart_from_scratch']
    else:
        assert read(H/'B2_ACTIVE_PRODUCTION_PRELAUNCH.json')['status']=='READY_FOR_FULL_B2_ACTIVE_SEPARATION'
    while True:
        complete=H/'B2/COMPLETE.json'
        if complete.exists():
            assert read(complete)['status']=='PASS'
            for name in ('B2/independent_clean_exact/AC_VALIDATION.json',
                         'B2/Fresh/AC_VALIDATION.json'):
                assert read(H/name)['status']=='PASS',name
            return
        if not psutil.pid_exists(pid):
            raise RuntimeError('B2_WORKER_EXITED_WITHOUT_EXACT_AC_COMPLETE')
        save(STATUS,dict(status='WAITING_FOR_B2_EXACT_AC',worker_pid=pid,
            latest_live=read(H/'STATUS.json'),updated_unix=time.time()))
        time.sleep(30)


def stage(label,script,*args,policy,complete,exact=None,actual=False):
    target=H/complete
    if target.exists():
        result=read(target)
        assert (result['AC_feasible'] if actual else result['status']=='PASS')
        save(STATUS,dict(status='ALREADY_COMPLETE',stage=label,
            evidence=str(target),updated_unix=time.time()))
        return
    save(STATUS,dict(status='RUNNING',stage=label,updated_unix=time.time()))
    if actual and (H/'ACTUAL_SPEED_RESUME_AUTHORITY.json').exists():
        if policy=='B2':script='actual_resume_fast.py'
        elif policy=='B3':script='actual_fresh_fast.py'
    if actual and policy in ('B2','B3') and (H/'ACTUAL_NATIVE_RESUME_AUTHORITY.json').exists():
        script='actual_native_entry.py'
    if actual and policy=='B1' and (H/'B1_ACTUAL_EVIDENCE_REPAIR.json').exists():
        script='actual_b1_evidence_entry.py'
    campaign.run(label,script,*args,policy=policy)
    result=read(target)
    assert (result['AC_feasible'] if actual else result['status']=='PASS')
    for path in exact or ():
        assert read(H/path)['status']=='PASS',path
    save(STATUS,dict(status='STAGE_COMPLETE',stage=label,
        evidence=str(target),updated_unix=time.time()))


def main():
    freeze=read(H/'FINAL_CANDIDATE_FREEZE.json')
    assert freeze['PAPER_PCC_CONFIG_USED'] and not freeze['RESITING_USED']
    assert (freeze['BG_SCALE'],freeze['AIDC_ABSOLUTE_SCALE'],freeze['MESS_SCALE'])==(.552,2.4,2.)
    assert read(H/'B0/COMPLETE.json')['status']=='PASS'
    assert read(H/'Actual/B0/COMPLETE.json')['AC_feasible']
    wait_for_b2()
    stage('B2_ACTUAL','actual_worker.py','B2',policy='B2',
          complete='Actual/B2/COMPLETE.json',actual=True)
    stage('B1_AIDC','production_worker.py','B1',policy='B1',
          complete='B1/COMPLETE.json',exact=('B1/Fresh/AC_VALIDATION.json',))
    stage('B1_ACTUAL','actual_worker.py','B1',policy='B1',
          complete='Actual/B1/COMPLETE.json',actual=True)
    assert read(H/'B1/COMPLETE.json')['status']=='PASS'
    assert read(H/'Actual/B1/COMPLETE.json')['AC_feasible']
    stage('B3_A1_AIDC','production_worker.py','B3_A1',policy='B3',
          complete='B3_A1/COMPLETE.json')
    stage('B3_M1_ROUTE_PQ','production_worker.py','B3_M1',policy='B3',
          complete='B3_M1/COMPLETE.json')
    stage('B3_A2_AIDC','production_worker.py','B3_A2',policy='B3',
          complete='B3_A2/COMPLETE.json')
    stage('B3_M2_PQ','mf_worker.py',policy='B3',complete='B3/COMPLETE.json',
          exact=('B3/final_exact/AC_VALIDATION.json','B3/Fresh/AC_VALIDATION.json'))
    stage('B3_ACTUAL','actual_worker.py','B3',policy='B3',
          complete='Actual/B3/COMPLETE.json',actual=True)
    stage('FINAL_REPORT','report_final_campaign.py',policy='REPORT',
          complete='FINAL_CAMPAIGN_RESULT.json')
    campaign.save('CAMPAIGN_STATUS.json',dict(status='COMPLETE',stage='FINISHED',
        policy='REPORT',order=['B0','B2','B1','B3'],completed_unix=time.time(),
        supervisor_pid=os.getpid()))
    save(STATUS,dict(status='COMPLETE',updated_unix=time.time()))


if __name__=='__main__':
    try:main()
    except BaseException as error:
        save(STATUS,dict(status='FAILED',error=repr(error),
            traceback=traceback.format_exc(),updated_unix=time.time()))
        campaign.save('CAMPAIGN_STATUS.json',dict(status='FAILED',
            stage='ACTIVE_CAMPAIGN_CONTINUATION_STOPPED',error=repr(error),
            recorded_unix=time.time(),supervisor_pid=os.getpid()))
        raise
