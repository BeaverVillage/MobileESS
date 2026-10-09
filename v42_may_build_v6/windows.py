"""Ordinary-user Task Scheduler adapters and measured Native=0 lifetime probe.

InteractiveToken avoids credential/security-policy changes. Its successful
registration does not prove logoff persistence. All new paths are on D:.
"""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import uuid
from xml.etree import ElementTree as ET

from .common import ROOT, d_path, read, atomic, record, process, same_process, now, environment
from v42_pr134_b1.detach import powershell, ancestry, windows_policy

NS = 'http://schemas.microsoft.com/windows/2004/02/mit/task'
LOGOFF_STATUS = 'LOGOFF_PERSISTENCE_NOT_PROVEN'
TASK_PREFIX = 'MobileESS_V42_B1B2_P1_'


def safe_name(name):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,200}', name) or not name.startswith(TASK_PREFIX):
        raise PermissionError('DEDICATED_CAMPAIGN_TASK_NAME_REQUIRED')
    return name


def python_windowless(python=None):
    candidate = Path(python or sys.executable)
    windowless = candidate.with_name('pythonw.exe')
    return str(windowless if windowless.is_file() else candidate)


def exists(name):
    name = safe_name(name)
    return powershell("@(Get-ScheduledTask -TaskName '" + name + "' -ErrorAction SilentlyContinue).Count").strip() != '0'


def task_definition(root, role, *, python, sid, hourly=False, probe_seconds=20):
    root = d_path(root)
    if role not in ('coordinator', 'monitor', 'watchdog', 'probe'):
        raise ValueError('UNKNOWN_TASK_ROLE')
    ET.register_namespace('', NS)

    def tag(parent, name, value=None):
        node = ET.SubElement(parent, '{' + NS + '}' + name)
        if value is not None:
            node.text = str(value)
        return node

    task = ET.Element('{' + NS + '}Task', version='1.4')
    registration = tag(task, 'RegistrationInfo')
    tag(registration, 'Description', 'V42 approved B1 then B2 P1 campaign ' + role + '; InteractiveToken; logoff not proven')
    triggers = tag(task, 'Triggers')
    if role != 'probe':
        if hourly or role == 'watchdog':
            trigger = tag(triggers, 'TimeTrigger')
            tag(trigger, 'Enabled', 'true')
            tag(trigger, 'StartBoundary', (datetime.now(timezone.utc) + timedelta(minutes=1)).replace(microsecond=0).isoformat())
            repeat = tag(trigger, 'Repetition')
            tag(repeat, 'Interval', 'PT1M')
            tag(repeat, 'StopAtDurationEnd', 'false')
        else:
            trigger = tag(triggers, 'LogonTrigger')
            tag(trigger, 'Enabled', 'true')
            tag(trigger, 'UserId', sid)
    principal = tag(tag(task, 'Principals'), 'Principal')
    principal.set('id', 'Author')
    tag(principal, 'UserId', sid)
    tag(principal, 'LogonType', 'InteractiveToken')
    tag(principal, 'RunLevel', 'LeastPrivilege')
    settings = tag(task, 'Settings')
    for name, value in (
        ('MultipleInstancesPolicy', 'IgnoreNew'), ('DisallowStartIfOnBatteries', 'false'),
        ('StopIfGoingOnBatteries', 'false'), ('AllowHardTerminate', 'false'),
        ('StartWhenAvailable', 'true'), ('RunOnlyIfNetworkAvailable', 'false'),
        ('AllowStartOnDemand', 'true'), ('Enabled', 'true'), ('Hidden', 'true'),
        ('ExecutionTimeLimit', 'PT0S'), ('Priority', '4'),
    ):
        tag(settings, name, value)
    actions = tag(task, 'Actions')
    actions.set('Context', 'Author')
    action = tag(actions, 'Exec')
    tag(action, 'Command', python_windowless(python))
    arguments = (['-B', '-X', 'utf8', '-m', 'v42_may_campaign.process_probe', 'launch',
                  '--root', str(root), '--seconds', str(probe_seconds)] if role == 'probe'
                 else ['-B', '-X', 'utf8', '-m', 'v42_may_build_v6.host', role, str(root)])
    tag(action, 'Arguments', subprocess.list2cmdline(arguments))
    tag(action, 'WorkingDirectory', ROOT)
    return task


def register(root, role, name=None, hourly=False, *, python=None, probe_seconds=20):
    root = d_path(root)
    root.mkdir(parents=True, exist_ok=True)
    name = safe_name(name or TASK_PREFIX + role.title() + '_' + uuid.uuid4().hex[:12])
    if exists(name):
        raise PermissionError('DEDICATED_TASK_NAME_ALREADY_EXISTS:' + name)
    sid = powershell('[System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value').strip()
    definition = task_definition(root, role, python=python or sys.executable, sid=sid,
                                 hourly=hourly, probe_seconds=probe_seconds)
    path = root / (name + '_TASK.xml')
    ET.ElementTree(definition).write(path, encoding='utf-16', xml_declaration=True)
    result = subprocess.run(['schtasks.exe', '/Create', '/TN', name, '/XML', str(path)],
                            capture_output=True, text=True, encoding='utf-8', errors='replace')
    if result.returncode:
        raise RuntimeError('TASK_REGISTRATION_FAILED:' + str(result.returncode) + ':' + (result.stderr or result.stdout).strip())
    exported = powershell("Export-ScheduledTask -TaskName '" + name + "'")
    exported_path = root / (name + '_REGISTERED_TASK.xml')
    exported_path.write_text(exported, encoding='utf-8')
    parsed = ET.fromstring(exported)
    values = lambda field: [node.text for node in parsed.findall('.//{' + NS + '}' + field)]
    if values('LogonType') != ['InteractiveToken'] or values('ExecutionTimeLimit') != ['PT0S']:
        raise PermissionError('REGISTERED_TASK_POLICY_DRIFT')
    return dict(PASS=True, name=name, task=name, role=role, registered=True, started=False,
                logon_type='InteractiveToken', logoff_persistence=LOGOFF_STATUS,
                definition=record(exported_path), user_sid=sid, UTC=now(),
                security_policy_changed=False, existing_tasks_changed=False)


def register_campaign_tasks(root, manifest):
    root = d_path(root)
    tasks = manifest.get('tasks', {})
    receipts = {}
    for role in ('coordinator', 'monitor', 'watchdog'):
        name = tasks.get(role) if isinstance(tasks, dict) else None
        if isinstance(name, dict):
            name = name.get('name')
        python = manifest.get('Python', manifest.get('python_executable'))
        receipts[role] = (reuse_registered_task(root, role, name, python=python) if name and exists(name)
                          else register(root, role, name, hourly=role == 'watchdog', python=python))
    atomic(root / 'WINDOWS_TASK_REGISTRATION_V6.json', dict(tasks=receipts, logoff_persistence=LOGOFF_STATUS,
          security_policy_changed=False, existing_tasks_changed=False, UTC=now()))
    return receipts


def reuse_registered_task(root, role, name, *, python=None):
    """Read and verify only an owned same-root definition; never rewrite it."""
    root = d_path(root)
    name = safe_name(name)
    original = root / (name + '_REGISTERED_TASK.xml')
    if not original.is_file():
        raise PermissionError('EXISTING_TASK_WITHOUT_OWN_REGISTRATION_RECEIPT:' + name)
    current = powershell("Export-ScheduledTask -TaskName '" + name + "'")
    if current.strip() != original.read_text(encoding='utf-8').strip():
        raise PermissionError('OWN_EXISTING_TASK_DEFINITION_DRIFT:' + name)
    sid = powershell('[System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value').strip()
    expected = task_definition(root, role, python=python or sys.executable, sid=sid)
    parsed = ET.fromstring(current)
    fields = ['Command', 'Arguments', 'WorkingDirectory', 'LogonType', 'RunLevel', 'Priority',
              'ExecutionTimeLimit', 'AllowHardTerminate', 'MultipleInstancesPolicy']
    if role == 'watchdog':
        fields.append('Interval')
    run_level_evidence = {}
    for field in fields:
        value = parsed.find('.//{' + NS + '}' + field)
        wanted = expected.find('.//{' + NS + '}' + field)
        actual_text = value.text if value is not None else None
        if field == 'RunLevel' and value is None:
            # Export may omit the optional least-privilege element. Confirm
            # the actual service property before accepting its normalization.
            run_level = powershell("(Get-ScheduledTask -TaskName '" + name + "').Principal.RunLevel").strip()
            actual_text = 'LeastPrivilege' if run_level == 'Limited' else run_level
            run_level_evidence = dict(XML_element_omitted=True, actual_service_RunLevel=run_level,
                normalized_RunLevel=actual_text, read_only_service_query=True)
        elif field == 'RunLevel':
            run_level_evidence = dict(XML_element_omitted=False, XML_RunLevel=actual_text)
        if wanted is None or actual_text != wanted.text:
            raise PermissionError('OWN_EXISTING_TASK_ACTION_OR_POLICY_DRIFT:' + field)
    return dict(PASS=True, name=name, task=name, role=role, registered=True, reused_owned_definition=True,
                existing_task_modified=False, logon_type='InteractiveToken', definition=record(original),
                RunLevel_verification=run_level_evidence, logoff_persistence=LOGOFF_STATUS, UTC=now())


def run_task(name):
    name = safe_name(name)
    result = subprocess.run(['schtasks.exe', '/Run', '/TN', name], capture_output=True,
                            encoding='utf-8', errors='replace')
    if result.returncode:
        raise RuntimeError('DEDICATED_TASK_RUN_FAILED:' + str(result.returncode) + ':' + (result.stderr or result.stdout).strip())
    return dict(name=name, dispatch_requested=True, UTC=now())


def task_status(name):
    name = safe_name(name)
    script = "$t=Get-ScheduledTask -TaskName '" + name + "';$i=Get-ScheduledTaskInfo -TaskName '" + name + "';" + (
        '[pscustomobject]@{name=$t.TaskName;state=[string]$t.State;logon_type=[string]$t.Principal.LogonType;'
        'last_task_result=$i.LastTaskResult;last_run_utc=$i.LastRunTime.ToUniversalTime().ToString("o")}|ConvertTo-Json -Compress')
    return json.loads(powershell(script))


def scheduler_service_identity():
    script = ("$s=Get-CimInstance Win32_Service -Filter \"Name='Schedule'\";"
              '[pscustomobject]@{name=$s.Name;PID=$s.ProcessId;state=$s.State}|ConvertTo-Json -Compress')
    return json.loads(powershell(script))


def scheduler_process_evidence(identity):
    """Read-only evidence for an actual Coordinator/Worker/Monitor identity."""
    if not same_process(identity):
        raise PermissionError('SCHEDULER_PROCESS_IDENTITY_NOT_LIVE')
    chain = ancestry(identity['PID'])
    service = scheduler_service_identity()
    names = [row['name'].lower() for row in chain]
    owned = (service['state'] == 'Running' and any(row['PID'] == service['PID'] for row in chain)
             and not any(name in ('codex.exe', 'chatgpt.exe') for name in names))
    return dict(PASS=owned, process=identity, ancestry=chain, Schedule_service=service,
                TaskScheduler_owned=owned, Codex_owned=any(name == 'codex.exe' for name in names),
                resource_policy=windows_policy(identity['PID']), UTC=now(),
                logoff_persistence=LOGOFF_STATUS, logoff_persistence_proven=False)


def unregister_own_probe(name, root, *, probe_seconds=20):
    name = safe_name(name)
    root = d_path(root)
    if not name.startswith(TASK_PREFIX + 'Probe_'):
        raise PermissionError('ONLY_OWN_PROBE_TASK_CAN_BE_REMOVED')
    exported = powershell("Export-ScheduledTask -TaskName '" + name + "'")
    parsed = ET.fromstring(exported)
    arguments = parsed.find('.//{' + NS + '}Arguments').text
    expected_arguments = subprocess.list2cmdline([
        '-B', '-X', 'utf8', '-m', 'v42_may_campaign.process_probe', 'launch',
        '--root', str(root), '--seconds', str(probe_seconds)])
    if arguments != expected_arguments:
        raise PermissionError('PROBE_ACTION_ROOT_IDENTITY_DRIFT')
    powershell("Unregister-ScheduledTask -TaskName '" + name + "' -Confirm:$false")
    if exists(name):
        raise RuntimeError('OWN_PROBE_TASK_CLEANUP_FAILED')


def observe_probe(root, *, scheduler_owned, deadline_seconds=15):
    root = d_path(root)
    deadline = time.monotonic() + deadline_seconds
    observations = []
    first_heartbeat = None
    while time.monotonic() < deadline:
        launch_path, child_path, heartbeat_path = (root / name for name in
            ('LAUNCHER_RESULT.json', 'CHILD_PROCESS.json', 'CHILD_HEARTBEAT.json'))
        if launch_path.is_file():
            launch = read(launch_path)
            if launch.get('PASS') is False:
                return dict(PASS=False, launch=launch, error='PROBE_CHILD_CREATE_FAILED', observations=observations)
            if child_path.is_file() and heartbeat_path.is_file():
                child, heartbeat = read(child_path), read(heartbeat_path)
                if first_heartbeat is None:
                    first_heartbeat = dict(heartbeat)
                launcher_alive = same_process(launch['process'])
                child_alive = same_process(child['process'])
                row = dict(UTC=now(), launcher_alive=launcher_alive, child_alive=child_alive,
                           heartbeat_number=heartbeat['heartbeat_number'], heartbeat_timestamp=heartbeat['timestamp_UTC'])
                observations.append(row)
                launcher_receipt = read(root / 'LAUNCHER_PROCESS.json')
                service_chain = any(r['name'].lower() in ('svchost.exe', 'taskeng.exe', 'taskhostw.exe')
                                    for r in launcher_receipt['ancestry'])
                out_of_job = child['job']['in_any_job'] is False
                job_no_kill = out_of_job or child['job'].get('kill_on_job_close') is False
                # At least two changing child heartbeat samples while launcher
                # is actually gone: process detachment is observed, not assumed.
                after_exit = [r for r in observations if not r['launcher_alive'] and r['child_alive']]
                changed = len({r['heartbeat_number'] for r in after_exit}) >= 2
                if not launcher_alive and child_alive and changed and job_no_kill and (service_chain or not scheduler_owned):
                    return dict(PASS=True, launcher=launcher_receipt, launch=launch, child=child,
                                first_child_heartbeat=first_heartbeat, heartbeat_at_verification=heartbeat,
                                observations=observations,
                                scheduler_service_ancestry_proven=service_chain if scheduler_owned else False,
                                launcher_exit_observed=True, changing_child_heartbeat_after_launcher_exit=True,
                                child_outside_all_job_objects=out_of_job,
                                child_current_job_kill_on_close=child['job'].get('kill_on_job_close'),
                                child_job_membership_and_limits_disclosed=True)
        time.sleep(0.5)
    return dict(PASS=False, error='LIFETIME_PROBE_OBSERVATION_TIMEOUT', observations=observations)


def detached_probe(root, *, seconds=20):
    from .process_probe import BREAKAWAY_FLAGS, job_information
    root = d_path(root)
    root.mkdir(parents=True, exist_ok=True)
    environment(root)
    caller = dict(process=process(), ancestry=ancestry(process()['PID']), job=job_information(), UTC=now())
    atomic(root / 'DETACHED_CALLER.json', caller)
    command = [python_windowless(), '-B', '-X', 'utf8', '-m', 'v42_may_campaign.process_probe',
               'launch', '--root', str(root), '--seconds', str(seconds)]
    try:
        with (root / 'detached.stdout.log').open('ab') as stdout, (root / 'detached.stderr.log').open('ab') as stderr:
            launcher = subprocess.Popen(command, cwd=ROOT, stdout=stdout, stderr=stderr,
                                        creationflags=BREAKAWAY_FLAGS)
        result = observe_probe(root, scheduler_owned=False)
        result.update(caller=caller, detached_creation_flags=BREAKAWAY_FLAGS,
                      launcher_exit_code=launcher.poll(), scheduler_registered=False)
        return result
    except (OSError, RuntimeError) as error:
        return dict(PASS=False, error=str(error), type=type(error).__name__, caller=caller)


def run_process_probe(candidate_root):
    """Only install/run/remove a unique Native=0 probe; never a campaign task."""
    candidate_root = d_path(candidate_root)
    prior = candidate_root / 'WINDOWS_PROCESS_PERSISTENCE_PROBE.json'
    if prior.is_file():
        shutil.copyfile(prior, candidate_root / ('WINDOWS_PROCESS_PERSISTENCE_PROBE_PREVIOUS_' + uuid.uuid4().hex[:8] + '.json'))
    root = candidate_root / ('os_probe_' + uuid.uuid4().hex[:12])
    root.mkdir(parents=True, exist_ok=False)
    source_snapshot = root / 'SOURCE'
    source_snapshot.mkdir()
    for source in (Path(__file__), ROOT / 'v42_may_campaign/process_probe.py'):
        shutil.copyfile(source, source_snapshot / source.name)
    environment(root)
    name = TASK_PREFIX + 'Probe_' + uuid.uuid4().hex[:12]
    registration = None
    scheduler_error = None
    try:
        registration = register(root, 'probe', name, probe_seconds=20)
        run_task(name)
        result = observe_probe(root, scheduler_owned=True)
        result.update(execution_owner='WINDOWS_TASK_SCHEDULER', registration=registration,
                      task_status=task_status(name), detached_fallback_used=False)
        if not result.get('PASS'):
            scheduler_error = dict(error='REGISTERED_TASK_LIFETIME_PROBE_FAILED', evidence=result, UTC=now())
            result = detached_probe(root / 'detached_fallback')
            result.update(execution_owner='DETACHED_BREAKAWAY_PROCESS' if result.get('PASS') else 'NONE',
                          scheduler_error=scheduler_error, detached_fallback_used=True)
    except (OSError, RuntimeError, PermissionError, subprocess.SubprocessError) as error:
        scheduler_error = dict(error=str(error), type=type(error).__name__, registered=registration is not None,
                               UTC=now())
        result = detached_probe(root / 'detached_fallback')
        result.update(execution_owner='DETACHED_BREAKAWAY_PROCESS' if result.get('PASS') else 'NONE',
                      scheduler_error=scheduler_error, detached_fallback_used=True)
    finally:
        try:
            if exists(name):
                unregister_own_probe(name, root)
                cleanup = dict(own_probe_task_removed=True, existing_tasks_changed=False)
            else:
                cleanup = dict(own_probe_task_removed=False, probe_never_registered=True, existing_tasks_changed=False)
        except Exception as error:
            cleanup = dict(own_probe_task_removed=False, error=str(error), existing_tasks_changed=False)
    result.update(Native_optimize_calls=0, scientific_models_called=False, campaign_started=False,
                  logoff_persistence=LOGOFF_STATUS, logoff_persistence_proven=False,
                  Codex_app_close_experiment_performed=False, launcher_exit_only_experiment=True,
                  S4U_attempts=0, security_policy_changed=False, cleanup=cleanup,
                  probe_root=str(root), UTC=now(), source_files=[record(Path(__file__)), record(ROOT / 'v42_may_campaign/process_probe.py')],
                  source_snapshot=[record(p) for p in sorted(source_snapshot.iterdir())],
                  primary_API_references=[
                      'https://learn.microsoft.com/en-us/windows/win32/api/jobapi2/nf-jobapi2-queryinformationjobobject',
                      'https://learn.microsoft.com/en-us/windows/win32/procthread/process-creation-flags'])
    if cleanup.get('error'):
        result['PASS'] = False
    atomic(candidate_root / 'WINDOWS_PROCESS_PERSISTENCE_PROBE.json', result)
    return result


if __name__ == '__main__':
    if len(sys.argv) != 3 or sys.argv[1] != 'probe':
        raise SystemExit('Only explicit Native=0 probe CLI is supported')
    result = run_process_probe(sys.argv[2])
    print(json.dumps({k: result.get(k) for k in ('PASS', 'execution_owner', 'logoff_persistence',
                                               'Native_optimize_calls', 'probe_root', 'scheduler_error')}, ensure_ascii=False))
    raise SystemExit(0 if result['PASS'] else 1)
