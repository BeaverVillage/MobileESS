"""Exact per-reservation boundary contract. No solver or I/O dependencies.

Reservations are positive-duration, contiguous, non-preemptive intervals,
with immutable GPU request and one site state. UNASSIGNED is a real frozen
state, not permission to select a future physical AIDC.
"""
from __future__ import annotations

from collections import defaultdict

BEGIN, H = 24, 120
DAYS = ("2025-05-24", "2025-05-25", "2025-05-26")
OLD_PRIMARY = dict(zip(DAYS, (108, 29568, 13086)))
BASE_MIGRATIONS = dict(zip(DAYS, (2, 8, 15)))
UNASSIGNED = "UNASSIGNED"


def post_h_profile(start, duration, site, boundary=H):
    """Canonical complete half-open post-H interval, including site state."""
    assert int(start) == start and int(duration) == duration and duration > 0
    end = int(start + duration)
    return () if end <= boundary else (max(int(start), boundary), end, site)


def compact_allowed(base_start, duration, base_site, start, site, boundary=H):
    """Equivalent to post-H equality when the duration is held fixed."""
    assert duration > 0
    if base_start + duration <= boundary:
        return start + duration <= boundary
    return start == base_start and site == base_site


def terminal_latest(base_start, duration, original_latest, boundary=H):
    assert duration > 0 and original_latest >= base_start
    if base_start + duration > boundary:
        return int(base_start)
    return int(min(original_latest, boundary - duration))


def terminal_category(start, end, boundary=H):
    if end <= boundary:
        return "IN_DAY_COMPLETE"
    return "CROSS_BOUNDARY" if start < boundary else "POST_H_ONLY"


def terminal_cohorts(a):
    """Integral cohorts cannot exchange terminal sites or boundary obligations.

    Eligible status remains unchanged; a terminal reservation has a singleton
    time domain. Site constraints apply to all baseline tails. RUNNING keeps
    the existing migration-OFF initial site. A wholly off-day PENDING site
    remains UNASSIGNED even in the allocation keys; no AIDC is manufactured.
    """
    result, groups = [], {}
    for r in a.itertuples(index=False):
        lo, d = int(r.RSP_scheduled_start), int(r.RSP_duration_slots)
        hi = terminal_latest(lo, d, int(r.latest_start))
        fixed = str(r.initial_AIDC)
        if lo + d > H and r.baseline_terminal_site != UNASSIGNED:
            if fixed:
                assert fixed == r.baseline_terminal_site
            fixed = str(r.baseline_terminal_site)
        key = (r.state_at_issue, fixed, int(r.requested_gpus), d, lo,
               hi, bool(r.eligible), str(r.baseline_terminal_site),
               terminal_category(lo, lo+d), float(r.RSP_duration_seconds))
        if key not in groups:
            groups[key] = len(result)
            result.append(dict(state=key[0], fixed_site=key[1], g=key[2],
                               d=key[3], lo=key[4], hi=key[5], eligible=key[6],
                               terminal_site=key[7], terminal_category=key[8],
                               safe_duration_seconds=key[9], members=[]))
        result[groups[key]]["members"].append(str(r.job_uid))
    return result


def reservation_site_state(row, candidate_site):
    if row.RSP_scheduled_start >= H and row.baseline_terminal_site == UNASSIGNED:
        return UNASSIGNED
    return candidate_site


def terminal_audit(a, b):
    """Compare every UID and its full tail; no aggregate cancellation allowed."""
    assert a.job_uid.is_unique and b.job_uid.is_unique
    assert set(a.job_uid) == set(b.job_uid)
    candidates = b.set_index("job_uid")
    rows = []
    for r in a.itertuples(index=False):
        q = candidates.loc[r.job_uid]
        s0, d0 = int(r.RSP_scheduled_start), int(r.RSP_duration_slots)
        s1, d1 = int(q.scheduled_start_slot), int(q.duration_slots)
        e0, e1 = s0 + d0, s1 + d1
        # A candidate must explicitly export the unassigned state; the audit
        # never silently translates an invented physical site to UNASSIGNED.
        site1 = str(q.terminal_site_state)
        p0 = post_h_profile(s0, d0, str(r.baseline_terminal_site))
        p1 = post_h_profile(s1, d1, site1)
        timing_changed = p0[:2] != p1[:2]
        site_changed = bool(p0 or p1) and (not p0 or not p1 or p0[2] != p1[2])
        before = int(r.requested_gpus) * max(0, e0 - max(s0, H))
        after = int(q.requested_gpus) * max(0, e1 - max(s1, H))
        rows.append(dict(job_uid=r.job_uid, eligible=bool(r.eligible),
            baseline_start=s0, baseline_end=e0, repaired_start=s1, repaired_end=e1,
            baseline_terminal_site=str(r.baseline_terminal_site),
            repaired_terminal_site=site1, post_H_timing_changed=timing_changed,
            post_H_reservation_profile_changed=p0 != p1,
            post_H_site_state_changed=site_changed,
            new_post_midnight_start=s0 < H <= s1,
            new_post_midnight_completion=e0 <= H < e1,
            post_H_GPU_slots_before=before, post_H_GPU_slots_after=after,
            incremental_post_midnight_GPU_h=(after-before)/4,
            safe_runtime_preserved=(d0 == d1 and r.RSP_duration_seconds == q.RSP_duration_seconds),
            GPU_request_preserved=r.requested_gpus == q.requested_gpus,
            RW_completion_pass=(not r.eligible or e1 <= r.RW_scheduled_completion),
            baseline_in_day_remains_in_day=e0 > H or e1 <= H))
    summary = {
        "jobs": len(rows),
        "NEW_POST_MIDNIGHT_STARTS_FROM_REPAIR": sum(r["new_post_midnight_start"] for r in rows),
        "NEW_POST_MIDNIGHT_COMPLETIONS_FROM_REPAIR": sum(r["new_post_midnight_completion"] for r in rows),
        "POST_H_RESERVATION_PROFILE_CHANGED_JOBS": sum(r["post_H_reservation_profile_changed"] for r in rows),
        "POST_H_SITE_STATE_CHANGED_JOBS": sum(r["post_H_site_state_changed"] for r in rows),
        "INCREMENTAL_POST_MIDNIGHT_GPU_H_FROM_REPAIR": sum(r["incremental_post_midnight_GPU_h"] for r in rows),
        "FROZEN_SAFE_RUNTIME_PRESERVED": all(r["safe_runtime_preserved"] for r in rows),
        "GPU_REQUEST_PRESERVED": all(r["GPU_request_preserved"] for r in rows),
        "RW_COMPLETION_NONINFERIORITY_PASS": all(r["RW_completion_pass"] for r in rows),
        "NEW_RW_COMPLETION_VIOLATIONS": sum(not r["RW_completion_pass"] for r in rows),
    }
    summary["PASS"] = (not any(summary[k] for k in (
        "NEW_POST_MIDNIGHT_STARTS_FROM_REPAIR", "NEW_POST_MIDNIGHT_COMPLETIONS_FROM_REPAIR",
        "POST_H_RESERVATION_PROFILE_CHANGED_JOBS", "POST_H_SITE_STATE_CHANGED_JOBS"))
        and summary["FROZEN_SAFE_RUNTIME_PRESERVED"] and summary["GPU_REQUEST_PRESERVED"]
        and summary["RW_COMPLETION_NONINFERIORITY_PASS"])
    return rows, summary


def mandatory_capacity_certificate(a, capacity):
    """Exact integer presolve proof, independent of Gurobi.

    Keep only jobs with singleton time and site domains in the full V39J
    formulation. Omit every other nonnegative load. If their exact load
    exceeds the frozen site capacity, the relaxation, hence the full model,
    is infeasible. This proves infeasibility both with and without any primary
    equality. It is not a voltage monotonicity assumption.
    """
    occupants = defaultdict(list)
    for c in terminal_cohorts(a):
        if c["lo"] != c["hi"] or not c["fixed_site"]:
            continue
        for t in range(max(BEGIN, c["lo"]), min(H, c["lo"] + c["d"])):
            occupants[t, c["fixed_site"]].extend(
                dict(job_uid=u, requested_GPU=c["g"], start=c["lo"], end=c["lo"]+c["d"],
                     site=c["fixed_site"], state=c["state"], eligible=c["eligible"],
                     fixation_reason="MIGRATION_OFF_RUNNING" if c["state"] == "RUNNING"
                     else "BASELINE_TERMINAL_RESERVATION") for u in c["members"])
    violations = []
    for (t, s), jobs in sorted(occupants.items()):
        load = sum(j["requested_GPU"] for j in jobs)
        if load > capacity[s]:
            violations.append(dict(issue_slot=t, site=s, mandatory_GPU=load,
                                   site_capacity=capacity[s], excess_GPU=load-capacity[s], jobs=jobs))
    return dict(status="INFEASIBLE" if violations else "NO_CONTRADICTION_FOUND",
        method="EXACT_INTEGER_MANDATORY_CAPACITY_PRESOLVE",
        feasible_set_relaxation="All non-singleton or unassigned nonnegative job loads deleted",
        violations=violations, primary_equality_needed=False,
        grid_domain=[BEGIN, H], Gurobi_optimize_calls=0,
        proof="Every full-model allocation includes each listed job at this site/slot. Their integer GPU sum exceeds the frozen cap. Adding other nonnegative loads cannot repair that row.")


def primary_upper_certificate(a, old_lower_bound):
    terms = []
    for r in a.itertuples(index=False):
        lo, d, g = int(r.RSP_scheduled_start), int(r.RSP_duration_slots), int(r.requested_gpus)
        hi = terminal_latest(lo, d, int(r.latest_start))
        terms.append(dict(job_uid=r.job_uid, baseline_start=lo, terminal_latest=hi,
                          duration=d, GPU=g, objective_upper=2*g*min(hi-lo, d)))
    upper = sum(t["objective_upper"] for t in terms)
    return dict(old_certified_global_lower_bound=old_lower_bound,
        terminal_domain_objective_upper=upper, terms=terms,
        infeasible_by_lower_greater_than_upper=old_lower_bound > upper,
        proof="V39J is a restriction of V39H, so every feasible primary is at least the old optimum. Summing per-job maxima over the terminal-safe domains gives a valid upper bound even before capacity/grid constraints. Lower > upper proves the full feasible set empty.")
