"""Arm an independent waiter; do not interrupt the protected live case."""
from pathlib import Path
import os,sys,subprocess,psutil
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from v44.common import read,record,atomic,now
from v44_recovery_r020.operations import OPS,PERMIT,ROOT,validate,workers
from v44_recovery_r020.handover import REASON
validate()
value=read(OPS/'CURRENT_HANDOFF.json');assert value['active_revision']=='v44_recovery_r019' and value.get('pending_revision') is None
assert read(OPS/'STOP_AUTONOMY.json')['reason']==REASON
guard=read(OPS/'R020_HANDOVER_GUARD.json')
active=workers()
if active:
    assert len(active)==1 and active[0]['pid']==guard['protected_worker']['pid']
    assert abs(active[0]['create_time']-guard['protected_worker']['process_created'])<.001
value.update(UTC=now(),latest_user_instruction='병목 개선해서 다음 날짜부터 실행. B1 B3 A2 단계 모두에 적용.',
    pending_revision='v44_recovery_r020',pending_permit=record(PERMIT),pending_validation=record(OPS/'R020_CHANGE_AND_VALIDATION.json'),
    pending_windows_task='MobileESS_V44_Campaign004_Recovery_R020',pending_regressions=193,
    dispatch_hold_reason=REASON,next_performance_revision='v44_recovery_r020',
    performance_revision_state='R020_SEALED_WAITING_FOR_MAY02_B3_ENTIRE_CASE',
    collector=str(OPS/'collect_watchdog_r020.py'),active_source_auditor=str(OPS/'audit_active_revision_r011.py'),
    effective_from_day='2025-05-03',B1_A2_performance_enabled=True,B3_A2_performance_enabled=True,
    next='Keep May02 B3 r019 untouched; after the entire case and natural owner exit switch to r020 for remaining May03+ cases including B1/B3 A2.')
atomic(OPS/'CURRENT_HANDOFF.json',value)
with (OPS/'r020_handover.log').open('ab') as stream:
    proc=subprocess.Popen([sys.executable,'-X','utf8','-u','-m','v44_recovery_r020.operations','--handover'],
        cwd=ROOT,stdin=subprocess.DEVNULL,stdout=stream,stderr=stream,
        env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1'),creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
started=dict(UTC=now(),pid=proc.pid,process_created=psutil.Process(proc.pid).create_time(),permit=record(PERMIT),
    guard=record(OPS/'R020_HANDOVER_GUARD.json'),protected_case_interrupted=False,effective_from_day='2025-05-03',B1_A2=True,B3_A2=True)
atomic(OPS/'R020_HANDOVER_START.json',started);print(started)
