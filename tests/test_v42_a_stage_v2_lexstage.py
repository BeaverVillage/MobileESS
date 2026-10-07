"""Explicit tiny locked-stage fixtures; no production inputs or optimizer."""
from dataclasses import replace
from fractions import Fraction

import numpy as np
import pytest
import scipy.sparse as sp
from scipy.optimize import Bounds, LinearConstraint, linprog, milp

from v42_a_stage_domain_v2.lexstage import (
    LexLock, LinearSnapshot, Objective, add_integer_shift_variable, exact_gpu_count_rounding,
    integer_objective_proof, integer_optimality_certificate,
    lift_zero_projection, project_migration_zero, rebuild_locked_snapshot,
)


def count_fixture():
    return LinearSnapshot(sp.csr_matrix([[1., 1.], [2., 0.], [0., 2.]]),
                          np.array([0., 0.]), np.array([2., 2.]),
                          np.array(["=", "<", "<"]), np.array([2., 3., 3.]),
                          np.array(["I", "I"]),
                          (Objective("rho", (), 0), Objective("migration_count", (), 0),
                           Objective("shift_magnitude", ((0, 0), (1, 2))),
                           Objective("prestart_relocation", ((0, 0), (1, 0)))))


def solve_tiny_lp(snapshot, cost):
    snapshot.require()
    equality = snapshot.senses == "="
    inequality = snapshot.senses != "="
    matrix = snapshot.matrix[inequality].copy()
    rhs = snapshot.rhs[inequality].copy()
    directions = np.where(snapshot.senses[inequality] == ">", -1., 1.)
    matrix = sp.diags(directions) @ matrix
    rhs *= directions
    return linprog(cost, A_ub=matrix, b_ub=rhs,
                   A_eq=snapshot.matrix[equality], b_eq=snapshot.rhs[equality],
                   bounds=list(zip(snapshot.lower, snapshot.upper)), method="highs",
                   options={"time_limit": 2.})


def test_shift_integrality_direct_class_counts_and_corruption_rejected():
    snapshot = count_fixture()
    proof = integer_objective_proof(snapshot, "shift_magnitude")
    assert proof["PASS"] and proof["absolute_value_auxiliaries"] == 0
    with pytest.raises(ValueError, match="CONTINUOUS_OBJECTIVE"):
        integer_objective_proof(snapshot, "rho")
    corrupted = replace(snapshot, vtypes=np.array(["I", "C"]))
    with pytest.raises(ValueError, match="INTEGRALITY_NOT_PROVEN"):
        integer_objective_proof(corrupted, "shift_magnitude")
    objectives = tuple(replace(objective, terms=((1, Fraction(1, 2)),))
                       if objective.name == "shift_magnitude" else objective for objective in snapshot.objectives)
    with pytest.raises(ValueError, match="INTEGRALITY_NOT_PROVEN"):
        integer_objective_proof(replace(snapshot, objectives=objectives), "shift_magnitude")


def test_optional_integer_shift_variable_exact_definition_without_solve():
    import gurobipy as gp
    model = gp.Model("TINY_STATIC_INTEGER_SHIFT_DEFINITION")
    try:
        model.Params.OutputFlag = 0
        early = model.addVar(lb=0, ub=2, vtype=gp.GRB.INTEGER)
        late = model.addVar(lb=0, ub=2, vtype=gp.GRB.INTEGER)
        model.addConstr(early + late == 2)
        z, proof = add_integer_shift_variable(model, 2 * early + 3 * late)
        model.update()
        assert proof["PASS"] and proof["same_LP_projection"] and z.VType == "I"
        row = model.getRow(model.getConstrs()[-1])
        coefficients = {row.getVar(i).index: row.getCoeff(i) for i in range(row.size())}
        assert coefficients == {early.index: -2., late.index: -3., z.index: 1.}
        continuous = model.addVar(lb=0)
        with pytest.raises(ValueError, match="INTEGER_SHIFT"):
            add_integer_shift_variable(model, continuous)
    finally:
        model.dispose()


@pytest.mark.parametrize("component", ["migration_count", "shift_magnitude", "prestart_relocation"])
def test_integer_certificate_proves_optimum_without_relative_gap(component):
    result = integer_optimality_certificate(component, 11., 10.25,
        bound_independently_validated=True, primal_independently_validated=True, integrality_proven=True)
    assert result["PASS"] and result["safe_integer_lower_bound"] == 11
    assert not result["integer_domain_closure_proven"]
    assert not integer_optimality_certificate(component, 11., 10.,
        bound_independently_validated=True, primal_independently_validated=True, integrality_proven=True)["PASS"]
    assert not integer_optimality_certificate(component, 11.2, 10.25,
        bound_independently_validated=True, primal_independently_validated=True, integrality_proven=True)["PASS"]
    assert not integer_optimality_certificate(component, 11., 10.25)["PASS"]
    assert not integer_optimality_certificate(component, 11., float("inf"),
        bound_independently_validated=True, primal_independently_validated=True, integrality_proven=True)["PASS"]
    assert not integer_optimality_certificate(component, 11., 12.,
        bound_independently_validated=True, primal_independently_validated=True, integrality_proven=True)["PASS"]
    with pytest.raises(ValueError, match="CONTINUOUS_OBJECTIVE"):
        integer_optimality_certificate("rho", 1., .99)


def test_fresh_rebuild_preserves_original_rows_and_exact_current_locks():
    snapshot = count_fixture()
    locks = (LexLock("rho", 0., True, "1" * 64, 1e-7),
             LexLock("migration_count", 0, True, "2" * 64))
    rebuilt, receipt = rebuild_locked_snapshot(snapshot, locks)
    assert receipt["PASS"] and receipt["lock_rows"] == {"rho": 3, "migration_count": 4}
    assert (rebuilt.matrix[:3] != snapshot.matrix).nnz == 0
    assert np.array_equal(rebuilt.rhs[:3], snapshot.rhs)
    assert np.array_equal(rebuilt.vtypes, snapshot.vtypes)
    assert rebuilt.objectives == snapshot.objectives
    assert rebuilt.senses[-1] == "=" and rebuilt.rhs[-1] == 0
    with pytest.raises(ValueError, match="LEX_PREFIX"):
        rebuild_locked_snapshot(snapshot, (locks[1],))
    with pytest.raises(ValueError, match="NEW_RUN_PROVEN_LOCK"):
        rebuild_locked_snapshot(snapshot, (replace(locks[0], independently_verified=False),))
    with pytest.raises(ValueError, match="EXACT_INTEGER_LOCK"):
        rebuild_locked_snapshot(snapshot, (locks[0], replace(locks[1], value=1.5)))


def mixed_native_fixture():
    """Build only: a tiny actual migration flow, no native optimize/presolve."""
    import gurobipy as gp
    from v42_exact.support import ExactFactory
    from v42_job_capability import Job, Resources, ServiceBoundary
    from v42_root.factor import add_job
    job = Job("TINY_LOCKED_MIGRATION_FIXTURE", "PENDING", 0, 0, 0, "A", 3, 1,
              initial_sites=("A", "B"), checkpoint_authorized=True,
              duration_authority="EXPLICIT_TINY_FIXTURE")
    resources = Resources(dict(A=4, B=4), dict(A=(4,), B=(4,)),
                          {(link, t): 4 for link in ("AB", "BA") for t in range(8)},
                          {("A", "B"): ("AB",), ("B", "A"): ("BA",)},
                          8, 4, {}, {}, {}, restart_slots=1)
    boundary = ServiceBoundary("EXPLICIT_TINY_FIXTURE", True, True, (0, 1, 2), 8)
    graph = ExactFactory(resources, 8).graph(job, boundary)
    model = gp.Model("TINY_STATIC_LOCKED_MIGRATION_FIXTURE")
    try:
        model.Params.OutputFlag = 0
        unit = add_job(model, job, graph, resources, eliminate_f0=True,
                       eliminate_state=True, eliminate_depart=True,
                       eliminate_arrive=True, share_links=True)
        rho = model.addVar(lb=0, name="rho")
        model.update()
        snapshot = LinearSnapshot(model.getA(), np.array(model.getAttr("LB")),
                                  np.array(model.getAttr("UB")), np.array(model.getAttr("Sense")),
                                  np.array(model.getAttr("RHS")), np.array(model.getAttr("VType")),
            (Objective("rho", ((rho.index, 1),)),
             Objective("migration_count", tuple((x.index, 1) for x in unit["q"].values())),
             Objective("shift_magnitude", tuple((x.index, abs(start - job.reference_start))
                                                for (_, start), x in unit["y"].items())),
             Objective("prestart_relocation", tuple((x.index, int(site != job.reference_site))
                                                    for (site, _), x in unit["y"].items()))))
        indices = {family: {key: x.index for key, x in values.items() if isinstance(x, gp.Var)}
                   for family, values in unit.items()}
        return snapshot, indices
    finally:
        model.dispose()


def zero_locked_fixture():
    source, indices = mixed_native_fixture()
    locks = (LexLock("rho", 0., True, "1" * 64, 1e-7),
             LexLock("migration_count", 0, True, "2" * 64))
    locked, receipt = rebuild_locked_snapshot(source, locks)
    return locked, receipt["lock_rows"]["migration_count"], indices


def test_migration_zero_removes_all_native_route_wan_states_preserves_source_lp():
    from v42_a_stage_domain_v2.stay_projection import lp_counterexample
    locked, row, indices = zero_locked_fixture()
    projected, mapping, proof = project_migration_zero(locked, migration_lock_row=row)
    verification = proof.verify(locked)
    assert verification["PASS"] and verification["same_LP_projection"]
    assert not verification["singleton_source_finish_occupancy_replaced_by_histogram"]
    assert projected.matrix.shape[1] < locked.matrix.shape[1]
    for family, values in indices.items():
        if family not in ("y", "f0", "r0"):
            assert all(mapping[column] < 0 for column in values.values()), family
    point = np.zeros(locked.matrix.shape[1])
    example = lp_counterexample()
    for family in ("y", "f0", "r0"):
        for key, value in example["point"][family].items():
            point[indices[family][key]] = float(value)
    projected_point = point[mapping >= 0]
    lifted = lift_zero_projection(projected_point, mapping)
    assert np.array_equal(lifted, point)
    activities = locked.matrix @ lifted
    assert np.allclose(activities[locked.senses == "="], locked.rhs[locked.senses == "="])
    assert np.all(activities[locked.senses == "<"] <= locked.rhs[locked.senses == "<"] + 1e-10)
    assert np.all(activities[locked.senses == ">"] >= locked.rhs[locked.senses == ">"] - 1e-10)


def test_zero_projection_independent_corruption_and_nonzero_migration_rejected():
    locked, row, _ = zero_locked_fixture()
    _, _, proof = project_migration_zero(locked, migration_lock_row=row)
    rhs = locked.rhs.copy(); rhs[row] = 1.
    with pytest.raises(ValueError, match="ACTUAL_NONNEGATIVE_MIGRATION_ZERO_LOCK"):
        project_migration_zero(replace(locked, rhs=rhs), migration_lock_row=row)
    with pytest.raises(ValueError, match="SOURCE_HASH_DRIFT"):
        proof.verify(replace(locked, rhs=rhs))
    damaged = replace(proof, removed_columns=proof.removed_columns + (locked.matrix.shape[1] - 1,))
    with pytest.raises(ValueError, match="REMOVED_AXIS"):
        damaged.verify(locked)


def test_exact_zero_projection_lp_values_on_five_tiny_scientific_directions():
    locked, row, indices = zero_locked_fixture()
    projected, mapping, proof = project_migration_zero(locked, migration_lock_row=row)
    assert proof.verify(locked)["PASS"]
    rng = np.random.default_rng(20261007)
    movable = sorted(set(column for family in ("y", "f0", "r0") for column in indices[family].values()))
    for _ in range(5):
        cost = np.zeros(locked.matrix.shape[1])
        cost[movable] = rng.uniform(-1, 1, len(movable))
        before = solve_tiny_lp(locked, cost)
        after = solve_tiny_lp(projected, cost[mapping >= 0])
        assert before.success and after.success
        assert abs(before.fun - after.fun) <= 1e-9


def test_valid_whole_gang_rounding_improves_tiny_shift_root_one_to_two():
    snapshot = count_fixture()
    # Complete physical STAY starts 0/2 for D=1, GPU=2, site capacity 3.
    # Slot1 is immutable background-full, so no omitted intermediate start.
    before = solve_tiny_lp(snapshot, [0., 2.])
    assert before.success and before.fun == pytest.approx(1.)
    cuts = [exact_gpu_count_rounding(((0, 2),), 3),
            exact_gpu_count_rounding(((1, 2),), 3)]
    matrix = sp.vstack((snapshot.matrix, sp.eye(2)), format="csr")
    strengthened = replace(snapshot, matrix=matrix,
                           senses=np.array(["=", "<", "<", "<", "<"]),
                           rhs=np.array([2., 3., 3., cuts[0]["upper"], cuts[1]["upper"]]))
    after = solve_tiny_lp(strengthened, [0., 2.])
    assert after.success and after.fun == pytest.approx(2.)
    mip = milp([0., 2.], integrality=[1, 1], bounds=Bounds([0., 0.], [2., 2.]),
               constraints=LinearConstraint(snapshot.matrix, [2., -np.inf, -np.inf], [2., 3., 3.]),
               options={"time_limit": 2., "mip_rel_gap": 0.})
    assert mip.success and mip.fun == pytest.approx(after.fun)
    for early in range(3):
        late = 2 - early
        if 2 * early <= 3 and 2 * late <= 3:
            assert early <= cuts[0]["upper"] and late <= cuts[1]["upper"]
    assert all(cut["valid_for_all_integer_schedules"] and not cut["scientific_capacity_changed"] for cut in cuts)
    with pytest.raises(ValueError, match="INTEGER_GANG"):
        exact_gpu_count_rounding(((0, 2), (0, 2)), 3)
