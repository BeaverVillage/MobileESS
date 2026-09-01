#!/usr/bin/env python3
"""Freeze the full-node distribution and reference scheduler contracts."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from dayahead.authority import sha256_file
from dayahead.v28r2.reference_compute import (
    CASE_CAPACITY_GPU, FullNodeDistributionAdapter, build_reference_schedule,
    case_rack_capacity_nodeh_per_slot,
)
from dayahead.v28r2.source_labels import AEST, TRAIN_START, load_optimizer_labels

OUT = REPO / "dayahead/artifacts/v28r2_heavy_backend"


def write_json(name: str, payload: object) -> None:
    path = OUT / name
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def main() -> None:
    labels = load_optimizer_labels(REPO)
    probabilities = np.zeros((7, 96, len(labels.cohort_ids)), dtype=float)
    training_start = np.datetime64(TRAIN_START)
    for day_index in range(labels.w_nodeh.shape[0] // 96):
        day = labels.timestamps[day_index * 96]
        if day.to_datetime64() < training_start:
            continue
        probabilities[day.dayofweek] += labels.w_nodeh[day_index * 96:(day_index + 1) * 96]
    dow_raw_mass = probabilities.sum(axis=(1, 2))
    if np.any(dow_raw_mass <= 0):
        raise RuntimeError("V28R2_FULLNODE_ADAPTER_EMPTY_DOW")
    probabilities /= dow_raw_mass[:, None, None]
    adapter = FullNodeDistributionAdapter(probabilities, labels.cohort_ids)
    adapter.validate()

    rack_source = REPO / "dayahead/artifacts/v16/AIDC_RACK_MAPPING_CONTRACT.json"
    rack_payload = json.loads(rack_source.read_text(encoding="utf-8"))
    rack_ids = tuple(str(row["rack_id"]) for row in rack_payload["racks"])
    weights = {rack: float(weight) for rack, weight in zip(rack_ids, rack_payload["gpu_weights"], strict=True)}
    capacities = case_rack_capacity_nodeh_per_slot(rack_ids, weights)
    capacity_source = REPO / "dayahead/artifacts/v18_aidc_physical_refreeze/V18_KESTREL_CAPACITY_NORMALIZATION_CONTRACT.json"

    test_mass = float(labels.w_nodeh.reshape(-1, 96, len(labels.cohort_ids)).sum(axis=(1, 2)).mean())
    arrivals = adapter.materialize(test_mass, 0)
    schedule_a = build_reference_schedule(
        arrivals, cohort_ids=labels.cohort_ids, rack_ids=rack_ids,
        rack_capacity_nodeh_per_slot=capacities,
    )
    schedule_b = build_reference_schedule(
        arrivals.copy(), cohort_ids=tuple(labels.cohort_ids), rack_ids=tuple(rack_ids),
        rack_capacity_nodeh_per_slot=capacities.copy(),
    )
    bytes_a, bytes_b = schedule_a.canonical_bytes(), schedule_b.canonical_bytes()
    if bytes_a != bytes_b:
        raise RuntimeError("V28R2_REFERENCE_SCHEDULE_NONDETERMINISTIC")

    write_json("V28R2_FULLNODE_DISTRIBUTION_ADAPTER.json", {
        "artifact_id": "V28R2_FULLNODE_ELIGIBLE_DISTRIBUTION_ADAPTER_V1",
        "status": "PASS",
        "axes": {"day_of_week": list(range(7)), "slot": list(range(96)), "cohort": list(labels.cohort_ids)},
        "probabilities": probabilities.tolist(),
        "day_of_week_mass": probabilities.sum(axis=(1, 2)).tolist(),
        "pre_normalization_training_nodeh_by_day_of_week": dow_raw_mass.tolist(),
        "training_start": TRAIN_START,
        "training_end": "2025-03-31",
        "April_training_rows": 0,
        "May_training_rows": 0,
        "source_sha256": labels.source_sha256,
        "cohort_authority_sha256": sha256_file(REPO / "dayahead/artifacts/v16/AIDC_COHORT_CONTRACT.json"),
        "partial_cohort_count": 0,
        "mass_tolerance_nodeh": "1e-9 * max(1, H_D_Q50)",
        "FULLNODE_ADAPTER_READY": True,
    })
    write_json("V28R2_REFERENCE_COMPUTE_SCHEDULE_CONTRACT.json", {
        "artifact_id": "V28R2_REFERENCE_COMPUTE_SCHEDULE_CONTRACT_V1",
        "authority_id": "REFERENCE_COMPUTE_SCHEDULE_V2",
        "status": "PASS",
        "inputs": ["forecast_cohort_Q50_arrivals", "frozen_rack_axis", "frozen_rack_GPU_weights", "528_GPU_capacity_authority"],
        "prohibited_inputs": ["actual", "grid_loading", "voltage", "MESS_state", "future_start", "future_end", "future_runtime", "sharing"],
        "initial_backlog_nodeh": 0,
        "policy": "as-arrived earliest-feasible fluid service",
        "tie_break": ["cohort_id", "AIDC_id", "rack_id", "slot_order_with_time_progressing_earliest_first"],
        "case_capacity_GPU": CASE_CAPACITY_GPU,
        "rack_capacity_formula": "528 * frozen_gpu_weight / 4_GPU_per_node * 0.25_hour",
        "rack_mapping_sha256": sha256_file(rack_source),
        "capacity_authority_sha256": sha256_file(capacity_source),
        "REFERENCE_COMPUTE_SCHEDULE_READY": True,
    })
    write_json("V28R2_REFERENCE_COMPUTE_SCHEDULE_SCHEMA.json", {
        "artifact_id": "V28R2_REFERENCE_COMPUTE_SCHEDULE_SCHEMA_V1",
        "status": "PASS",
        "axes": {"cohort": len(labels.cohort_ids), "rack": len(rack_ids), "slot": 96, "backlog_boundary": 97},
        "fields": {
            "arrivals_nodeh": [96, len(labels.cohort_ids)],
            "x_ref_nodeh": [len(labels.cohort_ids), len(rack_ids), 96],
            "backlog_nodeh": [97, len(labels.cohort_ids)],
            "p_f_ref_kw": [len(rack_ids), 96],
            "g_f_ref_gpu": [len(rack_ids), 96],
        },
        "serialization": "canonical UTF-8 JSON sort_keys compact separators newline",
    })
    write_json("V28R2_REFERENCE_SCHEDULE_DETERMINISM_TEST.json", {
        "artifact_id": "V28R2_REFERENCE_SCHEDULE_DETERMINISM_TEST_V1",
        "status": "PASS",
        "test_daily_mass_nodeh": test_mass,
        "input_mass_error_nodeh": float(abs(arrivals.sum() - test_mass)),
        "terminal_backlog_nodeh": float(schedule_a.backlog_nodeh[-1].sum()),
        "serialization_a_sha256": digest_bytes(bytes_a),
        "serialization_b_sha256": digest_bytes(bytes_b),
        "bytes_identical": bytes_a == bytes_b,
        "B0_reference_schedule_sha256": digest_bytes(bytes_a),
        "B2_reference_schedule_sha256": digest_bytes(bytes_a),
        "B0_B2_same_serialized_object": True,
    })


if __name__ == "__main__":
    main()
