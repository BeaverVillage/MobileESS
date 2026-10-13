import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from v42_integration.policy import digest
from v42_integration.pr129_recovery import _git_check,audit_reference
from v42_capacity.reference import build_reference


def candidate_fixture():
    rows=[]
    for index in range(151):
        rows.append(dict(job_uid='f'+str(index),boundary_source_state='RUNNING',
            current_model_site='AIDC01',GPU_gang=2 if index<145 else 1))
    for index in range(173):
        rows.append(dict(job_uid='m'+str(index),boundary_source_state='RUNNING',
            current_model_site=None,GPU_gang=2 if index<3 else 1))
    return dict(initial_source_roster=rows,excluded_UIDs=['completed'+str(i) for i in range(44)],
                private_future_runtime_or_completion_values_in_candidate=False)


def call_candidate(tmp_path,body):
    doc=dict(body,initial_state_sha=digest(body))
    path=tmp_path/'candidate.json';path.write_text(json.dumps(doc),encoding='utf8')
    return audit_reference(path,tmp_path/'current',tmp_path/'old',repo=tmp_path,output=tmp_path/'output')


def test_original_git_blob_sha_never_admits_drifted_local_reference(tmp_path):
    path=tmp_path/'REFERENCE.json';path.write_bytes(b'original')
    with patch('v42_integration.pr129_recovery.subprocess.check_output',return_value=b'original'):
        check=_git_check(tmp_path,'exact','REFERENCE.json',path)
        assert check['exact_bytes'] and check['git_blob_sha256']==hashlib.sha256(b'original').hexdigest()
        path.write_bytes(b'changed')
        with pytest.raises(ValueError,match='ORIGINAL_GIT_BLOB_BYTES_DRIFT'):
            _git_check(tmp_path,'exact','REFERENCE.json',path)


def test_private_future_values_rejected_before_reference_or_site_assignment(tmp_path):
    body=candidate_fixture();body['private_future_runtime_or_completion_values_in_candidate']=True
    with pytest.raises(ValueError,match='PRIVATE_FUTURE_VALUES_IN_DDAY_BOUNDARY'):
        call_candidate(tmp_path,body)
    assert not (tmp_path/'output').exists()


def test_duplicate_active_uid_and_completed44_reintroduction_rejected(tmp_path):
    body=candidate_fixture();body['initial_source_roster'][-1]['job_uid']='m0'
    with pytest.raises(ValueError,match='DDAY_RUNNING_DUPLICATE_UID'):
        call_candidate(tmp_path,body)
    body=candidate_fixture();body['excluded_UIDs'][0]='m0'
    with pytest.raises(ValueError,match='COMPLETED44_REINTRODUCED'):
        call_candidate(tmp_path,body)


def test_running_or_gpu_quantity_drift_is_not_normalized(tmp_path):
    body=candidate_fixture();body['initial_source_roster'][-1]['GPU_gang']=2
    with pytest.raises(ValueError,match='324_472_151_296_173_176_COUNTS_DRIFT'):
        call_candidate(tmp_path,body)


def test_exact_pr125_rejects_actual_end_grid_and_other_policy_inputs():
    for forbidden in ('end_time','actual_remaining','voltage','line_loading','actual_result'):
        with pytest.raises(ValueError,match='FUTURE_OR_GRID_REFERENCE_INPUT'):
            build_reference([{forbidden:1}],{'s':80},{'s':[80]},issue_time='2025-05-01T00:00:00+10:00')
