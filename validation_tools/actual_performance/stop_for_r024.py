from pathlib import Path
import sys,time,psutil
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import v44_recovery_r022
from v44.common import read,record,atomic,now,verify
from v44.checkpoints import ledger_state
from v44.locks import alive
from v44_recovery_r022.operations import validate
validate()
C=Path('D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/campaign004');OPS=C/'AUTONOMOUS_RECOVERY';case=C/'2025-05-02/B3/attempt005'
reason='R024_USER_REQUESTED_ALGORITHM_REVISION_STOP'
assert read(OPS/'CURRENT_HANDOFF.json')['active_revision']=='v44_recovery_r022'
verify(read(OPS/'R022_PASS_AND_M1_PRESERVATION_BASELINE.json')['files'])
atomic(OPS/'R024_PASS_AND_M1_PRESERVATION_BASELINE.json',read(OPS/'R022_PASS_AND_M1_PRESERVATION_BASELINE.json'))
atomic(OPS/'R024_USER_AUTHORIZATION.json',dict(UTC=now(),instruction='r024 Adaptive Multi-Column Pricing; stop current May02 B3 A2, preserve all PASS and completed A1/M1, fresh A2 Native0/5400; unconditional common B1/B3 A stages; continue M2 Actual Fresh',
 pasted_instruction=record('C:/Users/kjw39/.codex/attachments/a65198ba-0e62-43ff-81fa-6b215640d498/붙여넣은 텍스트.txt')))
atomic(OPS/'R024_PREVIOUS_HANDOFF_PRESERVED.json',read(OPS/'CURRENT_HANDOFF.json'))
atomic(OPS/'R024_PREVIOUS_STOP_PRESERVED.json',read(OPS/'STOP_AUTONOMY.json'))
atomic(OPS/'STOP_AUTONOMY.json',dict(UTC=now(),reason=reason,user_stop=True,scope='ONLY_TARGET_A2_USER_AUTHORIZED_REVISION_HOLD_NO_OLD_RESTART'))
identity=read(case/'START.json');proc=psutil.Process(identity['pid'])
assert alive(identity) and 'v44_recovery_r022.operations' in proc.cmdline()
assert read(case/'progress.json')['stage']=='A2'
ledger=case/'A2/NATIVE_RUNTIME_LEDGER.json'
for _ in range(240):
 if read(ledger).get('inflight') is not None:time.sleep(.25);continue
 proc.suspend()
 try:
  if read(ledger).get('inflight') is not None:proc.resume();time.sleep(.25);continue
  account=ledger_state(ledger,ceiling=5400.)
  trace=read(case/'A2/OUTPUT/PHASE_I_TRACE.json');closed=[r for r in trace['trajectory'] if r['row_closed']]
  interruption=dict(UTC=now(),user_requested=True,classification='USER_REQUESTED_ALGORITHM_REVISION_STOP',reason=reason,
   Native_inflight=False,Native_account=account,old_worker={k:identity[k] for k in ('pid','process_created')},
   last_closed=closed[-1],LP_solves=len(trace['trajectory']),activations=trace['activation_rounds'],
   prior_ledger=record(ledger),trace=record(case/'A2/OUTPUT/PHASE_I_TRACE.json'),raw_and_ledgers_preserved=True,
   stop_method='EXTERNAL_IPC_STOP_NOT_AVAILABLE_IN_SEALED_WORKER; PID_CREATE_VERIFIED_SUSPEND_RECHECK_NO_NATIVE_THEN_PROCESS_TERMINATE',
   runtime_unsettled=False)
  atomic(case/'USER_INTERRUPTION.json',interruption)
  proc.terminate();proc.wait(timeout=10)
  if not (case/'A2/RESULT.json').exists():atomic(case/'A2/RESULT.json',dict(PASS=False,status='USER_REQUESTED_RESTART',classification='USER_REQUESTED_ALGORITHM_REVISION_STOP',error=reason,Native_seconds=account['measured'],interruption=record(case/'USER_INTERRUPTION.json')))
  if not (case/'RESULT.json').exists():atomic(case/'RESULT.json',dict(day='2025-05-02',arm='B3',PASS=False,status='FAILED',classification='USER_REQUESTED_ALGORITHM_REVISION_STOP',error=reason,finished_UTC=now(),interruption=record(case/'USER_INTERRUPTION.json')))
  atomic(OPS/'R024_CURRENT_A2_STOPPED.json',interruption)
  assert record(ledger)==interruption['prior_ledger']
  print(dict(PASS=True,pid=proc.pid,Native_seconds=account['measured'],calls=account['calls'],last_Phi=closed[-1]['Phi'],inflight=False))
  break
 except BaseException:
  if proc.is_running():proc.resume()
  raise
else:raise RuntimeError('NO_SAFE_BOUNDARY_WITHIN_60_SECONDS_NO_PROCESS_TERMINATED')
