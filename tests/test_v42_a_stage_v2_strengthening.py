"""Tiny actual-matrix tests of the adopted integer gang/clique family."""
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest
import scipy.sparse as sp
from scipy.optimize import linprog

from v42_a_stage_domain_v2.lexstage import LinearSnapshot, Objective
from v42_a_stage_domain_v2.strengthening import (
    strengthen_histogram_capacity, verify_histogram_capacity_strengthening,
)


def fixture(mixed=False, optional=False, fixed_gpu=0):
    # x_early+x_late=2. known0=2*x_early+fixed_GPU; known2=2*x_late.
    snapshot = LinearSnapshot(sp.csr_matrix([[1., 1., 0., 0.],
                                            [-2., 0., 1., 0.],
                                            [0., -2., 0., 1.]]),
                              np.zeros(4), np.array([2., 2., 3., 3.]),
                              np.array(["=", "=", "="]), np.array([2., fixed_gpu, 0.]),
                              np.array(["I", "I", "C", "C"]),
                              (Objective("rho", (), 0), Objective("migration_count", (), 0),
                               Objective("shift_magnitude", ((1, 2),)),
                               Objective("prestart_relocation", (), 0)))
    job = SimpleNamespace(service_slots=1, gpu=2)
    graph = SimpleNamespace(events={"w": (("A", "B", 1),) if mixed else ()})
    data = ({}, {"j": job}, {}, SimpleNamespace(capacities={"A": 3}), {}, {"j": graph}, {}, {})
    descriptor = dict(units=[dict(uid="j", id="c_STAY", stay_count=not mixed,
                                  optional=optional,
                                  v=dict(y={("A", 0): ("v", 0), ("A", 2): ("v", 1)}))],
                      known={("A", 0): ("v", 2), ("A", 2): ("v", 3)})
    return snapshot, descriptor, data, np.arange(4, dtype=np.int64)


def lp(snapshot):
    return linprog([0., 2., 0., 0.], A_ub=snapshot.matrix[snapshot.senses == "<"],
                   b_ub=snapshot.rhs[snapshot.senses == "<"],
                   A_eq=snapshot.matrix[snapshot.senses == "="],
                   b_eq=snapshot.rhs[snapshot.senses == "="],
                   bounds=list(zip(snapshot.lower, snapshot.upper)),
                   method="highs", options={"time_limit": 2.})


def test_actual_known_gpu_rows_prove_rounding_and_raise_shift_root_bound():
    snapshot, descriptor, data, mapping = fixture()
    strengthened, proof = strengthen_histogram_capacity(snapshot, snapshot, descriptor, data, mapping)
    assert proof["PASS"] and proof["cuts_added"] == 2 and proof["cut_nnz"] == 2
    assert proof["same_integer_feasible_schedules"] and not proof["same_LP_projection_asserted"]
    assert lp(snapshot).fun == pytest.approx(1.)
    assert lp(strengthened).fun == pytest.approx(2.)
    assert verify_histogram_capacity_strengthening(snapshot, snapshot, strengthened,
        descriptor, data, mapping, proof)["PASS"]
    for early in range(3):
        late = 2 - early
        if 2 * early <= 3 and 2 * late <= 3:
            assert np.all(strengthened.matrix @ np.array([early, late, 2 * early, 2 * late]) <= strengthened.rhs)


@pytest.mark.parametrize("mixed,optional", [(True, False), (False, True)])
def test_unproved_singleton_mixed_and_optional_migration_units_excluded(mixed, optional):
    snapshot, descriptor, data, mapping = fixture(mixed=mixed, optional=optional)
    unchanged, proof = strengthen_histogram_capacity(snapshot, snapshot, descriptor, data, mapping)
    assert proof["cuts_added"] == 0
    assert (unchanged.matrix != snapshot.matrix).nnz == 0
    assert proof["mixed_singleton_flow_units_excluded"] == ["c_STAY"]


def test_actual_fixed_history_rhs_used_without_changing_physical_capacity():
    snapshot, descriptor, data, mapping = fixture(fixed_gpu=1)
    strengthened, proof = strengthen_histogram_capacity(snapshot, snapshot, descriptor, data, mapping)
    # At slot0 residual2 divides GPU2 exactly: its original LP is already count<=1.
    # Only slot2's fractional residual3 receives a rounding cut.
    assert proof["cuts_added"] == 1
    assert proof["cuts"][0]["slot"] == 2
    assert proof["unchanged_scientific_capacities"]
    assert lp(snapshot).fun == lp(strengthened).fun == pytest.approx(2.)


def test_corrupted_incidence_coefficient_and_proof_rejected():
    snapshot, descriptor, data, mapping = fixture()
    bad = deepcopy(descriptor)
    bad["units"][0]["v"]["y"] = {("A", 1): ("v", 0), ("A", 2): ("v", 1)}
    with pytest.raises(ValueError, match="INCIDENCE_DRIFT"):
        strengthen_histogram_capacity(snapshot, snapshot, bad, data, mapping)
    matrix = snapshot.matrix.copy(); matrix[1, 0] = -1.
    with pytest.raises(ValueError, match="COEFFICIENT_DRIFT"):
        strengthen_histogram_capacity(replace(snapshot, matrix=matrix), snapshot, descriptor, data, mapping)
    strengthened, proof = strengthen_histogram_capacity(snapshot, snapshot, descriptor, data, mapping)
    damaged = deepcopy(proof); damaged["cuts"][0]["upper"] = 0
    with pytest.raises(ValueError, match="HASH_DRIFT"):
        verify_histogram_capacity_strengthening(snapshot, snapshot, strengthened, descriptor, data, mapping, damaged)
    with pytest.raises(ValueError, match="ZERO_COLUMN_MAP"):
        strengthen_histogram_capacity(snapshot, snapshot, descriptor, data, mapping.astype(float))


def test_exact_cut_deduplication_and_bad_axis_rejected():
    snapshot, descriptor, data, mapping = fixture()
    # Additional known slot with the same occupancy coefficients gives the
    # identical cut; keep one canonical inequality rather than duplicate rows.
    snapshot = replace(snapshot, matrix=sp.hstack((snapshot.matrix, sp.csr_matrix((3, 1))), format="csr"),
                       lower=np.r_[snapshot.lower, 0.], upper=np.r_[snapshot.upper, 3.],
                       vtypes=np.append(snapshot.vtypes, "C"))
    addition = sp.csr_matrix([[-2., 0., 0., 0., 1.]])
    snapshot = replace(snapshot, matrix=sp.vstack((snapshot.matrix, addition), format="csr"),
                       senses=np.append(snapshot.senses, "="), rhs=np.r_[snapshot.rhs, 0.])
    data[3].capacities["A"] = 3
    data[1]["j"].service_slots = 2
    descriptor["known"][("A", 1)] = ("v", 4)
    _, proof = strengthen_histogram_capacity(snapshot, snapshot, descriptor, data, np.arange(5))
    assert proof["cuts_added"] == 2  # Same early-count inequality at slots0/1 kept once.
    del descriptor["known"][("A", 1)]
    descriptor["known"][("A", -1)] = ("v", 4)
    # Negative slot violates full occupancy incidence and must fail closed.
    with pytest.raises(ValueError, match="INCIDENCE_DRIFT"):
        strengthen_histogram_capacity(snapshot, snapshot, descriptor, data, np.arange(5))


def test_valid_partial_zero_mapping():
    current, descriptor, data, _ = fixture()
    original = replace(current, matrix=sp.hstack((current.matrix, sp.csr_matrix((3, 1))), format="csr"),
                       lower=np.r_[current.lower, 0.], upper=np.r_[current.upper, 0.],
                       vtypes=np.append(current.vtypes, "C"))
    mapping = np.array([0, 1, 2, 3, -1], dtype=np.int64)
    strengthened, proof = strengthen_histogram_capacity(original, current, descriptor, data, mapping)
    assert proof["cuts_added"] == 2 and strengthened.matrix.shape[1] == 4
    assert proof["same_integer_feasible_schedules"]


def test_current_binding_types_bounds_and_objectives_must_preserve_source():
    original, descriptor, data, mapping = fixture()
    # The source binding cannot justify a cut if the current actual matrix no
    # longer enforces that physical equation.
    matrix = original.matrix.copy(); matrix[1, 0] = -1.
    with pytest.raises(ValueError, match="CURRENT_GPU_BINDING_ROW"):
        strengthen_histogram_capacity(original, replace(original, matrix=matrix), descriptor, data, mapping)
    with pytest.raises(ValueError, match="RETAINED_COLUMN_BOUNDS_TYPES"):
        strengthen_histogram_capacity(original, replace(original, vtypes=np.array(["C", "I", "C", "C"])),
                                      descriptor, data, mapping)
    with pytest.raises(ValueError, match="RETAINED_COLUMN_BOUNDS_TYPES"):
        strengthen_histogram_capacity(original, replace(original, upper=np.array([2., 2., 4., 3.])),
                                      descriptor, data, mapping)
    objectives = tuple(replace(o, constant=1) if o.name == "shift_magnitude" else o for o in original.objectives)
    with pytest.raises(ValueError, match="PROJECTED_SCIENTIFIC_OBJECTIVES"):
        strengthen_histogram_capacity(original, replace(original, objectives=objectives), descriptor, data, mapping)


def test_independent_verifier_rejects_truncated_or_wrong_actual_binding_proof():
    import hashlib
    import json
    original, descriptor, data, mapping = fixture()
    strengthened, proof = strengthen_histogram_capacity(original, original, descriptor, data, mapping)
    for damage in ("GPU_per_column", "current_binding_row"):
        bad = deepcopy(proof)
        if damage == "GPU_per_column":
            bad["cuts"][0][damage] = []
        else:
            bad["cuts"][0][damage] = 0
        bad["cut_payload_sha256"] = hashlib.sha256(json.dumps(bad["cuts"], sort_keys=True,
            separators=(",", ":")).encode()).hexdigest()
        with pytest.raises(ValueError, match="CURRENT_GPU_BINDING_ROW_OR_COUNT_AXES"):
            verify_histogram_capacity_strengthening(original, original, strengthened,
                descriptor, data, mapping, bad)
