"""Attacks on complete-packet seals, actual lambda pool and immutable scope."""
from copy import deepcopy
import json

import numpy as np
import pytest

from test_v42_mess_joint_compression import fixture_packet,identity
from v42_integration.mess_joint_compression import compress_joint_packet,pool_sha
from v42_integration.mess_verified_packet_cache import seal_verified_packet,restore_verified_packet
from v42_integration.m_engine import file_record


def sealed(tmp_path):
    p=fixture_packet();i=identity();c=compress_joint_packet(p,identity=i)
    r=seal_verified_packet(p,c,identity=i,folder=tmp_path)
    return p,c,i,r["approved_manifest"]["sha256"]


def test_complete_seal_restores_same_integer_LP_matrix_lift_objective_start(tmp_path):
    p,c,i,seal=sealed(tmp_path)
    restored,receipt=restore_verified_packet(p,identity=i,folder=tmp_path,approved_manifest_sha=seal)
    assert (restored[0]!=c[0]).nnz==0 and (restored[2]!=c[2]).nnz==0
    for k in c[1]:assert np.array_equal(restored[1][k],c[1][k])
    assert np.array_equal(restored[3],p[3])
    assert receipt["original_independent_proof_repeated"] is False
    assert receipt["new_pool_proof_reused"] is False


def test_seal_scope_refuses_new_case_pool_objective_and_packet_corruption(tmp_path):
    p,c,i,seal=sealed(tmp_path)
    for field in ("case_sha","physical_sha","pool_sha"):
        with pytest.raises(ValueError,match="ACTUAL_DOMAIN_DRIFT"):
            restore_verified_packet(p,identity=dict(i,**{field:"f"*64}),folder=tmp_path,approved_manifest_sha=seal)
    changed=deepcopy(p);changed[1]["objective"][0]=2.
    with pytest.raises(ValueError,match="ACTUAL_DOMAIN_DRIFT"):
        restore_verified_packet(changed,identity=i,folder=tmp_path,approved_manifest_sha=seal)
    data=bytearray((tmp_path/"A.npz").read_bytes());data[-10]^=1;(tmp_path/"A.npz").write_bytes(data)
    with pytest.raises(ValueError,match="PACKET_BYTES_DRIFT"):
        restore_verified_packet(p,identity=i,folder=tmp_path,approved_manifest_sha=seal)


def test_unsealed_or_modified_manifest_and_overwrite_are_rejected(tmp_path):
    p,c,i,seal=sealed(tmp_path)
    with pytest.raises(ValueError,match="EXTERNAL_APPROVED_MANIFEST_SHA_REQUIRED"):
        restore_verified_packet(p,identity=i,folder=tmp_path,approved_manifest_sha=None)
    m=json.loads((tmp_path/"MANIFEST.json").read_text());m["status"]="FAIL"
    (tmp_path/"MANIFEST.json").write_text(json.dumps(m))
    with pytest.raises(ValueError,match="MANIFEST_SEAL_DRIFT"):
        restore_verified_packet(p,identity=i,folder=tmp_path,approved_manifest_sha=seal)
    with pytest.raises(ValueError,match="CANNOT_OVERWRITE"):
        seal_verified_packet(p,c,identity=i,folder=tmp_path)


def test_passed_pool_sha_must_describe_actual_ordered_lambda_paths(tmp_path):
    p=fixture_packet();p[-1]["lambda_axis"]=[dict(unit="MESS01",ordinal=0,path=[1,2],name="lambda[MESS01,0]")]
    i=identity();c=compress_joint_packet(p,identity=i)
    with pytest.raises(ValueError,match="DOES_NOT_DESCRIBE"):
        seal_verified_packet(p,c,identity=i,folder=tmp_path)


def test_external_manifest_seal_still_requires_all_five_packet_members(tmp_path):
    p,c,i,_=sealed(tmp_path);m=json.loads((tmp_path/"MANIFEST.json").read_text())
    del m["files"]["START.npz"]
    (tmp_path/"MANIFEST.json").write_text(json.dumps(m))
    sealed_sha=file_record(tmp_path/"MANIFEST.json")["sha256"]
    with pytest.raises(ValueError,match="COMPLETE_PACKET_MEMBERS_REQUIRED"):
        restore_verified_packet(p,identity=i,folder=tmp_path,approved_manifest_sha=sealed_sha)
