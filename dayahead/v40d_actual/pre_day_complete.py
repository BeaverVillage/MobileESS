"""Narrow user-approved exclusion, never an assignment or site-recovery rule."""
from datetime import timedelta
import math
from .contracts import BEGIN, H, SLOT_SECONDS, ReplayError


def classify(job, observation, issue_time):
    from .job_replay import timestamp
    boundary = timestamp(issue_time) + timedelta(seconds=BEGIN * SLOT_SECONDS)
    window_end = boundary + timedelta(days=1)
    checks = {}
    try:
        start, end = timestamp(observation["start_time"]), timestamp(observation["end_time"])
        planned_start, planned_end = float(job["start_slot"]), float(job["end_slot"])
        checks["timestamps_present_and_ordered"] = (
            start < end and math.isfinite(planned_start) and math.isfinite(planned_end)
            and 0 <= planned_start < planned_end)
        overlap = max(0.0, (min(end, window_end)-max(start, boundary)).total_seconds())
        checks["planned_complete_by_D00"] = planned_end <= BEGIN
        checks["observed_complete_by_D00"] = end <= boundary
        checks["observed_overlap_zero"] = overlap == 0.0
        checks["not_running_at_D00"] = not (start <= boundary < end)
        checks["not_running_at_D00"] &= not bool(job.get("running_at_operating_day_start", False))
        observed_start, observed_end = start.isoformat(), end.isoformat()
    except (KeyError, ValueError, TypeError, ReplayError, OverflowError):
        checks["timestamps_present_and_ordered"] = False
        overlap, observed_start, observed_end = None, None, None
    checks["site_remains_UNASSIGNED"] = job.get("AIDC_site") == "UNASSIGNED"
    checks["operating_day_GPU_zero"] = all(float(job.get(k, 0)) == 0 for k in
        ("operating_day_GPU_slots", "operating_day_GPU_hours", "operating_day_GPU_occupancy"))
    checks["operating_day_power_zero"] = all(float(job.get(k, 0)) == 0 for k in
        ("operating_day_power_contribution", "operating_day_PCC_kWh", "operating_day_IT_kWh"))
    placement = job.get("accepted_A0_assignment_and_WAN", {})
    no_placement_state = not placement or (
        not placement.get("migration_selected", False)
        and not placement.get("WAN_path") and not placement.get("rack_pool_id")
        and not placement.get("logical_Rack_compatibility_label"))
    checks["no_migration_WAN_Rack_state_crossing_D00"] = (
        job.get("migration_selected") is False and job.get("Rack_label") in (None, "NONE")
        and no_placement_state and not job.get("migration_state_crosses_D00", False)
        and not job.get("WAN_state_crosses_D00", False) and not job.get("Rack_state_crosses_D00", False)
        and not job.get("WAN_path") and job.get("actual_Rack") in (None, "NONE"))
    ok = len(checks) == 9 and all(checks.values())
    return {"job_uid": str(job["job_uid"]), "status": "PRE_DAY_COMPLETE" if ok else "FAIL_CLOSED",
        "checks": checks, "failed_conditions": [k for k, v in checks.items() if not v],
        "operating_day_start": boundary.isoformat(), "observed_start": observed_start,
        "observed_end": observed_end, "observed_overlap_seconds": overlap,
        "AIDC_site": "UNASSIGNED", "actual_Rack": None,
        "actual_execution_on_D_day": False if ok else None,
        "operating_day_GPU_slots": 0 if ok else None, "operating_day_GPU_hours": 0 if ok else None,
        "operating_day_power_contribution": 0 if ok else None,
        "backlog_GPU_hours": 0 if ok else None, "unfinished_at_operating_day_start": False if ok else None}


def audit_exclusion(classifications, rack_assignments=(), gpu_contributions=(), power_contributions=()):
    """Validate downstream job-keyed records rather than trusting summary zeroes."""
    ids = {r["job_uid"] for r in classifications if r["status"] == "PRE_DAY_COMPLETE"}
    for r in rack_assignments:
        if str(r["job_uid"]) in ids:
            raise ReplayError("PRE_DAY_COMPLETE_RACK_ASSIGNMENT")
    for r in gpu_contributions:
        if str(r["job_uid"]) in ids and float(r["occupied_GPU"]) != 0:
            raise ReplayError("PRE_DAY_COMPLETE_GPU_CONTRIBUTION")
    for r in power_contributions:
        if str(r["job_uid"]) in ids and any(float(r.get(k, 0)) != 0 for k in ("P_IT_kW", "P_PCC_kW", "Q_PCC_kvar")):
            raise ReplayError("PRE_DAY_COMPLETE_POWER_CONTRIBUTION")
    return {"status": "PASS", "PRE_DAY_COMPLETE_job_count": len(ids),
            "PRE_DAY_COMPLETE_operating_day_GPU_hours": 0,
            "PRE_DAY_COMPLETE_operating_day_power_kWh": 0}
