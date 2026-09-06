"""Complete job/trajectory identity checks, independent of optimization."""
from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from dataclasses import asdict, is_dataclass
from typing import Any, Mapping

H = 120
BEGIN = 24
METHOD = "BOUNDED_ITERATIVE_AIDC_MESS_CO_OPTIMIZATION"
MOBILITY_FIELDS = (
    "mess_id", "slot", "mode", "service_id", "origin_service_id",
    "destination_service_id", "departure_slot", "route_link_ids",
    "connection_ready_slot", "travel_slots_15min", "energy_safe_kwh",
    "energy_nominal_kwh", "route_q10_eta_sec", "route_q50_eta_sec",
    "route_q90_eta_sec", "route_safe_eta_sec",
)


def canonical(value: Any) -> bytes:
    def convert(item):
        if is_dataclass(item): return asdict(item)
        if hasattr(item, "tolist"): return item.tolist()
        if hasattr(item, "item"): return item.item()
        raise TypeError(type(item).__name__)
    return json.dumps(value, default=convert, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def indexed(rows, key="job_uid"):
    result = {str(r[key]): dict(r) for r in rows}
    if len(result) != len(rows): raise ValueError("DUPLICATE_ID")
    return result


def tail(row, boundary=H):
    start, end = int(row["start_slot"]), int(row["end_slot"])
    if end <= boundary: return ()
    return (max(start, boundary), end, str(row["post_H_site"]), int(row["requested_GPU"]))


def terminal_audit(baseline, candidate):
    a, b = indexed(baseline), indexed(candidate)
    if a.keys() != b.keys(): raise ValueError("JOB_UNIVERSE_CHANGED")
    profile_changed = site_changed = incremental = 0
    immutable = True
    for uid, before in a.items():
        after = b[uid]
        for row in (before, after):
            if (int(row["end_slot"]) - int(row["start_slot"]) != int(row["safe_duration_slots"])
                    or int(row["safe_duration_slots"]) <= 0 or int(row["requested_GPU"]) <= 0):
                raise ValueError("INVALID_JOB_INTERVAL:" + uid)
            if row["end_slot"] > H and row["AIDC_site"] != row["post_H_site"]:
                raise ValueError("INCONSISTENT_TERMINAL_SITE:" + uid)
        immutable &= all(before[k] == after[k] for k in (
            "state_at_issue", "qos", "requested_GPU", "safe_duration_slots"))
        for key in ('safe_duration_seconds', 'duration_authority', 'accepted_A0_assignment_and_WAN',
                    'source_snapshot_sha256', 'accepted_A0_file_SHA'):
            if key in before or key in after:
                immutable &= before.get(key) == after.get(key)
        p, q = tail(before), tail(after)
        profile_changed += p != q
        site_changed += bool(p or q) and (not p or not q or p[2] != q[2])
        old_load = (p[1] - p[0]) * p[3] if p else 0
        new_load = (q[1] - q[0]) * q[3] if q else 0
        # Positive increments cannot cancel across jobs.
        incremental += max(0, new_load - old_load) / 4
    return {
        "status": "PASS" if immutable and not profile_changed and not site_changed else "FAIL",
        "POST_H_RESERVATION_PROFILE_CHANGED_JOBS": int(profile_changed),
        "POST_H_SITE_STATE_CHANGED_JOBS": int(site_changed),
        "REPAIR_INDUCED_INCREMENTAL_POST_MIDNIGHT_GPU_H": incremental,
        "safe_runtime_GPU_state_qos_preserved": immutable,
    }


def occupancy_deviation(a, b):
    overlap = max(0, min(a["end_slot"], b["end_slot"]) - max(a["start_slot"], b["start_slot"]))
    if a["AIDC_site"] != b["AIDC_site"]: overlap = 0
    return int(a["requested_GPU"]) * (
        a["end_slot"] - a["start_slot"] + b["end_slot"] - b["start_slot"] - 2 * overlap)


def feedback_delta(before, after):
    a, b = indexed(before), indexed(after)
    terminal = terminal_audit(before, after)
    rows = []
    for uid in sorted(a):
        p, q = a[uid], b[uid]
        shift = q["start_slot"] - p["start_slot"]
        rows.append({"job_uid": uid, "state_at_issue": p["state_at_issue"],
                     "start_before": p["start_slot"], "start_after": q["start_slot"],
                     "site_before": p["AIDC_site"], "site_after": q["AIDC_site"],
                     "shift_minutes": shift * 15,
                     "shifted_GPU_h": abs(shift) * p["requested_GPU"] / 4,
                     "symmetric_GPU_h": occupancy_deviation(p, q) / 4,
                     "additional_running_migration": bool(q["migration_selected"] and not p["migration_selected"]),
                     "terminal_state_changed": tail(p) != tail(q)})
    shifts = sorted(abs(r["shift_minutes"]) for r in rows if r["shift_minutes"])
    import statistics
    summary = {
        "A0_to_A1_start_changed_jobs": len(shifts),
        "A0_to_A1_advanced_jobs": sum(r["shift_minutes"] < 0 for r in rows),
        "A0_to_A1_delayed_jobs": sum(r["shift_minutes"] > 0 for r in rows),
        "A0_to_A1_site_changed_jobs": sum(r["site_before"] != r["site_after"] for r in rows),
        "A0_to_A1_pending_initial_placement_changed_jobs": sum(r["state_at_issue"] == "PENDING" and r["site_before"] != r["site_after"] for r in rows),
        "A0_to_A1_running_migrations_added": sum(r["additional_running_migration"] for r in rows),
        "A0_to_A1_total_shifted_GPU_h": sum(r["shifted_GPU_h"] for r in rows),
        "A0_to_A1_symmetric_GPU_h": sum(r["symmetric_GPU_h"] for r in rows),
        "A0_to_A1_max_time_shift_minutes": max(shifts, default=0),
        "A0_to_A1_median_time_shift_minutes": statistics.median(shifts) if shifts else 0,
        "median_population": "CHANGED_JOBS_ONLY", **terminal,
    }
    return rows, summary


def mobility_payload(trajectory):
    rows = [r.to_dict() if hasattr(r, "to_dict") else dict(r) for r in trajectory]
    axis = [(r["mess_id"], r["slot"]) for r in rows]
    if len(set(axis)) != len(axis): raise ValueError("DUPLICATE_MESS_SLOT")
    return [{k: r[k] for k in MOBILITY_FIELDS} for r in sorted(rows, key=lambda r:(r["mess_id"],r["slot"]))]


def route_sha(trajectory): return digest(mobility_payload(trajectory))


def monotone(previous, candidate, hard_pass, tolerance):
    if not math.isfinite(previous) or not math.isfinite(tolerance) or tolerance < 0:
        raise ValueError("INVALID_ACCEPTANCE_AUTHORITY")
    return bool(hard_pass and math.isfinite(candidate) and candidate <= previous + tolerance)


def joint_decision(aidc, trajectory, authority: Mapping[str, Any]):
    rows = [r.to_dict() if hasattr(r, "to_dict") else dict(r) for r in trajectory]
    payload = {"method": METHOD, "FINAL_AIDC_DECISION_SHA": digest(sorted(aidc,key=lambda r:r["job_uid"])),
               "FINAL_MESS_ROUTE_SHA": route_sha(rows),
               "FINAL_MESS_PQ_SHA": digest([{k:r[k] for k in ("mess_id","slot","p_kw","q_kvar","battery_energy_kwh","soc_fraction")}
                                            for r in sorted(rows,key=lambda r:(r["mess_id"],r["slot"]))]),
               "authority": dict(authority)}
    return {**payload, "FINAL_JOINT_DECISION_SHA": digest(payload)}


def validate_joint(payload):
    p = dict(payload); expected = p.pop("FINAL_JOINT_DECISION_SHA", None)
    if p.get("method") != METHOD: raise ValueError("OLD_SEQUENTIAL_B3_IS_NOT_V40A")
    if digest(p) != expected: raise ValueError("JOINT_DECISION_HASH_MISMATCH")
    return expected


def interaction_metrics(j):
    if set(j) != {"B0","B1","B2","B3"} or not all(math.isfinite(x) for x in j.values()):
        raise ValueError("FOUR_FINITE_MATCHED_CASE_VALUES_REQUIRED")
    return {"AIDC_effect": j["B0"]-j["B1"], "MESS_effect": j["B0"]-j["B2"],
            "Combined_effect": j["B0"]-j["B3"],
            "Interaction": j["B3"]-j["B2"]-j["B1"]+j["B0"]}
