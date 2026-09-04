from __future__ import annotations

from decimal import Decimal
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from dayahead.v38.authority import load_capacity_authority, load_wan_authority
from dayahead.v38.rack import rack_plan_day_ahead, validate_frozen_rack_execution
from dayahead.v38.wan import simulate_frozen_migration
from dayahead.v39a.contracts import (
    ARTIFACT_ROOT,
    CENTER_SWING_W_PER_GPU,
    C_REF_W_PER_GPU,
    FULL_ACTIVE_IT_KW,
    GPU_CAPACITY,
    IDLE_W_PER_GPU,
    RUNTIME_FIREWALL,
    SITE_CAPACITY,
    V37_DAY_ROOT,
    V38_FAIL_EVIDENCE_HEAD,
    VOLTAGE_AUTHORITY,
    VOLTAGE_FROZEN_SHA256,
    VOLTAGE_LOGICAL_LF_SHA256,
)
from dayahead.v39a.power import (
    aggregate_it_power_kw,
    frozen_site_to_pcc,
    site_it_power_kw,
    validate_power_conservation,
)
from dayahead.v39a.spatial import (
    ActivityJob,
    hard_gang_cardinality_conflicts,
    plan_causal_day,
    production_activity,
)


REPO = Path(__file__).resolve().parents[2]
ARTIFACT = REPO / ARTIFACT_ROOT


def _json(name: str) -> dict:
    return json.loads((ARTIFACT / name).read_text(encoding="utf-8"))


def test_frozen_site_capacity_is_exact_and_sums_to_624() -> None:
    capacity = load_capacity_authority(REPO)
    assert dict(capacity.site_capacity) == SITE_CAPACITY
    assert sum(capacity.site_capacity.values()) == GPU_CAPACITY == 624
    audit = _json("V39A_SITE_CAPACITY_AUTHORITY.json")
    assert audit["status"] == "PASS"
    assert audit["source_SHA256"] == "4546c0672a4d25aa5c7c92ea90fb90ec8d3c009dda426939179b293abdeb83c0"


def test_v37_120_slot_coordinates_are_mapped_with_offset_24() -> None:
    day = "2025-05-21"
    schedule = pd.read_parquet(REPO / V37_DAY_ROOT / day / "V37_R4A_RW_SCHEDULE.parquet")
    jobs = production_activity(schedule)
    profile = np.zeros(96, dtype=np.int64)
    for job in jobs:
        profile[job.active_start_slot:job.active_end_slot] += job.requested_GPU
    v37 = pd.read_parquet(REPO / V37_DAY_ROOT / day / "V37_R4A_GPU_IT_TRAJECTORY.parquet")
    assert np.array_equal(profile, v37["N_active_RW"].to_numpy(np.int64))


def test_hard_32_gpu_gang_cardinality_conflict_is_slot_local() -> None:
    schedule = pd.read_parquet(
        REPO / V37_DAY_ROOT / "2025-05-21" / "V37_R4A_RW_SCHEDULE.parquet"
    )
    conflicts = hard_gang_cardinality_conflicts(
        production_activity(schedule), load_capacity_authority(REPO)
    )
    first = conflicts[0]
    assert first["slot"] == 60
    assert first["requested_GPU"] == 32
    assert first["active_gang_count"] == 15
    assert first["maximum_hostable_gang_count"] == 14


def test_gurobi_relaxation_is_infeasible_and_iis_is_persisted() -> None:
    audit = _json("V39A_SPATIAL_FEASIBILITY_AUDIT.json")
    assert audit["status"] == "FAIL"
    assert audit["models_built"] == 62
    assert audit["models_infeasible"] == 14
    assert audit["first_IIS"]["solver_status"] == 3
    assert audit["first_IIS"]["IIS_constraint_count"] == 11
    assert (REPO / audit["first_IIS"]["IIS_path"]).is_file()


def test_pending_initial_placement_has_no_source_or_migration() -> None:
    jobs = (
        ActivityJob("pending", "PENDING", 4, 0, 8),
        ActivityJob("running", "RUNNING", 4, 0, 8),
    )
    plan = plan_causal_day(jobs, load_capacity_authority(REPO), {"running": "AIDC01"})
    assert plan.status == "OPTIMAL"
    pending = next(row for row in plan.decisions if row.job_uid == "pending")
    assert pending.initial_AIDC is not None
    assert pending.source_AIDC is None
    assert pending.migration_selected is False


def test_running_current_aidc_is_carried_without_daily_remap() -> None:
    job = ActivityJob("running", "RUNNING", 4, 0, 8)
    first = plan_causal_day((job,), load_capacity_authority(REPO), {"running": "AIDC03"})
    second = plan_causal_day((job,), load_capacity_authority(REPO), first.next_running_state)
    assert first.decisions[0].current_AIDC == "AIDC03"
    assert second.decisions[0].current_AIDC == "AIDC03"
    assert first.daily_remap_count == second.daily_remap_count == 0


def test_no_job_computes_at_two_aidcs_and_gangs_are_not_split() -> None:
    jobs = tuple(ActivityJob(f"j{i}", "PENDING", 4, 0, 4) for i in range(6))
    plan = plan_causal_day(jobs, load_capacity_authority(REPO), {})
    assert plan.status == "OPTIMAL"
    assert len(plan.decisions) == len({row.job_uid for row in plan.decisions})
    assert all(row.requested_GPU == 4 for row in plan.decisions)


def test_v38_checkpoint_state_transition_has_no_compute_overlap() -> None:
    trace = simulate_frozen_migration(
        selected=True,
        payload_bytes=320_000_000_000,
        checkpoint_slot=2,
        capacity_bytes_by_slot=[0, 0, 160_000_000_000, 160_000_000_000, 0, 0, 0, 0, 0, 0],
        requested_gpu=4,
        required_compute_slots=5,
    )
    assert trace.ready_slot == 4
    assert trace.compute_resume_slot == 5
    assert all(
        not row["compute"]
        for row in trace.rows
        if row["state_at_start"] in {"MIGRATING", "RESTARTING"}
    )
    assert all(
        row["source_active_GPU"] + row["destination_active_GPU"] <= 4
        for row in trace.rows
    )


def test_wan_authority_has_fixed_paths_capacity_and_no_latency() -> None:
    wan = load_wan_authority(REPO)
    audit = _json("V39A_WAN_MIGRATION_AUDIT.json")
    assert audit["fixed_ordered_OD_paths"] == 132
    assert audit["WAN_path_optimization"] == "NO"
    assert audit["maximum_simultaneous_network_wide_transfers"] == 1
    assert audit["latency"] == "NO_AUTHORITATIVE_LATENCY_AVAILABLE"
    assert wan.payload_bytes(4) == 320_000_000_000


def test_rack_oracle_assigns_whole_gang_and_runtime_reopt_is_zero() -> None:
    capacity = load_capacity_authority(REPO)
    reservations = rack_plan_day_ahead([{
        "job_uid": "pending", "operating_day": "2025-04-01", "temporal_mode": "RW",
        "destination_AIDC": "AIDC09", "requested_GPU": 32,
        "active_start_slot": 0, "active_end_slot": 4,
    }], capacity)
    assert len(reservations) == 1
    validation = validate_frozen_rack_execution(reservations, capacity)
    assert validation["status"] == "PASS"
    assert validation["runtime_counters"] == RUNTIME_FIREWALL
    assert all(value == 0 for value in validation["runtime_counters"].values())


def test_site_power_formula_and_full_active_anchor_conserve() -> None:
    assert IDLE_W_PER_GPU == Decimal("104.1606964512843")
    active = dict(SITE_CAPACITY)
    check = validate_power_conservation(SITE_CAPACITY, active)
    assert check["status"] == "PASS"
    site_sum = sum(
        (site_it_power_kw(cap, cap) for cap in SITE_CAPACITY.values()), Decimal(0)
    )
    assert abs(site_sum - FULL_ACTIVE_IT_KW) <= Decimal("2e-12")
    assert aggregate_it_power_kw(624) == FULL_ACTIVE_IT_KW
    assert C_REF_W_PER_GPU - CENTER_SWING_W_PER_GPU == IDLE_W_PER_GPU


def test_all_v37_aggregate_gpu_and_power_cells_pass_algebraic_equivalence() -> None:
    audit = _json("V39A_AGGREGATE_EQUIVALENCE.json")
    assert audit["status"] == "PASS"
    assert audit["checked_day_mode_slots"] == 31 * 2 * 96
    assert Decimal(audit["RW_site_to_aggregate_max_error_kW"]) <= Decimal(audit["tolerance_kW"])
    assert Decimal(audit["RSP_site_to_aggregate_max_error_kW"]) <= Decimal(audit["tolerance_kW"])
    assert audit["case_trajectory_identity"]["B0_equals_B2"] is True
    assert audit["case_trajectory_identity"]["B1_equals_B3"] is True


def test_site_to_pcc_mapping_is_frozen_and_canonical_aidc_keyed() -> None:
    mapping = frozen_site_to_pcc(REPO)
    assert tuple(mapping) == tuple(SITE_CAPACITY)
    assert len(set(mapping.values())) == 12
    audit = _json("V39A_RACK_ASSIGNMENT_AUDIT.json")
    assert audit["AIDC_to_PCC_mapping_status"] == "PASS"


def test_production_trajectory_parquets_are_explicitly_blocked_not_fabricated() -> None:
    for name in (
        "V39A_SITE_GPU_TRAJECTORIES.parquet",
        "V39A_SITE_IT_POWER_TRAJECTORIES.parquet",
        "V39A_SITE_PCC_POWER_TRAJECTORIES.parquet",
    ):
        frame = pd.read_parquet(ARTIFACT / name)
        assert frame.empty
        assert frame.attrs["artifact_status"] == "BLOCKED_NOT_MATERIALIZED"
        assert frame.attrs["blocker"] == "V39A_SPATIAL_FEASIBILITY_INFEASIBLE"


def test_causality_firewalls_and_may_launch_gate_are_closed() -> None:
    initial = _json("V39A_CAUSAL_INITIAL_STATE_AUDIT.json")
    assert initial["status"] == "PASS"
    assert initial["jobs_initialized"] == 243
    assert initial["future_fields_read_count"] == 0
    assert initial["May_result_reads"] == 0
    assert initial["grid_or_Fresh_result_reads"] == 0
    preflight = _json("V39A_MAY_31DAY_INPUT_PREFLIGHT.json")
    assert preflight["READY"] == 0
    assert preflight["NOT_READY"] == 31
    assert preflight["missing"] == 0
    assert preflight["true_production_loader_PASS_count"] == 0
    assert preflight["MAY_CAMPAIGN_LAUNCH_READY"] == "NO"
    assert preflight["MAY_STARTED"] == "NO"


def test_voltage_authority_bytes_are_exact_and_logically_equivalent() -> None:
    raw = (REPO / VOLTAGE_AUTHORITY).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == VOLTAGE_FROZEN_SHA256
    assert hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest() == VOLTAGE_LOGICAL_LF_SHA256
    audit = _json("V39A_VOLTAGE_AUTHORITY_BYTE_STABILITY_AUDIT.json")
    assert audit["status"] == "PASS"
    assert audit["byte_preservation_status"] == "PASS"
    assert audit["content_equivalence_status"] == "PASS"
    assert audit["regression_status"] == "PASS"


def test_v38_failure_lineage_and_v39a_fingerprint_are_distinct() -> None:
    fingerprint = _json("V39A_IMPLEMENTATION_FINGERPRINT.json")
    assert fingerprint["V38_FAIL_EVIDENCE_HEAD"] == V38_FAIL_EVIDENCE_HEAD
    assert fingerprint["V39A_IMPLEMENTATION_FINGERPRINT"] != fingerprint["V38_IMPLEMENTATION_FINGERPRINT"]
    assert len(fingerprint["V39A_IMPLEMENTATION_FINGERPRINT"]) == 64
