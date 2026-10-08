from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from v42_m1_research import final_admission as admission
from v42_unified.storage import sha


def test_repoint_only_changes_operational_evidence_paths(tmp_path):
    original=tmp_path/'original';view=tmp_path/'view'
    original.mkdir();view.mkdir()
    for directory in (original,view):(directory/'dual.json').write_text('{"0":"1/3"}')
    value={'dual_evidence':{'path':str(original/'dual.json'),'sha256':sha(original/'dual.json')},
        'cover':{'scientific_source':str(original/'immutable_source'),'columns':[1,2]},
        'ledger':{'Native_Runtime_sum':42},'exact_bound':'3/5'}
    before=deepcopy(value)
    admission.repoint_evidence(value,original,view)
    assert value['dual_evidence']['path']==str(view/'dual.json')
    assert value['cover']==before['cover']
    assert value['ledger']==before['ledger']
    assert value['exact_bound']=='3/5'


def test_repoint_rejects_changed_copied_dual(tmp_path):
    original=tmp_path/'original';view=tmp_path/'view';original.mkdir();view.mkdir()
    (original/'dual.json').write_text('{"0":"1/3"}')
    (view/'dual.json').write_text('{"0":"2/3"}')
    value={'dual_evidence':{'path':str(original/'dual.json'),'sha256':sha(original/'dual.json')}}
    with pytest.raises(ValueError,match='BYTE_DRIFT'):admission.repoint_evidence(value,original,view)


def test_repoint_rejects_outside_run_evidence(tmp_path):
    original=tmp_path/'original';view=tmp_path/'view'
    value={'row_proof_evidence':{'path':str(tmp_path/'foreign.json'),'sha256':'x'}}
    with pytest.raises(ValueError,match='OUTSIDE_ORIGINAL_RUN'):admission.repoint_evidence(value,original,view)


def test_final_admission_requires_finished_immutable_ledger(tmp_path,monkeypatch):
    monkeypatch.setattr(admission,'ROOT',tmp_path)
    original=tmp_path/'runtime/v42_m1_joint_gap_research/unfinished'
    original.mkdir(parents=True)
    ledger={'inflight':{'label':'ACTIVE_NATIVE'}}
    (original/'NATIVE_RUNTIME_LEDGER.json').write_text(json.dumps(ledger))
    (original/'RESEARCH_TRACK_RESULTS.json').write_text(json.dumps({'ledger':ledger}))
    with pytest.raises(ValueError,match='NOT_FINALIZED'):
        admission.create_view(original,case=SimpleNamespace(case_sha='x'))
    assert not (original.parent/'unfinished_final_strict_admission_view').exists()
