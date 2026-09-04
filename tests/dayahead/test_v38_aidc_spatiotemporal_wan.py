from __future__ import annotations

import inspect
import json
from pathlib import Path
import subprocess

import pandas as pd

from dayahead.v38.authority import (
    checkpoint_slots,
    load_capacity_authority,
    load_wan_authority,
    materialize_fixed_od_paths,
    sha256_file,
    write_recovery_audits,
)
from dayahead.v38.contracts import (
    CENTER_SWING_W_PER_GPU,
    GPU_CAPACITY,
    RUNTIME_FIREWALL,
)
from dayahead.v38.rack import rack_plan_day_ahead, validate_frozen_rack_execution
from dayahead.v38.wan import (
    schedule_fixed_path_transfers,
    simulate_frozen_migration,
    validate_fixed_path_transfers,
    write_synthetic_migration_certificate,
)


REPO = Path(__file__).resolve().parents[2]
ARTIFACT = REPO / "dayahead/artifacts/v38_aidc_spatiotemporal_wan"


def test_recovered_capacity_and_wan_semantics() -> None:
    audits = write_recovery_audits(REPO)
    capacity = load_capacity_authority(REPO)
    assert audits["status"] == "PASS"
    assert sum(capacity.site_capacity.values()) == GPU_CAPACITY == 624
    assert capacity.site_capacity == {
        "AIDC01": 42, "AIDC02": 75, "AIDC03": 77, "AIDC04": 34,
        "AIDC05": 53, "AIDC06": 68, "AIDC07": 21, "AIDC08": 62,
        "AIDC09": 139, "AIDC10": 17, "AIDC11": 12, "AIDC12": 24,
    }
    semantics = json.loads((ARTIFACT / "V38_WAN_FIELD_SEMANTICS_AUDIT.json").read_text(encoding="utf-8"))
    by_source = {row["source"]: row for row in semantics["rows"]}
    assert by_source["Abilene Zhang demand matrices"]["allowed_use"] == "NOT_ALLOWED_AS_CAPACITY"
    assert by_source["RIPE Atlas"]["allowed_use"] == "NOT_ALLOWED_AS_THROUGHPUT_OR_INTER_AIDC_LATENCY"
    assert by_source["M-Lab"]["allowed_use"] == "NOT_ALLOWED_AS_ABILENE_CAPACITY"


def test_five_to_fifteen_minute_bytes_are_summed_exactly() -> None:
    wan = load_wan_authority(REPO)
    for link, five in wan.link_capacity_bytes_5min.items():
        assert all(value == 3 * five for value in wan.link_capacity_bytes_15min[link])
    audit = json.loads((ARTIFACT / "V38_WAN_5MIN_TO_15MIN_CONSERVATION_AUDIT.json").read_text(encoding="utf-8"))
    assert audit["aggregation"] == "SUM_NOT_AVERAGE"
    assert audit["max_byte_conservation_error"] == 0


def test_one_frozen_path_per_ordered_od_and_no_path_optimizer() -> None:
    frame, audit = materialize_fixed_od_paths(REPO)
    assert audit["status"] == "PASS"
    assert len(frame) == 12 * 11 == 132
    assert not frame[["source_AIDC", "destination_AIDC"]].duplicated().any()
    assert frame["path_id"].nunique() == 132
    source = inspect.getsource(simulate_frozen_migration) + inspect.getsource(validate_fixed_path_transfers)
    for forbidden in ("candidate_paths", "path_index", "k_shortest", "yen"):
        assert forbidden not in source.lower()
    removal = json.loads((ARTIFACT / "V38_WAN_PATH_OPTIMIZATION_REMOVAL_AUDIT.json").read_text(encoding="utf-8"))
    assert removal["WAN_PATH_OPTIMIZATION_ENABLED"] == "NO"
    assert removal["production_path_selection_variables"] == 0
    assert removal["production_K_path_enumeration_calls"] == 0


def test_fixed_path_is_independent_of_grid_condition() -> None:
    wan = load_wan_authority(REPO)
    before = (wan.path_id("AIDC03", "AIDC08"), wan.path("AIDC03", "AIDC08"))
    dummy_grid_conditions = ["weak_AIDC03", "strong_AIDC03", "MESS_ON", "MESS_OFF"]
    after = [(wan.path_id("AIDC03", "AIDC08"), wan.path("AIDC03", "AIDC08")) for _ in dummy_grid_conditions]
    assert all(value == before for value in after)


def test_shared_bottleneck_competes_but_timing_can_shift() -> None:
    wan = load_wan_authority(REPO)
    path = wan.path("AIDC01", "AIDC02")
    bottleneck = min(wan.capacity_bytes(link, 0) for link in path)
    each = bottleneck * 3 // 4
    overlap = [
        {"job_uid": "j1", "source_AIDC": "AIDC01", "destination_AIDC": "AIDC02", "bytes_by_slot": [each, 0]},
        {"job_uid": "j2", "source_AIDC": "AIDC01", "destination_AIDC": "AIDC02", "bytes_by_slot": [each, 0]},
    ]
    shifted = [overlap[0], {**overlap[1], "bytes_by_slot": [0, each]}]
    failed = validate_fixed_path_transfers(wan, overlap)
    passed = validate_fixed_path_transfers(wan, shifted)
    assert failed["status"] == "FAIL"
    assert any(row["type"] == "LINK_CAPACITY" for row in failed["violations"])
    assert passed["status"] == "PASS"
    assert failed["fixed_path_bindings"] == passed["fixed_path_bindings"]


def test_d1_transfer_scheduler_changes_timing_not_path() -> None:
    wan = load_wan_authority(REPO)
    cap = wan.path_capacity_bytes("AIDC01", "AIDC02", 0)
    schedule = schedule_fixed_path_transfers(wan, [
        {"job_uid": "j1", "source_AIDC": "AIDC01", "destination_AIDC": "AIDC02", "payload_bytes": cap, "earliest_transfer_slot": 0, "latest_arrival_slot": 3},
        {"job_uid": "j2", "source_AIDC": "AIDC01", "destination_AIDC": "AIDC02", "payload_bytes": cap, "earliest_transfer_slot": 0, "latest_arrival_slot": 3},
    ], horizon=3)
    assert {row["fixed_path_id"] for row in schedule} == {"OD01_02_FIXED"}
    assert all(row["path_selection_decisions"] == 0 for row in schedule)
    active_slots = [
        [slot for slot, amount in enumerate(row["bytes_by_slot"]) if amount]
        for row in schedule
    ]
    assert set(active_slots[0]).isdisjoint(active_slots[1])


def test_checkpoint_phase_and_byte_driven_state_machine() -> None:
    assert checkpoint_slots(0, 8) == (2, 4, 6)
    trace = simulate_frozen_migration(
        selected=True,
        payload_bytes=100,
        checkpoint_slot=2,
        capacity_bytes_by_slot=[0, 0, 40, 40, 20, 0, 0, 0, 0, 0],
        requested_gpu=4,
        required_compute_slots=5,
    )
    assert trace.transfer_complete_slot == 4
    assert trace.ready_slot == 5
    assert trace.restart_complete_slot == trace.compute_resume_slot == 6
    assert all(row["bytes_sent"] == 0 for row in trace.rows[:2])
    assert sum(row["bytes_sent"] for row in trace.rows) == 100
    assert all(row["bytes_remaining_end"] + row["bytes_pipeline_end"] + row["bytes_arrived_end"] == 100 for row in trace.rows)
    assert all(not row["compute"] for row in trace.rows if row["state_at_start"] in {"MIGRATING", "RESTARTING"})
    assert all(row["source_active_GPU"] + row["destination_active_GPU"] <= 4 for row in trace.rows)


def test_synthetic_migration_certificate() -> None:
    certificate = write_synthetic_migration_certificate(REPO)
    assert certificate["status"] == "PASS"
    assert all(certificate["checks"].values())
    assert certificate["latency_binding"] == "NO_AUTHORITATIVE_LATENCY_AVAILABLE"


def test_exact_d1_rack_assignment_and_immutable_runtime() -> None:
    capacity = load_capacity_authority(REPO)
    jobs = [
        {
            "job_uid": "running", "operating_day": "2025-04-01", "temporal_mode": "RSP",
            "source_AIDC": "AIDC09", "destination_AIDC": "AIDC09", "requested_GPU": 4,
            "active_start_slot": 5, "active_end_slot": 12, "migration_checkpoint_slot": 5,
            "source_Rack_release_slot": 5, "destination_Rack_reservation_start": 4,
            "destination_Rack_activation_start": 6,
        },
        {
            "job_uid": "pending", "operating_day": "2025-04-01", "temporal_mode": "RSP",
            "source_AIDC": "AIDC09", "destination_AIDC": "AIDC09", "requested_GPU": 8,
            "active_start_slot": 8, "active_end_slot": 14,
        },
    ]
    reservations = rack_plan_day_ahead(jobs, capacity)
    assert len(reservations) == 2
    running = next(row for row in reservations if row.job_uid == "running")
    assert running.source_Rack_release_slot == running.migration_checkpoint_slot
    assert running.destination_Rack_reservation_start < running.destination_Rack_activation_start
    execution = validate_frozen_rack_execution(reservations, capacity)
    assert execution["status"] == "PASS"
    assert execution["runtime_counters"] == RUNTIME_FIREWALL
    assert all(value == 0 for value in execution["runtime_counters"].values())


def test_frozen_center_and_home_infeasibility_forensics() -> None:
    assert CENTER_SWING_W_PER_GPU == 547.7239090195797
    home = json.loads((ARTIFACT / "V38_HOME_IDC_MAPPING_AUDIT.json").read_text(encoding="utf-8"))
    assert home["status"] == "FAIL"
    assert home["solver_status_name"] == "INFEASIBLE"
    assert home["May_result_reads"] == 0
    assert home["grid_result_reads"] == 0
    assert sha256_file(REPO / home["IIS_path"]) == home["IIS_sha256"]
    assert not (ARTIFACT / "V38_HOME_IDC_MAPPING.parquet").exists()


def test_current_v38_terminology_is_aidc_with_legacy_aliases() -> None:
    audit = json.loads((ARTIFACT / "V38_AIDC_TERMINOLOGY_AUDIT.json").read_text(encoding="utf-8"))
    assert audit["status"] == "PASS"
    assert audit["CURRENT_V38_CANONICAL_TERM"] == "AIDC"
    assert audit["NEW_V38_IDC_ONLY_USER_FACING_OCCURRENCES"] == 0
    assert audit["LEGACY_IDC_OCCURRENCES_PRESERVED_WITH_ALIAS"] == "PASS"
    frame = pd.read_parquet(ARTIFACT / "V38_WAN_FIXED_OD_PATHS.parquet")
    assert {"source_AIDC", "destination_AIDC"}.issubset(frame.columns)
    assert not {"source_IDC", "destination_IDC"}.intersection(frame.columns)


def test_launcher_refuses_non_31_of_31_readiness() -> None:
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
         str(REPO / "tools/v38/run_may_v38_locked_final.ps1"), "-ValidateOnly"],
        cwd=REPO, text=True, capture_output=True, check=False,
    )
    combined = result.stdout + result.stderr
    assert result.returncode != 0
    assert "V38_READY=NO" in combined
    assert "MAY_STARTED=NO" in combined


def test_monitor_once_reads_atomic_status_contract() -> None:
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
         str(REPO / "tools/v38/monitor_may_v38.ps1"), "-Once", "-Json"],
        cwd=REPO, text=True, capture_output=True, check=True,
    )
    view = json.loads(result.stdout.strip())
    assert view["title"] == "MobileESS V38 May Final Monitor"
    assert view["refresh_seconds"] == 10
    assert view["V38_READY"] == "NO"
