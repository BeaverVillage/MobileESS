import v44_recovery_r045
import v44_week2_restart_r045a as entry
from v44_recovery_r045 import operations as op
from v44.common import read,record,atomic,now
from v44.locks import alive,process_identity
from pathlib import Path
import os,sys,subprocess,json

with op.bindings(),entry.install(validate=False):
    if entry.AUTH.exists() or alive(read(op.STATE).get('lease')) or op.seq.STOP.exists():raise PermissionError('R045A_EXISTING_AUTHORITY_OR_ACTIVE_OWNER')
    before=record(op.STATE)
    adopted=op.restore_state(dict(**process_identity(),preflight_only=True))
    assert record(op.STATE)==before
    assert sum(j['status']=='PREPARED' for j in adopted['jobs'])==3
    assert sum(j['status']=='PENDING' for j in adopted['jobs'])==11
    assert sum(j['status']=='BASELINE_QUEUED' for j in adopted['jobs'])==14
    for j in adopted['jobs']:
        if j['status']=='PREPARED':
            r=read(j['prepare_request']);assert r['sequence_mode']=='MAIN' and r['sequence_authorization']==record(op.seq.AUTH)
            h=read(j['handoff']['path']);assert h['source_sha']==r['source_sha'] and h['sources']==r['sources']
    validation=op.OPS/'R045A_FULL_STATE_ADOPTION_VALIDATION.json'
    atomic(validation,dict(PASS=True,UTC=now(),Native_calls=0,actual_restore_state_executed=True,
        original_state_unchanged=True,prepared_handoffs_revalidated=3,pending_main=11,baseline_queued=14,
        handoff_sources_and_SHA_unchanged=True,source=record(entry.__file__)))
    atomic(entry.AUTH,dict(UTC=now(),explicit_user_approved=True,source=record(entry.__file__),
        previous_authorization=record(op.PERMIT),validation=record(validation),
        diagnosis='May08 B1 preparation predates the sequence dispatch authorization. Attach current dispatch labels while preserving the original prepared source manifest and SHA.'))
    log=op.OPS/'R045_CONTROLLER_ERROR.json'
    if log.exists():log.rename(op.OPS/'R045A_PREVIOUS_STARTUP_ERROR_PRESERVED.json')
    env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',NUMEXPR_NUM_THREADS='1')
    with (op.OPS/'r045a_controller.log').open('ab') as stream:
        p=subprocess.Popen([sys.executable,'-X','utf8','-u','-m',entry.ENTRY,'--run'],cwd=op.week.RUNNER_ROOT,
            env=env,stdout=stream,stderr=stream,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    atomic(op.OPS/'R045A_CONTROLLER_LAUNCH.json',dict(UTC=now(),pid=p.pid,process_created=__import__('psutil').Process(p.pid).create_time(),authorization=record(entry.AUTH)))
    print(json.dumps(dict(PASS=True,pid=p.pid,adoption_validated=28)))
