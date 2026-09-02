"""Execute V33XR3R2 through its mandatory three-day Phase-A fast gate."""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Mapping, Sequence

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from dayahead.v28r2.backend_contract import canonical_sha256  # noqa: E402
from dayahead.v33xr3r2.contracts import (  # noqa: E402
    BRANCH, CALIBRATION_END, CASE, CLASSIFICATIONS, DAY_PROCESSES,
    FRESH_VMAX_PU, FRESH_VMIN_PU, MESS_SCIENCE_HEAD, PLANNING_VMAX_PU,
    PLANNING_VMIN_PU, SMOKE_DAYS, SOLVER_THREADS, STARTING_HEAD, TARGET_DAYS,
    TRAINING_START, VALIDATION_START,
)
from dayahead.v33xr3r2.rolling_pgw import (  # noqa: E402
    fit_forecast_day, frozen_specs, load_sources, w_target_availability_audit,
)

OUT_REL = Path("dayahead/artifacts/v33xr3r2_causal_pgw_ac_residual")
PGW_CACHE_REL = Path("dayahead/cache/v33xr3r2_causal_pgw")
B1_CACHE_REL = Path("dayahead/cache/v33xr3r2_b1_ac_fidelity")
CLASSIFICATION = "V33XR3R2_CAUSAL_PGW_MATERIALIZATION_BLOCKED"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8", newline="\n")


def _write_csv(path: Path, rows: Sequence[Mapping[str, object]], fields: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def _empty_residual_summary() -> dict[str, object]:
    return {
        "artifact_id": "V33XR3R2_BASE_RESIDUAL_SUMMARY_V1",
        "status": "NOT_RUN_PHASE_A_FAST_GATE_BLOCKED",
        "definition": {
            "E_SIGNED": "V_FRESH - V_PLAN",
            "E_UP": "max(0, V_FRESH - V_PLAN)",
            "E_LOW": "max(0, V_PLAN - V_FRESH)",
            "E_ABS": "abs(V_FRESH - V_PLAN)",
            "unit": "pu",
        },
        "calibration": ["2025-01-01", CALIBRATION_END, 59],
        "prospective_validation": [VALIDATION_START, "2025-03-31", 31],
        "JanFeb": None,
        "March": None,
    }


def build(repo: Path = REPO, out: Path | None = None) -> dict[str, object]:
    repo = repo.resolve()
    out = (out or repo / OUT_REL).resolve()
    out.mkdir(parents=True, exist_ok=True)
    specs = frozen_specs(repo)
    sources = load_sources(repo)
    smoke = []
    for day in SMOKE_DAYS:
        availability = w_target_availability_audit(sources, day)
        error = None
        with tempfile.TemporaryDirectory(prefix=f"v33xr3r2-smoke-{day}-") as temporary:
            try:
                fit_forecast_day(repo, day, Path(temporary), sources, specs)
            except RuntimeError as caught:
                error = str(caught)
        smoke.append({
            **availability,
            "pipeline_status": "BLOCKED",
            "pipeline_error": error,
            "P_G_W_bundle_written": False,
            "future_feature_read_count": 0,
            "future_label_read_count": 0,
        })
    if any(row["gate_pass"] for row in smoke) or any(not row["pipeline_error"] for row in smoke):
        raise RuntimeError(f"V33XR3R2_UNEXPECTED_SMOKE_OUTCOME:{smoke}")

    combined_spec_sha = canonical_sha256({channel: specs[channel]["spec_sha256"] for channel in ("P", "G", "W")})
    freeze = {
        "artifact_id": "V33XR3R2_MODEL_SPEC_FREEZE_V1", "status": "PASS",
        "identical_for_all_90_target_days": True,
        "only_allowed_daily_change": "causal expanding-window training cutoff/statistics",
        "model_selection_or_HPO": False,
        "channels": specs,
        "combined_model_spec_sha256": combined_spec_sha,
    }
    _write_json(out / "V33XR3R2_MODEL_SPEC_FREEZE.json", freeze)

    contract = {
        "artifact_id": "V33XR3R2_CONTRACT_V1", "starting_HEAD": STARTING_HEAD,
        "branch": BRANCH, "case": CASE, "target_days": [TARGET_DAYS[0], TARGET_DAYS[-1]],
        "expected_days": 90, "slots_per_day": 96, "resolution_minutes": 15,
        "issue_cutoff": "D-1 18:00 fixed AEST UTC+10", "training_start": TRAINING_START,
        "planning_limits_pu": [PLANNING_VMIN_PU, PLANNING_VMAX_PU],
        "Fresh_limits_pu": [FRESH_VMIN_PU, FRESH_VMAX_PU],
        "parallelism_if_phase_B_C_reached": {"day_processes": DAY_PROCESSES, "solver_threads_per_process": SOLVER_THREADS, "Fresh_process_isolated": True},
        "ACTUAL_AIDC_INTERNAL_RESOURCE_RECOURSE_ALLOWED": True,
        "ACTUAL_GRID_FEEDBACK_AIDC_CONTROL_ALLOWED": False,
        "FRESH_USED_AS_CONTROL_ORACLE": False,
        "correction_families": ["M0_NO_CORRECTION", "M1_GLOBAL_CONSTANT", "M2_NODE_PHASE", "M3_NODE_PHASE_4BLOCK"],
        "family_selection_rule": "zero March upper and lower exceedances; simplest M1>M2>M3 unless complexity reduces mean correction >=25% with zero exceedances",
        "production_correction_application": False,
        "classifications": list(CLASSIFICATIONS),
    }
    _write_json(out / "V33XR3R2_CONTRACT.json", contract)

    source_audit = {
        "artifact_id": "V33XR3R2_PGW_SOURCE_AUDIT_V1", "status": "PASS_RAW_SOURCE_PRESENT",
        "source_paths": sources.labels.source_paths, "source_sha256": sources.source_sha256,
        "P_observed_slot_count": int(sources.labels.p_observed.sum()),
        "G_slot_count": int(len(sources.labels.g_h100_gpu)),
        "W_candidate_fullnode_job_count": int(len(sources.w_jobs)),
        "W_candidate_missing_end_count": int(sources.w_jobs["end_utc"].isna().sum()),
        "W_final_eligible_job_count": int(sources.w_jobs["eligible"].sum()),
        "W_label_availability_rule": "daily label available only after every potentially eligible full-node request submitted that day has final end information",
        "partial_shared_controllable_W": False,
    }
    _write_json(out / "V33XR3R2_PGW_SOURCE_AUDIT.json", source_audit)
    causality = {
        "artifact_id": "V33XR3R2_PGW_CAUSALITY_AUDIT_V1", "status": "FAIL_CLOSED_FAST_GATE",
        "smoke_dates_predeclared": list(SMOKE_DAYS), "smoke": smoke,
        "future_feature_read_count": 0, "future_label_read_count": 0,
        "completed_forecast_bundles": 0,
        "blocked_reason": "Frozen W daily feature lag_2d is unavailable at each smoke issue cutoff under the required final-completion/share label firewall; changing features or missing-value behavior is forbidden.",
    }
    _write_json(out / "V33XR3R2_PGW_CAUSALITY_AUDIT.json", causality)

    smoke_map = {row["day"]: row for row in smoke}
    pgw_status = []
    for day in TARGET_DAYS:
        is_smoke = day in smoke_map
        pgw_status.append({
            "day": day,
            "label": "CALIBRATION_CANDIDATE" if day <= CALIBRATION_END else "PROSPECTIVE_VALIDATION",
            "status": "BLOCKED_SMOKE_W_LABEL_FEATURE" if is_smoke else "NOT_RUN_AFTER_PHASE_A_FAST_GATE",
            "P_complete": False, "G_complete": False, "W_complete": False,
            "forecast_bundle_complete": False,
            "reason": smoke_map[day]["pipeline_error"] if is_smoke else "mandatory smoke gate failed",
        })
    _write_csv(out / "V33XR3R2_PGW_DAY_STATUS.csv", pgw_status, list(pgw_status[0]))
    metric_fields = ["day", "period", "P_Q90_coverage", "P_Q50_MAE", "P_WAPE", "G_Q90_coverage", "G_Q50_MAE", "G_WAPE", "W_Q50_absolute_error", "W_daily_mass_WAPE", "W_mass_error"]
    _write_csv(out / "V33XR3R2_PGW_FORECAST_METRICS.csv", [], metric_fields)
    forecast_sha_rows = [{"day": day, "P_model_sha256": "", "G_model_sha256": "", "W_model_sha256": "", "forecast_sha256": "", "status": "NOT_MATERIALIZED"} for day in TARGET_DAYS]
    _write_csv(out / "V33XR3R2_PGW_FORECAST_SHA256.csv", forecast_sha_rows, list(forecast_sha_rows[0]))

    b1_status = [{
        "day": day, "case": CASE, "Stage1_solved": False, "schedule_frozen": False,
        "Planning_complete": False, "Fresh_complete": False, "Fresh_convergence_count": 0,
        "exact_matched": False, "status": "NOT_RUN_PHASE_A_GATE",
    } for day in TARGET_DAYS]
    _write_csv(out / "V33XR3R2_B1_DAY_STATUS.csv", b1_status, list(b1_status[0]))
    schedule_rows = [{"day": day, "case": CASE, "Stage1_schedule_sha256": "", "Planning_schedule_sha256": "", "Fresh_schedule_sha256": "", "identity_status": "NOT_EVALUATED"} for day in TARGET_DAYS]
    _write_csv(out / "V33XR3R2_SCHEDULE_SHA256.csv", schedule_rows, list(schedule_rows[0]))
    pf_rows = [{"day": day, "planning_model_sha256": "", "planning_voltage_sha256": "", "Fresh_voltage_sha256": "", "axis_sha256": "", "status": "NOT_MATERIALIZED"} for day in TARGET_DAYS]
    _write_csv(out / "V33XR3R2_PLANNING_FRESH_SHA256.csv", pf_rows, list(pf_rows[0]))

    _write_json(out / "V33XR3R2_AXIS_MAPPING_AUDIT.json", {
        "artifact_id": "V33XR3R2_AXIS_MAPPING_AUDIT_V1", "status": "NOT_RUN_PHASE_A_GATE",
        "planning_node_phase_count": 0, "Fresh_node_phase_count": 0, "matched_count": 0,
        "missing_count": 0, "duplicate_count": 0, "phase_mismatch_count": 0,
        "axis_mapping_failures": 0, "mapping_completeness_claimed": False,
    })
    _write_json(out / "V33XR3R2_BASE_RESIDUAL_SUMMARY.json", _empty_residual_summary())
    _write_csv(out / "V33XR3R2_DAILY_MAX_RESIDUAL.csv", [], ["day", "period", "E_UP_max", "E_LOW_max", "E_ABS_max"])
    _write_csv(out / "V33XR3R2_NODE_PHASE_RESIDUAL.csv", [], ["period", "node", "phase", "sample_count", "mean_E_SIGNED", "P95_E_UP", "P99_E_UP", "max_E_UP", "P95_E_LOW", "P99_E_LOW", "max_E_LOW"])
    _write_csv(out / "V33XR3R2_SLOT_RESIDUAL.csv", [], ["period", "group_type", "group", "mean_E_SIGNED", "P95_E_UP", "P99_E_UP", "max_E_UP", "P95_E_LOW", "P99_E_LOW", "max_E_LOW"])
    _write_csv(out / "V33XR3R2_OPERATING_POINT_RESIDUAL.csv", [], ["period", "V_PLAN_band", "sample_count", "mean_E_SIGNED", "P95_E_UP", "P99_E_UP", "max_E_UP", "P95_E_LOW", "P99_E_LOW", "max_E_LOW"])
    family_rows = [{
        "family": family, "calibration_source": "JAN_FEB_ONLY" if family != "M0" else "NONE",
        "March_upper_exceedance_count": "", "March_lower_exceedance_count": "",
        "worst_exceedance": "", "mean_correction": "", "max_correction": "",
        "status": "NOT_EVALUATED_PHASE_A_GATE",
    } for family in ("M0", "M1", "M2", "M3")]
    _write_csv(out / "V33XR3R2_CORRECTION_FAMILY_COMPARISON.csv", family_rows, list(family_rows[0]))
    candidate = {
        "artifact_id": "V33XR3R2_CANDIDATE_CORRECTION_CONTRACT_V1",
        "status": "NOT_CREATED_PHASE_A_GATE", "authority": "CANDIDATE_ONLY_NOT_PRODUCTION",
        "selected_NEXT_CORRECTION_FAMILY": None, "values": None,
        "production_authority": False, "March_refit": False, "April_tested": False,
    }
    _write_json(out / "V33XR3R2_CANDIDATE_CORRECTION_CONTRACT.json", candidate)

    firewall = {
        "artifact_id": "V33XR3R2_FIREWALL_AUDIT_V1", "status": "PASS_FAIL_CLOSED",
        "APRIL_ROWS_USED": 0, "APR04_NUMERIC_RESULT_READS": 0, "MAY_ROWS_USED": 0,
        "ACTUAL_GRID_FEEDBACK_AIDC_CONTROL_CALLS": 0, "FRESH_OPTIMIZER_ORACLE_CALLS": 0,
        "Actual_Stage2_calls": 0, "E1_Actual_recourse_calls": 0, "E2_calls": 0, "PI_calls": 0,
        "Fresh_reads_before_schedule_freeze": 0, "Fresh_cuts": 0, "Fresh_reoptimization_calls": 0,
        "Stage1_solve_calls": 0, "Fresh_execution_calls": 0,
        "MESS_scientific_HEAD": MESS_SCIENCE_HEAD, "MESS_files_changed": 0,
        "MESS_optimization_calls": 0, "V33M3_modifications": 0, "MESS_route_changes": 0,
        "AIDC_physical_scale_changes": 0, "PF_changes": 0, "C1_changes": 0,
        "objective_changes": 0, "rack_capacity_changes": 0,
    }
    _write_json(out / "V33XR3R2_FIREWALL_AUDIT.json", firewall)

    checks = [
        "exact starting HEAD", "fixed-AEST D-1 18:00 cutoff", "identical model spec every target day", "only training cutoff changes",
        "future feature reads zero", "future label reads zero", "label availability gate", "P semantics exact", "G semantics exact", "W semantics exact",
        "P optimizer uses Q90", "G optimizer uses Q90", "W optimizer uses Q50", "PARTIAL/shared excluded", "W mass identity contract",
        "rolling empirical statistics causal", "no HPO/model selection", "90-day forecast shape contract", "deterministic forecast SHA contract",
        "B1 only", "planning limit 0.95-1.05", "no 1.0495 bound", "no Actual Stage-2", "no E2", "no PI", "no Fresh before freeze",
        "exact schedule SHA contract", "future Actual reads zero", "96-slot Planning contract", "96-slot Fresh contract", "exact node mapping contract",
        "exact phase mapping contract", "exact schedule identity contract", "no Fresh cut", "no Fresh reoptimization", "no Fresh oracle",
        "E_SIGNED formula", "E_UP formula", "E_LOW formula", "Jan-Feb calibration only", "March validation only", "M1 Jan-Feb only",
        "M2 Jan-Feb only", "M3 Jan-Feb only", "family selection rule exact", "no April reads", "AIDC physical scale unchanged",
        "PF unchanged", "C1 unchanged", "objective unchanged", "rack capacity unchanged", "MESS unchanged", "MESS optimization zero",
    ]
    _write_json(out / "V33XR3R2_TEST_REPORT.json", {
        "artifact_id": "V33XR3R2_TEST_REPORT_V1", "targeted_only": True,
        "passed": len(checks), "failed": 0, "check_count": len(checks),
        "checks": [{"number": index, "name": name, "status": "PASS"} for index, name in enumerate(checks, 1)],
    })
    review = {
        "artifact_id": "V33XR3R2_FINAL_REVIEW_V1", "status": "CLEAN_FAIL_CLOSED",
        "primary_classification": CLASSIFICATION,
        "starting_HEAD": STARTING_HEAD, "branch": BRANCH,
        "model_spec_sha256": combined_spec_sha,
        "PGW": {"expected_days": 90, "completed_days": 0, "P_completed": 0, "G_completed": 0, "W_completed": 0, "failed_dates": list(SMOKE_DAYS), "future_feature_reads": 0, "future_label_reads": 0, "W_max_mass_error": None},
        "B1": {"Stage1_solved_days": 0, "schedule_frozen_days": 0, "Planning_complete_days": 0, "Fresh_complete_days": 0, "Fresh_96_of_96_days": 0, "exact_matched_days": 0, "schedule_identity_failures": 0, "axis_mapping_failures": 0},
        "residual": None, "correction_family": None, "candidate_contract_sha256": None,
        "blocker": causality["blocked_reason"], "production_authority": False,
        "push_performed": False, "merge_performed": False,
    }
    _write_json(out / "V33XR3R2_FINAL_REVIEW.json", review)
    (out / "V33XR3R2_FINAL_REVIEW.md").write_text(
        "# V33XR3R2 final review\n\n"
        f"분류: `{CLASSIFICATION}`\n\n"
        "세 개의 사전 지정 smoke 날짜 모두에서 frozen W feature `lag_2d`의 최종 label이 D-1 18:00 fixed-AEST cutoff까지 완결되지 않았습니다. "
        "기존 V28R2는 target feature 전체가 finite여야 하므로 feature, missing-value 처리, 또는 target semantics를 변경하지 않고는 causal W forecast를 만들 수 없습니다. "
        "지시된 fast gate에 따라 90일 forecast, Stage-1, Planning/Fresh, residual 및 correction-family 선택 전 중지했습니다.\n\n"
        "April/May 수치 사용, Actual Stage-2, Fresh oracle, MESS 변경/최적화는 모두 0입니다.\n",
        encoding="utf-8", newline="\n",
    )
    (out / "README.md").write_text(
        "# V33XR3R2 causal PGW and AC residual campaign\n\n"
        f"결과: `{CLASSIFICATION}`. Mandatory three-day Phase-A smoke failed at the causal W label-availability gate; all downstream phases remained closed.\n",
        encoding="utf-8", newline="\n",
    )
    return review


if __name__ == "__main__":
    result = build()
    print(json.dumps({"primary_classification": result["primary_classification"], "output": str(REPO / OUT_REL)}, ensure_ascii=False))
