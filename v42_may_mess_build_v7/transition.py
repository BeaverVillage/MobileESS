"""Formal source handoff. The current B1 Worker is adopted, never stopped."""
from copy import deepcopy
from pathlib import Path
import shutil
import subprocess
import time
from .common import ROOT, read, record, atomic, now, sha, digest, same_process


def hold_previous(root, *, source_version):
    from v42_may_build_v6.coordinator import read_actives
    root = Path(root).resolve()
    active = read_actives(root)
    if any(row['arm'] != 'B1' for row in active.values()):
        raise PermissionError('SOURCE_SWITCH_CANNOT_TOUCH_RUNNING_B2')
    path = root / 'HOLD_V6.json'
    value = dict(reason='EXPLICIT_USER_B2_BUILD_VERSION_HANDOFF', next_source_version=source_version,
                 dispatch_only=True, healthy_worker_kill=False, active_worker_identities=active, UTC=now())
    if path.exists():
        existing = read(path)
        if (existing.get('reason') != value['reason'] or existing.get('next_source_version') != source_version):
            raise PermissionError('EXISTING_V6_HOLD_HAS_ANOTHER_AUTHORITY')
    else:
        atomic(path, value)
    return value


def previous_stopped(root):
    root = Path(root)
    receipt = root / 'COORDINATOR_V6_HOST.json'
    return not receipt.exists() or not same_process(read(receipt)['process'])


def admit(root, validation):
    from .policy import VERSION, MANIFEST, ATTEMPT, PRECISION, source_files, verify_policy
    from .storage import initialize_checkpoint
    root = Path(root).resolve()
    if (root / MANIFEST).exists():
        return verify_policy(root)
    if not (root / 'HOLD_V6.json').exists() or not previous_stopped(root):
        raise PermissionError('V7_SOURCE_SWITCH_REQUIRES_PREVIOUS_COORDINATOR_BOUNDARY')
    from v42_may_build_v6.policy import verify_policy as verify_previous
    previous = verify_previous(root)
    for receipt in validation.values():
        if record(receipt['path']) != receipt or read(receipt['path']).get('PASS') is not True:
            raise PermissionError('V7_SOURCE_SWITCH_LIGHT_GATE_NOT_PASS')
    boundary = root / 'BASE_CHECKPOINT_BOUNDARY_V7.json'
    if boundary.exists():
        raise PermissionError('V7_IMMUTABLE_CHECKPOINT_BOUNDARY_ALREADY_EXISTS')
    shutil.copyfile(root / 'CHECKPOINT_V6.json', boundary)
    checkpoint = read(boundary)
    if any(row['arm'] == 'B2' and row['status'] != 'PENDING' for row in checkpoint['dates'].values()):
        raise PermissionError('V7_CANNOT_RESET_OR_REPLACE_STARTED_B2_DATES')
    doc = deepcopy(previous)
    doc.update(schema=VERSION, attempt_id=ATTEMPT, precision=PRECISION,
        previous_manifest=record(root / 'CONTINUATION_V6_MANIFEST.json'), base_checkpoint=record(boundary),
        authorized_recovery_dates=[], input_cache_sources={},
        input_authority_root=str(Path(previous['scientific_authority']['path']).parent),
        implementation=dict(version=VERSION, sources=source_files(), source_SHA=digest(source_files())),
        validation=validation,
        tasks={role:'MobileESS_V42_B1B2_P1_'+previous['run_id']+'_MessBuildV7_'+role.title()
               for role in ('coordinator', 'monitor', 'watchdog')},
        source_HEAD=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        source_transition=dict(user_authorized=True, worker_restarts=0, completed_date_resets=0,
            inherited_worker_sources_preserved=True, B1_build_implementation='FROZEN_V6',
            B2_build_implementation=VERSION, B2_full_equivalence='DEFERRED_UNTIL_ALL_B1_WORKERS_EXIT',
            automatic_failed_date_retries=0), UTC=now())
    atomic(root / MANIFEST, doc)
    verify_policy(root)
    initialize_checkpoint(root, doc)
    return doc


def activate(root):
    from .policy import MANIFEST
    from .windows import register_campaign_tasks, start
    root = Path(root)
    doc = read(root / MANIFEST)
    registration = register_campaign_tasks(root, doc)
    # Replace only the read-only monitor by exact identity. Native Workers and
    # the ordinary task definitions of all previous versions are preserved.
    monitor = root / 'MONITOR_PROCESS.json'
    if monitor.exists():
        identity = read(monitor)
        if same_process(identity):
            import psutil
            command = identity.get('command', [])
            if 'v42_may_build_v6.host' not in command or 'monitor' not in command:
                raise PermissionError('V7_CAN_REPLACE_ONLY_EXACT_V6_READ_ONLY_MONITOR')
            atomic(root / 'MONITOR_V6_BEFORE_V7.json', identity)
            peer = psutil.Process(identity['PID'])
            peer.terminate()
            peer.wait(timeout=10)
    started = {role:start(doc['tasks'][role]) for role in ('monitor', 'coordinator', 'watchdog')}
    value = dict(UTC=now(), registration=registration, started=started, worker_kills=0,
                 previous_source_files_changed=0, logoff_persistence='NOT_PROVEN')
    atomic(root / 'SOURCE_TRANSITION_ACTIVATION_V7.json', value)
    return value


def execute(root, validation):
    from .policy import VERSION
    hold_previous(root, source_version=VERSION)
    # This wait is only for the Coordinator's cooperative dispatch boundary.
    # It does not delay or throttle a worker or consume its Native account.
    deadline = time.monotonic() + 15
    while not previous_stopped(root):
        if time.monotonic() >= deadline:
            raise TimeoutError('V6_COORDINATOR_BOUNDARY_NOT_OBSERVED')
        time.sleep(.2)
    doc = admit(root, validation)
    return dict(manifest=record(Path(root) / 'CONTINUATION_V7_MANIFEST.json'), activation=activate(root),
                source_version=doc['implementation']['version'])
