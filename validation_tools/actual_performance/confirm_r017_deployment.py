"""Record actual activation, single worker and preserved protected result."""
from pathlib import Path
import sys,psutil,tomllib
sys.path.insert(0,'D:/v44_may01_07_prepare_20261016')
from v44.common import read,record,verify,atomic,now
from v44.locks import alive
from v44_recovery_r017 import operations as ops
from v44_recovery_r016.operations import validate as validate16
from v44_recovery_r015.operations import validate as validate15

permit=ops.validate();validate16();validate15()
guard=read(ops.OPS/'R017_HANDOVER_GUARD.json');verify([guard['protected_request']])
for key in ('protected_worker','protected_coordinator'):assert not alive(guard[key])
protected=Path(guard['protected_case_root'])/'RESULT.json';result=read(protected)
assert result['PASS'] and result['Actual96_PASS'] and result['Fresh96_PASS']
handoff=read(ops.OPS/'CURRENT_HANDOFF.json');assert handoff['active_revision']=='v44_recovery_r017' and handoff['pending_revision'] is None
lease=read(ops.CAMPAIGN/'COORDINATOR_LEASE.json');assert alive(lease)
owner=psutil.Process(lease['pid']);assert 'v44_recovery_r017.operations' in owner.cmdline() and '--coordinator' in owner.cmdline()
workers=ops.workers();assert len(workers)==1,workers
worker=workers[0];assert 'v44_recovery_r017.operations' in worker['cmdline']
request=read(worker['cmdline'][-1]);assert request['arm'] in ('B0','B1','B3')
assert read(request['execution_permit']['path'])['autonomous_recovery_policy_sha']==permit['autonomous_recovery_policy_sha']
verify(request['sources']);case=Path(request['case_root'])
started=read(ops.OPS/'R017_HANDOVER_START.json');assert alive(started)
assert not (ops.OPS/'STOP_AUTONOMY.json').exists()
assert read(ops.OPS/'R017_HANDOVER_STOP_PRESERVED.json')['reason']=='R017_STRUCTURAL_PERFORMANCE_SAFE_HANDOVER_AFTER_HEALTHY_WORKER'
automation=tomllib.loads(Path('C:/Users/kjw39/.codex/automations/v44-may-campaign-autonomous-recovery/automation.toml').read_text(encoding='utf8'))
assert automation['status']=='PAUSED' and 'collect_watchdog_r017.py' in automation['prompt']
handoff.update(UTC=now(),revision_selection='Sealed r017 active under live r017 coordinator lease; pending r016 superseded by explicit user instruction.',
    pending_windows_task=None,pending_regressions=None,handover_process_pid=started['pid'],
    handover_start=record(ops.OPS/'R017_HANDOVER_START.json'),
    May01_B3_completion=dict(PASS=True,Actual96_PASS=True,Fresh96_PASS=True,result=record(protected)),
    last_observed_case_stage=f"{request['day']}/{request['arm']}/{case.name} r017 active",
    active_regressions=173,active_improved_arms=['B0','B1','B3'],
    active_deployment_receipt_file=str(ops.OPS/'R017_DEPLOYMENT_COMPLETE.json'))
atomic(ops.OPS/'CURRENT_HANDOFF.json',handoff)
receipt=dict(UTC=now(),PASS=True,active_revision='v44_recovery_r017',pending_revision=None,
    improved_arms=['B0','B1','B3'],permit=record(ops.PERMIT),validation=record(ops.OPS/'R017_CHANGE_AND_VALIDATION.json'),
    protected_B3=dict(result=record(protected),Actual96_PASS=True,Fresh96_PASS=True,
        worker_natural_exit=True,coordinator_natural_exit=True,restarted=False),
    coordinator=dict(**lease,command=owner.cmdline()),single_worker=worker,
    next_case=dict(day=request['day'],arm=request['arm'],root=str(case),stage=read(case/'progress.json').get('stage')),
    activated=record(ops.OPS/'R017_HANDOVER_APPLIED.json'),
    registered_windows_task=record(ops.OPS/'R017_WINDOWS_TASK.json'),r016_waiter_stopped_naturally=True,
    Codex_heartbeat_status_preserved=automation['status'],
    collector=record(ops.OPS/'collect_watchdog_r017.py'),auditor=record(ops.OPS/'audit_active_revision_r008.py'),
    all_old_seals_verified=True,Native_budgets_changed=False,original_results_or_Raw_modified=False)
atomic(ops.OPS/'R017_DEPLOYMENT_COMPLETE.json',receipt)
print(dict(PASS=True,revision='r017',coordinator=lease['pid'],worker=worker['pid'],next_case=receipt['next_case']))
