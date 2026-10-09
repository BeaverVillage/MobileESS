"""Pure final-delivery binding attacks; no model builders or Native calls."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from v42_m1_research import audit_delivery as delivery
from v42_m1_research.check_joint import check_ledger


def _write(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj),encoding='utf8')


def _hash(path):return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def bound_run(tmp_path,monkeypatch):
    root=tmp_path/'repo';reports=root/'docs';base=root/'runtime/v42_m1_joint_gap_research'
    original=base/'registered';view=base/'registered_final_view'
    original.mkdir(parents=True);view.mkdir();reports.mkdir()
    monkeypatch.setattr(delivery,'ROOT',root);monkeypatch.setattr(delivery,'REPORTS',reports)
    checker=root/'v42_m1_research/check_joint.py';checker.parent.mkdir()
    checker.write_bytes(Path(__file__).resolve().parents[1].joinpath('v42_m1_research/check_joint.py').read_bytes())
    call=dict(track='LB',label='failed_count',case_sha='same_case',state='FAILED',
        Native_Runtime=100.,measured_Native_Runtime=100.,Native_Work=20.,
        requested_seconds=200.,allocated_native_seconds=200.,runtime_unavailable=False,
        runtime_accounting_scope='MEASURED',optimize_wall_seconds=110.)
    ledger=dict(case_sha='same_case',total_native_limit_seconds=5400.,Threads=1,
        scientific_tolerances=dict(Threads=1,MIPGap=.005,FeasibilityTol=1e-8,OptimalityTol=1e-8,IntFeasTol=1e-8),
        memory_limits=False,memory_automatic_stop=False,historical_ledgers_modified=False,
        inflight=None,calls=[call],transfers=[],allocations={'LB':3600.,'UB':1800.},
        Native_Runtime_sum=100.,native_measured_Runtime_sum=100.,track_Runtime={'LB':100.,'UB':0.},
        Native_Work_sum=20.,non_native_wall_costs=[dict(kind='build',label='case',wall_seconds=13.)],
        wall_seconds=125.,practical_wall_PASS=True,native_accounting_PASS=True,native_runtime_measurement_complete=True)
    raw=dict(case_sha='same_case',ledger=deepcopy(ledger))
    _write(original/'RESEARCH_TRACK_RESULTS.json',raw);_write(original/'NATIVE_RUNTIME_LEDGER.json',ledger)
    (original/'FINAL_VALID_UB_POINT.npz').write_bytes(b'original near-zero checkpoint retained')
    (original/'count_row_proof.json').write_text('{"original immutable cover":true}')
    (view/'FINAL_VALID_UB_POINT.npz').write_bytes(b'already validated saved exact RAW')
    (view/'NATIVE_RUNTIME_LEDGER.json').write_bytes((original/'NATIVE_RUNTIME_LEDGER.json').read_bytes())
    _write(view/'RESEARCH_TRACK_RESULTS.json',dict(raw,run_path=str(view)))
    files={p.name:_hash(p) for p in original.iterdir()}
    _write(reports/'SCIENTIFIC_MODEL_IDENTITY.json',dict(case_sha='same_case'))
    _write(reports/'FINAL_INDEPENDENT_REVIEW.json',dict(scientific_case_sha='same_case',
        final_admission=dict(unchanged_final_check_joint_source_sha256=_hash(checker))))
    creation=dict(PASS=True,case_sha='same_case',original_run=str(original),read_only_replay_view=str(view),
        original_native_ledger_sha256=_hash(original/'NATIVE_RUNTIME_LEDGER.json'),
        view_native_ledger_sha256=_hash(view/'NATIVE_RUNTIME_LEDGER.json'),original_files_SHA256=files,
        selected_view_packet=dict(path=str(view/'FINAL_VALID_UB_POINT.npz'),sha256=_hash(view/'FINAL_VALID_UB_POINT.npz')))
    receipt=dict(PASS=True,case_sha='same_case',checked_UB_packet=deepcopy(creation['selected_view_packet']),
        independent_native_accounting=check_ledger(ledger,'same_case'))
    _write(reports/'FINAL_ADMISSION_VIEW.json',creation);_write(reports/'JOINT_LB_UB_GAP.json',receipt)
    return root,reports,original,view


def _mutate(path,change):
    data=json.loads(path.read_text());change(data);_write(path,data)


def test_final_binding_recomputes_failed_call_cost_and_preserves_originals(bound_run):
    _,_,original,_=bound_run
    before={p.name:p.read_bytes() for p in original.iterdir()}
    checked=delivery.verify_final_binding(original)
    assert checked['PASS'] and checked['Native_Runtime']==100.
    assert checked['checker_accounting_freshly_recomputed_without_Native']
    assert checked['independent_final_gate']['PASS']
    assert {p.name:p.read_bytes() for p in original.iterdir()}==before


def test_different_run_cannot_reuse_existing_pass_receipt(bound_run):
    _,_,original,_=bound_run
    wrong=original.parent/'other_registered';wrong.mkdir()
    with pytest.raises(ValueError,match='ORIGINAL_RUN_MISMATCH'):
        delivery.verify_final_binding(wrong)


@pytest.mark.parametrize('file',['JOINT_LB_UB_GAP.json','FINAL_ADMISSION_VIEW.json','SCIENTIFIC_MODEL_IDENTITY.json'])
def test_case_receipt_mismatch_rejected(bound_run,file):
    _,reports,original,_=bound_run
    _mutate(reports/file,lambda d:d.update(case_sha='other_case'))
    with pytest.raises(ValueError,match='SCIENTIFIC_CASE_MISMATCH'):
        delivery.verify_final_binding(original)


def test_original_and_view_ledger_must_have_identical_bytes(bound_run):
    _,_,original,view=bound_run
    with (view/'NATIVE_RUNTIME_LEDGER.json').open('a') as stream:stream.write(' ')
    with pytest.raises(ValueError,match='LEDGER_BYTE_DRIFT'):
        delivery.verify_final_binding(original)


def test_original_finalized_result_cannot_have_different_ledger_snapshot(bound_run):
    _,_,original,_=bound_run
    _mutate(original/'RESEARCH_TRACK_RESULTS.json',lambda d:d['ledger'].update(Native_Runtime_sum=0.))
    with pytest.raises(ValueError,match='ORIGINAL_LEDGER_NOT_FINALIZED'):
        delivery.verify_final_binding(original)


def test_stale_accounting_pass_cannot_erase_failed_native_call(bound_run):
    _,reports,original,_=bound_run
    _mutate(reports/'JOINT_LB_UB_GAP.json',lambda d:d['independent_native_accounting'].update(Native_Runtime_sum=0.,failed_native_calls=0))
    with pytest.raises(ValueError,match='INDEPENDENT_ACCOUNTING_RECEIPT_DRIFT'):
        delivery.verify_final_binding(original)


def test_independent_gate_source_is_hash_checked_not_assumed(bound_run):
    root,_,original,_=bound_run
    (root/'v42_m1_research/check_joint.py').write_bytes(b'modified source after static review')
    with pytest.raises(ValueError,match='INDEPENDENT_CHECKER_SOURCE_DRIFT'):
        delivery.verify_final_binding(original)


def test_original_immutable_count_proof_drift_rejected(bound_run):
    _,_,original,_=bound_run
    (original/'count_row_proof.json').write_text('{"original immutable cover":false}')
    with pytest.raises(ValueError,match='ORIGINAL_PRODUCER_FILE_DRIFT'):
        delivery.verify_final_binding(original)


def test_checked_final_ub_must_be_this_view_packet(bound_run):
    _,reports,original,_=bound_run
    _mutate(reports/'JOINT_LB_UB_GAP.json',lambda d:d['checked_UB_packet'].update(path=str(original/'FINAL_VALID_UB_POINT.npz')))
    with pytest.raises(ValueError,match='CHECKED_UB_VIEW_PACKET_MISMATCH'):
        delivery.verify_final_binding(original)


def test_review_refuses_wrong_run_before_writing_status(bound_run,monkeypatch):
    from v42_m1_research import review
    _,reports,original,_=bound_run;monkeypatch.setattr(review,'REPORTS',reports)
    wrong=original.parent/'other_registered';wrong.mkdir()
    with pytest.raises(ValueError,match='ORIGINAL_RUN_MISMATCH'):
        review.review(wrong)
    assert not (reports/'FINAL_RESEARCH_STATUS.json').exists()


def test_delivery_refuses_wrong_run_before_source_and_resource_work(bound_run):
    _,reports,original,_=bound_run
    wrong=original.parent/'other_registered';wrong.mkdir()
    with pytest.raises(ValueError,match='ORIGINAL_RUN_MISMATCH'):
        delivery.final_audits(wrong)
    assert not (reports/'EXECUTION_PRESERVATION_AUDIT.json').exists()
