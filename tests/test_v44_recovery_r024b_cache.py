from copy import deepcopy
import inspect
from pathlib import Path
import textwrap

import pytest

from v44.common import read
from v44_recovery_r024b.a2_cache import ownership, verifier_body


def test_original_semantic_and_full_domain_tail_is_unchanged():
    from v42_may_campaign_native90.a_cache import load_current_date_physical_cache
    old = textwrap.dedent(inspect.getsource(load_current_date_physical_cache))
    new = verifier_body(load_current_date_physical_cache)
    mark = "    data_path = source / 'STATIC/DATA/DATA.pkl'"
    assert old[old.index(mark):] == new[new.index(mark):]


@pytest.fixture
def recorded_request():
    path = Path('D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/campaign004/2025-05-01/B3/attempt001/A2/request.json')
    q = read(path)
    return dict(q['physical_domain_request'], output=q['output']), q['physical_cache_case_proof']['path']


def test_recorded_accepted_a1_and_actual_a2_paths_are_admitted(recorded_request):
    q, proof = recorded_request
    result = ownership(q, ({'day':q['day']},), proof)
    assert result[1] == Path(q['_current_date_physical_cache']).resolve()
    assert result[2] == Path(q['output']).resolve()


@pytest.mark.parametrize('field,value', [
    ('day','2025-05-02'), ('arm','B3'), ('stage','A2'),
    ('root','D:/unrelated/A1'), ('case_root','D:/unrelated/attempt001'),
    ('campaign_root','D:/unrelated/campaign'), ('output','D:/unrelated/A2/OUTPUT'),
    ('_current_date_physical_cache','D:/unrelated/cache'),
])
def test_cross_date_arm_owner_and_unrelated_cache_are_denied(recorded_request, field, value):
    q, proof = recorded_request
    q = deepcopy(q)
    q[field] = value
    with pytest.raises((PermissionError, ValueError)):
        ownership(q, ({'day':q['day']},), proof)


def test_scientific_fresh_data_day_is_checked(recorded_request):
    q, proof = recorded_request
    with pytest.raises(ValueError, match='FRESH_DATA_DAY'):
        ownership(q, ({'day':'2025-05-02'},), proof)


@pytest.mark.parametrize('field', ['_physical_cache_identity','_expected_model_verification','_expected_complete_domain_hashes'])
def test_pinned_receipt_and_model_domain_identity_cannot_drift(recorded_request, field):
    q, proof = recorded_request
    q = deepcopy(q)
    q[field] = {}
    with pytest.raises((PermissionError, ValueError)):
        ownership(q, ({'day':q['day']},), proof)


def test_b3_cache_retry_requires_exact_a2_error_and_remains_bounded(tmp_path):
    from v44.common import atomic
    from v44_recovery_r024b.operations import needs_retry
    parent = tmp_path/'2025-05-01/B3/attempt001'
    result = dict(error="ValueError('INCOMPLETE_OR_FAILED_PARENT')")
    atomic(parent/'A2/RESULT.json',dict(error='OTHER'))
    assert not needs_retry(parent,result)
    atomic(parent/'A2/RESULT.json',dict(error="RuntimeError('A2_REQUIRED_COMPLETE_LOCAL_DOMAIN_REUSE_FAILED')"))
    assert needs_retry(parent,result)
    (parent/'RECOVERY_R024B_APPLIED.json').write_text('{}')
    assert not needs_retry(parent,result)
    assert not needs_retry(parent.with_name('attempt003'),result)
