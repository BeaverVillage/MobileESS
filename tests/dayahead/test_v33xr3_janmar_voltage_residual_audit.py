from __future__ import annotations

import ast
import json
import subprocess
from pathlib import Path

import numpy as np
import pytest

from dayahead.v33xr3.audit import (
    residual_components,
    split_population,
    validate_exact_match,
    validate_janmar_day,
)
from dayahead.v33xr3.contracts import BRANCH, CLASSIFICATION, MATCH_FIELDS, STARTING_HEAD
from tools.v33xr3.run_v33xr3 import build


REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "dayahead/artifacts/v33xr3_janmar_voltage_residual_audit"


def j(name: str) -> dict[str, object]:
    value = json.loads((OUT / name).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def row(**updates: object) -> dict[str, object]:
    value = {field: f"same-{field}" for field in MATCH_FIELDS}
    value.update({"day": "2025-03-01", "case": "B1", "slot": 7, "node": "N1", "phase": "A", "namespace": "DAYAHEAD"})
    value.update(updates)
    return value


def changed(*paths: str) -> list[str]:
    return subprocess.check_output(
        ["git", "-C", str(REPO), "diff", "--name-only", STARTING_HEAD, "--", *paths], text=True
    ).splitlines()


def imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    result = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    return result + [item.name for node in ast.walk(tree) if isinstance(node, ast.Import) for item in node.names]


def test_01_exact_starting_head() -> None:
    review = j("V33XR3_FINAL_REVIEW.json")
    assert review["starting_HEAD"] == STARTING_HEAD
    assert review["branch"] == BRANCH


def test_02_janmar_date_gate() -> None:
    assert validate_janmar_day("2025-01-01").isoformat() == "2025-01-01"
    assert validate_janmar_day("2025-03-31").isoformat() == "2025-03-31"


def test_03_april_input_rejection() -> None:
    with pytest.raises(ValueError, match="OUTSIDE_JANMAR"):
        validate_janmar_day("2025-04-01")


def test_04_may_input_rejection() -> None:
    with pytest.raises(ValueError, match="OUTSIDE_JANMAR"):
        validate_janmar_day("2025-05-01")


def test_05_exact_schedule_sha_match() -> None:
    validate_exact_match(row(), row())
    with pytest.raises(ValueError, match="schedule_sha256"):
        validate_exact_match(row(), row(schedule_sha256="different"))


def test_06_dayahead_vs_dayahead_fresh_only() -> None:
    validate_exact_match(row(), row())
    with pytest.raises(ValueError, match="DAYAHEAD_ONLY"):
        validate_exact_match(row(), row(namespace="ACTUAL"))


def test_07_actual_trajectory_excluded() -> None:
    firewall = j("V33XR3_CAUSALITY_FIREWALL.json")
    assert firewall["Actual_trajectories_mixed_into_primary_audit"] == 0


def test_08_node_mapping_exact() -> None:
    with pytest.raises(ValueError, match="node"):
        validate_exact_match(row(), row(node="N2"))
    assert j("V33XR3_AXIS_MAPPING_AUDIT.json")["missing_mapping_count"] == 0


def test_09_phase_mapping_exact() -> None:
    with pytest.raises(ValueError, match="phase"):
        validate_exact_match(row(), row(phase="B"))
    assert j("V33XR3_AXIS_MAPPING_AUDIT.json")["phase_mismatch_count"] == 0


def test_10_slot_alignment_exact() -> None:
    with pytest.raises(ValueError, match="slot"):
        validate_exact_match(row(), row(slot=8))


def test_11_e_signed_formula() -> None:
    signed, _, _ = residual_components([1.0, 1.02], [1.01, 1.00])
    np.testing.assert_allclose(signed, [0.01, -0.02])


def test_12_e_up_formula() -> None:
    _, upper, _ = residual_components([1.0, 1.02], [1.01, 1.00])
    np.testing.assert_allclose(upper, [0.01, 0.0])


def test_13_e_low_formula() -> None:
    _, _, lower = residual_components([1.0, 1.02], [1.01, 1.00])
    np.testing.assert_allclose(lower, [0.0, 0.02])


def test_14_janfeb_calibration_only() -> None:
    assert split_population("2025-01-01") == "CALIBRATION_JANFEB"
    assert split_population("2025-02-28") == "CALIBRATION_JANFEB"


def test_15_march_validation_only() -> None:
    assert split_population("2025-03-01") == "VALIDATION_MARCH"
    assert split_population("2025-03-31") == "VALIDATION_MARCH"


def test_16_no_random_split() -> None:
    assert j("V33XR3_RESIDUAL_CONTRACT.json")["split"]["random"] is False
    assert "random" not in imports(REPO / "dayahead/v33xr3/audit.py")


def test_17_no_apr04_calibration_import() -> None:
    modules = imports(REPO / "dayahead/v33xr3/audit.py")
    assert not any("v33xr1" in name or "v33xr2" in name for name in modules)
    firewall = j("V33XR3_CAUSALITY_FIREWALL.json")
    assert firewall["APRIL_ROWS_READ_FOR_RESIDUAL_AUDIT"] == 0
    assert firewall["APRIL_ROWS_USED_FOR_MODEL_SELECTION"] == 0
    assert firewall["APRIL_ROWS_USED_FOR_MARGIN_SELECTION"] == 0


def test_18_no_fresh_control_oracle() -> None:
    firewall = j("V33XR3_CAUSALITY_FIREWALL.json")
    assert firewall["ACTUAL_GRID_FEEDBACK_AIDC_CONTROL_ALLOWED"] is False
    assert firewall["FRESH_USED_AS_ACTUAL_CONTROL_ORACLE"] is False
    assert firewall["Fresh_control_oracle_calls"] == 0


def test_19_no_production_optimizer_mutation() -> None:
    assert changed("dayahead/v30", "dayahead/v33x", "dayahead/v33xr1", "dayahead/v33xr2") == []
    assert j("V33XR3_CAUSALITY_FIREWALL.json")["production_science_changes"] == 0


def test_20_e1_unchanged() -> None:
    assert changed("dayahead/v33x", "dayahead/v33xr1") == []
    assert j("V33XR3_CAUSALITY_FIREWALL.json")["E1_files_modified"] == 0


def test_21_e2_unchanged() -> None:
    assert changed("dayahead/v33x/headroom_stage1.py") == []
    assert j("V33XR3_CAUSALITY_FIREWALL.json")["E2_files_modified"] == 0


def test_22_mess_unchanged() -> None:
    assert changed("dayahead/mess_physics.py", "dayahead/v28r2/mess_replay.py", "dayahead/v28r2/variable_registry.py") == []
    assert j("V33XR3_CAUSALITY_FIREWALL.json")["MESS_files_modified"] == 0


def test_23_no_mess_optimization() -> None:
    firewall = j("V33XR3_CAUSALITY_FIREWALL.json")
    assert firewall["MESS_optimization_calls"] == 0
    assert firewall["MESS_P_Q_mutations"] == 0
    assert firewall["V33M_V33M2_V33M3_changes"] == 0


def test_24_artifact_determinism(tmp_path: Path) -> None:
    first = build(REPO, tmp_path / "one")
    second = build(REPO, tmp_path / "two")
    names = sorted(path.name for path in first.iterdir())
    assert names == sorted(path.name for path in second.iterdir())
    assert all((first / name).read_bytes() == (second / name).read_bytes() for name in names)
    expected = {
        "README.md", "V33XR3_SOURCE_INVENTORY.json", "V33XR3_MATCHED_TRAJECTORY_AUDIT.json",
        "V33XR3_AXIS_MAPPING_AUDIT.json", "V33XR3_RESIDUAL_CONTRACT.json",
        "V33XR3_PRIMARY_B1_RESIDUAL_SUMMARY.json", "V33XR3_DAILY_MAX_RESIDUAL.csv",
        "V33XR3_NODE_PHASE_RESIDUAL.csv", "V33XR3_SLOT_RESIDUAL.csv",
        "V33XR3_OPERATING_POINT_RESIDUAL.csv", "V33XR3_JANFEB_MARCH_PROSPECTIVE_AUDIT.json",
        "V33XR3_CORRECTION_STRUCTURE_COMPARISON.csv", "V33XR3_CAUSALITY_FIREWALL.json",
        "V33XR3_FINAL_REVIEW.json", "V33XR3_FINAL_REVIEW.md", "V33XR3_TEST_REPORT.json",
    }
    assert set(names) == expected
    assert j("V33XR3_FINAL_REVIEW.json")["primary_classification"] == CLASSIFICATION
