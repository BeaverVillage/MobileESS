"""Explicit user restart, only between measured Native calls; preserve all ledgers."""
from pathlib import Path
import sys,time,psutil
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from v44.common import read,record,atomic,now
from v44.checkpoints import ledger_state
from v44.locks import alive

C=Path('D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/campaign004')
OPS=C/'AUTONOMOUS_RECOVERY';case=C/'2025-05-02/B3/attempt004'
reason='R022_MAY02_B3_FRESH_A2_ROWGEN_RESTART'
assert read(OPS/'CURRENT_HANDOFF.json')['active_revision']=='v44_recovery_r021'
protected=[record(p) for p in C.glob('2025-*/*/attempt*/RESULT.json') if read(p).get('PASS')]
protected += [record(p) for p in (C/'2025-05-02/B3/attempt001').glob('M1/**/*') if p.is_file()]
atomic(OPS/'R022_PASS_AND_M1_PRESERVATION_BASELINE.json',dict(UTC=now(),files=protected))
atomic(OPS/'R022_USER_AUTHORIZATION.json',dict(UTC=now(),instruction='Improve r021 as r022; May02 B3 A2 fresh from completed M1, Native0; preserve PASS; finish M2 Actual Fresh; commit push PR233',
    pasted_instruction=record('C:/Users/kjw39/.codex/attachments/fc1ab8b3-adef-4cbf-bb42-bbf404697d4f/붙여넣은 텍스트.txt')))
atomic(OPS/'STOP_AUTONOMY.json',dict(UTC=now(),reason=reason,user_stop=True,scope='NEW_DISPATCH_HOLD_CURRENT_A2_SAFE_BOUNDARY_ONLY'))
identity=read(case/'START.json');process=psutil.Process(identity['pid'])
assert alive(identity) and 'v44_recovery_r021.operations' in process.cmdline()
assert read(case/'progress.json').get('stage')=='A2'
path=case/'A2/NATIVE_RUNTIME_LEDGER.json'
for _ in range(240):
    if read(path).get('inflight') is not None:time.sleep(.25);continue
    process.suspend()
    try:
        if read(path).get('inflight') is not None:
            process.resume();time.sleep(.25);continue
        account=ledger_state(path,ceiling=5400.)
        interruption=dict(UTC=now(),user_requested=True,reason=reason,Native_inflight=False,Native_account=account,
            old_worker=identity,checkpoint_parent=str(C/'2025-05-02/B3/attempt001'),raw_and_ledgers_preserved=True)
        atomic(case/'USER_INTERRUPTION.json',interruption)
        process.terminate();process.wait(timeout=10)
        stage=case/'A2/RESULT.json'
        if not stage.exists():atomic(stage,dict(PASS=False,status='USER_REQUESTED_RESTART',classification='USER_REQUESTED_RESTART',
            error=reason,Native_seconds=account['measured'],interruption=record(case/'USER_INTERRUPTION.json')))
        result=case/'RESULT.json'
        if not result.exists():atomic(result,dict(day='2025-05-02',arm='B3',PASS=False,status='FAILED',error=reason,finished_UTC=now(),interruption=record(case/'USER_INTERRUPTION.json')))
        atomic(OPS/'R022_CURRENT_A2_STOPPED.json',interruption)
        print(dict(PASS=True,stopped_pid=process.pid,Native_seconds=account['measured'],calls=account['calls'],remaining=account['remaining']))
        break
    except BaseException:
        if process.is_running():process.resume()
        raise
else:raise RuntimeError('NO_SAFE_BOUNDARY_WITHIN_ONE_MINUTE_NO_WORKER_KILLED')
