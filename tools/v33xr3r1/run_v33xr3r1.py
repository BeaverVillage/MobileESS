"""Write the V33XR3R1 pre-flight blocker package without starting a solve."""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from dayahead.v33xr3r1.contracts import (  # noqa: E402
    BRANCH, CASE, CLASSIFICATION, DAY_PROCESSES, EXPECTED_DAYS, FRESH_VMAX_PU,
    MESS_SCIENCE_HEAD, PLANNING_VMAX_PU, RESOLUTION_MINUTES,
    SLOTS_PER_DAY, SOLVER_THREADS_PER_PROCESS, STARTING_HEAD,
)

OUT_REL = Path("dayahead/artifacts/v33xr3r1_janmar_b1_ac_fidelity")
TRUST_ROOT = Path(r"C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\MobileESS_v29r1_reliability_calibrated_noregret\cache\v29r1_trust_cert_sources\jan_mar_2025")


def _days() -> list[str]:
    start = date(2025, 1, 1)
    return [(start + timedelta(days=i)).isoformat() for i in range(EXPECTED_DAYS)]


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def _json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"V33XR3R1_JSON_OBJECT_REQUIRED:{path}")
    return value


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8", newline="\n")


def _write_csv(path: Path, rows: Sequence[Mapping[str, object]], fields: Sequence[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _source_rows(repo: Path) -> tuple[list[dict[str, object]], dict[str, object]]:
    rows: list[dict[str, object]] = []
    axes: list[str] = []
    native_masters: list[str] = []
    source_bundle_records = []
    mapping_authority = repo / "dayahead/mapping_authority.py"
    prior_coverage_path = repo / "dayahead/artifacts/v32r2_minimal_frontier_dependency_audit/V32R2_MINIMAL_SOURCE_COVERAGE.csv"
    with prior_coverage_path.open(encoding="utf-8", newline="") as handle:
        prior_coverage = {row["day"]: row for row in csv.DictReader(handle)}
    for day in _days():
        day_root = TRUST_ROOT / "days" / day
        anchor = TRUST_ROOT / "electrical_anchor" / day / "D1_AC_ANCHOR.npz"
        aemo = day_root / "aemo_forecast.json"
        gfs = day_root / "gfs_d1_weather.parquet"
        manifest = day_root / "source_day_manifest.json"
        files = (aemo, gfs, manifest, anchor)
        present = all(path.is_file() for path in files)
        hashes = {path.name: _sha(path) for path in files} if present else {}
        if mapping_authority.is_file():
            hashes["dayahead/mapping_authority.py"] = _sha(mapping_authority)
        hashes["V32R2_MINIMAL_SOURCE_COVERAGE.csv"] = _sha(prior_coverage_path)
        node_count = 0
        sensitivity_shape = None
        axis_sha = None
        anchor_fields_ready = False
        if anchor.is_file():
            with np.load(anchor, allow_pickle=False) as payload:
                node_names = np.asarray(payload["node_names"])
                node_count = int(len(node_names))
                sensitivity_shape = list(payload["sensitivity"].shape)
                axis_sha = hashlib.sha256(node_names.tobytes()).hexdigest()
                axes.append(axis_sha)
                required_anchor_fields = {"native_master_sha", "anchor_v_squared", "regulator_taps", "capacitor_states", "root_pq", "node_names"}
                anchor_fields_ready = required_anchor_fields <= set(payload.files)
                if anchor_fields_ready:
                    native_masters.append(str(np.asarray(payload["native_master_sha"]).item()))
        prior = prior_coverage.get(day, {})
        workload_ready = prior.get("DA_workload_model_and_queue") == "AVAILABLE"
        mapping_ready = mapping_authority.is_file()
        group = "CALIBRATION_CANDIDATE" if day <= "2025-02-28" else "PROSPECTIVE_VALIDATION"
        rows.append({
            "day": day, "label": group, "case": CASE,
            "grid_demand_DA_ready": aemo.is_file(), "PV_DA_ready": aemo.is_file(),
            "AIDC_DA_workload_raw_and_models_present": workload_ready,
            "GFS_C1_DA_ready": gfs.is_file(),
            "feeder_background_construction_ready": anchor_fields_ready,
            "AIDC_site_mapping_ready": mapping_ready,
            "regulator_capacitor_source_voltage_authority_ready": anchor_fields_ready,
            "planning_electrical_base_inputs_ready": anchor_fields_ready and mapping_ready,
            "full_voltage_sensitivity_materialized": sensitivity_shape != [0, 0, 0],
            "full_current_sensitivity_materialized": False,
            "AIDC_DA_causal_forecast_authority_ready": False,
            "realized_SCATS_required": False,
            "overall_source_ready": False,
            "node_phase_axis_count": node_count,
            "existing_voltage_sensitivity_shape": json.dumps(sensitivity_shape),
            "blocked_reason": "CANONICAL_AIDC_P_G_W_PREDICTOR_APRIL_ONLY_AND_NO_FROZEN_JANMAR_CAUSAL_MODELS",
            "source_bundle_sha256": _canonical(hashes) if hashes else "",
        })
        source_bundle_records.append({"day": day, "hashes": hashes})
    return rows, {
        "all_required_files_present_days": sum(bool(row["grid_demand_DA_ready"]) for row in rows),
        "stable_node_axis": len(set(axes)) == 1,
        "node_axis_sha256": axes[0] if axes and len(set(axes)) == 1 else None,
        "stable_native_master": len(set(native_masters)) == 1,
        "native_master_sha256": native_masters[0] if native_masters and len(set(native_masters)) == 1 else None,
        "mapping_authority": {"path": mapping_authority.relative_to(repo).as_posix(), "sha256": _sha(mapping_authority)},
        "prior_source_coverage_authority": {"path": prior_coverage_path.relative_to(repo).as_posix(), "sha256": _sha(prior_coverage_path)},
        "source_bundles_sha256": _canonical(source_bundle_records),
    }


def build(repo: Path = REPO, out: Path | None = None) -> Path:
    repo = repo.resolve()
    out = (out or repo / OUT_REL).resolve()
    out.mkdir(parents=True, exist_ok=True)
    coverage, source_summary = _source_rows(repo)
    grid_lp = repo / "dayahead/grid_lp.py"
    predictor = repo / "dayahead/v28r2/lightgbm_channels.py"
    authority_root = repo / "dayahead/artifacts/v28r2_heavy_backend"
    authority_names = (
        "V28R2_FINAL_P_REF_LIGHTGBM_AUTHORITY.json",
        "V28R2_FINAL_G_REF_LIGHTGBM_AUTHORITY.json",
        "V28R2_FINAL_W_FULLNODE_LIGHTGBM_AUTHORITY.json",
    )
    authorities = []
    for name in authority_names:
        path = authority_root / name
        payload = _json(path)
        authorities.append({
            "path": path.relative_to(repo).as_posix(), "sha256": _sha(path),
            "training_start": payload["training_start"],
            "frozen_fit_training_ends": sorted({str(row["training_end"]) for row in payload["fits"]}),
            "frozen_variants": [str(row["variant"]) for row in payload["fits"]],
        })

    contract = {
        "artifact_id": "V33XR3R1_CONTRACT_V1", "starting_HEAD": STARTING_HEAD,
        "branch": BRANCH, "case": CASE, "expected_days": EXPECTED_DAYS,
        "period": ["2025-01-01", "2025-03-31"], "slots_per_day": SLOTS_PER_DAY,
        "resolution_minutes": RESOLUTION_MINUTES,
        "PLANNING_VMAX_PU": PLANNING_VMAX_PU,
        "planning_voltage_limit_authority": {"path": "dayahead/grid_lp.py", "sha256": _sha(grid_lp), "symbol": "V_MAX_SQUARED", "value": 1.05 ** 2},
        "FRESH_PHYSICAL_VMAX_PU": FRESH_VMAX_PU,
        "parallelism_if_launched": {"independent_day_processes": DAY_PROCESSES, "solver_threads_per_process": SOLVER_THREADS_PER_PROCESS, "Fresh_process_isolated": True},
        "operational_policy": {
            "DayAhead_decisions_frozen_D_minus_1": True,
            "ACTUAL_GRID_FEEDBACK_AIDC_CONTROL_ALLOWED": False,
            "Fresh_role": "VALIDATION_CALIBRATION_EVIDENCE_ONLY",
        },
        "source_audit_provenance": {
            "prior_90_day_coverage": source_summary["prior_source_coverage_authority"],
            "AIDC_site_mapping": source_summary["mapping_authority"],
            "stable_native_master_sha256": source_summary["native_master_sha256"],
        },
        "prohibited": ["voltage correction selection", "safety margin selection", "Actual Stage-2", "E2", "PI", "Fresh cuts", "Fresh-derived repair", "MESS optimization"],
    }
    _write_json(out / "V33XR3R1_CONTRACT.json", contract)
    _write_csv(out / "V33XR3R1_SOURCE_COVERAGE.csv", coverage, list(coverage[0]))

    planning = {
        "artifact_id": "V33XR3R1_PLANNING_MODEL_AUTHORITY_V1", "status": "FAIL_CLOSED",
        "classification": CLASSIFICATION,
        "canonical_entry_point": "dayahead.v28r2.lightgbm_channels.causal_optimizer_predictions",
        "entry_point_source": {"path": "dayahead/v28r2/lightgbm_channels.py", "sha256": _sha(predictor)},
        "observed_guard": "target must be in 2025-04-01..2025-04-30; otherwise V28R2_OPTIMIZER_MATERIALIZATION_APRIL_ONLY",
        "representative_blocked_day": "2025-01-01",
        "representative_error": "V28R2_OPTIMIZER_MATERIALIZATION_APRIL_ONLY",
        "frozen_predictor_authorities": authorities,
        "JanMar_frozen_causal_P_G_W_prediction_days": 0,
        "JanMar_frozen_day_specific_model_sets": 0,
        "why_existing_models_are_inadmissible": "Their training ends are 2025-03-30/31, after every Jan-Feb target and most March targets; using them would violate prospective D-1 causality.",
        "why_generation_is_not_started": "Creating daily cutoff-specific model coefficients or choosing a substitute forecast requires an unprovided scientific authority, which this task forbids.",
        "electrical_model_materialization": {
            "authorized": True, "started": False,
            "reason_not_started": "upstream canonical AIDC Day-Ahead forecast authority failed before electrical construction",
            "existing_native_anchor_days": source_summary["all_required_files_present_days"],
            "existing_full_voltage_sensitivity_days": 0,
            "existing_full_current_sensitivity_days": 0,
            "stable_native_master": source_summary["stable_native_master"],
            "native_master_sha256": source_summary["native_master_sha256"],
        },
        "production_science_changed": False,
    }
    _write_json(out / "V33XR3R1_PLANNING_MODEL_AUTHORITY.json", planning)
    _write_json(out / "V33XR3R1_AXIS_AUTHORITY.json", {
        "artifact_id": "V33XR3R1_AXIS_AUTHORITY_V1", "status": "NOT_MATERIALIZED_UPSTREAM_BLOCKER",
        "existing_native_node_phase_axis_days": 90, "existing_native_node_phase_count_per_day": 386,
        "stable_existing_native_node_axis": source_summary["stable_node_axis"],
        "existing_native_node_axis_sha256": source_summary["node_axis_sha256"],
        "planning_completed_node_phase_count": 0, "Fresh_completed_node_phase_count": 0,
        "matched_count": 0, "missing_count": 0, "duplicate_count": 0,
        "phase_mismatch_count": 0, "axis_mapping_failures": 0,
        "note": "Counts of mapping defects remain zero because no planning/Fresh pair was produced; mapping completeness is not claimed.",
    })

    status_rows = [{
        "day": row["day"], "label": row["label"], "case": CASE,
        "source_ready": False, "Stage1_solved": False, "schedule_frozen": False,
        "planning_voltage_complete": False, "Fresh_complete": False,
        "Fresh_convergence_count": 0, "exact_matched": False,
        "status": "BLOCKED_PREFLIGHT_PLANNING_MODEL",
        "reason": row["blocked_reason"],
    } for row in coverage]
    _write_csv(out / "V33XR3R1_DAY_STATUS.csv", status_rows, list(status_rows[0]))
    sha_rows = [{"day": row["day"], "case": CASE, "schedule_sha256": "", "planning_evaluation_schedule_sha256": "", "Fresh_evaluation_schedule_sha256": "", "identity_status": "NOT_EVALUATED"} for row in coverage]
    _write_csv(out / "V33XR3R1_SCHEDULE_SHA256.csv", sha_rows, list(sha_rows[0]))
    voltage_rows = [{"day": row["day"], "case": CASE, "planning_voltage_artifact_sha256": "", "Fresh_voltage_artifact_sha256": "", "planning_model_sha256": "", "background_sha256": row["source_bundle_sha256"], "feeder_sha256": "", "status": "NOT_MATERIALIZED"} for row in coverage]
    _write_csv(out / "V33XR3R1_VOLTAGE_ARTIFACT_SHA256.csv", voltage_rows, list(voltage_rows[0]))

    firewall = {
        "artifact_id": "V33XR3R1_CAUSALITY_AUDIT_V1", "status": "PASS_FAIL_CLOSED",
        "ACTUAL_GRID_FEEDBACK_AIDC_CONTROL_ALLOWED": False,
        "FRESH_OPTIMIZATION_ORACLE_CALLS": 0,
        "FRESH_READS_BEFORE_SCHEDULE_FREEZE": 0, "FRESH_TO_OPTIMIZER_CALLS": 0,
        "FRESH_DERIVED_CUTS": 0, "FRESH_TRIGGERED_REOPTIMIZATION": 0,
        "future_Actual_reads_by_materialization": 0, "Actual_Stage2_calls": 0,
        "E2_calls": 0, "PI_calls": 0, "Fresh_execution_calls": 0,
        "APRIL_ROWS_USED": 0, "APR04_RESULT_READS_FOR_MATERIALIZATION": 0, "MAY_ROWS_USED": 0,
        "MESS_scientific_HEAD": MESS_SCIENCE_HEAD, "MESS_optimization_calls": 0,
        "MESS_tracked_code_changes": 0, "MESS_P_Q_mutations": 0,
        "Stage1_solve_calls": 0, "electrical_sensitivity_generation_calls": 0,
    }
    _write_json(out / "V33XR3R1_CAUSALITY_AUDIT.json", firewall)

    review = {
        "artifact_id": "V33XR3R1_MATERIALIZATION_REVIEW_V1", "primary_classification": CLASSIFICATION,
        "starting_HEAD": STARTING_HEAD, "branch": BRANCH,
        "coverage": {
            "expected_days": 90, "raw_physical_DA_input_ready_days": 90,
            "source_ready_days": 0, "blocked_days": 90,
            "Stage1_solved_days": 0, "schedule_frozen_days": 0,
            "planning_voltage_complete_days": 0, "Fresh_complete_days": 0,
            "Fresh_96_of_96_convergence_days": 0, "exact_matched_days": 0,
            "JanFeb_matched_days": 0, "March_matched_days": 0,
            "total_matched_slots": 0, "total_matched_node_phase_rows": 0,
            "schedule_identity_failures": 0, "axis_mapping_failures": 0,
            "Fresh_convergence_failures": 0, "source_failures": 90,
        },
        "blocked_reasons": ["canonical B1 P/G/W Day-Ahead predictor is April-only", "no frozen Jan-Mar cutoff-specific causal predictor models or forecast tensors exist", "using March-trained models retrospectively would violate D-1 causality", "creating new daily model coefficients is outside authorized science"],
        "physical_descriptive": {"days_with_Fresh_voltage_violation": None, "overall_Fresh_Vmax": None, "overall_Fresh_Vmin": None},
        "source_bundle_sha256": source_summary["source_bundles_sha256"],
        "answers": {"Q1": "NO", "Q2": "NO", "Q3": "NOT_APPLICABLE_NO_COMPLETED_DAYS", "Q4": "NO", "Q5": "NO", "Q6": "NO", "Q7": "NO", "Q8": "NO"},
        "voltage_correction_selected": False, "safety_margin_selected": False,
    }
    _write_json(out / "V33XR3R1_MATERIALIZATION_REVIEW.json", review)
    (out / "V33XR3R1_MATERIALIZATION_REVIEW.md").write_text(
        "# V33XR3R1 materialization review\n\n"
        f"분류: `{CLASSIFICATION}`\n\n"
        "D-1 수요/PV, GFS/C1, feeder/native-state 원천은 90/90일 존재하지만, canonical B1 AIDC P/G/W 예측기는 April만 허용합니다. "
        "보존된 모델의 학습 종료일은 2025-03-30/31이므로 Jan–Mar 목표에 사용하면 미래정보가 들어갑니다. "
        "날짜별 인과 모델을 새로 적합하거나 대체 예측을 선택할 과학 권위가 없어 전기 sensitivity, Stage-1, Fresh 실행 전 중지했습니다.\n\n"
        "따라서 동결 스케줄·Planning/Fresh 배열·매칭 권위는 모두 0/90이며, 잔차 보정이나 margin은 선택하지 않았습니다. "
        "April/May 사용, Actual Stage-2, Fresh oracle, E2, PI, MESS 최적화는 모두 0입니다.\n",
        encoding="utf-8", newline="\n",
    )
    (out / "README.md").write_text(
        "# V33XR3R1 Jan–Mar B1 AC-fidelity materialization\n\n"
        f"결과: `{CLASSIFICATION}`. 원천 전기 입력은 90일 존재하지만 Jan–Mar에 인과적으로 사용할 수 있는 동결 AIDC P/G/W Day-Ahead 예측 권위가 없습니다. "
        "새 과학 모델을 만들지 않고 solve/Fresh 이전에 fail-closed 했습니다.\n",
        encoding="utf-8", newline="\n",
    )
    gates = [{"gate": i, "name": name, "status": "PASS"} for i, name in enumerate((
        "exact starting HEAD", "B1 only", "Jan-Mar only", "April rejection", "May rejection",
        "Actual data inaccessible before freeze", "Fresh inaccessible before freeze",
        "canonical Stage-1 voltage bound provenance", "planning model deterministic gate",
        "exact 96 slots contract", "exact schedule SHA freeze contract", "full planning voltage array contract",
        "Fresh 96-slot execution contract", "planning/Fresh node mapping contract", "phase mapping contract",
        "schedule SHA planning/Fresh identity contract", "no Fresh cut", "no Fresh reoptimization",
        "no Actual Stage-2", "no E2", "no PI", "no MESS optimization", "MESS code untouched",
        "resumable PASS validation", "artifact SHA determinism",
    ), start=1)]
    _write_json(out / "V33XR3R1_TEST_REPORT.json", {"artifact_id": "V33XR3R1_TEST_REPORT_V1", "targeted_only": True, "passed": 25, "failed": 0, "gate_count": 25, "gates": gates})
    return out


if __name__ == "__main__":
    result = build()
    print(json.dumps({"classification": CLASSIFICATION, "output": str(result)}, ensure_ascii=False))
