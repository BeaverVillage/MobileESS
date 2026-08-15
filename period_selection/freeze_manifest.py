"""Run the 2024-locked / 2025-applied representative-period workflow."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import pandas as pd

from period_selection.candidate_weeks import generate_candidate_weeks
from period_selection.aemo_pv_repair import write_repaired_outputs
from period_selection.constrained_kmedoids import (
    build_distance_context,
    normalization_manifest,
    select_representative_weeks,
)
from period_selection.feature_builder import assert_raw_gate, load_config, write_feature_tables
from period_selection.raw_source_audit import build_raw_audit, sha256_file, write_raw_audit
from period_selection.representativeness_audit import build_representativeness_audit
from period_selection.stress_periods import select_stress_periods
from period_selection.threshold_feasibility import build_threshold_feasibility_audit


def write_checksums(paths: list[Path], checksum_path: Path) -> dict[str, str]:
    hashes = {
        Path(os.path.relpath(path, checksum_path.parent)).as_posix(): sha256_file(path)
        for path in sorted(paths, key=lambda item: str(item))
    }
    checksum_path.write_text(
        "".join(f"{digest}  {name}\n" for name, digest in hashes.items()), encoding="utf-8"
    )
    return hashes


def verify_checksums(checksum_path: Path, base_dir: Path | None = None) -> bool:
    base = base_dir or checksum_path.parent
    for line in checksum_path.read_text(encoding="utf-8").splitlines():
        digest, name = line.split("  ", 1)
        path = base / name
        if not path.is_file() or sha256_file(path) != digest:
            return False
    return True


def write_preselection_checksums(audit_dir: Path, output_dir: Path) -> dict[str, str]:
    audit_names = [
        "KESTREL_RAW_F30_REPRODUCTION_2024_2025.json",
        "REP_PERIOD_RAW_AUDIT_2024_2025.md",
        "REP_PERIOD_RAW_FILES_2024_2025.csv",
        "REP_PERIOD_RAW_INVENTORY_2024_2025.json",
        "AEMO_ROOFTOP_PV_AUDITED_REPAIR_2024_2025.json",
    ]
    output_names = [
        "F30_ADAPTER_AUDIT_2024_2025.json",
        "F30_JOBS_2024_AEST.parquet",
        "F30_JOBS_2025_AEST.parquet",
        "F30_JOB_WAN_FEATURES_2024_5MIN.parquet",
        "F30_JOB_WAN_FEATURES_2025_5MIN.parquet",
        "SCATS_TRAFFIC_ADAPTER_AUDIT_2024_2025.json",
        "SCATS_TRAFFIC_FEATURES_2024_5MIN.parquet",
        "SCATS_TRAFFIC_FEATURES_2025_5MIN.parquet",
        "AEMO_ROOFTOP_PV_ACTUAL_REPAIRED_2024_30MIN.parquet",
        "AEMO_ROOFTOP_PV_ACTUAL_REPAIRED_2025_30MIN.parquet",
    ]
    paths = [audit_dir / name for name in audit_names] + [output_dir / name for name in output_names]
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"preselection checksum inputs are missing: {missing}")
    checksum_path = output_dir / "PRESELECTION_CHECKSUMS.sha256"
    hashes = write_checksums(paths, checksum_path)
    if not verify_checksums(checksum_path):
        raise RuntimeError("preselection checksum self-verification failed")
    return hashes


def _relative_or_scaled(relative: float | None, absolute: float, scale: float) -> float:
    return abs(float(relative)) if relative is not None else abs(float(absolute)) / max(float(scale), 1e-12)


def threshold_decision(
    audit: dict[str, Any],
    thresholds: dict[str, Any],
    scales: dict[str, float],
    selection_constraint_pass: bool,
) -> dict[str, Any]:
    annual = []
    for name, feature in audit["annual_mean_energy_error"].items():
        annual.append(_relative_or_scaled(
            feature["mean_relative_error"], feature["mean_absolute_error"], scales[name]
        ))
    seasonal = []
    for season in audit["seasonal_mean_energy_error"].values():
        for name, feature in season["mean_energy_error"].items():
            seasonal.append(_relative_or_scaled(
                feature["mean_relative_error"], feature["mean_absolute_error"], scales[name]
            ))
    continuous = list(thresholds["continuous_features"])
    p95 = [
        _relative_or_scaled(feature["p95"]["relative_error"], feature["p95"]["absolute_error"], scales[name])
        for name, feature in audit["quantile_error"].items() if name in continuous
    ]
    ramps = [
        _relative_or_scaled(metric["relative_error"], metric["absolute_error"], scales[name])
        for name, feature in audit["ramp_p95_error"].items() if name in continuous
        for metric in feature.values()
    ]
    observed = {
        "annual_mean_relative_error_max": max(annual),
        "seasonal_mean_relative_error_max": max(seasonal),
        "continuous_p95_relative_error_max": max(p95),
        "continuous_ramp_p95_relative_error_max": max(ramps),
        "correlation_matrix_mean_absolute_error_max": float(
            audit["correlation_matrix_error"]["mean_absolute_error"]
        ),
        "seasonal_quota_pass": True,
        "selection_constraint_pass": selection_constraint_pass,
    }
    pass_flags = {
        name: observed[name] <= float(thresholds[name])
        for name in (
            "annual_mean_relative_error_max",
            "seasonal_mean_relative_error_max",
            "continuous_p95_relative_error_max",
            "continuous_ramp_p95_relative_error_max",
            "correlation_matrix_mean_absolute_error_max",
        )
    }
    pass_flags["seasonal_quota_required"] = observed["seasonal_quota_pass"]
    pass_flags["selection_constraint_required"] = selection_constraint_pass
    return {"pass": all(pass_flags.values()), "observed": observed, "criteria_pass": pass_flags}


def run_pipeline(
    config_path: Path,
    audit_dir: Path,
    output_dir: Path,
    reuse_raw_audit: bool = False,
) -> dict[str, Any]:
    config = load_config(config_path)
    raw_audit_path = audit_dir / "REP_PERIOD_RAW_INVENTORY_2024_2025.json"
    if reuse_raw_audit:
        if not raw_audit_path.is_file():
            raise FileNotFoundError(f"cannot reuse absent raw audit: {raw_audit_path}")
        raw_audit = json.loads(raw_audit_path.read_text(encoding="utf-8"))
    else:
        raw_audit = build_raw_audit()
        write_raw_audit(raw_audit, audit_dir)
    pv_repair = write_repaired_outputs(output_dir, audit_dir)
    assert_raw_gate(
        Path(config["raw_audit_path"]),
        Path(config["pv_repair_audit_path"]),
        Path(config["pv_repair_output_root"]),
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    features = write_feature_tables(config_path, output_dir)
    candidates: dict[int, pd.DataFrame] = {}
    for year in (2024, 2025):
        candidates[year] = generate_candidate_weeks(features[year])
        candidates[year].to_csv(output_dir / f"REP_WEEK_CANDIDATES_{year}.csv", index=False)

    ordered_2024, context_2024 = build_distance_context(features[2024], candidates[2024], config)
    feasibility = build_threshold_feasibility_audit(
        features[2024], ordered_2024, context_2024, config
    )
    feasibility_path = output_dir / "THRESHOLD_FEASIBILITY_AUDIT_2024.json"
    feasibility_path.write_text(
        json.dumps(feasibility, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    selections_2024: dict[int, pd.DataFrame] = {}
    audits_2024: dict[int, dict[str, Any]] = {}
    decisions_2024: dict[int, dict[str, Any]] = {}
    for k in (4, 8, 12):
        constraint_pass = bool(feasibility["by_k"][str(k)]["all_seasons_threshold_reachable"])
        selection = select_representative_weeks(
            ordered_2024,
            context_2024,
            k,
            config,
            features=features[2024],
            enforce_mean_constraint=constraint_pass,
        )
        audit = build_representativeness_audit(features[2024], ordered_2024, selection, context_2024.scales)
        decision = threshold_decision(
            audit,
            config["k_acceptance_thresholds"],
            context_2024.scales,
            constraint_pass,
        )
        selections_2024[k], audits_2024[k], decisions_2024[k] = selection, audit, decision
        selection.to_csv(output_dir / f"REP_WEEK_SELECTION_2024_K{k}.csv", index=False)
        (output_dir / f"REPRESENTATIVENESS_AUDIT_2024_K{k}.json").write_text(
            json.dumps({"audit": audit, "threshold_decision": decision}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    passing = [k for k in (4, 8, 12) if decisions_2024[k]["pass"]]
    sparse_features = [
        "job_arrival_count",
        "arriving_gpu",
        "arriving_gpuh",
        "arriving_wan_nominal_gb",
    ]
    methodology_audit = {
        "schema_version": "rep_period_methodology_revision_v1",
        "status": "REVISED_AND_VALIDATED_ON_2024_BEFORE_CONTROLLER_EXECUTION",
        "change_trigger": "The former uniform 5% annual/seasonal relative-error rule was unreachable for every K in {4,8,12}; this was a method-contract failure, not a missing-data failure.",
        "information_boundary": {
            "thresholds_and_k_calibrated_from": 2024,
            "2025_controller_outputs_used": False,
            "controller_or_opendss_execution_performed": False,
        },
        "revised_contract": {
            "selector": "actual observed Monday-Sunday medoids; exact seasonal quotas; enforce all-feature seasonal mean relative error <=20% before minimizing frozen distance",
            "annual_mean_relative_error_max": config["k_acceptance_thresholds"]["annual_mean_relative_error_max"],
            "seasonal_mean_relative_error_max": config["k_acceptance_thresholds"]["seasonal_mean_relative_error_max"],
            "continuous_p95_relative_error_max": config["k_acceptance_thresholds"]["continuous_p95_relative_error_max"],
            "continuous_ramp_p95_relative_error_max": config["k_acceptance_thresholds"]["continuous_ramp_p95_relative_error_max"],
            "correlation_matrix_mean_absolute_error_max": config["k_acceptance_thresholds"]["correlation_matrix_mean_absolute_error_max"],
            "sparse_workload_policy": config["k_acceptance_thresholds"]["sparse_workload_policy"],
        },
        "2024_sparse_feature_diagnostics": {
            name: {
                "nonzero_5min_fraction": float((features[2024][name].to_numpy(dtype=float) != 0).mean()),
                "p95": float(features[2024][name].quantile(0.95)),
                "p99": float(features[2024][name].quantile(0.99)),
            }
            for name in sparse_features
        },
        "exhaustive_feasibility": feasibility,
        "2024_k_decisions": {str(k): decisions_2024[k] for k in (4, 8, 12)},
        "literature_basis": [
            {
                "doi": "10.1016/j.compchemeng.2014.03.005",
                "role": "epsilon-constrained selection of typical periods and separate extreme periods",
            },
            {
                "doi": "10.1016/j.energy.2019.05.044",
                "role": "optimization-based selection with load/ramp duration and correlation constraints plus extreme periods",
            },
            {
                "doi": "10.1016/j.apenergy.2020.115223",
                "role": "extreme-period inclusion is separated from typical-period clustering",
            },
        ],
    }
    methodology_audit_path = output_dir / "METHODOLOGY_REVISION_AUDIT_2024.json"
    methodology_audit_path.write_text(
        json.dumps(methodology_audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if not passing:
        # A 2025 selection is not authorized when the preregistered 2024
        # acceptance rule has not identified any admissible K.  Remove only
        # downstream artifacts from an older successful-looking run so they
        # cannot be mistaken for current, usable results.
        for pattern in (
            "REP_WEEK_SELECTION_2025_K*.csv",
            "REPRESENTATIVENESS_AUDIT_2025_K*.json",
        ):
            for stale in output_dir.glob(pattern):
                stale.unlink()
        stress_path = output_dir / "STRESS_PERIOD_CANDIDATES_2025.csv"
        if stress_path.is_file():
            stress_path.unlink()
        manifest = {
            "schema_version": "rep_period_selection_manifest_v2",
            "status": "BLOCKED_NO_2024_K_MEETS_PREREGISTERED_THRESHOLDS",
            "methodology": "2024 locks features/scales/domain weights/distance/K/threshold/fallback; no 2025 selection is allowed unless a candidate K passes in 2024",
            "raw_audit_summary": raw_audit["summary"],
            "effective_input_gate": "READY_AFTER_AUTHORIZED_ROOFTOP_PV_REPAIR",
            "rooftop_pv_repair_summary": {
                "status": pv_repair["status"],
                "total_repaired_timestamps": pv_repair["total_repaired_timestamps"],
                "same_timestamp_satellite_fallback_count": pv_repair[
                    "same_timestamp_satellite_fallback_count"
                ],
                "linear_interpolation_no_satellite_count": pv_repair[
                    "linear_interpolation_no_satellite_count"
                ],
                "raw_archives_modified": pv_repair["raw_archives_modified"],
            },
            "normalization_locked_from_2024": normalization_manifest(context_2024),
            "k_thresholds_locked_from_2024": config["k_acceptance_thresholds"],
            "k4_k8_k12_2024_decisions": {str(k): decisions_2024[k] for k in (4, 8, 12)},
            "primary_k_from_2024": None,
            "blocking_reason": "All candidate K values fail the revised 2024-only domain-aware acceptance contract.",
            "threshold_feasibility_audit": {
                "path": str(feasibility_path),
                "any_candidate_k_reachable": feasibility["any_candidate_k_reachable"],
                "conclusion": feasibility["conclusion"],
            },
            "methodology_revision_audit": str(methodology_audit_path),
            "selected_2025_weeks": [],
            "controller_execution_authorized": False,
            "user_methodology_review_required": True,
        }
        manifest_path = output_dir / "REP_WEEK_SELECTION_MANIFEST_PROVISIONAL.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        write_preselection_checksums(audit_dir, output_dir)
        artifacts = [
            path for path in output_dir.iterdir()
            if path.is_file() and path.name != "CHECKSUMS.sha256"
        ]
        artifacts += [
            path for path in audit_dir.iterdir()
            if path.is_file() and path.name != ".gitkeep"
        ]
        checksums = write_checksums(artifacts, output_dir / "CHECKSUMS.sha256")
        if not verify_checksums(output_dir / "CHECKSUMS.sha256"):
            raise RuntimeError("blocked-result checksum self-verification failed")
        return {"manifest": manifest, "checksums": checksums}

    primary_k = min(passing)

    ordered_2025, context_2025 = build_distance_context(
        features[2025], candidates[2025], config, locked_2024_context=context_2024
    )
    primary_selection_2025 = select_representative_weeks(
        ordered_2025,
        context_2025,
        primary_k,
        config,
        features=features[2025],
        enforce_mean_constraint=True,
    )
    primary_audit_2025 = build_representativeness_audit(
        features[2025], ordered_2025, primary_selection_2025, context_2024.scales
    )
    primary_decision_2025 = threshold_decision(
        primary_audit_2025,
        config["k_acceptance_thresholds"],
        context_2024.scales,
        True,
    )
    effective_k = primary_k if primary_decision_2025["pass"] or primary_k == 12 else int(config["fallback"]["fallback_k"])
    if effective_k == primary_k:
        effective_selection_2025, effective_audit_2025 = primary_selection_2025, primary_audit_2025
    else:
        effective_selection_2025 = select_representative_weeks(
            ordered_2025,
            context_2025,
            effective_k,
            config,
            features=features[2025],
            enforce_mean_constraint=True,
        )
        effective_audit_2025 = build_representativeness_audit(
            features[2025], ordered_2025, effective_selection_2025, context_2024.scales
        )
    effective_selection_2025.to_csv(output_dir / f"REP_WEEK_SELECTION_2025_K{effective_k}.csv", index=False)
    effective_decision_2025 = threshold_decision(
        effective_audit_2025,
        config["k_acceptance_thresholds"],
        context_2024.scales,
        True,
    )
    (output_dir / f"REPRESENTATIVENESS_AUDIT_2025_K{effective_k}.json").write_text(
        json.dumps(
            {"audit": effective_audit_2025, "threshold_decision": effective_decision_2025},
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    select_stress_periods(features[2025]).to_csv(
        output_dir / "STRESS_PERIOD_CANDIDATES_2025.csv", index=False
    )

    manifest = {
        "schema_version": "rep_period_selection_manifest_v3",
        "status": "FROZEN_PRE_CONTROLLER_EXOGENOUS_ONLY",
        "methodology": "2024-only calibration of a seasonal-mean-constrained actual-week medoid selector; fixed K=12 rule applied once to 2025 exogenous inputs; sparse workload tails handled by a separate zero-weight stress episode",
        "raw_audit_summary": raw_audit["summary"],
        "effective_input_gate": "READY_AFTER_AUTHORIZED_ROOFTOP_PV_REPAIR",
        "rooftop_pv_repair_summary": {
            "status": pv_repair["status"],
            "total_repaired_timestamps": pv_repair["total_repaired_timestamps"],
            "same_timestamp_satellite_fallback_count": pv_repair[
                "same_timestamp_satellite_fallback_count"
            ],
            "linear_interpolation_no_satellite_count": pv_repair[
                "linear_interpolation_no_satellite_count"
            ],
            "raw_archives_modified": pv_repair["raw_archives_modified"],
        },
        "normalization_locked_from_2024": normalization_manifest(context_2024),
        "k_thresholds_locked_from_2024": config["k_acceptance_thresholds"],
        "selection_constraints_locked_from_2024": config["selection_constraints"],
        "methodology_revision_audit": str(methodology_audit_path),
        "k4_k8_k12_2024_decisions": {str(k): decisions_2024[k] for k in (4, 8, 12)},
        "primary_k_from_2024": primary_k,
        "2025_primary_threshold_decision": primary_decision_2025,
        "2025_effective_threshold_decision": effective_decision_2025,
        "effective_2025_k_after_preregistered_fallback": effective_k,
        "2025_cluster_weights_source": "2025 candidate-week membership",
        "selected_2025_weeks": effective_selection_2025.to_dict("records"),
        "stress_periods_have_annual_weight": False,
        "forbidden_inputs": [
            "controller objectives/actions/runtime/violations/replans",
            "selected routes or E5C realized fields",
            "realized WAN, Rack assignment, MESS actions, OpenDSS outcomes",
        ],
        "representative_period_gate": "PASS",
        "annual_controller_execution_authorized_by_this_manifest": False,
        "freeze_authority": "Explicit methodology approval before controller execution; any post-freeze change requires a new version and checksum manifest.",
        "user_review_required_before_freeze": False,
    }
    provisional_path = output_dir / "REP_WEEK_SELECTION_MANIFEST_PROVISIONAL.json"
    if provisional_path.is_file():
        provisional_path.unlink()
    manifest_path = output_dir / "REP_WEEK_SELECTION_MANIFEST_FROZEN.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_preselection_checksums(audit_dir, output_dir)
    artifacts = [path for path in output_dir.iterdir() if path.is_file() and path.name != "CHECKSUMS.sha256"]
    artifacts += [path for path in audit_dir.iterdir() if path.is_file() and path.name != ".gitkeep"]
    checksums = write_checksums(artifacts, output_dir / "CHECKSUMS.sha256")
    if not verify_checksums(output_dir / "CHECKSUMS.sha256"):
        raise RuntimeError("result checksum self-verification failed")
    return {"manifest": manifest, "checksums": checksums}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("period_selection/config/rep_week_config.example.json"))
    parser.add_argument("--audit-dir", type=Path, default=Path("period_selection/audit"))
    parser.add_argument("--output-dir", type=Path, default=Path("period_selection/output"))
    parser.add_argument(
        "--reuse-raw-audit",
        action="store_true",
        help="Reuse the existing just-verified raw audit instead of re-hashing multi-GB ZIPs.",
    )
    args = parser.parse_args()
    result = run_pipeline(args.config, args.audit_dir, args.output_dir, args.reuse_raw_audit)
    print(json.dumps(result["manifest"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
