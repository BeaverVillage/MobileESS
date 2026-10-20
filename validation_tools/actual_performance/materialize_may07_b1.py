"""One-off, Native0 metadata registration; preserve the live B3 solver lease."""
from pathlib import Path
import argparse, sys, subprocess, time, traceback
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import psutil
from v44_recovery_r041 import operations as op
from v44.common import read, atomic, record, now, verify
from v44.locks import alive, exclusive_lock, process_identity

RECEIPT=op.OPS/'MAY07_B1_METADATA_REGISTRATION.json'
TRANSITION=op.OPS/'MAY07_B1_COORDINATOR_TRANSITION.json'
JOB=op.OPS/'MAY07_B1_PREPARED_JOB.json'

def materialize():
    from v44_recovery_r038.batch import compose_request
    from v44_recovery_r041.preparation import publish_a1, deny_actual
    from v44_recovery_r038.phases import prepare_actual
    from v44_recovery_r029 import wall_resume
    from v44.execution import case_scope
    from v44.campaign import stage_request
    from v42_may_campaign_native90.preflight import native_zero
    from unittest.mock import patch
    op.authority()
    state=read(op.STATE); lease=state['lease']
    assert alive(lease) and lease==read(op.CAMPAIGN/'COORDINATOR_LEASE.json') and op.allowed()
    job=next(j for j in state['jobs'] if op.key(j)==('2025-05-07','B1'))
    assert job['status']=='PENDING'
    request,pointer,_=compose_request(job,lease);request=op.attach(request)
    parent=op.CAMPAIGN/'2025-05-07/B1/attempt001'
    request.update(wall_resume_parent=str(parent),resume_completed_A1_only=True,
                   metadata_only_user_registration=True)
    root=Path(request['case_root'])
    who=dict(**process_identity(),day=request['day'],arm=request['arm'],worker_slot=1)
    # No MAIN slot is claimed: this path only reads certificates and writes
    # its own metadata, with optimizer and Actual entry points denied.
    with exclusive_lock(op.CAMPAIGN/'locks/cases/2025-05-07_B1.lock'):
        root.mkdir(parents=True,exist_ok=False)
        atomic(pointer,request)
        atomic(root/'START.json',dict(who,UTC=now(),sources=request['sources'],source_sha=request['source_sha'],metadata_only=True))
        with op.previous.original.install(request), native_zero() as calls, case_scope(request,lease,who), patch('v44.worker.actual',deny_actual):
            folder,mess,mess_result=wall_resume.validate_parent(parent,root/'PARENT_AUDIT')
            assert mess is None and mess_result is None
            original=read(parent/'A1/RESULT.json');publish_a1(request,parent,original)
            stage=stage_request(request,'ACTUAL');stage['MESS_result']=None
            result=dict(day=request['day'],arm=request['arm'],status='PRE_ACTUAL_READY',
                        **prepare_actual(stage,folder,None),reused_A1=record(parent/'A1/RESULT.json'),
                        new_optimization_calls=0,finished_UTC=now())
            assert not calls and not (root/'ACTUAL').exists()
        atomic(root/'RESULT.json',result);atomic(root/'PRE_ACTUAL_RESULT.json',result)
        atomic(root/'progress.json',dict(UTC=now(),stage='PRE_ACTUAL_READY',status='WAITING',Actual_started=False))
        atomic(root/'PREPARE_PROCESS_EXIT.json',dict(UTC=now(),exit_code=0,metadata_only=True))
        atomic(JOB,dict(day=request['day'],arm=request['arm'],status='PREPARED',case_root=str(root),
                       prepare_request=str(pointer),handoff=result['pre_actual_handoff'],
                       result=record(root/'RESULT.json'),process_exit=0))
        atomic(op.CAMPAIGN/'requests/2025-05-07_B1.json',request)

def register():
    op.authority()
    with exclusive_lock(op.OPS/'MAY07_B1_REGISTRATION.lock'):
        state=read(op.STATE);lease=state['lease'];coord=psutil.Process(lease['pid'])
        assert alive(lease) and lease==read(op.CAMPAIGN/'COORDINATOR_LEASE.json')
        assert '--coordinator' in coord.cmdline() and op.ENTRY in coord.cmdline()
        assert state['phase']=='PREPARE_SERIAL' and op.allowed()
        running=[j for j in state['jobs'] if j['status']=='PREPARING']
        assert len(running)==1 and op.key(running[0])==('2025-05-06','B3')
        worker=read(Path(running[0]['case_root'])/'START.json');assert alive(worker)
        before=read(op.STATE);committed=False
        coord.suspend()
        try:
            # Freeze only the scheduler, retaining its real OS locks and live
            # lease. Its independent B3 worker continues without interruption.
            atomic(TRANSITION,dict(UTC=now(),**process_identity(),phase='MATERIALIZING',coordinator=lease,preserved_worker={k:worker[k] for k in ('pid','process_created')}))
            result=subprocess.run([sys.executable,'-X','utf8',__file__,'--materialize'],cwd=Path(__file__).resolve().parents[2],check=True)
            job=read(JOB)
            from v44_recovery_r040.batch import check_ready, publish, status
            check_ready(job)
            state=read(op.STATE);assert state==before
            state['jobs']=[job if op.key(j)==op.key(job) else j for j in state['jobs']]
            atomic(op.OPS/'MAY07_B1_BATCH_BEFORE_REGISTRATION.json',before)
            publish(state);committed=True
            status(state,[(psutil.Process(worker['pid']),running[0])] if alive(worker) else [])
            atomic(RECEIPT,dict(UTC=now(),PASS=True,job=job,prepared_jobs=sum(j['status']=='PREPARED' for j in state['jobs']),
                  Native_optimizer_calls=0,Actual_executed=False,existing_A1_reused=True,
                  B3_worker_preserved={k:worker[k] for k in ('pid','process_created')},
                  coordinator_transition=str(TRANSITION),source=record(__file__)))
        finally:
            if not committed:coord.resume()
        # The old scheduler has a stale in-memory queue. Retire it only after
        # its solver exits naturally, then the existing r041 watchdog reads
        # the registered PREPARED state and reconciles the finished B3.
        while alive(worker):
            atomic(TRANSITION,dict(UTC=now(),**process_identity(),phase='WAITING_FOR_B3_NATURAL_EXIT',coordinator=lease,
                  preserved_worker={k:worker[k] for k in ('pid','process_created')},registered_job=record(JOB)))
            time.sleep(15)
        if alive(lease):coord.terminate();coord.wait(timeout=30)
        atomic(TRANSITION,dict(UTC=now(),**process_identity(),phase='STALE_COORDINATOR_RETIRED',B3_exited_naturally=True,
                              existing_r041_watchdog_resumes=True,Actual_auto_start_configuration_unchanged=True))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--materialize',action='store_true');args=parser.parse_args()
    try:materialize() if args.materialize else register()
    except BaseException as error:
        atomic(op.OPS/'MAY07_B1_METADATA_ERROR.json',dict(UTC=now(),error=repr(error),traceback=traceback.format_exc()))
        raise
