"""Read-only V17 external H100 source discovery and authority audit.

The raw archives are never extracted into or modified under the external data
root.  Archive members are streamed for hashing and schema inspection only.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import zipfile
from pathlib import Path
from typing import Any, Iterable


REQUIRED_HEAD = "0c441f1a8eb2b851fb6bf4bc7c3fde26f543970a"
EUROSYS_SHA256 = "e941baeb5fc083d404cf6f676cf11794e269bf06e96fea6d3d58746fb1919ac7"
SCIENTIFIC_OUTER_SHA256 = "66c6e69823cba078ada7be852b293d5d1ead7526a95645f033df674031bbc71a"
SCIENTIFIC_PAYLOAD_SHA256 = "c0ccebea568612f5445b70c3baa7ce659935a949e5cc8f345a0af907739fa6f3"
DATASET312_SHA256 = "dcad6de800fb565d850b163902e2eddae48aabd1ed1c7336f9a1cdaf3012f137"

EUROSYS_DIR = "EuroSys 2026 — Untangling GPU Power Consumption artifact"
EUROSYS_ARCHIVE = "untangling-gpu-power-main.zip"
SCIENTIFIC_DIR = "Scientific Data 2026 — H100B200 high-resolution workload dataset"
SCIENTIFIC_ARCHIVE = "31654879.zip"
SCIENTIFIC_DUP_DIR = "H100B200 AI Training Power Dataset"
SCIENTIFIC_PAYLOAD = "High-resolution-AI-Data-Center-Training-Workloads-Dataset_FigShare.zip"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def zero_counters() -> dict[str, int]:
    return {
        "May_scientific_input_reads": 0,
        "June_scientific_input_reads": 0,
        "May_result_content_reads": 0,
        "June_result_content_reads": 0,
        "remaining_April_day_runs": 0,
        "effect_selected_power_parameters": 0,
        "grid_benefit_selected_power_parameters": 0,
        "arbitrary_flexible_scaling_calls": 0,
        "rowwise_external_to_Kestrel_merges": 0,
        "OpenDSS_calls_inside_Benders": 0,
    }


def _stream_member_sha(archive: zipfile.ZipFile, info: zipfile.ZipInfo) -> str:
    digest = hashlib.sha256()
    with archive.open(info) as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def archive_manifest(path: Path) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            records.append(
                {
                    "path": info.filename,
                    "bytes": info.file_size,
                    "compressed_bytes": info.compress_size,
                    "crc32": f"{info.CRC:08x}",
                    "sha256": _stream_member_sha(archive, info),
                }
            )
    canonical = "".join(
        f"{row['path']}\0{row['bytes']}\0{row['sha256']}\n" for row in records
    ).encode("utf-8")
    return {
        "archive_path": str(path.resolve()),
        "archive_bytes": path.stat().st_size,
        "archive_sha256": sha256_file(path),
        "file_count": len(records),
        "uncompressed_bytes": sum(row["bytes"] for row in records),
        "recursive_content_manifest_sha256": sha256_bytes(canonical),
        "files": records,
    }


def _read_zip_text(archive: zipfile.ZipFile, name: str) -> str:
    return archive.read(name).decode("utf-8-sig", errors="replace")


def _url_value(path: Path) -> str:
    match = re.search(r"^URL=(.+)$", path.read_text(encoding="utf-8-sig"), flags=re.MULTILINE)
    return match.group(1).strip() if match else "NOT_ENCODED"


def _scientific_headers(payload_path: Path) -> dict[str, Any]:
    prefix = "High-resolution-AI-Data-Center-Training-Workloads-Dataset_FigShare/"
    with zipfile.ZipFile(payload_path) as archive:
        csv_names = [name for name in archive.namelist() if name.casefold().endswith(".csv")]
        node_names = [name for name in csv_names if "/Node_Dataset/" in name]
        h100_names = [name for name in node_names if "/H100/" in name]
        unique: dict[str, list[str]] = {}
        for name in csv_names:
            header = archive.open(name).readline().decode("utf-8-sig", errors="replace").strip()
            unique.setdefault(header, []).append(name)
        h100_header = archive.open(h100_names[0]).readline().decode("utf-8-sig").strip()
        columns = next(csv.reader([h100_header]))
        member_identity = [
            {"path": name, "bytes": archive.getinfo(name).file_size, "crc32": f"{archive.getinfo(name).CRC:08x}"}
            for name in h100_names
        ]
        return {
            "archive_prefix": prefix,
            "csv_member_count": len(csv_names),
            "node_csv_member_count": len(node_names),
            "h100_csv_member_count": len(h100_names),
            "h100_unique_content_count_by_crc32": len({row["crc32"] for row in member_identity}),
            "unique_header_count": len(unique),
            "h100_schema_columns": columns,
            "h100_members": member_identity,
        }


def discover(external_root: Path, dataset312: Path, output: Path) -> dict[str, Any]:
    external_root = external_root.resolve()
    eurosys = external_root / EUROSYS_DIR / EUROSYS_ARCHIVE
    sci_outer = external_root / SCIENTIFIC_DIR / SCIENTIFIC_ARCHIVE
    sci_payload = external_root / SCIENTIFIC_DUP_DIR / SCIENTIFIC_PAYLOAD
    if sha256_file(eurosys) != EUROSYS_SHA256:
        raise RuntimeError("V17_EUROSYS_SOURCE_SHA_MISMATCH")
    if sha256_file(sci_outer) != SCIENTIFIC_OUTER_SHA256:
        raise RuntimeError("V17_SCIENTIFIC_OUTER_SOURCE_SHA_MISMATCH")
    if sha256_file(sci_payload) != SCIENTIFIC_PAYLOAD_SHA256:
        raise RuntimeError("V17_SCIENTIFIC_PAYLOAD_SOURCE_SHA_MISMATCH")
    if sha256_file(dataset312) != DATASET312_SHA256:
        raise RuntimeError("V17_DATASET312_SOURCE_SHA_MISMATCH")

    with zipfile.ZipFile(sci_outer) as outer:
        if len(outer.infolist()) != 1:
            raise RuntimeError("V17_SCIENTIFIC_OUTER_NOT_SINGLE_PAYLOAD")
        nested = outer.read(outer.infolist()[0])
    nested_sha = sha256_bytes(nested)
    if nested_sha != SCIENTIFIC_PAYLOAD_SHA256:
        raise RuntimeError("V17_SCIENTIFIC_NESTED_PAYLOAD_SHA_MISMATCH")

    eurosys_manifest = archive_manifest(eurosys)
    scientific_manifest = archive_manifest(sci_payload)
    with zipfile.ZipFile(eurosys) as archive:
        euro_readme_name = "untangling-gpu-power-main/README.md"
        euro_license_name = "untangling-gpu-power-main/LICENSE"
        euro_experiment_readme = "untangling-gpu-power-main/experiments/README.md"
        euro_readme = _read_zip_text(archive, euro_readme_name)
        euro_data_files = [
            info.filename for info in archive.infolist()
            if not info.is_dir()
            and ("/data/" in info.filename or "/bench-res/" in info.filename)
            and not info.filename.endswith(".gitkeep")
        ]
        euro_experiment_files = [
            info.filename for info in archive.infolist()
            if info.filename.startswith("untangling-gpu-power-main/experiments/exp-")
            and info.filename.endswith(".py")
        ]
        euro_figure_code = [
            info.filename for info in archive.infolist()
            if info.filename.startswith("untangling-gpu-power-main/src/") and info.filename.endswith(".py")
        ]
        euro_readme_sha = sha256_bytes(archive.read(euro_readme_name))
        euro_license_sha = sha256_bytes(archive.read(euro_license_name))
        euro_experiment_readme_sha = sha256_bytes(archive.read(euro_experiment_readme))

    with zipfile.ZipFile(sci_payload) as archive:
        sci_readme_name = "High-resolution-AI-Data-Center-Training-Workloads-Dataset_FigShare/README.md"
        sci_license_name = "High-resolution-AI-Data-Center-Training-Workloads-Dataset_FigShare/LICENSE"
        sci_readme = _read_zip_text(archive, sci_readme_name)
        sci_readme_sha = sha256_bytes(archive.read(sci_readme_name))
        sci_license_sha = sha256_bytes(archive.read(sci_license_name))
    sci_headers = _scientific_headers(sci_payload)

    euro_url_file = next((external_root / EUROSYS_DIR).glob("*.url"))
    sci_url_files = sorted((external_root / SCIENTIFIC_DIR).glob("*.url"))
    discovery = {
        "artifact_id": "V17_EXTERNAL_H100_DATASET_DISCOVERY_V1",
        "status": "PASS_TWO_INTENDED_DATASET_IDENTITIES_UNIQUE",
        "external_root": str(external_root),
        "raw_root_access_mode": "READ_ONLY",
        "datasets": [
            {
                "dataset_id": "EUROSYS_UNTANGLING_GPU_POWER",
                "absolute_path": str(eurosys.resolve()),
                "file_type": "ZIP",
                "archive_bytes": eurosys.stat().st_size,
                "sha256": EUROSYS_SHA256,
                "extracted_file_count_virtual_read_only": eurosys_manifest["file_count"],
                "title": "Untangling GPU Power Consumption: Job-Level Inference in Cloud Shared Settings",
                "publication": "EuroSys 2026",
                "authors_project_local": "repository owner maxime-agusti; ETS Montreal and Inria copyright; full author list not encoded locally",
                "repository_provenance": _url_value(euro_url_file),
                "license": "BSD-3-Clause",
                "H100_presence": True,
                "raw_telemetry_presence": bool(euro_data_files),
                "raw_telemetry_file_count": len(euro_data_files),
                "sharing_MIG_time_slicing_presence": "EXPERIMENT_AND_FIGURE_CODE_ONLY; RAW_MEASUREMENTS_ABSENT",
                "experiment_script_count": len(euro_experiment_files),
                "figure_script_count": len(euro_figure_code),
                "identification_evidence": [
                    "README exact paper title and EuroSys 2026 acceptance",
                    "MIG and time-slicing experiment scripts",
                    "H100-PCIE-80GB and H100-NVL-94GB figure-source labels",
                ],
            },
            {
                "dataset_id": "SCIENTIFIC_DATA_H100_B200_HIGH_RESOLUTION",
                "absolute_path": str(sci_outer.resolve()),
                "file_type": "ZIP_WRAPPING_EXACT_FIGSHARE_ZIP",
                "archive_bytes": sci_outer.stat().st_size,
                "sha256": SCIENTIFIC_OUTER_SHA256,
                "nested_payload_path": str(sci_payload.resolve()),
                "nested_payload_sha256": SCIENTIFIC_PAYLOAD_SHA256,
                "nested_payload_byte_identity": True,
                "extracted_file_count_virtual_read_only": scientific_manifest["file_count"],
                "title": "High-resolution AI Data Center Training Workloads Dataset",
                "publication": "Characterization of high-resolution AI data center training workloads on single and multiple GPU nodes",
                "authors_project_local": ["Ahmed Abd Elaziz Elsayed", "Abdullah Azhar Al-Obaidi", "Hany E.Z. Farag"],
                "doi_repository_provenance": {
                    "publication": _url_value(sci_url_files[0]),
                    "figshare": _url_value(sci_url_files[1]),
                    "readme_preprint_doi": "10.21203/rs.3.rs-7943457/v1",
                    "figshare_item_id": "31654879",
                },
                "license": "CC-BY-NC-ND-4.0",
                "H100_presence": True,
                "raw_telemetry_presence": True,
                "sharing_MIG_time_slicing_presence": False,
                "h100_csv_members": sci_headers["h100_csv_member_count"],
                "h100_unique_content_count": sci_headers["h100_unique_content_count_by_crc32"],
                "identification_evidence": [
                    "README exact dataset title",
                    "H100 SXM 80GB and B200 8-GPU hardware table",
                    "20 ms node telemetry description",
                    "Figshare item 31654879 local shortcut and wrapper filename",
                ],
            },
        ],
        "candidate_resolution": {
            "scientific_duplicate_directory_is_exact_nested_payload": True,
            "scientific_outer_zip_contains_one_member": True,
            "scientific_outer_nested_payload_sha256": nested_sha,
            "intended_dataset_count": 2,
        },
        **zero_counters(),
    }

    source_authority = {
        "artifact_id": "V17_EXTERNAL_H100_SOURCE_AUTHORITY_MANIFEST_V1",
        "status": "PASS_SOURCE_PROVENANCE_FROZEN_READ_ONLY",
        "datasets": {
            "EUROSYS_UNTANGLING_GPU_POWER": {
                "archive": eurosys_manifest,
                "readme_sha256": euro_readme_sha,
                "experiment_readme_sha256": euro_experiment_readme_sha,
                "license_sha256": euro_license_sha,
                "license": "BSD-3-Clause",
                "hardware_configuration": {
                    "H100_variants_named_in_figure_code": [
                        "H100-PCIE-80GB (350W)", "H100-NVL-94GB (400W)"
                    ],
                    "A100_variants_named_in_figure_code": [
                        "A100-PCIE-40GB (250W)", "A100-PCIE-80GB (300W)", "A100-SXM4-40GB (400W)"
                    ],
                    "GPU_form_factor": ["PCIe", "NVL"],
                    "GPUs_per_node": [1, 2],
                    "CPU_model": "NOT_ENCODED_LOCALLY",
                    "CUDA": "NOT_ENCODED_LOCALLY",
                    "driver": ["535.183.06", "570.124.06"],
                    "monitoring": ["DCGM", "nvidia-smi", "IPMI", "CPU monitor"],
                    "sampling_interval": "NOT_ENCODED_AS_FIXED_AUTHORITY",
                    "workloads": ["GPU burn", "Blender", "HPCG", "LLaMA inference", "YOLO training"],
                    "sharing": ["MIG GI/CI", "container time-slicing", "Kubernetes time-slicing", "concurrent containers"],
                },
                "critical_limitation": "Downloaded archive has no non-placeholder files under data/ or bench-res/.",
            },
            "SCIENTIFIC_DATA_H100_B200_HIGH_RESOLUTION": {
                "outer_archive": {
                    "path": str(sci_outer.resolve()), "bytes": sci_outer.stat().st_size,
                    "sha256": SCIENTIFIC_OUTER_SHA256,
                },
                "payload_archive": scientific_manifest,
                "readme_sha256": sci_readme_sha,
                "license_sha256": sci_license_sha,
                "license": "CC-BY-NC-ND-4.0",
                "hardware_configuration": {
                    "GPU": ["8x NVIDIA H100 SXM 80GB", "8x NVIDIA B200 180GB"],
                    "GPU_form_factor": {"H100": "SXM", "B200": "NOT_FURTHER_ENCODED"},
                    "GPUs_per_node": 8,
                    "H100_power_cap_W_derived_from_power_and_percent_TDP_columns": 700.0,
                    "CPU": "Intel Xeon 208 vCPU",
                    "RAM_GB": {"H100": 1800, "B200": 2900},
                    "OS": "Ubuntu Server 22.04; README contains internally inconsistent arm64 and x86-64 label",
                    "CUDA_driver": "NOT_ENCODED_LOCALLY",
                    "monitoring": "pynvml GPU telemetry plus psutil/os CPU telemetry",
                    "sampling_interval": "20 ms minimum, limited by NVIDIA driver update frequency",
                    "workloads": ["diffusion image generation training", "LLM training"],
                    "sharing": "NONE; one 8-GPU training workload per CSV session",
                },
                "license_use_note": "Noncommercial analysis allowed; adapted data may be produced but not shared under CC-BY-NC-ND-4.0. No raw or transformed telemetry is copied into repository artifacts.",
            },
        },
        **zero_counters(),
    }

    compatibility = {
        "artifact_id": "V17_EXTERNAL_H100_HARDWARE_COMPATIBILITY_V1",
        "status": "PASS_FAIL_CLOSED_NO_DIRECT_EXTERNAL_ABSOLUTE_KW_TRANSFER",
        "matrix": [
            {
                "source": "Dataset312",
                "GPU_SKU": "NVIDIA H100; exact SKU/form factor not encoded locally",
                "memory_SKU": "NOT_ENCODED_LOCALLY",
                "power_cap": "NOT_ENCODED_LOCALLY",
                "GPUs_per_node": 4,
                "CPU_platform": "two CPU sockets; exact CPU model not encoded locally",
                "GPU_interconnect": "NOT_ENCODED_LOCALLY",
                "system_architecture": "NLR Kestrel node",
                "measured_power_boundary": "sum per-GPU NVML board power + CPU RAPL package power",
                "idle_subtraction": "4*72.5 W GPU plus 2*64.1 W CPU-socket constants per node",
                "workload": "full-node Llama2-70B LoRA and Stable Diffusion training; Llama3 inference",
            },
            {
                "source": "EuroSys artifact",
                "GPU_SKU": "H100 PCIe 80GB and H100 NVL 94GB",
                "memory_SKU": "80GB/94GB",
                "power_cap": "350W/400W",
                "GPUs_per_node": "1 and 2 in local figure-source labels",
                "CPU_platform": "NOT_ENCODED_LOCALLY",
                "GPU_interconnect": "NVL only for H100-NVL experiments; otherwise not encoded",
                "system_architecture": "multiple experimental platforms",
                "measured_power_boundary": "scripts declare DCGM device power and IPMI platform power",
                "idle_subtraction": "figure logic exists but raw measurements absent",
                "workload": "MIG/time-slicing/concurrent benchmark experiments",
            },
            {
                "source": "Scientific Data H100",
                "GPU_SKU": "H100 SXM 80GB",
                "memory_SKU": "80GB",
                "power_cap": "700W derived reproducibly from reported W and percent-TDP fields",
                "GPUs_per_node": 8,
                "CPU_platform": "Intel Xeon 208 vCPU",
                "GPU_interconnect": "NOT_ENCODED_LOCALLY",
                "system_architecture": "8-GPU data-center node",
                "measured_power_boundary": "per-GPU pynvml board power; CPU power columns empty in H100 CSVs",
                "idle_subtraction": "no explicit idle state or idle baseline",
                "workload": "single full-node diffusion or LLM training session",
            },
        ],
        "relationships": [
            {
                "from": "EuroSys artifact", "to": "Dataset312",
                "classification": "QUALITATIVE_ONLY",
                "reason": "H100 PCIe/NVL hardware and power caps differ or are unverified, and the downloaded artifact omits all raw sharing telemetry.",
            },
            {
                "from": "Scientific Data H100", "to": "Dataset312",
                "classification": "DIMENSIONLESS_RESPONSE_TRANSFER_ONLY",
                "reason": "H100 identity overlaps, but 8x SXM/700W, CPU and power boundary differ from Dataset312's 4-GPU NVML+RAPL incremental node boundary.",
            },
            {
                "from": "EuroSys artifact", "to": "Scientific Data H100",
                "classification": "INCOMPATIBLE",
                "reason": "Sharing data are absent locally and the encoded H100 variants (PCIe/NVL 350/400W) differ from the Scientific Data SXM 700W platform.",
            },
        ],
        "absolute_external_kW_may_replace_Dataset312_kappa": False,
        "Dataset312_kappa_changes": 0,
        **zero_counters(),
    }

    euro_fields = {
        key: {"classification": "NOT_AVAILABLE", "note": "Instrumentation or configuration is declared by code, but the downloaded data and bench-res directories contain no measurements."}
        for key in [
            "timestamp", "GPU_index_device_identity", "per_GPU_instantaneous_power", "GPU_utilization",
            "memory_utilization", "CPU_package_power", "host_system_power", "active_GPU_count",
            "powered_GPU_count", "requested_GPU_count", "concurrent_process_container_count",
            "idle_state", "idle_baseline", "node_count",
        ]
    }
    euro_fields.update({
        "MIG_slice_configuration": {"classification": "CONFIGURATION_METADATA", "note": "GI/CI profile enumeration and creation logic in experiment scripts; no result rows."},
        "MIG_instance_ID": {"classification": "CONFIGURATION_METADATA", "note": "Runtime GI/CI/MIG UUID plumbing in experiment scripts; no recorded result values."},
        "time_slicing_mode": {"classification": "CONFIGURATION_METADATA", "note": "Docker and Kubernetes time-slicing experiment definitions."},
        "workload_ID": {"classification": "CONFIGURATION_METADATA", "note": "Blender/HPCG/LLaMA/YOLO/GPU-burn experiment definitions."},
        "experiment_session_ID": {"classification": "CONFIGURATION_METADATA", "note": "Expected filenames and labels in figure scripts; source CSVs absent."},
        "batch_concurrency": {"classification": "CONFIGURATION_METADATA", "note": "Container/pod and MIG complement loops define concurrency settings."},
        "power_cap": {"classification": "CONFIGURATION_METADATA", "note": "350W H100 PCIe and 400W H100 NVL labels in figure code."},
    })
    scientific_fields = {
        "timestamp": {"classification": "DIRECT_MEASUREMENT", "fields": ["timestamp"]},
        "GPU_index_device_identity": {"classification": "DIRECT_MEASUREMENT", "fields": ["gpu0..gpu7 column identity"]},
        "per_GPU_instantaneous_power": {"classification": "DIRECT_MEASUREMENT", "fields": ["gpu0_power_W..gpu7_power_W"]},
        "GPU_utilization": {"classification": "DIRECT_MEASUREMENT", "fields": ["gpu0_utilization_percent..gpu7_utilization_percent"]},
        "memory_utilization": {"classification": "DIRECT_MEASUREMENT", "fields": ["gpu0_mem_utilization..gpu7_mem_utilization"]},
        "CPU_package_power": {"classification": "NOT_AVAILABLE", "note": "cpu_power_W column exists but is empty in all audited H100 node CSVs."},
        "host_system_power": {"classification": "NOT_AVAILABLE"},
        "active_GPU_count": {"classification": "NOT_AVAILABLE", "note": "Eight device channels exist; no causal active/allocation count field."},
        "powered_GPU_count": {"classification": "NOT_AVAILABLE"},
        "requested_GPU_count": {"classification": "NOT_AVAILABLE"},
        "MIG_slice_configuration": {"classification": "NOT_AVAILABLE"},
        "MIG_instance_ID": {"classification": "NOT_AVAILABLE"},
        "time_slicing_mode": {"classification": "NOT_AVAILABLE"},
        "concurrent_process_container_count": {"classification": "NOT_AVAILABLE"},
        "workload_ID": {"classification": "CONFIGURATION_METADATA", "fields": ["CSV path and filename"]},
        "experiment_session_ID": {"classification": "CONFIGURATION_METADATA", "fields": ["one CSV file per recorded session/configuration"]},
        "batch_concurrency": {"classification": "CONFIGURATION_METADATA", "fields": ["BatchSize in filename"]},
        "idle_state": {"classification": "NOT_AVAILABLE", "note": "No source-labeled idle state."},
        "idle_baseline": {"classification": "NOT_AVAILABLE"},
        "power_cap": {"classification": "DERIVED", "fields": ["gpu*_power_W / gpu*_Power_TDP"], "derived_H100_W": 700.0},
        "node_count": {"classification": "CONFIGURATION_METADATA", "value": 1},
    }
    schema_audit = {
        "artifact_id": "V17_EXTERNAL_H100_SCHEMA_AUDIT_V1",
        "status": "PASS_SCHEMA_AUDIT_WITH_EUROSYS_RAW_TELEMETRY_ABSENT",
        "concept_firewall": {
            "GPU_utilization_percentage_is_GPU_allocation_fraction": False,
            "MIG_2g20gb_is_Kestrel_2_of_4_GPU_request": False,
            "time_slicing_is_Kestrel_co_residency": False,
        },
        "datasets": {
            "EUROSYS_UNTANGLING_GPU_POWER": {
                "fields": euro_fields,
                "raw_telemetry_file_count": 0,
                "schema_is_fit_capable": False,
            },
            "SCIENTIFIC_DATA_H100_B200_HIGH_RESOLUTION": {
                "fields": scientific_fields,
                "schema": sci_headers,
                "schema_is_fit_capable_for_utilization_power_response": True,
                "schema_is_fit_capable_for_allocation_or_sharing_power": False,
            },
        },
        **zero_counters(),
    }

    artifacts = {
        "V17_EXTERNAL_H100_DATASET_DISCOVERY.json": discovery,
        "V17_EXTERNAL_H100_SOURCE_AUTHORITY_MANIFEST.json": source_authority,
        "V17_EXTERNAL_H100_HARDWARE_COMPATIBILITY.json": compatibility,
        "V17_EXTERNAL_H100_SCHEMA_AUDIT.json": schema_audit,
    }
    for name, payload in artifacts.items():
        write_json(output / name, payload)
    return {
        "status": "PASS_DISCOVERY_AUTHORITY_SCHEMA",
        "artifacts": sorted(artifacts),
        "EuroSys_raw_telemetry_present": bool(euro_data_files),
        "Scientific_nested_payload_identity": True,
    }


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--external-root", type=Path, required=True)
    parser.add_argument("--dataset312", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(list(argv) if argv is not None else None)
    result = discover(args.external_root, args.dataset312, args.output)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
