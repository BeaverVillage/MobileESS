import pytest
from dayahead.paper_analysis.storage import write_json
from dayahead.v40h.identity import file_record, IntegrityError
from dayahead.v40i.closeout import nonrecursive_identity, preflight


def test_self_referential_manifest_forbidden(tmp_path):
    path=tmp_path/'execution.json';write_json(path,{'old':'bytes'})
    with pytest.raises(IntegrityError,match='SELF_REFERENTIAL'):
        nonrecursive_identity(path,{'inputs':[file_record(path)]})
    with pytest.raises(IntegrityError,match='RECURSIVE_IDENTITY'):
        nonrecursive_identity(path,{'identity_SHA':'self'})


def test_leaf_only_identity_is_not_recursive(tmp_path):
    path=tmp_path/'leaf.json';write_json(path,{'x':1})
    value=nonrecursive_identity(tmp_path/'execution.json',{'inputs':[file_record(path)]})
    assert len(value['identity_SHA'])==64


def test_incomplete_authority_does_not_open_execution(tmp_path):
    write_json(tmp_path/'V40I_EXECUTION_AUTHORIZATION.json',{'complete_execution_identity':'FAIL','B2_B3_AUTHORIZED':'NO','FULL_MAY_AUTHORIZED':'NO'})
    with pytest.raises(IntegrityError,match='NOT_AUTHORIZED'):preflight(tmp_path)
