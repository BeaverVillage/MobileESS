"""Reuse admission must preserve provenance and reject altered evidence."""
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from reuse_svr11_completed import verify_reuse
from v42_pr134_b1.common import atomic,record

def case(tmp_path):
    evidence=tmp_path/'original_RESULT.json';evidence.write_bytes(b'original immutable result')
    proof=tmp_path/'reuse'/'day.json'
    v=dict(PASS=True,arm='B0',day='2025-05-31',validation_source_SHA='current',
        execution_source_SHA='original',original_result=str(evidence),
        original_result_SHA=record(evidence)['sha256'],evidence=[record(evidence)],
        validation=dict(PASS=True,source_SHA='original',Native_Runtime=0,wall_seconds=101.3))
    atomic(proof,v)
    row=dict(arm='B0',day=v['day'],result=str(evidence),result_SHA=v['original_result_SHA'],reuse_proof=record(proof))
    return row,v,proof,evidence

def test_preserves_original_execution_and_runtime(tmp_path):
    row,v,proof,evidence=case(tmp_path);before=evidence.read_bytes()
    result=verify_reuse(tmp_path,dict(execution_SHA='current'),row)
    assert result['execution_source_SHA']=='original'
    assert result['validation_source_SHA']=='current' and result['wall_seconds']==101.3
    assert result['reused'] and evidence.read_bytes()==before

@pytest.mark.parametrize('change',['evidence','proof','day','current_sha'])
def test_rejects_drift_and_cross_identity(tmp_path,change):
    row,v,proof,evidence=case(tmp_path);m=dict(execution_SHA='current')
    if change=='evidence':evidence.write_bytes(b'altered')
    elif change=='proof':proof.write_bytes(b'{}')
    elif change=='day':row['day']='2025-05-30'
    elif change=='current_sha':m['execution_SHA']='foreign'
    with pytest.raises(ValueError):verify_reuse(tmp_path,m,row)
