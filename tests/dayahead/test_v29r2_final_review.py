from __future__ import annotations

import csv
import json
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "dayahead/artifacts/v29r2_anchor_aware_trust_noregret"


def _rows(name: str) -> list[dict[str, str]]:
    with (OUT / name).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def test_apr04_required_outputs_and_frozen_schedule_contract() -> None:
    required = (
        "V29R2_APR04_DA_RESULTS.csv", "V29R2_APR04_ACTUAL_RESULTS.csv",
        "V29R2_APR04_PI_RESULTS.csv", "V29R2_APR04_OPENDSS_RESULTS.csv",
        "V29R2_APR04_SERVICE_RESULTS.csv", "V29R2_APR04_MESS_RESULTS.csv",
        "V29R2_APR04_V29_COMPARISON.csv", "V29R2_APR04_DEVELOPMENT_REVIEW.json",
        "V29R2_APR04_DEVELOPMENT_REVIEW.md", "V29R2_APR04_WORKLOAD_DECOMPOSITION.csv",
    )
    assert all((OUT / name).is_file() for name in required)
    review = json.loads((OUT / "V29R2_APR04_DEVELOPMENT_REVIEW.json").read_text(encoding="utf-8"))
    manifest = json.loads((OUT / "V29R2_APR04_DAYAHEAD_SCHEDULE_MANIFEST.json").read_text(encoding="utf-8"))
    assert review["RESULT_CLASSIFICATION"] == "V29R2_APR04_DEVELOPMENT_CHECKPOINT_PASS"
    assert review["full_Apr1_4_regression_justified"] is True
    assert review["independent_validation"] is False and review["final_validation"] is False
    assert manifest["B0_B2_reference_schedule_bytes_identical"] is True
    assert manifest["actual_namespace_open_before_freeze"] == 0
    assert manifest["future_actual_reads_before_freeze"] == 0


def test_apr04_no_regret_actual_firewall_and_fresh_physics() -> None:
    da = {row["case"]: float(row["planning_objective"]) for row in _rows("V29R2_APR04_DA_RESULTS.csv")}
    assert da["B1"] <= da["B0"] + 1e-4
    assert da["B2"] <= da["B0"] + 1e-4
    assert da["B3"] <= min(da["B1"], da["B2"]) + 1e-4
    decision = _rows("V29R2_MESS_FALLBACK_DECISION.csv")
    assert len(decision) == 1 and decision[0]["selected_rung"] == "Q_RELEASE" and decision[0]["safe"] == "True"
    q_release = [row for row in _rows("V29R2_MESS_NOREGRET_AC_GATE.csv") if row["rung"] == "Q_RELEASE"]
    assert {row["scenario"] for row in q_release} == {"S_NOM", "S_LOW", "S_ZERO_CARRY"}
    assert all(float(row["planning_delta_vs_B2"]) <= 1e-4 for row in q_release)
    assert all(float(row["rho_AC_delta_vs_B2"]) <= 1e-4 and row["all_converged"] == "True" for row in q_release)
    actual = {row["case"]: row for row in _rows("V29R2_APR04_ACTUAL_RESULTS.csv")}
    assert set(actual) == {"R0", "B0", "B1", "B2", "B3"}
    assert all(int(row["actual_reoptimization_calls"]) == 0 for row in actual.values())
    assert all(float(row["hidden_shedding_nodeh"]) == 0 for row in actual.values())
    assert all(abs(float(row["workload_mass_error_nodeh"])) <= 1e-8 for row in actual.values())
    assert float(actual["B3"]["rho_max_AC"]) <= float(actual["B2"]["rho_max_AC"]) + 1e-4
    physical = _rows("V29R2_APR04_OPENDSS_RESULTS.csv")
    assert len(physical) == 10
    assert all(int(row["convergence_count"]) == 96 and int(row["clean_engine_count"]) == 1 for row in physical)
    pi = _rows("V29R2_APR04_PI_RESULTS.csv")
    assert len(pi) == 1 and int(pi[0]["DA_namespace_reads"]) == 0


def test_apr04_workload_miss_decomposition_and_service_authority() -> None:
    workload = _rows("V29R2_APR04_WORKLOAD_DECOMPOSITION.csv")
    assert {row["case"] for row in workload} == {"B0", "B1", "B2", "B3"}
    for row in workload:
        missed = float(row["missed_workload_nodeh"])
        source = float(row["source_availability_miss_nodeh"])
        rack = float(row["rack_capacity_miss_nodeh"])
        assert min(missed, source, rack) >= -1e-8
        assert abs(missed - source - rack) <= 1e-8
        assert abs(float(row["decomposition_identity_error_nodeh"])) <= 1e-8
        assert int(row["actual_optimizer_calls"]) == 0
    service = _rows("V29R2_APR04_SERVICE_RESULTS.csv")
    assert service and all(0 <= float(row["H_LOW"]) <= float(row["H_NOM"]) <= float(row["H_REQ"]) for row in service)
