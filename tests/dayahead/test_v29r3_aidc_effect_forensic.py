"""V29R3 fail-closed artifact and scientific-firewall regression gates."""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from pathlib import Path

import numpy as np

from dayahead.mess_physics import PCS_KVA, P_LIMIT_KW
from dayahead.v29r3.forensic import (
    BASE_SHA,
    DEV_FREEZE_SHA,
    OUT_REL,
    V29R1_SHA,
    V29R2_MANIFEST_SHA,
    _files_digest,
)


REPO = Path(__file__).resolve().parents[2]
OUT = REPO / OUT_REL
V29R2 = REPO / "dayahead/artifacts/v29r2_anchor_aware_trust_noregret"


def load(name: str) -> object:
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def rows(name: str) -> list[dict[str, str]]:
    with (OUT / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def git(*args: str) -> str:
    return subprocess.check_output(["git", "-C", str(REPO), *args], text=True).strip()


def test_01_exact_frozen_v29r2_base() -> None:
    audit = load("V29R3_STARTING_AUTHORITY_AUDIT.json")
    assert audit["status"] == "PASS"
    assert audit["chosen_base_SHA"] == BASE_SHA
    assert audit["DEV_FREEZE_HEAD"] == DEV_FREEZE_SHA
    assert audit["V29R1_head"] == V29R1_SHA
    assert all(audit["ancestry"].values())
    assert audit["scientific_paths_changed_above_DEV_FREEZE"] == []


def test_02_apr04_actuation_mass_energy_identities() -> None:
    summary = load("V29R3_APR04_AIDC_ACTUATION_SUMMARY.json")
    assert summary["status"] == "PASS"
    for comparison in summary["comparisons"].values():
        for quantity in comparison.values():
            assert quantity["identity_error_kwh"] <= 1e-9


def test_03_service_rack_waterfall_identity() -> None:
    data = load("V29R3_APR04_SERVICE_RACK_WATERFALL.json")
    assert abs(data["planned_nodeh"] - data["executed_nodeh"] - data["source_availability_miss_nodeh"] - data["rack_capacity_miss_nodeh"] - data["other_explicit_miss_nodeh"]) <= 1e-9
    assert abs(data["planned_nodeh"] - 179.80406907977607) <= 1e-9
    assert abs(data["executed_nodeh"] - 40.365577219926706) <= 1e-9


def test_04_no_double_counting_of_miss_reasons() -> None:
    ledger = rows("V29R3_APR04_SERVICE_RACK_WATERFALL.csv")
    totals = {key: sum(float(row[key]) for row in ledger) for key in (
        "planned_nodeh", "executed_nodeh", "source_unavailable_nodeh",
        "rack_capacity_miss_nodeh", "other_explicit_miss_nodeh",
    )}
    assert abs(totals["planned_nodeh"] - totals["executed_nodeh"] - totals["source_unavailable_nodeh"] - totals["rack_capacity_miss_nodeh"] - totals["other_explicit_miss_nodeh"]) <= 1e-9
    assert all(float(row["source_unavailable_nodeh"]) >= 0 and float(row["rack_capacity_miss_nodeh"]) >= 0 for row in ledger)


def test_05_rack_stranding_accounting() -> None:
    data = load("V29R3_RACK_COUNTERFACTUAL_CEILINGS.json")
    waterfall = load("V29R3_APR04_SERVICE_RACK_WATERFALL.json")
    assert abs(data["STRANDED_CAPACITY_NODEH"] + data["TRUE_CAPACITY_SHORTAGE_NODEH"] - waterfall["rack_capacity_miss_nodeh"]) <= 1e-9
    assert data["classification"] == "RACK_ALLOCATION_STRANDING"


def test_06_counterfactual_capacity_conservation() -> None:
    data = load("V29R3_RACK_COUNTERFACTUAL_CEILINGS.json")
    assert data["source_backlog_and_total_capacity_preserved"] is True
    assert data["CF_R0_exact_rack_restrictions_executed_nodeh"] <= data["CF_R1_site_pooled_executed_nodeh"] <= data["CF_R2_system_pooled_executed_nodeh"]
    assert data["CF_R2_system_pooled_executed_nodeh"] <= data["CF_FULL_PHYSICAL_system_pooled_executed_nodeh"]


def test_07_critical_line_sensitivity_axis_and_sign() -> None:
    review = load("V29R3_CRITICAL_LINE_SENSITIVITY_REVIEW.json")
    assert review["critical_line"] == "line.sw2" and review["critical_phase"] == "A" and review["critical_slot"] == 63
    assert review["sign_agreement"] is True
    assert "fixed-PF" in review["finite_difference_axis"]


def test_08_finite_difference_has_no_hidden_changes() -> None:
    review = load("V29R3_CRITICAL_LINE_SENSITIVITY_REVIEW.json")
    assert review["finite_difference_solve_count"] == 25
    assert len(rows("V29R3_CRITICAL_LINE_SENSITIVITY.csv")) == 12
    assert review["planning_vs_fresh_max_abs_error_pu_per_kw"] < 3e-5


def test_09_background_attribution_identity() -> None:
    data = rows("V29R3_BACKGROUND_GRID_ATTRIBUTION.csv")
    by_slot: dict[int, list[dict[str, str]]] = {}
    for row in data:
        by_slot.setdefault(int(row["slot"]), []).append(row)
    assert len(by_slot) == 10
    for values in by_slot.values():
        values.sort(key=lambda row: int(row["attribution_order"]))
        assert abs(sum(float(row["sequential_contribution_pu"]) for row in values) - float(values[-1]["cumulative_loading_pu"])) <= 1e-12


def test_10_critical_slot_execution_retention() -> None:
    review = load("V29R3_EXECUTION_RETENTION_REVIEW.json")
    assert abs(review["benefit_retention"] - 0.7585751019372755) <= 1e-12
    assert review["critical_slot_63_execution_ratio"] < 0.3
    assert review["top10_critical_slots_weighted_ratio"] < review["all_day_weighted_execution_ratio"]


def test_11_service_model_april_fit_reads_zero() -> None:
    forensic = load("V29R3_SERVICE_HURDLE_FORENSIC.json")
    decision = load("V29R3_SERVICE_MODEL_DECISION.json")
    assert forensic["April_fit_rows"] == 0
    assert decision["April_used_for_fit_calibration_or_selection"] is False


def test_12_preapril_oof_only_candidate_selection() -> None:
    comparison = rows("V29R3_SERVICE_MODEL_COMPARISON.csv")
    assert all(int(row["April_fit_rows"]) == 0 for row in comparison)
    assert load("V29R3_SERVICE_MODEL_DECISION.json")["selected_candidate"] == "S0_CURRENT_HURDLE"


def test_13_no_arbitrary_h_low_positive_floor() -> None:
    forensic = load("V29R3_SERVICE_HURDLE_FORENSIC.json")
    assert forensic["arbitrary_positive_floor_present"] is False
    assert all(row["H_LOW"] == 0.0 and row["raw_lower_before_nonnegative_bound_nodeh"] < 0 for row in forensic["cohort_lower_bound_calculation"])


def test_14_no_scale_rho_or_mess_rating_changes() -> None:
    assert P_LIMIT_KW == 550.0 and PCS_KVA == 700.0
    assert git("diff", "--name-only", BASE_SHA, "--", "dayahead/v29r2", "dayahead/v28r2/variable_registry.py", "dayahead/mess_physics.py") == ""
    authority = json.loads((V29R2 / "V29R2_TRUST_CERT_DECISION.json").read_text(encoding="utf-8"))
    assert authority["selected_rho_AIDC"] == 1.0


def test_15_protected_artifact_preservation() -> None:
    pre = load("V29R3_PRECHANGE_PRESERVATION_MANIFEST.json")
    post = load("V29R3_POSTCHANGE_PRESERVATION_AUDIT.json")
    assert pre["status"] == post["status"] == "PASS"
    assert pre["V29R2_observed_aggregate_manifest_sha256"] == V29R2_MANIFEST_SHA
    assert pre["protected_tracked_artifact_trees"] == post["protected_tracked_artifact_trees"]


def test_16_apr04_no_regret() -> None:
    actual = list(csv.DictReader((V29R2 / "V29R2_APR04_ACTUAL_RESULTS.csv").open(encoding="utf-8")))
    by = {row["case"]: float(row["rho_max_AC"]) for row in actual}
    assert by["B3"] <= by["B2"]


def test_17_actual_optimizer_calls_zero() -> None:
    actual = list(csv.DictReader((V29R2 / "V29R2_APR04_ACTUAL_RESULTS.csv").open(encoding="utf-8")))
    assert all(int(row["actual_reoptimization_calls"]) == 0 and int(row["optimizer_import_count"]) == 0 for row in actual)


def test_18_fresh_opendss_completeness() -> None:
    opendss = list(csv.DictReader((V29R2 / "V29R2_APR04_OPENDSS_RESULTS.csv").open(encoding="utf-8")))
    assert len(opendss) == 10
    assert all(int(row["OpenDSS_solve_count"]) == 96 and int(row["convergence_count"]) == 96 for row in opendss)


def test_19_sha_manifest_consistency() -> None:
    manifest = load("V29R3_ARTIFACT_SHA256.json")
    observed = _files_digest(OUT, exclude=("V29R3_ARTIFACT_SHA256.json", "V29R3_TEST_REPORT.json"))
    expected = [row for row in manifest["files"] if row["path"] != "V29R3_TEST_REPORT.json"]
    digest = hashlib.sha256(json.dumps(expected, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()
    assert {row["path"]: row["sha256"] for row in expected} == {row["path"]: row["sha256"] for row in observed["files"]}
    assert digest == hashlib.sha256(json.dumps(observed["files"], sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def test_20_required_artifacts_and_not_run_zero() -> None:
    required = {
        "README.md", "V29R3_STARTING_AUTHORITY_AUDIT.json", "V29R3_PRECHANGE_PRESERVATION_MANIFEST.json",
        "V29R3_APR04_AIDC_ACTUATION_FORENSIC.csv", "V29R3_APR04_AIDC_ACTUATION_SUMMARY.json",
        "V29R3_TRUST_BOUND_ACTIVITY.csv", "V29R3_TRUST_BOUND_ATTRIBUTION.json",
        "V29R3_APR04_SERVICE_RACK_WATERFALL.csv", "V29R3_APR04_SERVICE_RACK_WATERFALL.json",
        "V29R3_RACK_CAPACITY_FORENSIC.csv", "V29R3_RACK_COUNTERFACTUAL_CEILINGS.json",
        "V29R3_CRITICAL_LINE_SENSITIVITY.csv", "V29R3_CRITICAL_LINE_SENSITIVITY_REVIEW.json",
        "V29R3_BACKGROUND_GRID_ATTRIBUTION.csv", "V29R3_BACKGROUND_GRID_ATTRIBUTION_REVIEW.json",
        "V29R3_CRITICAL_SLOT_EXECUTION_RETENTION.csv", "V29R3_EXECUTION_RETENTION_REVIEW.json",
        "V29R3_SERVICE_HURDLE_FORENSIC.json", "V29R3_SERVICE_MODEL_COMPARISON.csv",
        "V29R3_SERVICE_MODEL_DECISION.json", "V29R3_ROOT_CAUSE_FINAL_REVIEW.json",
        "V29R3_ROOT_CAUSE_FINAL_REVIEW.md", "V29R3_POSTCHANGE_PRESERVATION_AUDIT.json",
        "V29R3_ARTIFACT_SHA256.json",
    }
    assert required <= {path.name for path in OUT.iterdir() if path.is_file()}
