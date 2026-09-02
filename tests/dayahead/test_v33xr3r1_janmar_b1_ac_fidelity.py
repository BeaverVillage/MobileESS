from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from dayahead.v33xr3r1.contracts import (
    BRANCH,
    CASE,
    CLASSIFICATION,
    END_DAY,
    EXPECTED_DAYS,
    PLANNING_VMAX_PU,
    SLOTS_PER_DAY,
    STARTING_HEAD,
    START_DAY,
)
from dayahead.v33xr3r1.gate import MaterializationFirewall, validate_day, validate_pass_marker
from tools.v33xr3r1.run_v33xr3r1 import OUT_REL, build


REPO = Path(__file__).resolve().parents[2]


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


@pytest.fixture(scope="module")
def artifacts(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return build(REPO, tmp_path_factory.mktemp("v33xr3r1"))


def test_01_exact_starting_head() -> None:
    assert STARTING_HEAD == "f49bb4e2028c49621c22854b536f5c4cf22f574d"
    assert BRANCH == "codex/v33xr3r1-janmar-b1-ac-fidelity-materialization"
    assert subprocess.run(["git", "branch", "--show-current"], cwd=REPO, check=True, capture_output=True, text=True).stdout.strip() == BRANCH
    assert subprocess.run(["git", "merge-base", "HEAD", STARTING_HEAD], cwd=REPO, check=True, capture_output=True, text=True).stdout.strip() == STARTING_HEAD


def test_02_b1_only(artifacts: Path) -> None:
    assert CASE == "B1"
    assert {_row["case"] for _row in _csv(artifacts / "V33XR3R1_DAY_STATUS.csv")} == {"B1"}


def test_03_jan_mar_only() -> None:
    assert validate_day("2025-01-01") == START_DAY
    assert validate_day("2025-03-31") == END_DAY
    assert EXPECTED_DAYS == 90


def test_04_april_rejection() -> None:
    with pytest.raises(ValueError, match="V33XR3R1_DAY_OUTSIDE_JANMAR"):
        validate_day("2025-04-01")


def test_05_may_rejection() -> None:
    with pytest.raises(ValueError, match="V33XR3R1_DAY_OUTSIDE_JANMAR"):
        validate_day("2025-05-01")


def test_06_actual_data_inaccessible_before_freeze() -> None:
    with pytest.raises(RuntimeError, match="ACTUAL_INACCESSIBLE_BEFORE_FREEZE"):
        MaterializationFirewall().open_actual("a" * 64)


def test_07_fresh_inaccessible_before_freeze() -> None:
    with pytest.raises(RuntimeError, match="FRESH_INACCESSIBLE_BEFORE_FREEZE"):
        MaterializationFirewall().open_fresh("a" * 64)


def test_08_canonical_stage1_voltage_bound_provenance(artifacts: Path) -> None:
    contract = _json(artifacts / "V33XR3R1_CONTRACT.json")
    provenance = contract["planning_voltage_limit_authority"]
    assert PLANNING_VMAX_PU == 1.05
    assert contract["PLANNING_VMAX_PU"] == 1.05
    assert provenance["path"] == "dayahead/grid_lp.py"
    assert provenance["value"] == pytest.approx(1.05**2)
    assert provenance["sha256"] == hashlib.sha256((REPO / provenance["path"]).read_bytes()).hexdigest()


def test_09_planning_model_deterministic_gate(artifacts: Path) -> None:
    authority = _json(artifacts / "V33XR3R1_PLANNING_MODEL_AUTHORITY.json")
    assert authority["classification"] == CLASSIFICATION
    assert authority["representative_error"] == "V28R2_OPTIMIZER_MATERIALIZATION_APRIL_ONLY"
    assert authority["JanMar_frozen_causal_P_G_W_prediction_days"] == 0
    assert authority["production_science_changed"] is False
    assert all(
        set(item["frozen_fit_training_ends"]) <= {"2025-03-30", "2025-03-31"}
        for item in authority["frozen_predictor_authorities"]
    )


def test_10_exact_96_slots_contract(artifacts: Path) -> None:
    assert SLOTS_PER_DAY == 96
    assert _json(artifacts / "V33XR3R1_CONTRACT.json")["slots_per_day"] == 96


def test_11_exact_schedule_sha_freeze() -> None:
    firewall = MaterializationFirewall()
    with pytest.raises(ValueError, match="SCHEDULE_SHA_REQUIRED"):
        firewall.freeze_schedule("bad")
    firewall.freeze_schedule("a" * 64)
    firewall.open_actual("a" * 64)
    firewall.open_fresh("a" * 64)
    assert (firewall.actual_reads, firewall.fresh_reads) == (1, 1)


def test_12_full_planning_voltage_array_contract(artifacts: Path) -> None:
    review = _json(artifacts / "V33XR3R1_MATERIALIZATION_REVIEW.json")
    axis = _json(artifacts / "V33XR3R1_AXIS_AUTHORITY.json")
    assert review["coverage"]["planning_voltage_complete_days"] == 0
    assert axis["planning_completed_node_phase_count"] == 0
    assert axis["status"] == "NOT_MATERIALIZED_UPSTREAM_BLOCKER"


def test_13_fresh_96_slot_execution_contract(artifacts: Path) -> None:
    review = _json(artifacts / "V33XR3R1_MATERIALIZATION_REVIEW.json")
    audit = _json(artifacts / "V33XR3R1_CAUSALITY_AUDIT.json")
    assert review["coverage"]["Fresh_complete_days"] == 0
    assert review["coverage"]["Fresh_96_of_96_convergence_days"] == 0
    assert audit["Fresh_execution_calls"] == 0


def test_14_planning_fresh_node_mapping_contract(artifacts: Path) -> None:
    axis = _json(artifacts / "V33XR3R1_AXIS_AUTHORITY.json")
    assert axis["existing_native_node_phase_axis_days"] == 90
    assert axis["stable_existing_native_node_axis"] is True
    assert axis["matched_count"] == axis["missing_count"] == axis["duplicate_count"] == 0


def test_15_phase_mapping_contract(artifacts: Path) -> None:
    axis = _json(artifacts / "V33XR3R1_AXIS_AUTHORITY.json")
    assert axis["phase_mismatch_count"] == 0
    assert "mapping completeness is not claimed" in axis["note"]


def test_16_schedule_sha_planning_fresh_identity_contract(artifacts: Path) -> None:
    rows = _csv(artifacts / "V33XR3R1_SCHEDULE_SHA256.csv")
    assert len(rows) == 90
    assert {row["identity_status"] for row in rows} == {"NOT_EVALUATED"}
    assert all(not row["schedule_sha256"] and not row["planning_evaluation_schedule_sha256"] and not row["Fresh_evaluation_schedule_sha256"] for row in rows)


def test_17_no_fresh_cut(artifacts: Path) -> None:
    assert _json(artifacts / "V33XR3R1_CAUSALITY_AUDIT.json")["FRESH_DERIVED_CUTS"] == 0


def test_18_no_fresh_reoptimization(artifacts: Path) -> None:
    audit = _json(artifacts / "V33XR3R1_CAUSALITY_AUDIT.json")
    assert audit["FRESH_TRIGGERED_REOPTIMIZATION"] == 0
    assert audit["FRESH_TO_OPTIMIZER_CALLS"] == 0


def test_19_no_actual_stage2(artifacts: Path) -> None:
    assert _json(artifacts / "V33XR3R1_CAUSALITY_AUDIT.json")["Actual_Stage2_calls"] == 0


def test_20_no_e2(artifacts: Path) -> None:
    assert _json(artifacts / "V33XR3R1_CAUSALITY_AUDIT.json")["E2_calls"] == 0


def test_21_no_pi(artifacts: Path) -> None:
    assert _json(artifacts / "V33XR3R1_CAUSALITY_AUDIT.json")["PI_calls"] == 0


def test_22_no_mess_optimization(artifacts: Path) -> None:
    audit = _json(artifacts / "V33XR3R1_CAUSALITY_AUDIT.json")
    assert audit["MESS_optimization_calls"] == 0
    assert audit["MESS_P_Q_mutations"] == 0


def test_23_mess_code_untouched() -> None:
    changed = subprocess.run(
        ["git", "diff", "--name-only", STARTING_HEAD, "--", "dayahead/mess_physics.py", "dayahead/v28r2/mess_replay.py", "dayahead/v28r2/variable_registry.py"],
        cwd=REPO,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert changed == ""
    status = subprocess.run(
        ["git", "status", "--porcelain", "--", "dayahead/mess_physics.py", "dayahead/v28r2/mess_replay.py", "dayahead/v28r2/variable_registry.py"],
        cwd=REPO,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert status == ""


def test_24_resumable_pass_validation(tmp_path: Path) -> None:
    payload = tmp_path / "payload.bin"
    payload.write_bytes(b"immutable")
    digest = hashlib.sha256(payload.read_bytes()).hexdigest()
    marker = {
        "day": "2025-01-01",
        "code_head": STARTING_HEAD,
        "schedule_sha256": "a" * 64,
        "planning_voltage_artifact_sha256": "b" * 64,
        "fresh_voltage_artifact_sha256": "c" * 64,
        "source_sha_bundle": "d" * 64,
        "status": "PASS",
        "files": {"payload.bin": digest},
    }
    assert validate_pass_marker(marker, tmp_path)
    payload.write_bytes(b"changed")
    assert not validate_pass_marker(marker, tmp_path)


def test_25_artifact_sha_determinism(tmp_path: Path) -> None:
    first = build(REPO, tmp_path / "first")
    second = build(REPO, tmp_path / "second")
    expected = {
        "README.md",
        "V33XR3R1_CONTRACT.json",
        "V33XR3R1_SOURCE_COVERAGE.csv",
        "V33XR3R1_PLANNING_MODEL_AUTHORITY.json",
        "V33XR3R1_AXIS_AUTHORITY.json",
        "V33XR3R1_DAY_STATUS.csv",
        "V33XR3R1_SCHEDULE_SHA256.csv",
        "V33XR3R1_VOLTAGE_ARTIFACT_SHA256.csv",
        "V33XR3R1_CAUSALITY_AUDIT.json",
        "V33XR3R1_MATERIALIZATION_REVIEW.json",
        "V33XR3R1_MATERIALIZATION_REVIEW.md",
        "V33XR3R1_TEST_REPORT.json",
    }
    assert {path.name for path in first.iterdir()} == expected
    assert {path.name for path in second.iterdir()} == expected
    assert {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in first.iterdir()} == {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in second.iterdir()
    }
