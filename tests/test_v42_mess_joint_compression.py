"""Attack case/pool cache identity and continuous same-pool row equivalence."""
from copy import deepcopy
from itertools import product

import numpy as np
import pytest
from scipy import sparse

from v42_integration.mess_joint_compression import compress_joint_packet, replay_same_pool_rows, pool_sha


def fixture_packet():
    A = sparse.csr_matrix(np.array([[1., -1.], [1., -1.], [1., -1.],
        [0., -1.], [1., 0.], [0., 0.], [1., 1.]], dtype=np.float64))
    d = dict(names=np.array(["Pdis[MESS01,STA01,0]", "lambda[MESS01,0]"]),
        rhs=np.array([.2, .4, .2, 1., 1., 0., 1.]),
        sense=np.array(["<", "<", "<", "<", "<", "<", "="]),
        lower=np.array([0., 0.]), upper=np.array([1., 1.]), types=np.array(["C", "B"]),
        objective=np.array([1., 0.]), constant=np.array(0.),
        row_names=np.array(["line_thermal_face[0,a,0]", "line_thermal_face[0,a,1]",
            "line_thermal_face[0,a,2]", "voltage_lower[0,a]", "PCS16[MESS01,STA01,0,0]",
            "energy_balance[MESS01,0]", "route_pool_one[MESS01]"]))
    return A, d, sparse.eye(2, format="csr"), np.array([0., 1.]), dict(PASS=True, restricted_to_FULL_inclusion=True)


def identity():
    return dict(source_sha="1"*64, case_sha="2"*64, physical_sha="3"*64, pool_sha="4"*64)


def test_continuous_and_integer_pool_domains_same_and_physical_rows_retained():
    packet = fixture_packet()
    compressed = compress_joint_packet(packet, identity=identity())
    A, d = packet[:2]
    C, cd = compressed[:2]
    assert C.shape[0] == 4
    assert cd["row_names"].tolist()[-3:] == d["row_names"].tolist()[-3:]
    for x in product(np.linspace(0., 1., 9), repeat=2):
        x = np.array(x)
        def feasible(B, dom):
            residual = B @ x - dom["rhs"]
            return np.all(np.where(dom["sense"] == "=", abs(residual), residual) <= 1e-14)
        assert feasible(A, d) == feasible(C, cd)
    assert replay_same_pool_rows(packet, compressed, [.5, .5])["PASS"]
    assert replay_same_pool_rows(packet, compressed, [.5, .5])["witness_domain"] == "LP_FRACTIONAL"
    assert replay_same_pool_rows(packet, compressed, [0., 1.])["witness_domain"] == "INTEGER"
    assert compressed[2] is packet[2]
    for k in ("names", "lower", "upper", "types", "objective", "constant"):
        assert compressed[1][k].tobytes() == packet[1][k].tobytes()


def test_cache_never_reuses_other_pool_case_physical_or_mutated_objective(tmp_path):
    packet = fixture_packet()
    first = compress_joint_packet(packet, identity=identity(), cache_dir=tmp_path)
    key = first[-1]["exact_joint_grid_compression"]["cache_key"]
    second = compress_joint_packet(packet, identity=identity(), cache_dir=tmp_path)
    assert second[-1]["exact_joint_grid_compression"]["cache_hit"] is True
    for field in identity():
        changed = dict(identity(), **{field: "f"*64})
        result = compress_joint_packet(packet, identity=changed, cache_dir=tmp_path)
        assert result[-1]["exact_joint_grid_compression"]["cache_hit"] is False
    corrupt = deepcopy(packet)
    corrupt[1]["objective"][0] = 2.
    result = compress_joint_packet(corrupt, identity=identity(), cache_dir=tmp_path)
    assert result[-1]["exact_joint_grid_compression"]["cache_key"] != key
    proof_file = tmp_path / key / "PROOF.npz"
    raw = bytearray(proof_file.read_bytes()); raw[-10] ^= 1; proof_file.write_bytes(raw)
    with pytest.raises(ValueError, match="PROOF_BYTES_DRIFT"):
        compress_joint_packet(packet, identity=identity(), cache_dir=tmp_path)


def test_identity_and_original_lift_authority_required():
    packet = fixture_packet()
    with pytest.raises(ValueError, match="PHYSICAL_POOL_SHA_REQUIRED"):
        compress_joint_packet(packet, identity=dict(identity(), physical_sha=""))
    with pytest.raises(ValueError, match="ORIGINAL_ROUTE_LIFT_PROOF_REQUIRED"):
        compress_joint_packet((*packet[:4], dict(PASS=False)), identity=identity())
    assert pool_sha({"MESS01": [[1, 2], [3, 4]]}) != pool_sha({"MESS01": [[3, 4], [1, 2]]})


def test_retained_helper_equality_implied_box_preserves_fractional_points():
    # Original broad helper boxes do not justify voltage deletion. Retained
    # equality + physical connection imply P=0 and z=0 for BOTH integer/LP.
    A=sparse.csr_matrix(np.array([[1.,0.,0.],[-2.,1.,0.],[0.,1.,0.],[0.,0.,1.]],dtype=float))
    d=dict(names=np.array(["Pch[MESS01,A,0]","response_voltage_shared[0,a]","lambda[MESS01,0]"]),
        rhs=np.array([0.,0.,1.,1.]),sense=np.array(["<","=","<","="]),
        lower=np.array([0.,-100.,0.]),upper=np.array([1.,100.,1.]),types=np.array(["C","C","B"]),
        objective=np.array([0.,1.,0.]),constant=np.array(0.),
        row_names=np.array(["connected_Pch[MESS01,A,0]","response_voltage_shared_binding[0,a]",
            "voltage_upper[0,a]","route_pool_one[MESS01]"]))
    packet=(A,d,sparse.eye(3,format="csr"),np.array([0.,0.,1.]),dict(PASS=True,restricted_to_FULL_inclusion=True))
    compressed=compress_joint_packet(packet,identity=identity())
    assert "voltage_upper[0,a]" not in compressed[1]["row_names"]
    assert "connected_Pch[MESS01,A,0]" in compressed[1]["row_names"]
    assert "response_voltage_shared_binding[0,a]" in compressed[1]["row_names"]
    receipt=compressed[-1]["exact_joint_grid_compression"]
    assert receipt["retained_helper_equality_support_proof"]["bounds_are_installed_in_model"] is False
    assert receipt["same_pool_LP_domain_equivalent"] is True
    assert np.array_equal(compressed[1]["upper"],d["upper"])
