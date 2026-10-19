from pathlib import Path
import sys,os,subprocess,psutil
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import v44_recovery_r025
from v44.common import read,record,atomic,now
from v44.locks import alive
from v44_recovery_r025.operations import OPS,CAMPAIGN,PERMIT,validate,workers
from v44_recovery_r025.handover import REASON

validate();assert not workers() and not alive(read(CAMPAIGN/'COORDINATOR_LEASE.json'))
h=read(OPS/'CURRENT_HANDOFF.json');assert h['active_revision']=='v44_recovery_r024a' and h.get('pending_revision') is None
assert read(OPS/'STOP_AUTONOMY.json')['reason']==REASON
h.update(UTC=now(),pending_revision='v44_recovery_r025',pending_permit=record(PERMIT),
    pending_validation=record(OPS/'R025_CHANGE_AND_VALIDATION.json'),pending_regressions=read(OPS/'R025_CHANGE_AND_VALIDATION.json')['regressions'],
    pending_windows_task='MobileESS_V44_Campaign004_Recovery_R025',next_performance_revision='v44_recovery_r025',
    performance_revision_state='R025_SEALED_NATIVE60_PHASE400_VERIFIED_UB_READY',
    unconditional_future_B1_B3=True,pilot_PASS_required=False,effective_from_day='2025-05-02',
    latest_user_instruction='B1/B3 A1/A2 total measured Native3600, Phase I cutoff400, skip Phase I/P1 when not zero; original integer search and independently verified UB freeze on timeout; inherit current Native342.117.',
    next='Current May02 B3 A2 attempt008 Native continuation then original M2 Actual Fresh; all unstarted B1/B3 A stages same policy.')
atomic(OPS/'CURRENT_HANDOFF.json',h)
with (OPS/'r025_handover.log').open('ab') as stream:
    p=subprocess.Popen([sys.executable,'-X','utf8','-u','-m','v44_recovery_r025.operations','--handover'],cwd=Path(__file__).resolve().parents[2],
        stdin=subprocess.DEVNULL,stdout=stream,stderr=stream,env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1'),creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
atomic(OPS/'R025_HANDOVER_START.json',dict(UTC=now(),pid=p.pid,process_created=psutil.Process(p.pid).create_time(),permit=record(PERMIT)))
print(dict(PASS=True,pid=p.pid))
