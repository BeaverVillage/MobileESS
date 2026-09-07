"""Detached ten-minute campaign watchdog with durable inspection records."""
from datetime import datetime, timezone
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import uuid

import psutil

from dayahead.paper_analysis.storage import atomic, read
from dayahead.v39l.infrastructure import durable_atomic_json as write_json
from dayahead.v41.data import RUNTIME
from dayahead.v41.detached import job_membership
from dayahead.v41.preflight import ROOT, OUT, record
from dayahead.v41.reserve import require


INTERVAL_SECONDS = 600
LOG = ROOT / 'logs/v41r1_migration/SUPERVISOR_10MIN_LOG.jsonl'
HEARTBEAT = RUNTIME / 'SUPERVISOR_10MIN_HEARTBEAT.json'
FAILURE = re.compile(r'Traceback|\bException\b|\bFATAL\b|Out of memory|No space left|PermissionError|PHASE_PROCESS_FAILED', re.I)


def now():
    return datetime.now(timezone.utc).isoformat()


def _age(value):
    return max(0., time.time() - datetime.fromisoformat(value).timestamp())


def _process(pid, tokens=()):
    try:
        process = psutil.Process(int(pid))
        command = process.cmdline()
        return process.is_running() and process.status() != psutil.STATUS_ZOMBIE and all(token in command for token in tokens), command
    except (psutil.NoSuchProcess, psutil.AccessDenied, ValueError, TypeError):
        return False, []


def _monitor_processes():
    result = []
    for process in psutil.process_iter(['pid', 'cmdline']):
        command = process.info['cmdline'] or []
        if any(str(item).replace('\\','/').split('/')[-1].lower()=='monitor_v41r1_may_live.ps1' for item in command):
            result.append(process.pid)
    return result


def _restart_monitor():
    script = ROOT / 'dayahead/tools/monitor_v41r1_may_live.ps1'
    args=['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(script)]
    quote=lambda value:"'"+value.replace("'","''")+"'"
    # CREATE_NEW_CONSOLE and DETACHED_PROCESS are mutually exclusive. WMI
    # supplies independent parentage while the monitor gets its visible console.
    helper=RUNTIME/'launcher_helpers'/('monitor_'+uuid.uuid4().hex+'.ps1')
    body=("$ErrorActionPreference='Stop'\n"
        "$s=New-CimInstance -CimClass (Get-CimClass Win32_ProcessStartup) -ClientOnly -Property @{ShowWindow=[uint16]1;CreateFlags=[uint32]16}\n"
        "$p=Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine="+
        quote(subprocess.list2cmdline(args))+";CurrentDirectory="+quote(str(ROOT))+";ProcessStartupInformation=$s}\n"
        "$p | Select-Object ProcessId,ReturnValue | ConvertTo-Json -Compress\n")
    with atomic(helper) as stream:stream.write(body.encode('utf-8-sig'))
    created=subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(helper)],
        cwd=ROOT,capture_output=True,text=True,check=True,creationflags=subprocess.CREATE_NO_WINDOW)
    response=json.loads(created.stdout);require(response['ReturnValue']==0,'MONITOR_CIM_RESTART_FAILED')
    pid=int(response['ProcessId'])
    time.sleep(.5)
    alive, _ = _process(pid)
    require(alive, 'MONITOR_RESTART_FAILED')
    write_json(RUNTIME / 'MONITOR_LAUNCH.json', dict(opened_at=now(), pid=pid, path=str(script),
        restarted_by_watchdog=os.getpid()))
    return pid


def _tail(path, limit=256 * 1024):
    try:
        with Path(path).open('rb') as stream:
            stream.seek(0, os.SEEK_END)
            size = stream.tell()
            stream.seek(max(0, size - limit))
            return stream.read().decode('utf-8', errors='replace')
    except (OSError, TypeError):
        return ''


def inspect():
    state = read(RUNTIME / 'campaign_state.json')
    progress = read(RUNTIME / 'campaign_progress.json')
    heartbeat = read(RUNTIME / 'campaign_heartbeat.json')
    memory = read(RUNTIME / 'campaign_memory.json')
    manager_pid = int(progress['PID'])
    manager_alive, manager_command = _process(manager_pid, ('dayahead.v41r1.campaign_run', 'worker'))
    heartbeat_age = _age(heartbeat['timestamp'])
    rows = list(state['units'].values())
    active = [row for row in rows if row['status'] in ('DAYAHEAD_RUNNING', 'ACTUAL_RUNNING')]
    active_days = sorted({row['day'] for row in active})
    failed = [row for row in rows if row['status'] == 'FAILED']
    complete = [row for row in rows if row['status'] == 'COMPLETE']
    unfinished_days = {row['day'] for row in rows if row['status'] != 'COMPLETE'}
    worker_checks = []
    fatal = []
    warnings = []
    for row in active:
        alive, command = _process(row.get('worker_pid'), ('dayahead.v41.execution', row['day'], row['policy'], row['phase']))
        worker_checks.append(dict(day=row['day'], policy=row['policy'], phase=row['phase'], pid=row.get('worker_pid'),
            alive=alive, command=command))
        if not alive and heartbeat_age > 30:
            fatal.append('ACTIVE_WORKER_DEAD:' + row['day'] + '/' + row['policy'])
        marker = FAILURE.search(_tail(row.get('log')))
        if marker:
            fatal.append('ACTIVE_LOG_FATAL_MARKER:' + row['day'] + '/' + row['policy'] + ':' + marker.group(0))
    intentionally_stopped = state['status'].startswith('PAUSED') or state['status'].startswith('READY')
    if state['status'] != 'COMPLETE' and not intentionally_stopped and not manager_alive:
        fatal.append('CAMPAIGN_MANAGER_DEAD')
    if state['status'] == 'RUNNING' and heartbeat_age > 30:
        fatal.append('CAMPAIGN_HEARTBEAT_STALE')
    if failed:
        fatal.append('FAILED_UNITS:' + str(len(failed)))
    expected = min(4, len(unfinished_days)) if state['status'] == 'RUNNING' else 0
    if state['status'] == 'RUNNING' and len(active_days) != expected:
        warnings.append(f'ACTIVE_DAY_TRANSITION:{len(active_days)}/{expected}')
    current_commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    if state['status'] == 'RUNNING' and current_commit != state['scientific_commit']:
        fatal.append('MIXED_SCIENTIFIC_COMMIT')
    checkpoint_errors = []
    for row in complete:
        receipt = row.get('unit_receipt', {}).get('path')
        if not receipt or not Path(receipt).is_file() or record(receipt) != row['unit_receipt']:
            checkpoint_errors.append(row['day'] + '/' + row['policy'])
    if checkpoint_errors:
        fatal.append('COMPLETE_CHECKPOINT_DRIFT:' + ','.join(checkpoint_errors))
    monitor_pids = _monitor_processes()
    monitor_restarted = None
    if not monitor_pids and state['status'] != 'COMPLETE':
        try:
            monitor_restarted = _restart_monitor()
            monitor_pids = [monitor_restarted]
        except Exception as error:
            warnings.append('MONITOR_RESTART_FAILED:' + repr(error))
    disk = shutil.disk_usage(ROOT)
    from .campaign_run import RESULT_STORAGE_ROOT
    result_disk=shutil.disk_usage(RESULT_STORAGE_ROOT if RESULT_STORAGE_ROOT.exists() else RESULT_STORAGE_ROOT.anchor)
    if result_disk.free < 1024 ** 3:fatal.append('RESULT_DISK_FREE_BELOW_1_GIB')
    if disk.free < 1024 ** 3:
        fatal.append('DISK_FREE_BELOW_1_GIB')
    elif disk.free < 5 * 1024 ** 3:
        warnings.append('DISK_FREE_BELOW_5_GIB')
    host = psutil.virtual_memory()
    if host.available < 1024 ** 3:
        warnings.append('AVAILABLE_RAM_BELOW_1_GIB')
    result = dict(schema='V41R1_10MIN_WATCHDOG_V1', timestamp=now(), interval_seconds=INTERVAL_SECONDS,
        status='FAIL' if fatal else 'COMPLETE' if state['status'] == 'COMPLETE' else 'PASS',
        campaign_status=state['status'], manager=dict(pid=manager_pid, alive=manager_alive, command=manager_command),
        campaign_heartbeat_age_seconds=heartbeat_age, scientific_commit=state['scientific_commit'],
        current_git_commit=current_commit, mixed_revision=current_commit != state['scientific_commit'],
        active_day_count=len(active_days), expected_active_day_count=expected, active_days=active_days,
        workers=worker_checks, active_solver_child_pids=[row['pid'] for row in worker_checks if row['alive']],
        completed_policy_days=len(complete), completed_days=sum(all(r['status'] == 'COMPLETE' for r in rows if r['day'] == day)
            for day in sorted({r['day'] for r in rows})), remaining_units=124-len(complete), failed_units=len(failed),
        new_PASS_units='DERIVED_BY_DIFF_FROM_PREVIOUS_RECORD', new_FAIL_units='DERIVED_BY_DIFF_FROM_PREVIOUS_RECORD',
        monitor_pids=monitor_pids, monitor_restarted_pid=monitor_restarted,
        artifact_readback_status='PASS' if not checkpoint_errors else 'FAIL', checkpoint_consistency='PASS' if not checkpoint_errors else 'FAIL',
        state_consistency='PASS' if progress['scientific_commit'] == state['scientific_commit'] else 'FAIL',
        memory=dict(host_total_bytes=host.total, host_available_bytes=host.available,
            campaign_snapshot=memory, OOM_indicator=False), disk=dict(free_bytes=disk.free, total_bytes=disk.total,
                result_volume=str(RESULT_STORAGE_ROOT),result_free_bytes=result_disk.free,result_total_bytes=result_disk.total),
        fatal=fatal, warnings=warnings, next_check_not_before_epoch=time.time() + INTERVAL_SECONDS)
    if result['state_consistency'] == 'FAIL':
        result['fatal'].append('CAMPAIGN_STATE_PROGRESS_COMMIT_MISMATCH')
        result['status'] = 'FAIL'
    return result


def _append(value):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, separators=(',', ':')) + '\n')
        stream.flush()
        os.fsync(stream.fileno())


def worker(token, git):
    from dayahead.tools.v41_detached_launcher import provision_git
    provision_git(git)
    sys.stdin = open(os.devnull, 'r')
    sys.stdout = (ROOT / 'logs/v41r1_migration/watchdog_process.log').open('a', encoding='utf-8', buffering=1)
    sys.stderr = sys.stdout
    proof = dict(status='RUNNING', pid=os.getpid(), parent_pid=os.getppid(), token=token, started_at=now(),
        in_Windows_job=job_membership(), interval_seconds=INTERVAL_SECONDS, command=psutil.Process().cmdline())
    require(not proof['in_Windows_job'], 'WATCHDOG_NOT_DETACHED_FROM_CODEX')
    write_json(RUNTIME / 'SUPERVISOR_10MIN_PID.json', proof)
    last_complete = set()
    last_failed = set()
    while True:
        cycle_started = time.time()
        try:
            value = inspect()
            state = read(RUNTIME / 'campaign_state.json')
            rows = list(state['units'].values())
            complete = {row['day'] + '/' + row['policy'] for row in rows if row['status'] == 'COMPLETE'}
            failed = {row['day'] + '/' + row['policy'] for row in rows if row['status'] == 'FAILED'}
            value['new_PASS_units'] = sorted(complete - last_complete)
            value['new_FAIL_units'] = sorted(failed - last_failed)
            last_complete, last_failed = complete, failed
            if value['fatal'] and not (RUNTIME / 'STOP_REQUESTED.json').exists():
                write_json(RUNTIME / 'STOP_REQUESTED.json', dict(requested_at=now(), mode='FINISH_CURRENT_PHASE',
                    requested_by='V41R1_10MIN_WATCHDOG', fatal=value['fatal']))
                value['campaign_pause_requested'] = True
            else:
                value['campaign_pause_requested'] = False
        except Exception as error:
            value = dict(schema='V41R1_10MIN_WATCHDOG_V1', timestamp=now(), status='WATCHDOG_ERROR',
                error=repr(error), next_check_not_before_epoch=cycle_started + INTERVAL_SECONDS)
        write_json(HEARTBEAT, value)
        _append(value)
        if value.get('campaign_status') == 'COMPLETE':
            write_json(RUNTIME / 'SUPERVISOR_10MIN_COMPLETE.json', value)
            return
        time.sleep(max(1., cycle_started + INTERVAL_SECONDS - time.time()))


def launch():
    from dayahead.tools.v41_detached_launcher import git_executable
    for process in psutil.process_iter(['pid', 'cmdline']):
        command = process.info['cmdline'] or []
        require(not ('dayahead.v41r1.watchdog' in command and 'worker' in command), 'WATCHDOG_ALREADY_RUNNING')
    token = uuid.uuid4().hex
    args = [sys.executable, '-u', '-m', 'dayahead.v41r1.watchdog', 'worker', '--token', token,
        '--git', git_executable()]
    quote = lambda value: "'" + value.replace("'", "''") + "'"
    script = ("$ErrorActionPreference='Stop'\n"
        "$v41Startup=New-CimInstance -CimClass (Get-CimClass Win32_ProcessStartup) -ClientOnly -Property @{ShowWindow=[uint16]0;CreateFlags=[uint32]8}\n"
        "$v41Created=Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine=" +
        quote(subprocess.list2cmdline(args)) + ";CurrentDirectory=" + quote(str(ROOT)) + ";ProcessStartupInformation=$v41Startup}\n"
        "$v41Created | Select-Object ProcessId,ReturnValue | ConvertTo-Json -Compress\n")
    helper = RUNTIME / 'launcher_helpers' / ('watchdog_' + token + '.ps1')
    with atomic(helper) as stream:
        stream.write(script.encode('utf-8-sig'))
    created = subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(helper)],
        capture_output=True, text=True, check=True)
    response = json.loads(created.stdout)
    require(response['ReturnValue'] == 0, 'WATCHDOG_CIM_CREATE_FAILED')
    pid = int(response['ProcessId'])
    time.sleep(.5)
    alive, _ = _process(pid, ('dayahead.v41r1.watchdog', 'worker'))
    require(alive, 'WATCHDOG_CHILD_START_FAILED')
    receipt = dict(status='RUNNING', pid=pid, launcher_pid=os.getpid(), started_at=now(), token=token,
        interval_seconds=INTERVAL_SECONDS, mechanism='Independent WMI provider; DETACHED_PROCESS; worker-owned streams',
        source=record(__file__), log=str(LOG), heartbeat=str(HEARTBEAT))
    write_json(RUNTIME / 'SUPERVISOR_10MIN_LAUNCH.json', receipt)
    print(json.dumps(receipt, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['launch', 'worker', 'once'])
    parser.add_argument('--token')
    parser.add_argument('--git')
    args = parser.parse_args()
    if args.mode == 'launch':
        launch()
    elif args.mode == 'worker':
        worker(args.token, args.git)
    else:
        print(json.dumps(inspect(), ensure_ascii=False, indent=2), flush=True)
