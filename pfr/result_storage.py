"""Electrical-stress campaign result materialization.

COMMIT_MARKER.json remains the atomic source evidence.  These Parquet tables
are deterministic, analysis-facing projections of those committed records.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence


RESULT_SCHEMA_VERSION = "ELECTRICAL_STRESS_RESULT_SCHEMA_V1"

ISSUE_REQUIRED_COLUMNS = (
    "date", "timestamp", "issue", "method_id", "method_order", "plan_id",
    "replan_id", "plan_origin_timestamp", "plan_age_steps", "objective_id",
    "predicted_worst_stress_z", "predicted_stress_exposure",
    "predicted_voltage_stress_max", "predicted_line_stress_max",
    "predicted_transformer_stress_max", "predicted_worst_stress_type",
    "predicted_worst_element_id", "predicted_worst_phase",
    "ac_worst_stress_z", "ac_voltage_stress_max", "ac_line_stress_max",
    "ac_transformer_stress_max", "ac_worst_stress_type",
    "ac_worst_element_id", "ac_worst_phase", "ac_voltage_min_pu",
    "ac_voltage_max_pu", "ac_voltage_min_bus", "ac_voltage_max_bus",
    "ac_voltage_min_phase", "ac_voltage_max_phase", "ac_line_max_current_a",
    "ac_line_max_loading_pu", "ac_line_max_id", "ac_line_max_phase",
    "ac_transformer_max_current_a", "ac_transformer_current_loading_pu",
    "ac_transformer_max_kva", "ac_transformer_kva_loading_pu",
    "ac_transformer_max_id", "ac_transformer_max_phase", "ac_voltage_pass",
    "ac_line_pass", "ac_transformer_pass", "ac_hard_constraint_pass",
    "safety_filter_intervened", "safety_filter_stage", "fallback_used",
    "commit_accepted", "safety_action_delta_norm", "active_job_count",
    "queued_job_count", "completed_job_count", "deadline_miss_count",
    "remaining_compute_work", "compute_debt", "energy_debt_kwh",
    "recovery_active", "recovery_horizon_remaining", "compute_debt_target",
    "energy_debt_target", "terminal_recovery_feasible", "root_import_kw",
    "root_export_kw", "background_root_kw", "idc_power_kw",
    "mess_net_power_kw", "wan_power_kw", "shadow_root_import_kw",
    "rebound_power_kw", "aemo_price_aud_per_mwh",
    "kpi_step_grid_cost_aud", "kpi_cumulative_grid_cost_aud",
    "slow_solver_time_s", "fast_solver_time_s", "ac_safety_filter_time_s",
    "opendss_time_s", "total_control_time_s", "communication_bytes",
    "communication_bytes_step", "run_status", "failure_stage",
    "failure_reason", "last_committed_issue", "attempt_id",
    "parent_attempt_id", "retry_count",
)
MESS_REQUIRED_COLUMNS = (
    "timestamp", "issue", "method_id", "mess_id", "location", "state",
    "origin", "destination", "route_id", "in_transit", "plugged",
    "connection_ready", "planned_p_kw", "planned_q_kvar", "accepted_p_kw",
    "accepted_q_kvar", "p_kw", "q_kvar", "s_kva", "soc", "energy_kwh",
    "charge_kw", "discharge_kw", "battery_throughput_kwh",
    "route_eta_pred_s", "route_eta_realized_s", "route_energy_pred_kwh",
    "route_energy_realized_kwh", "mobility_started", "mobility_completed",
)
JOB_REQUIRED_COLUMNS = (
    "timestamp", "issue", "method_id", "job_id", "arrival_issue",
    "deadline_issue", "remaining_work_gpu_hours", "required_gpu", "current_idc",
    "assigned_idc", "running", "queued", "completed", "planned_compute_rate",
    "compute_rate", "gpu_allocated", "shifted_temporally",
    "migrated_spatially", "checkpoint_state", "checkpoint_eligible",
    "checkpoint_started", "checkpoint_completed", "restart_remaining",
    "migration_source", "migration_destination", "migration_payload_gb",
    "wan_transfer_gb_cumulative", "wan_transfer_gb",
    "prestart_wan_target_idc", "prestart_wan_required_gb",
    "prestart_wan_transferred_gb", "prestart_wan_transfer_gb_step",
    "prestart_wan_data_ready",
)
EVENT_REQUIRED_COLUMNS = (
    "timestamp", "issue", "method_id", "plan_age_steps", "risk_raw_total",
    "risk_calibrated_total", "risk_raw_components_json",
    "risk_calibrated_components_json", "risk_soc_raw", "risk_deadline_raw",
    "risk_gpu_raw", "risk_wan_raw", "risk_voltage_raw", "risk_thermal_raw",
    "risk_soc_calibrated", "risk_deadline_calibrated", "risk_gpu_calibrated",
    "risk_wan_calibrated", "risk_voltage_calibrated",
    "risk_thermal_calibrated", "trigger_safety", "trigger_opportunity",
    "trigger_max_refresh", "triggered", "trigger_reason_json",
    "full_replan_requested", "full_replan_executed", "fast_recourse_executed",
    "safety_filter_intervened", "slow_solver_time_s", "fast_solver_time_s",
    "ac_safety_filter_time_s", "total_control_time_s",
)
CAMPAIGN_REQUIRED_COLUMNS = (
    "method_id", "method_order", "status", "aggregation_scope",
    "calendar_day_count", "factorial_energy", "factorial_compute",
    "daily_max_ac_stress", "daily_ac_stress_exposure",
    "daily_max_voltage_stress", "daily_max_line_stress",
    "daily_max_transformer_stress", "daily_peak_root_import_kw",
    "daily_rebound_peak_kw", "daily_rebound_energy_kwh",
    "deadline_miss_count", "mess_move_count", "mobility_completed_count",
    "workload_temporal_shift_count", "migration_count", "checkpoint_count",
    "wan_transfer_gb", "full_replan_count", "fast_recourse_count",
    "safety_filter_intervention_count", "communication_bytes",
    "grid_cost_aud", "solver_time_p95_s", "total_control_time_p95_s",
)


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _atomic_parquet(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
    *,
    empty_columns: Sequence[str] = (),
) -> None:
    import pandas as pd

    path.parent.mkdir(parents=True, exist_ok=True)
    frame = (
        pd.DataFrame(tuple(rows))
        if rows
        else pd.DataFrame(columns=tuple(empty_columns))
    )
    temporary = path.with_name(f".{path.stem}.tmp{path.suffix}")
    frame.to_parquet(temporary, index=False)
    temporary.replace(path)


def _timestamp_fields(record: Mapping[str, Any]) -> tuple[int | None, str | None, str | None]:
    exact = record.get("exact_ac", {})
    raw = exact.get("timestamp_utc_ns")
    if raw is None:
        return None, None, None
    import pandas as pd

    timestamp_ns = int(raw)
    timestamp = pd.Timestamp(timestamp_ns, unit="ns", tz="UTC")
    return timestamp_ns, timestamp.isoformat(), timestamp.date().isoformat()


def _issue_row(record: Mapping[str, Any]) -> dict[str, Any]:
    exact = dict(record.get("exact_ac", {}))
    stress = dict(record.get("realized_exact_electrical_stress", {}))
    timestamp_ns, timestamp, date = _timestamp_fields(record)
    voltage = float(stress.get("voltage_stress_pu", 0.0))
    line = float(stress.get("line_stress_pu", 0.0))
    transformer = float(stress.get("transformer_stress_pu", 0.0))
    components = {"VOLTAGE": voltage, "LINE": line, "TRANSFORMER": transformer}
    worst_type = max(components, key=components.get)
    voltage_lower = max(
        0.0, (1.0 - float(exact.get("voltage_min_pu", 1.0))) / 0.05
    )
    voltage_upper = max(
        0.0, (float(exact.get("voltage_max_pu", 1.0)) - 1.0) / 0.05
    )
    voltage_worst_is_lower = voltage_lower >= voltage_upper
    transformer_current = float(
        exact.get("transformer_max_current_loading_pu", 0.0) or 0.0
    )
    transformer_kva = float(
        exact.get("transformer_max_kva_loading_pu", 0.0) or 0.0
    )
    transformer_worst_is_current = transformer_current >= transformer_kva
    transformer_worst_element = (
        exact.get("transformer_max_current_loading_name")
        if transformer_worst_is_current
        else exact.get("transformer_max_kva_loading_name")
    )
    worst_element = {
        "VOLTAGE": (
            exact.get("voltage_min_bus_node")
            if voltage_worst_is_lower
            else exact.get("voltage_max_bus_node")
        ),
        "LINE": exact.get("line_max_loading_name"),
        "TRANSFORMER": transformer_worst_element,
    }[worst_type]
    worst_phase = {
        "VOLTAGE": (
            exact.get("voltage_min_phase")
            if voltage_worst_is_lower
            else exact.get("voltage_max_phase")
        ),
        "LINE": exact.get("line_max_phase"),
        "TRANSFORMER": exact.get("transformer_max_phase"),
    }[worst_type]
    plan_age_steps = record.get("plan_age_steps")
    plan_origin_timestamp = None
    if timestamp is not None and plan_age_steps is not None:
        import pandas as pd

        plan_origin_timestamp = (
            pd.Timestamp(timestamp) - pd.Timedelta(minutes=5 * int(plan_age_steps))
        ).isoformat()
    return {
        "result_schema_version": RESULT_SCHEMA_VERSION,
        "date": date,
        "timestamp": timestamp,
        "timestamp_utc_ns": timestamp_ns,
        "issue": int(record["issue"]),
        "method_id": record["comparison_method_id"],
        "method_order": int(record["method_order"]),
        "plan_id": record.get("plan_id"),
        "replan_id": record.get("replan_id"),
        "plan_origin_issue": record.get("plan_origin_issue"),
        "plan_origin_timestamp": plan_origin_timestamp,
        "plan_age_steps": record.get("plan_age_steps"),
        "objective_id": record.get("objective_id"),
        "predicted_worst_stress_z": record.get("predicted_worst_electrical_stress_pu"),
        "predicted_stress_exposure": record.get("predicted_electrical_stress_exposure_pu_hours"),
        "predicted_voltage_stress_max": record.get("predicted_voltage_stress_max"),
        "predicted_line_stress_max": record.get("predicted_line_stress_max"),
        "predicted_transformer_stress_max": record.get("predicted_transformer_stress_max"),
        "predicted_worst_stress_type": record.get("predicted_worst_stress_type"),
        "predicted_worst_element_id": record.get("predicted_worst_element_id"),
        "predicted_worst_phase": record.get("predicted_worst_phase"),
        "ac_worst_stress_z": stress.get("worst_electrical_stress_pu"),
        "ac_voltage_stress_max": voltage,
        "ac_line_stress_max": line,
        "ac_transformer_stress_max": transformer,
        "ac_worst_stress_type": worst_type,
        "ac_worst_element_id": worst_element,
        "ac_worst_phase": worst_phase,
        "ac_voltage_min_pu": exact.get("voltage_min_pu"),
        "ac_voltage_max_pu": exact.get("voltage_max_pu"),
        "ac_voltage_min_bus": exact.get("voltage_min_bus_node"),
        "ac_voltage_max_bus": exact.get("voltage_max_bus_node"),
        "ac_voltage_min_phase": exact.get("voltage_min_phase"),
        "ac_voltage_max_phase": exact.get("voltage_max_phase"),
        "ac_line_max_current_a": exact.get("line_max_current_a"),
        "ac_line_max_loading_pu": exact.get("line_max_loading_pu"),
        "ac_line_max_id": exact.get("line_max_loading_name"),
        "ac_line_max_phase": exact.get("line_max_phase"),
        "ac_transformer_max_current_a": exact.get("transformer_max_current_a"),
        "ac_transformer_current_loading_pu": exact.get("transformer_max_current_loading_pu"),
        "ac_transformer_max_kva": exact.get("transformer_max_kva"),
        "ac_transformer_kva_loading_pu": exact.get("transformer_max_kva_loading_pu"),
        "ac_transformer_max_id": transformer_worst_element,
        "ac_transformer_max_phase": exact.get("transformer_max_phase"),
        "ac_voltage_pass": int(exact.get("voltage_violation_count", 1)) == 0,
        "ac_line_pass": int(exact.get("line_violation_count", 1)) == 0,
        "ac_transformer_pass": (
            int(exact.get("transformer_kva_violation_count", 1)) == 0
            and int(exact.get("transformer_current_violation_count", 1)) == 0
        ),
        "ac_hard_constraint_pass": bool(exact.get("hard_constraint_pass", False)),
        "safety_filter_intervened": bool(record.get("safety_filter_intervention")),
        "safety_filter_stage": record.get("safety_filter_stage"),
        "fallback_used": bool(record.get("safety_filter_escalation_count", 0)),
        "commit_accepted": bool(record.get("commit_marker")),
        "safety_action_delta_norm": record.get("safety_action_delta_norm"),
        "active_job_count": record.get("active_jobs"),
        "queued_job_count": record.get("queued_jobs"),
        "completed_job_count": record.get("completed_jobs"),
        "deadline_miss_count": record.get("deadline_misses"),
        "remaining_compute_work": record.get("remaining_work_gpu_hours"),
        "compute_debt": record.get("compute_debt_gpu_hours"),
        "energy_debt_kwh": record.get("energy_debt_kwh"),
        "recovery_active": bool(record.get("compute_debt_gpu_hours", 0.0) or record.get("energy_debt_kwh", 0.0)),
        "recovery_horizon_remaining": record.get("recovery_horizon_remaining"),
        "compute_debt_target": record.get("compute_debt_target"),
        "energy_debt_target": record.get("energy_debt_target"),
        "terminal_recovery_feasible": record.get("terminal_recovery_feasible"),
        "root_import_kw": exact.get("root_import_p_kw"),
        "root_export_kw": exact.get("root_export_p_kw", 0.0),
        "background_root_kw": record.get("background_root_kw"),
        "idc_power_kw": record.get("facility_p_kw_total"),
        "mess_net_power_kw": record.get("mess_p_kw_total"),
        "wan_power_kw": record.get("wan_power_kw"),
        "shadow_root_import_kw": record.get("shadow_root_import_kw"),
        "rebound_power_kw": record.get("rebound_power_kw"),
        "aemo_price_aud_per_mwh": record.get("price_aud_per_mwh"),
        "kpi_step_grid_cost_aud": record.get("realized_grid_cost_aud"),
        "kpi_cumulative_grid_cost_aud": record.get("cumulative_grid_cost_aud"),
        "slow_solver_time_s": record.get("slow_solver_time_s"),
        "fast_solver_time_s": record.get("fast_recourse_runtime_seconds"),
        "ac_safety_filter_time_s": record.get("safety_filter_runtime_seconds"),
        "opendss_time_s": record.get("opendss_runtime_seconds"),
        "total_control_time_s": record.get("runtime_seconds"),
        "communication_bytes": record.get("communication_bytes_cumulative"),
        "communication_bytes_step": record.get("communication_bytes_step"),
        "full_replan": bool(record.get("full_replan_executed")),
        "fast_recourse_executed": True,
        "run_status": record.get("status"),
        "failure_stage": record.get("failure_stage"),
        "failure_reason": record.get("failure_reason"),
        "last_committed_issue": record.get("last_committed_issue", record.get("issue")),
        "attempt_id": record.get("attempt_id"),
        "parent_attempt_id": record.get("parent_attempt_id"),
        "retry_count": record.get("retry_count", 0),
    }


def _mess_rows(record: Mapping[str, Any]) -> list[dict[str, Any]]:
    timestamp_ns, timestamp, _ = _timestamp_fields(record)
    rows = []
    energy = record.get("mess_energy_kwh", {})
    location = record.get("mess_location", {})
    transit = record.get("mess_in_transit", {})
    destinations = record.get("mess_route_destination", {})
    planned = record.get("planned_control", {})
    accepted = record.get("accepted_control", {})
    started = {event["mess_id"]: event for event in record.get("mobility_started_events", ())}
    for mess_id in sorted(location):
        charge = float(accepted.get("mess_charge_kw", {}).get(mess_id, 0.0))
        discharge = float(accepted.get("mess_discharge_kw", {}).get(mess_id, 0.0))
        q = float(accepted.get("mess_q_kvar", {}).get(mess_id, 0.0))
        p = discharge - charge
        event = started.get(mess_id, {})
        rows.append({
            "result_schema_version": RESULT_SCHEMA_VERSION,
            "timestamp": timestamp,
            "timestamp_utc_ns": timestamp_ns,
            "issue": int(record["issue"]),
            "method_id": record["comparison_method_id"],
            "mess_id": mess_id,
            "location": location[mess_id],
            "state": "IN_TRANSIT" if bool(transit.get(mess_id)) else "CONNECTED",
            "origin": event.get("source_service_id", location[mess_id]),
            "destination": destinations.get(mess_id) or event.get("destination_service_id"),
            "route_id": event.get("route_rank", record.get("mess_route_rank", {}).get(mess_id)),
            "in_transit": bool(transit.get(mess_id)),
            "plugged": not bool(transit.get(mess_id)),
            "connection_ready": not bool(transit.get(mess_id)),
            "planned_p_kw": float(planned.get("mess_discharge_kw", {}).get(mess_id, 0.0)) - float(planned.get("mess_charge_kw", {}).get(mess_id, 0.0)),
            "planned_q_kvar": planned.get("mess_q_kvar", {}).get(mess_id),
            "accepted_p_kw": p,
            "accepted_q_kvar": q,
            "p_kw": p,
            "q_kvar": q,
            "s_kva": (p * p + q * q) ** 0.5,
            "soc": float(energy.get(mess_id, 0.0)) / 1080.0,
            "energy_kwh": energy.get(mess_id),
            "charge_kw": charge,
            "discharge_kw": discharge,
            "battery_throughput_kwh": (charge + discharge) * (5.0 / 60.0),
            "route_eta_pred_s": event.get("planning_eta_seconds"),
            "route_eta_realized_s": event.get("realized_eta_seconds"),
            "route_energy_pred_kwh": event.get("planned_mobility_energy_kwh"),
            "route_energy_realized_kwh": event.get("realized_mobility_energy_route_total_kwh"),
            "mobility_started": mess_id in started,
            "mobility_completed": bool(record.get("mobility_completed", {}).get(mess_id, False)),
        })
    return rows


def _job_rows(record: Mapping[str, Any]) -> list[dict[str, Any]]:
    timestamp_ns, timestamp, _ = _timestamp_fields(record)
    accepted = record.get("accepted_control", {}).get("job_compute_rate_fraction", {})
    planned = record.get("planned_control", {}).get("job_compute_rate_fraction", {})
    prestart_step = record.get(
        "prestart_wan_bytes_transferred_step_by_job", {}
    )
    rows = []
    for uid, job in sorted(record.get("job_states", {}).items()):
        lifecycle = job.get("lifecycle")
        checkpoint_state = str(job.get("checkpoint_state") or "")
        rows.append({
            "result_schema_version": RESULT_SCHEMA_VERSION,
            "timestamp": timestamp,
            "timestamp_utc_ns": timestamp_ns,
            "issue": int(record["issue"]),
            "method_id": record["comparison_method_id"],
            "job_id": uid,
            "arrival_issue": job.get("arrival_issue"),
            "arrival_time": job.get("arrival_issue"),
            "deadline_issue": job.get("deadline_issue"),
            "deadline": job.get("deadline_issue"),
            "remaining_work_gpu_hours": job.get("remaining_work_gpu_hours"),
            "required_gpu": job.get("required_gpu"),
            "current_idc": job.get("destination_idc"),
            "assigned_idc": job.get("planned_idc"),
            "running": lifecycle == "RUNNING",
            "queued": lifecycle == "QUEUED",
            "completed": lifecycle == "COMPLETED",
            "planned_compute_rate": planned.get(uid),
            "compute_rate": accepted.get(uid, job.get("compute_rate_fraction")),
            "gpu_allocated": job.get("required_gpu") if lifecycle == "RUNNING" else 0,
            "shifted_temporally": bool(job.get("planned_start_issue", record["issue"]) > job.get("arrival_issue", record["issue"])),
            "migrated_spatially": job.get("destination_idc") != job.get("origin_idc"),
            "checkpoint_state": job.get("checkpoint_state"),
            "checkpoint_eligible": "ELIGIBLE" in checkpoint_state,
            "checkpoint_started": "START" in checkpoint_state,
            "checkpoint_completed": "COMPLETE" in checkpoint_state,
            "restart_remaining": job.get("restart_remaining_steps"),
            "migration_source": job.get("migration_source_idc"),
            "migration_destination": job.get("migration_destination_idc"),
            "migration_payload_gb": (job.get("migration_payload_remaining_bytes", 0) or 0) / 1e9,
            "prestart_wan_target_idc": job.get("prestart_wan_target_idc"),
            "prestart_wan_required_gb": (
                (job.get("prestart_wan_required_bytes", 0) or 0) / 1e9
            ),
            "prestart_wan_transferred_gb": (
                (job.get("prestart_wan_transferred_bytes", 0) or 0) / 1e9
            ),
            "prestart_wan_transfer_gb_step": (
                (prestart_step.get(uid, 0) or 0) / 1e9
            ),
            "prestart_wan_data_ready": bool(
                (job.get("prestart_wan_required_bytes", 0) or 0) > 0
                and (job.get("prestart_wan_transferred_bytes", 0) or 0)
                >= (job.get("prestart_wan_required_bytes", 0) or 0)
            ),
            "wan_transfer_gb_cumulative": record.get("wan_transferred_bytes_cumulative", 0) / 1e9,
            "wan_transfer_gb": record.get("wan_bytes_transferred_step", 0) / 1e9,
        })
    return rows


def _event_row(record: Mapping[str, Any]) -> dict[str, Any]:
    timestamp_ns, timestamp, _ = _timestamp_fields(record)
    raw = dict(record.get("risk_raw_components", {}))
    calibrated = dict(record.get("risk_calibrated_components", {}))
    causes = tuple(record.get("replan_causes", ()))
    def component(values: Mapping[str, Any], *names: str) -> Any:
        for name in names:
            if name in values:
                return values[name]
        return None

    return {
        "result_schema_version": RESULT_SCHEMA_VERSION,
        "timestamp": timestamp,
        "timestamp_utc_ns": timestamp_ns,
        "issue": int(record["issue"]),
        "method_id": record["comparison_method_id"],
        "plan_age_steps": record.get("plan_age_steps"),
        "risk_raw_total": max(raw.values(), default=0.0),
        "risk_calibrated_total": max(calibrated.values(), default=0.0),
        "risk_raw_components_json": _json(raw),
        "risk_calibrated_components_json": _json(calibrated),
        "risk_soc_raw": component(raw, "R_SOC", "R_soc"),
        "risk_deadline_raw": component(raw, "R_DEADLINE", "R_deadline"),
        "risk_gpu_raw": component(raw, "R_GPU", "R_gpu"),
        "risk_wan_raw": component(raw, "R_WAN", "R_wan"),
        "risk_voltage_raw": component(raw, "R_VOLTAGE", "R_voltage"),
        "risk_thermal_raw": component(raw, "R_THERMAL", "R_thermal"),
        "risk_soc_calibrated": component(calibrated, "R_SOC", "R_soc"),
        "risk_deadline_calibrated": component(calibrated, "R_DEADLINE", "R_deadline"),
        "risk_gpu_calibrated": component(calibrated, "R_GPU", "R_gpu"),
        "risk_wan_calibrated": component(calibrated, "R_WAN", "R_wan"),
        "risk_voltage_calibrated": component(calibrated, "R_VOLTAGE", "R_voltage"),
        "risk_thermal_calibrated": component(calibrated, "R_THERMAL", "R_thermal"),
        "trigger_safety": any("SAFETY" in str(cause) for cause in causes),
        "trigger_opportunity": any("OPPORTUNITY" in str(cause) for cause in causes),
        "trigger_max_refresh": any("REFRESH" in str(cause) for cause in causes),
        "triggered": bool(record.get("full_replan_executed")),
        "trigger_reason_json": _json(causes),
        "full_replan_requested": bool(record.get("full_replan_executed")),
        "full_replan_executed": bool(record.get("full_replan_executed")),
        "fast_recourse_executed": True,
        "safety_filter_intervened": bool(record.get("safety_filter_intervention")),
        "slow_solver_time_s": record.get("slow_solver_time_s"),
        "fast_solver_time_s": record.get("fast_recourse_runtime_seconds"),
        "ac_safety_filter_time_s": record.get("safety_filter_runtime_seconds"),
        "total_control_time_s": record.get("runtime_seconds"),
    }


def materialize_method_results(
    method_root: Path,
    records: Sequence[Mapping[str, Any]],
    summary: Mapping[str, Any],
) -> None:
    issue_rows = [_issue_row(record) for record in records]
    mess_rows = [row for record in records for row in _mess_rows(record)]
    job_rows = [row for record in records for row in _job_rows(record)]
    event_rows = [_event_row(record) for record in records]
    _atomic_parquet(
        method_root / "ISSUE_RESULT.parquet",
        issue_rows,
        empty_columns=ISSUE_REQUIRED_COLUMNS,
    )
    _atomic_parquet(
        method_root / "MESS_TRAJECTORY.parquet",
        mess_rows,
        empty_columns=MESS_REQUIRED_COLUMNS,
    )
    _atomic_parquet(
        method_root / "JOB_WAN_TRAJECTORY.parquet",
        job_rows,
        empty_columns=JOB_REQUIRED_COLUMNS,
    )
    _atomic_parquet(
        method_root / "EVENT_CONTROL_LOG.parquet",
        event_rows,
        empty_columns=EVENT_REQUIRED_COLUMNS,
    )
    audit = validate_method_results(method_root, expected_issue_count=len(records))
    _atomic_json(method_root / "RESULT_STORAGE_AUDIT.json", audit)


def materialize_campaign_summary(
    output: Path, method_summaries: Sequence[Mapping[str, Any]]
) -> None:
    expected_method_ids = tuple(
        str(summary.get("comparison_method_id")) for summary in method_summaries
    )
    rows = []
    for summary in method_summaries:
        stress = summary.get("realized_exact_electrical_stress", {})
        rows.append({
            "result_schema_version": RESULT_SCHEMA_VERSION,
            "method_id": summary.get("comparison_method_id"),
            "method_order": int(str(summary.get("comparison_method_id", "B0"))[1:]),
            "status": summary.get("status"),
            "aggregation_scope": summary.get("aggregation_scope", "DAY"),
            "calendar_day_count": summary.get("calendar_day_count", 1),
            "factorial_energy": summary.get("factorial_energy"),
            "factorial_compute": summary.get("factorial_compute"),
            "daily_max_ac_stress": stress.get("worst_electrical_stress_pu"),
            "daily_ac_stress_exposure": stress.get("electrical_stress_exposure_pu_hours"),
            "daily_max_voltage_stress": summary.get("daily_max_voltage_stress"),
            "daily_max_line_stress": summary.get("daily_max_line_stress"),
            "daily_max_transformer_stress": summary.get(
                "daily_max_transformer_stress"
            ),
            "daily_peak_root_import_kw": summary.get("daily_peak_root_import_kw"),
            "daily_rebound_peak_kw": summary.get("daily_rebound_peak_kw"),
            "daily_rebound_energy_kwh": summary.get("daily_rebound_energy_kwh"),
            "deadline_miss_count": summary.get(
                "deadline_miss_count", summary.get("deadline_misses")
            ),
            "mess_move_count": summary.get(
                "mess_move_count", summary.get("mobility_started_route_count")
            ),
            "mobility_completed_count": summary.get("mobility_completed_count"),
            "workload_temporal_shift_count": summary.get(
                "workload_temporal_shift_count"
            ),
            "migration_count": summary.get(
                "workload_migration_count", summary.get("migration_count")
            ),
            "checkpoint_count": summary.get("checkpoint_count"),
            "wan_transfer_gb": summary.get("wan_transfer_gb"),
            "full_replan_count": summary.get("full_replan_count"),
            "fast_recourse_count": summary.get("fast_recourse_count"),
            "safety_filter_intervention_count": summary.get(
                "safety_filter_intervention_count"
            ),
            "communication_bytes": summary.get("communication_bytes"),
            "grid_cost_aud": summary.get("grid_cost_aud"),
            "solver_time_p95_s": summary.get("solver_time_p95_s"),
            "total_control_time_p95_s": summary.get(
                "total_control_time_p95_s"
            ),
        })
    rows.sort(key=lambda row: row["method_order"])
    _atomic_parquet(
        output / "CAMPAIGN_SUMMARY.parquet",
        rows,
        empty_columns=CAMPAIGN_REQUIRED_COLUMNS,
    )
    audit = validate_campaign_summary(
        output / "CAMPAIGN_SUMMARY.parquet",
        expected_method_ids=expected_method_ids,
    )
    _atomic_json(output / "CAMPAIGN_STORAGE_AUDIT.json", audit)


def materialize_period_summary(
    output: Path,
    *,
    calendar_dates: Sequence[str],
    method_ids: Sequence[str],
) -> None:
    """Aggregate completed independent days into one ordered 10-row table.

    Daily cold starts remain separate scientific episodes.  This function only
    projects their committed evidence into a period-level analysis table; it
    never changes controller state or reuses a day as another day's input.
    """

    import pandas as pd

    dates = tuple(str(value) for value in calendar_dates)
    methods = tuple(str(value) for value in method_ids)
    if methods != tuple(f"B{index:02d}" for index in range(10)):
        raise RuntimeError("period summary requires the frozen ordered B00-B09 axis")
    if not dates or len(set(dates)) != len(dates):
        raise RuntimeError("period summary requires unique calendar dates")

    def maximum(rows: Sequence[Mapping[str, Any]], key: str) -> Any:
        values = [float(row[key]) for row in rows if row.get(key) is not None]
        return max(values) if values else None

    def total(rows: Sequence[Mapping[str, Any]], key: str) -> Any:
        values = [float(row[key]) for row in rows if row.get(key) is not None]
        return sum(values) if values else None

    summaries: list[dict[str, Any]] = []
    evidence_rows = []
    for method in methods:
        daily: list[Mapping[str, Any]] = []
        solver_times: list[float] = []
        control_times: list[float] = []
        for calendar_date in dates:
            method_root = output / calendar_date / method
            summary_path = method_root / "DAILY_SUMMARY.json"
            try:
                summary = json.loads(summary_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise RuntimeError(
                    f"missing or invalid daily summary: {summary_path}"
                ) from exc
            if summary.get("status") != "PASS":
                raise RuntimeError(
                    f"period summary cannot include failed day: {calendar_date}/{method}"
                )
            daily.append(summary)
            issue_path = method_root / "ISSUE_RESULT.parquet"
            issue = pd.read_parquet(
                issue_path,
                columns=("slow_solver_time_s", "total_control_time_s"),
            )
            solver_times.extend(
                float(value)
                for value in issue["slow_solver_time_s"].dropna().tolist()
            )
            control_times.extend(
                float(value)
                for value in issue["total_control_time_s"].dropna().tolist()
            )

        p95_index = max(0, math.ceil(0.95 * len(solver_times)) - 1)
        control_p95_index = max(0, math.ceil(0.95 * len(control_times)) - 1)
        stress_worst = maximum(daily, "daily_max_ac_stress")
        stress_exposure = total(daily, "daily_ac_stress_exposure")
        summary = {
            "comparison_method_id": method,
            "status": "PASS",
            "aggregation_scope": "PERIOD",
            "calendar_day_count": len(dates),
            "factorial_energy": daily[0].get("factorial_energy"),
            "factorial_compute": daily[0].get("factorial_compute"),
            "realized_exact_electrical_stress": {
                "worst_electrical_stress_pu": stress_worst,
                "electrical_stress_exposure_pu_hours": stress_exposure,
            },
            "daily_max_voltage_stress": maximum(
                daily, "daily_max_voltage_stress"
            ),
            "daily_max_line_stress": maximum(daily, "daily_max_line_stress"),
            "daily_max_transformer_stress": maximum(
                daily, "daily_max_transformer_stress"
            ),
            "daily_peak_root_import_kw": maximum(
                daily, "daily_peak_root_import_kw"
            ),
            "daily_rebound_peak_kw": maximum(daily, "daily_rebound_peak_kw"),
            "daily_rebound_energy_kwh": total(
                daily, "daily_rebound_energy_kwh"
            ),
            "deadline_miss_count": int(total(daily, "deadline_miss_count") or 0),
            "mess_move_count": int(total(daily, "mess_move_count") or 0),
            "mobility_completed_count": int(
                total(daily, "mobility_completed_count") or 0
            ),
            "workload_temporal_shift_count": int(
                total(daily, "workload_temporal_shift_count") or 0
            ),
            "workload_migration_count": int(
                total(daily, "workload_migration_count") or 0
            ),
            "checkpoint_count": int(total(daily, "checkpoint_count") or 0),
            "wan_transfer_gb": total(daily, "wan_transfer_gb") or 0.0,
            "full_replan_count": int(total(daily, "full_replan_count") or 0),
            "fast_recourse_count": int(total(daily, "fast_recourse_count") or 0),
            "safety_filter_intervention_count": int(
                total(daily, "safety_filter_intervention_count") or 0
            ),
            "communication_bytes": int(total(daily, "communication_bytes") or 0),
            "grid_cost_aud": total(daily, "grid_cost_aud") or 0.0,
            "solver_time_p95_s": (
                sorted(solver_times)[p95_index] if solver_times else None
            ),
            "total_control_time_p95_s": (
                sorted(control_times)[control_p95_index]
                if control_times
                else None
            ),
        }
        summaries.append(summary)
        evidence_rows.append(
            {
                "method_id": method,
                "calendar_day_count": len(daily),
                "issue_row_count": len(solver_times),
            }
        )
    materialize_campaign_summary(output, summaries)
    _atomic_json(
        output / "PERIOD_SUMMARY_AUDIT.json",
        {
            "result_schema_version": RESULT_SCHEMA_VERSION,
            "status": "PASS",
            "aggregation_scope": "PERIOD",
            "calendar_dates": list(dates),
            "method_ids_in_order": list(methods),
            "daily_cold_start_state_chains_preserved": True,
            "evidence": evidence_rows,
        },
    )


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _read_and_check(
    path: Path,
    *,
    required_columns: Sequence[str],
) -> tuple[Any, dict[str, Any]]:
    import pandas as pd

    if not path.is_file():
        raise RuntimeError(f"missing result table: {path}")
    frame = pd.read_parquet(path)
    missing = sorted(set(required_columns) - set(frame.columns))
    if missing:
        raise RuntimeError(f"result table {path.name} lacks columns: {missing}")
    return frame, {
        "path": path.name,
        "row_count": int(len(frame)),
        "column_count": int(len(frame.columns)),
        "required_columns_present": True,
    }


def validate_method_results(
    method_root: Path,
    *,
    expected_issue_count: int,
) -> dict[str, Any]:
    """Read back every table and fail closed on row/schema/identity drift."""

    issue, issue_audit = _read_and_check(
        method_root / "ISSUE_RESULT.parquet", required_columns=ISSUE_REQUIRED_COLUMNS
    )
    mess, mess_audit = _read_and_check(
        method_root / "MESS_TRAJECTORY.parquet", required_columns=MESS_REQUIRED_COLUMNS
    )
    jobs, job_audit = _read_and_check(
        method_root / "JOB_WAN_TRAJECTORY.parquet", required_columns=JOB_REQUIRED_COLUMNS
    )
    events, event_audit = _read_and_check(
        method_root / "EVENT_CONTROL_LOG.parquet", required_columns=EVENT_REQUIRED_COLUMNS
    )
    if len(issue) != expected_issue_count or len(events) != expected_issue_count:
        raise RuntimeError(
            "five-minute result row count mismatch: "
            f"expected={expected_issue_count} issue={len(issue)} event={len(events)}"
        )
    method_ids = sorted(set(issue["method_id"].dropna().astype(str)))
    stress_campaign = bool(method_ids and len(method_ids[0]) == 3)
    if expected_issue_count:
        if issue["issue"].duplicated().any():
            raise RuntimeError("ISSUE_RESULT contains duplicate issue identifiers")
        if not issue["commit_accepted"].fillna(False).all():
            raise RuntimeError("ISSUE_RESULT contains an uncommitted action")
        if issue["ac_worst_stress_z"].isna().any():
            raise RuntimeError("realized exact-AC stress is missing")
        if stress_campaign and issue["predicted_worst_stress_z"].isna().any():
            raise RuntimeError("predicted objective stress is missing")
        if stress_campaign:
            mandatory = (
                "timestamp",
                "method_id",
                "ac_hard_constraint_pass",
                "root_import_kw",
                "run_status",
                "attempt_id",
            )
            null_columns = [
                column for column in mandatory if issue[column].isna().any()
            ]
            if null_columns:
                raise RuntimeError(
                    f"B00-B09 mandatory result values are missing: {null_columns}"
                )
    if len(method_ids) > 1:
        raise RuntimeError(f"method table mixes identities: {method_ids}")
    return {
        "result_schema_version": RESULT_SCHEMA_VERSION,
        "status": "PASS",
        "expected_issue_count": int(expected_issue_count),
        "method_ids": method_ids,
        "tables": {
            "ISSUE_RESULT": issue_audit,
            "MESS_TRAJECTORY": mess_audit,
            "JOB_WAN_TRAJECTORY": job_audit,
            "EVENT_CONTROL_LOG": event_audit,
        },
        "nullable_measurements": {
            "predicted_component_element_phase": "required columns; populated only when the planner certificate exposes component argmax metadata",
            "shadow_and_rebound": "nullable until a frozen shadow-baseline authority is supplied",
            "opendss_time_s": "nullable until the exact runner reports isolated wall time",
        },
    }


def validate_campaign_summary(
    path: Path,
    *,
    expected_method_ids: Sequence[str],
) -> dict[str, Any]:
    frame, table_audit = _read_and_check(
        path, required_columns=CAMPAIGN_REQUIRED_COLUMNS
    )
    actual = tuple(frame.sort_values("method_order")["method_id"].astype(str))
    expected = tuple(expected_method_ids)
    if actual != expected:
        raise RuntimeError(
            f"campaign method order mismatch: expected={expected} actual={actual}"
        )
    if len(set(actual)) != len(actual):
        raise RuntimeError("CAMPAIGN_SUMMARY contains duplicate methods")
    if actual and actual[0].startswith("B0") and len(actual[0]) == 3:
        frozen = tuple(f"B{index:02d}" for index in range(10))
        if actual != frozen:
            raise RuntimeError(
                f"electrical-stress campaign must contain exactly {frozen}"
            )
    return {
        "result_schema_version": RESULT_SCHEMA_VERSION,
        "status": "PASS",
        "method_ids_in_order": list(actual),
        "table": table_audit,
    }
