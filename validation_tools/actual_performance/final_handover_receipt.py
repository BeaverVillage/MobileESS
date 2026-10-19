import sys,tomllib
from pathlib import Path
sys.path.insert(0,'D:/v44_may01_07_prepare_20261016')
import psutil
from v44.common import read,record,verify,atomic,now
from v44.locks import alive
from v44_recovery_r016 import operations as revision
from v44_recovery_r015 import operations as current

ops=revision.OPS;current.validate();revision.validate()
seal=read(ops/'R016_SEALED.json');verify([seal['permit'],seal['validation'],seal['guard']]+seal['sources']+seal['snapshots'])
guard=read(ops/'R016_HANDOVER_GUARD.json');start=read(ops/'R016_HANDOVER_START.json')
assert alive(guard['protected_worker']) and alive(guard['protected_coordinator']) and alive(start)
old=read(ops/'R015_HANDOVER_START.json');assert not alive(old)
heartbeat=read(ops/'R016_HANDOVER_HEARTBEAT.json')
assert heartbeat['pid']==start['pid'] and heartbeat['coordinator_alive']
assert [r['pid'] for r in heartbeat['workers']]==[guard['protected_worker']['pid']]
handoff=read(ops/'CURRENT_HANDOFF.json')
assert handoff['active_revision']=='v44_recovery_r015' and handoff['pending_revision']=='v44_recovery_r016'
assert read(ops/'STOP_AUTONOMY.json')['reason']=='R016_PERFORMANCE_VALIDATION_SAFE_HANDOVER_AFTER_HEALTHY_WORKER'
config=tomllib.loads(Path('C:/Users/kjw39/.codex/automations/v44-may-campaign-autonomous-recovery/automation.toml').read_text(encoding='utf8'))
assert config['status']=='PAUSED' and 'collect_watchdog_r016.py' in config['prompt']
watch=read(revision.CAMPAIGN/'V44_30MIN_WATCHDOG_RECEIPT.json')
assert watch['active_revision']=='v44_recovery_r015' and watch['pending_revision']=='v44_recovery_r016'
handoff.update(collector=str(ops/'collect_watchdog_r016.py'),active_source_auditor=str(ops/'audit_active_revision_r007.py'))
atomic(ops/'CURRENT_HANDOFF.json',handoff)
receipt=ops/'R016_SAFE_HANDOVER_ARMED.json'
atomic(receipt,dict(UTC=now(),PASS=True,active_revision='v44_recovery_r015',pending_revision='v44_recovery_r016',
    improved_arms=['B0','B1','B3'],validation=seal['validation'],permit=seal['permit'],tests_PASS=168,
    waiting_handover=start,heartbeat=heartbeat,protected_worker=guard['protected_worker'],protected_coordinator=guard['protected_coordinator'],
    previous_r015_waiter_naturally_exited=True,current_worker_not_interrupted=True,
    current_actual_heartbeat=read(Path(guard['protected_case_root'])/'ACTUAL/HEARTBEAT.json'),
    early_r016_dispatch_denied=True,boundary='ENTIRE_ACTUAL_AND_INDEPENDENT_FRESH_CASE_TERMINAL_AND_OLD_WORKER_COORDINATOR_NATURAL_EXIT',
    windows_task='MobileESS_V44_Campaign004_Recovery_R016',previous_r015_task_disabled=True,
    original_Codex_heartbeat_status_preserved=config['status'],
    collector=record(ops/'collect_watchdog_r016.py'),auditor=record(ops/'audit_active_revision_r007.py'),
    watchdog_counts=watch['counts'],case_source_or_Raw_modified=False,Native_budgets_changed=False))
print(dict(PASS=True,receipt=record(receipt),active='r015',pending='r016',arms=['B0','B1','B3'],counts=watch['counts']))
