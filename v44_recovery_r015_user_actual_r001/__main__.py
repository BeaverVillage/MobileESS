import argparse,os,subprocess,sys,time
from pathlib import Path
import psutil
from v44.common import read,record,verify,atomic,digest,now,ROOT
from v44.locks import coordinator,alive,process_identity
from v44_recovery_r015 import operations as performance
from .authorization import validate,PERMIT,PARENT,TARGET,OPS,sources

def run_coordinator():
    validate()
    if performance.workers():raise PermissionError('EXISTING_CAMPAIGN_WORKER')
    if alive(read(performance.CAMPAIGN/'COORDINATOR_LEASE.json')):raise PermissionError('EXISTING_COORDINATOR')
    with coordinator(performance.CAMPAIGN) as lease:
        atomic(OPS/'COORDINATOR_START.json',dict(UTC=now(),**process_identity(),permit=record(performance.PERMIT),user_actual_restart_permit=record(PERMIT)))
        old=read(OPS/'requests/2025-05-01_B3_attempt002.json')
        case={k:old[k] for k in ['day','arm','worker_slot','lane','campaign_root','scientific_source_sha','axis']}
        case.update(case_root=str(TARGET),lease=lease,sources=old['sources']+sources(),execution_permit=record(performance.PERMIT))
        case=performance.decorate(case,performance.validate())
        case.update(wall_resume_parent=str(PARENT),user_actual_restart_permit=record(PERMIT))
        pointer=OPS/'requests/2025-05-01_B3_attempt003.json';assert not pointer.exists();atomic(pointer,case)
        original=performance.CAMPAIGN/'requests/2025-05-01_B3.json'
        atomic(OPS/'request_history/2025-05-01_B3_before_user_r015_attempt003.json',read(original));atomic(original,case)
        atomic(performance.CAMPAIGN/'PHASE.json',dict(lane='MAIN',UTC=now()))
        with (OPS/'launcher_logs/2025-05-01_B3_attempt003.out.log').open('ab') as out,(OPS/'launcher_logs/2025-05-01_B3_attempt003.err.log').open('ab') as err:
            proc=subprocess.Popen([sys.executable,'-X','utf8','-u','-m','v44_recovery_r015_user_actual_r001','--worker',str(pointer)],cwd=ROOT,
                env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',NUMEXPR_NUM_THREADS='1'),stdout=out,stderr=err,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        atomic(OPS/'R015_USER_ACTUAL_STARTED.json',dict(UTC=now(),coordinator=lease,worker=dict(pid=proc.pid,process_created=psutil.Process(proc.pid).create_time()),request=record(pointer),r015_permit=record(performance.PERMIT),operational_permit=record(PERMIT)))
        while True:
            states=performance.states(performance.CAMPAIGN);states[('2025-05-01','B3')]='RUNNING'
            atomic(performance.CAMPAIGN/'CAMPAIGN_STATUS.json',dict(UTC=now(),cases=[dict(day=d,arm=a,status=s) for (d,a),s in states.items()],workers=[dict(pid=proc.pid,day='2025-05-01',arm='B3',worker_slot=1)]))
            if proc.poll() is not None:break
            time.sleep(1)
        atomic(TARGET.with_suffix('.PROCESS_EXIT.json'),dict(UTC=now(),exit_code=proc.returncode))
        if not (TARGET/'RESULT.json').exists():atomic(TARGET/'RESULT.json',dict(day='2025-05-01',arm='B3',status='FAILED',PASS=False,error='USER_ACTUAL_WORKER_EXIT_WITHOUT_RESULT',exit_code=proc.returncode,finished_UTC=now()))
        atomic(TARGET/'RECOVERY_R015_APPLIED.json',dict(UTC=now(),permit=record(performance.PERMIT),operational_permit=record(PERMIT),new_M_Native_clocks_from_zero=False,new_M_Native_calls=0,prior_M_UB_LB_seed_inherited=False,Actual_context='NEW_INDEPENDENT',original_parent=str(PARENT)))
        atomic(OPS/'R015_USER_ACTUAL_FINISHED.json',dict(UTC=now(),result=record(TARGET/'RESULT.json'),r015_standard_queue_may_resume_after_coordinator_exit=True))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--worker',type=Path);parser.add_argument('--coordinator',action='store_true');args=parser.parse_args()
    if args.worker:
        from .worker import worker
        worker(read(args.worker))
    elif args.coordinator:run_coordinator()
    else:raise PermissionError('EXPLICIT_USER_ACTUAL_MODE_REQUIRED')
if __name__=='__main__':main()
