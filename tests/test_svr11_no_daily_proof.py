from types import SimpleNamespace
from unittest.mock import patch
import pytest
from v42_pr134_b1.common import atomic, record
from v42_svr11 import campaign_mode


def test_default_keeps_independent_replay():
    with patch('v42_svr11.authority.active',return_value=None):
        assert campaign_mode.permit() is None
    with patch('v42_svr11.authority.active',return_value={'independent_model_proof_replay':True}):
        assert campaign_mode.permit() is None


def manifest(tmp_path,**updates):
    path=tmp_path/'authority.json'
    atomic(path,dict(source_SHA='current',construction_algorithms_unchanged=True,
        user_authorized_no_daily_proof=True,**updates))
    return dict(execution_SHA='current',independent_model_proof_replay=False,
        validated_construction_algorithm=record(path))


def test_no_replay_receipt_does_not_claim_new_independent_proof(tmp_path):
    m=manifest(tmp_path)
    with patch('v42_svr11.authority.active',return_value=m):
        authority=campaign_mode.permit()
        value=campaign_mode.receipt(authority,removed_rows=10)
        assert value['independent_model_proof_replayed'] is False
        assert value['independent_verifier_wall_seconds']==0
        assert value['validated_construction_algorithm']==m['validated_construction_algorithm']


def test_tampered_authority_rejected(tmp_path):
    m=manifest(tmp_path)
    atomic(m['validated_construction_algorithm']['path'],{'user_authorized_no_daily_proof':True})
    with patch('v42_svr11.authority.active',return_value=m),pytest.raises(PermissionError,match='RECEIPT_DRIFT'):
        campaign_mode.permit()


def test_other_source_rejected(tmp_path):
    m=manifest(tmp_path);m['execution_SHA']='other'
    with patch('v42_svr11.authority.active',return_value=m),pytest.raises(PermissionError,match='BINDING_DRIFT'):
        campaign_mode.permit()


def test_current_transport_skips_replay_only_in_authorized_mode(tmp_path):
    from v42_may_campaign_native90.m_model import verify_transport
    m=manifest(tmp_path)
    compact=SimpleNamespace(original=SimpleNamespace(shape=(10,8)),A=SimpleNamespace(shape=(12,10)))
    presolve=SimpleNamespace(A=SimpleNamespace(shape=(9,7)))
    with patch('v42_svr11.authority.active',return_value=m):
        value=verify_transport(compact,presolve)
    assert value['retained_rows']==9 and value['retained_columns']==7
    assert value['independent_model_proof_replayed'] is False
    assert value['daily_deleted_row_replay_performed'] is False
