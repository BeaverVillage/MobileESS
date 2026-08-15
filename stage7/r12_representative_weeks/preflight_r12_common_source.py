#!/usr/bin/env python3
"""Read-only R12 common-source coverage preflight; never calls a solver."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


SCIENCE_SHA = "1177ac8814f1008907f89ebf513bf9fe3e469d2c09a51ba85303c46c428f76b9"
FORECAST_SHA = "d0e10553851cd9cbaf08cd01009915454d2c81eb0366e36fdd916a54b039fb65"
R7_SOURCE_SHA = "f712d096e9b8ae5efc12ad01aef6ca28ce5d5cb313a2b22f8db1a5765ffeb735"
R10_SOURCE_SHA = "bbe307835ff97e9e340d294f664c7c0ac5b2c19715af7c5c7f509687aae47fc4"
Q2_RUNTIME_SHA = "447fad6d2ffe61cb7cf3ab33c97b4c9653d04d28ce4f5ccaf698e74f3ea1ecf1"
RACK_ACTUAL_SHA = "e2262017b05121b8675403d82e591d47141b776c90a582196663d1c6ccabd5c3"
RACK_INFERENCE_SHA = "1339deb0c0f4edd30159cd96046224f31c4d0a1178ac88ed249daeb765524f38"
RACK_FORECAST_SHA = "56f7486716869ddacacd9345482dfb6b3763564cffed534ea6f4670c7a0c40ab"
H = 54
AXIS_STEPS = 105120
ISSUE_TO_TRAFFIC_ORIGIN = 631296


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def intervals(root: Path) -> tuple[list[dict[str, str]], np.ndarray]:
    with (root / "frozen_authority/REP_WEEK_SELECTION_2025_K12.csv").open(
        encoding="utf-8", newline=""
    ) as stream:
        weeks = list(csv.DictReader(stream))
    required = np.unique(
        np.concatenate(
            [
                np.arange(
                    int(row["burn_in_start_index"]),
                    int(row["start_index"]),
                    dtype=np.int32,
                )
                for row in weeks
            ]
        )
    )
    return weeks, required


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-work", default="/home/jaewon/mobile_ess_work")
    parser.add_argument(
        "--repo",
        default="/home/jaewon/mobile_ess_work/stage7_final_completion_20260815/repo",
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    base = Path(args.base_work).resolve()
    repo = Path(args.repo).resolve()
    weeks, issues = intervals(root)
    checks: dict[str, bool] = {}

    science = repo / "science/main.py"
    forecast = base / "execution_packages/Mobile_ESS_stage_p6a4h1b_p7a3f1b_conditional_dag_parallel_v3_0_1/assets/forecast/P6A3_FULL_YEAR_CAUSAL_FORECAST.npz"
    r7 = base / "stage7_t2_power_price_r7/A_TO_C_T2_R7_20260815T052954Z/power/source_tree/main.py"
    r10 = base / "stage7_t2_precision_repair/A_TO_C_T2_R10_20260815T074441Z/REPAIRED_SOURCE_PACKAGE/main.py"
    paths = {
        "science": (science, SCIENCE_SHA),
        "forecast": (forecast, FORECAST_SHA),
        "r7_source": (r7, R7_SOURCE_SHA),
        "r10_source": (r10, R10_SOURCE_SHA),
    }
    for name, (path, expected) in paths.items():
        checks[f"{name}_sha_exact"] = path.is_file() and sha256(path) == expected

    checks["required_burn_in_issue_count_6912"] = len(issues) == 6912
    checks["required_issue_axis_inside_2025"] = int(issues.min()) >= 0 and int(issues.max()) < AXIS_STEPS
    targets = issues[:, None].astype(np.int64) + np.arange(H, dtype=np.int64)[None, :]
    checks["all_h54_targets_inside_2025"] = int(targets.max()) == 102292 < AXIS_STEPS

    with np.load(forecast, allow_pickle=False) as source:
        checks["forecast_issue_axis_exact"] = np.array_equal(
            np.asarray(source["issue_step"], dtype=np.int32),
            np.arange(AXIS_STEPS, dtype=np.int32),
        )
        quantiles = {
            name: np.asarray(source[name][issues], dtype=np.float32)
            for name in ("q10", "q50", "q90")
        }
    checks["forecast_union_shape"] = all(
        value.shape == (6912, H, 3) for value in quantiles.values()
    )
    checks["forecast_union_finite"] = all(np.isfinite(value).all() for value in quantiles.values())
    checks["forecast_quantiles_ordered"] = bool(
        np.all(quantiles["q10"] <= quantiles["q50"])
        and np.all(quantiles["q50"] <= quantiles["q90"])
    )

    # R10 maps each five-minute controller issue to its traffic origin.  The
    # frozen Q2 tensor is read only at causal forecast cells selected by that
    # origin and the 54-step horizon.  Checking the complete union here avoids
    # discovering a split-boundary NaN after an expensive materialization.
    r10_text = r10.read_text(encoding="utf-8")
    expected_stage2a_lines = (
        'RP=Path("/home/jaewon/mobile_ess_sumo/research_pipeline")',
        'TML10=RP/"22_ml_stage10_v11_2025_one_shot_final_test_v1"',
        'STAGE2A_RUNTIME=TML10/"runtime_inputs/stage2a_q2_amendment_v1_1"',
    )
    checks["r10_stage2a_binding_exact"] = all(line in r10_text for line in expected_stage2a_lines)
    stage2a = Path(
        "/home/jaewon/mobile_ess_sumo/research_pipeline/"
        "22_ml_stage10_v11_2025_one_shot_final_test_v1/"
        "runtime_inputs/stage2a_q2_amendment_v1_1"
    )
    q2 = stage2a / "scats_forecast/q2_global_volume_forecast_offsets1_19.float32.npy"
    checks["q2_sha_exact"] = q2.is_file() and sha256(q2) == Q2_RUNTIME_SHA
    origins = ISSUE_TO_TRAFFIC_ORIGIN + issues.astype(np.int64)
    latest_complete = origins // 3 - 1
    future_index = origins[:, None] + np.arange(1, H + 1, dtype=np.int64)[None, :]
    offsets = future_index // 3 - latest_complete[:, None]
    checks["q2_offsets_inside_frozen_1_19"] = int(offsets.min()) >= 1 and int(offsets.max()) <= 19
    q2_array = np.load(q2, mmap_mode="r")
    required_q2 = np.asarray(q2_array[latest_complete[:, None], offsets - 1], dtype=np.float32)
    checks["q2_complete_union_finite"] = bool(np.isfinite(required_q2).all())
    checks["q2_boundary_overlay_not_required"] = checks["q2_complete_union_finite"]

    rack_root = base / "frozen_artifacts/stage_k9h7_v2044r12b1d1ar3r1r3r4r6r2r4r6_phase_boundary_rack_20260808T222927"
    rack_forecast_root = base / "frozen_artifacts/stage_k9h7_v2044r12b1d1ar3r1r3r4r6r2r2r3_float32_identity_20260808T203037"
    rack_actual = rack_root / "RACK_CURRENT_FIXED_BACKGROUND_PRIMARY_FIXED_AEST_5MIN.parquet"
    rack_inference = rack_root / "PRIMARY_FIXED_AEST_CURRENT_FIXED_GPU_IT_12IDC.parquet"
    rack_forecast = rack_forecast_root / "GLOBAL_K5B2_K5C3_FIXED_GPU_48STEP_2025.parquet"
    for name, path, expected in (
        ("rack_actual", rack_actual, RACK_ACTUAL_SHA),
        ("rack_inference", rack_inference, RACK_INFERENCE_SHA),
        ("rack_forecast", rack_forecast, RACK_FORECAST_SHA),
    ):
        checks[f"{name}_sha_exact"] = path.is_file() and sha256(path) == expected

    axis0 = pd.Timestamp("2024-12-31T14:00:00Z")
    required_ns_array = (
        axis0 + pd.to_timedelta(issues.astype(np.int64) * 5, unit="min")
    ).as_unit("ns").asi8
    required_ns = set(required_ns_array.tolist())
    actual = pd.read_parquet(rack_actual, columns=["timestamp_utc", "rack_pool_id"])
    inference = pd.read_parquet(rack_inference, columns=["timestamp_utc", "idc_id"])
    rack_q = pd.read_parquet(rack_forecast, columns=["timestamp_utc"])
    for frame in (actual, inference, rack_q):
        frame["timestamp_utc"] = pd.to_datetime(frame["timestamp_utc"], utc=True, errors="raise")
    actual_mask = np.isin(pd.DatetimeIndex(actual["timestamp_utc"]).as_unit("ns").asi8, required_ns_array)
    inference_mask = np.isin(pd.DatetimeIndex(inference["timestamp_utc"]).as_unit("ns").asi8, required_ns_array)
    rack_q_mask = np.isin(pd.DatetimeIndex(rack_q["timestamp_utc"]).as_unit("ns").asi8, required_ns_array)
    actual_count = actual[actual_mask].groupby("timestamp_utc")["rack_pool_id"].nunique()
    inference_count = inference[inference_mask].groupby("timestamp_utc")["idc_id"].nunique()
    rack_q_count = rack_q[rack_q_mask]["timestamp_utc"].nunique()
    checks["rack_actual_union_48_rows_each"] = len(actual_count) == len(issues) and bool((actual_count == 48).all())
    checks["rack_inference_union_12_rows_each"] = len(inference_count) == len(issues) and bool((inference_count == 12).all())
    checks["rack_forecast_union_covered"] = int(rack_q_count) == len(issues)

    # Structural audit: the accepted R10 implementation indexes all work from
    # module-global ISSUES/ORIGINS and iterates zip(ISSUES, ORIGINS).  It has no
    # contiguity predicate inside materialize_mobility, so a sorted unique union
    # is lawful.  The streaming wrapper still requires a 54-issue exact replay
    # before production cache materialization.
    mobility_body = r10_text[r10_text.index("def materialize_mobility"):r10_text.index("def forecast_audit")]
    checks["r10_union_axis_parameterized"] = "zip(ISSUES,ORIGINS)" in mobility_body
    checks["r10_no_contiguity_requirement_in_materializer"] = "np.diff(ISSUES)" not in mobility_body and "arange" not in mobility_body
    checks["common_cache_not_materialized_by_preflight"] = True
    checks["gurobi_not_executed"] = True
    checks["opendss_not_executed"] = True

    failed = sorted(name for name, passed in checks.items() if not passed)
    payload = {
        "schema_version": "conversation_c.stage7.r12.common_source_preflight.v1",
        "status": "PASS_READY_FOR_STREAMING_CACHE_IMPLEMENTATION" if not failed else "FAIL_CLOSED",
        "checks": checks,
        "failed_checks": failed,
        "candidate_ids": [row["candidate_id"] for row in weeks],
        "primary_unique_issue_count": len(issues),
        "issue_min": int(issues.min()),
        "issue_max": int(issues.max()),
        "h54_target_max": int(targets.max()),
        "q2_nonfinite_required_values": int(np.sum(~np.isfinite(required_q2))),
        "common_cache_materialized": False,
        "gurobi_executed": False,
        "opendss_executed": False,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if not failed else 2


if __name__ == "__main__":
    raise SystemExit(main())
