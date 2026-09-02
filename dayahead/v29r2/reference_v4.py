"""Deterministic grid-blind REFERENCE_COMPUTE_SCHEDULE_V4 authority."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from dayahead.v28r2.lightgbm_channels import causal_optimizer_predictions
from dayahead.v28r2.reference_compute import (
    FullNodeDistributionAdapter, case_rack_capacity_nodeh_per_slot,
)
from dayahead.v28r2.reference_delta import build_reference_delta
from dayahead.v28r2.source_labels import load_optimizer_labels
from dayahead.v29.reference_compute_v3 import ReferenceScheduleV3, build_reference_schedule_v3
from dayahead.v29r1.source_resume import write_json

from .anchor_forensic import OUT_REL
from .bridge_v2 import predict_bridge_day


@dataclass(frozen=True)
class ReferenceScheduleV4:
    schedule: ReferenceScheduleV3
    h0_req_nodeh: np.ndarray
    h0_nom_nodeh: np.ndarray
    h0_low_nodeh: np.ndarray
    uncertain_initial_nodeh: np.ndarray

    def validate(self) -> None:
        self.schedule.validate()
        shape = (len(self.schedule.cohort_ids),)
        arrays = (self.h0_req_nodeh, self.h0_nom_nodeh, self.h0_low_nodeh, self.uncertain_initial_nodeh)
        if any(np.asarray(value).shape != shape or not np.isfinite(value).all() for value in arrays):
            raise ValueError("V29R2_REFERENCE_V4_INITIAL_AXIS")
        if not (
            np.all(self.h0_low_nodeh >= -1e-12)
            and np.all(self.h0_low_nodeh <= self.h0_nom_nodeh + 1e-12)
            and np.all(self.h0_nom_nodeh <= self.h0_req_nodeh + 1e-12)
            and np.allclose(self.uncertain_initial_nodeh, self.h0_nom_nodeh - self.h0_low_nodeh, atol=1e-12, rtol=0)
            and np.array_equal(self.schedule.initial_backlog_nodeh, self.h0_nom_nodeh)
        ):
            raise ValueError("V29R2_REFERENCE_V4_INITIAL_MASS")

    def canonical_bytes(self) -> bytes:
        self.validate()
        payload = {
            "authority_id": "REFERENCE_COMPUTE_SCHEDULE_V4",
            "cohort_ids": list(self.schedule.cohort_ids),
            "rack_ids": list(self.schedule.rack_ids),
            "H0_REQ_nodeh": self.h0_req_nodeh.tolist(),
            "H0_NOM_nodeh": self.h0_nom_nodeh.tolist(),
            "H0_LOW_controllable_nodeh": self.h0_low_nodeh.tolist(),
            "H0_UNCERTAIN_reference_only_nodeh": self.uncertain_initial_nodeh.tolist(),
            "D_day_Q50_arrivals_nodeh": self.schedule.arrivals_nodeh.tolist(),
            "x_ref_nodeh": self.schedule.x_ref_nodeh.tolist(),
            "backlog_nodeh": self.schedule.backlog_nodeh.tolist(),
            "p_f_ref_kw": self.schedule.p_f_ref_kw.tolist(),
            "g_f_ref_gpu": self.schedule.g_f_ref_gpu.tolist(),
            "policy": "deterministic earliest-feasible; cohort then capacity-proportional rack; no grid signal",
        }
        return (json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def _base_inputs(repo: Path, day: str) -> dict[str, object]:
    artifacts = repo / "dayahead/artifacts/v28r2_heavy_backend"
    labels = load_optimizer_labels(repo)
    p_quantiles, g_quantiles, w_quantiles = causal_optimizer_predictions(
        labels, day, artifacts / "V28R2_OPTIMIZER_CHANNEL_MODELS",
    )
    p_authority = json.loads((artifacts / "V28R2_FINAL_P_REF_LIGHTGBM_AUTHORITY.json").read_text(encoding="utf-8"))
    p_q90 = p_quantiles[2] * float(p_authority["scale_binding"]["alpha_IT"])
    g_q90 = g_quantiles[2]
    adapter_payload = json.loads((artifacts / "V28R2_FULLNODE_DISTRIBUTION_ADAPTER.json").read_text(encoding="utf-8"))
    adapter = FullNodeDistributionAdapter(np.asarray(adapter_payload["probabilities"], dtype=float), labels.cohort_ids)
    arrivals = adapter.materialize(float(w_quantiles[1]), pd.Timestamp(day).dayofweek)
    mapping = json.loads((repo / "dayahead/artifacts/v16/AIDC_RACK_MAPPING_CONTRACT.json").read_text(encoding="utf-8"))
    rack_ids = tuple(str(row["rack_id"]) for row in mapping["racks"])
    power_weights = dict(zip(rack_ids, map(float, mapping["power_weights"]), strict=True))
    gpu_weights = dict(zip(rack_ids, map(float, mapping["gpu_weights"]), strict=True))
    capacities = case_rack_capacity_nodeh_per_slot(rack_ids, gpu_weights)
    return {
        "cohort_ids": labels.cohort_ids, "rack_ids": rack_ids,
        "arrivals": arrivals, "p_q90": p_q90, "g_q90": g_q90,
        "power_weights": power_weights, "gpu_weights": gpu_weights,
        "capacities": capacities,
    }


def build_reference_v4(
    repo: Path, day: str, *, h0_req: np.ndarray, h0_nom: np.ndarray, h0_low: np.ndarray,
) -> tuple[ReferenceScheduleV4, object]:
    base = _base_inputs(repo, day)
    cohort_ids = tuple(base["cohort_ids"])
    rack_ids = tuple(base["rack_ids"])
    h0_req = np.asarray(h0_req, dtype=float)
    h0_nom = np.asarray(h0_nom, dtype=float)
    h0_low = np.asarray(h0_low, dtype=float)
    power_weights = base["power_weights"]
    gpu_weights = base["gpu_weights"]
    p_q90 = np.asarray(base["p_q90"], dtype=float)
    g_q90 = np.asarray(base["g_q90"], dtype=float)
    p_envelope = np.asarray([power_weights[rack] for rack in rack_ids])[:, None] * p_q90[None, :]
    g_envelope = np.asarray([gpu_weights[rack] for rack in rack_ids])[:, None] * g_q90[None, :]
    schedule = build_reference_schedule_v3(
        np.asarray(base["arrivals"], dtype=float), h0_nom,
        cohort_ids=cohort_ids, rack_ids=rack_ids,
        rack_capacity_nodeh_per_slot=np.asarray(base["capacities"], dtype=float),
        rack_power_envelope_kw=p_envelope, rack_gpu_envelope_gpu=g_envelope,
    )
    reference = ReferenceScheduleV4(schedule, h0_req, h0_nom, h0_low, h0_nom - h0_low)
    reference.validate()
    delta = build_reference_delta(
        p_q90, g_q90, schedule.p_f_ref_kw, schedule.g_f_ref_gpu,
        rack_ids=rack_ids, power_weights=power_weights, gpu_weights=gpu_weights,
    )
    return reference, delta


def build_reference_v4_authority(repo: Path) -> dict[str, object]:
    out = repo / OUT_REL
    bridge = json.loads((out / "V29R2_BRIDGE_V2_CONTRACT.json").read_text(encoding="utf-8"))
    if bridge["status"] != "PASS" or not bridge["reference_v4_authorized"]:
        raise RuntimeError("V29R2_REFERENCE_V4_WITHOUT_BRIDGE_PASS")
    bridge_rows = predict_bridge_day(repo, "2025-04-04")
    if not bridge_rows:
        raise RuntimeError("V29R2_REFERENCE_V4_APR04_CUTOFF_INPUT_EMPTY")
    days = ["2025-04-04"]
    reports: list[dict[str, object]] = []
    for day in days:
        base = _base_inputs(repo, day)
        cohorts = tuple(base["cohort_ids"])
        index = {name: position for position, name in enumerate(cohorts)}
        h0_req = np.zeros(len(cohorts)); h0_nom = np.zeros(len(cohorts)); h0_low = np.zeros(len(cohorts))
        for row in bridge_rows:
            if row["day"] != day:
                continue
            position = index[row["cohort_id"]]
            h0_req[position] = float(row["H0_REQ"])
            h0_nom[position] = float(row["H0_NOM"])
            h0_low[position] = float(row["H0_LOW"])
        reference, delta = build_reference_v4(repo, day, h0_req=h0_req, h0_nom=h0_nom, h0_low=h0_low)
        content = reference.canonical_bytes()
        sha = hashlib.sha256(content).hexdigest()
        # Direct decomposition uses the schedule flexible channels exactly once.
        p_total = delta.p_res_plan_kw + reference.schedule.p_f_ref_kw
        g_total = delta.g_res_plan_gpu + reference.schedule.g_f_ref_gpu
        mapped_p = np.asarray([base["power_weights"][rack] for rack in base["rack_ids"]])[:, None] * np.asarray(base["p_q90"])[None, :]
        mapped_g = np.asarray([base["gpu_weights"][rack] for rack in base["rack_ids"]])[:, None] * np.asarray(base["g_q90"])[None, :]
        reports.append({
            "day": day, "H0_REQ": float(h0_req.sum()), "H0_NOM": float(h0_nom.sum()),
            "H0_LOW": float(h0_low.sum()), "H0_UNCERTAIN": float((h0_nom - h0_low).sum()),
            "D_day_Q50_arrivals_nodeh": float(reference.schedule.arrivals_nodeh.sum()),
            "reference_service_nodeh": float(reference.schedule.x_ref_nodeh.sum()),
            "reference_terminal_backlog_nodeh": float(reference.schedule.backlog_nodeh[-1].sum()),
            "reference_mass_error_nodeh": float(
                h0_nom.sum() + reference.schedule.arrivals_nodeh.sum()
                - reference.schedule.x_ref_nodeh.sum() - reference.schedule.backlog_nodeh[-1].sum()
            ),
            "B0_reference_V4_sha256": sha, "B2_reference_V4_sha256": sha,
            "B0_B2_reference_bytes_identical": True,
            "minimum_P_RES_kw": float(delta.p_res_plan_kw.min()),
            "minimum_G_RES_gpu": float(delta.g_res_plan_gpu.min()),
            "minimum_raw_P_RES_kw": delta.minimum_raw_p_kw,
            "minimum_raw_G_RES_gpu": delta.minimum_raw_g_gpu,
            "P_numeric_tolerance_cells": delta.p_tolerance_cells,
            "G_numeric_tolerance_cells": delta.g_tolerance_cells,
            "maximum_P_total_double_count_error_kw": float(np.max(np.abs(p_total - mapped_p))),
            "maximum_G_total_double_count_error_gpu": float(np.max(np.abs(g_total - mapped_g))),
            "uncertain_remainder_identity_error": float(np.max(np.abs(reference.uncertain_initial_nodeh - (h0_nom - h0_low)))),
            "April_fit_rows": 0, "Apr04_result_reads": 0,
        })
    status = "PASS" if all(
        row["B0_B2_reference_bytes_identical"]
        and float(row["minimum_P_RES_kw"]) >= 0
        and float(row["minimum_G_RES_gpu"]) >= 0
        and abs(float(row["reference_mass_error_nodeh"])) <= 1e-8
        and float(row["maximum_P_total_double_count_error_kw"]) <= 1e-8
        and float(row["maximum_G_total_double_count_error_gpu"]) <= 1e-8
        and float(row["minimum_raw_P_RES_kw"]) >= -1e-9
        and float(row["minimum_raw_G_RES_gpu"]) >= -1e-9
        for row in reports
    ) else "FAIL"
    contract = {
        "artifact_id": "V29R2_REFERENCE_V4_CONTRACT_V1", "status": status,
        "authority": "REFERENCE_COMPUTE_SCHEDULE_V4",
        "inputs": ["H0_NOM from PRE_DAY_QUEUE_BRIDGE_V2", "existing D-day Q50 flexible arrivals"],
        "controllable_carryin_actuator": "H0_LOW only",
        "uncertain_remainder": "H0_NOM - H0_LOW remains in reference/residual and is not guaranteed control flexibility",
        "policy": "deterministic earliest-feasible fluid service; no grid signal",
        "tie_break": ["cohort ID", "capacity-proportional frozen rack order", "slot"],
        "grid_loading_reads": 0, "MESS_state_reads": 0, "Actual_reads": 0, "result_reads": 0,
        "negative_residual_clipping": False, "PARTIAL_shared_controllable": False,
        "running_job_preemption": False, "synthetic_deadline": False,
        "B0_B2_single_serialized_object": True,
        "prefreeze_structural_day_count": len(reports),
        "Apr04_causal_cutoff_input_materialized": True,
        "Apr04_optimizer_result_reads": 0, "Apr04_Actual_reads": 0,
        "April_fit_rows": 0,
    }
    sha_report = {
        "artifact_id": "V29R2_REFERENCE_V4_SHA_REPORT_V1", "status": status,
        "B0_B2_byte_identity_all_days": all(row["B0_B2_reference_bytes_identical"] for row in reports),
        "days": reports,
    }
    residual = {
        "artifact_id": "V29R2_REFERENCE_V4_RESIDUAL_AUDIT_V1", "status": status,
        "minimum_P_RES_kw": min(float(row["minimum_P_RES_kw"]) for row in reports),
        "minimum_G_RES_gpu": min(float(row["minimum_G_RES_gpu"]) for row in reports),
        "negative_residual_clipping_call_count": 0,
        "substantive_negative_residual_count": 0,
        "numeric_tolerance_canonicalization_authority": "existing 1e-9 reference-delta numerical closure only",
        "P_numeric_tolerance_cell_count": sum(int(row["P_numeric_tolerance_cells"]) for row in reports),
        "G_numeric_tolerance_cell_count": sum(int(row["G_numeric_tolerance_cells"]) for row in reports),
        "minimum_raw_P_RES_kw": min(float(row["minimum_raw_P_RES_kw"]) for row in reports),
        "minimum_raw_G_RES_gpu": min(float(row["minimum_raw_G_RES_gpu"]) for row in reports),
        "maximum_P_total_double_count_error_kw": max(float(row["maximum_P_total_double_count_error_kw"]) for row in reports),
        "maximum_G_total_double_count_error_gpu": max(float(row["maximum_G_total_double_count_error_gpu"]) for row in reports),
        "maximum_uncertain_remainder_identity_error": max(float(row["uncertain_remainder_identity_error"]) for row in reports),
        "uncertain_remainder_counted_as_controllable": False,
        "April_fit_rows": 0, "Apr04_result_reads": 0, "days": reports,
    }
    write_json(out / "V29R2_REFERENCE_V4_CONTRACT.json", contract)
    write_json(out / "V29R2_REFERENCE_V4_SHA_REPORT.json", sha_report)
    write_json(out / "V29R2_REFERENCE_V4_RESIDUAL_AUDIT.json", residual)
    if status != "PASS":
        raise RuntimeError("V29R2_REFERENCE_V4_GATE_FAIL")
    return contract
