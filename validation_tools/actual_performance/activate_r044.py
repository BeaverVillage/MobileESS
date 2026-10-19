"""Seal tested recovery and arm a natural-boundary transition, without stopping a solver."""
import v44_recovery_r044
import os,sys,subprocess,json
from v44_recovery_r044 import operations as op
from v44.common import read,record,atomic,now

with op.week.bindings():
    op.sequence.authority();op.validate_parent()
    if op.PERMIT.exists() or op.sequence.STOP.exists():raise FileExistsError('EXISTING_AUTHORITY_OR_USER_STOP_PRESERVED')
    evidence=[record(op.PARENT/p) for p in ('RESULT.json','A2/RESULT.json','A2/request.json',
        'A2/NATIVE_RUNTIME_LEDGER.json','A2/OUTPUT/STATIC/P1_CLOSED_STATE.pkl.gz',
        'A2/OUTPUT/P1_FULL_DOMAIN_BOUND_CERTIFICATE.json','A2/OUTPUT/P1_RESULT.json',
        'A2/OUTPUT/P1/INTEGER_CONTROL/NATIVE_RESULT.json','M1/COMPLETED_STAGE_CHECKPOINT.json','M1/RESULT.json')]
    raw=read(op.PARENT/'A2/OUTPUT/P1/INTEGER_CONTROL/NATIVE_RESULT.json')['raw_attributes'];evidence.append(raw)
    atomic(op.PERMIT,dict(UTC=now(),explicit_user_approved=True,user_instruction='2026-10-19 user: 지금 5월 8일 B3 실패한 원인 찾아서 해결해.',
        target=str(op.TARGET),parent=str(op.PARENT),day='2025-05-08',arm='B3',sources=op.sources(),
        previous_authorization=record(op.sequence.AUTH),validation=record(op.VALIDATION),evidence=evidence,
        diagnosis='Exact saved integer decisions; tolerated original row residual makes UB fall below exact P1 certificate by 2.0491225083407727e-7.',
        repair='Reuse closed strict P1 and exact saved integers; independently solve continuous remainder with the proven redundant rho lower bound; replay every original row, physical check and strict exact LB<=UB gate.',
        M1_reoptimized=False,Native_clock_reset=False,A2_inherited_Native_seconds=12.59800386428833,A2_total_ceiling=5400.,
        original_tolerances_unchanged=True,main_prepare_workers=1,main_actual_workers=7,baseline_full_case_workers=1,
        healthy_preparations_preserved=True,active_solver_interrupted=False))
    with op.bindings():op.authority()
    atomic(op.sequence.STOP,dict(UTC=now(),reason=op.REASON,R044_authorization=record(op.PERMIT),
        operational_transition=True,operational_transition_only=True,active_worker_interrupted=False,user_stop=False))
    env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',NUMEXPR_NUM_THREADS='1')
    with (op.OPS/'r044_controller.log').open('ab') as stream:
        process=subprocess.Popen([sys.executable,'-X','utf8','-u','-m',op.ENTRY,'--transition'],
            cwd=op.week.RUNNER_ROOT,env=env,stdout=stream,stderr=stream,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    atomic(op.OPS/'R044_CONTROLLER_LAUNCH.json',dict(UTC=now(),pid=process.pid,process_created=__import__('psutil').Process(process.pid).create_time(),
        authorization=record(op.PERMIT),active_worker_interrupted=False))
    print(json.dumps(dict(PASS=True,pid=process.pid,authorization=record(op.PERMIT),pending_transition=True),indent=2))
