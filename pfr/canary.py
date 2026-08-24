"""Deterministic no-external-solver IDC migration release canary."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Mapping

from .methods import ComparisonMethod, ExperimentAuthority, MethodFactory
from .migration import MigrationAuthority
from .power import H100UtilizationPowerCurve
from .risk_calibration import (
    AUTHORITY_ID,
    FrozenRiskCalibration,
    RISK_FAMILY_SCALES,
)
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
        risk_calibration_authority=FrozenRiskCalibration(
            authority_id=AUTHORITY_ID,
            alpha=0.05,
            source_method="B6",
            source_period="2025-01",
            calibration_dates=tuple(
                (date(2025, 1, 1) + timedelta(days=offset)).isoformat()
                for offset in range(31)
            ),
            finite_sample_rank=31,
            normalized_joint_quantile=0.0,
            predeclared_scales=dict(RISK_FAMILY_SCALES),
            calibrated_increments={family: 0.0 for family in RISK_FAMILY_SCALES},
            source_audit_sha256="d" * 64,
            artifact_sha256="e" * 64,
        ),
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
        frames=_frames(authority, last_issue=106),
        initial=initial,
        representative_week_id="IDC_MIGRATION_CANARY_B8_PRECHECKPOINT",
        output=b8_root,
    )
    b8_markers = [_read_marker(b8_root, "B8", issue) for issue in range(100, 106)]
    b8_boundary = _read_marker(b8_root, "B8", 106)
    b8_precheckpoint_blocked = all(
        not marker["migration_started"]
        and int(marker["wan_bytes_transferred_step"]) == 0
        for marker in b8_markers
    )
    b8_episode_boundary_blocked = bool(
        not b8_boundary["migration_started"]
        and int(b8_boundary["wan_bytes_transferred_step"]) == 0
        and int(
            b8_boundary["spatial_optimizer_certificate"].get(
                "episode_boundary_blocked_candidate_count", 0
            )
        )
        > 0
    )
    work_conserved = bool(
        len(completed) == 1
        and completed[0]["work_conserved"] is True
        and completed[0]["remaining_work_gpu_hours_before"]
        == completed[0]["remaining_work_gpu_hours_after"]
    )
    prediction_actual = restart.get("migration_prediction_actual_events", [])
    prediction_actual_audit = bool(
        len(prediction_actual) == 1
        and prediction_actual[0].get("predicted_total_downtime_steps")
        == prediction_actual[0].get("realized_total_downtime_steps")
        and prediction_actual[0].get("total_downtime_error_seconds") == 0
        and prediction_actual[0].get("payload_error_bytes") == 0
        and prediction_actual[0].get("external_observed_wan_telemetry") is False
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
        and prediction_actual_audit
        and b8_summary["status"] == "PASS"
        and b8_summary["full_replan_count"] == 7
        and b8_precheckpoint_blocked
        and b8_episode_boundary_blocked
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
        "migration_prediction_actual_audit": prediction_actual_audit,
        "migration_prediction_actual_event": (
            prediction_actual[0] if len(prediction_actual) == 1 else None
        ),
        "b8_every_five_minute_full_replans": b8_summary["full_replan_count"],
        "b8_precheckpoint_migration_blocked": b8_precheckpoint_blocked,
        "b8_episode_boundary_migration_blocked": b8_episode_boundary_blocked,
    }
