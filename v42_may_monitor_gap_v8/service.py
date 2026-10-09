"""Separate owned Scheduler tasks replace only the exact read-only monitor."""
from contextlib import contextmanager
from pathlib import Path
import subprocess
import sys
from xml.etree import ElementTree as ET
import psutil
from v42_pr134_b1.common import ROOT, atomic, read, record, sha, now, same_process
from v42_may_campaign_native90.common import exclusive_lock, LockBusy
from v42_may_campaign_native90.a_routing import rebound
from v42_may_mess_build_v7 import windows
from v42_may_mess_build_v7.policy import MANIFEST, verify_policy

PERMIT = 'MONITOR_GAP_V8R2_PERMIT.json'


def sources():
    return {p.relative_to(ROOT).as_posix():sha(p) for p in sorted(Path(__file__).parent.iterdir())
            if p.is_file() and p.suffix in ('.py', '.html')}


def verify(root):
    root = Path(root).resolve()
    doc = read(root / PERMIT)
    if (doc['sources'] != sources() or record(root / MANIFEST) != doc['campaign_manifest']
            or record(doc['validation']['path']) != doc['validation']
            or read(doc['validation']['path']).get('PASS') is not True):
        raise PermissionError('READ_ONLY_MONITOR_V8_PIN_DRIFT')
    return doc


def definition(root, role, **kwargs):
    doc = windows.task_definition(root, role, **kwargs)
    doc.find('.//{' + windows.NS + '}Arguments').text = subprocess.list2cmdline([
        '-B', '-X', 'utf8', '-m', 'v42_may_monitor_gap_v8.host', role, str(Path(root).resolve())])
    return doc


def activate(root, validation):
    root = Path(root).resolve()
    campaign = verify_policy(root)
    path = root / PERMIT
    if not path.exists():
        if record(validation['path']) != validation or read(validation['path']).get('PASS') is not True:
            raise PermissionError('READ_ONLY_MONITOR_V8_TESTS_REQUIRED')
        atomic(path, dict(UTC=now(),deployment_revision=2,source_HEAD=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            sources=sources(), campaign_manifest=record(root / MANIFEST), validation=validation,
            optimizer_changes=0, completed_result_changes=0, existing_task_changes=0,
            tasks={role:'MobileESS_V42_B1B2_P1_'+campaign['run_id']+'_MonitorGapV8R2_'+role.title()
                   for role in ('monitor','watchdog')}))
    doc = verify(root)
    register = rebound(windows.register, dict(windows.register.__globals__, task_definition=definition))
    reuse = rebound(windows.reuse_registered_task,
                    dict(windows.reuse_registered_task.__globals__, task_definition=definition))
    registrations = {role:(reuse(root,role,name) if windows.exists(name) else register(root,role,name))
                     for role,name in doc['tasks'].items()}
    identity_path = root / 'MONITOR_PROCESS.json'
    if identity_path.exists():
        peer = read(identity_path)
        if same_process(peer) and peer.get('command',[])[1:] == [
                '-B','-X','utf8','-m','v42_may_monitor_gap_v8.host','monitor',str(root)]:
            atomic(root/'MONITOR_GAP_V8_BEFORE_R2.json',dict(UTC=now(),process=peer,worker_kills=0))
            current = psutil.Process(peer['PID'])
            current.terminate()
            current.wait(timeout=10)
    started = {role:windows.run_task(name) for role,name in doc['tasks'].items()}
    result = dict(UTC=now(),permit=record(path),registration=registrations,started=started,
                  optimizer_changes=0, existing_task_changes=0, logoff_persistence=windows.LOGOFF_STATUS)
    atomic(root/'MONITOR_GAP_V8R2_ACTIVATION.json',result)
    return result


@contextmanager
def monitor_scope(root):
    root = Path(root).resolve()
    verify(root)
    try:
        with exclusive_lock(root / 'MONITOR_GAP_V8.lock'):
            identity_path = root / 'MONITOR_PROCESS.json'
            if identity_path.exists():
                peer = read(identity_path)
                if same_process(peer):
                    expected = ['-B','-X','utf8','-m','v42_may_mess_build_v7.host','monitor',str(root)]
                    if peer.get('command', [])[1:] != expected:
                        raise PermissionError('V8_REPLACEMENT_REQUIRES_EXACT_OWNED_READ_ONLY_V7_MONITOR')
                    atomic(root/'MONITOR_V7R2_BEFORE_GAP_V8.json',dict(UTC=now(),process=peer,worker_kills=0))
                    process = psutil.Process(peer['PID'])
                    process.terminate()
                    process.wait(timeout=10)
            yield True
    except LockBusy:
        yield False


def watchdog(root):
    root = Path(root).resolve()
    doc = verify(root)
    path = root / 'MONITOR_PROCESS.json'
    peer = read(path) if path.exists() else {}
    healthy = same_process(peer) and peer.get('command',[])[1:] == [
        '-B','-X','utf8','-m','v42_may_monitor_gap_v8.host','monitor',str(root)]
    if not healthy:
        windows.run_task(doc['tasks']['monitor'])
    atomic(root/'MONITOR_GAP_V8_WATCHDOG.json',dict(UTC=now(),healthy=healthy,
        action=None if healthy else 'START_OWNED_READ_ONLY_MONITOR',worker_kills=0))
