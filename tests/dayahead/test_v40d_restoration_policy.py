from dataclasses import replace
import json
from types import SimpleNamespace

import pytest

from dayahead.v40d import policy
from dayahead.v40a.postfreeze import verify_after_freeze
from dayahead.v33m.mess_trajectory import MessTrajectory, MessTrajectorySlot
from dayahead.v39l.infrastructure import durable_atomic_json


def sealed(tmp_path):
    identity = {'base_max_rounds': 5, 'max_rounds': 10,
                'changed_controls': ['max_restoration_rounds'],
                'voltage_limits': [0.95, 1.05], 'inherited_files': {}}
    value = {'status': 'APPROVED', 'identity': identity, 'policy_sha256': policy.digest(identity)}
    path = tmp_path / policy.POLICY_PATH
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(value))
    return value


def test_policy_scope_restores_globals_after_failure(tmp_path):
    from dayahead import v17_ac_restoration_contract as contract
    from dayahead.v37 import runner
    sealed(tmp_path)
    before = (contract.K_MAX, runner.PASS_ID, runner._input_authority, runner.write_status)
    with pytest.raises(RuntimeError, match='simulated failure'):
        with policy.applied(tmp_path, baseline_namespace=True):
            assert contract.K_MAX == 10 and runner.PASS_ID == 'V40D'
            raise RuntimeError('simulated failure')
    assert before == (contract.K_MAX, runner.PASS_ID, runner._input_authority, runner.write_status)


def test_result_fingerprint_cannot_be_reused_as_legacy(tmp_path):
    p = sealed(tmp_path)
    base = {'execution_fingerprint_sha256': 'a' * 64, 'K': 200, 'beam': 2}
    new = policy.case_fingerprint(base, p)
    assert new['execution_fingerprint_sha256'] != base['execution_fingerprint_sha256']
    assert new['planning_execution_fingerprint_sha256'] == base['execution_fingerprint_sha256']
    assert base == {'execution_fingerprint_sha256': 'a' * 64, 'K': 200, 'beam': 2}


@pytest.mark.parametrize('success_round', [6, 10, None])
def test_boundary_uses_fresh_after_last_allowed_correction(tmp_path, success_round):
    sealed(tmp_path)
    trajectory = MessTrajectory((MessTrajectorySlot('MESS01', 0, 'CONNECTED', 'STA01', None, None,
                     (), None, 0, 0, 0, 0, 0, None, 0, 0, 0, 0, 100, .5),))
    calls = {'fresh': 0, 'restore': 0}

    def fresh(jobs, mess, sha, output):
        k = calls['fresh']
        calls['fresh'] += 1
        return SimpleNamespace(schedule_sha256=sha, summary={'physical_violation': success_round is None or k < success_round})

    def restore(jobs, mess, value, sha, iteration):
        calls['restore'] += 1
        return MessTrajectory((replace(mess.slots[0], q_kvar=iteration),)), {'iteration': iteration}

    def run():
        with policy.applied(tmp_path):
            from dayahead.v17_ac_restoration_contract import K_MAX
            return verify_after_freeze([{'job_uid': 'a'}], trajectory, {'input': 'a' * 64}, tmp_path / 'result',
                fresh_call=fresh, restore_call=restore, validate_trajectory=lambda *_: None,
                max_rounds=K_MAX, write=durable_atomic_json)

    if success_round is None:
        with pytest.raises(RuntimeError, match='FAILED_CLOSED'):
            run()
        assert calls == {'fresh': 11, 'restore': 10}
    else:
        result = run()
        assert result['report']['restoration_rounds'] == success_round
        assert calls == {'fresh': success_round + 1, 'restore': success_round}


def test_pause_blocks_manual_and_automatic_launch(tmp_path):
    path = tmp_path / 'dayahead/artifacts/v40b_v40a_may_launch/USER_PAUSE.json'
    path.parent.mkdir(parents=True)
    path.write_text('{}')
    with pytest.raises(RuntimeError, match='CAMPAIGN_PAUSED_BY_USER'):
        policy.assert_campaign_not_paused(tmp_path)


def test_policy_rejects_tampering_and_inherited_drift(tmp_path):
    value = sealed(tmp_path)
    path = tmp_path / policy.POLICY_PATH
    value['identity']['max_rounds'] = 20
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match='NOT_SEALED'):
        policy.load_policy(tmp_path)
    value['identity']['max_rounds'] = 10
    source = tmp_path / 'source.py'
    source.write_text('modified')
    value['identity']['inherited_files'] = {'source.py': '0' * 64}
    value['policy_sha256'] = policy.digest(value['identity'])
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match='INHERITED_SOURCE_DRIFT'):
        policy.load_policy(tmp_path)


def test_fresh_progress_reports_effective_bound(tmp_path, monkeypatch):
    from dayahead.v37 import runner
    sealed(tmp_path)
    seen = []
    monkeypatch.setattr(runner, 'write_status', lambda *a, **k: seen.append(k['extra']))
    with policy.applied(tmp_path):
        runner.write_status('unused', extra={'restoration_round': 6, 'restoration_round_max': 5})
    assert seen[0]['restoration_round_max'] == 10


def test_supervisor_respects_pause_but_detects_unexpected_worker(tmp_path, monkeypatch):
    from dayahead.tools import v40c_supervise_once as supervisor
    monkeypatch.setattr(supervisor, 'ROOT', tmp_path)
    for name, value in [('V40A_MAY_PROGRESS.json', {'completed_days': ['2025-05-01']}),
                        ('V40B_EXECUTION_FREEZE.json', {}), ('USER_PAUSE.json', {})]:
        (tmp_path / name).write_text(json.dumps(value))
    monkeypatch.setattr(supervisor, 'inventory', lambda: {'orchestrators': [], 'workers': []})
    report = supervisor.observe()
    assert not report['incident_detected'] and report['action_taken'] == 'RESPECT_USER_PAUSE_NO_RESTART'
    monkeypatch.setattr(supervisor, 'inventory', lambda: {'orchestrators': [], 'workers': [{'pid': 123}]})
    assert supervisor.observe()['issues'] == ['PROCESS_RUNNING_DURING_USER_PAUSE']
