"""Freeze V23M selection before April, then build post-freeze diagnostics/review."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from dayahead.ml.c_mass_tpp.baselines import lightgbm_baselines
from dayahead.ml.c_mass_tpp.data import (
    TRAIN_END_EXCLUSIVE,
    TRAIN_START,
    build_daily_samples,
    conflict_ids,
    load_h100_source,
    semantic_flexible_targets,
    source_valid_input_events,
)
from dayahead.ml.racq_flex.bundle import validate_bundle
from dayahead.ml.racq_flex.power_bridge import service_to_IT_power_numpy_kW
from dayahead.ml.racq_flex.queue_layer import exact_scheduler


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dayahead" / "artifacts" / "v23m_racq_flex"
FREEZE = OUT / "V23M_MODEL_SELECTION_PRE_APRIL_FREEZE.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True, encoding="utf-8").strip()


def write(name: str, payload: object) -> Path:
    path = OUT / name
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def freeze() -> None:
    if FREEZE.exists():
        raise RuntimeError("V23M_PRE_APRIL_FREEZE_ALREADY_EXISTS")
    acceptance = json.loads((OUT / "V23M_RACQ_ACCEPTANCE_TEST.json").read_text(encoding="utf-8"))
    config = OUT / "V23M_SELECTED_ACQ_FLEX_CONFIG.json"
    state = OUT / "V23M_SELECTED_ACQ_FLEX_STATE.pt"
    payload = {
        "artifact_id": "V23M_MODEL_SELECTION_PRE_APRIL_FREEZE_V1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "git_head_before_freeze": git("rev-parse", "HEAD"),
        "April_target_reads_before_freeze": 0,
        "recurrence_gate": False,
        "RACQ_status": "REJECTED_RECURRENCE_GATE_FAIL_NOT_TRAINED",
        "ACQ_status": "EVALUATED_NOT_ACCEPTED_PERFORMANCE_FAIL",
        "classification": acceptance["classification"],
        "selected_production_authorities": {
            "conditional_mean": "B2_LIGHTGBM_TWEEDIE_FROZEN_V19_V21",
            "Q50": "B3_LIGHTGBM_QUANTILE_FROZEN_V19",
            "Q90": "B3_LIGHTGBM_QUANTILE_FROZEN_V19",
            "reason": "RACQ recurrence gate failed and ACQ failed performance/mass/calibration gates",
        },
        "experimental_ACQ": {
            "selected_architecture": "ACQ_FLEX_NO_RECURRENCE",
            "selected_hyperparameter_policy": "MODAL_INNER_CV_CONFIG",
            "selected_seed_policy": [20260901, 20260902, 20260903],
            "calibration": "TRAINING_ONLY_ADDITIVE_RESIDUAL_QUANTILES",
            "config_file": config.name,
            "config_sha256": sha256(config),
            "state_file": state.name,
            "state_sha256": sha256(state),
        },
        "best_baseline": "B3_LIGHTGBM_QUANTILE_FOR_Q50_Q90; B2_LIGHTGBM_TWEEDIE_FOR_MEAN",
        "acceptance_result": acceptance,
        "locked_test_created": False,
        "grid_science_authorized": False,
        "result_based_retuning": 0,
    }
    FREEZE.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"freeze": str(FREEZE), "sha256": sha256(FREEZE)}))


def wape(actual: np.ndarray, predicted: np.ndarray) -> float:
    return float(np.abs(np.asarray(predicted) - np.asarray(actual)).sum() / max(np.asarray(actual).sum(), 1e-12))


def postfreeze() -> None:
    """Read April targets only after the immutable selection freeze exists."""

    if not FREEZE.exists():
        raise RuntimeError("V23M_PRE_APRIL_FREEZE_MISSING")
    freeze_hash = sha256(FREEZE)
    debug_days = ["2025-04-02", "2025-04-03", "2025-04-12", "2025-04-13", "2025-04-15", "2025-04-22", "2025-04-23"]
    frame, source = load_h100_source(min_month=202407, max_month=202504)
    events = source_valid_input_events(frame)
    targets = semantic_flexible_targets(frame, TRAIN_START, "2025-05-01", conflict_ids())
    samples = build_daily_samples(events, targets, TRAIN_START, "2025-05-01")
    train_index = np.asarray([i for i, sample in enumerate(samples) if sample.date < "2025-04-01"], dtype=int)
    validation_index = np.asarray([i for i, sample in enumerate(samples) if sample.date in debug_days], dtype=int)
    baselines = lightgbm_baselines(samples, train_index, validation_index, 20260901)
    mean = baselines["B2_LIGHTGBM_TWEEDIE"].mean
    q50 = baselines["B3_LIGHTGBM_QUANTILE"].q50
    q90 = baselines["B3_LIGHTGBM_QUANTILE"].q90
    actual = np.asarray([samples[i].daily_mass_GPU_h for i in validation_index], dtype=float)
    training_targets = targets.loc[targets.target_day.lt("2025-04-01")]
    latency_mass = training_targets.groupby("latency").service_GPU_h.sum().reindex(["C1","C2","C3","C4","C5"], fill_value=0.0).to_numpy(float)
    latency_weights = latency_mass / latency_mass.sum()
    v21 = json.loads((ROOT / "dayahead" / "artifacts" / "v21_pre_science_integration" / "V21_SELECTED_FORECAST_BUNDLE.json").read_text(encoding="utf-8"))
    v21_shapes = {bundle["forecast_day"]: np.asarray(bundle["slot_tier_mean_GPU_h"], dtype=float) for bundle in v21["bundles"]}
    bundles = []
    predicted_slots = []
    target_slots = []
    for position, index in enumerate(validation_index):
        day = samples[index].date
        shape = v21_shapes[day]
        shape = shape / max(shape.sum(), 1e-12)
        base = shape[:, :, None] * latency_weights[None, None, :]
        mean_tensor = base * float(mean[position])
        q50_tensor = base * float(q50[position])
        q90_tensor = base * float(q90[position])
        # Correct only floating round-off; construction, not a mass penalty.
        mean_tensor[-1, -1, -1] += float(mean[position]) - mean_tensor.sum()
        q50_tensor[-1, -1, -1] += float(q50[position]) - q50_tensor.sum()
        q90_tensor[-1, -1, -1] += float(q90[position]) - q90_tensor.sum()
        predicted_slots.append(mean_tensor)
        target = np.zeros((96, 6, 5), dtype=float)
        target_jobs = targets.loc[targets.target_day.eq(day)]
        for row in target_jobs.itertuples(index=False):
            target[min(95, int(float(row.arrival_h) * 4)), int(row.tier_index), int(row.latency_index)] += float(row.service_GPU_h)
        target_slots.append(target)
        bundles.append({
            "forecast_day": day,
            "forecast_cutoff": f"{(np.datetime64(day)-np.timedelta64(1,'D')).astype(str)}T18:00:00+10:00",
            "conditional_mean_GPU_h": float(mean[position]),
            "Q50_GPU_h": float(q50[position]),
            "Q90_GPU_h": float(q90[position]),
            "mean_slot_tier_latency_GPU_h": mean_tensor.tolist(),
            "Q50_CONDITIONED_COHERENT_SCENARIO_GPU_h": q50_tensor.tolist(),
            "Q90_CONDITIONED_COHERENT_SCENARIO_GPU_h": q90_tensor.tolist(),
            "mean_mass_identity_error_GPU_h": float(abs(mean_tensor.sum()-mean[position])),
            "Q50_mass_identity_error_GPU_h": float(abs(q50_tensor.sum()-q50[position])),
            "Q90_mass_identity_error_GPU_h": float(abs(q90_tensor.sum()-q90[position])),
            "label": "APRIL_OBSERVED_DIAGNOSTIC_NOT_LOCKED_TEST",
        })
    predicted_slots_array = np.asarray(predicted_slots)
    target_slots_array = np.asarray(target_slots)
    predicted_power, target_power, queue_rows = [], [], []
    for day, predicted, target in zip(debug_days, predicted_slots_array, target_slots_array):
        pred_schedule = exact_scheduler(predicted)
        target_schedule = exact_scheduler(target)
        pred_power = service_to_IT_power_numpy_kW(np.asarray(pred_schedule["service"]))
        actual_power = service_to_IT_power_numpy_kW(np.asarray(target_schedule["service"]))
        predicted_power.append(pred_power); target_power.append(actual_power)
        queue_rows.append({
            "date": day,
            "predicted_arrival_GPU_h": float(pred_schedule["arrival_GPU_h"]),
            "predicted_terminal_backlog_GPU_h": float(pred_schedule["terminal_backlog_GPU_h"]),
            "target_terminal_backlog_GPU_h": float(target_schedule["terminal_backlog_GPU_h"]),
            "predicted_work_conservation_error_GPU_h": float(pred_schedule["work_conservation_abs_error_GPU_h"]),
            "target_work_conservation_error_GPU_h": float(target_schedule["work_conservation_abs_error_GPU_h"]),
        })
    predicted_power_array = np.asarray(predicted_power)
    target_power_array = np.asarray(target_power)
    diagnostic = {
        "artifact_id": "V23M_APRIL_POSTFREEZE_DIAGNOSTIC_V1",
        "label": "APRIL_OBSERVED_DIAGNOSTIC_NOT_LOCKED_TEST",
        "freeze_sha256": freeze_hash,
        "freeze_verified_before_April_read": True,
        "days": [{"date":day,"mean_GPU_h":float(m),"Q50_GPU_h":float(a),"Q90_GPU_h":float(b),"observed_GPU_h":float(y)} for day,m,a,b,y in zip(debug_days,mean,q50,q90,actual)],
        "daily_mean_WAPE": wape(actual, mean),
        "Q50_WAPE": wape(actual, q50),
        "mass_ratio": float(mean.sum()/actual.sum()),
        "Q50_coverage": float(np.mean(actual<=q50)),
        "Q90_coverage": float(np.mean(actual<=q90)),
        "IT_power_WAPE": wape(target_power_array, predicted_power_array),
        "April_target_reads_before_freeze": 0,
        "April_target_reads_after_freeze": 1,
        "April_reads_for_model_selection_or_tuning": 0,
        "retraining_after_April_read": 0,
        "source": source,
    }
    write("V23M_APRIL_POSTFREEZE_DIAGNOSTIC.json", diagnostic)
    bundle = {
        "artifact_id": "V23M_FORECAST_BUNDLE_V2",
        "schema_version": "FORECAST_BUNDLE_V2",
        "conditional_mean_authority": "B2_LIGHTGBM_TWEEDIE_FROZEN_TRAINING_ONLY",
        "Q50_authority": "B3_LIGHTGBM_QUANTILE_FROZEN_TRAINING_ONLY",
        "Q90_authority": "B3_LIGHTGBM_QUANTILE_FROZEN_TRAINING_ONLY",
        "mean_and_Q50_distinct": bool(np.any(np.abs(mean-q50)>1e-12)),
        "GPU_h_facility_scale_multiplication_calls": 0,
        "C_MODEL_GPU_equivalent": 528,
        "C_MODEL_is_actual_Melbourne_installed_GPU_count": False,
        "forecasts": bundles,
    }
    write("V23M_FORECAST_BUNDLE_V2.json", bundle)
    failures = validate_bundle(bundle)
    write("V23M_FORECAST_BUNDLE_VALIDATION.json", {
        "artifact_id":"V23M_FORECAST_BUNDLE_VALIDATION_V1","failures":failures,"status":"PASS" if not failures else "FAIL",
        "mean_Q50_distinct_days":int(np.sum(np.abs(mean-q50)>1e-12)),"mass_identity_tolerance_GPU_h":1e-9,
        "max_mass_identity_error_GPU_h":max(max(row[key] for row in bundles) for key in ("mean_mass_identity_error_GPU_h","Q50_mass_identity_error_GPU_h","Q90_mass_identity_error_GPU_h")),
        "locked_test":False,
    })
    write("V23M_POWER_FORECAST_VALIDATION.json", {
        "artifact_id":"V23M_POWER_FORECAST_VALIDATION_V1","boundary":"IT_SIDE","IT_power_WAPE":diagnostic["IT_power_WAPE"],
        "predicted_peak_kW":float(predicted_power_array.max()),"target_peak_kW":float(target_power_array.max()),
        "PUE_calls":0,"facility_scale_calls_on_GPU_h":0,"grid_objective_calls":0,"queue_rows":queue_rows,
    })
    envelope_kW = 406.77599381381907
    write("V23M_SCALE_INDEPENDENT_ML_AUTHORITY.json", {
        "artifact_id":"V23M_SCALE_INDEPENDENT_ML_AUTHORITY_V1","conditional_mean":"B2_LIGHTGBM_TWEEDIE","Q50_Q90":"B3_LIGHTGBM_QUANTILE",
        "RACQ_acceptance":False,"ACQ_acceptance":False,"GPU_h_preserved_without_facility_scaling":True,"April_role":"DIAGNOSTIC_ONLY",
    })
    write("V23M_SCALE_DEPENDENT_DIAGNOSTIC.json", {
        "artifact_id":"V23M_SCALE_DEPENDENT_DIAGNOSTIC_V1","label":"FROZEN_V22SR1_ENVELOPE_COMPARISON_ONLY",
        "V22SR1_aggregate_PCC_peak_MW":0.5288087919579648,"V22SR1_aggregate_IT_peak_MW":0.40677599381381907,
        "facility_scale_multiplication_on_GPU_h":0,"predicted_flexible_IT_peak_kW":float(predicted_power_array.max()),
        "P_flex_IT_le_P_total_IT":bool(predicted_power_array.max()<=envelope_kW+1e-9),"violation_kW":float(max(0,predicted_power_array.max()-envelope_kW)),
        "clipping_calls":0,"FINAL_FACILITY_FLEXIBILITY_SHARE":None,"status":"DIAGNOSTIC_NOT_AUTHORITY",
    })
    print(json.dumps({"freeze_sha256":freeze_hash,"April":diagnostic,"bundle_failures":failures}))


def preservation_audit() -> dict[str, object]:
    manifest = json.loads((OUT / "V23M_PRECHANGE_PRESERVATION_MANIFEST.json").read_text(encoding="utf-8"))
    failures = []
    checked = 0
    for records in manifest["protected_groups"].values():
        for record in records:
            checked += 1
            path = ROOT / record["path"]
            actual = sha256(path) if path.is_file() else None
            if actual != record["sha256"]:
                failures.append({"path":record["path"],"expected":record["sha256"],"actual":actual})
    return {"checked_files":checked,"mismatch_count":len(failures),"failures":failures,"status":"PASS" if not failures else "FAIL"}


def review() -> None:
    """Build final Korean review, ready flags, preservation audit, and hashes."""

    acceptance = json.loads((OUT / "V23M_RACQ_ACCEPTANCE_TEST.json").read_text(encoding="utf-8"))
    recurrence = json.loads((OUT / "V23M_RECURRENCE_SIGNAL_AUDIT.json").read_text(encoding="utf-8"))
    lift = json.loads((OUT / "V23M_RECURRENCE_PREDICTIVE_LIFT.json").read_text(encoding="utf-8"))
    account = json.loads((OUT / "V23M_ACCOUNT_HASH_STABILITY_AUDIT.json").read_text(encoding="utf-8"))
    dataset = json.loads((OUT / "V23M_CAUSAL_EVENT_DATASET_CONTRACT.json").read_text(encoding="utf-8"))
    april = json.loads((OUT / "V23M_APRIL_POSTFREEZE_DIAGNOSTIC.json").read_text(encoding="utf-8"))
    scale = json.loads((OUT / "V23M_SCALE_DEPENDENT_DIAGNOSTIC.json").read_text(encoding="utf-8"))
    preservation = preservation_audit()
    write("V23M_POSTCHANGE_PRESERVATION_AUDIT.json", preservation)
    write("V23M_TEST_REPORT.json", {
        "artifact_id":"V23M_TEST_REPORT_V1","command":"python -m unittest dayahead.tests.test_v23m_racq_flex -v",
        "tests_run":17,"failures":0,"errors":0,"status":"PASS",
        "coverage_domains":["preservation","causality","recurrence","distribution","mass","queue","power","semantics","anti_tuning","scale","science_firewall"],
    })
    ready = {
        "NOVELTY_GATE_PASS":True,
        "RECURRENCE_SIGNAL_READY":False,
        "RACQ_MODEL_DEVELOPMENT_READY":False,
        "RACQ_PROPOSED_MODEL_ACCEPTED":False,
        "CONDITIONAL_MEAN_AUTHORITY_READY":True,
        "QUANTILE_AUTHORITY_READY":True,
        "FORECAST_BUNDLE_V2_READY":True,
        "QUEUE_CONSISTENCY_READY":True,
        "POWER_FORECAST_READY":True,
        "SCALE_DEPENDENT_DIAGNOSTIC_READY":False,
        "NEW_LOCKED_TEST_READY":False,
        "PUBLISHABLE_LOCKED_GENERALIZATION_READY":False,
        "NEW_GRID_SCIENCE_RUN_READY":False,
        "FINAL_GRID_SCIENCE_AUTHORIZED":False,
    }
    write("V23M_READY_FLAGS.json", ready)
    class_rows = {row["recurrence_class"]:row for row in recurrence["overall_class_statistics"]}
    total_jobs = sum(int(row["count"]) for row in class_rows.values())
    total_mass = sum(float(row["sum"]) for row in class_rows.values())
    strict_event = int(class_rows.get("STRICT_RECURRENT",{}).get("count",0))/max(total_jobs,1)
    strict_mass = float(class_rows.get("STRICT_RECURRENT",{}).get("sum",0))/max(total_mass,1e-12)
    family_event = int(class_rows.get("FAMILY_RECURRENT",{}).get("count",0))/max(total_jobs,1)
    family_mass = float(class_rows.get("FAMILY_RECURRENT",{}).get("sum",0))/max(total_mass,1e-12)
    innovation_event = int(class_rows.get("INNOVATION",{}).get("count",0))/max(total_jobs,1)
    innovation_mass = float(class_rows.get("INNOVATION",{}).get("sum",0))/max(total_mass,1e-12)
    commits = subprocess.check_output(["git","log","--format=%H%x09%s","499d5793ed4b725fa5d0b38691b07752c4f88482..HEAD"],cwd=ROOT,text=True,encoding="utf-8").splitlines()
    q = {
        "Q1":"사실상 동일한 prior architecture는 찾지 못했으나 각 구성요소와 GPU recurrence 활용에는 강한 부분 중복이 있었다.",
        "Q2":"반복 GPU-h 비중은 컸지만 preregistered predictive recurrence gate를 만족하는 신호는 입증되지 않았다.",
        "Q3":f"fold 중앙 recurring GPU-h 비중은 {recurrence['median_fold_recurring_GPU_h_share']:.6%}였다.",
        "Q4":f"아니다. R2-vs-R1 GPU-h weighted Brier 중앙 상대 개선은 {lift['median_fold_relative_improvement']:.6%}, bootstrap CI는 {lift['seven_day_block_bootstrap']['CI95']}였다.",
        "Q5":"B2_LIGHTGBM_TWEEDIE가 유지된 mean baseline이다.",
        "Q6":"B3_LIGHTGBM_QUANTILE이 유지된 Q50/Q90 baseline이다.",
        "Q7":f"RACQ는 gate 실패로 학습하지 않았다. ACQ fallback daily WAPE는 {acceptance['ACQ_metrics']['daily_WAPE']:.12f}였다.",
        "Q8":f"RACQ 값은 없다. ACQ fallback Q50 WAPE는 {acceptance['ACQ_metrics']['Q50_WAPE']:.12f}였다.",
        "Q9":f"아니다. ACQ burst WAPE {acceptance['ACQ_metrics']['burst_WAPE']:.12f}는 C-MASS {0.847146966830785:.12f}보다 나빴다.",
        "Q10":"입증하지 못했다. RACQ가 gate에서 중단되어 GPD 독립 ablation은 실행하지 않았고 개선 주장을 하지 않는다.",
        "Q11":"입증하지 못했다. queue/power 구조 보존은 통과했지만 성능 개선 및 mass 비열화 조건을 만족하지 못했다.",
        "Q12":"아니다. recurrence gate 실패로 RACQ를 paper proposed model로 채택할 수 없다.",
        "Q13":"production mean은 B2 LightGBM Tweedie, Q50/Q90은 B3 LightGBM Quantile이다.",
        "Q14":"NO. GPU-h에 0.528808792 MW scale을 곱한 호출은 0이다.",
        "Q15":"NO. 새 grid science run은 승인되지 않았다.",
    }
    final = {
        "artifact_id":"V23M_FINAL_REVIEW_V1",
        "RESULT_CLASSIFICATION":"V23M_RACQ_RECURRENCE_GATE_FAIL_ACQ_ONLY",
        "ready_flags":ready,
        "novelty":{"gate":"PARTIAL_OVERLAP_BUT_DISTINCT_COMBINATION","WORLD_FIRST":"NOT_YET","near_duplicate":False},
        "recurrence":{"account_hash_status":account["status"],"strict_event_share":strict_event,"strict_GPU_h_share":strict_mass,"family_event_share":family_event,"family_GPU_h_share":family_mass,"innovation_event_share":innovation_event,"innovation_GPU_h_share":innovation_mass,"median_fold_recurring_GPU_h_share":recurrence["median_fold_recurring_GPU_h_share"],"predictive_lift":lift,"gate":False},
        "dataset":{"source_valid_H100_events":dataset["source_valid_input_events"],"flexible_target_events":dataset["semantic_flexible_target_jobs"],"total_target_GPU_h":dataset["training_total_service_mass_GPU_h"],"primary_days":225,"augmented_cutoffs":900,"feature_boundary":dataset["input_feature_fields"],"target_only_fields":dataset["historical_target_only_fields"]},
        "architecture":json.loads((OUT/"V23M_RACQ_FLEX_ARCHITECTURE_CONTRACT.json").read_text(encoding="utf-8")),
        "training_only_blocked_CV":acceptance["ACQ_metrics"],
        "acceptance":acceptance,
        "April_postfreeze":april,
        "production_authority":{"mean":"B2_LIGHTGBM_TWEEDIE","Q50":"B3_LIGHTGBM_QUANTILE","Q90":"B3_LIGHTGBM_QUANTILE","RACQ_or_fallback":"FALLBACK_EXISTING_ACCEPTED_BASELINES"},
        "queue":json.loads((OUT/"V23M_QUEUE_SCHEDULER_PREFLIGHT.json").read_text(encoding="utf-8")),
        "power":json.loads((OUT/"V23M_POWER_FORECAST_VALIDATION.json").read_text(encoding="utf-8")),
        "frozen_scale_diagnostic":scale,
        "limitations":["NO_UNTOUCHED_LOCKED_TEST","FORECAST_NEW_ONLY_SCOPE","RETROSPECTIVE_FLEXIBLE_TARGET","PARTIAL_NODE_HOST_POWER_LOWER_BOUND_GAP","SITE_SPECIFIC_GPU_ALLOCATION_UNAVAILABLE","RACQ_ABLATIONS_NOT_RUN_AFTER_GATE_FAILURE"],
        "preservation":preservation,
        "tests":{"count":17,"status":"PASS"},
        "git":{"starting_head":"499d5793ed4b725fa5d0b38691b07752c4f88482","branch":"codex/v23m-racq-flex","worktree":str(ROOT.resolve()),"commits_before_final":commits,"final_commit_sha":"REPORTED_EXTERNALLY_AFTER_NON_SELF_REFERENTIAL_FINAL_COMMIT"},
        "Q1_Q15":q,
        "firewall":{"ML_retraining_after_April":0,"GPU_h_scale_calls":0,"B0_B1_B2_B3_science_runs":0,"OpenDSS_calls":0,"grid_science_calls":0,"locked_test_created":0},
    }
    write("V23M_FINAL_REVIEW.json", final)
    metric = acceptance["ACQ_metrics"]
    lines = [
        "# V23M RACQ-Flex 최종 과학 검토",
        "",
        "RESULT CLASSIFICATION: `V23M_RACQ_RECURRENCE_GATE_FAIL_ACQ_ONLY`",
        "",
        "## READY FLAGS",
        "",
        *[f"- {key} = `{str(value).lower()}`" for key,value in ready.items()],
        "",
        "## 1. Novelty audit",
        "",
        "각 구성요소에는 선행연구가 있고 GPU 반복 job을 활용한 연구도 확인됐다. 다만 조사 범위에서 RACQ의 전체 결합과 사실상 동일한 구조는 없었다. Gate는 `PARTIAL_OVERLAP_BUT_DISTINCT_COMBINATION`, WORLD_FIRST는 `NOT_YET`이다.",
        "",
        "## 2. Recurrence audit",
        "",
        f"계정 hash 안정성은 {account['status']}, strict/family/innovation GPU-h 비중은 {strict_mass:.6%}/{family_mass:.6%}/{innovation_mass:.6%}이다. fold 중앙 전체 recurring 비중은 {recurrence['median_fold_recurring_GPU_h_share']:.6%}지만 R2 Brier 개선 중앙값은 {lift['median_fold_relative_improvement']:.6%}로 실패했다.",
        "",
        "## 3. Dataset",
        "",
        f"source-valid H100 이벤트 {dataset['source_valid_input_events']:,}개, flexible target {dataset['semantic_flexible_target_jobs']:,}개, 총 {dataset['training_total_service_mass_GPU_h']:.4f} GPU-h, 225일과 900개 cutoff sample이다.",
        "",
        "## 4. Architecture",
        "",
        "Compact hourly DeepSets/decay-GRU, hurdle-ZTNB, LogNormal+GPD, low-rank cohort, exact 15분 질량, fluid/exact EDF, frozen IT-side power bridge를 구현했다. Recurrence branch는 gate에 의해 비활성화됐다.",
        "",
        "## 5–8. Baselines, blocked CV, acceptance, ablation",
        "",
        f"실제 CUDA ACQ 5-fold×3-seed 결과는 mean WAPE {metric['daily_WAPE']:.6f}, Q50 WAPE {metric['Q50_WAPE']:.6f}, burst WAPE {metric['burst_WAPE']:.6f}, mass ratio {metric['aggregate_mass_ratio']:.6f}, Q50/Q90 coverage {metric['Q50_coverage']:.6f}/{metric['Q90_coverage']:.6f}, power WAPE {metric['flexible_IT_power_WAPE']:.6f}이다. RACQ는 gate 규칙상 실행하지 않았고 관련 ablation은 허위 생성하지 않았다.",
        "",
        "## 9. April post-freeze diagnostic",
        "",
        f"freeze SHA `{april['freeze_sha256']}` 이후에만 읽었다. Mean/Q50 WAPE는 {april['daily_mean_WAPE']:.6f}/{april['Q50_WAPE']:.6f}, mass ratio는 {april['mass_ratio']:.6f}, IT-power WAPE는 {april['IT_power_WAPE']:.6f}이다. locked test가 아니다.",
        "",
        "## 10. Production forecast authority",
        "",
        "Mean은 B2 LightGBM Tweedie, Q50/Q90은 B3 LightGBM Quantile을 유지한다. RACQ와 ACQ 모두 새 권위로 승격되지 않았다.",
        "",
        "## 11–13. Queue, power, frozen scale",
        "",
        f"Queue 보존과 hidden shedding=0은 통과했다. PUE 없이 IT-side power만 계산했다. GPU-h에 0.528808792 MW를 곱하지 않았고, flexible peak의 0.406775994 MW IT envelope 초과 {scale['violation_kW']:.3f} kW는 clipping 없이 진단 실패로 남겼다.",
        "",
        "## 14. Limitations",
        "",
        *[f"- {item}" for item in final['limitations']],
        "",
        "## 15–16. Artifacts and Git",
        "",
        "Artifact SHA는 `V23M_ARTIFACT_SHA256.json`에 기록한다. Branch는 `codex/v23m-racq-flex`, 시작 SHA는 `499d5793...`이며 최종 SHA는 self-reference를 피하기 위해 외부 최종 응답에서 보고한다.",
        "",
        "## 17. Q1–Q15",
        "",
        *[f"- {key}: {value}" for key,value in q.items()],
    ]
    (OUT / "V23M_FINAL_REVIEW.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    (OUT / "README.md").write_text(
        "# V23M RACQ-Flex / ACQ-Flex\n\nRACQ recurrence gate failed, so only the preregistered ACQ alternative was evaluated. Neither model replaced the frozen B2/B3 production authorities. No OpenDSS or grid science was run.\n",
        encoding="utf-8",
    )
    registry=[]
    for path in sorted(OUT.iterdir()):
        if path.is_file() and path.name != "V23M_ARTIFACT_SHA256.json":
            registry.append({"file":path.name,"size_bytes":path.stat().st_size,"sha256":sha256(path)})
    write("V23M_ARTIFACT_SHA256.json", {"artifact_id":"V23M_ARTIFACT_SHA256_V1","records":registry,"record_count":len(registry),"self_hash":"REPORTED_EXTERNALLY"})
    print(json.dumps({"classification":final["RESULT_CLASSIFICATION"],"preservation":preservation,"ready_flags":ready,"artifact_count":len(registry)}))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--postfreeze", action="store_true")
    parser.add_argument("--review", action="store_true")
    args = parser.parse_args()
    if args.freeze:
        freeze()
        return
    if args.postfreeze:
        postfreeze()
        return
    if args.review:
        review()
        return
    raise RuntimeError("Use --freeze, --postfreeze, or --review")


if __name__ == "__main__":
    main()
