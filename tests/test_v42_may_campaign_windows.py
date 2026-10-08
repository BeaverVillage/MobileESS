"""Native=0 task policy/lifetime checks; no OS task is changed by unit tests."""
from pathlib import Path
import shutil
import threading
import time
import uuid
from unittest.mock import patch
from xml.etree import ElementTree as ET

import pytest

from v42_may_campaign.common import ROOT, atomic, process
from v42_may_campaign import windows


@pytest.fixture
def probe_root():
    base = ROOT / 'tmp/v42_may_campaign_windows_tests'
    base.mkdir(parents=True, exist_ok=True)
    root = base / uuid.uuid4().hex
    root.mkdir()
    try:
        yield root
    finally:
        assert root.resolve().is_relative_to(base.resolve())
        shutil.rmtree(root)


def test_interactive_task_policy_has_no_logoff_claim_or_campaign_probe_action(probe_root):
    task = windows.task_definition(probe_root, 'probe', python='python.exe', sid='S-1-5-test')
    find = lambda name: task.find('.//{' + windows.NS + '}' + name)
    assert find('LogonType').text == 'InteractiveToken'
    assert find('RunLevel').text == 'LeastPrivilege'
    assert find('ExecutionTimeLimit').text == 'PT0S'
    assert find('MultipleInstancesPolicy').text == 'IgnoreNew'
    assert find('AllowHardTerminate').text == 'false'
    assert find('Hidden').text == 'true'
    assert len(find('Triggers')) == 0
    assert 'process_probe launch' in find('Arguments').text
    assert 'v42_may_campaign.host' not in find('Arguments').text
    assert windows.LOGOFF_STATUS == 'LOGOFF_PERSISTENCE_NOT_PROVEN'


def test_campaign_task_actions_resume_coordinator_and_monitor_and_watchdog_each_minute(probe_root):
    for role in ('coordinator', 'monitor'):
        task = windows.task_definition(probe_root, role, python='python.exe', sid='S-1-5-test')
        assert task.find('.//{' + windows.NS + '}LogonTrigger') is not None
        assert ('v42_may_campaign.host ' + role) in task.find('.//{' + windows.NS + '}Arguments').text
    task = windows.task_definition(probe_root, 'watchdog', python='python.exe', sid='S-1-5-test')
    assert task.find('.//{' + windows.NS + '}Interval').text == 'PT1M'


def test_owned_existing_monitor_definition_can_be_verified_without_mutation(probe_root):
    name = windows.TASK_PREFIX + 'Monitor_existing'
    definition = windows.task_definition(probe_root, 'monitor', python='python.exe', sid='S-1-5-test')
    xml = ET.tostring(definition, encoding='unicode')
    (probe_root / (name + '_REGISTERED_TASK.xml')).write_text(xml, encoding='utf-8')
    with patch.object(windows, 'powershell', side_effect=[xml, 'S-1-5-test']) as calls:
        result = windows.reuse_registered_task(probe_root, 'monitor', name, python='python.exe')
    assert result['reused_owned_definition'] is True
    assert result['existing_task_modified'] is False
    assert calls.call_count == 2  # Export and user identity are both read-only.


def test_existing_task_is_never_overwritten(probe_root):
    with patch.object(windows, 'exists', return_value=True), patch.object(windows.subprocess, 'run') as create:
        with pytest.raises(PermissionError, match='ALREADY_EXISTS'):
            windows.register(probe_root, 'probe', windows.TASK_PREFIX + 'Probe_collision')
    create.assert_not_called()


def test_owned_export_missing_runlevel_requires_actual_limited_property_without_mutation(probe_root):
    name = windows.TASK_PREFIX + 'Monitor_export_omitted_default'
    definition = windows.task_definition(probe_root, 'monitor', python='python.exe', sid='S-1-5-test')
    principal = definition.find('.//{' + windows.NS + '}Principal')
    principal.remove(principal.find('{' + windows.NS + '}RunLevel'))
    xml = ET.tostring(definition, encoding='unicode')
    (probe_root / (name + '_REGISTERED_TASK.xml')).write_text(xml, encoding='utf-8')
    with patch.object(windows, 'powershell', side_effect=[xml, 'S-1-5-test', 'Limited']) as calls:
        receipt = windows.reuse_registered_task(probe_root, 'monitor', name, python='python.exe')
    assert receipt['PASS'] and receipt['existing_task_modified'] is False
    assert receipt['RunLevel_verification']['actual_service_RunLevel'] == 'Limited'
    assert receipt['RunLevel_verification']['XML_element_omitted'] is True
    assert calls.call_count == 3  # Export, SID and actual RunLevel are read-only.
    with patch.object(windows, 'powershell', side_effect=[xml, 'S-1-5-test', 'Highest']):
        with pytest.raises(PermissionError, match='POLICY_DRIFT:RunLevel'):
            windows.reuse_registered_task(probe_root, 'monitor', name, python='python.exe')


def test_cleanup_refuses_campaign_task_and_other_probe_root(probe_root):
    with patch.object(windows, 'powershell') as mutate:
        with pytest.raises(PermissionError, match='ONLY_OWN_PROBE'):
            windows.unregister_own_probe(windows.TASK_PREFIX + 'Coordinator_existing', probe_root)
    mutate.assert_not_called()
    task = windows.task_definition(probe_root / 'other', 'probe', python='python.exe', sid='S-1-5-test')
    xml = ET.tostring(task, encoding='unicode')
    with patch.object(windows, 'powershell', return_value=xml) as mutate:
        with pytest.raises(PermissionError, match='ROOT_IDENTITY_DRIFT'):
            windows.unregister_own_probe(windows.TASK_PREFIX + 'Probe_existing', probe_root / 'ours')
    assert mutate.call_count == 1  # Export is read-only; Unregister was never called.


def fake_receipts(root, *, in_job=False, kill_on_close=None):
    own = process()
    departed = dict(own, created=own['created'] + 1)
    atomic(root / 'LAUNCHER_RESULT.json', dict(PASS=True, process=departed, child=own))
    atomic(root / 'LAUNCHER_PROCESS.json', dict(process=departed, ancestry=[dict(name='svchost.exe')]))
    atomic(root / 'CHILD_PROCESS.json', dict(process=own, job=dict(in_any_job=in_job, kill_on_job_close=kill_on_close)))
    atomic(root / 'CHILD_HEARTBEAT.json', dict(heartbeat_number=1, timestamp_UTC='2026-10-09T00:00:00Z'))
    return own


def test_probe_requires_changing_heartbeat_after_launcher_exit(probe_root):
    fake_receipts(probe_root)
    stale = windows.observe_probe(probe_root, scheduler_owned=True, deadline_seconds=0.05)
    assert stale['PASS'] is False
    def update():
        time.sleep(0.15)
        atomic(probe_root / 'CHILD_HEARTBEAT.json', dict(heartbeat_number=2, timestamp_UTC='2026-10-09T00:00:01Z'))
    thread = threading.Thread(target=update)
    thread.start()
    changing = windows.observe_probe(probe_root, scheduler_owned=True, deadline_seconds=2)
    thread.join()
    assert changing['PASS'] is True
    assert changing['launcher_exit_observed'] is True
    assert changing['child_outside_all_job_objects'] is True


def test_probe_refuses_child_with_unknown_job_lifetime(probe_root):
    fake_receipts(probe_root, in_job=True)
    result = windows.observe_probe(probe_root, scheduler_owned=True, deadline_seconds=0.05)
    assert result['PASS'] is False


def test_creation_flags_do_not_inherit_kill_on_close_job_or_change_security_policy():
    from v42_may_campaign.process_probe import creation_flags_for_job, BREAKAWAY_FLAGS
    import subprocess
    assert creation_flags_for_job(dict(in_any_job=True, kill_on_job_close=False, breakaway_ok=False)) == (
        subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP)
    assert creation_flags_for_job(dict(in_any_job=True, kill_on_job_close=True, breakaway_ok=True)) == BREAKAWAY_FLAGS
    with pytest.raises(PermissionError, match='KILL_ON_CLOSE_NONBREAKAWAY'):
        creation_flags_for_job(dict(in_any_job=True, kill_on_job_close=True, breakaway_ok=False))
