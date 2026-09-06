"""Individual-job fixed-site replay. Historical start defines duration, never admission."""
from copy import deepcopy
from datetime import datetime
import math
from .contracts import BEGIN, H, SLOT_SECONDS, ZERO_COUNTERS, ReplayError
from .rack_dispatch import RackDispatcher


def timestamp(value):
    if hasattr(value, "to_pydatetime"):
        value = value.to_pydatetime()
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ReplayError("MISSING_OR_NAIVE_TIMESTAMP")
    return value


def priority_key(job):
    qos = str(job["qos"]).lower()
    tier = 0 if qos in ("high", "urgent") else 1 if qos == "normal" else 2 if qos == "standby" else 3
    return int(job["start_slot"]), tier, timestamp(job["submit_time"]).isoformat(), str(job["job_uid"])


def validate_jobs(jobs, observations, site_capacity, issue_time):
    issue = timestamp(issue_time)
    seen, errors = set(), []
    for r in jobs:
        uid = str(r["job_uid"])
        if uid in seen:
            errors.append({"job_uid": uid, "reason": "DUPLICATE_UID"})
        seen.add(uid)
        reason = None
        g = r.get("requested_GPU")
        if not isinstance(g, (int, float)) or not math.isfinite(g) or g <= 0 or int(g) != g:
            reason = "INVALID_GPU_COUNT"
        elif r["state_at_issue"] not in ("RUNNING", "PENDING"):
            reason = "INVALID_STATE_AT_ISSUE"
        elif r["AIDC_site"] != "UNASSIGNED" and r["AIDC_site"] not in site_capacity:
            reason = "UNKNOWN_FROZEN_SITE"
        elif uid not in observations:
            reason = "MISSING_ACTUAL_RUNTIME"
        else:
            try:
                o = observations[uid]
                start, end = timestamp(o["start_time"]), timestamp(o["end_time"])
                if end <= start:
                    reason = "INVALID_ACTUAL_RUNTIME"
                elif r["state_at_issue"] == "RUNNING" and not (start <= issue < end):
                    reason = "RUNNING_OBSERVATION_NOT_ACTIVE_AT_ISSUE"
                elif int(o["gpus_requested"]) != g:
                    reason = "OBSERVED_GPU_MISMATCH"
                priority_key(r)
            except (ValueError, TypeError, KeyError, ReplayError):
                reason = "INVALID_OBSERVATION_OR_PRIORITY"
        if reason is None and r["AIDC_site"] == "UNASSIGNED" and r["start_slot"] < H:
            from .pre_day_complete import classify
            if classify(r, observations.get(uid, {}), issue)["status"] != "PRE_DAY_COMPLETE":
                reason = "UNASSIGNED_PRE_DAY_COMPLETE_CONDITIONS_FAILED"
        if reason:
            errors.append({"job_uid": uid, "reason": reason, "state_at_issue": r.get("state_at_issue"),
                "frozen_site": r.get("AIDC_site"), "planned_start": r.get("start_slot"),
                "planned_end": r.get("end_slot")})
    return errors


def replay_jobs(jobs, observations, *, issue_time, site_capacity, racks):
    """No mutable state survives a call. Assigned jobs are accounted beyond H."""
    jobs = deepcopy(list(jobs))
    issue = timestamp(issue_time)
    errors = validate_jobs(jobs, observations, site_capacity, issue)
    if errors:
        raise ReplayError("JOB_PREFLIGHT_FAIL:" + str(errors[:5]))
    dispatcher = RackDispatcher(site_capacity, racks)
    completed, waiting, running, excluded = {}, [], [], []
    for r in jobs:
        uid = str(r["job_uid"])
        r["job_uid"] = uid
        r["requested_GPU"] = int(r["requested_GPU"])
        o = observations[uid]
        if r["AIDC_site"] == "UNASSIGNED" and r["start_slot"] < H:
            from .pre_day_complete import classify
            classification = classify(r, o, issue)
            if classification["status"] != "PRE_DAY_COMPLETE":
                raise ReplayError("PRE_DAY_COMPLETE_ADMISSION_GUARD")
            excluded.append(classification)
            completed[uid] = {**r, **classification, "actual_execution_start": None,
                "actual_execution_end": None, "actual_runtime_seconds": (timestamp(o["end_time"])-timestamp(o["start_time"])).total_seconds(),
                "start_delay_slots": 0, "start_delay_seconds": 0, "unfinished_at_H": False,
                "remaining_runtime_at_H": 0, "remaining_GPU_hours_at_H": 0,
                "post_H_completion_time": None, "post_H_site": None,
                "migration_frozen": False, "migration_executed": False, "WAN_state": "NONE"}
            continue
        total = (timestamp(o["end_time"]) - timestamp(o["start_time"])).total_seconds()
        residual = max(0.0, (timestamp(o["end_time"]) - issue).total_seconds())
        duration = residual if r["state_at_issue"] == "RUNNING" else total
        migration = bool(r.get("migration_selected", False))
        # An explicit preserved execution-ready record is required for migration.
        if migration and "frozen_execution_ready_slot" not in r:
            raise ReplayError("FROZEN_MIGRATION_READINESS_MISSING:" + uid)
        r.update(actual_runtime_seconds=total, actual_service_seconds=duration,
                 actual_runtime_slots=math.ceil(duration / SLOT_SECONDS),
                 actual_runtime_source="KESTREL_OBSERVED_END_MINUS_START",
                 actual_runtime_gt_requested_walltime=total > float(r["requested_walltime_seconds"]),
                 delayed_by_GPU_capacity=False, delayed_by_Rack_capacity=False,
                 migration_frozen=migration, migration_executed=migration,
                 WAN_state=deepcopy(r.get("accepted_A0_assignment_and_WAN", {})))
        if r["AIDC_site"] == "UNASSIGNED":
            completed[uid] = {**r, "actual_execution_start": None, "actual_execution_end": None,
                "actual_Rack": None, "start_delay_slots": None, "start_delay_seconds": None,
                "unfinished_at_H": True, "remaining_runtime_at_H": duration,
                "remaining_GPU_hours_at_H": duration * r["requested_GPU"] / 3600,
                "backlog_GPU_hours": duration * r["requested_GPU"] / 3600,
                "post_H_completion_time": None, "post_H_site": "UNASSIGNED",
                "status": "UNASSIGNED_POST_H_BACKLOG"}
        elif r["state_at_issue"] == "RUNNING":
            running.append(r)
        else:
            waiting.append(r)
    waiting.sort(key=priority_key)
    occupancy = []

    def record(r, start, rack):
        exact_end = start + r["actual_service_seconds"] / SLOT_SECONDS
        remaining = max(0.0, (exact_end - max(H, start)) * SLOT_SECONDS)
        remaining_waiting = r["actual_service_seconds"] if start >= H else 0.0
        row = {**r, "frozen_AIDC_site": r["AIDC_site"], "frozen_planned_start": r["start_slot"],
            "frozen_planned_end": r["end_slot"], "frozen_Rack_if_any": r.get("Rack_label"),
            "actual_execution_start": start if r["state_at_issue"] == "PENDING" else None,
            "actual_execution_origin": "CONTINUING_AT_ISSUE" if r["state_at_issue"] == "RUNNING" else "FROZEN_START_OR_CAPACITY_DELAY",
            "actual_residual_start": start, "actual_execution_end": exact_end,
            "actual_Rack": rack, "start_delay_slots": max(0, start - r["start_slot"]),
            "start_delay_seconds": max(0, start - r["start_slot"]) * SLOT_SECONDS,
            "unfinished_at_H": exact_end > H, "remaining_runtime_at_H": remaining,
            "remaining_GPU_hours_at_H": remaining * r["requested_GPU"] / 3600,
            "backlog_GPU_hours": remaining_waiting * r["requested_GPU"] / 3600,
            "post_H_completion_time": exact_end if exact_end > H else None,
            "post_H_site": r["AIDC_site"] if exact_end > H else None, "status": "EXECUTION_ACCOUNTED"}
        completed[r["job_uid"]] = row

    for r in sorted(running, key=lambda x: x["job_uid"]):
        rack, _ = dispatcher.admit(r, 0, r["actual_runtime_slots"], priority_key(r), existing=True)
        record(r, 0, rack)
    slot = 0
    # No arbitrary accounting cutoff: finite assigned jobs are drained on releases.
    while slot < H or waiting or dispatcher.active:
        dispatcher.release(slot)
        remaining = []
        for r in waiting:
            ready = max(int(r["start_slot"]), int(r.get("frozen_execution_ready_slot", 0)))
            if ready > slot:
                remaining.append(r)
                continue
            rack, reason = dispatcher.admit(r, slot, slot + r["actual_runtime_slots"], priority_key(r))
            if rack is None:
                r["delayed_by_GPU_capacity" if reason == "GPU_CAPACITY" else "delayed_by_Rack_capacity"] = True
                remaining.append(r)
            else:
                record(r, slot, rack)
        waiting = remaining
        dispatcher.validate()
        if BEGIN <= slot < H:
            occupancy.extend({"site_id": site, "slot": slot - BEGIN,
                "occupied_GPU_slots": dispatcher.occupied(site=site), "GPU_capacity": cap}
                for site, cap in sorted(site_capacity.items()))
        slot += 1
        if slot >= H and (waiting or dispatcher.active):
            future = [a["release_slot"] for a in dispatcher.active.values() if a["release_slot"] >= slot]
            future += [max(int(r["start_slot"]), int(r.get("frozen_execution_ready_slot", 0)))
                       for r in waiting if max(int(r["start_slot"]), int(r.get("frozen_execution_ready_slot", 0))) >= slot]
            if future:
                slot = min(future)
    rows = [completed[u] for u in sorted(completed)]
    if len(rows) != len(jobs):
        raise ReplayError("JOB_UID_COMPLETENESS")
    from .pre_day_complete import audit_exclusion
    exclusion = audit_exclusion(excluded, dispatcher.assignments)
    return {"status": "PASS", "job_ledger": rows, "rack_ledger": dispatcher.assignments,
            "rack_waits": dispatcher.failures, "site_occupancy": occupancy,
            "counters": {**dict.fromkeys(ZERO_COUNTERS, 0), "Actual_Rack_assignment_calls": dispatcher.calls,
                **{k: v for k, v in exclusion.items() if k != "status"},
                "PRE_DAY_COMPLETE_GPU_count": sum(completed[r["job_uid"]]["requested_GPU"] for r in excluded),
                "UNASSIGNED_with_operating_day_overlap_count": 0, "UNASSIGNED_fail_closed_count": 0},
            "pre_day_complete": excluded,
            "execution_accounting_last_slot": slot, "physical_horizon_slots": 96,
            "cross_day_state_carried": False}
