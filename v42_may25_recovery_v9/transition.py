"""Admit the explicit May25/26 restart at the already-stopped OS boundary."""
from copy import deepcopy
from pathlib import Path
import shutil
import subprocess
from xml.etree import ElementTree as ET
from .common import ROOT, read, record, atomic, now, sha, digest, same_process


def admit(root, validation):
    from .policy import VERSION, BUILD_VERSION, MANIFEST, ATTEMPT, PRECISION, DAYS, RETRY_DATES, source_files, verify_policy
    from .storage import initialize_checkpoint
    from v42_may_mess_build_v7.policy import verify_policy as verify_previous
    from v42_may_mess_build_v7.coordinator import read_actives
    root = Path(root).resolve()
    if (root / MANIFEST).exists():
        return verify_policy(root)
    if (not (root / 'HOLD_V7R2.json').is_file()
            or same_process(read(root / 'COORDINATOR_V7R2_HOST.json')['process'])
            or any(same_process(a.get('worker', {})) for a in read_actives(root).values())):
        raise PermissionError('V9_SOURCE_SWITCH_REQUIRES_STOPPED_PREVIOUS_COORDINATOR_AND_WORKER')
    previous = verify_previous(root)
    for receipt in validation.values():
        if record(receipt['path']) != receipt or read(receipt['path']).get('PASS') is not True:
            raise PermissionError('V9_SOURCE_SWITCH_GATE_NOT_PASS')
    boundary = root / 'BASE_CHECKPOINT_BOUNDARY_V9.json'
    if boundary.exists():
        raise PermissionError('V9_IMMUTABLE_CHECKPOINT_BOUNDARY_ALREADY_EXISTS')
    shutil.copyfile(root / 'CHECKPOINT_V7R2.json', boundary)
    checkpoint = read(boundary)
    if any(row['arm'] == 'B2' and row['status'] != 'PENDING' for row in checkpoint['dates'].values()):
        raise PermissionError('V9_CANNOT_REPLACE_STARTED_B2_DATES')
    doc = deepcopy(previous)
    doc.update(schema=VERSION, continuation_version=VERSION, attempt_id=ATTEMPT, precision=PRECISION,
        precision_dates=sorted(DAYS), phase_I_presolve=0,
        previous_manifest=record(root / 'CONTINUATION_V7R2_MANIFEST.json'), base_checkpoint=record(boundary),
        may26_stop=record(ROOT / 'docs/v42_may25_recovery_v9_20261009/MAY26_USER_AUTHORIZED_STOP.json'),
        authorized_recovery_dates=list(RETRY_DATES), input_cache_sources={},
        input_authority_root=str(Path(previous['scientific_authority']['path']).parent),
        implementation=dict(version=BUILD_VERSION, sources=source_files(), source_SHA=digest(source_files())),
        validation=validation,
        tasks={role: 'MobileESS_V42_B1B2_P1_' + previous['run_id'] + '_RecoveryV9_' + role.title()
               for role in ('coordinator', 'monitor', 'watchdog')},
        source_HEAD=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        source_transition=dict(user_authorized=True, completed_date_resets=0,
            recovery_order=list(RETRY_DATES), all_May_precision=True, Phase_I_original_rows=True,
            acceptance_tolerance_changed=False, Heuristics=.05, built_in_heuristics_enabled=True,
            B1_scientific_implementation='FROZEN_V6_WITH_VERSIONED_NATIVE_PRECISION_ADAPTER',
            B2_build_implementation=BUILD_VERSION, B2_full_equivalence='DEFERRED_UNTIL_ALL_B1_WORKERS_EXIT',
            automatic_failed_date_retries=0), UTC=now())
    atomic(root / MANIFEST, doc)
    verify_policy(root)
    initialize_checkpoint(root, doc)
    return doc


def disable_replaced_gap_tasks(root):
    """Disable only our newer read-only display tasks, preserving their XML."""
    from .windows import powershell, NS
    root = Path(root)
    results = []
    prefix = 'MobileESS_V42_B1B2_P1_' + read(root / 'CONTINUATION_V7R2_MANIFEST.json')['run_id']
    for revision in ('MonitorGapV8', 'MonitorGapV8R2'):
        for role in ('Monitor', 'Watchdog'):
            name = prefix + '_' + revision + '_' + role
            original = root / (name + '_REGISTERED_TASK.xml')
            if not original.is_file():
                continue
            text = powershell("Export-ScheduledTask -TaskName '" + name + "'")
            task = ET.fromstring(text)
            args = task.find('.//{' + NS + '}Arguments').text
            expected = subprocess.list2cmdline(['-B', '-X', 'utf8', '-m', 'v42_may_monitor_gap_v8.host', role.lower(), str(root)])
            if args != expected:
                raise PermissionError('V9_CANNOT_DISABLE_UNRELATED_TASK:' + name)
            preserved = root / (name + '_BEFORE_V9.xml')
            if not preserved.exists():
                preserved.write_text(text, encoding='utf-8', newline='\n')
            powershell("Disable-ScheduledTask -TaskName '" + name + "' | Out-Null")
            enabled = powershell("(Get-ScheduledTask -TaskName '" + name + "').Settings.Enabled").strip()
            if enabled != 'False':
                raise PermissionError('V9_REPLACED_GAP_TASK_STILL_ENABLED')
            results.append(dict(name=name, disabled=True, historical_definition=record(preserved),
                read_only_monitor_deployment=True, Solver_Coordinator_research_task=False))
    atomic(root / 'REPLACED_GAP_TASKS_V9.json', dict(UTC=now(), tasks=results, research_tasks_modified=0))
    return results


def activate(root):
    from .policy import MANIFEST
    from .windows import register_campaign_tasks, run_task
    root = Path(root).resolve()
    doc = read(root / MANIFEST)
    registration = register_campaign_tasks(root, doc)
    replaced = disable_replaced_gap_tasks(root)
    monitor = root / 'MONITOR_PROCESS.json'
    if monitor.exists():
        identity = read(monitor)
        if same_process(identity):
            import psutil
            command = identity.get('command', [])
            if ('v42_may_monitor_gap_v8.host' not in command or 'monitor' not in command
                    or Path(command[-1]).resolve() != root):
                raise PermissionError('V9_CAN_REPLACE_ONLY_EXACT_OWN_READ_ONLY_GAP_MONITOR')
            atomic(root / 'MONITOR_GAP_V8_BEFORE_V9.json', identity)
            peer = psutil.Process(identity['PID']); peer.terminate(); peer.wait(timeout=10)
    started = {role: run_task(doc['tasks'][role]) for role in ('monitor', 'coordinator', 'watchdog')}
    value = dict(UTC=now(), registration=registration, started=started,
        replaced_read_only_tasks=replaced, activation_worker_kills=0,
        previous_source_files_changed=0, logoff_persistence='LOGOFF_PERSISTENCE_NOT_PROVEN')
    atomic(root / 'SOURCE_TRANSITION_ACTIVATION_V9.json', value)
    return value
