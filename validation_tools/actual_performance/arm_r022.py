from pathlib import Path
import sys,os,subprocess,psutil
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import v44_recovery_r022
from v44.common import read,record,atomic,now
from v44.locks import alive
from v44_recovery_r022.operations import OPS,CAMPAIGN,PERMIT,validate,workers
from v44_recovery_r022.handover import REASON
validate();assert not workers() and not alive(read(CAMPAIGN/'COORDINATOR_LEASE.json'))
assert read('D:/MobileESS_V44/development/r022/native_smoke/RESULT.json')['PASS']
h=read(OPS/'CURRENT_HANDOFF.json');assert h['active_revision']=='v44_recovery_r021' and h.get('pending_revision') is None
assert read(OPS/'STOP_AUTONOMY.json')['reason']==REASON
h.update(UTC=now(),pending_revision='v44_recovery_r022',pending_permit=record(PERMIT),
    pending_validation=record(OPS/'R022_CHANGE_AND_VALIDATION.json'),pending_regressions=read(OPS/'R022_CHANGE_AND_VALIDATION.json')['regressions'],
    pending_windows_task='MobileESS_V44_Campaign004_Recovery_R022',next_performance_revision='v44_recovery_r022',
    performance_revision_state='R022_SEALED_READY_MAY02_B3_A2_ROWGEN_NATIVE0',
    collector=str(OPS/'collect_watchdog_r022.py'),active_source_auditor=str(OPS/'audit_active_revision_r022.py'),
    latest_user_instruction='r022 row generation and bottleneck improvements; May02 B3 A2 fresh Native0, completed M1 reused. Common B1 A1 and B3 A2 routing; apply to future unstarted stages after pilot PASS.',
    next='May02 B3 attempt005 fresh A2 at S0; no A1/M1 recomputation; then K48_M2 M2 Actual Fresh; preserve every earlier PASS.')
atomic(OPS/'CURRENT_HANDOFF.json',h)
root=Path(__file__).resolve().parents[2]
with (OPS/'r022_handover.log').open('ab') as stream:
    proc=subprocess.Popen([sys.executable,'-X','utf8','-u','-m','v44_recovery_r022.operations','--handover'],cwd=root,
        stdin=subprocess.DEVNULL,stdout=stream,stderr=stream,env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1'),creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
atomic(OPS/'R022_HANDOVER_START.json',dict(UTC=now(),pid=proc.pid,process_created=psutil.Process(proc.pid).create_time(),permit=record(PERMIT),adapter_source_root=str(root)))
print(dict(PASS=True,pid=proc.pid,adapter_source_root=str(root)))
