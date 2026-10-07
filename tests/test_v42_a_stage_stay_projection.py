"""Build-free exact projection tests and two tiny static native row audits."""
from dataclasses import replace
from fractions import Fraction
from itertools import product
from types import SimpleNamespace

import pytest

from v42_a_stage_domain_v2.stay_projection import (
    HISTOGRAM_REFERENCE, RETAIN_EVENT_FLOW, add_stay_unit, incidence,
    lift_counts, lp_counterexample, project_extended, reconstruct_counts,
    representation_gate,
)
from v42_job_capability import Job


def fixture():
    job = Job("fixture", "PENDING", 0, 0, 2, "A", 2, 3,
              initial_sites=("A", "B"), duration_authority="EXPLICIT_SYNTHETIC_FIXTURE")
    return job, incidence(job, [("A", 0), ("A", 1), ("A", 2), ("B", 1)], 3, "c")


def test_integer_histogram_full_cardinality_and_bijection():
    _, spec = fixture()
    for amounts in product(range(4), repeat=4):
        if sum(amounts) != 3:
            continue
        counts = dict(zip(spec.starts, amounts))
        point = lift_counts(spec, counts, integral=True)
        assert project_extended(spec, point, integral=True) == point["y"]
        plans = reconstruct_counts(spec, counts)
        assert len(plans) == 3
        assert all(sum(b - a for _, a, b in plan.segments) == 2 for plan in plans)
        assert sum(point["r0"].values()) == 3 * 2
        assert sum(point["f0"].values()) == 3


def test_real_lp_histogram_unique_projection_with_optional_migration():
    _, spec = fixture()
    counts = dict(zip(spec.starts, [Fraction(1, 2), Fraction(1, 3),
                                    Fraction(1, 6), Fraction(1)]))
    point = lift_counts(spec, counts, migration_count=1)
    assert project_extended(spec, point, migration_count=1) == point["y"]
    assert all(0 <= x <= 3 for x in point["r0"].values())
    with pytest.raises(ValueError, match="FRACTIONAL_CLASS_COUNT"):
        lift_counts(spec, counts, migration_count=1, integral=True)


def test_class_count_conservation_rejects_job_loss_and_negative_migration():
    _, spec = fixture()
    with pytest.raises(ValueError, match="CLASS_EXACT_CARDINALITY"):
        lift_counts(spec, {("A", 0): 2})
    with pytest.raises(ValueError, match="CLASS_COUNT_BOUNDS"):
        lift_counts(spec, {("A", 0): 4}, migration_count=-1)


def test_objective_projection_keeps_absolute_shift_and_placement_reference():
    _, spec = fixture()
    counts = {("A", 0): 1, ("A", 2): 1, ("B", 1): 1}
    point = lift_counts(spec, counts, integral=True)
    direct = {name: sum(spec.objective_column(key)[name] * x for key, x in point["y"].items())
              for name in ("migration_count", "shift_magnitude", "prestart_relocation")}
    plans = reconstruct_counts(spec, counts)
    assert direct == dict(migration_count=0, shift_magnitude=3, prestart_relocation=1)
    assert direct["shift_magnitude"] == sum(abs(plan.start - spec.reference_start) for plan in plans)
    assert direct["prestart_relocation"] == sum(plan.initial_site != spec.reference_site for plan in plans)
    assert spec.objective_column(("A", 0))["inherited_signed_shift"] == -2


def test_runtime_grid_and_cc4_interfaces_exact_identity():
    job, spec = fixture()
    from v42_compact.native import completion_risk
    raw = dict(risk_nominal_completion_issue_slot=26, reference_end=4)
    bundle = dict(runtime_reserve_gamma=2.423057443558147,
                  runtime_survival_kernel=[1, .5, .25])
    provider = lambda site, end: completion_risk(job, raw, site, end, bundle)
    grid = {("line", 0): {("A", 0): -.25, ("A", 1): .125,
                           ("A", 2): -.5, ("B", 1): 2.0}}
    counts = {("A", 0): Fraction(1, 2), ("A", 2): Fraction(1, 2), ("B", 1): 2}
    point = lift_counts(spec, counts)
    combined = {}
    for key, count in point["y"].items():
        for row, value in spec.scientific_column(key, runtime_provider=provider,
                                                grid_gpu_rows=grid).items():
            combined[row] = combined.get(row, Fraction(0)) + value * count
    for (site, t), x in point["r0"].items():
        assert combined["known_GPU", site, t] == spec.gpu * x
    runtime = {}
    for (site, end), x in point["f0"].items():
        for (target_site, t), value in provider(site, end).items():
            key = "Runtime", target_site, t
            runtime[key] = runtime.get(key, Fraction(0)) + Fraction(value) * x
    assert {row: x for row, x in combined.items() if row[0] == "Runtime"} == runtime
    grid_lift = sum(Fraction(value) * spec.gpu * point["r0"].get(key, 0)
                    for key, value in grid[("line", 0)].items())
    assert combined["grid", "line", 0] == grid_lift
    assert all(row[0] != "CC4_forecast" for row in combined)
    # Every inherited CC4 headroom row depends on the same known/risk values;
    # its untouched anonymous forecast and reserve variables therefore bind
    # identically after substitution. This does not invent a new CC4 forecast.


def test_deterministic_incidence_and_exact_structural_counts():
    job, spec = fixture()
    assert incidence(job, reversed(spec.starts), 3, "c") == spec
    census = spec.structural_census()
    assert census["compact"]["integer"] == 4
    assert census["compact"]["continuous"] == 0
    assert census["extended_histogram"]["continuous"] == len(spec.states)
    assert census["already_projected_factor_stay_delta"] == dict(binary=0, integer=0, continuous=0, rows=0, nnz=0)


def test_event_flow_lp_counterexample_is_exact_and_forbids_universal_adoption():
    example = lp_counterexample()
    assert example["event_flow_rows_exact_pass"] and example["bounds_exact_pass"]
    job, _ = fixture()
    spec = incidence(replace(job, gpu=1, service_slots=example["service_slots"]),
                     example["starts"], 1)
    with pytest.raises(ValueError, match="FIXED_DURATION_PROJECTION_IDENTITY"):
        project_extended(spec, example["point"])
    gate = representation_gate(1, has_migration=True)
    assert not gate["adopt"] and gate["reference"] == RETAIN_EVENT_FLOW
    assert representation_gate(3, has_migration=True)["adopt"]
    assert representation_gate(1, has_migration=False)["adopt"]
    assert not representation_gate(3, has_migration=False, fixed=True)["adopt"]


def test_native_histogram_api_has_same_variables_and_coefficients_without_solve():
    import gurobipy as gp
    from v42_root.factor import stay
    job, spec = fixture()
    graph = SimpleNamespace(events=dict(y=spec.starts, w=()), fixed=None)
    models = [gp.Model("TINY_STATIC_HISTOGRAM_FIXTURE") for _ in range(2)]
    try:
        units = [stay(models[0], job, graph, 3, starts=spec.starts,
                      eliminate_f0=True, eliminate_state=True),
                 add_stay_unit(models[1], job, graph, 3, starts=spec.starts)]
        for model, unit in zip(models, units):
            model.Params.OutputFlag = 0
            model.addConstr(gp.quicksum(unit["y"].values()) == 3,
                            name="class_exact_cardinality")
            model.update()
        assert models[0].getAttr("VarName") == models[1].getAttr("VarName")
        assert models[0].getAttr("VType") == models[1].getAttr("VType")
        assert models[0].getA().toarray().tolist() == models[1].getA().toarray().tolist()
        def terms(expression):
            if isinstance(expression, gp.Var):
                return {expression.VarName: Fraction(1)}
            return {expression.getVar(i).VarName: Fraction(expression.getCoeff(i))
                    for i in range(expression.size())}
        for family in ("y", "f0", "r0"):
            assert set(units[0][family]) == set(units[1][family])
            for key in units[0][family]:
                assert terms(units[0][family][key]) == terms(units[1][family][key])
    finally:
        for model in models:
            model.dispose()


def test_native_gate_rejects_singleton_migration_before_solver_import():
    job, spec = fixture()
    graph = SimpleNamespace(events=dict(y=spec.starts, w=(("A", "B", 2),)), fixed=None)
    with pytest.raises(ValueError, match="LP_PROJECTION_UNPROVEN"):
        add_stay_unit(None, job, graph, 1)
    with pytest.raises(ValueError, match="LP_PROJECTION_UNPROVEN"):
        add_stay_unit(None, job, graph, 3, reference_representation="UNPROVEN_EVENT_FLOW")


def test_lp_counterexample_replays_all_actual_mixed_native_rows_without_solve():
    import gurobipy as gp
    from v42_exact.support import ExactFactory
    from v42_job_capability import Resources, ServiceBoundary
    from v42_root.factor import add_job
    job, _ = fixture()
    job = replace(job, gpu=1, service_slots=3, reference_start=0,
                  checkpoint_authorized=True)
    resources = Resources(dict(A=4, B=4), dict(A=(4,), B=(4,)),
                          {(link, t): 4 for link in ("AB", "BA") for t in range(8)},
                          {("A", "B"): ("AB",), ("B", "A"): ("BA",)},
                          8, 4, {}, {}, {}, restart_slots=1)
    boundary = ServiceBoundary("EXPLICIT_TINY_FIXTURE", True, True, (0, 1, 2), 8)
    graph = ExactFactory(resources, 8).graph(job, boundary)
    assert graph.events["w"] and graph.events["q"]
    model = gp.Model("TINY_STATIC_SINGLETON_EVENT_FLOW_COUNTEREXAMPLE")
    try:
        model.Params.OutputFlag = 0
        unit = add_job(model, job, graph, resources,
                       eliminate_f0=True, eliminate_state=True,
                       eliminate_depart=True, eliminate_arrive=True, share_links=True)
        model.update()
        # Static row replay only. No Model.optimize, relax, or presolve call.
        vector = [Fraction(0)] * model.NumVars
        example = lp_counterexample()
        for family in ("y", "f0", "r0"):
            for key, value in example["point"][family].items():
                variable = unit[family][key]
                assert isinstance(variable, gp.Var)
                vector[variable.index] = value
        matrix = model.getA().tocsr()
        for row in model.getConstrs():
            indices = matrix.indices[matrix.indptr[row.index]:matrix.indptr[row.index + 1]]
            coefficients = matrix.data[matrix.indptr[row.index]:matrix.indptr[row.index + 1]]
            value = sum((Fraction(float(a)) * vector[int(i)] for i, a in zip(indices, coefficients)), Fraction(0))
            rhs = Fraction(row.RHS)
            assert value == rhs if row.Sense == "=" else value <= rhs if row.Sense == "<" else value >= rhs
        for variable, value in zip(model.getVars(), vector):
            assert Fraction(variable.LB) <= value <= Fraction(variable.UB)
    finally:
        model.dispose()
