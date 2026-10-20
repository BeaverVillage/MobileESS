from pathlib import Path
import sys,time,psutil
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import v44_recovery_r024a
from v44.common import read,record,atomic,now,verify
from v44.checkpoints import ledger_state
from v44.locks import alive
from v44_recovery_r024a.operations import validate

validate()
C=Path('D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/campaign004');ops=C/'AUTONOMOUS_RECOVERY';case=C/'2025-05-02/B3/attempt007'
reason='R025_USER_REQUESTED_NATIVE60_PHASE400_UB_POLICY_STOP'
assert read(ops/'CURRENT_HANDOFF.json')['active_revision']=='v44_recovery_r024a'
baseline=read(ops/'R024A_PASS_AND_M1_PRESERVATION_BASELINE.json');verify(baseline['files'])
atomic(ops/'R025_PASS_AND_M1_PRESERVATION_BASELINE.json',baseline)
atomic(ops/'R025_USER_AUTHORIZATION.json',dict(UTC=now(),instruction='B1 and B3 A1/A2: total measured Native limit 3600 seconds; if Phase I remains unsolved at cumulative Native400, skip remaining Phase I and P1 and run original integer model; freeze independently physically verified best UB on time limit; never claim missing LB/gap; preserve completed PASS and M1, inherit current A2 Native without reset.'))
atomic(ops/'R025_PREVIOUS_HANDOFF_PRESERVED.json',read(ops/'CURRENT_HANDOFF.json'))
atomic(ops/'STOP_AUTONOMY.json',dict(UTC=now(),reason=reason,user_stop=True,scope='USER_AUTHORIZED_POLICY_HANDOVER_ONLY'))
identity=read(case/'START.json');proc=psutil.Process(identity['pid'])
assert alive(identity) and 'v44_recovery_r024a.operations' in proc.cmdline()
assert read(case/'progress.json')['stage']=='A2'
ledger=case/'A2/NATIVE_RUNTIME_LEDGER.json'
for _ in range(240):
    if read(ledger).get('inflight') is not None:time.sleep(.25);continue
    proc.suspend()
    try:
        if read(ledger).get('inflight') is not None:proc.resume();time.sleep(.25);continue
        account=ledger_state(ledger,ceiling=5400.)
        trace=read(case/'A2/OUTPUT/PHASE_I_TRACE.json')
        interruption=dict(UTC=now(),user_requested=True,classification='USER_REQUESTED_ALGORITHM_REVISION_STOP',reason=reason,
            Native_inflight=False,Native_account=account,old_worker={k:identity[k] for k in ('pid','process_created')},
            old_coordinator=read(C/'COORDINATOR_LEASE.json'),prior_ledger=record(ledger),
            trace=record(case/'A2/OUTPUT/PHASE_I_TRACE.json'),last_closed=[r for r in trace['trajectory'] if r['row_closed']][-1],
            stop_method='PID_CREATION_VERIFIED_SUSPEND_RECHECK_NO_NATIVE_THEN_TERMINATE_NO_EXTERNAL_IPC_IN_SEALED_WORKER',
            runtime_unsettled=False,Native_clock_reset=False,raw_and_ledgers_preserved=True)
        atomic(case/'USER_INTERRUPTION.json',interruption)
        proc.terminate();proc.wait(timeout=10)
        if not (case/'A2/RESULT.json').exists():atomic(case/'A2/RESULT.json',dict(PASS=False,classification='USER_REQUESTED_ALGORITHM_REVISION_STOP',error=reason,Native_seconds=account['measured']))
        if not (case/'RESULT.json').exists():atomic(case/'RESULT.json',dict(day='2025-05-02',arm='B3',PASS=False,status='FAILED',classification='USER_REQUESTED_ALGORITHM_REVISION_STOP',error=reason,finished_UTC=now()))
        atomic(ops/'R025_CURRENT_A2_STOPPED.json',interruption)
        assert record(ledger)==interruption['prior_ledger']
        print(dict(PASS=True,Native_seconds=account['measured'],calls=account['calls'],Native_clock_reset=False));break
    except BaseException:
        if proc.is_running():proc.resume()
        raise
else:raise RuntimeError('NO_SAFE_NATIVE_BOUNDARY_WORKER_NOT_TERMINATED')
