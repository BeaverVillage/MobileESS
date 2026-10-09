"""Read-only proof of actual recovery dispatch, clocks, OS ownership and UI."""
import json,urllib.request
from pathlib import Path
from v42_pr134_b1.common import read,sha,atomic,now,same_process
from v42_may_recovery_v5.policy import verify_policy
from v42_may_recovery_v5.windows import scheduler_process_evidence
from v42_may_recovery_v5.coordinator import read_actives
from .preflight import RUN,DOC


def main():
    manifest=verify_policy(RUN)
    active=read_actives(RUN).get('B1/2025-05-11')
    if not active:
        print(json.dumps(dict(PASS=False,status='RECOVERY_WORKER_NOT_YET_OBSERVED')));return
    request=read(active['request']);attempt=Path(active['request']).parent
    heartbeat=read(attempt/'HEARTBEAT.json')
    ledger=read(attempt/'NATIVE_RUNTIME_LEDGER.json')
    snapshot=json.loads(urllib.request.urlopen('http://127.0.0.1:8793/api/status',timeout=15).read())
    preserved=all(sha(receipt['path'])==receipt['sha256'] for row in manifest['inherited_original_attempts'].values()
                  for receipt in (row['result'],row['ledger']))
    ownership={name:scheduler_process_evidence(identity) for name,identity in dict(
        Coordinator=read(RUN/'COORDINATOR_V5_HOST.json')['process'],
        Worker=active['worker'],Monitor=read(RUN/'MONITOR_V5_HOST.json')['process']).items()}
    live=same_process(active['worker'])
    calls=ledger['calls'];runtime=sum(c['Native_Runtime'] for c in calls)
    monitor=[w for w in snapshot['workers'] if w['day']=='2025-05-11' and w['arm']=='B1']
    passed=live and preserved and all(v['PASS'] for v in ownership.values()) and len(monitor)==1
    passed=passed and monitor[0]['PID']==active['worker']['PID'] and runtime==ledger['measured_Native_Runtime']
    checkpoint=read(RUN/'CHECKPOINT_V5.json')
    report=dict(PASS=passed,UTC=now(),Native_calls_by_observer=0,
        actual_recovery_worker=active,request_SHA=sha(active['request']),
        input_SHA=sha(Path(request['input_folder'])/'NATIVE_INPUT.json'),
        Heartbeat=heartbeat,completed_Native_calls=len(calls),completed_Native_Runtime=runtime,
        Native_status='OBSERVED' if calls else 'NOT_YET_CALLED_MODEL_CONSTRUCTION',
        OS_ownership=ownership,original_results_and_ledgers_unchanged=preserved,
        current_queue={day:checkpoint['dates']['B1/'+day]['status'] for day in ('2025-05-11','2025-05-19','2025-05-22','2025-05-23')},
        May22_original_PASS=checkpoint['dates']['B1/2025-05-22']['status']=='PASS',
        B2_three_workers_after_all_B1_terminal=True,additional_automatic_date_retries=0,
        production_recovery_terminal_status='NOT_YET_OBSERVED',
        real_B1_to_B2_transition_status='NOT_YET_OBSERVED',
        monitor_URL='http://127.0.0.1:8793/',monitor_algorithm_version=snapshot['algorithm_version'],
        monitor_worker={k:monitor[0].get(k) for k in ('day','PID','phase','Native_Runtime_seconds','native_remaining_seconds','Native_calls','heartbeat_age_seconds','input_SHA')} if monitor else None,
        logoff_persistence='LOGOFF_PERSISTENCE_NOT_PROVEN')
    atomic(DOC/'DEPLOYMENT_VERIFICATION.json',report)
    print(json.dumps({k:report[k] for k in ('PASS','current_queue','Native_status','completed_Native_calls','completed_Native_Runtime','monitor_worker')}))


if __name__=='__main__':main()
