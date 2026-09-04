import ast
import json
from pathlib import Path

import numpy as np

from dayahead.v28r2.formulation import formulation_fingerprint, materialize_formulation_data
from dayahead.v28r2.electrical_subproblem import is_dominated_mess_current_row
from dayahead.v28r2.solver_equivalence import verify_b3_equivalence
from dayahead.v28r2.solver_payload import SolverPayload


def payload(solver: str = "MONOLITHIC", objective: float = 1.0) -> SolverPayload:
    return SolverPayload(
        case="B3", solver=solver, objective=objective, status="OPTIMAL", hard_feasible=True,
        incumbent=objective, lower_bound=objective, upper_bound=objective, gap=0.0,
        iterations=1, optimality_cuts=0, feasibility_cuts=0,
        termination_reason="TEST", runtime_seconds=0.1,
        controls=np.zeros((96, 60)).tolist(),
        workload_service_tensor=np.zeros((15, 48, 96)).tolist(),
        aidc_rack_cohort_allocation={"tensor_order": "cohort,rack,slot"},
        site_it_power_kw=np.zeros((96, 12)).tolist(),
        rack_it_power_kw=np.zeros((96, 48)).tolist(),
        rack_gpu=np.zeros((96, 48)).tolist(), site_gpu=np.zeros((96, 12)).tolist(),
        planning_pcc_power_kw=np.zeros((96, 12)).tolist(),
        planning_pcc_reactive_kvar=np.zeros((96, 12)).tolist(),
        mess_p_kw=np.zeros((96, 4)).tolist(), mess_q_kvar=np.zeros((96, 4)).tolist(),
        mess_soc_kwh=np.zeros((97, 4)).tolist(), mess_route_location={},
        backlog_nodeh=np.zeros((97, 15)).tolist(),
        feasibility_residuals={"maximum": 0.0},
        formulation_fingerprint="a" * 64, input_sha256="b" * 64,
    )


def test_complete_payload_shapes_are_mandatory():
    value = payload()
    value.validate()
    assert len(value.workload_service_tensor) == 15
    assert len(value.controls) == 96
    assert value.canonical_payload()["LB"] == value.lower_bound
    assert value.canonical_payload()["UB"] == value.upper_bound


def test_frozen_mess_transformer_current_exception_is_exact():
    assert is_dominated_mess_current_row("transformer.mess_idc01_tx::a")
    assert is_dominated_mess_current_row("TRANSFORMER.MESS_STA12_TX::C")
    assert not is_dominated_mess_current_row("transformer.aidc01_tx::a")
    assert not is_dominated_mess_current_row("line.mess_idc01_tx::a")


def test_three_solver_equivalence_uses_fingerprint_input_and_objective():
    result = verify_b3_equivalence({
        "MONOLITHIC": payload(),
        "STANDARD_BD": payload("STANDARD_BD", 1.0002),
        "CL_MC_BD": payload("CL_MC_BD", 1.0001),
    })
    assert result["B3_SOLVER_EQUIVALENCE_READY"] is True


def test_april1_formulation_materialization_uses_fullnode_c1_and_reference_delta():
    repo = Path(__file__).resolve().parents[2]
    if not (repo / "cache/v28r2_campaign_sources/april_2025/days/2025-04-01/source_day_manifest.json").is_file():
        return
    data = materialize_formulation_data(repo, "2025-04-01")
    assert data.arrivals_nodeh.shape == (96, 15)
    assert data.reference.x_ref_nodeh.shape == (15, 48, 96)
    assert data.delta.p_res_plan_kw.shape == (48, 96)
    assert len(data.c1_coefficients) == 12 * 96
    assert data.formulation_fingerprint == formulation_fingerprint(repo)


def test_production_solver_graph_has_no_legacy_pue_beta_c2_import():
    repo = Path(__file__).resolve().parents[2]
    paths = [
        repo / "dayahead/v28r2/formulation.py", repo / "dayahead/v28r2/variable_registry.py",
        repo / "dayahead/v28r2/solver_runner.py", repo / "dayahead/v28r2/benders_authority.py",
    ]
    imports = []
    names = []
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports.extend(node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom))
        imports.extend(alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names)
        names.extend(node.id for node in ast.walk(tree) if isinstance(node, ast.Name))
    assert not any("aidc_boundary_v16_1" in module for module in imports)
    assert "PUE_PLAN" not in names and "beta_AIDC" not in names and "C2" not in names
    audit = json.loads((
        repo / "dayahead/artifacts/v28r2_heavy_backend/V28R2_PRODUCTION_IMPORT_GRAPH_AUDIT.json"
    ).read_text(encoding="utf-8"))
    assert audit["PRODUCTION_IMPORT_GRAPH_READY"] is True
    assert audit["transitive_local_module_count"] >= len(paths)
    assert not any(audit["denied_symbol_occurrences"].values())
