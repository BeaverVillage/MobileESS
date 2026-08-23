"""Deterministic no-external-solver IDC migration release canary."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .methods import ComparisonMethod, ExperimentAuthority, MethodFactory
from .migration import MigrationAuthority
from .power import H100UtilizationPowerCurve
from .runtime import (
    CausalExperimentFrame,
    OperationalTrainingJob,
    PhysicalCommit,
    PfrRuntimeRunner,
    RuntimeInitialState,
)
from .safety import ExactAcResult


class _CanaryPhysical:
    def verify_fresh(self, **kwargs: Any) -> PhysicalCommit:
        raw = {
            "root_import_p_kw": 100.0,
            "voltage_min_pu": 0.98,
            "voltage_max_pu": 1.02,
            "line_max_loading_pu": 0.5,
            "transformer_max_kva_loading_pu": 0.5,
            "transformer_max_current_loading_pu": 0.5,
            "hard_constraint_pass": True,
        }
        return PhysicalCommit(
            ExactAcResult(True, "PASS", True, True, 0.98, 1.02, 0.5, 0.5, 0),
            raw,
            False,
            True,
        )


def _job(index: int, authority: MigrationAuthority) -> OperationalTrainingJob:
    return OperationalTrainingJob(
        f"canary-j{index}",
        "IDC01",
        100,
        102,
        130,
        1,
        7200,
        0.01,
        None,
        f"canary-source-j{index}",
        authority.checkpoint_payload_bytes(1),
        authority.fingerprint,
    )


def _frames(
    authority: MigrationAuthority, *, last_issue: int
) -> tuple[CausalExperimentFrame, ...]:
    jobs = (_job(1, authority), _job(2, authority))
    return tuple(
        CausalExperimentFrame(
            issue,
            100.0,
            100.0,
            1000.0,
            100.0,
            jobs if issue == 100 else (),
            format(issue, "064x"),
            workload_reserve_gpu={
                site: (20.0 if issue >= 101 and site == "IDC01" else 0.0)
                for site in authority.idc_to_wan_node
            },
        )
        for issue in range(100, last_issue + 1)
    )


def _read_marker(root: Path, method: str, issue: int) -> Mapping[str, Any]:
    return json.loads(
        (root / method / f"issue_{issue:06d}/COMMIT_MARKER.json").read_text(
            encoding="utf-8"
        )
    )


def run_idc_migration_canary(
    authority: MigrationAuthority, output: Path
) -> Mapping[str, Any]:
    hashes = tuple(format(index, "064x") for index in range(1, 8))
    factory = MethodFactory(ExperimentAuthority(*hashes))
    curve = H100UtilizationPowerCurve(
        (0.0, 1.0), (0.1, 0.65), "a" * 64, ("b" * 64,)
    )
    initial = RuntimeInitialState(
        100,
        "c" * 64,
        {f"MESS{index:02d}": 760.0 for index in range(1, 5)},
        {f"MESS{index:02d}": f"STA{index:02d}" for index in range(1, 5)},
    )
    runner = PfrRuntimeRunner(
        power_curve=curve,
        physical_backend=_CanaryPhysical(),
        migration_authority=authority,
    )
    b5 = factory.create(ComparisonMethod.B5)
    b5_root = output / "b5"
    b5_summary = runner.run_method(
        config=b5,
        frames=_frames(authority, last_issue=108),
        initial=initial,
        representative_week_id="IDC_MIGRATION_CANARY_B5",
        output=b5_root,
    )
    start = _read_marker(b5_root, "B5", 106)
    restart = _read_marker(b5_root, "B5", 107)
    started = start["migration_started"]
    completed = start["migration_completed"]
    job_uid = str(started[0]["job_uid"]) if len(started) == 1 else ""
    start_state = start["migration_job_state_evidence"].get(job_uid, {})
    restart_state = restart["migration_job_state_evidence"].get(job_uid, {})

    b8 = factory.create(ComparisonMethod.B8)
    b8_root = output / "b8"
    b8_summary = runner.run_method(
        config=b8,
        frames=_frames(authority, last_issue=105),
        initial=initial,
        representative_week_id="IDC_MIGRATION_CANARY_B8_PRECHECKPOINT",
        output=b8_root,
    )
    b8_markers = [_read_marker(b8_root, "B8", issue) for issue in range(100, 106)]
    b8_precheckpoint_blocked = all(
        not marker["migration_started"]
        and int(marker["wan_bytes_transferred_step"]) == 0
        for marker in b8_markers
    )
    work_conserved = bool(
        len(completed) == 1
        and completed[0]["work_conserved"] is True
        and completed[0]["remaining_work_gpu_hours_before"]
        == completed[0]["remaining_work_gpu_hours_after"]
    )
    passed = bool(
        b5_summary["status"] == "PASS"
        and len(started) == 1
        and int(start["wan_bytes_transferred_step"]) > 0
        and len(completed) == 1
        and start_state.get("lifecycle") == "RESTARTING"
        and restart_state.get("lifecycle") == "RUNNING"
        and start_state.get("destination_idc")
        == restart_state.get("destination_idc")
        and started[0]["source_idc"] != restart_state.get("destination_idc")
        and len(restart["migration_restarts_completed"]) == 1
        and work_conserved
        and b8_summary["status"] == "PASS"
        and b8_summary["full_replan_count"] == 6
        and b8_precheckpoint_blocked
    )
    return {
        "pass": passed,
        "status": "PASS" if passed else "FAIL_CLOSED",
        "migration_authority_sha256": authority.fingerprint,
        "migration_contract_sha256": authority.contract_fingerprint,
        "checkpoint_payload_occupancy_factor": (
            authority.checkpoint_payload_occupancy_factor
        ),
        "checkpoint_ready_then_migration_started": len(started) == 1,
        "wan_bytes_transferred": int(start["wan_bytes_transferred_step"]),
        "transfer_completed": len(completed) == 1,
        "restart_state_observed": start_state.get("lifecycle") == "RESTARTING",
        "running_at_different_idc_after_restart": bool(
            restart_state.get("lifecycle") == "RUNNING"
            and started
            and started[0]["source_idc"] != restart_state.get("destination_idc")
        ),
        "remaining_compute_work_conserved": work_conserved,
        "b8_every_five_minute_full_replans": b8_summary["full_replan_count"],
        "b8_precheckpoint_migration_blocked": b8_precheckpoint_blocked,
    }
