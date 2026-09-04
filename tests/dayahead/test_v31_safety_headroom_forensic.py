"""V31 diagnostic artifact and scientific-contract gates."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dayahead/artifacts/v31_v30_safety_headroom_forensic"


def j(name: str) -> dict[str, object]:
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def rows(name: str) -> list[dict[str, str]]:
    with (OUT / name).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def test_01_exact_v30_starting_head() -> None:
    assert j("V31_STARTING_AUTHORITY_AUDIT.json")["verified_V30_starting_HEAD"] == "f0fcc1c2835cc90b65aab7b788f1b55af544f6ea"


def test_02_v30_artifact_sha_identity() -> None:
    assert j("V31_STARTING_AUTHORITY_AUDIT.json")["V30_artifact_aggregate_sha256"] == "db57e68d116707d45ec0af4ab111a6e25ce4ee0234d08353e86dc498e7898fcb"


def test_03_v29r2_preservation() -> None:
    assert j("V31_STARTING_AUTHORITY_AUDIT.json")["V29R2_artifact_aggregate_sha256"] == "ca24e661450b7af0e894730602166c792711273e3b4a873976b7a61b4f96a3b2"


def test_04_v29r3_preservation() -> None:
    assert j("V31_STARTING_AUTHORITY_AUDIT.json")["V29R3_artifact_aggregate_sha256"] == "3ab09255797942f04a2aa0cd15f2c5c1870bcb71b6dff7b0676b76b853f6e223"


def test_05_exact_current_margin() -> None:
    assert j("V31_CURRENT_MARGIN_REPRODUCTION.json")["M_CURRENT_pu"] == 0.0009917274479849247


def test_06_current_margin_formula() -> None:
    assert j("V31_CURRENT_MARGIN_REPRODUCTION.json")["exact_implemented_formula"] == "max_preApril_day(2 * rho1_candidate_max_abs_planning_minus_Fresh_current_error_pu)"


def test_07_paired_error_identity() -> None:
    assert max(abs(float(r["identity_error_pu"])) for r in rows("V31_PREAPRIL_PAIRED_ERROR_LEDGER.csv")) <= 1e-15


def test_08_no_april_paired_rows() -> None:
    assert all(r["day"] < "2025-04-01" and int(r["April_rows_used"]) == 0 for r in rows("V31_PREAPRIL_PAIRED_ERROR_LEDGER.csv"))


def test_09_paired_uses_janmar_only() -> None:
    data = rows("V31_PREAPRIL_PAIRED_ERROR_LEDGER.csv")
    assert len(data) == 90 and min(r["day"] for r in data) == "2025-01-01" and max(r["day"] for r in data) == "2025-03-31"


def test_10_b1_anchor_exact() -> None:
    assert j("V31_PAIRED_MARGIN_DIAGNOSTIC.json")["B1_anchor"] == "B0"


def test_11_b3_anchor_exact() -> None:
    assert j("V31_PAIRED_MARGIN_DIAGNOSTIC.json")["B3_anchor"] == "B2"


def test_12_diagnostics_non_authority() -> None:
    assert set(j("V31_FINAL_BOTTLENECK_REVIEW.json")["diagnostic_trajectories"].values()) == {"NON_AUTHORITY_DIAGNOSTIC_ONLY"}


def test_13_official_cases_exactly_four() -> None:
    review = j("V31_FINAL_BOTTLENECK_REVIEW.json")
    assert review["official_case_count"] == 4 and review["official_cases"] == ["B0", "B1", "B2", "B3"]


def test_14_no_v30_production_change_authorized() -> None:
    assert j("V31_FINAL_BOTTLENECK_REVIEW.json")["V30_production_change_authorized"] is False


@pytest.mark.parametrize("case,expected", [("B1", 59.18816048947252), ("B3", 62.38843607314548)])
def test_15_dcur_reproduces_official_stage2(case: str, expected: float) -> None:
    data = rows("V31_APR04_MARGIN_COUNTERFACTUAL.csv")
    row = next(r for r in data if r["case"] == case and r["diagnostic"] == "D_CUR")
    assert float(row["executed_nodeh"]) == pytest.approx(expected, abs=1e-12)


def test_16_dpair_fixed_janmar_margin() -> None:
    data = [r for r in rows("V31_APR04_MARGIN_COUNTERFACTUAL.csv") if r["diagnostic"] == "D_PAIR"]
    assert data and all(float(r["margin_pu"]) == 0.0004958637239924624 for r in data)


def test_17_dzero_margin_zero() -> None:
    data = [r for r in rows("V31_APR04_MARGIN_COUNTERFACTUAL.csv") if r["diagnostic"] == "D_ZERO"]
    assert data and all(float(r["margin_pu"]) == 0.0 for r in data)


def test_18_stage1_schedule_fixed() -> None:
    assert all(r["Stage1_schedule_fixed"] == "True" for r in rows("V31_APR04_MARGIN_COUNTERFACTUAL.csv"))


def test_19_mess_fixed() -> None:
    assert all(r["MESS_fixed"] == "True" for r in rows("V31_APR04_MARGIN_COUNTERFACTUAL.csv"))


def test_20_same_slot_only() -> None:
    assert all(r["same_slot_causal_information_fixed"] == "True" for r in rows("V31_APR04_MARGIN_COUNTERFACTUAL.csv"))


def test_21_future_actual_reads_zero() -> None:
    assert all(int(r["April_rows_used"]) == 0 for r in rows("V31_PREAPRIL_PAIRED_ERROR_LEDGER.csv"))


def test_22_no_preemption() -> None:
    assert "preemption" not in j("V31_FINAL_BOTTLENECK_REVIEW.json").get("one_next_scientific_change", "").lower()


def test_23_no_running_job_migration() -> None:
    assert "migration" not in j("V31_FINAL_BOTTLENECK_REVIEW.json").get("one_next_scientific_change", "").lower()


def test_24_strict_full_authority_preserved() -> None:
    assert j("V31_STARTING_AUTHORITY_AUDIT.json")["V30_result"] == "V30_APR04_TWO_STAGE_AIDC_DEVELOPMENT_CHECKPOINT_PASS"


@pytest.mark.parametrize("case", ["B1", "B3"])
def test_25_workload_mass_identity(case: str) -> None:
    wf = j("V31_APR04_EXECUTION_WATERFALL.json")["cases"][case]
    total = wf["EXECUTED_nodeh"] + wf["SOURCE_UNAVAILABLE_nodeh"] + wf["TRUE_RACK_CAPACITY_LIMIT_nodeh"] + wf["NOMINAL_CURRENT_LIMIT_nodeh"] + wf["CURRENT_MARGIN_ONLY_nodeh"]
    assert total == pytest.approx(wf["DA_AUTHORIZED_nodeh"], abs=1e-9)


def test_26_safety_reason_exclusive() -> None:
    allowed = {"CURRENT_MARGIN_ONLY", "NOMINAL_CURRENT_LIMIT"}
    assert rows("V31_APR04_GRID_SAFETY_BLOCK_LEDGER.csv") and all(r["primary_blocking_reason"] in allowed for r in rows("V31_APR04_GRID_SAFETY_BLOCK_LEDGER.csv"))


def test_27_waterfall_identity() -> None:
    assert max(abs(float(r["identity_error_nodeh"])) for r in rows("V31_APR04_EXECUTION_WATERFALL.csv")) <= 1e-9


def test_28_headroom_accounting_identity() -> None:
    data = rows("V31_RECOURSE_HEADROOM_FORENSIC.csv")
    assert len(data) == 2 * 96 * 48
    assert all(float(r["h_REC_nodeh"]) >= -1e-12 for r in data)


def test_29_fresh_ex_post_only() -> None:
    assert j("V31_APR04_FALSE_SAFETY_BLOCK_REVIEW.json")["Fresh_used_ex_post_only"] is True


def test_30_fresh_solve_count_bound() -> None:
    review = j("V31_APR04_FALSE_SAFETY_BLOCK_REVIEW.json")
    assert review["new_Fresh_trajectory_count"] == 4 and review["new_full_slot_Fresh_solve_count"] == 384


def test_31_no_physical_parameter_change() -> None:
    assert j("V31_APR04_MARGIN_COUNTERFACTUAL.json")["rows"][0]["rack_authority_fixed"] is True


def test_32_required_not_run_zero_contract() -> None:
    assert not (OUT / "V31_TEST_REPORT.json").exists() or j("V31_TEST_REPORT.json")["not_run"] == 0


def test_33_margin_partition() -> None:
    for value in j("V31_APR04_GRID_SAFETY_BLOCK_SUMMARY.json")["cases"].values():
        assert value["GRID_SAFETY_BLOCKED_nodeh"] == pytest.approx(value["CURRENT_MARGIN_ONLY_nodeh"] + value["NOMINAL_CURRENT_LIMIT_nodeh"], abs=1e-9)


def test_34_signed_evidence_limitation_explicit() -> None:
    value = j("V31_PAIRED_MARGIN_DIAGNOSTIC.json")
    assert value["signed_elementwise_residual_arrays_frozen"] is False and value["candidate_anchor_error_correlation"] is None


def test_35_fresh_convergence_complete() -> None:
    data = [r for r in rows("V31_APR04_FALSE_SAFETY_BLOCK.csv") if r["row_type"] == "FRESH_TRAJECTORY"]
    assert len(data) == 4 and all(int(r["convergence_count"]) == 96 for r in data)


def test_36_b3_slot63_delta() -> None:
    value = j("V31_CRITICAL_SLOT_RECOURSE_FORENSIC.json")
    assert value["B3_slot63_reproduced"] is True


def test_37_margin_reduction_exact() -> None:
    value = j("V31_MARGIN_COMPARISON.json")
    assert value["margin_reduction_percent"] == 50.0


def test_38_stage2_voltage_transformer_not_misrepresented() -> None:
    data = rows("V31_APR04_GRID_SAFETY_BLOCK_LEDGER.csv")
    assert all(r["voltage_constraint_state"] == "NOT_MODELED_IN_V30_STAGE2" and r["transformer_constraint_state"] == "NOT_MODELED_IN_V30_STAGE2" for r in data)


def test_39_fresh_dpair_no_regret() -> None:
    data = [r for r in rows("V31_APR04_FALSE_SAFETY_BLOCK.csv") if r["diagnostic"] == "D_PAIR"]
    assert len(data) == 2 and all(r["anchor_relative_no_regret"] == "True" for r in data)


def test_40_fresh_dzero_no_regret() -> None:
    data = [r for r in rows("V31_APR04_FALSE_SAFETY_BLOCK.csv") if r["row_type"] == "FRESH_TRAJECTORY" and r["diagnostic"] == "D_ZERO"]
    assert len(data) == 2 and all(r["anchor_relative_no_regret"] == "True" for r in data)
