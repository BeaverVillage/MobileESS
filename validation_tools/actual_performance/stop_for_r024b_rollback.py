from pathlib import Path
import sys,time,psutil
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import v44_recovery_r025b
from v44.common import read,record,atomic,now,verify
from v44.locks import alive
from v44_recovery_r025b.operations import validate
validate()
c=Path('D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/campaign004');ops=c/'AUTONOMOUS_RECOVERY';case=c/'2025-05-02/B3/attempt009'
reason='R024B_USER_REQUESTED_RESTORE_R024A_NATIVE90_POLICY'
assert read(ops/'CURRENT_HANDOFF.json')['active_revision']=='v44_recovery_r025b'
atomic(ops/'R024B_USER_AUTHORIZATION.json',dict(UTC=now(),instruction='User explicitly cancels PhaseI400/1000 cutoff and Native3600/UB-only fallback, restores pre-change r024a (algorithm r024) with total A Native5400 and no separate PhaseI cutoff. Resume current May02 B3 A2 checkpoint and all prior Native costs; preserve completed PASS/A1/M1 and Raw.'))
atomic(ops/'R024B_PREVIOUS_HANDOFF_PRESERVED.json',read(ops/'CURRENT_HANDOFF.json'))
atomic(ops/'STOP_AUTONOMY.json',dict(UTC=now(),reason=reason,user_stop=True,scope='USER_AUTHORIZED_ROLLBACK_BOUNDARY_HOLD'))
identity=read(case/'START.json');proc=psutil.Process(identity['pid']);assert alive(identity)
assert 'v44_recovery_r025b.operations' in proc.cmdline() and read(case/'progress.json')['stage']=='A2'
ledger=case/'A2/NATIVE_RUNTIME_LEDGER.json'
for _ in range(240):
    account=read(ledger)
    if account.get('inflight') is not None:time.sleep(.25);continue
    proc.suspend()
    try:
        account=read(ledger)
        if account.get('inflight') is not None:proc.resume();time.sleep(.25);continue
        assert abs(sum(r.get('Native_Runtime') or 0 for r in account['calls'])-account['measured_Native_Runtime'])<1e-6
        interruption=dict(UTC=now(),user_requested=True,reason=reason,classification='USER_REQUESTED_ALGORITHM_REVISION_STOP',
            old_worker={k:identity[k] for k in ('pid','process_created')},old_coordinator=read(c/'COORDINATOR_LEASE.json'),
            Native_inflight=False,prior_ledger=record(ledger),measured=account['measured_Native_Runtime'],
            calls=len(account['calls']),Native_clock_reset=False,raw_and_previous_results_preserved=True,
            stop_method='PID_CREATION_VERIFIED_SUSPEND_RECHECK_NO_NATIVE_THEN_TERMINATE')
        atomic(case/'USER_INTERRUPTION.json',interruption);proc.terminate();proc.wait(timeout=10)
        for path in (case/'A2/RESULT.json',case/'RESULT.json'):
            if not path.exists():atomic(path,dict(day='2025-05-02',arm='B3',PASS=False,status='FAILED',classification=interruption['classification'],error=reason,Native_seconds=account['measured_Native_Runtime'],finished_UTC=now()))
        atomic(ops/'R024B_CURRENT_A2_STOPPED.json',interruption)
        assert record(ledger)==interruption['prior_ledger']
        print(dict(PASS=True,Native=account['measured_Native_Runtime'],calls=len(account['calls']),Native_clock_reset=False));break
    except BaseException:
        if proc.is_running():proc.resume()
        raise
else:raise RuntimeError('NO_SAFE_BOUNDARY_NO_TERMINATION')
