"""One OS-scheduled observation/recovery pass; never stops a healthy worker."""
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys

from v42_pr134_b1.common import atomic, read, same_process, now, process, sha
from .coordinator import counts, load_manifest, runtime_path, read_actives


def task_name(manifest, role):
    tasks = manifest.get('tasks', {})
    value = tasks.get(role) if isinstance(tasks, dict) else None
    if value:
        return value['name'] if isinstance(value, dict) else value
    return manifest.get({'coordinator': 'task_name', 'monitor': 'monitor_task', 'watchdog': 'watchdog_task'}[role])


def optional(path):
    return read(path) if Path(path).is_file() else {}


def run(root):
    root = runtime_path(root)
    if (root/'HOLD_V7R2.json').exists():return dict(state='HOLD',actions=[])
    manifest = load_manifest(root, verify=True)
    checkpoint = optional(root / 'CHECKPOINT_V7R2.json')
    heartbeat = optional(root / 'COORDINATOR_HEARTBEAT.json')
    active = optional(root / 'ACTIVE_V7R2.json')
    actives = read_actives(root)
    host = optional(root / 'COORDINATOR_V7R2_HOST.json')
    coordinator_alive = same_process(heartbeat.get('process', {})) or same_process(host.get('process', {}))
    worker_alive = same_process(active.get('worker', {}))
    workers_alive = {name: same_process(row.get('worker', {})) for name, row in actives.items()}
    age = (max(0.0, datetime.now(timezone.utc).timestamp() - datetime.fromisoformat(heartbeat['timestamp_UTC']).timestamp())
           if heartbeat.get('timestamp_UTC') else None)
    actions = []
    if checkpoint.get('state') != 'COMPLETE' and not coordinator_alive:
        name = task_name(manifest, 'coordinator')
        if not name:
            raise PermissionError('COORDINATOR_DEDICATED_TASK_NAME_MISSING')
        subprocess.run(['schtasks.exe', '/Run', '/TN', name], check=True, capture_output=True)
        actions.append('RESTART_DEAD_COORDINATOR_WITH_ORPHAN_ADOPTION_AND_NO_DATE_RETRY')
    monitor = optional(root / 'MONITOR_PROCESS.json')
    if not same_process(monitor):
        name = task_name(manifest, 'monitor')
        if not name:
            raise PermissionError('MONITOR_DEDICATED_TASK_NAME_MISSING')
        subprocess.run(['schtasks.exe', '/Run', '/TN', name], check=True, capture_output=True)
        actions.append('RESTART_DEAD_READ_ONLY_MONITOR')
    sha_failures = []
    for name, row in checkpoint.get('dates', {}).items():
        if row.get('result') and sha(row['result']) != row['result_SHA']:
            sha_failures.append(name)
    value = dict(UTC=now(), run_id=manifest['run_id'], process=process(),
                 coordinator_alive=coordinator_alive, worker_alive=worker_alive,
                 workers_alive=workers_alive, active_worker_count=sum(workers_alive.values()),
                 B1_parallel_workers=1, B2_parallel_workers=3,
                 current_phase=active.get('arm'), current_day=active.get('day'),
                 heartbeat_age_seconds=age, healthy_solver_kill=False,
                 solver_settings_changed=False, terminal_date_retries=0,
                 actions=actions, completed_result_SHA_failures=sha_failures,
                 counts=counts(checkpoint) if checkpoint else None,
                 monitor_alive=same_process(monitor), state=checkpoint.get('state', 'NOT_STARTED'))
    atomic(root / 'WATCHDOG_STATUS.json', value)
    return value


if __name__ == '__main__':
    run(sys.argv[1])
