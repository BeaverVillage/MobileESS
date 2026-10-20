from pathlib import Path
import pytest
from v44_recovery_r029_switch import operations as switch
from v44.common import atomic, record


def test_campaign_worker_and_coordinator_route_to_user_switch():
    for mode in ('--worker', '--coordinator'):
        original = ['python', '-u', '-m', switch.ALGORITHM, mode, 'request.json']
        actual = switch.command(original)
        assert actual[3] == switch.ENTRY
        assert actual[-2:] == ['--algorithm', switch.ALGORITHM]
        assert original[3] == switch.ALGORITHM


def test_other_subprocesses_are_unchanged():
    for args in ('some shell command', ['python', '-m', 'unrelated'], ['python', '-u', '-m', switch.ALGORITHM, '--handover']):
        assert switch.command(args) == args


def test_only_original_interrupted_case_is_ready(monkeypatch):
    from v44_recovery_r029 import failure_continue
    monkeypatch.setattr(switch, 'authority', lambda: {})
    monkeypatch.setattr(Path, 'exists', lambda p: p.name == 'USER_INTERRUPTION.json')
    monkeypatch.setattr(switch.base, 'needs_retry', lambda p, r: False)
    monkeypatch.setattr(failure_continue, 'deferred_dates', lambda p: {switch.KEY, ('2025-05-06', 'B1')})
    monkeypatch.setattr(switch.base, 'latest', lambda *a: switch.PARENT)
    with switch.install():
        assert switch.base.needs_retry(switch.PARENT, {'PASS': False})
        assert not switch.base.needs_retry(switch.PARENT, {'PASS': True})
        assert not switch.base.needs_retry(switch.PARENT.with_name('attempt002'), {'PASS': False})
        assert failure_continue.deferred_dates('ops') == {('2025-05-06', 'B1')}
        monkeypatch.setattr(switch.base, 'latest', lambda *a: switch.PARENT.with_name('attempt002'))
        assert switch.KEY in failure_continue.deferred_dates('ops')


def test_install_restores_original_functions():
    from v44_recovery_r029 import failure_continue, wall_resume
    old = (switch.base.needs_retry, switch.base.decorate, switch.base.subprocess.Popen,
           failure_continue.deferred_dates, wall_resume.validate_parent)
    with switch.install():
        assert wall_resume.validate_parent is switch.validate_parent
    assert old == (switch.base.needs_retry, switch.base.decorate, switch.base.subprocess.Popen,
                   failure_continue.deferred_dates, wall_resume.validate_parent)


def test_authority_rejects_code_or_evidence_changes(tmp_path, monkeypatch):
    permit = tmp_path/'permit.json'; proof = tmp_path/'proof.json'; evidence = tmp_path/'evidence.json'
    for p in (permit, evidence): atomic(p, {'ok': True})
    atomic(proof, {'PASS': True})
    auth = tmp_path/'auth.json'
    value = dict(algorithm_permit=record(permit), validation=record(proof), sources=switch.sources(),
                 evidence=[record(evidence)], parent=str(switch.PARENT), May02_A2_Native_start=0,
                 May07_resume='COMPLETED_A1_THEN_NEW_ACTUAL', user_authorized=True)
    atomic(auth, value)
    monkeypatch.setattr(switch, 'AUTH', auth); monkeypatch.setattr(switch.base, 'PERMIT', permit)
    assert switch.authority()['user_authorized']
    atomic(evidence, {'ok': False})
    with pytest.raises(ValueError, match='SOURCE_SHA_DRIFT'): switch.authority()


def test_other_parent_keeps_original_admission(monkeypatch, tmp_path):
    monkeypatch.setattr(switch, 'wall_resume_original', lambda parent, output: ('original', parent, output))
    assert switch.validate_parent(tmp_path/'other', tmp_path/'audit')[0] == 'original'


def test_same_parent_rejects_live_worker_before_checkpoint_use(monkeypatch, tmp_path):
    monkeypatch.setattr(switch, 'authority', lambda: {})
    monkeypatch.setattr(switch, 'read', lambda p: dict(day=switch.KEY[0], arm=switch.KEY[1]))
    monkeypatch.setattr(switch, 'alive', lambda start: True)
    with pytest.raises(PermissionError, match='DEAD_B1_REQUIRED'):
        switch.validate_parent(switch.PARENT, tmp_path)


def test_request_marks_checkpoint_only_for_may07(monkeypatch, tmp_path):
    auth = tmp_path/'auth.json'; atomic(auth, {'evidence': []})
    monkeypatch.setattr(switch, 'AUTH', auth)
    monkeypatch.setattr(switch, 'authority', lambda: {})
    monkeypatch.setattr(switch.base, 'decorate', lambda case, permit: case)
    monkeypatch.setattr(switch.base, 'latest', lambda *a: switch.PARENT)
    with switch.install():
        target = switch.base.decorate(dict(day=switch.KEY[0], arm=switch.KEY[1], sources=[]), {})
        other = switch.base.decorate(dict(day='2025-05-02', arm='B3', sources=[]), {})
        assert target['wall_resume_parent'] == str(switch.PARENT)
        assert target['resume_completed_A1_only'] is True
        assert 'wall_resume_parent' not in other
        assert target['source_sha'] == switch.digest(target['sources'])
