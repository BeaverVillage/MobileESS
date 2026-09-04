"""Dataset312-only partial-node identifiability and training-only cohort audit."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from .aidc_ml_data import AEST, NODE_CLASSES, TRAIN_START
from .aidc_power_response import GPU_PER_NODE
from .authority import DEFAULT_RAW_ROOT, sha256_file
from .reproduce_nlr_authority import object_empty
from .v17_deferrability_semantics import write_json


TRAIN_END_EXCLUSIVE = "2025-04-01"
CLASSIFICATION = "V17_AIDC_POWER_V2_C_PARTIAL_NODE_POWER_NOT_IDENTIFIABLE"
DATASET312_DEFAULT = Path(
    r"C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\raw데이터\NLR_Dataset_312_GenAI_Power\dataset.zip"
)
KESTREL_SHA256 = "3a90f9ac40991712f8718c686fa7b05d7a303a44a87ed1a8f21b403c11efd26f"
DATASET312_SHA256 = "dcad6de800fb565d850b163902e2eddae48aabd1ed1c7336f9a1cdaf3012f137"


def _h100(value: object) -> bool:
    return any(token.strip().casefold().startswith("gpu-h100") for token in str(value).split(","))


def _firewall() -> dict[str, int]:
    return {
        "Dataset312_Kestrel_row_merge_count": 0,
        "current_kappa_applied_to_unmodeled_node_hours": 0,
        "May_scientific_input_reads": 0,
        "June_scientific_input_reads": 0,
        "May_result_content_reads": 0,
        "June_result_content_reads": 0,
        "remaining_April_day_runs": 0,
        "AIDC_site_changes": 0,
        "beta_changes": 0,
        "PUE_changes": 0,
        "PF_changes": 0,
        "effect_selected_parameters": 0,
        "grid_benefit_selected_parameters": 0,
        "RCMQT_retraining_calls": 0,
        "H_regeneration_calls": 0,
        "J_I_regeneration_calls": 0,
    }


def _member_record(archive: zipfile.ZipFile, name: str) -> dict[str, Any]:
    raw = archive.read(name)
    return {
        "member": name,
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "crc32": f"{archive.getinfo(name).CRC:08x}",
    }


def _first_data_header(archive: zipfile.ZipFile, name: str) -> list[str]:
    line = archive.open(name).readline().decode("utf-8", errors="replace").strip()
    return line.lstrip("#").strip().split()


def audit_dataset312(dataset: Path) -> dict[str, Any]:
    import pyarrow.parquet as pq

    dataset = dataset.resolve()
    source_sha = sha256_file(dataset)
    if source_sha != DATASET312_SHA256:
        raise RuntimeError(f"V17_DATASET312_SHA_MISMATCH:{source_sha}")
    with zipfile.ZipFile(dataset) as archive:
        names = archive.namelist()
        readme = "README.md"
        training_metadata = "01_aggregated_datasets/training/metadata.csv"
        metadata_text = archive.read(training_metadata).decode("utf-8")
        metadata = list(csv.DictReader(io.StringIO(metadata_text)))
        nvml_members = [name for name in names if "/nvml_" in name.lower() and name.lower().endswith(".log")]
        rapl_members = [name for name in names if "/rapl_" in name.lower() and name.lower().endswith(".log")]
        training_nvml = next(name for name in nvml_members if "training_" in name)
        training_rapl = next(name for name in rapl_members if "training_" in name)
        aggregate_members = [
            "01_aggregated_datasets/training/results/000000.parquet",
            "01_aggregated_datasets/training/results/000021.parquet",
            "01_aggregated_datasets/inference_offline_llama3_70b/results/000000.parquet",
        ]
        aggregate_schema = []
        for name in aggregate_members:
            parquet = pq.ParquetFile(io.BytesIO(archive.read(name)))
            aggregate_schema.append({
                "member": name,
                "rows": int(parquet.metadata.num_rows),
                "fields": [{"name": field.name, "type": str(field.type)} for field in parquet.schema_arrow],
            })
        whole_facility_metadata = (
            "03_whole-facility_profiles/colocation/metadata.csv",
            "03_whole-facility_profiles/inference/metadata.csv",
        )
        whole_rows = {
            name: list(csv.DictReader(io.StringIO(archive.read(name).decode("utf-8"))))
            for name in whole_facility_metadata
        }
        readme_text = archive.read(readme).decode("utf-8", errors="replace")
        nvml_header = _first_data_header(archive, training_nvml)
        rapl_header = _first_data_header(archive, training_rapl)
        node_counts = sorted({int(row["nodes"]) for row in metadata})
        source_records = [
            _member_record(archive, readme),
            _member_record(archive, training_metadata),
            _member_record(archive, training_nvml),
            _member_record(archive, training_rapl),
            *[_member_record(archive, name) for name in whole_facility_metadata],
        ]
    fields = {
        "per_GPU_NVML_power": {
            "available": all(f"gpu-{index}[mW]" in nvml_header for index in range(4)),
            "fields": [name for name in nvml_header if re.fullmatch(r"gpu-\d+\[mW\]", name)],
            "meaning": "per-socket instantaneous board power telemetry",
        },
        "CPU_RAPL_package_power": {
            "available": "cpu-0[W]" in rapl_header and "cpu-1[W]" in rapl_header,
            "fields": [name for name in rapl_header if name.endswith("[W]") or name.endswith("[uJ]")],
        },
        "node_level_idle_or_base_power_label": {
            "available": False,
            "reason": "No measured experiment/state label identifies a node-idle baseline; post-processing constants are not measured partial-node ground truth.",
        },
        "number_of_powered_or_active_GPUs": {
            "available": False,
            "reason": "Four telemetry channels exist per measured node, but no per-timestamp powered/active/requested GPU-count field exists.",
        },
        "per_device_GPU_utilization": {
            "available": False,
            "reason": "NVML logs contain power and temperature only, not per-device utilization or allocation occupancy.",
        },
        "scenario_or_utilization_metadata": {
            "available": True,
            "meaning": "training model/node-count/repeat and inference workload/request-rate/batch metadata; not GPU allocation occupancy",
        },
        "node_count": {
            "available": True,
            "training_values": node_counts,
            "full_node_only_experimental_design": True,
        },
        "temporal_power_telemetry": {
            "available": True,
            "raw_NVML_header": nvml_header,
            "raw_RAPL_header": rapl_header,
            "aggregated_schemas": aggregate_schema,
        },
        "direct_partial_node_or_partial_GPU_ground_truth": {
            "available": False,
            "reason": "No experiment varies active/requested GPU count within a powered node while observing host, idle-GPU and active-GPU components separately.",
        },
    }
    return {
        "artifact_id": "V17_AIDC_PARTIAL_NODE_SOURCE_AUDIT_V1",
        "status": "PASS_SOURCE_AUDIT",
        "source": {"path": str(dataset), "bytes": dataset.stat().st_size, "sha256": source_sha, "zip_member_count": len(names)},
        "README_semantics": {
            "raw_is_WattAMeter_per_GPU_socket_and_CPU_core": "per individual GPU socket and CPU core" in readme_text,
            "whole_facility_profiles_are_DIPLOEE_simulated": "simulated using NLR's Data center Infrastructure Planning" in readme_text,
        },
        "source_member_records": source_records,
        "raw_member_counts": {"NVML": len(nvml_members), "RAPL": len(rapl_members)},
        "training_metadata": {
            "run_count": len(metadata),
            "models": sorted({row["model"] for row in metadata}),
            "node_counts": node_counts,
            "GPU_allocation_count_field_present": False,
        },
        "available_fields": fields,
        "utilization_firewall": {
            "whole_facility_average_utilization_values": sorted({float(row["Average Utilization"]) for rows in whole_rows.values() for row in rows}),
            "physical_meaning": "DIPLOEE simulated whole-facility average node/system utilization scenario",
            "not_GPU_allocation_occupancy": True,
            "not_flexible_energy_share": True,
            "admitted_for_partial_node_fit": False,
        },
        **_firewall(),
    }


def _find_kestrel(raw_root: Path) -> Path:
    matches = [path for path in raw_root.rglob("esif.hpc.kestrel.job-anon.zip") if path.is_file()]
    exact = [path for path in matches if sha256_file(path) == KESTREL_SHA256]
    if not exact:
        raise FileNotFoundError("V17_EXACT_KESTREL_TRAINING_SOURCE_NOT_FOUND")
    return sorted(exact)[0]


def decompose_unmodeled_training(raw_root: Path, prior: Mapping[str, Any]) -> dict[str, Any]:
    import pandas as pd
    import pyarrow.parquet as pq

    train_start = pd.Timestamp(TRAIN_START, tz=AEST).tz_convert("UTC")
    train_end = pd.Timestamp(TRAIN_END_EXCLUSIVE, tz=AEST).tz_convert("UTC")
    source = _find_kestrel(raw_root)
    required = {
        "partition", "state_simple", "submit_time", "start_time", "end_time",
        "gpu_nodes_occupied", "gpus_requested", "shared_job_count", "nodes_shared", "jobs_shared",
    }
    groups = {name: {"jobs": 0, "GPU_hours": 0.0, "node_equivalent_hours": 0.0, "occupied_node_hours": 0.0}
              for name in ("U1_EXCLUSIVE_PARTIAL_NODE", "U2_SHARED_PARTIAL_OR_SHARED_NODE",
                           "U3_FULL_NODE_BUT_UNSUPPORTED_NODE_COUNT", "U4_OTHER_POWER_UNMODELED")}
    semantic = {"jobs": 0, "GPU_hours": 0.0, "node_equivalent_hours": 0.0, "occupied_node_hours": 0.0}
    modelable = {"jobs": 0, "GPU_hours": 0.0, "node_equivalent_hours": 0.0, "occupied_node_hours": 0.0}
    members = []
    with zipfile.ZipFile(source) as archive, tempfile.TemporaryDirectory(prefix="v17-partial-node-") as temporary:
        local = Path(temporary) / "month.parquet"
        selected = []
        for info in archive.infolist():
            match = re.search(r"year=(\d{4})/month=(\d{1,2})", info.filename.replace("\\", "/"))
            if match and info.filename.casefold().endswith(".parquet"):
                month = int(match.group(1)) * 100 + int(match.group(2))
                if 202408 <= month <= 202503:
                    selected.append((month, info))
        for month, info in sorted(selected):
            with archive.open(info) as origin, local.open("wb") as target:
                shutil.copyfileobj(origin, target)
            if not required.issubset(set(pq.read_schema(local).names)):
                raise RuntimeError("V17_KESTREL_PARTIAL_NODE_REQUIRED_SCHEMA_MISSING")
            frame = pq.read_table(local, columns=sorted(required)).to_pandas()
            members.append({"month": month, "member": info.filename, "rows": len(frame)})
            submit = pd.to_datetime(frame["submit_time"], utc=True, errors="coerce", format="mixed")
            start = pd.to_datetime(frame["start_time"], utc=True, errors="coerce", format="mixed")
            end = pd.to_datetime(frame["end_time"], utc=True, errors="coerce", format="mixed")
            nodes = pd.to_numeric(frame["gpu_nodes_occupied"], errors="coerce")
            gpus = pd.to_numeric(frame["gpus_requested"], errors="coerce")
            sharing = pd.to_numeric(frame["shared_job_count"], errors="coerce")
            valid_execution = start.notna() & end.notna() & end.gt(start) & nodes.gt(0) & gpus.gt(0)
            overlap = end.gt(train_start) & start.lt(train_end)
            queue = (start - submit).dt.total_seconds()
            valid_queue = submit.notna() & queue.ge(0) & np.isfinite(queue)
            completed = frame["state_simple"].astype(str).str.upper().eq("COMPLETED")
            semantic_mask = frame["partition"].apply(_h100) & valid_execution & overlap & valid_queue & queue.gt(600.0) & completed
            no_share = (
                (sharing.isna() | sharing.eq(0))
                & frame["nodes_shared"].apply(object_empty)
                & frame["jobs_shared"].apply(object_empty)
            )
            full_node = np.isclose(gpus, GPU_PER_NODE * nodes)
            supported_count = nodes.isin(NODE_CLASSES)
            modelable_mask = semantic_mask & full_node & supported_count & no_share
            unmodeled = semantic_mask & ~modelable_mask
            masks = {
                "U1_EXCLUSIVE_PARTIAL_NODE": unmodeled & no_share & gpus.gt(0) & gpus.lt(GPU_PER_NODE * nodes),
                "U2_SHARED_PARTIAL_OR_SHARED_NODE": unmodeled & ~no_share,
                "U3_FULL_NODE_BUT_UNSUPPORTED_NODE_COUNT": unmodeled & no_share & full_node & ~supported_count,
            }
            masks["U4_OTHER_POWER_UNMODELED"] = unmodeled & ~(
                masks["U1_EXCLUSIVE_PARTIAL_NODE"] | masks["U2_SHARED_PARTIAL_OR_SHARED_NODE"]
                | masks["U3_FULL_NODE_BUT_UNSUPPORTED_NODE_COUNT"]
            )
            clipped_start = start.where(start.ge(train_start), train_start)
            clipped_end = end.where(end.le(train_end), train_end)
            duration = ((clipped_end - clipped_start).dt.total_seconds() / 3600.0).where(semantic_mask, 0.0).fillna(0.0)

            def accumulate(target: dict[str, float], mask) -> None:
                target["jobs"] += int(mask.sum())
                target["GPU_hours"] += float((gpus.where(mask, 0.0) * duration).sum())
                target["node_equivalent_hours"] += float(((gpus.where(mask, 0.0) / GPU_PER_NODE) * duration).sum())
                target["occupied_node_hours"] += float((nodes.where(mask, 0.0) * duration).sum())

            accumulate(semantic, semantic_mask); accumulate(modelable, modelable_mask)
            for name, mask in masks.items(): accumulate(groups[name], mask)
    if len(members) != 8:
        raise RuntimeError("V17_PARTIAL_NODE_TRAINING_MONTH_AXIS_INCOMPLETE")
    prior_semantic = prior["semantic_vs_power_model_attrition"]["semantically_flexible_H100_node_equivalent_hours"]
    prior_modelable = prior["semantic_vs_power_model_attrition"]["modelable_flexible_node_hours"]
    if abs(float(semantic["node_equivalent_hours"]) - float(prior_semantic)) > 1e-6:
        raise RuntimeError("V17_PARTIAL_NODE_SEMANTIC_TOTAL_MISMATCH")
    if abs(float(modelable["node_equivalent_hours"]) - float(prior_modelable)) > 1e-6:
        raise RuntimeError("V17_PARTIAL_NODE_MODELABLE_TOTAL_MISMATCH")
    unmodeled_jobs = int(semantic["jobs"] - modelable["jobs"])
    unmodeled_nodeh = float(semantic["node_equivalent_hours"] - modelable["node_equivalent_hours"])
    if sum(int(row["jobs"]) for row in groups.values()) != unmodeled_jobs:
        raise RuntimeError("V17_PARTIAL_NODE_GROUP_JOB_PARTITION_FAIL")
    if abs(sum(float(row["node_equivalent_hours"]) for row in groups.values()) - unmodeled_nodeh) > 1e-6:
        raise RuntimeError("V17_PARTIAL_NODE_GROUP_NODEH_PARTITION_FAIL")
    rows = []
    for name, values in groups.items():
        rows.append({
            "group": name,
            **values,
            "fraction_of_semantic_flexible_jobs": float(values["jobs"] / semantic["jobs"]),
            "fraction_of_semantic_flexible_node_equivalent_hours": float(values["node_equivalent_hours"] / semantic["node_equivalent_hours"]),
            "fraction_of_currently_unmodeled_node_equivalent_hours": float(values["node_equivalent_hours"] / unmodeled_nodeh),
        })
    return {
        "artifact_id": "V17_AIDC_UNMODELED_COHORT_DECOMPOSITION_V1",
        "status": "PASS_MUTUALLY_EXCLUSIVE_TRAINING_ONLY_PARTITION",
        "source": {"path": str(source.resolve()), "sha256": sha256_file(source), "members_opened": members},
        "definitions": {
            "semantic_flexible": "H100 + valid positive training-overlap runtime + valid queue + queue>600s + COMPLETED",
            "node_equivalent_hours": "integral(gpus_requested/4) over training-clipped execution",
            "U1": "semantic unmodeled + no sharing evidence + 0<gpus_requested<4*occupied_nodes",
            "U2": "semantic unmodeled + sharing/co-residency evidence",
            "U3": "semantic unmodeled + no sharing + full-node + occupied-node count outside {1,2,4,8,16}",
            "U4": "remaining semantic power-unmodeled rows",
            "precedence": ["U1", "U2", "U3", "U4"],
        },
        "semantic_flexible": semantic,
        "current_V1_modelable": modelable,
        "currently_power_unmodeled": {"jobs": unmodeled_jobs, "node_equivalent_hours": unmodeled_nodeh},
        "groups": rows,
        "partition_checks": {
            "mutually_exclusive_by_construction": True,
            "jobs_sum_exact": True,
            "node_equivalent_hours_sum_abs_error": abs(sum(float(row["node_equivalent_hours"]) for row in groups.values()) - unmodeled_nodeh),
        },
        **_firewall(),
    }


def materialize(repo: Path, raw_root: Path, dataset: Path, output: Path) -> dict[str, Any]:
    repo = repo.resolve(); raw_root = raw_root.resolve(); output = output.resolve()
    prior_path = output / "V17_AIDC_FLEXIBLE_SCALE_ATTRITION_FORENSIC.json"
    prior = json.loads(prior_path.read_text(encoding="utf-8"))
    source_audit = audit_dataset312(dataset)
    decomposition = decompose_unmodeled_training(raw_root, prior)
    write_json(output / "V17_AIDC_PARTIAL_NODE_SOURCE_AUDIT.json", source_audit)
    write_json(output / "V17_AIDC_UNMODELED_COHORT_DECOMPOSITION.json", decomposition)
    identifiability = {
        "artifact_id": "V17_AIDC_PARTIAL_NODE_POWER_IDENTIFIABILITY_V1",
        "status": "NOT_IDENTIFIABLE_FAIL_CLOSED",
        "classification": CLASSIFICATION,
        "required_decomposition": "P_inc_node = P_host_increment + sum_g P_GPU_increment,g (or measured equivalent)",
        "evidence": {
            "per_GPU_power_available": True,
            "CPU_RAPL_available": True,
            "explicit_node_host_idle_or_increment_label_available": False,
            "active_or_requested_GPU_count_per_node_state_available": False,
            "idle_GPU_contribution_identifiable": False,
            "direct_partial_GPU_ground_truth_available": False,
            "full_node_only_training_node_counts": source_audit["training_metadata"]["node_counts"],
        },
        "reason": "Per-socket power is observed only without an authoritative active/requested-GPU state or measured host/idle-GPU counterfactual. Full-node fits cannot validate partial-node allocation.",
        "candidate_model_fit_calls": 0,
        "partial_node_validation_claimed": False,
        "scientific_boundary_expansion_authorized": False,
        "source_audit_sha256": sha256_file(output / "V17_AIDC_PARTIAL_NODE_SOURCE_AUDIT.json"),
        "cohort_decomposition_sha256": sha256_file(output / "V17_AIDC_UNMODELED_COHORT_DECOMPOSITION.json"),
        **_firewall(),
    }
    write_json(output / "V17_AIDC_PARTIAL_NODE_POWER_IDENTIFIABILITY.json", identifiability)
    validation = {
        "artifact_id": "V17_AIDC_POWER_MODEL_V2_VALIDATION_V1",
        "status": "REJECTED_NOT_AUTHORIZED",
        "classification": CLASSIFICATION,
        "reason": "No direct partial-node ground truth; fitting and held-out partial-node validation are not scientifically identifiable.",
        "fit_rows": 0,
        "validation_rows": 0,
        "MAE": None, "RMSE": None, "bias": None, "NRMSE": None,
        "full_node_kappa_replacement": False,
        "V1_retained_byte_identically": True,
        **_firewall(),
    }
    contract = {
        "artifact_id": "V17_AIDC_POWER_MODEL_V2_CONTRACT_V1",
        "status": "REJECTED_NOT_AUTHORIZED",
        "classification": CLASSIFICATION,
        "authority_minted": False,
        "support_set": [],
        "reason": "B10 classification A was not achieved; V17_AIDC_POWER_MODEL_V2 may not be minted.",
        "active_scientific_power_model": "V17_AIDC_POWER_MODEL_V1_FROZEN_KAPPA_BOUNDARY",
        **_firewall(),
    }
    semantic = decomposition["semantic_flexible"]
    v1 = decomposition["current_V1_modelable"]
    boundary = {
        "artifact_id": "V17_AIDC_POWER_V1_V2_BOUNDARY_COMPARISON_V1",
        "status": "V2_REJECTED_V1_RETAINED",
        "classification": CLASSIFICATION,
        "semantic_flexible_jobs": semantic["jobs"],
        "semantic_flexible_node_equivalent_hours": semantic["node_equivalent_hours"],
        "V1_modelable_jobs": v1["jobs"],
        "V1_modelable_node_equivalent_hours": v1["node_equivalent_hours"],
        "V1_modelable_job_fraction_of_semantic": float(v1["jobs"] / semantic["jobs"]),
        "V1_modelable_node_hour_fraction_of_semantic": float(v1["node_equivalent_hours"] / semantic["node_equivalent_hours"]),
        "U1_potential_only_not_recoverable_without_authority": next(row for row in decomposition["groups"] if row["group"] == "U1_EXCLUSIVE_PARTIAL_NODE"),
        "V2_modelable_jobs": v1["jobs"],
        "V2_modelable_node_equivalent_hours": v1["node_equivalent_hours"],
        "V2_incremental_recovered_jobs": 0,
        "V2_incremental_recovered_node_equivalent_hours": 0.0,
        "V2_scientific_runs": 0,
        "active_boundary": "V1",
        **_firewall(),
    }
    for name, payload in (
        ("V17_AIDC_POWER_MODEL_V2_VALIDATION.json", validation),
        ("V17_AIDC_POWER_MODEL_V2_CONTRACT.json", contract),
        ("V17_AIDC_POWER_V1_V2_BOUNDARY_COMPARISON.json", boundary),
    ):
        write_json(output / name, payload)
    return {
        "status": "PASS_FAIL_CLOSED_NO_V2",
        "classification": CLASSIFICATION,
        "source_audit": source_audit,
        "decomposition": decomposition,
        "identifiability": identifiability,
        "validation": validation,
        "contract": contract,
        "boundary": boundary,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--raw-root", type=Path, default=DEFAULT_RAW_ROOT)
    parser.add_argument("--dataset312", type=Path, default=DATASET312_DEFAULT)
    parser.add_argument("--output", type=Path, default=Path("dayahead/artifacts/v17_candidate"))
    args = parser.parse_args(argv)
    result = materialize(args.repo, args.raw_root, args.dataset312, args.output)
    print(json.dumps({"status": result["status"], "classification": result["classification"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
