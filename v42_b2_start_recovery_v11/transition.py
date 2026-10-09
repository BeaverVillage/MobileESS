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
    from v42_may31_recovery_v10.policy import verify_policy as verify_previous
    from v42_may31_recovery_v10.coordinator import read_actives
    root = Path(root).resolve()
    if (root / MANIFEST).exists():
        return verify_policy(root)
    if (not (root/'HOLD_V10.json').is_file()
            or same_process(read(root/'COORDINATOR_V10_HOST.json')['process'])
            or any(same_process(a.get('worker', {})) for a in read_actives(root).values())):
        raise PermissionError('V11_REQUIRES_STOPPED_PREVIOUS_COORDINATOR_AND_WORKERS')
    state = root/'B2_BUILD_FULL_VALIDATION_V10.json'
    if state.exists() and same_process((read(state).get('active') or {}).get('process', {})):
        raise PermissionError('V11_REQUIRES_PREVIOUS_NATIVE_ZERO_BUILD_EXIT')
    previous = verify_previous(root)
    for receipt in validation.values():
        if record(receipt['path']) != receipt or read(receipt['path']).get('PASS') is not True:
            raise PermissionError('V11_VALIDATION_GATE_NOT_PASS')
    boundary = root/'BASE_CHECKPOINT_BOUNDARY_V11.json'
    if boundary.exists():
        raise PermissionError('V11_BOUNDARY_ALREADY_EXISTS')
    checkpoint = read(root/'CHECKPOINT_V10.json')
    if any(row['arm']=='B2' and row['status']!='PENDING' for row in checkpoint['dates'].values()):
        raise PermissionError('V11_CANNOT_REPLACE_STARTED_B2_DATES')
    if len([r for r in checkpoint['dates'].values() if r['arm']=='B1' and r['status']=='PASS']) != 31:
        raise PermissionError('V11_ALL_31_B1_PASS_REQUIRED')
    inherited_requests = {}
    for name, row in checkpoint['dates'].items():
        if row['arm'] == 'B1':
            if row.get('attempts') != 1 or sha(row['result']) != row['result_SHA']:
                raise PermissionError('V11_INHERITED_RESULT_DRIFT:' + name)
            inherited_requests[name] = record(row['request'])
    failed_validation = read(state)
    failed_request_path = root/'source_validation_v10/B2/2025-05-01/BASELINE/request.json'
    failed_result_path = failed_request_path.parent/'RESULT.json'
    if failed_validation.get('status') != 'FAIL' or read(failed_result_path).get('PASS') is not False:
        raise PermissionError('V11_PRESERVED_FAILED_VALIDATION_REQUIRED')
    shutil.copyfile(root/'CHECKPOINT_V10.json', boundary)
    doc = deepcopy(previous)
    doc.pop('may26_stop', None)
    doc.update(schema=VERSION, continuation_version=VERSION, attempt_id=ATTEMPT,
        precision=PRECISION, precision_dates=sorted(DAYS), phase_I_presolve=0,
        precision_components=['INTEGER_CONTROL', 'ORIGINAL_P1', 'PHASE_I'],
        previous_manifest=record(root/'CONTINUATION_V10_MANIFEST.json'),
        base_checkpoint=record(boundary), retry_authority=record(root/'HOLD_V10.json'),
        inherited_request_receipts=inherited_requests,
        prior_failed_validation=dict(gate=record(state), request=record(failed_request_path), result=record(failed_result_path)),
        authorized_recovery_dates=list(RETRY_DATES),
        input_cache_sources={}, implementation=dict(version=BUILD_VERSION,
            sources=source_files(), source_SHA=digest(source_files())), validation=validation,
        tasks={role:'MobileESS_V42_B1B2_P1_'+previous['run_id']+'_RecoveryV11_'+role.title()
               for role in ('coordinator','monitor','watchdog')},
        source_HEAD=subprocess.check_output(['git','rev-parse','HEAD'], cwd=ROOT, text=True).strip(),
        source_transition=dict(user_authorized=True, B2_validation_restart=True, recovery_order=list(RETRY_DATES),
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
    previous = read(root/'CONTINUATION_V10_MANIFEST.json')
    disabled = []
    for role, name in previous['tasks'].items():
        exported = powershell("Export-ScheduledTask -TaskName '"+name+"'")
        task = ET.fromstring(exported)
        args = task.find('.//{'+NS+'}Arguments').text
        expected = subprocess.list2cmdline(['-B','-X','utf8','-m','v42_may31_recovery_v10.host',role,str(root)])
        if args != expected:
            raise PermissionError('V11_CANNOT_DISABLE_UNRELATED_TASK:'+name)
        saved = root/(name+'_BEFORE_V11.xml')
        if not saved.exists():
            saved.write_text(exported,encoding='utf-8',newline='\n')
        powershell("Disable-ScheduledTask -TaskName '"+name+"' | Out-Null")
        disabled.append(dict(name=name, preserved_definition=record(saved)))
    monitor = root/'MONITOR_PROCESS.json'
    if monitor.exists():
        identity = read(monitor)
        if same_process(identity):
            args = identity['command']
            if ('v42_may31_recovery_v10.host' not in args or 'monitor' not in args
                    or Path(args[-1]).resolve()!=root):
                raise PermissionError('V11_ONLY_EXACT_OWN_MONITOR_MAY_BE_REPLACED')
            atomic(root/'MONITOR_V10_BEFORE_V11.json', identity)
            peer=psutil.Process(identity['PID']);peer.terminate();peer.wait(timeout=10)
    registration=register_campaign_tasks(root, doc)
    started={role:run_task(doc['tasks'][role]) for role in ('monitor','coordinator','watchdog')}
    value=dict(UTC=now(), registration=registration, started=started,
        replaced_tasks=disabled, healthy_Native_worker_kills=0, prior_source_files_changed=0,
        logoff_persistence='LOGOFF_PERSISTENCE_NOT_PROVEN')
    atomic(root/'SOURCE_TRANSITION_ACTIVATION_V11.json', value)
    return value
