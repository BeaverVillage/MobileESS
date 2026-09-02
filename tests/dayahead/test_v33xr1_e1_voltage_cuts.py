from __future__ import annotations

import ast
import csv
import json
import subprocess
from pathlib import Path

import numpy as np
import pytest

from dayahead.v30.dayahead_formulation import load_frozen_schedules
from dayahead.v33xr1.contracts import BRANCH, MASS_TOLERANCE_NODEH, MAX_REPAIR_ITERATIONS, STARTING_HEAD
from dayahead.v33xr1.voltage_cut_recourse import LocalVoltageCut


REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "dayahead/artifacts/v33x_r1_e1_voltage_cuts"
V33X_OUT = REPO / "dayahead/artifacts/v33x_fasttrack_grid_deliverable_aidc"


def j(name: str) -> dict[str, object]:
    value = json.loads((OUT / name).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def rows(name: str) -> list[dict[str, str]]:
    with (OUT / name).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def test_01_exact_starting_head_and_branch() -> None:
    value = j("V33XR1_CUT_CONTRACT.json")
    assert value["starting_SHA"] == STARTING_HEAD
    assert value["branch"] == BRANCH


def test_02_e1_da_schedule_is_unchanged() -> None:
    value = j("V33XR1_CUT_CONTRACT.json")
    schedules = load_frozen_schedules(REPO)
    assert value["E1_DA_schedule_identity"] is True
    assert value["E1_DA_schedule_sha256"] == schedules["B1"]["schedule_sha256"]
    assert j("V33XR1_FINAL_B1_RESULTS.json")["DA_schedule_identity"] is True


@pytest.mark.parametrize("field", ["MESS_P_sha256", "MESS_Q_sha256", "MESS_route_sha256"])
def test_03_mess_trajectory_is_frozen(field: str) -> None:
    assert len(j("V33XR1_CUT_CONTRACT.json")[field]) == 64
    assert j("V33XR1_FINAL_B1_RESULTS.json")["MESS_trajectory_identity"] is True
    assert j("V33XR1_FINAL_B3_RESULTS.json")["MESS_trajectory_identity"] is True


def test_04_cuts_are_generated_only_from_fresh_violations() -> None:
    values = rows("V33XR1_CUT_LEDGER.csv")
    assert len(values) == 4
    assert all(float(row["Fresh_voltage_before_cut_pu"]) > 1.05 for row in values)
    assert all(row["case"] == "B1" for row in values)


def test_05_cut_bus_phase_slot_is_exact() -> None:
    observed = {(row["bus"], row["phase"], int(row["slot"])) for row in rows("V33XR1_CUT_LEDGER.csv")}
    assert observed == {
        ("83", "A", 85), ("mess_sta12_pcc", "A", 85),
        ("83", "A", 95), ("mess_sta12_pcc", "A", 95),
    }


def test_06_cut_uses_frozen_planning_sensitivity() -> None:
    value = j("V33XR1_CUT_CONTRACT.json")
    assert value["planning_gradient_source"] == "frozen Apr-04 voltage_matrix with fixed-PF coupled AIDC control"
    for row in rows("V33XR1_CUT_LEDGER.csv"):
        assert len(json.loads(row["planning_sensitivity_vector_pu_per_kw"])) == 12


def test_07_no_arbitrary_voltage_margin() -> None:
    assert j("V33XR1_CUT_CONTRACT.json")["arbitrary_voltage_margin"] is False
    assert all(float(row["arbitrary_margin_pu"]) == 0.0 for row in rows("V33XR1_CUT_LEDGER.csv"))


def test_08_affine_cut_form_is_correct() -> None:
    for row in rows("V33XR1_CUT_LEDGER.csv"):
        p = np.asarray(json.loads(row["AIDC_p_k_vector_kw"]), dtype=float)
        a = np.asarray(json.loads(row["planning_sensitivity_vector_pu_per_kw"]), dtype=float)
        expected_rhs = 1.05 - float(row["Fresh_voltage_before_cut_pu"]) + float(a @ p)
        assert float(row["cut_RHS_pu"]) == pytest.approx(expected_rhs, abs=1e-12)
        assert row["cut_formula"] == "V_FRESH_k + a_k^T(p_t-p_k) <= 1.05"


def test_09_causal_suffix_replay_starts_at_earliest_cut() -> None:
    b1 = [row for row in rows("V33XR1_ITERATION_RESULTS.csv") if row["case"] == "B1"]
    assert int(b1[1]["replay_start_slot"]) == 85
    assert b1[1]["causal_prefix_reused"].lower() == "true"


def test_10_no_future_actual_reads() -> None:
    assert all(int(row["future_Actual_reads"]) == 0 for row in rows("V33XR1_ITERATION_RESULTS.csv"))
    assert j("V33XR1_FINAL_B1_RESULTS.json")["future_Actual_reads"] == 0


def test_11_workload_conservation() -> None:
    for row in rows("V33XR1_ITERATION_RESULTS.csv"):
        assert abs(float(row["mass_conservation_error_nodeh"])) <= MASS_TOLERANCE_NODEH


def test_12_rack_capacity_accounting_is_present() -> None:
    for row in rows("V33XR1_ITERATION_RESULTS.csv"):
        assert float(row["rack_blocked_nodeh"]) >= 0.0
        assert float(row["grid_cut_blocked_nodeh"]) >= 0.0


@pytest.mark.parametrize("field,expected", [
    ("strict_FULL_only", True),
    ("preemption", False),
    ("running_job_migration", False),
    ("same_slot_only", True),
])
def test_13_execution_contract_is_preserved(field: str, expected: object) -> None:
    assert j("V33XR1_CUT_CONTRACT.json")[field] == expected


def test_14_stage2_objective_is_unchanged() -> None:
    repair = j("V33XR1_CUT_CONTRACT.json")["Stage2_objective"]
    original = json.loads((V33X_OUT / "V33X_E1_FORMULATION_CONTRACT.json").read_text(encoding="utf-8"))["objective_hierarchy"]
    assert repair == original == ["MAX_SERVICE", "MIN_MAX_PLANNING_LINE_CURRENT", "MIN_DA_PLACEMENT_DEVIATION"]


def test_15_ordinary_cut_solver_has_no_fresh_import() -> None:
    path = REPO / "dayahead/v33xr1/voltage_cut_recourse.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    imports += [name.name for node in ast.walk(tree) if isinstance(node, ast.Import) for name in node.names]
    assert not any("fresh" in name.lower() or "opendss" in name.lower() for name in imports)


def test_16_fresh_cut_loop_is_isolated_to_development_driver() -> None:
    solver = (REPO / "dayahead/v33xr1/voltage_cut_recourse.py").read_text(encoding="utf-8").lower()
    driver = (REPO / "dayahead/v33xr1/runner.py").read_text(encoding="utf-8").lower()
    assert "run_fresh_opendss" not in solver
    assert "run_fresh_opendss" in driver
    assert j("V33XR1_CUT_CONTRACT.json")["FRESH_AC_CUT_GENERATION_USED"] is True


@pytest.mark.parametrize("field", ["physical_limit_changes", "continuous_parameter_tuning"])
def test_17_physical_limits_and_parameters_are_unchanged(field: str) -> None:
    value = j("V33XR1_CUT_CONTRACT.json")[field]
    assert value == 0 or value is False


def test_18_e2_is_untouched() -> None:
    changed = subprocess.check_output([
        "git", "-C", str(REPO), "diff", "--name-only", STARTING_HEAD, "--",
        "dayahead/v33x/headroom_stage1.py",
        "dayahead/artifacts/v33x_fasttrack_grid_deliverable_aidc/V33X_E2*",
    ], text=True).strip()
    assert changed == ""
    assert j("V33XR1_FINAL_REVIEW.json")["E2_touched"] is False


def test_19_all_four_local_cuts_are_infeasible_without_relaxation() -> None:
    values = rows("V33XR1_CUT_LEDGER.csv")
    assert all(row["cut_feasibility"] == "INFEASIBLE" for row in values)
    assert all(float(row["minimum_achievable_LHS_pu"]) > float(row["required_RHS_pu"]) for row in values)
    assert all(float(row["feasibility_shortfall_pu"]) > 0.0 for row in values)
    assert all(row["cut_active_after_resolve"].lower() == "false" for row in values)


def test_20_failure_is_not_hidden() -> None:
    value = j("V33XR1_FINAL_B1_RESULTS.json")
    assert value["RESULT_CLASSIFICATION"] == "V33XR1_E1_CUTS_FAILED_TO_CLOSE_VOLTAGE"
    assert value["repaired_candidate_exists"] is False
    assert value["final"]["Fresh_voltage_violation_count"] == 4
    assert value["final"]["Fresh_Vmax_pu"] > 1.05


def test_21_no_new_current_or_transformer_violation() -> None:
    value = j("V33XR1_FINAL_B1_RESULTS.json")["final"]
    assert value["Fresh_line_current_violation_count"] == 0
    assert value["Fresh_transformer_current_violation_count"] == 0
    assert value["Fresh_transformer_kva_violation_count"] == 0
    assert value["Fresh_convergence_count"] == 96


def test_22_infeasible_cuts_do_not_claim_service_loss() -> None:
    value = j("V33XR1_FINAL_B1_RESULTS.json")
    assert value["cut_set_infeasible"] is True
    assert value["cut_induced_service_loss_nodeh"] == 0.0
    assert value["retained_original_E1_gain_fraction"] == 1.0


def test_23_b3_is_reused_without_resolve_or_fresh() -> None:
    value = j("V33XR1_FINAL_B3_RESULTS.json")
    assert value["cuts_generated"] == 0
    assert value["trajectory_unchanged_by_construction"] is True
    assert value["Fresh_result_reused"] is True
    assert value["Fresh_voltage_violation_count"] == 0


def test_24_iteration_limit_is_fixed_not_tuned() -> None:
    value = j("V33XR1_CUT_CONTRACT.json")
    assert MAX_REPAIR_ITERATIONS == value["maximum_additional_repair_iterations"] == 4
    assert value["continuous_parameter_tuning"] is False


def test_25_only_required_small_artifacts_exist() -> None:
    required = {
        "README.md", "V33XR1_CUT_CONTRACT.json", "V33XR1_CUT_LEDGER.csv",
        "V33XR1_ITERATION_RESULTS.csv", "V33XR1_FINAL_B1_RESULTS.json",
        "V33XR1_FINAL_B3_RESULTS.json", "V33XR1_FINAL_FRESH_OPENDSS_RESULTS.csv",
        "V33XR1_FINAL_REVIEW.json", "V33XR1_FINAL_REVIEW.md", "V33XR1_TEST_REPORT.json",
    }
    assert {path.name for path in OUT.iterdir() if path.is_file()} == required


def test_26_final_authority_is_false() -> None:
    value = j("V33XR1_FINAL_REVIEW.json")
    assert value["FINAL_AUTHORITY"] is False
    assert value["development_candidate"] is False
    assert value["MESS_reoptimized"] is False


def test_27_test_report_has_no_failure_or_not_run() -> None:
    value = j("V33XR1_TEST_REPORT.json")
    assert value["failed"] == value["not_run"] == 0
