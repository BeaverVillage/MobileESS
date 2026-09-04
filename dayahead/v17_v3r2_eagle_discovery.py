"""Build the source-backed V17 V3R2 Eagle discovery checkpoint."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from dayahead.v17_v3r2_eagle_forensic import (
    EAGLE_NODES,
    GANGLIA_BYTES,
    GANGLIA_MD5,
    GANGLIA_NAME,
    GANGLIA_SHA256,
    ILO_BYTES,
    ILO_MD5,
    ILO_NAME,
    ILO_SHA256,
    JOBS_BYTES,
    JOBS_MD5,
    JOBS_NAME,
    JOBS_SHA256,
    verify_source,
    write_json,
    zero_counters,
)


def _base(schema: str, status: str) -> dict[str, Any]:
    return {"schema": schema, "status": status, **zero_counters()}


def build(gpu_root: Path, jobs_root: Path, output: Path) -> list[Path]:
    ganglia_path = gpu_root / GANGLIA_NAME
    ilo_path = gpu_root / ILO_NAME
    jobs_path = jobs_root / JOBS_NAME
    sources = {
        "ganglia": verify_source(
            ganglia_path, size=GANGLIA_BYTES, sha256=GANGLIA_SHA256, md5=GANGLIA_MD5
        ),
        "ilo": verify_source(ilo_path, size=ILO_BYTES, sha256=ILO_SHA256, md5=ILO_MD5),
        "jobs_energy": verify_source(
            jobs_path, size=JOBS_BYTES, sha256=JOBS_SHA256, md5=JOBS_MD5
        ),
    }
    source_before_after = all(item["immutable_before_after"] for item in sources.values())
    discovery = {
        **_base("V17_EAGLE_DATASET_DISCOVERY_V1", "PASS_ALL_THREE_OFFICIAL_EAGLE_SOURCES_IDENTIFIED"),
        "raw_roots_access_mode": "READ_ONLY",
        "gpu_root": str(gpu_root.resolve()),
        "jobs_energy_root": str(jobs_root.resolve()),
        "sources": sources,
        "official_records": {
            "gpu_metrics": {
                "title": "NLR HPC Eagle GPU Node Metrics",
                "url": "https://data.nlr.gov/submissions/301",
                "doi": "10.7799/3015213",
                "author": "Struan Clark",
            },
            "jobs_energy": {
                "title": "NLR HPC Eagle Jobs Data and Additional Energy Metrics",
                "url": "https://data.nlr.gov/submissions/295",
                "doi": "10.7799/3023273",
                "authors": ["Struan Clark", "Matt Selensky", "Kevin Menear"],
            },
        },
        "license": {
            "authority": "NLR Data Catalog standard terms",
            "scientific_use_permitted_with_notice_and_credit": True,
            "warranty": "AS_IS",
            "gpu_license_url": "https://data.nlr.gov/node/301/license",
            "jobs_license_url": "https://data.nlr.gov/node/295/license",
        },
        "source_immutable_before_after": source_before_after,
    }
    authority = {
        **_base("V17_EAGLE_SOURCE_AUTHORITY_MANIFEST_V1", "PASS_SOURCE_SHA_AND_REGISTRY_MD5_FROZEN"),
        "sources": sources,
        "raw_source_modifications": 0,
        "source_immutable_before_after": source_before_after,
    }
    hardware = {
        **_base("V17_EAGLE_HARDWARE_MEASUREMENT_AUTHORITY_V1", "PASS_V100_PCIE_METHOD_AUTHORITY"),
        "hardware": {
            "machine": "NREL/NLR Eagle",
            "gpu_model": "NVIDIA Tesla V100 PCIe",
            "gpus_per_node": 2,
            "cpu_model": "Intel Xeon Gold 6154",
            "cpu_sockets_per_node": 2,
            "cpu_cores_per_socket": 18,
            "node_ids": list(EAGLE_NODES),
        },
        "measurement": {
            "gpu_board_power": "Ganglia gpu[0|1]_power_usage_report, direct watts",
            "gpu_memory_utilization": "Ganglia gpu[0|1]_mem_util, direct telemetry",
            "gpu_temperature": "Ganglia gpu[0|1]_temp, Celsius",
            "whole_node_power": "HPE iLO instantaneous watts",
            "ganglia_observed_median_sampling_seconds": 60.0,
            "ilo_observed_median_sampling_seconds": 60.0,
            "timestamp_authority": "UTC ISO-8601 Z in raw telemetry",
        },
        "dataset312_comparison": {
            "eagle": "2 x V100 PCIe; Intel Xeon Gold 6154; GPU-board and iLO node boundary",
            "dataset312": "Kestrel H100-era frozen absolute kappa authority",
            "absolute_kw_transfer_authorized": False,
        },
        "compatibility_to_dataset312": "DIMENSIONLESS_RESPONSE_TRANSFER_ONLY",
    }
    fields = {
        "job_id": "DIRECT_SOURCE_FIELD",
        "submit_time_tz": "DIRECT_SOURCE_FIELD",
        "start_time_tz": "DIRECT_SOURCE_FIELD",
        "end_time_tz": "DIRECT_SOURCE_FIELD",
        "wallclock_used": "DIRECT_SOURCE_FIELD",
        "state": "DIRECT_SOURCE_FIELD",
        "nodes_req": "DIRECT_SOURCE_FIELD",
        "nodes_used": "DIRECT_SOURCE_FIELD",
        "nodelist": "DIRECT_SOURCE_FIELD",
        "processors_req": "DIRECT_SOURCE_FIELD",
        "memory_req": "DIRECT_SOURCE_FIELD",
        "gpus_requested": "DERIVED_BY_NLR",
        "gpu_nodes_occupied": "DERIVED_BY_NLR",
        "node_energy_total_watt_hours": "DERIVED_BY_NLR",
        "node_energy_node_array": "DERIVED_BY_NLR",
        "node_energy_avg_watts_array": "DERIVED_BY_NLR",
        "node_energy_watt_hours_array": "DERIVED_BY_NLR",
        "node_energy_wallclock_hours_array": "DERIVED_BY_NLR",
        "gpu0_energy_total_watt_hours": "DERIVED_BY_NLR",
        "gpu1_energy_total_watt_hours": "DERIVED_BY_NLR",
        "gpu_energy_node_array": "DERIVED_BY_NLR",
        "gpu_energy_gpu_array": "DERIVED_BY_NLR",
        "gpu_energy_avg_watts_array": "DERIVED_BY_NLR",
        "gpu_energy_watt_hours_array": "DERIVED_BY_NLR",
        "gpu_energy_wallclock_hours_array": "DERIVED_BY_NLR",
        "gpu_energy_timeseries_timestamp_array": "DERIVED_BY_NLR",
        "gpu_energy_timeseries_node_array": "DERIVED_BY_NLR",
        "gpu_energy_timeseries_gpu_array": "DERIVED_BY_NLR",
        "gpu_energy_timeseries_watts_array": "DERIVED_BY_NLR",
        "explicit_sharing_flag": "NOT_AVAILABLE",
        "per_gpu_device_assignment": "NOT_AVAILABLE",
        "MIG_state": "NOT_AVAILABLE",
        "time_slice_fraction": "NOT_AVAILABLE",
    }
    job_schema = {
        **_base("V17_EAGLE_JOB_ENERGY_SCHEMA_AUDIT_V1", "PASS_SCHEMA_ENUMERATED_FAIL_CLOSED_ON_SHARING_LABELS"),
        "parquet_member_count": sources["jobs_energy"]["member_count"],
        "parquet_period": "2018-11 through 2024-06",
        "fields": fields,
        "six_gpu_node_subset": {
            "job_rows": 110_614,
            "rows_with_valid_start_end": 110_117,
            "rows_with_node_energy": 85_761,
            "rows_with_gpu_energy": 7_309,
            "rows_with_gpu_timeseries": 7_302,
            "rows_with_positive_gpus_requested": 31_429,
            "rows_overlapping_ganglia_period": 79_321,
            "rows_overlapping_ilo_period": 105_146,
        },
        "energy_semantics": {
            "node_energy": "NLR-derived job-window integral of same-node iLO telemetry; not an individual-job meter",
            "gpu_energy": "NLR-derived job-window integral of same-node/device Ganglia power telemetry",
            "shared_job_attribution_authority": "NOT_PROVIDED",
        },
    }
    telemetry_schema = {
        **_base("V17_EAGLE_GPU_NODE_TELEMETRY_SCHEMA_AUDIT_V1", "PASS_EAGLE_INTERNAL_NODE_TIME_JOIN_AVAILABLE"),
        "ganglia_columns": ["__time", "dv", "mt", "vl"],
        "ilo_columns": ["__time", "dv", "vl"],
        "ganglia_metrics": {
            "gpu_device_power": ["gpu0_power_usage_report", "gpu1_power_usage_report"],
            "gpu_memory_utilization": ["gpu0_mem_util", "gpu1_mem_util"],
            "gpu_temperature": ["gpu0_temp", "gpu1_temp"],
            "cpu_utilization_diagnostic": ["cpu_idle", "cpu_user", "cpu_wio"],
        },
        "physical_node_key": "dv",
        "timestamp_key": "__time",
        "Eagle_internal_join_allowed": True,
        "Eagle_to_Kestrel_row_join_allowed": False,
        "gpu0_gpu1_exact_timestamp_sync_percent_by_node": {
            "r103u17": 99.999919,
            "r103u21": 100.0,
            "r104u29": 100.0,
            "r104u33": 100.0,
            "r105u09": 100.0,
            "r105u15": 100.0,
        },
    }
    timing = {
        **_base("V17_EAGLE_TEMPORAL_ALIGNMENT_CONTRACT_V1", "PASS_DETERMINISTIC_SOURCE_TIME_ALIGNMENT_FROZEN"),
        "coverage": {
            "ganglia_utc": ["2021-01-01T07:00:03Z", "2024-06-17T13:22:13Z"],
            "ilo_utc": ["2019-04-16T16:03:30Z", "2024-08-28T01:09:01Z"],
            "jobs_energy": ["2018-11", "2024-06"],
        },
        "quality": {
            "ganglia_median_interval_seconds": 60.0,
            "ganglia_p95_interval_seconds_range": [70.0, 72.0],
            "ganglia_duplicate_rows": {
                "gpu0_power_usage_report": 22_249,
                "gpu1_power_usage_report": 22_342,
            },
            "ilo_median_interval_seconds": 60.0,
            "ilo_p95_interval_seconds": 60.0,
            "ilo_duplicate_rows": 0,
            "prior_ilo_lag_median_seconds": 29.0,
            "prior_ilo_lag_p95_seconds": 58.0,
            "known_long_gaps_exist": True,
            "gap_rows_are_not_imputed": True,
        },
        "alignment_rule": {
            "timezone": "UTC",
            "job_timestamp_fields": ["start_time_tz", "end_time_tz"],
            "telemetry_duplicate_resolution": "exact node/metric/timestamp collapse only; no value fitting",
            "gpu_pair_rule": "exact same physical-node timestamp",
            "ilo_rule": "most recent same-node iLO sample at or before Ganglia timestamp",
            "ilo_max_staleness_seconds": 300,
            "outside_staleness": "MISSING_FAIL_CLOSED",
            "heldout_offset_selection": False,
            "random_row_split_allowed": False,
        },
    }
    payloads = {
        "V17_EAGLE_DATASET_DISCOVERY.json": discovery,
        "V17_EAGLE_SOURCE_AUTHORITY_MANIFEST.json": authority,
        "V17_EAGLE_HARDWARE_MEASUREMENT_AUTHORITY.json": hardware,
        "V17_EAGLE_JOB_ENERGY_SCHEMA_AUDIT.json": job_schema,
        "V17_EAGLE_GPU_NODE_TELEMETRY_SCHEMA_AUDIT.json": telemetry_schema,
        "V17_EAGLE_TEMPORAL_ALIGNMENT_CONTRACT.json": timing,
    }
    written: list[Path] = []
    for name, payload in payloads.items():
        path = output / name
        write_json(path, payload)
        written.append(path)
    return written


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gpu-root", type=Path, required=True)
    parser.add_argument("--jobs-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    for path in build(args.gpu_root, args.jobs_root, args.output):
        print(path)


if __name__ == "__main__":
    main()
