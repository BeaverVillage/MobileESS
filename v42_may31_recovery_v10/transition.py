"""Versioned handoff of one explicit failed date; prior files remain immutable."""
from copy import deepcopy
from pathlib import Path
import shutil
import subprocess
from xml.etree import ElementTree as ET
from .common import ROOT, read, record, atomic, now, sha, digest, same_process


def admit(root, validation):
    from .policy import (VERSION, BUILD_VERSION, MANIFEST, ATTEMPT, PRECISION,
                         DAYS, RETRY_DATES, source_files, verify_policy)
    from .storage import initialize_checkpoint
    from v42_may25_recovery_v9.policy import verify_policy as verify_previous
    from v42_may25_recovery_v9.coordinator import read_actives
    root = Path(root).resolve()
    if (root / MANIFEST).exists():
        return verify_policy(root)
    if (not (root/'HOLD_V9.json').is_file()
            or same_process(read(root/'COORDINATOR_V9_HOST.json')['process'])
            or any(same_process(a.get('worker', {})) for a in read_actives(root).values())):
        raise PermissionError('V10_REQUIRES_STOPPED_PREVIOUS_COORDINATOR_AND_WORKERS')
    state = root/'B2_BUILD_FULL_VALIDATION_V9.json'
    if state.exists() and same_process((read(state).get('active') or {}).get('process', {})):
        raise PermissionError('V10_REQUIRES_PREVIOUS_NATIVE_ZERO_BUILD_EXIT')
    previous = verify_previous(root)
    for receipt in validation.values():
        if record(receipt['path']) != receipt or read(receipt['path']).get('PASS') is not True:
            raise PermissionError('V10_VALIDATION_GATE_NOT_PASS')
    boundary = root/'BASE_CHECKPOINT_BOUNDARY_V10.json'
    if boundary.exists():
        raise PermissionError('V10_BOUNDARY_ALREADY_EXISTS')
    checkpoint = read(root/'CHECKPOINT_V9.json')
    if any(row['arm']=='B2' and row['status']!='PENDING' for row in checkpoint['dates'].values()):
        raise PermissionError('V10_CANNOT_REPLACE_STARTED_B2_DATES')
    row = checkpoint['dates']['B1/2025-05-31']
    if row['status']=='PASS' or sha(row['result']) != row['result_SHA']:
        raise PermissionError('V10_FAILED_DATE_RECEIPT_REQUIRED')
    prior_ledger = record(Path(row['result']).parent/'NATIVE_RUNTIME_LEDGER.json')
    shutil.copyfile(root/'CHECKPOINT_V9.json', boundary)
    doc = deepcopy(previous)
    doc.pop('may26_stop', None)
    doc.update(schema=VERSION, continuation_version=VERSION, attempt_id=ATTEMPT,
        precision=PRECISION, precision_dates=sorted(DAYS), phase_I_presolve=0,
        precision_components=['INTEGER_CONTROL', 'ORIGINAL_P1', 'PHASE_I'],
        previous_manifest=record(root/'CONTINUATION_V9_MANIFEST.json'),
        base_checkpoint=record(boundary), retry_authority=record(root/'HOLD_V9.json'),
        prior_native_ledger=prior_ledger, authorized_recovery_dates=list(RETRY_DATES),
        input_cache_sources={}, implementation=dict(version=BUILD_VERSION,
            sources=source_files(), source_SHA=digest(source_files())), validation=validation,
        tasks={role:'MobileESS_V42_B1B2_P1_'+previous['run_id']+'_RecoveryV10_'+role.title()
               for role in ('coordinator','monitor','watchdog')},
        source_HEAD=subprocess.check_output(['git','rev-parse','HEAD'], cwd=ROOT, text=True).strip(),
        source_transition=dict(user_authorized=True, recovery_order=list(RETRY_DATES),
            completed_PASS_resets=0, automatic_failed_date_retries=0,
            prior_Native_Runtime_preserved=True, date_runtime_reset=False,
            acceptance_tolerance_changed=False, Heuristics=.05, built_in_heuristics_enabled=True,
            original_Method=2, scientific_LB_UB_conflict_not_clamped=True), UTC=now())
    atomic(root/MANIFEST, doc)
    verify_policy(root)
    initialize_checkpoint(root, doc)
    return doc


def activate(root):
    from .policy import verify_policy
    from .windows import register_campaign_tasks, run_task, powershell, NS
    import psutil
    root = Path(root).resolve()
    doc = verify_policy(root)
    previous = read(root/'CONTINUATION_V9_MANIFEST.json')
    disabled = []
    for role, name in previous['tasks'].items():
        exported = powershell("Export-ScheduledTask -TaskName '"+name+"'")
        task = ET.fromstring(exported)
        args = task.find('.//{'+NS+'}Arguments').text
        expected = subprocess.list2cmdline(['-B','-X','utf8','-m','v42_may25_recovery_v9.host',role,str(root)])
        if args != expected:
            raise PermissionError('V10_CANNOT_DISABLE_UNRELATED_TASK:'+name)
        saved = root/(name+'_BEFORE_V10.xml')
        if not saved.exists():
            saved.write_text(exported,encoding='utf-8',newline='\n')
        powershell("Disable-ScheduledTask -TaskName '"+name+"' | Out-Null")
        disabled.append(dict(name=name, preserved_definition=record(saved)))
    monitor = root/'MONITOR_PROCESS.json'
    if monitor.exists():
        identity = read(monitor)
        if same_process(identity):
            args = identity['command']
            if ('v42_may25_recovery_v9.host' not in args or 'monitor' not in args
                    or Path(args[-1]).resolve()!=root):
                raise PermissionError('V10_ONLY_EXACT_OWN_MONITOR_MAY_BE_REPLACED')
            atomic(root/'MONITOR_V9_BEFORE_V10.json', identity)
            peer=psutil.Process(identity['PID']);peer.terminate();peer.wait(timeout=10)
    registration=register_campaign_tasks(root, doc)
    started={role:run_task(doc['tasks'][role]) for role in ('monitor','coordinator','watchdog')}
    value=dict(UTC=now(), registration=registration, started=started,
        replaced_tasks=disabled, healthy_Native_worker_kills=0, prior_source_files_changed=0,
        logoff_persistence='LOGOFF_PERSISTENCE_NOT_PROVEN')
    atomic(root/'SOURCE_TRANSITION_ACTIVATION_V10.json', value)
    return value
