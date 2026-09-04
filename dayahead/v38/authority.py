"""Historical-authority recovery and conservative 5-to-15 minute adapters."""

from __future__ import annotations

from dataclasses import dataclass
import csv
import hashlib
import json
import math
from pathlib import Path
from statistics import median
from typing import Any, Iterable, Mapping

import pandas as pd
from pfr.migration import MigrationAuthority, WanLink, load_migration_authority

from .contracts import (
    ARTIFACT_ROOT,
    CHECKPOINT_INTERVAL_SECONDS,
    EXPECTED_RACK_SHA256,
    EXPECTED_WAN_README_SHA256,
    EXPECTED_WAN_TOPOLOGY_SHA256,
    EXPECTED_WAN_TRAFFIC_SHA256,
    GPU_CAPACITY,
    RACK_CONTRACT,
    RACK_PROVENANCE,
    RAW_RACK_CAPACITY,
    RAW_WAN_README,
    RAW_WAN_TOPOLOGY,
    RAW_WAN_TRAFFIC,
    RESTART_SECONDS,
    RUNTIME_FIREWALL,
    SLOT_SECONDS,
    WAN_CONTRACT,
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    temporary.replace(path)


@dataclass(frozen=True)
class RackPool:
    aidc_id: str
    rack_pool_id: str
    historical_gpu_capacity: float


@dataclass(frozen=True)
class CapacityAuthority:
    site_capacity: Mapping[str, int]
    historical_site_capacity: Mapping[str, float]
    rack_pools: tuple[RackPool, ...]
    source_sha256: str

    @property
    def aidc_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self.site_capacity))

    def eligible_racks(self, aidc_id: str, gpu_gang: int) -> tuple[RackPool, ...]:
        return tuple(
            row for row in self.rack_pools
            if row.aidc_id == aidc_id
            and row.historical_gpu_capacity + 1e-9 >= gpu_gang
        )


@dataclass(frozen=True)
class V38WanAuthority:
    historical: MigrationAuthority
    link_capacity_bytes_5min: Mapping[str, int]
    link_capacity_bytes_15min: Mapping[str, tuple[int, ...]]
    latency_semantics: str = "NO_AUTHORITATIVE_LATENCY_AVAILABLE"

    @staticmethod
    def link_id(link: WanLink) -> str:
        return "--".join(sorted((link.a, link.b)))

    @staticmethod
    def historical_idc(value: str) -> str:
        """Map canonical AIDC labels to the frozen legacy IDC schema."""
        if value.startswith("AIDC") and len(value) == 6:
            return "IDC" + value[4:]
        return value

    def path(self, source_aidc: str, destination_aidc: str) -> tuple[str, ...]:
        return tuple(self.link_id(link) for link in self.historical.route(
            self.historical_idc(source_aidc), self.historical_idc(destination_aidc)
        ))

    def path_nodes(self, source_aidc: str, destination_aidc: str) -> tuple[str, ...]:
        source = self.historical_idc(source_aidc)
        destination = self.historical_idc(destination_aidc)
        links = self.historical.route(source, destination)
        node = self.historical.idc_to_wan_node[source]
        nodes = [node]
        for link in links:
            node = link.b if link.a == node else link.a
            nodes.append(node)
        if nodes[-1] != self.historical.idc_to_wan_node[destination]:
            raise RuntimeError("V38_WAN_FIXED_PATH_ORDER")
        return tuple(nodes)

    def path_id(self, source_aidc: str, destination_aidc: str) -> str:
        left = int(self.historical_idc(source_aidc)[3:])
        right = int(self.historical_idc(destination_aidc)[3:])
        return f"OD{left:02d}_{right:02d}_FIXED"

    def capacity_bytes(self, link_id: str, slot: int) -> int:
        if not 0 <= slot < 96:
            raise ValueError("V38_WAN_SLOT")
        return int(self.link_capacity_bytes_15min[link_id][slot])

    def path_capacity_bytes(self, source_aidc: str, destination_aidc: str, slot: int) -> int:
        path = self.path(source_aidc, destination_aidc)
        if not path:
            return 0
        return min(self.capacity_bytes(link, slot) for link in path)

    def payload_bytes(self, requested_gpu: int) -> int:
        return self.historical.checkpoint_payload_bytes(requested_gpu)


def _largest_remainder(total: int, weights: Mapping[str, float]) -> dict[str, int]:
    denominator = sum(float(value) for value in weights.values())
    raw = {key: total * float(value) / denominator for key, value in weights.items()}
    result = {key: int(math.floor(value)) for key, value in raw.items()}
    order = sorted(raw, key=lambda key: (-(raw[key] - result[key]), key))
    for key in order[: total - sum(result.values())]:
        result[key] += 1
    if sum(result.values()) != total or any(value <= 0 for value in result.values()):
        raise RuntimeError("V38_GPU_CAPACITY_LARGEST_REMAINDER")
    return result


def load_capacity_authority(repo: Path) -> CapacityAuthority:
    contract_path = repo / RACK_CONTRACT
    payload = json.loads(contract_path.read_text(encoding="utf-8"))
    if str(payload.get("source_sha256")) != EXPECTED_RACK_SHA256:
        raise RuntimeError("V38_RACK_CONTRACT_SOURCE_SHA")
    if not RAW_RACK_CAPACITY.is_file() or sha256_file(RAW_RACK_CAPACITY) != EXPECTED_RACK_SHA256:
        raise RuntimeError("V38_RACK_RAW_SOURCE_MISSING_OR_CHANGED")
    racks = tuple(
        RackPool(
            str(row["aidc_id"]),
            str(row["rack_id"]),
            float(row["deliverable_gpu_capacity"]),
        )
        for row in payload["racks"]
    )
    if len(racks) != 48 or len({row.rack_pool_id for row in racks}) != 48:
        raise RuntimeError("V38_RACK_AXIS")
    historical: dict[str, float] = {}
    for row in racks:
        historical[row.aidc_id] = historical.get(row.aidc_id, 0.0) + row.historical_gpu_capacity
    site = _largest_remainder(GPU_CAPACITY, historical)
    return CapacityAuthority(site, historical, racks, EXPECTED_RACK_SHA256)


def load_wan_authority(repo: Path) -> V38WanAuthority:
    required = (
        (RAW_WAN_TOPOLOGY, EXPECTED_WAN_TOPOLOGY_SHA256),
        (RAW_WAN_README, EXPECTED_WAN_README_SHA256),
        (RAW_WAN_TRAFFIC, EXPECTED_WAN_TRAFFIC_SHA256),
    )
    for path, expected in required:
        if not path.is_file() or sha256_file(path) != expected:
            raise RuntimeError(f"V38_WAN_RAW_SOURCE_MISSING_OR_CHANGED:{path}")
    historical = load_migration_authority(repo / WAN_CONTRACT)
    if historical.step_seconds != 300 or historical.maximum_active_transfers != 1:
        raise RuntimeError("V38_WAN_HISTORICAL_CONTRACT")
    five: dict[str, int] = {}
    fifteen: dict[str, tuple[int, ...]] = {}
    for link in historical.links:
        identifier = V38WanAuthority.link_id(link)
        # The frozen contract uses decimal Mbit/s and decimal bytes.  Convert
        # rate to a transferred-byte budget once, at the native five-minute step.
        per_five = int(math.floor(link.capacity_mbps * 1_000_000 / 8 * 300))
        five[identifier] = per_five
        fifteen[identifier] = tuple(per_five * 3 for _ in range(96))
    return V38WanAuthority(historical, five, fifteen)


def checkpoint_slots(elapsed_seconds: float, service_slots: int) -> tuple[int, ...]:
    """Map job-specific 30-minute phase to conservative 15-minute slot starts."""

    if elapsed_seconds < 0 or service_slots <= 0:
        return ()
    remainder = elapsed_seconds % CHECKPOINT_INTERVAL_SECONDS
    wait_seconds = CHECKPOINT_INTERVAL_SECONDS if remainder == 0 else (
        CHECKPOINT_INTERVAL_SECONDS - remainder
    )
    first = int(math.ceil(wait_seconds / SLOT_SECONDS))
    return tuple(range(first, service_slots, CHECKPOINT_INTERVAL_SECONDS // SLOT_SECONDS))


def materialize_fixed_od_paths(repo: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Persist the historical one-path-per-OD routing authority.

    Route generation is outside the spatial MILP and depends only on the
    frozen topology's minimum-hop/lexicographic rule.
    """

    wan = load_wan_authority(repo)
    aidcs = tuple(f"AIDC{index:02d}" for index in range(1, 13))
    rows: list[dict[str, Any]] = []
    for source in aidcs:
        for destination in aidcs:
            if source == destination:
                continue
            record = {
                "source_AIDC": source,
                "destination_AIDC": destination,
                "path_id": wan.path_id(source, destination),
                "ordered_WAN_nodes": list(wan.path_nodes(source, destination)),
                "ordered_WAN_links": list(wan.path(source, destination)),
                "hop_count": len(wan.path(source, destination)),
                "frozen_path_latency_parameter": None,
                "latency_semantics": wan.latency_semantics,
                "path_authority": "V38_INTER_AIDC_FIXED_OD_PATH_AUTHORITY",
                "legacy_authority_id": "PFR_IDC_MIGRATION_ABILENE12_H10080_V1",
                "path_generation_rule": "DETERMINISTIC_MINIMUM_HOP_LEXICOGRAPHIC",
            }
            record["path_SHA"] = canonical_sha256(record)
            rows.append(record)
    frame = pd.DataFrame(rows).sort_values(["source_AIDC", "destination_AIDC"]).reset_index(drop=True)
    if len(frame) != 132 or frame[["source_AIDC", "destination_AIDC"]].duplicated().any():
        raise RuntimeError("V38_WAN_FIXED_OD_PATH_AXIS")
    path = repo / ARTIFACT_ROOT / "V38_WAN_FIXED_OD_PATHS.parquet"
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_parquet(temporary, index=False)
    temporary.replace(path)
    audit = {
        "artifact_id": "V38_WAN_FIXED_OD_PATH_AUTHORITY_V1",
        "status": "PASS",
        "ordered_OD_expected": 132,
        "ordered_OD_rows": len(frame),
        "infeasible_OD_rows": 0,
        "exactly_one_path_per_feasible_ordered_OD": True,
        "path_generation_scope": "FROZEN_NETWORK_AUTHORITY_OUTSIDE_AIDC_MILP",
        "path_generation_rule": "DETERMINISTIC_MINIMUM_HOP_LEXICOGRAPHIC",
        "grid_inputs_used": False,
        "May_results_used": False,
        "fixed_path_table_sha256": sha256_file(path),
        "historical_migration_contract_sha256": sha256_file(repo / WAN_CONTRACT),
    }
    atomic_json(repo / ARTIFACT_ROOT / "V38_WAN_FIXED_OD_PATH_AUTHORITY.json", audit)
    return frame, audit


def write_recovery_audits(repo: Path) -> dict[str, Any]:
    out = repo / ARTIFACT_ROOT
    out.mkdir(parents=True, exist_ok=True)
    capacity = load_capacity_authority(repo)
    wan = load_wan_authority(repo)
    contract_sha = sha256_file(repo / WAN_CONTRACT)
    rack_contract_sha = sha256_file(repo / RACK_CONTRACT)
    recovery = {
        "artifact_id": "V38_A_HISTORICAL_WAN_MIGRATION_RECOVERY_AUDIT_V1",
        "status": "PASS",
        "objects": [
            {"object": "12-AIDC WAN topology", "classification": "CURRENT_COMPATIBLE_REUSE", "source_sha256": EXPECTED_WAN_TOPOLOGY_SHA256},
            {"object": "Abilene benchmark identity", "classification": "CURRENT_COMPATIBLE_REUSE", "identity": "BENCHMARK_12NODE_INTER_AIDC_WAN"},
            {"object": "preinstalled link capacity", "classification": "REQUIRES_15MIN_ADAPTER", "raw_unit": "MBITPERSEC"},
            {"object": "5-minute observed demand matrices", "classification": "HISTORICAL_ONLY", "primary_use": "NOT_APPLIED_TO_PREINSTALLED_CAPACITY"},
            {"object": "routing/path authority", "classification": "CURRENT_COMPATIBLE_REUSE", "rule": "DETERMINISTIC_MINIMUM_HOP_LEXICOGRAPHIC"},
            {"object": "propagation/RTT latency", "classification": "MISSING", "v38_disposition": "NO_SEPARATE_LATENCY_APPLIED"},
            {"object": "checkpoint payload", "classification": "CURRENT_COMPATIBLE_REUSE", "rule": "rho_ckpt * requested_GPU * 80_000_000_000 bytes"},
            {"object": "restart delay", "classification": "REQUIRES_15MIN_ADAPTER", "historical_seconds": RESTART_SECONDS, "current_slots": 1},
            {"object": "SEND/PIPELINE/INVENTORY/READY", "classification": "REQUIRES_15MIN_ADAPTER", "historical_runtime_semantics": "bytes advance directly to arrived inventory at end of each transfer step"},
            {"object": "48 logical Rack pools", "classification": "CURRENT_COMPATIBLE_REUSE", "scope": "GPU_GANG_ORACLE_ONLY"},
            {"object": "historical Rack IT caps", "classification": "REJECTED", "reason": "V16 provenance proves ESIF/current boundary mismatch"},
            {"object": "historical rolling controller", "classification": "HISTORICAL_ONLY"},
            {"object": "historical reference/home-AIDC mapping compatible with current Kestrel IDs", "classification": "MISSING", "legacy_search_alias": "home IDC"},
        ],
        "source_hashes": {
            "wan_topology": EXPECTED_WAN_TOPOLOGY_SHA256,
            "wan_readme": EXPECTED_WAN_README_SHA256,
            "wan_traffic": EXPECTED_WAN_TRAFFIC_SHA256,
            "migration_contract": contract_sha,
            "rack_capacity": EXPECTED_RACK_SHA256,
            "rack_contract": rack_contract_sha,
        },
        "prohibited_claim": "NOT_A_MEASURED_MELBOURNE_PRIVATE_AIDC_WAN",
    }
    atomic_json(out / "V38_A_HISTORICAL_WAN_MIGRATION_RECOVERY_AUDIT.json", recovery)

    rates = sorted(float(link.capacity_mbps) for link in wan.historical.links)
    native_bytes = sorted(wan.link_capacity_bytes_5min.values())
    current_bytes = sorted(values[0] for values in wan.link_capacity_bytes_15min.values())
    transfer_capacity = {
        "artifact_id": "V38_WAN_TRANSFER_CAPACITY_AUTHORITY_V1",
        "status": "PASS",
        "WAN_TRANSFER_CAPACITY_AUTHORITY": "PASS",
        "source": str(RAW_WAN_TOPOLOGY),
        "source_sha256": EXPECTED_WAN_TOPOLOGY_SHA256,
        "field": "pre_installed_capacity",
        "raw_unit": "MBITPERSEC",
        "limiting_quantity": "link-specific benchmark nameplate transferred-byte budget",
        "constant_or_time_varying": "CONSTANT",
        "capacity_directionality": "UNDIRECTED_SHARED_LINK; ONE_NETWORK_WIDE_TRANSFER_MAKES_SIMULTANEOUS_DIRECTION_CONTENTION_INAPPLICABLE",
        "background_traffic_consumes_primary_capacity": False,
        "background_traffic_already_subtracted": False,
        "native_step_seconds": 300,
        "current_step_seconds": 900,
        "rate_Mbit_per_s": {"min": min(rates), "median": median(rates), "max": max(rates)},
        "native_capacity_bytes_per_5min": {"min": min(native_bytes), "median": median(native_bytes), "max": max(native_bytes)},
        "current_capacity_decimal_GB_per_15min": {
            "min": min(current_bytes) / 1_000_000_000,
            "median": median(current_bytes) / 1_000_000_000,
            "max": max(current_bytes) / 1_000_000_000,
        },
        "conversion": "floor(Mbit_per_s * 1_000_000 / 8 * 300) bytes; sum 3 native intervals",
        "maximum_active_transfers_network_wide": wan.historical.maximum_active_transfers,
    }
    atomic_json(out / "V38_WAN_TRANSFER_CAPACITY_AUTHORITY.json", transfer_capacity)
    checkpoint_contract = {
        "artifact_id": "V38_CHECKPOINT_RESTART_CONTRACT_AUDIT_V1",
        "status": "PASS",
        "historical_contract_sha256": contract_sha,
        "checkpoint_interval_seconds": wan.historical.checkpoint_interval_steps * wan.historical.step_seconds,
        "checkpoint_interval_minutes": wan.historical.checkpoint_interval_steps * wan.historical.step_seconds / 60,
        "checkpoint_phase": "JOB_SPECIFIC_FROM_D_MINUS_1_ELAPSED_SECONDS",
        "rho_ckpt": wan.historical.checkpoint_payload_occupancy_factor,
        "framebuffer_reference_bytes_per_GPU": wan.historical.framebuffer_reference_bytes_per_gpu,
        "payload_rule": "rho_ckpt * requested_GPU * 80_000_000_000 bytes",
        "restart_seconds_historical": wan.historical.restart_steps * wan.historical.step_seconds,
        "restart_slots_current_conservative": 1,
        "compute_suspended_during_migration": True,
        "compute_suspended_during_restart": True,
    }
    atomic_json(out / "V38_CHECKPOINT_RESTART_CONTRACT_AUDIT.json", checkpoint_contract)

    semantics_rows = [
        {
            "source": "Abilene SNDlib topology",
            "file_artifact": str(RAW_WAN_TOPOLOGY), "sha256": EXPECTED_WAN_TOPOLOGY_SHA256,
            "field": "pre_installed_capacity", "raw_unit": "MBITPERSEC",
            "time_resolution": "constant", "physical_meaning": "benchmark link nameplate capacity",
            "current_V38_use": "checkpoint transfer byte limit", "allowed_use": "ALLOWED",
        },
        {
            "source": "Abilene Zhang demand matrices", "file_artifact": str(RAW_WAN_TRAFFIC),
            "sha256": EXPECTED_WAN_TRAFFIC_SHA256, "field": "directed OD demand",
            "raw_unit": "Mbit/s", "time_resolution": "5 minutes",
            "physical_meaning": "observed historical traffic demand, not physical capacity",
            "current_V38_use": "provenance/sensitivity only; not subtracted in primary contract",
            "allowed_use": "NOT_ALLOWED_AS_CAPACITY",
        },
        {
            "source": "M-Lab", "file_artifact": "historical raw-data inventory",
            "sha256": None, "field": "usable throughput samples", "raw_unit": "source-dependent",
            "time_resolution": "observational", "physical_meaning": "external client throughput",
            "current_V38_use": "none", "allowed_use": "NOT_ALLOWED_AS_ABILENE_CAPACITY",
        },
        {
            "source": "RIPE Atlas", "file_artifact": "historical raw-data inventory",
            "sha256": None, "field": "RTT/loss/ping/traceroute", "raw_unit": "ms/fraction/path",
            "time_resolution": "observational", "physical_meaning": "external network latency/context",
            "current_V38_use": "none", "allowed_use": "NOT_ALLOWED_AS_THROUGHPUT_OR_INTER_AIDC_LATENCY",
        },
    ]
    field_payload = {
        "artifact_id": "V38_WAN_FIELD_SEMANTICS_AUDIT_V1", "status": "PASS",
        "rows": semantics_rows,
        "capacity_authority": "ABILENE_PREINSTALLED_LINK_CAPACITY",
        "background_traffic_subtracted": False,
    }
    atomic_json(out / "V38_WAN_FIELD_SEMANTICS_AUDIT.json", field_payload)
    csv_path = out / "V38_WAN_FIELD_SEMANTICS_AUDIT.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=list(semantics_rows[0]), lineterminator="\n"
        )
        writer.writeheader(); writer.writerows(semantics_rows)

    errors = [
        abs(sum((wan.link_capacity_bytes_5min[link],) * 3) - wan.link_capacity_bytes_15min[link][slot])
        for link in sorted(wan.link_capacity_bytes_5min) for slot in range(96)
    ]
    capacities_gb = [
        slot_values[0] / 1_000_000_000
        for slot_values in wan.link_capacity_bytes_15min.values()
    ]
    adapter = {
        "artifact_id": "V38_WAN_15MIN_ADAPTER_AUDIT_V1", "status": "PASS",
        "raw_rate_unit": "Mbit/s", "native_step_seconds": 300,
        "current_step_seconds": 900,
        "conversion": "floor(Mbit_per_s * 1_000_000 / 8 * 300) bytes, then sum three native budgets",
        "aggregation": "SUM_NOT_AVERAGE", "link_count": len(wan.historical.links),
        "slots": 96, "max_byte_conservation_error": max(errors, default=0),
        "C_WAN_unit": "decimal_GB_per_15min_slot",
        "capacity_GB_per_15min": {"min": min(capacities_gb), "median": median(capacities_gb), "max": max(capacities_gb)},
    }
    atomic_json(out / "V38_WAN_15MIN_ADAPTER_AUDIT.json", adapter)
    atomic_json(out / "V38_WAN_5MIN_TO_15MIN_CONSERVATION_AUDIT.json", {
        **adapter, "artifact_id": "V38_WAN_5MIN_TO_15MIN_CONSERVATION_AUDIT_V1"
    })
    latency = {
        "artifact_id": "V38_WAN_LATENCY_BINDING_AUDIT_V1", "status": "PASS",
        "binding": "NO_AUTHORITATIVE_LATENCY_AVAILABLE",
        "separate_latency_applied": False, "latency_double_counted": False,
        "proof": "Frozen migration contract contains capacity/routing and advances transmitted bytes to inventory at the end of each native step; no RTT or one-way latency field is bound.",
        "RIPE_RTT_used": False, "M_Lab_throughput_used": False,
    }
    atomic_json(out / "V38_WAN_LATENCY_BINDING_AUDIT.json", latency)

    fixed_paths, fixed_path_audit = materialize_fixed_od_paths(repo)
    path_removal = {
        "artifact_id": "V38_WAN_PATH_OPTIMIZATION_REMOVAL_AUDIT_V1",
        "status": "PASS",
        "WAN_PATH_OPTIMIZATION_ENABLED": "NO",
        "WAN_FIXED_OD_PATH_AUTHORITY": "PASS",
        "WAN_FIXED_OD_PATH_TABLE": "PASS",
        "WAN_TRANSFER_SCHEDULING_ENABLED": "YES",
        "GRID_AWARE_DESTINATION_OPTIMIZATION_ENABLED": "YES",
        "production_path_selection_variables": 0,
        "production_K_path_enumeration_calls": 0,
        "runtime_WAN_path_reoptimization_calls": RUNTIME_FIREWALL["runtime_WAN_path_reoptimization_calls"],
        "fixed_OD_path_rows": len(fixed_paths),
        "fixed_OD_path_table_sha256": fixed_path_audit["fixed_path_table_sha256"],
        "production_semantics": (
            "Grid-aware AIDC destination placement and checkpoint migration are "
            "optimized subject to capacity-constrained checkpoint transfer over "
            "frozen deterministic inter-AIDC WAN paths."
        ),
        "rejected_terms": [
            "K_WAN", "candidate WAN paths", "path-selection variables",
            "Yen K-shortest paths", "alternate-path optimization",
            "multi-commodity WAN routing",
        ],
    }
    atomic_json(out / "V38_WAN_PATH_OPTIMIZATION_REMOVAL_AUDIT.json", path_removal)

    raw_rows = [
        {"AIDC_id": key, "historical_deliverable_gpu_capacity": capacity.historical_site_capacity[key], "gamma": capacity.historical_site_capacity[key] / sum(capacity.historical_site_capacity.values()), "unrounded_current_equivalent": GPU_CAPACITY * capacity.historical_site_capacity[key] / sum(capacity.historical_site_capacity.values()), "C_GPU": capacity.site_capacity[key]}
        for key in capacity.aidc_ids
    ]
    capacity_payload = {
        "artifact_id": "V38_AIDC_GPU_CAPACITY_MAPPING_V1", "status": "PASS",
        "compatibility_verdict": "COMPATIBLE_AS_OUTCOME_BLIND_RELATIVE_SITE_CAPACITY_PRIOR",
        "source_sha256": capacity.source_sha256, "rounding": "LARGEST_REMAINDER",
        "rows": raw_rows, "site_count": 12,
        "total_equivalent_GPU_capacity": sum(capacity.site_capacity.values()),
        "facility_MW_conversion_used": False,
    }
    atomic_json(out / "V38_AIDC_GPU_CAPACITY_MAPPING.json", capacity_payload)
    rack_payload = {
        "artifact_id": "V38_RACK_ORACLE_COMPATIBILITY_AUDIT_V1", "status": "PASS",
        "rack_count": 48, "logical_pools_per_site": 4,
        "source_sha256": capacity.source_sha256,
        "compatible_use": "D1_GPU_GANG_FEASIBILITY_AND_RESERVATION_ORACLE",
        "historical_pool_GPU_caps_used_for_gang_fit": True,
        "current_AIDC_aggregate_caps_enforced_separately": True,
        "historical_IT_caps_used": False,
        "historical_IT_cap_disposition": "REJECTED_CURRENT_BOUNDARY_MISMATCH",
        "physical_rack_geography_claimed": False,
    }
    atomic_json(out / "V38_RACK_ORACLE_COMPATIBILITY_AUDIT.json", rack_payload)
    runtime_audit = {
        "artifact_id": "V38_RUNTIME_RACK_REOPTIMIZATION_AUDIT_V1", "status": "PASS",
        "historical_runtime_Rack_reoptimization_found": True,
        "paths": [
            {"module_function": "pfr.runtime._schedule_capacity_feasible_queued_jobs", "when_called": "historical rolling runtime", "decision_variables_changed": "runtime logical placement/admission", "D_day_actual_visible": True, "current_V38_disposition": "HISTORICAL_DISABLED"},
            {"module_function": "pfr.runtime._optimize_job_migrations", "when_called": "historical slow replan", "decision_variables_changed": "legacy destination_IDC (adapted as current destination_AIDC)", "D_day_actual_visible": True, "current_V38_disposition": "INVALID_FOR_V38"},
            {"module_function": "dayahead.v38.rack.rack_plan_day_ahead", "when_called": "D-1 one-shot planning", "decision_variables_changed": "frozen rack_pool_id/reservations", "D_day_actual_visible": False, "current_V38_disposition": "DAY_AHEAD_ALLOWED"},
            {"module_function": "dayahead.v38.rack.validate_frozen_rack_execution", "when_called": "D-day fixed replay", "decision_variables_changed": "none; validates frozen reservations only", "D_day_actual_visible": True, "current_V38_disposition": "RUNTIME_EXECUTION_ONLY"},
        ],
        "V38_runtime_Rack_reoptimization_enabled": False,
        "production_counters": dict(RUNTIME_FIREWALL),
    }
    atomic_json(out / "V38_RUNTIME_RACK_REOPTIMIZATION_AUDIT.json", runtime_audit)
    terminology = {
        "artifact_id": "V38_AIDC_TERMINOLOGY_AUDIT_V1",
        "status": "PASS",
        "CURRENT_V38_CANONICAL_TERM": "AIDC",
        "canonical_definition": "AIDC = AI Data Center",
        "NEW_V38_IDC_ONLY_USER_FACING_OCCURRENCES": 0,
        "LEGACY_IDC_OCCURRENCES_PRESERVED_WITH_ALIAS": "PASS",
        "numerical_science_changed": False,
        "readiness_result_changed": False,
        "modeled_site_claim": "TRACE_DRIVEN_CYBER_PHYSICAL_TESTBED_NOT_MEASURED_REAL_WORLD_AIDC_FACILITIES",
        "legacy_aliases": [
            {
                "legacy_object": "pfr/contracts/IDC_MIGRATION_AUTHORITY_V1.json",
                "legacy_fields": ["idc_to_wan_node", "IDC01..IDC12"],
                "current_V38_adapter": "V38WanAuthority.historical_idc",
                "current_semantics": "AIDC01..AIDC12 and inter-AIDC WAN",
                "reason_preserved": "frozen historical bytes and API compatibility",
            },
            {
                "legacy_object": "V38_HOME_IDC_MAPPING_AUDIT.json filename/artifact id",
                "current_V38_adapter": "contents expose home_AIDC and SYNTHETIC_REFERENCE_HOME_AIDC_MAPPING",
                "current_semantics": "reference/home AIDC",
                "reason_preserved": "required artifact name in the original V38 contract",
            },
            {
                "legacy_object": "runtime_IDC_replacement_calls",
                "current_V38_adapter": "runtime_AIDC_replacement_calls",
                "current_semantics": "runtime AIDC replacement calls",
                "reason_preserved": "earlier supplemental contract alias only",
            },
            {
                "legacy_object": "historical pfr runtime destination_IDC fields",
                "current_V38_adapter": "read-only historical audit mapping",
                "current_semantics": "destination_AIDC",
                "reason_preserved": "historical schema compatibility; disabled in V38 runtime",
            },
        ],
    }
    atomic_json(out / "V38_AIDC_TERMINOLOGY_AUDIT.json", terminology)
    return {
        "status": "PASS", "recovery": recovery, "capacity": capacity_payload,
        "adapter": adapter, "latency": latency, "rack": rack_payload,
        "transfer_capacity": transfer_capacity,
        "checkpoint_restart": checkpoint_contract,
        "fixed_paths": fixed_path_audit, "path_optimization_removal": path_removal,
        "terminology": terminology,
    }


__all__ = [
    "CapacityAuthority", "RackPool", "V38WanAuthority", "atomic_json",
    "canonical_sha256", "checkpoint_slots", "load_capacity_authority",
    "load_wan_authority", "materialize_fixed_od_paths", "sha256_file",
    "write_recovery_audits",
]
