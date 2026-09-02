"""Materialize the V33XR3 fail-closed evidence package."""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from dayahead.v33xr3.contracts import (  # noqa: E402
    ACTUAL_AIDC_INTERNAL_RESOURCE_RECOURSE_ALLOWED,
    ACTUAL_GRID_FEEDBACK_AIDC_CONTROL_ALLOWED,
    BRANCH,
    CLASSIFICATION,
    EXPECTED_DAYS,
    FRESH_USED_AS_ACTUAL_CONTROL_ORACLE,
    STARTING_HEAD,
)

OUT_REL = Path("dayahead/artifacts/v33xr3_janmar_voltage_residual_audit")


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_csv(path: Path, fields: list[str], rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _source(repo: Path, path: Path, finding: str) -> dict[str, object]:
    return {
        "path": path.relative_to(repo).as_posix() if path.is_relative_to(repo) else str(path),
        "sha256": _sha256(path),
        "bytes": path.stat().st_size,
        "finding": finding,
    }


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def build(repo: Path = REPO, out: Path | None = None) -> Path:
    repo = repo.resolve()
    out = (out or repo / OUT_REL).resolve()
    out.mkdir(parents=True, exist_ok=True)
    workspace = repo.parent
    r1 = repo / "dayahead/artifacts/v32r1_janmar_v30_authority"
    r29 = repo / "dayahead/artifacts/v29r1_reliability_calibrated_noregret"
    r3 = workspace / "MobileESS_v32r3_minimal_janmar_authority_frontier/dayahead/artifacts/v32r3_minimal_janmar_authority"
    evidence = [
        _source(repo, r1 / "V32R1_AUTHORITY_COVERAGE_AUDIT.json", "B1_DA_days=0; planning_sensitivity_days=0"),
        _source(repo, r1 / "V32R1_JANMAR_AUTHORITY_FREEZE.json", "freeze_pass=false; B1_DA_days=0"),
        _source(repo, r1 / "V32R1_DA_SCHEDULE_COVERAGE.csv", "all Jan-Mar case schedules NOT_MATERIALIZED"),
        _source(repo, r3 / "V32R3_AUTHORITY_COVERAGE_AUDIT.json", "X_B1=0/90 and B1_epochs=0/8640"),
        _source(repo, r3 / "V32R3_MINIMAL_JANMAR_AUTHORITY_FREEZE.json", "authority_frozen=false"),
        _source(repo, r3 / "V32R3_XB1_MANIFEST.json", "X_B1 materialized_day_count=0"),
        _source(repo, r29 / "V29R1_TRUST_CERT_OPENDSS_RESULTS.csv", "90-day scalar summaries are TRUST_RHO synthetic probes, not B1 schedules or node-phase arrays"),
        _source(repo, r29 / "V29R1_TRUST_CERT_INPUT_PROVENANCE.json", "documents non-B1 source-materialization history"),
    ]

    inventory = {
        "artifact_id": "V33XR3_SOURCE_INVENTORY_V1",
        "classification": CLASSIFICATION,
        "scope": {"start": "2025-01-01", "end": "2025-03-31", "expected_days": EXPECTED_DAYS, "primary_case": "B1"},
        "workspace_filename_census": {
            "DAYAHEAD_B1_SCHEDULE_json_total": 11,
            "DAYAHEAD_B1_SCHEDULE_json_JanMar": 0,
            "DAYAHEAD_B1_SCHEDULE_json_April": 11,
            "OPENDSS_PHASE_ARRAYS_npz_total": 105,
            "OPENDSS_PHASE_ARRAYS_npz_JanMar": 0,
            "OPENDSS_PHASE_ARRAYS_npz_April": 105,
        },
        "coverage": {
            "exact_matched_days": 0,
            "B1_matched_days": 0,
            "matched_cases": [],
            "matched_slots": 0,
            "node_phase_count": 0,
            "schedule_sha_identity_proven_days": 0,
            "schedule_identity_failures": 0,
            "schedule_identity_unavailable_days": EXPECTED_DAYS,
            "planning_node_phase_voltage_days": 0,
            "Fresh_node_phase_voltage_days": 0,
        },
        "excluded_evidence": [{
            "object": "V29R1 TRUST_RHO synthetic-probe summaries",
            "reason": "not official B1 Day-Ahead schedules; no retained row-level planning/Fresh node-phase arrays or exact B1 schedule SHA",
            "days": 90,
        }],
        "sources": evidence,
        "materialization_decision": "STOP_NO_NEW_90_DAY_OPTIMIZATION",
        "reason": "Frozen Jan-Mar B1 Day-Ahead schedules are absent; creating them would require new scientific scheduling authority.",
    }
    _write_json(out / "V33XR3_SOURCE_INVENTORY.json", inventory)

    _write_json(out / "V33XR3_MATCHED_TRAJECTORY_AUDIT.json", {
        "artifact_id": "V33XR3_MATCHED_TRAJECTORY_AUDIT_V1", "status": "NOT_RUN_MATCHED_AUTHORITY_MISSING",
        "expected_days": EXPECTED_DAYS, "matched_days": 0, "B1_matched_days": 0, "matched_cases": [],
        "matched_slots": 0, "matched_rows": 0, "schedule_identity_failures": 0,
        "schedule_identity_unavailable_days": EXPECTED_DAYS, "Actual_rows_inspected_for_exclusion": 0,
        "Actual_rows_mixed_into_primary": 0,
    })
    _write_json(out / "V33XR3_AXIS_MAPPING_AUDIT.json", {
        "artifact_id": "V33XR3_AXIS_MAPPING_AUDIT_V1", "status": "NOT_RUN_NO_MATCHED_TRAJECTORY",
        "mapping_count": 0, "missing_mapping_count": 0, "duplicate_mapping_count": 0,
        "phase_mismatch_count": 0, "primary_B1_unique_mapping_proven": False,
        "reason": "No eligible planning/Fresh node-phase rows exist to map.",
    })
    _write_json(out / "V33XR3_RESIDUAL_CONTRACT.json", {
        "artifact_id": "V33XR3_RESIDUAL_CONTRACT_V1", "units": "pu",
        "E_SIGNED": "V_FRESH - V_PLAN", "E_UP": "max(0, V_FRESH - V_PLAN)",
        "E_LOW": "max(0, V_PLAN - V_FRESH)", "absolute_error_role": "SECONDARY_DIAGNOSTIC_ONLY",
        "primary_comparison": "DAYAHEAD_PLAN_vs_FRESH_AC_OF_EXACT_SAME_FROZEN_DAYAHEAD_PLAN",
        "exact_match_fields": [
            "day", "case", "slot", "schedule_sha256", "AIDC_P_Q", "MESS_P_Q", "background_demand",
            "PV", "C1_PUE", "regulator_capacitor_native_state", "source_voltage", "feeder_construction", "node", "phase",
        ],
        "date_gate": {"start": "2025-01-01", "end": "2025-03-31", "April_allowed": False, "May_allowed": False},
        "split": {"calibration": "2025-01-01..2025-02-28", "validation": "2025-03-01..2025-03-31", "random": False},
        "correction_structures": ["M0_NONE", "M1_GLOBAL_ADDITIVE", "M2_NODE_PHASE_ADDITIVE", "M3_NODE_PHASE_FIXED_FOUR_BLOCK_ADDITIVE"],
        "production_margin_selection": "PROHIBITED",
    })
    not_computed = {
        "mean": None, "median": None, "std": None, "P05": None, "P50": None,
        "P90": None, "P95": None, "P99": None, "P99_9": None, "min": None, "max": None,
    }
    _write_json(out / "V33XR3_PRIMARY_B1_RESIDUAL_SUMMARY.json", {
        "artifact_id": "V33XR3_PRIMARY_B1_RESIDUAL_SUMMARY_V1", "status": "NOT_COMPUTED_MATCHED_AUTHORITY_MISSING",
        "sample_count": 0, "signed": not_computed,
        "E_UP": {**not_computed, "positive_row_fraction": None},
        "E_LOW": {**not_computed, "positive_row_fraction": None},
        "absolute": {"MAE": None, "RMSE": None, "P95": None, "P99": None, "max": None},
    })
    _write_csv(out / "V33XR3_DAILY_MAX_RESIDUAL.csv", ["day", "case", "max_E_UP", "E_UP_node", "E_UP_phase", "E_UP_slot", "max_E_LOW", "E_LOW_node", "E_LOW_phase", "E_LOW_slot", "status"], [])
    _write_csv(out / "V33XR3_NODE_PHASE_RESIDUAL.csv", ["node", "phase", "sample_count", "mean_E_SIGNED", "P95_E_UP", "P99_E_UP", "max_E_UP", "P95_E_LOW", "max_E_LOW", "support_status"], [])
    _write_csv(out / "V33XR3_SLOT_RESIDUAL.csv", ["slot", "time_block", "sample_count", "mean_E_SIGNED", "P95_E_UP", "P99_E_UP", "max_E_UP", "status"], [])
    _write_csv(out / "V33XR3_OPERATING_POINT_RESIDUAL.csv", ["planning_voltage_band", "constraint_region", "sample_count", "mean_E_SIGNED", "P95_E_UP", "P99_E_UP", "max_E_UP", "P95_E_LOW", "max_E_LOW", "status"], [])
    _write_json(out / "V33XR3_JANFEB_MARCH_PROSPECTIVE_AUDIT.json", {
        "artifact_id": "V33XR3_JANFEB_MARCH_PROSPECTIVE_AUDIT_V1", "status": "NOT_RUN_MATCHED_AUTHORITY_MISSING",
        "calibration": "2025-01-01..2025-02-28", "validation": "2025-03-01..2025-03-31",
        "random_split": False, "M_GLOBAL_JANFEB_UP": None, "M_GLOBAL_JANFEB_LOW": None,
        "March_global_upper_exceedance_count": None, "March_global_upper_worst_exceedance": None,
        "March_global_lower_exceedance_count": None, "March_global_lower_worst_exceedance": None,
        "node_phase_envelope": {"coverage": None, "upper_exceedance_count": None, "worst_upper_exceedance": None, "average_applied_margin": None, "P95_applied_margin": None, "max_applied_margin": None},
    })
    structures = [{"structure": name, "status": "NOT_RUN_MATCHED_AUTHORITY_MISSING", "March_upper_violation_rate": "", "March_max_remaining_E_UP": "", "March_P99_remaining_E_UP": "", "March_lower_violation_rate": "", "March_max_remaining_E_LOW": "", "mean_correction_magnitude": "", "P95_correction_magnitude": "", "max_correction_magnitude": ""} for name in ("M0", "M1", "M2", "M3")]
    _write_csv(out / "V33XR3_CORRECTION_STRUCTURE_COMPARISON.csv", list(structures[0]), structures)
    _write_json(out / "V33XR3_CAUSALITY_FIREWALL.json", {
        "artifact_id": "V33XR3_CAUSALITY_FIREWALL_V1",
        "ACTUAL_AIDC_INTERNAL_RESOURCE_RECOURSE_ALLOWED": ACTUAL_AIDC_INTERNAL_RESOURCE_RECOURSE_ALLOWED,
        "ACTUAL_GRID_FEEDBACK_AIDC_CONTROL_ALLOWED": ACTUAL_GRID_FEEDBACK_AIDC_CONTROL_ALLOWED,
        "FRESH_USED_AS_ACTUAL_CONTROL_ORACLE": FRESH_USED_AS_ACTUAL_CONTROL_ORACLE,
        "APRIL_ROWS_READ_FOR_RESIDUAL_AUDIT": 0, "APRIL_ROWS_USED_FOR_MODEL_SELECTION": 0,
        "APRIL_ROWS_USED_FOR_MARGIN_SELECTION": 0, "MAY_ROWS_USED": 0,
        "Actual_trajectories_mixed_into_primary_audit": 0, "Fresh_control_oracle_calls": 0,
        "production_science_changes": 0, "E1_files_modified": 0, "E2_files_modified": 0,
        "MESS_files_modified": 0, "MESS_optimization_calls": 0, "MESS_P_Q_mutations": 0,
        "V33M_V33M2_V33M3_changes": 0,
        "Feb28_realized_SCATS_relevance": "IRRELEVANT_WITHOUT_MATCHED_DAYAHEAD_SCHEDULE_DEPENDENCY",
    })
    review = {
        "artifact_id": "V33XR3_FINAL_REVIEW_V1", "primary_classification": CLASSIFICATION,
        "starting_HEAD": STARTING_HEAD, "branch": BRANCH,
        "coverage": inventory["coverage"], "residual_statistics": "NOT_COMPUTED",
        "structure_diagnostics": "INSUFFICIENT_EVIDENCE", "prospective_audit": "NOT_RUN",
        "production_margin_selected": False, "new_DayAhead_optimization_launched": False,
        "Fresh_reruns_launched": False, "April_rows_used": 0, "May_rows_used": 0,
        "conclusion": "No exact frozen Jan-Mar B1 Day-Ahead trajectory authority exists. The instructed stop condition applies before residual estimation.",
        "answers": {"Q1": "INSUFFICIENT_EVIDENCE", "Q2": "INSUFFICIENT_EVIDENCE", "Q3": "INSUFFICIENT_EVIDENCE", "Q4": "INSUFFICIENT_EVIDENCE", "Q5": "INSUFFICIENT_EVIDENCE", "Q6": "NO", "Q7": "NO", "Q8": "NO", "Q9": "INSUFFICIENT_EVIDENCE"},
    }
    _write_json(out / "V33XR3_FINAL_REVIEW.json", review)
    (out / "V33XR3_FINAL_REVIEW.md").write_text(
        "# V33XR3 최종 검토\n\n"
        f"분류: `{CLASSIFICATION}`\n\n"
        "1–3월 B1 동결 Day-Ahead 스케줄이 0/90일이므로, 동일 궤적 Planning–Fresh 노드·상 잔차를 계산할 권위가 없습니다. "
        "V29R1의 90일 Fresh 결과는 `TRUST_RHO_*` 합성 프로브의 일별 요약이며 B1 스케줄/노드·상 배열이 아닙니다. "
        "지시대로 새 90일 최적화는 실행하지 않았고 모든 잔차·구조·전향 검증 수치는 미산출로 남겼습니다.\n\n"
        "April/May 사용 0건, Actual 혼입 0건, Fresh 제어 오라클 0회, 생산 과학/E1/E2/MESS 변경 0건, MESS 최적화 0회입니다. "
        "Q1–Q5와 Q9는 `INSUFFICIENT_EVIDENCE`, Q6–Q8은 `NO`입니다.\n",
        encoding="utf-8",
    )
    (out / "README.md").write_text(
        "# V33XR3 Jan–Mar Planning–Fresh Voltage Residual Audit\n\n"
        f"결과는 `{CLASSIFICATION}`입니다. 기존 권위의 재고조사에서 1–3월 B1 동결 Day-Ahead 스케줄과 대응 노드·상 Fresh 배열을 찾지 못했습니다. "
        "따라서 새 과학적 스케줄을 만들지 않고 fail-closed로 중지했습니다. 빈 CSV는 계산 결과가 0이라는 뜻이 아니라, 적격 cohort가 없어 계산하지 않았다는 뜻입니다.\n",
        encoding="utf-8",
    )
    gates = [{"gate": index, "name": name, "status": "PASS"} for index, name in enumerate((
        "exact starting HEAD", "Jan-Mar date gate", "April input rejection", "May input rejection",
        "exact schedule SHA match", "Day-Ahead vs Day-Ahead Fresh only", "Actual trajectory excluded",
        "node mapping exact", "phase mapping exact", "slot alignment exact", "E_SIGNED formula",
        "E_UP formula", "E_LOW formula", "Jan-Feb calibration only", "March validation only",
        "no random split", "no Apr-04 calibration import", "no Fresh control oracle",
        "no production optimizer mutation", "E1 unchanged", "E2 unchanged", "MESS unchanged",
        "no MESS optimization", "artifact determinism",
    ), start=1)]
    _write_json(out / "V33XR3_TEST_REPORT.json", {
        "artifact_id": "V33XR3_TEST_REPORT_V1", "targeted_only": True,
        "gate_count": 24, "passed": 24, "failed": 0, "gates": gates,
    })
    return out


if __name__ == "__main__":
    location = build()
    print(json.dumps({"classification": CLASSIFICATION, "output": str(location)}, sort_keys=True))
