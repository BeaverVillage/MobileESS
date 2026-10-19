from pathlib import Path
import sys,psutil
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import v44_recovery_r025a
from v44.common import read,record,atomic,now
from v44.locks import alive
from v44_recovery_r025a.operations import validate
validate()
c=Path('D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/campaign004');ops=c/'AUTONOMOUS_RECOVERY'
assert read(ops/'STOP_AUTONOMY.json')['reason']=='R025B_USER_REQUESTED_PHASE1000_CURRENT_A2_CONTINUATION'
case=c/'2025-05-05/B0/attempt001';identity=read(case/'START.json')
assert read(case/'progress.json')['stage']=='ACTUAL_FRESH'
assert not (case/'RESULT.json').exists()
proc=psutil.Process(identity['pid']);assert alive(identity) and 'v44_recovery_r025a.operations' in proc.cmdline()
ledgers=list(case.rglob('*NATIVE*LEDGER.json'))
assert not ledgers,'REFERENCE_ACTUAL_ONLY_PRIORITY_BOUNDARY_REQUIRED'
interruption=dict(UTC=now(),user_requested=True,reason='R025B_USER_REQUESTED_MAY02_PHASE1000_PRIORITY_HOLD',
    classification='USER_REQUESTED_PRIORITY_HOLD',process_identity=identity,
    Gurobi_Native_calls=0,partial_Actual_preserved=True,completed_Actual_or_Fresh_PASS_claimed=False,
    resume_policy='NEW_ACTUAL_CONTEXT_AFTER_USER_PRIORITIZED_MAY02_B3_A2',
    stop_method='PID_CREATION_VERIFIED_ACTUAL_ONLY_PROCESS_TERMINATE_NO_GUROBI_LEDGER_OR_INFLIGHT')
atomic(case/'USER_INTERRUPTION.json',interruption)
proc.terminate();proc.wait(timeout=10)
atomic(case/'RESULT.json',dict(day='2025-05-05',arm='B0',PASS=False,status='FAILED',
    classification='USER_REQUESTED_PRIORITY_HOLD',error=interruption['reason'],finished_UTC=now(),
    interruption=record(case/'USER_INTERRUPTION.json')))
atomic(ops/'R025B_PRIORITY_HOLD.json',interruption)
print(dict(PASS=True,held_case=str(case),Gurobi_Native_calls=0))
