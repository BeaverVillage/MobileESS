from types import SimpleNamespace
import numpy as np
import scipy.sparse as sp
import pytest
from v42_may_replay_v3.replay import inspect, ReplayNative
from v42_may_replay_v3.a_stage import classify_result, run


def case(x=0., pi=0., rc=0.):
    class Objective:
        def coefficients(self):
            return {}
    snapshot = SimpleNamespace(matrix=sp.csr_matrix([[1.]]), rhs=np.array([0.]),
        senses=np.array(['=']), lower=np.array([-np.inf]), upper=np.array([np.inf]),
        objectives=(Objective(),), fingerprint=lambda: 'original')
    return snapshot, dict(X=np.array([x]), Pi=np.array([pi]), RC=np.array([rc]))


def test_rejected_primal_keeps_original_tolerance_and_raw():
    s, raw = case(1.9073486328125e-6)
    old = raw['X'].copy()
    p = inspect(s, raw)
    assert not p['PASS'] and p['dual']['PASS']
    assert p['primal']['tolerance'] == 1e-6
    assert p['rejected_rows'][0]['row'] == 0
    np.testing.assert_array_equal(raw['X'], old)


def test_dual_failure_is_separate_from_primal():
    s, raw = case(rc=1.)
    p = inspect(s, raw)
    assert p['primal']['PASS'] and not p['dual']['PASS'] and not p['PASS']


@pytest.mark.parametrize('x, rejected', [(0., False), (1e-6, False), (2e-6, True)])
def test_delegate_once_preserves_runtime_and_persists_before_rejection(tmp_path, x, rejected):
    s, raw = case(x)
    class Delegate:
        calls = 0
        def solve(self, *args):
            self.calls += 1
            return dict(status=2, native_seconds=.417), raw
    original = Delegate()
    wrapper = ReplayNative(original)
    if rejected:
        with pytest.raises(ValueError, match='ORIGINAL_NUMERICAL_REPLAY_REJECTED'):
            wrapper.solve(s, tmp_path, 'PHASE_I')
        assert wrapper.failure
    else:
        rec, returned = wrapper.solve(s, tmp_path, 'PHASE_I')
        assert rec['native_seconds'] == .417 and returned is raw
    assert original.calls == 1
    assert (tmp_path/'ORIGINAL_NUMERICAL_REPLAY.json').is_file()


def test_classification_only_for_recorded_numerical_failure():
    result = dict(classification='IMPLEMENTATION_FAILURE', PASS=False, accepted=False,
        native_seconds=.417, native_calls=1)
    failure = dict(path='proof')
    assert classify_result(result, None) is result
    fixed = classify_result(result, failure)
    assert fixed['classification'] == 'NUMERICAL_FAILURE'
    assert fixed['native_seconds'] == .417 and fixed['native_calls'] == 1
    assert result['classification'] == 'IMPLEMENTATION_FAILURE'
    for status in ('PHYSICAL_FAILURE', 'TIME_LIMIT_NO_VALID_INCUMBENT', 'INPUT_FAILURE'):
        other = dict(result, classification=status)
        assert classify_result(other, failure) is other


def test_current_requests_cannot_activate_candidate():
    with pytest.raises(PermissionError, match='SEPARATELY_ADMITTED_REPLAY_VERSION_REQUIRED'):
        run({}, None)
