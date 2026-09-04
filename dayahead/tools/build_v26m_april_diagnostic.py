"""Open the seven April days only after verified pre-April freeze."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from dayahead.ml.c_mass_tpp.data import conflict_ids, load_h100_source, semantic_flexible_targets, source_valid_input_events
from dayahead.ml.safe_flex.bundle import validate_bundle
from dayahead.ml.safe_flex.capacity_timeline import read_observed_capacity_timeline
from dayahead.ml.safe_flex.conformal_set import calibrate_inner_set
from dayahead.ml.safe_flex.envelope import inner_envelope_from_mass, reference_arrival_tensor
from dayahead.ml.safe_flex.metrics import envelope_metrics
from dayahead.ml.safe_flex.observable_share import observable_share_by_day
from dayahead.ml.safe_flex.scenario import empirical_shape
from dayahead.ml.safe_flex.service_set import cumulative_bounds
from dayahead.ml.safe_flex.state_reconstruction import reconstruct_at_cutoff


REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "dayahead/artifacts/v26m_safe_flex"
DATES = ["2025-04-02", "2025-04-03", "2025-04-12", "2025-04-13", "2025-04-15", "2025-04-22", "2025-04-23"]


def main() -> None:
    freeze = OUT / "V26M_MODEL_SELECTION_PRE_APRIL_FREEZE.json"
    expected = (OUT / "V26M_MODEL_SELECTION_PRE_APRIL_FREEZE.sha256").read_text().strip()
    import hashlib
    if hashlib.sha256(freeze.read_bytes()).hexdigest() != expected:
        raise RuntimeError("V26M_PRE_APRIL_FREEZE_SHA_MISMATCH")
    raw, provenance = load_h100_source(min_month=202407, max_month=202504)
    events = source_valid_input_events(raw)
    jobs = semantic_flexible_targets(raw, "2024-07-01", "2025-05-01", conflict_ids()).reset_index(drop=True)
    training_shares = pd.read_csv(OUT / "V26M_OBSERVABLE_STATE_SHARE_BY_DAY.csv")
    state_audit = pd.read_csv(OUT / "V26M_STATE_RECONSTRUCTION_AUDIT.csv")
    ratio = training_shares.H_K_pending_GPU_h / state_audit.visible_pending_jobs.replace(0, np.nan)
    ratio = ratio.replace([np.inf, -np.inf], np.nan).dropna()
    ratio_q = ratio.quantile([0.1, 0.5, 0.9]).to_numpy(float)
    gap_q = training_shares.H_G_GPU_h.quantile([0.1, 0.5, 0.9]).to_numpy(float)
    training_tensors = np.stack([reference_arrival_tensor(jobs, day) for day in pd.date_range("2024-08-19", "2025-03-31")])
    shape = empirical_shape(training_tensors)
    cal_contract = json.loads((OUT / "V26M_SAFE_SET_CALIBRATION_CONTRACT.json").read_text(encoding="utf-8"))
    conformal_q = float(cal_contract["model_summaries"]["FULL_SAFE_FLEX_RAW"]["trajectory_score_Q90"])
    cal_dates = cal_contract["chronological_calibration_days"]
    cal_tensors = np.stack([reference_arrival_tensor(jobs, day) for day in cal_dates])
    cal_scale_value = max(float(tensor.sum()) for tensor in cal_tensors)
    cal_scale = np.full((96, 6, 5), max(cal_scale_value, 1.0))
    v25_april = json.loads((REPO / "dayahead/artifacts/v25m_beacon_flex/V25M_APRIL_POSTFREEZE_DIAGNOSTIC.json").read_text(encoding="utf-8"))
    v25_rows = {row["date"]: row for row in v25_april["dates"]}
    april_nodes = set()
    april_raw = raw.loc[raw.source_month.eq(202504)]
    for nodes in april_raw.node_tuple:
        april_nodes.update(nodes)
    capacity_gpu = 4 * len(april_nodes)
    records, bundle_records, validations = [], [], []
    for date in DATES:
        state = reconstruct_at_cutoff(events, date)
        share = observable_share_by_day(jobs, date, date).iloc[0]
        reference = reference_arrival_tensor(jobs, date); ref_l, ref_u = cumulative_bounds(reference)
        kq = ratio_q * state.visible_pending_jobs
        nrow = v25_rows[date]
        nq50 = float(nrow["base_Q50_GPU_h"]); nq90 = float(nrow["base_Q90_GPU_h"])
        nq10 = max(0.0, 2 * nq50 - nq90)
        total_q10 = float(kq[0] + gap_q[0] + nq10); total_q50 = float(kq[1] + gap_q[1] + nq50); total_q90 = float(kq[2] + gap_q[2] + nq90)
        raw_l, raw_u = inner_envelope_from_mass(shape, total_q10, total_q90)
        safe_l, safe_u = calibrate_inner_set(raw_l, raw_u, conformal_q, cal_scale)
        metric = envelope_metrics(safe_l, safe_u, ref_l, ref_u)
        record = {
            "date": date, "visible_RUNNING_jobs": state.visible_running_jobs, "visible_PENDING_jobs": state.visible_pending_jobs,
            "known_schedulable_mass_Q10_Q50_Q90_GPU_h": kq.tolist(), "gap_innovation_Q10_Q50_Q90_GPU_h": gap_q.tolist(),
            "day_innovation_Q10_Q50_Q90_GPU_h": [nq10, nq50, nq90],
            "reference_schedulable_GPU_h": float(reference.sum()),
            "reference_schedulable_share": float((share.H_K_pending_GPU_h + share.H_G_GPU_h + share.H_N_GPU_h) / share.H_total_GPU_h) if share.H_total_GPU_h > 0 else None,
            "simultaneous_set_covered": metric["simultaneous_inner_coverage"], "safe_set_nonempty": metric["nonempty_set"],
            "load_reduction_safe_capacity_GPU_h": 0.0 if not metric["nonempty_set"] else float(np.maximum(safe_u-safe_l,0).sum()),
            "load_increase_safe_capacity_GPU_h": 0.0 if not metric["nonempty_set"] else float(np.maximum(safe_u-safe_l,0).sum()),
            "reserve_shortfall_GPU_h": 0.0, "fit_calls_after_open": 0, "calibration_calls_after_open": 0, "selection_calls_after_open": 0,
        }
        records.append(record)
        bundle = {
            "forecast_day": date, "cutoff": state.cutoff_AEST, "timezone": "FIXED_AEST_UTC_PLUS_10",
            "capacity_normalization_authority": "APRIL_RAW_OBSERVED_USE_LOWER_BOUND_NOT_INSTALLED_CAPACITY",
            "state_reconstruction_label": "EVENT_CENSORED_RECONSTRUCTED_STATE",
            "visible_running_job_count": state.visible_running_jobs, "visible_pending_job_count": state.visible_pending_jobs,
            "known_schedulable_mass_mean": float(kq[1]), "known_schedulable_mass_Q10": float(kq[0]), "known_schedulable_mass_Q50": float(kq[1]), "known_schedulable_mass_Q90": float(kq[2]),
            "gap_innovation_mean": float(gap_q[1]), "gap_innovation_Q50": float(gap_q[1]), "gap_innovation_Q90": float(gap_q[2]),
            "day_innovation_mean": float(nrow["base_mean_GPU_h"]), "day_innovation_Q50": nq50, "day_innovation_Q90": nq90,
            "cumulative_L_safe": safe_l.tolist(), "cumulative_U_safe": safe_u.tolist(), "capacity_safe": [capacity_gpu * 0.25] * 96,
            "P_IT_reference": [None] * 96, "P_IT_min_safe": [None] * 96, "P_IT_max_safe": [None] * 96,
            "F_load_reduction_Q10": [0.0] * 96, "F_load_reduction_Q50": [0.0] * 96, "F_load_reduction_Q90": [0.0] * 96,
            "F_load_increase_Q10": [0.0] * 96, "F_load_increase_Q50": [0.0] * 96, "F_load_increase_Q90": [0.0] * 96,
            "simultaneous_coverage_target": 0.90, "conformal_calibration_certificate": "FAIL_EMPTY_SET",
            "service_conservation_certificate": "PASS_DESCRIPTOR_MASS", "state_causality_certificate": "PASS",
            "capacity_normalization_certificate": "OBSERVED_USE_LOWER_BOUND_ONLY", "model_hashes": {},
            "data_hash": provenance["source_sha256"], "code_hash": json.loads(freeze.read_text())["V26M_code_SHA256"],
        }
        bundle_records.append(bundle); validations.append({"date": date, **validate_bundle(bundle)})
    diagnostic = {
        "artifact_id": "V26M_APRIL_POSTFREEZE_DIAGNOSTIC_V1", "label": "APRIL_OBSERVED_POSTFREEZE_DIAGNOSTIC_NOT_LOCKED_TEST",
        "freeze_SHA256_verified_before_open": True, "dates": records,
        "April_archive_members_opened": provenance["members_opened"], "April_observed_distinct_H100_nodes": len(april_nodes),
        "April_observed_capacity_GPU_lower_bound": capacity_gpu, "fit_calls_after_open": 0, "calibration_calls_after_open": 0,
        "selection_calls_after_open": 0, "architecture_changes_after_open": 0,
    }
    (OUT / "V26M_APRIL_POSTFREEZE_DIAGNOSTIC.json").write_text(json.dumps(diagnostic, indent=2) + "\n", encoding="utf-8")
    bundle_artifact = {"schema": "SAFE_FLEX_BUNDLE_V5", "authority": "DIAGNOSTIC_ONLY_REJECTED_MODEL", "bundle_status": "NOT_ISSUED_FOR_PRODUCTION", "records": bundle_records}
    (OUT / "V26M_SAFE_FORECAST_BUNDLE_V5.json").write_text(json.dumps(bundle_artifact) + "\n", encoding="utf-8")
    (OUT / "V26M_BUNDLE_VALIDATION.json").write_text(json.dumps({"artifact_id": "V26M_BUNDLE_VALIDATION_V1", "records": validations, "all_shape_PASS": all(v["shape_PASS"] for v in validations), "all_nonempty_PASS": all(v["nonempty_PASS"] for v in validations), "SAFE_FLEX_BUNDLE_V5_READY": False}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"dates": len(records), "fit_after_open": 0, "all_nonempty": all(v["nonempty_PASS"] for v in validations), "April_capacity_GPU_lower_bound": capacity_gpu}))


if __name__ == "__main__":
    main()
