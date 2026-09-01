"""V17 V3R1 Zenodo inventory and Kestrel semantic-bridge audit.

This phase deliberately ends before fitting.  It tests whether the externally
measured sharing states can be constructed from Kestrel's causal observables.
"""

from __future__ import annotations

import argparse
import collections
import csv
import io
import json
import math
import re
import shutil
import tarfile
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from .aidc_ml_data import AEST, NODE_CLASSES, TRAIN_START
from .aidc_power_response import KAPPA_KW_PER_ACTIVE_H100_NODE
from .authority import sha256_file as authority_sha256
from .reproduce_nlr_authority import object_empty
from .v17_external_h100_identifiability import (
    GPU_PER_NODE,
    KESTREL_SHA256,
    TRAIN_END_EXCLUSIVE,
    _as_sequence,
    _h100,
    _training_members,
    audit_kestrel_u2,
)
from .v17_v3r1_zenodo import (
    ZENODO_RELATIVE,
    ZENODO_SHA256,
    sha256_bytes,
    tar_manifest,
    write_json,
    zero_counters,
)


PRIMARY_CLASSIFICATION = "V17_AIDC_POWER_V3R1_E_SEMANTICALLY_INCOMPATIBLE"
U1_CLASSIFICATION = "MARGINAL_POWER_NOT_IDENTIFIABLE"
U2_CLASSIFICATION = "SEMANTICALLY_INCOMPATIBLE"
U3_CLASSIFICATION = "MARGINAL_POWER_NOT_IDENTIFIABLE"


def _hardware_from_name(name: str) -> dict[str, Any]:
    lower = name.casefold()
    if "h100" in lower and "ovh" in lower:
        return {"GPU": "H100-PCIE-80GB", "form_factor": "PCIe", "power_cap_W": 350, "GPUs_per_node": 1}
    if "h100" in lower and "muva" in lower:
        return {"GPU": "H100-NVL-94GB", "form_factor": "NVL", "power_cap_W": 400, "GPUs_per_node": 2}
    if "a100" in lower and "chuc" in lower:
        return {"GPU": "A100-SXM4-40GB", "form_factor": "SXM4", "power_cap_W": 400, "GPUs_per_node": 4}
    if "a100" in lower and "grouille" in lower:
        return {"GPU": "A100-PCIE-40GB", "form_factor": "PCIe", "power_cap_W": 250, "GPUs_per_node": 2 if "2x" in lower else 4}
    if "a100" in lower and "ovh" in lower:
        return {"GPU": "A100-PCIE-80GB", "form_factor": "PCIe", "power_cap_W": 300, "GPUs_per_node": 1}
    if "a100" in lower and "sirius" in lower:
        return {"GPU": "A100", "form_factor": "SOURCE_NOT_EXPLICIT", "power_cap_W": None, "GPUs_per_node": 8}
    if "p100" in lower:
        return {"GPU": "P100", "form_factor": "SOURCE_NOT_EXPLICIT", "power_cap_W": None, "GPUs_per_node": 2}
    if "v100" in lower:
        return {"GPU": "V100", "form_factor": "SOURCE_NOT_EXPLICIT", "power_cap_W": None, "GPUs_per_node": 2}
    return {"GPU": "UNKNOWN", "form_factor": "UNKNOWN", "power_cap_W": None, "GPUs_per_node": None}


def _family_from_name(name: str) -> str:
    lower = name.casefold()
    if "timeslice" in lower:
        return "TIME_SLICING_CONCURRENT_WORKLOAD"
    if "migbench" in lower or re.search(r"(^|-)mig-", lower):
        return "MIG_CONCURRENT_WORKLOAD"
    if "passthrough" in lower:
        return "MULTI_GPU_CONCURRENT_WORKLOAD"
    hardware = _hardware_from_name(name)
    if lower.startswith(tuple(str(day) for day in range(10))) and "-bench-" in lower:
        return "FULL_GPU_SINGLE_WORKLOAD" if hardware["GPUs_per_node"] == 1 else "MULTI_GPU_CONCURRENT_WORKLOAD"
    return "OTHER"


def _channels(metrics: set[str]) -> list[str]:
    channels: list[str] = []
    if any(item.startswith("DCGM_") for item in metrics):
        channels.append("DCGM")
    if any(item.startswith("SMI_") for item in metrics):
        channels.append("NVML_NVIDIA_SMI")
    if any(item.startswith("IPMI_") for item in metrics):
        channels.append("IPMI_TEMPERATURE_ONLY")
    if any(item.startswith("CPU_") for item in metrics):
        channels.append("PROC_STAT_CPU_UTILIZATION_ONLY")
    return channels


def _parse_telemetry_member(archive: tarfile.TarFile, member: tarfile.TarInfo, member_sha: str) -> dict[str, Any]:
    stream = archive.extractfile(member)
    if stream is None:
        raise RuntimeError(f"V17_V3R1_TELEMETRY_MEMBER_UNREADABLE:{member.name}")
    reader = csv.reader(io.TextIOWrapper(stream, encoding="utf-8-sig", errors="replace", newline=""))
    header = next(reader)
    if header != ["timestamp", "domain", "metric", "measure"]:
        raise RuntimeError(f"V17_V3R1_TELEMETRY_SCHEMA_MISMATCH:{member.name}")
    metrics: set[str] = set()
    domains: set[str] = set()
    contexts: set[str] = set()
    row_count = 0
    timestamp_resets = 0
    previous: float | None = None
    for row in reader:
        if len(row) != 4:
            continue
        timestamp, domain, metric, measure = row
        row_count += 1
        domains.add(domain)
        metrics.add(metric)
        if metric == "CONST_context":
            contexts.add(measure)
        try:
            current = float(timestamp)
        except ValueError:
            continue
        if previous is not None and current < previous:
            timestamp_resets += 1
        previous = current
    name = Path(member.name).name
    channels = _channels(metrics)
    return {
        "path": member.name,
        "bytes": member.size,
        "sha256": member_sha,
        "row_count": row_count,
        "schema": header,
        "experiment_family": _family_from_name(name),
        "hardware": _hardware_from_name(name),
        "measurement_provenance": "MEASURED_RAW_TELEMETRY",
        "measurement_channels": channels,
        "device_power_available": "DCGM" in channels or "NVML_NVIDIA_SMI" in channels,
        "node_or_wall_power_available": False,
        "CPU_package_power_available": False,
        "domains": sorted(domains),
        "metrics": sorted(metrics),
        "contexts": sorted(contexts),
        "timestamp_reset_count": timestamp_resets,
    }


def inventory_zenodo(zenodo: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    if authority_sha256(zenodo) != ZENODO_SHA256:
        raise RuntimeError("V17_V3R1_ZENODO_SOURCE_SHA_MISMATCH")
    manifest = tar_manifest(zenodo)
    hashes = {row["path"]: row["sha256"] for row in manifest["files"]}
    telemetry: list[dict[str, Any]] = []
    benchmark_results: list[dict[str, Any]] = []
    figure_outputs: list[dict[str, Any]] = []
    config_only: list[dict[str, Any]] = []
    source_before = (zenodo.stat().st_size, zenodo.stat().st_mtime_ns)
    with tarfile.open(zenodo, "r:gz") as archive:
        for member in archive.getmembers():
            if not member.isfile():
                continue
            if "/data/" in member.name and member.name.endswith(".csv"):
                telemetry.append(_parse_telemetry_member(archive, member, hashes[member.name]))
            elif "/bench-res/" in member.name and member.name.endswith(".csv"):
                stream = archive.extractfile(member)
                header = stream.readline().decode("utf-8-sig", errors="replace").strip() if stream else ""
                benchmark_results.append({
                    "path": member.name,
                    "bytes": member.size,
                    "sha256": hashes[member.name],
                    "header": header,
                    "measurement_provenance": "MEASURED_AGGREGATED_RESULT",
                })
            elif "/figures/" in member.name and member.name.endswith(".pdf"):
                figure_outputs.append({
                    "path": member.name,
                    "bytes": member.size,
                    "sha256": hashes[member.name],
                    "measurement_provenance": "FIGURE_DERIVED_DATA",
                })
            elif "/experiments/" in member.name or "/src/" in member.name:
                config_only.append({
                    "path": member.name,
                    "bytes": member.size,
                    "sha256": hashes[member.name],
                    "measurement_provenance": "CONFIG_ONLY",
                })
    if source_before != (zenodo.stat().st_size, zenodo.stat().st_mtime_ns):
        raise RuntimeError("V17_V3R1_EXTERNAL_SOURCE_MUTATION_DETECTED")

    family_counts = collections.Counter(row["experiment_family"] for row in telemetry)
    family_bytes = collections.Counter()
    family_rows = collections.Counter()
    for row in telemetry:
        family_bytes[row["experiment_family"]] += row["bytes"]
        family_rows[row["experiment_family"]] += row["row_count"]
    required_families = [
        "FULL_GPU_SINGLE_WORKLOAD", "MIG_SINGLE_WORKLOAD", "MIG_CONCURRENT_WORKLOAD",
        "TIME_SLICING_SINGLE_WORKLOAD", "TIME_SLICING_CONCURRENT_WORKLOAD",
        "MULTI_GPU_CONCURRENT_WORKLOAD", "NODE_LEVEL_SHARED_WORKLOAD", "OTHER",
    ]
    families = [
        {
            "family": name,
            "file_count": int(family_counts[name]),
            "uncompressed_bytes": int(family_bytes[name]),
            "row_count": int(family_rows[name]),
        }
        for name in required_families
    ]
    h100 = [row for row in telemetry if str(row["hardware"]["GPU"]).startswith("H100")]
    inventory = {
        "artifact_id": "V17_EUROSYS_ZENODO_RAW_DATA_INVENTORY_V1",
        "status": "PASS_COMPLETE_READ_ONLY_RAW_FAMILY_INVENTORY",
        "source_path": str(zenodo.resolve()),
        "source_sha256": ZENODO_SHA256,
        "source_recursive_manifest_sha256": manifest["recursive_content_manifest_sha256"],
        "telemetry_file_count": len(telemetry),
        "telemetry_row_count": sum(row["row_count"] for row in telemetry),
        "H100_telemetry_file_count": len(h100),
        "benchmark_result_file_count": len(benchmark_results),
        "families": families,
        "telemetry": telemetry,
        "benchmark_results": benchmark_results,
        "raw_root_mutations": 0,
        **zero_counters(),
    }
    provenance = {
        "artifact_id": "V17_EUROSYS_ZENODO_MEASUREMENT_PROVENANCE_V1",
        "status": "PASS_MEASUREMENT_BOUNDARIES_EXPLICIT",
        "class_counts": {
            "MEASURED_RAW_TELEMETRY": len(telemetry),
            "MEASURED_AGGREGATED_RESULT": len(benchmark_results),
            "FIGURE_DERIVED_DATA": len(figure_outputs),
            "SYNTHETIC_OR_GENERATED": 0,
            "CONFIG_ONLY": len(config_only),
        },
        "measured_channels": {
            "DCGM": "per-device GPU telemetry including DCGM_FI_DEV_POWER_USAGE where present",
            "NVML_NVIDIA_SMI": "per-device board power.draw and utilization",
            "IPMI_BMC": "temperature sensors only; no IPMI/BMC node-power channel is collected by the supplied monitor",
            "CPU": "/proc/stat utilization only; no RAPL/package power",
            "wall_power": "NOT_AVAILABLE",
        },
        "power_boundaries": {
            "GPU_device_board_power": True,
            "node_aggregate_power": False,
            "CPU_package_power": False,
            "wall_power": False,
            "job_attributed_power": False,
        },
        "telemetry_records": [
            {
                "path": row["path"], "sha256": row["sha256"],
                "provenance": row["measurement_provenance"],
                "channels": row["measurement_channels"],
                "device_power_available": row["device_power_available"],
            }
            for row in telemetry
        ],
        "benchmark_records": benchmark_results,
        "figure_records": figure_outputs,
        "config_record_count": len(config_only),
        "source_immutable": True,
        **zero_counters(),
    }
    transfer = {
        "artifact_id": "V17_V3R1_H100_HARDWARE_TRANSFER_MATRIX_V1",
        "status": "PASS_NO_DIRECT_ABSOLUTE_POWER_TRANSFER",
        "platforms": [
            {
                "source": "Dataset312 / Kestrel V1",
                "GPU": "NVIDIA H100 exact SKU/form factor not encoded",
                "GPUs_per_node": 4,
                "power_cap_W": "NOT_ENCODED",
                "power_boundary": "NVML GPU board power + two-socket RAPL CPU package power, frozen idle subtraction",
                "role": "ABSOLUTE_KAPPA_AUTHORITY",
            },
            {
                "source": "EuroSys Zenodo OVH",
                "GPU": "H100-PCIE-80GB", "GPUs_per_node": 1, "power_cap_W": 350,
                "power_boundary": "per-device SMI/DCGM board power; IPMI temperature only",
                "relationship_to_Dataset312": "DIMENSIONLESS_RESPONSE_TRANSFER_ONLY",
            },
            {
                "source": "EuroSys Zenodo MUVA",
                "GPU": "H100-NVL-94GB", "GPUs_per_node": 2, "power_cap_W": 400,
                "power_boundary": "per-device SMI/DCGM board power; IPMI temperature only",
                "relationship_to_Dataset312": "DIMENSIONLESS_RESPONSE_TRANSFER_ONLY",
            },
            {
                "source": "Scientific Data H100",
                "GPU": "H100-SXM-80GB", "GPUs_per_node": 8, "power_cap_W": 700,
                "power_boundary": "per-device pynvml board power; CPU/node power absent",
                "relationship_to_Dataset312": "DIMENSIONLESS_RESPONSE_TRANSFER_ONLY",
            },
        ],
        "direct_absolute_external_kW_transfer_authorized": False,
        "only_candidate_equation": "P_V3R1(state) = kappa_V1(reference) * g_Zenodo(state), with g_Zenodo(full-node reference)=1",
        "candidate_equation_authorized_for_fit": False,
        "reason": "The causal state bridge fails before a dimensionless response can be transferred to Kestrel cohorts.",
        "Dataset312_kappa_changes": 0,
        **zero_counters(),
    }
    return inventory, provenance, transfer


def _u2_aggregate_coverage(kestrel: Path) -> dict[str, Any]:
    import pandas as pd
    import pyarrow.parquet as pq

    if authority_sha256(kestrel) != KESTREL_SHA256:
        raise RuntimeError("V17_V3R1_KESTREL_SOURCE_SHA_MISMATCH")
    train_start = pd.Timestamp(TRAIN_START, tz=AEST).tz_convert("UTC")
    train_end = pd.Timestamp(TRAIN_END_EXCLUSIVE, tz=AEST).tz_convert("UTC")
    columns = [
        "job_id", "partition", "state_simple", "submit_time", "start_time", "end_time",
        "gpu_nodes_occupied", "gpus_requested", "shared_job_count", "nodes_shared",
        "jobs_shared", "nodelist",
    ]
    # job_id is not a row-unique key for all Slurm array records.  Preserve
    # every U2 row independently; only peer lookup uses the numeric ID and
    # therefore treats multiple matching rows as ambiguous.
    targets: list[dict[str, Any]] = []
    referenced: set[int] = set()
    with zipfile.ZipFile(kestrel) as archive, tempfile.TemporaryDirectory(prefix="v17-v3r1-u2-") as temporary:
        local = Path(temporary) / "month.parquet"
        members = _training_members(archive)
        for _, info in members:
            with archive.open(info) as origin, local.open("wb") as target:
                shutil.copyfileobj(origin, target)
            frame = pq.read_table(local, columns=columns).to_pandas()
            submit = pd.to_datetime(frame["submit_time"], utc=True, errors="coerce", format="mixed")
            start = pd.to_datetime(frame["start_time"], utc=True, errors="coerce", format="mixed")
            end = pd.to_datetime(frame["end_time"], utc=True, errors="coerce", format="mixed")
            nodes = pd.to_numeric(frame["gpu_nodes_occupied"], errors="coerce")
            gpus = pd.to_numeric(frame["gpus_requested"], errors="coerce")
            sharing = pd.to_numeric(frame["shared_job_count"], errors="coerce")
            valid = start.notna() & end.notna() & end.gt(start) & nodes.gt(0) & gpus.gt(0)
            overlap = end.gt(train_start) & start.lt(train_end)
            queue = (start - submit).dt.total_seconds()
            semantic = (
                frame["partition"].apply(_h100) & valid & overlap & submit.notna()
                & queue.ge(0) & np.isfinite(queue) & queue.gt(600.0)
                & frame["state_simple"].astype(str).str.upper().eq("COMPLETED")
            )
            no_share = (
                (sharing.isna() | sharing.eq(0))
                & frame["nodes_shared"].apply(object_empty)
                & frame["jobs_shared"].apply(object_empty)
            )
            full = np.isclose(gpus, GPU_PER_NODE * nodes)
            modelable = semantic & full & nodes.isin(NODE_CLASSES) & no_share
            u2 = semantic & ~modelable & ~no_share
            for index in frame.index[u2]:
                job_id = int(frame.at[index, "job_id"])
                clipped_start = max(start.at[index], train_start)
                clipped_end = min(end.at[index], train_end)
                jobs = [int(value) for value in _as_sequence(frame.at[index, "jobs_shared"]) if str(value).isdigit()]
                row = {
                    "job_id": job_id,
                    "start": clipped_start, "end": clipped_end,
                    "gpus": float(gpus.at[index]), "nodes": float(nodes.at[index]),
                    "nodelist": _as_sequence(frame.at[index, "nodelist"]),
                    "nodes_shared": _as_sequence(frame.at[index, "nodes_shared"]),
                    "jobs_shared": jobs,
                    "shared_job_count": int(float(sharing.at[index])),
                    "node_equivalent_hours": float(gpus.at[index] / GPU_PER_NODE * ((clipped_end - clipped_start).total_seconds() / 3600.0)),
                }
                targets.append(row)
                referenced.update(jobs)

        resolved_rows: dict[int, list[dict[str, Any]]] = collections.defaultdict(list)
        resolve_ids = referenced | {row["job_id"] for row in targets}
        resolve_columns = ["job_id", "start_time", "end_time", "gpus_requested", "gpu_nodes_occupied", "nodelist"]
        for _, info in members:
            with archive.open(info) as origin, local.open("wb") as target:
                shutil.copyfileobj(origin, target)
            frame = pq.read_table(local, columns=resolve_columns).to_pandas()
            frame = frame[frame["job_id"].isin(resolve_ids)]
            for _, row in frame.iterrows():
                resolved_rows[int(row["job_id"])].append({
                    "start": pd.to_datetime(row["start_time"], utc=True, errors="coerce"),
                    "end": pd.to_datetime(row["end_time"], utc=True, errors="coerce"),
                    "gpus": float(row["gpus_requested"]),
                    "nodes": float(row["gpu_nodes_occupied"]),
                    "nodelist": _as_sequence(row["nodelist"]),
                })

    total_nodeh = sum(row["node_equivalent_hours"] for row in targets)
    complete_jobs = 0
    complete_nodeh = 0.0
    separate_gpu_feasible_jobs = 0
    separate_gpu_feasible_nodeh = 0.0
    max_aggregate_requested = 0.0
    failure_counts: collections.Counter[str] = collections.Counter()
    for target in targets:
        if target["nodes"] != 1 or len(target["nodelist"]) != 1:
            failure_counts["target_not_single_physical_node"] += 1
            continue
        node = target["nodelist"][0]
        if len(target["nodes_shared"]) != 1 or target["nodes_shared"][0] != node:
            failure_counts["shared_node_identity_not_unique_or_mismatched"] += 1
            continue
        if not target["jobs_shared"] or len(target["jobs_shared"]) != target["shared_job_count"]:
            failure_counts["shared_job_list_not_complete_by_count"] += 1
            continue
        peers: list[dict[str, Any]] = []
        failed = False
        for job_id in target["jobs_shared"]:
            candidates = resolved_rows.get(job_id, [])
            if len(candidates) != 1:
                failure_counts["peer_job_unresolved_or_ambiguous"] += 1
                failed = True
                break
            peer = candidates[0]
            if (
                peer["nodes"] != 1 or len(peer["nodelist"]) != 1 or peer["nodelist"][0] != node
                or pd.isna(peer["start"]) or pd.isna(peer["end"]) or peer["end"] <= peer["start"]
                or not math.isfinite(peer["gpus"]) or peer["gpus"] <= 0
            ):
                failure_counts["peer_state_not_single_node_reconstructable"] += 1
                failed = True
                break
            peers.append(peer)
        if failed:
            continue
        complete_jobs += 1
        complete_nodeh += target["node_equivalent_hours"]
        boundaries = {target["start"], target["end"]}
        for peer in peers:
            boundaries.add(max(peer["start"], target["start"]))
            boundaries.add(min(peer["end"], target["end"]))
        ordered = sorted(value for value in boundaries if target["start"] <= value <= target["end"])
        max_requested = target["gpus"]
        for left, right in zip(ordered, ordered[1:]):
            if right <= left:
                continue
            middle = left + (right - left) / 2
            aggregate = target["gpus"] + sum(peer["gpus"] for peer in peers if peer["start"] <= middle < peer["end"])
            max_requested = max(max_requested, aggregate)
        max_aggregate_requested = max(max_aggregate_requested, max_requested)
        if max_requested <= GPU_PER_NODE + 1e-9:
            separate_gpu_feasible_jobs += 1
            separate_gpu_feasible_nodeh += target["node_equivalent_hours"]
        else:
            failure_counts["aggregate_requested_GPUs_exceed_4"] += 1

    return {
        "artifact_id": "V17_V3R1_U2_AGGREGATE_STATE_COVERAGE_V1",
        "status": "PASS_EX_POST_COVERAGE_AUDIT_NOT_D1_ACTUATOR_AUTHORITY",
        "U2_jobs": len(targets),
        "U2_node_equivalent_hours": total_nodeh,
        "fully_reconstructable_ex_post_jobs": complete_jobs,
        "fully_reconstructable_ex_post_node_equivalent_hours": complete_nodeh,
        "fully_reconstructable_ex_post_job_fraction": complete_jobs / max(len(targets), 1),
        "fully_reconstructable_ex_post_node_hour_fraction": complete_nodeh / max(total_nodeh, 1e-12),
        "separate_GPU_capacity_consistent_jobs": separate_gpu_feasible_jobs,
        "separate_GPU_capacity_consistent_node_equivalent_hours": separate_gpu_feasible_nodeh,
        "max_reconstructed_aggregate_requested_GPUs": max_aggregate_requested,
        "failure_counts": dict(failure_counts),
        "reconstruction_rule": "single target node; one matching nodes_shared value; jobs_shared count identity; every peer uniquely resolved to the same single node with valid interval and requested GPUs",
        "exhaustiveness_basis": "source-derived jobs_shared list and shared_job_count identity; no per-device placement is inferred",
        "per_device_GPU_placement_reconstructed": False,
        "same_GPU_vs_separate_GPU_sharing_reconstructed": False,
        "MIG_state_reconstructed": False,
        "time_slice_fraction_reconstructed": False,
        "D1_future_physical_node_assignment_available": False,
        "active_point_model_support_node_hours": 0.0,
        **zero_counters(),
    }


def materialize(repo: Path, external_root: Path, kestrel: Path, output: Path) -> dict[str, Any]:
    output = output.resolve()
    zenodo = external_root.resolve() / ZENODO_RELATIVE
    prior = json.loads((output / "V17_AIDC_UNMODELED_COHORT_DECOMPOSITION.json").read_text(encoding="utf-8"))
    cohort_old, u2_old = audit_kestrel_u2(kestrel, prior)
    inventory, provenance, transfer = inventory_zenodo(zenodo)
    coverage = _u2_aggregate_coverage(kestrel)

    groups = {row["group"]: row for row in cohort_old["groups"]}
    u2_group = groups["U2_SHARED_PARTIAL_OR_SHARED_NODE"]
    reproduction = {
        "artifact_id": "V17_V3R1_KESTREL_U2_REPRODUCTION_V1",
        "status": "PASS_EXACT_TRAINING_ONLY_REPRODUCTION",
        "source_path": str(kestrel.resolve()),
        "source_sha256": KESTREL_SHA256,
        "training_window": [TRAIN_START, "2025-03-31"],
        "semantic_flexible": cohort_old["semantic_flexible"],
        "V1_modelable": cohort_old["V1_modelable"],
        "U1": groups["U1_EXCLUSIVE_PARTIAL_NODE"],
        "U2": u2_group,
        "U3": groups["U3_FULL_NODE_BUT_UNSUPPORTED_NODE_COUNT"],
        "U4": groups["U4_OTHER_POWER_UNMODELED"],
        "prior_reproduction_identity": cohort_old["reproduction_identity"],
        "U2_observables": u2_old["observables"],
        "training_members_opened": cohort_old["source"]["members_opened"],
        **zero_counters(),
    }
    bridge_rows = [
        {
            "external_experiment": "H100 MIG GI/CI single or concurrent partitions",
            "external_state": ["MIG profile", "GI/CI count", "MIG UUID", "workload", "device power"],
            "Kestrel_bridge": "REQUIRES_UNOBSERVED_STATE",
            "reason": "Kestrel U2 has no MIG state, slice profile, MIG instance, or per-device placement.",
        },
        {
            "external_experiment": "P100 time-slicing concurrent containers",
            "external_state": ["oversubscription policy", "instances per GPU", "per-device power"],
            "Kestrel_bridge": "REQUIRES_UNOBSERVED_STATE",
            "reason": "Kestrel U2 has no time-slicing mechanism/fraction and the source GPU is P100, not H100.",
        },
        {
            "external_experiment": "H100 full-GPU one/two-GPU benchmark",
            "external_state": ["physical active GPU count", "workload", "device power"],
            "Kestrel_bridge": "DERIVABLE_FROM_KESTREL",
            "reason": "Requested aggregate GPU count is observable, but the runs do not identify a 4-GPU Kestrel co-resident marginal or per-job attribution.",
        },
        {
            "external_experiment": "A100 multi-GPU pass-through active vector",
            "external_state": ["per-GPU active vector", "device power", "IPMI temperature"],
            "Kestrel_bridge": "REQUIRES_UNOBSERVED_STATE",
            "reason": "Per-device placement is absent in Kestrel and the hardware is A100.",
        },
        {
            "external_experiment": "node-level shared aggregate power",
            "external_state": [],
            "Kestrel_bridge": "REQUIRES_UNOBSERVED_STATE",
            "reason": "No Zenodo node/wall-power measurement exists; IPMI collection is temperature-only.",
        },
    ]
    bridge = {
        "artifact_id": "V17_V3R1_EXTERNAL_TO_KESTREL_SEMANTIC_BRIDGE_V1",
        "status": "FAIL_CLOSED_U2_EXTERNAL_SHARING_STATE_NOT_OBSERVABLE_IN_KESTREL",
        "U2_meaning": "physical same-node co-residency derived by NLR from Slurm allocation overlap",
        "U2_known": [
            "physical node ID", "co-resident job IDs", "job start/end intervals",
            "aggregate job GPU request", "occupied-node count",
        ],
        "U2_unknown": [
            "per-device GPU placement", "same-GPU vs separate-GPU sharing", "MIG state",
            "time-slicing state/fraction", "GPU utilization", "D-1 future physical node assignment",
        ],
        "experiment_bridges": bridge_rows,
        "job_attributed_power": {
            "source_backed": False,
            "reason": "Device traces are not labeled by Kestrel job and Kestrel lacks the external sharing intervention state.",
        },
        "aggregate_shared_node_power": {
            "source_backed": False,
            "reason": "The artifact has GPU board power but no node/wall power; Kestrel future placement is unavailable at D-1.",
        },
        "marginal_power_of_schedulable_work": {
            "identifiable": False,
            "reason": "Removing a Kestrel U2 job does not map causally to an observed Zenodo MIG/time-slice/device state transition.",
        },
        "U2_classification": U2_CLASSIFICATION,
        "rowwise_external_to_Kestrel_merges": 0,
        **zero_counters(),
    }
    split = {
        "artifact_id": "V17_V3R1_EXTERNAL_SPLIT_CONTRACT_V1",
        "status": "FROZEN_BEFORE_ANY_FIT_NOT_ACTIVATED",
        "unit": "complete source experiment run / telemetry CSV and complete workload-sharing configuration",
        "grouping_axes": ["GPU SKU", "host platform", "experiment family", "workload", "sharing configuration", "run identity"],
        "random_row_split_allowed": False,
        "temporal_samples_from_same_run_may_cross_splits": False,
        "deterministic_assignment": "SHA256(canonical group key + V17_V3R1_SPLIT_20260831); complete groups only",
        "holdout_rule": "20 percent by deterministic group hash within each identifiable hardware/family stratum; fallback last canonical complete run",
        "fit_calls": 0,
        "held_out_error_reads": 0,
        **zero_counters(),
    }
    acceptance = {
        "artifact_id": "V17_AIDC_POWER_V3R1_ACCEPTANCE_CONTRACT_V1",
        "status": "FAIL_CLOSED_NO_DEFENSIBLE_NUMERICAL_GATE_AFTER_SEMANTIC_FAILURE",
        "created_before_fit": True,
        "created_before_held_out_error_reads": True,
        "required_metrics_if_candidate_exists": [
            "MAE", "RMSE", "bias", "NRMSE", "absolute relative-error distribution",
            "P95 error", "worst-case error", "marginal-power MAE", "marginal-power bias",
        ],
        "threshold_sources_considered": {
            "Dataset312_V1": "deterministic kappa reproduction has no held-out predictive error envelope",
            "Zenodo_repeatability": "no source-documented measurement uncertainty bound for a Kestrel-equivalent state",
            "documented_noise_bound": "not provided",
        },
        "numerical_acceptance_threshold": None,
        "reason": "No Kestrel-equivalent causal state reaches the fit gate; inventing a threshold after source inspection is prohibited.",
        "outcome_seeking_thresholds": 0,
        "fit_calls": 0,
        "held_out_error_reads": 0,
        **zero_counters(),
    }
    semantic = cohort_old["semantic_flexible"]
    v1 = cohort_old["V1_modelable"]
    identifiability = {
        "artifact_id": "V17_AIDC_POWER_V3R1_COHORT_IDENTIFIABILITY_V1",
        "status": PRIMARY_CLASSIFICATION,
        "classifications": {"U1": U1_CLASSIFICATION, "U2": U2_CLASSIFICATION, "U3": U3_CLASSIFICATION},
        "U1": {
            **groups["U1_EXCLUSIVE_PARTIAL_NODE"],
            "recoverable_node_equivalent_hours": 0.0,
            "reason": "Requested GPU fraction is observable but Zenodo lacks a compatible 4-GPU physical-allocation marginal and node boundary.",
        },
        "U2": {
            **u2_group,
            "recoverable_node_equivalent_hours": 0.0,
            "reason": "MIG/time-slicing/device placement state is unobserved; board-power data cannot identify a Kestrel shared-job marginal.",
        },
        "U3": {
            **groups["U3_FULL_NODE_BUT_UNSUPPORTED_NODE_COUNT"],
            "recoverable_node_equivalent_hours": 0.0,
            "reason": "Zenodo does not validate Dataset312 node-count extrapolation beyond frozen V1 classes.",
        },
        "partial_U2_supported_predicate": None,
        "partial_U2_remainder_predicate": "all U2",
        "disjoint_support_validation": True,
        "point_model_cohorts": [],
        "bound_only_cohorts": [],
        **zero_counters(),
    }
    coverage_compare = {
        "artifact_id": "V17_AIDC_POWER_V1_V3R1_COVERAGE_COMPARISON_V1",
        "status": "PASS_V3R1_REJECTED_ACTIVE_COVERAGE_UNCHANGED",
        "semantic_flexible": semantic,
        "V1_modelable": v1,
        "V3R1_modelable": v1,
        "newly_recovered": {
            "U1": {"jobs": 0, "node_equivalent_hours": 0.0},
            "U2": {"jobs": 0, "node_equivalent_hours": 0.0},
            "U3": {"jobs": 0, "node_equivalent_hours": 0.0},
        },
        "V1_coverage_fraction": {
            "jobs": v1["jobs"] / semantic["jobs"],
            "node_equivalent_hours": v1["node_equivalent_hours"] / semantic["node_equivalent_hours"],
        },
        "V3R1_coverage_fraction": {
            "jobs": v1["jobs"] / semantic["jobs"],
            "node_equivalent_hours": v1["node_equivalent_hours"] / semantic["node_equivalent_hours"],
        },
        "incremental_coverage_fraction": {"jobs": 0.0, "node_equivalent_hours": 0.0},
        "U2_ex_post_aggregate_state_coverage_is_not_active_power_support": {
            "jobs": coverage["fully_reconstructable_ex_post_jobs"],
            "node_equivalent_hours": coverage["fully_reconstructable_ex_post_node_equivalent_hours"],
        },
        **zero_counters(),
    }
    contract = {
        "artifact_id": "V17_AIDC_POWER_MODEL_V3R1_CONTRACT_REJECTION_RECORD_V1",
        "status": "NOT_MINTED",
        "requested_authority": "V17_AIDC_POWER_MODEL_V3R1_ZENODO_SHARED_AUTHORITY",
        "authority": None,
        "primary_classification": PRIMARY_CLASSIFICATION,
        "active_boundary": "V17_AIDC_POWER_MODEL_V1_FROZEN_KAPPA_BOUNDARY",
        "candidate_equation_not_authorized": "P_V3R1(state)=kappa_V1(reference)*g_Zenodo(state)",
        "V1_kappa": {str(key): value for key, value in KAPPA_KW_PER_ACTIVE_H100_NODE.items()},
        "V1_kappa_changes": 0,
        "reason": "No new cohort passes the causal semantic bridge; point-model minting is forbidden.",
        **zero_counters(),
    }
    validation = {
        "artifact_id": "V17_AIDC_POWER_MODEL_V3R1_VALIDATION_REJECTION_RECORD_V1",
        "status": "NOT_RUN_NOT_AUTHORIZED",
        "primary_classification": PRIMARY_CLASSIFICATION,
        "U1_CLASSIFICATION": U1_CLASSIFICATION,
        "U2_CLASSIFICATION": U2_CLASSIFICATION,
        "U3_CLASSIFICATION": U3_CLASSIFICATION,
        "fit_calls": 0,
        "held_out_error_reads": 0,
        "held_out_metrics": None,
        "marginal_power_metrics": None,
        "acceptance_gate": acceptance["status"],
        **zero_counters(),
    }

    artifacts = {
        "V17_EUROSYS_ZENODO_RAW_DATA_INVENTORY.json": inventory,
        "V17_EUROSYS_ZENODO_MEASUREMENT_PROVENANCE.json": provenance,
        "V17_V3R1_H100_HARDWARE_TRANSFER_MATRIX.json": transfer,
        "V17_V3R1_Kestrel_U2_REPRODUCTION.json": reproduction,
        "V17_V3R1_EXTERNAL_TO_KESTREL_SEMANTIC_BRIDGE.json": bridge,
        "V17_V3R1_U2_AGGREGATE_STATE_COVERAGE.json": coverage,
        "V17_V3R1_EXTERNAL_SPLIT_CONTRACT.json": split,
        "V17_AIDC_POWER_V3R1_ACCEPTANCE_CONTRACT.json": acceptance,
        "V17_AIDC_POWER_V3R1_COHORT_IDENTIFIABILITY.json": identifiability,
        "V17_AIDC_POWER_MODEL_V3R1_CONTRACT.json": contract,
        "V17_AIDC_POWER_MODEL_V3R1_VALIDATION.json": validation,
        "V17_AIDC_POWER_V1_V3R1_COVERAGE_COMPARISON.json": coverage_compare,
    }
    for name, payload in artifacts.items():
        write_json(output / name, payload)
    return {
        "status": PRIMARY_CLASSIFICATION,
        "U1_CLASSIFICATION": U1_CLASSIFICATION,
        "U2_CLASSIFICATION": U2_CLASSIFICATION,
        "U3_CLASSIFICATION": U3_CLASSIFICATION,
        "V3R1_minted": False,
        "RCMQT_retraining_required": False,
        "same_7day_rerun": False,
        **zero_counters(),
    }


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--external-root", required=True, type=Path)
    parser.add_argument("--kestrel", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(list(argv) if argv is not None else None)
    print(json.dumps(materialize(args.repo, args.external_root, args.kestrel, args.output), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
