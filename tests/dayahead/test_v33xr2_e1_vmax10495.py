from __future__ import annotations

import ast
import json
import math
import subprocess
from pathlib import Path

import numpy as np

from dayahead.grid_lp import V_MIN_SQUARED
from dayahead.v28r2.actual_replay import PF_TAN
from dayahead.v33x.full_grid_recourse import HIGHS_THREADS
from dayahead.v33xr2.contracts import (
    BRANCH,
    CLASS_FRESH_V,
    DEVELOPMENT_PLANNING_VMAX_PU,
    FRESH_PHYSICAL_VMAX_PU,
    MESS_INTEGRATION_HEAD,
    PF,
    PLANNING_VMIN_PU,
    STARTING_HEAD,
)


REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "dayahead/artifacts/v33xr2_e1_vmax10495"


def j(name: str) -> dict[str, object]:
    value = json.loads((OUT / name).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def imports(path: str) -> list[str]:
    tree = ast.parse((REPO / path).read_text(encoding="utf-8"))
    result = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    result += [item.name for node in ast.walk(tree) if isinstance(node, ast.Import) for item in node.names]
    return result


def changed_since_start(*paths: str) -> list[str]:
    output = subprocess.check_output(
        ["git", "-C", str(REPO), "diff", "--name-only", STARTING_HEAD, "--", *paths],
        text=True,
    )
    return output.splitlines()


def test_01_exact_starting_head_and_branch() -> None:
    contract = j("V33XR2_CONTRACT.json")
    assert contract["starting_HEAD"] == STARTING_HEAD
    assert contract["branch"] == BRANCH


def test_02_single_planning_vmax_is_exact() -> None:
    assert DEVELOPMENT_PLANNING_VMAX_PU == 1.0495
    assert j("V33XR2_CONTRACT.json")["DEVELOPMENT_PLANNING_VMAX_PU"] == 1.0495


def test_03_fresh_physical_limit_is_unchanged() -> None:
    assert FRESH_PHYSICAL_VMAX_PU == 1.05
    assert j("V33XR2_CONTRACT.json")["FRESH_PHYSICAL_VMAX_PU"] == 1.05


def test_04_lower_voltage_limit_is_unchanged() -> None:
    contract = j("V33XR2_CONTRACT.json")
    assert PLANNING_VMIN_PU == 0.95
    assert V_MIN_SQUARED == 0.95**2
    assert contract["lower_voltage_bound_changed"] is False


def test_05_stage1_receives_10495() -> None:
    result = j("V33XR2_B1_STAGE1_RESULT.json")
    source = (REPO / "dayahead/v33xr2/stage1.py").read_text(encoding="utf-8")
    assert result["DEVELOPMENT_PLANNING_VMAX_PU"] == 1.0495
    assert "planning_vmax_pu=planning_vmax_pu" in source


def test_06_stage2_receives_10495() -> None:
    result = j("V33XR2_B1_STAGE2_RESULT.json")
    source = (REPO / "dayahead/v33xr2/runner.py").read_text(encoding="utf-8")
    assert result["DEVELOPMENT_PLANNING_VMAX_PU"] == 1.0495
    assert "planning_vmax_pu=DEVELOPMENT_PLANNING_VMAX_PU" in source


def test_07_no_e2_path_was_touched() -> None:
    assert j("V33XR2_CONTRACT.json")["E2_touched"] is False
    assert changed_since_start("dayahead/v33x/headroom_stage1.py") == []


def test_08_no_hrec_was_added_or_modified() -> None:
    contract = j("V33XR2_CONTRACT.json")
    sources = "".join((REPO / path).read_text(encoding="utf-8") for path in (
        "dayahead/v33xr2/stage1.py", "dayahead/v33xr2/runner.py",
    ))
    assert contract["h_REC_added_or_modified"] is False
    assert "v33x_h_REC" not in sources


def test_09_no_fresh_derived_cut() -> None:
    stage2 = j("V33XR2_B1_STAGE2_RESULT.json")
    assert stage2["local_Fresh_cuts"] == 0
    assert j("V33XR2_CONTRACT.json")["Fresh_derived_cuts"] == 0


def test_10_fresh_is_absent_from_decision_modules() -> None:
    decision_imports = imports("dayahead/v33xr2/stage1.py") + imports("dayahead/v33x/full_grid_recourse.py")
    assert not any("fresh" in name.lower() or "opendss" in name.lower() for name in decision_imports)
    assert j("V33XR2_B1_STAGE2_RESULT.json")["Fresh_inputs_to_solver"] == 0


def test_11_mess_is_unchanged_and_not_reoptimized() -> None:
    contract = j("V33XR2_CONTRACT.json")
    stage1 = j("V33XR2_B1_STAGE1_RESULT.json")
    assert contract["MESS_integration_HEAD"] == MESS_INTEGRATION_HEAD
    assert contract["MESS_touched_or_reoptimized"] is False
    assert stage1["MESS_unchanged"] is True
    assert stage1["MESS_max_abs_P_difference_kw"] == 0.0
    assert stage1["MESS_max_abs_Q_difference_kvar"] == 0.0
    assert changed_since_start("dayahead/mess_physics.py", "dayahead/v28r2/mess_replay.py", "dayahead/v28r2/variable_registry.py") == []


def test_12_pf_is_unchanged() -> None:
    assert PF == 0.95
    assert PF_TAN == math.tan(math.acos(0.95))
    assert j("V33XR2_CONTRACT.json")["PF"] == 0.95


def test_13_current_and_transformer_ratings_are_unchanged() -> None:
    contract = j("V33XR2_CONTRACT.json")
    source = (REPO / "dayahead/v28r2/solver_runner.py").read_text(encoding="utf-8")
    assert contract["current_transformer_ratings_changed"] is False
    assert "current_hat <= 1.0" in source
    assert "transformer_total_kva_hard" in source


def test_14_stage2_objective_is_unchanged() -> None:
    expected = ["MAX_SERVICE", "MIN_MAX_PLANNING_LINE_CURRENT", "MIN_DA_PLACEMENT_DEVIATION"]
    assert j("V33XR2_B1_STAGE2_RESULT.json")["objective_hierarchy"] == expected
    assert HIGHS_THREADS == 4


def test_15_future_actual_reads_are_zero() -> None:
    assert j("V33XR2_B1_STAGE1_RESULT.json")["future_Actual_reads"] == 0
    assert j("V33XR2_B1_STAGE2_RESULT.json")["future_Actual_reads"] == 0


def test_16_mass_conservation() -> None:
    assert float(j("V33XR2_B1_STAGE2_RESULT.json")["mass_error_nodeh"]) <= 1e-9


def test_17_no_preemption_and_strict_full() -> None:
    result = j("V33XR2_B1_STAGE2_RESULT.json")
    assert result["preemption"] is False
    assert result["strict_FULL_only"] is True
    assert result["same_slot_only"] is True


def test_18_no_running_job_migration() -> None:
    assert j("V33XR2_B1_STAGE2_RESULT.json")["running_job_migration"] is False


def test_19_b1_fast_gate_classification_and_b3_stop() -> None:
    review = j("V33XR2_FINAL_REVIEW.json")
    assert review["primary_classification"] == CLASS_FRESH_V
    assert review["B1"]["fresh"]["voltage_violation_count"] == 4
    assert review["B3_run"] is False
    assert not (OUT / "V33XR2_B3_STAGE1_RESULT.json").exists()


def test_20_only_declared_artifacts_exist() -> None:
    assert {path.name for path in OUT.iterdir()} == {
        "README.md",
        "V33XR2_CONTRACT.json",
        "V33XR2_B1_STAGE1_RESULT.json",
        "V33XR2_B1_STAGE2_RESULT.json",
        "V33XR2_B1_FRESH_RESULT.csv",
        "V33XR2_FINAL_REVIEW.json",
        "V33XR2_FINAL_REVIEW.md",
        "V33XR2_TEST_REPORT.json",
    }
