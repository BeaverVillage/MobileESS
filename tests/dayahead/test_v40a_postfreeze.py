from dataclasses import replace
import json
from types import SimpleNamespace
import pytest

from dayahead.v33m.mess_trajectory import MessTrajectory, MessTrajectorySlot
from dayahead.v40a.postfreeze import verify_after_freeze
from dayahead.v40a.invariants import validate_joint, route_sha
from dayahead.v39l.infrastructure import durable_atomic_json


def trajectory():
    return MessTrajectory((MessTrajectorySlot('MESS01',0,'CONNECTED','STA01',None,None,(),None,0,0,0,0,0,None,0,0,0,0,100,.5),))


def run(tmp_path, *, violations=0, wrong_sha=False, change_route=False):
    calls = []
    def fresh(jobs, mess, sha, output):
        saved = json.loads((output.parent / 'FINAL_JOINT_DECISION.json').read_text())
        assert validate_joint(saved) == sha
        assert (output.parent / 'JOINT_DECISION_PAYLOAD.json').is_file()
        calls.append('fresh')
        return SimpleNamespace(schedule_sha256='x'*64 if wrong_sha else sha,
                               summary={'physical_violation': calls.count('fresh') <= violations})
    def restore(jobs, mess, fresh, sha, iteration):
        calls.append('restore')
        row = replace(mess.slots[0], p_kw=iteration,
                      service_id='STA02' if change_route else 'STA01')
        return MessTrajectory((row,)), {'iteration': iteration}
    result = verify_after_freeze([{'job_uid':'a'}], trajectory(), {'input':'a'*64}, tmp_path,
                                 fresh_call=fresh, restore_call=restore,
                                 validate_trajectory=lambda *_: None, max_rounds=2,
                                 write=durable_atomic_json)
    return result, calls


def test_fresh_and_actual_bind_same_joint_after_on_disk_freeze(tmp_path):
    result, calls = run(tmp_path)
    assert calls == ['fresh']
    sha = result['joint']['FINAL_JOINT_DECISION_SHA']
    assert result['actual']['FINAL_JOINT_DECISION_SHA'] == result['fresh'].schedule_sha256 == sha


def test_restoration_preserves_route_and_refreezes_pq(tmp_path):
    result, calls = run(tmp_path, violations=1)
    assert calls == ['fresh', 'restore', 'fresh']
    assert route_sha(result['trajectory'].slots) == route_sha(trajectory().slots)
    assert result['report']['rounds'][0]['joint_sha256'] != result['report']['rounds'][1]['joint_sha256']
    assert result['report']['route_search_calls'] == 0


def test_restoration_limit_fails_closed(tmp_path):
    with pytest.raises(RuntimeError, match='FAILED_CLOSED'):
        run(tmp_path, violations=100)
    assert json.loads((tmp_path / 'POSTFREEZE_VERIFICATION.json').read_text())['Fresh_calls'] == 3


def test_restoration_cannot_change_route(tmp_path):
    with pytest.raises(RuntimeError, match='DISCRETE_MUTATION'):
        run(tmp_path, violations=1, change_route=True)


def test_fresh_wrong_joint_never_reaches_actual(tmp_path):
    with pytest.raises(RuntimeError, match='FRESH_JOINT_SHA_MISMATCH'):
        run(tmp_path, wrong_sha=True)
    assert not (tmp_path / 'ACTUAL_FIXED_REPLAY.json').exists()
