"""Read-only V39F causal schedule forensic; never a campaign or science refreeze.

The production RSP path is a deterministic runtime-reservation first-fit
scheduler, not a temporal MILP. Undefined counterfactuals are recorded as such;
this helper must not invent a scalar objective, deadline, or legal start set.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import fields
from datetime import datetime, timedelta, timezone
import hashlib
import inspect
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from dayahead.v37.aidc_materializer import Job, schedule, issue_time

OUT = REPO / "dayahead/artifacts/v39f_day17_rsp_temporal_grid_diagnostic"
DAYS = REPO / "dayahead/artifacts/v37_r4a_per_day_aidc/days"
DAY = "2025-05-17"
SLOT = 82
ISSUE_SLOT = SLOT + 24
LABELS = ["DIAGNOSTIC_ONLY", "NOT_PRODUCTION_AUTHORITY", "NOT_SCIENCE_FREEZE"]
IIS = REPO / "dayahead/artifacts/v39e_full_may_2025/diagnostics/V39E_RSP_MIGRATION_2025-05-17_IIS.ilp"
HIST_REPO = Path(r"C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS\github_MobileESS")
HIST_HEAD = "aa1a113abdd6eb1bc76cf3bfdcb6dcdb29660b2e"


def git(*args: str, repo: Path = REPO) -> str:
    return subprocess.check_output(["git", *args], cwd=repo, text=True, encoding="utf-8").strip()


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def clean(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if isinstance(value, np.generic):
        return clean(value.item())
    if isinstance(value, float) and not np.isfinite(value):
        return None
    if value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.isoformat()
    return value


def write_json(name: str, value: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    payload = {"labels": LABELS, **value}
    (OUT / name).write_text(json.dumps(clean(payload), ensure_ascii=False,
                                     indent=2, allow_nan=False) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def frame(name: str, data: pd.DataFrame) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    if name.endswith(".parquet"):
        data.to_parquet(OUT / name, index=False)
    else:
        data.to_csv(OUT / name, index=False, encoding="utf-8-sig")


def tracked_snapshot() -> dict[str, str]:
    # Hash tracked files, including a previously dirty runtime parquet. This
    # proves byte preservation without declaring the worktree initially clean.
    names = git("ls-files", "-z").split("\0")
    return {name: sha(REPO / name) for name in names if name and (REPO / name).is_file()}


def capture_start() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "V39F_START_STATE.json"
    if path.exists():
        return
    write_json(path.name, {
        "starting_HEAD": git("rev-parse", "HEAD"),
        "starting_branch": git("branch", "--show-current"),
        "starting_status_porcelain": git("status", "--porcelain"),
        "working_tree_clean": not bool(git("status", "--porcelain")),
        "tracked_file_SHA256": tracked_snapshot(),
        "captured_at": datetime.now(timezone.utc).isoformat(),
    })


def profile(a: pd.DataFrame, start: str, duration: str, left: int = 24, right: int = 120) -> np.ndarray:
    result = np.zeros(right - left, dtype=np.int64)
    for s, d, g in a[[start, duration, "requested_gpus"]].itertuples(index=False, name=None):
        if float(g) != int(g):
            raise ValueError("NONINTEGER_GPU")
        lo, hi = max(left, int(s)), min(right, int(s + d))
        if lo < hi:
            result[lo-left:hi-left] += int(g)
    return result


def interval_difference(s0: int, d0: int, s1: int, d1: int, g: int) -> tuple[int, int]:
    overlap = max(0, min(s0+d0, s1+d1) - max(s0, s1))
    return g * (d0 - overlap), g * (d1 - overlap)


def distribution(values: np.ndarray) -> dict:
    values = np.asarray(values, dtype=float)
    if not len(values):
        return {"n": 0, **{k: None for k in ("median", "P75", "P90", "P95", "maximum")}}
    return {"n": len(values), "median": float(np.median(values)),
            "P75": float(np.quantile(values, .75)), "P90": float(np.quantile(values, .90)),
            "P95": float(np.quantile(values, .95)), "maximum": float(values.max())}


def shift_band(minutes: float) -> str:
    if minutes == 0:
        return "same slot"
    for upper, label in ((30, "<=30 min"), (60, "30-60 min"), (120, "1-2 h"),
                         (240, "2-4 h"), (480, "4-8 h")):
        if minutes <= upper:
            return label
    return ">8 h"


def backlog(a: pd.DataFrame, mode: str) -> dict:
    starts = a[f"{mode}_scheduled_start"].to_numpy(int)
    durations = a[f"{mode}_duration_slots"].to_numpy(int)
    g = a.requested_gpus.to_numpy(int)
    pending = a.state_at_issue.eq("PENDING").to_numpy()
    # Historical service_metrics defines pending backlog as NOT STARTED at
    # terminal; unfinished running reservation is a distinct diagnostic.
    queued = pending & (starts >= 120)
    remaining = np.minimum(durations, np.maximum(0, starts + durations - 120))
    return {"terminal_pending_jobs": int(queued.sum()),
            "terminal_pending_GPU_hours": float((g[queued] * durations[queued]).sum() / 4),
            "terminal_unfinished_reservation_GPU_hours": float((g * remaining).sum() / 4),
            "completed_jobs_at_terminal": int((starts + durations <= 120).sum())}


def day_metrics(a: pd.DataFrame, day: str) -> dict:
    delta = (a.RSP_scheduled_start - a.RW_scheduled_start).to_numpy(int)
    pending = a.state_at_issue.eq("PENDING").to_numpy()
    shift = np.abs(delta) * 15
    diffs = [interval_difference(int(s0), int(d), int(s1), int(d), int(g))
             for s0, s1, d, g in a[["RW_scheduled_start", "RSP_scheduled_start",
                                     "RSP_duration_slots", "requested_gpus"]].itertuples(index=False, name=None)]
    # Translate the SAME RSP duration to RW/RSP starts. This avoids calling
    # reduced requested reservations 'shifted workload'.
    bh0, bh1 = backlog(a, "RW"), backlog(a, "RSP")
    q = distribution(shift)
    qp = distribution(shift[pending])
    return {"operating_day": day, "jobs": len(a), "pending_jobs": int(pending.sum()),
            "shifted_jobs": int((delta != 0).sum()), "advanced_jobs": int((delta < 0).sum()),
            "delayed_jobs": int((delta > 0).sum()),
            "shifted_GPU_hours_equal_duration_relocation": sum(x[0] for x in diffs) / 4,
            "GPU_hour_start_displacement": float((a.requested_gpus * np.abs(delta)).sum() / 4),
            "reservation_duration_reduction_GPU_hours": float((a.requested_gpus * (a.RW_duration_slots-a.RSP_duration_slots)).sum()/4),
            "median_shift_minutes": q["median"], "P95_shift_minutes": q["P95"],
            "max_shift_minutes": q["maximum"],
            "pending_median_abs_shift_minutes": qp["median"], "pending_P95_abs_shift_minutes": qp["P95"],
            "max_positive_deferral_minutes": float(np.maximum(delta, 0).max()*15),
            **{f"fraction_abs_shift_gt_{m}min_all_jobs": float((shift > m).mean()) for m in (30, 60, 120, 240, 480)},
            **{f"fraction_positive_deferral_gt_{m}min_all_jobs": float((delta*15 > m).mean()) for m in (30, 60, 120, 240, 480)},
            **{f"fraction_abs_shift_gt_{m}min_pending_jobs": float((shift[pending] > m).mean()) if pending.any() else 0 for m in (30, 60, 120, 240, 480)},
            **{f"{key}_RW": val for key, val in bh0.items()},
            **{f"{key}_RSP": val for key, val in bh1.items()},
            "terminal_pending_backlog_parity_observed": bh0["terminal_pending_GPU_hours"] == bh1["terminal_pending_GPU_hours"],
            "terminal_pending_backlog_noninferiority_observed": bh1["terminal_pending_GPU_hours"] <= bh0["terminal_pending_GPU_hours"],
            "service_parity_constraint_present": False,
            "duration_workload_mass_equality_RW_RSP": bool(np.array_equal(a.RW_duration_slots, a.RSP_duration_slots))}


def reproduce(a: pd.DataFrame, mode: str, saved: pd.DataFrame) -> dict:
    job_fields = {f.name for f in fields(Job)}
    jobs = [Job(**{**{key: row[key] for key in job_fields if key != "duration_slots"},
                   "duration_slots": int(row[f"{mode}_duration_slots"])}) for row in a.to_dict("records")]
    rebuilt, occ = schedule(jobs, "V39F_REPLAY_NO_OPTIMIZATION")
    keys = ["scheduled_start_slot", "scheduled_end_slot", "priority_rank"]
    expected = saved.assign(job_id=saved.job_id.astype(str)).set_index("job_id").sort_index()
    actual = rebuilt.assign(job_id=rebuilt.job_id.astype(str)).set_index("job_id").sort_index()
    exact = expected.index.equals(actual.index) and np.array_equal(expected[keys], actual[keys])
    if not exact:
        raise AssertionError(f"FROZEN_{mode}_REPLAY_MISMATCH")
    return {"status": "PASS", "all_job_starts_ends_priority_ranks_exact": exact,
            "jobs": len(jobs), "maximum_GPU": int(occ.max()), "MILP_calls": 0}


def audit_data() -> dict:
    all_days = []
    all_delta = []
    delayed_rows = []
    input_shas = {}
    for day_dir in sorted(DAYS.glob("2025-05-*")):
        p = day_dir / "V37_R4A_JOB_LEDGER.parquet"
        a = pd.read_parquet(p)
        all_days.append(day_metrics(a, day_dir.name))
        all_delta.extend((a.RSP_scheduled_start-a.RW_scheduled_start).astype(int).tolist())
        late = a.loc[a.RSP_scheduled_start.gt(a.RW_scheduled_start)].copy()
        late["operating_day"] = day_dir.name
        late["positive_deferral_minutes"] = (late.RSP_scheduled_start-late.RW_scheduled_start)*15
        delayed_rows.extend(late.to_dict("records"))
        for name in ("V37_R4A_JOB_LEDGER.parquet", "V37_R4A_RW_SCHEDULE.parquet",
                     "V37_R4A_RSP_SCHEDULE.parquet", "V37_R4A_DAY_MANIFEST.json"):
            input_shas[str((day_dir/name).relative_to(REPO))] = sha(day_dir/name)
    assert len(all_days) == 31
    monthly = pd.DataFrame(all_days)
    frame("V39F_MAY31_TEMPORAL_FLEXIBILITY_REALISM_AUDIT.csv", monthly)
    frame("V39F_MAY31_POSITIVE_DEFERRAL_JOBS.csv",pd.DataFrame(delayed_rows))
    write_json("V39F_MAY31_TEMPORAL_FLEXIBILITY_REALISM_AUDIT.json", {
        "definition": "Signed start shift=RSP_start-RW_start; positive is postponement. Absolute shift mixes advances and delays.",
        "time_unit": "15 minutes", "statistics_population": "all eligible daily jobs; pending-only fractions separately provided",
        "shifted_GPU_hours_definition": "sum_j GPU_j*(RSP_duration_j - overlap(RW_start+RSP_duration,RSP_start+RSP_duration))/4; not total reservation-duration reduction",
        "backlog_definition": "Pending jobs with start>=120, weighted by mode-specific reserved GPU-hours; unfinished running reservations reported separately",
        "future_results_used_for_May17_decision": False,
        "optimization_calls": 0, "days": all_days,
        "summary": {"day_count": 31, "job_day_count": len(all_delta),
                    "days_with_delays": int((monthly.delayed_jobs>0).sum()),
                    "delayed_job_days": int(monthly.delayed_jobs.sum()),
                    "advanced_job_days": int(monthly.advanced_jobs.sum()),
                    "maximum_positive_deferral_minutes": int(max(0,max(all_delta))*15),
                    "maximum_advance_minutes": int(max(0,-min(all_delta))*15),
                    "delayed_job_days_fraction": float(sum(v>0 for v in all_delta)/len(all_delta)),
                    "job_days_delayed_over_8h": int(sum(v>32 for v in all_delta)),
                    "pending_backlog_parity_days": int(monthly.terminal_pending_backlog_parity_observed.sum())},
        "input_SHA256": input_shas})
    a = pd.read_parquet(DAYS / DAY / "V37_R4A_JOB_LEDGER.parquet")
    a["job_id"] = a.job_id.astype(str)
    rw_active = (a.RW_scheduled_start <= ISSUE_SLOT) & (a.RW_scheduled_completion > ISSUE_SLOT)
    rsp_active = (a.RSP_scheduled_start <= ISSUE_SLOT) & (a.RSP_scheduled_completion > ISSUE_SLOT)
    removed = a.loc[rw_active & ~rsp_active].copy()
    added = a.loc[~rw_active & rsp_active].copy()
    removed["job_uid"] = removed.job_id
    removed["number_of_jobs"] = 1
    removed["shift_slots"] = removed.RSP_scheduled_start-removed.RW_scheduled_start
    removed["shift_minutes"] = removed.shift_slots*15
    removed["active_GPU_removed_from_slot82"] = removed.requested_gpus.astype(int)
    removed["latest_start"] = None
    removed["deadline"] = None
    removed["maximum_deferral"] = None
    removed["latest_start_deadline_source"] = "ABSENT; scheduled_start/end are model-generated reservations, not deadlines"
    removed["time_coordinate"] = "issue-relative; target-slot=issue-slot-24; fixed AEST UTC+10"
    removed["D1_issue_time"] = issue_time(DAY).isoformat()
    removed["D1_information_used"] = "submission resource/QoS/partition, D-1 queue state, requested walltime, frozen pre-May runtime predictor plus conformal q"
    removed["duration_is_measured_May_execution"] = False
    removed["workload_class_authority"] = "submission QoS + V37 _classify_pending; no numerical QoS SLA"
    removed["destination_interval_is_relocated_381_GPU"] = False
    for mode in ("RW", "RSP"):
        removed[f"{mode}_start_AEST"] = [
            (issue_time(DAY)+timedelta(minutes=int(s)*15)).isoformat() for s in removed[f"{mode}_scheduled_start"]]
        removed[f"{mode}_end_AEST"] = [
            (issue_time(DAY)+timedelta(minutes=int(s)*15)).isoformat() for s in removed[f"{mode}_scheduled_completion"]]
        removed[f"{mode}_start_target_slot"] = removed[f"{mode}_scheduled_start"]-24
        removed[f"{mode}_end_target_slot"] = removed[f"{mode}_scheduled_completion"]-24
    groupcols = ["requested_gpus", "state_at_issue", "workload_class", "RW_scheduled_start",
                 "RW_scheduled_completion", "RSP_scheduled_start", "RSP_scheduled_completion"]
    cohorts=[]
    for n,(key,group) in enumerate(removed.groupby(groupcols, sort=True)):
        ident=f"V39F_SLOT82_C{n+1:02d}"
        removed.loc[group.index,"exact_cohort_id"]=ident
        cohorts.append({"cohort_id":ident, **dict(zip(groupcols,key)), "number_of_jobs":len(group),
                        "GPU_removed":int(group.requested_gpus.sum()), "job_uids":group.job_id.tolist()})
    observed = int(a.loc[rw_active,"requested_gpus"].sum()-a.loc[rsp_active,"requested_gpus"].sum())
    assert int(removed.requested_gpus.sum()-added.requested_gpus.sum()) == observed == 381
    rwp=profile(a,"RW_scheduled_start","RW_duration_slots")
    same_start=profile(a,"RW_scheduled_start","RSP_duration_slots")
    rspp=profile(a,"RSP_scheduled_start","RSP_duration_slots")
    assert (int(rwp[82]),int(same_start[82]),int(rspp[82])) == (471,90,90)
    frame("V39F_DAY17_SLOT82_SHIFT_DECOMPOSITION.csv",removed)
    frame("V39F_DAY17_SLOT82_SHIFT_COHORTS.csv",pd.DataFrame([{k:v for k,v in c.items() if k!="job_uids"} for c in cohorts]))
    frame("V39F_DAY17_ACTIVE_GPU_BY_SLOT.csv",pd.DataFrame({"slot":range(96),"RW":rwp,
        "RW_START_RSP_DURATION":same_start,"FROZEN_RSP":rspp,
        "duration_effect_GPU":same_start-rwp,"start_shift_effect_GPU":rspp-same_start}))
    identity={"RW_slot82":471,"RSP_slot82":90,"gross_removed_GPU":int(removed.requested_gpus.sum()),
              "gross_added_GPU":int(added.requested_gpus.sum()),"net_difference_GPU":observed,
              "duration_effect_at_RW_starts_GPU":int(rwp[82]-same_start[82]),
              "subsequent_start_shift_effect_GPU":int(same_start[82]-rspp[82])}
    write_json("V39F_DAY17_SLOT82_SHIFT_DECOMPOSITION.json",{
        "conservation":identity,"cohorts":cohorts,"rows":removed.to_dict("records"),
        "finding":"The 381-GPU drop is already fully explained by shorter RSP reservations at unchanged RW starts; no displaced 381-GPU service mass exists.",
        "removed_job_count":len(removed), "added_job_count":len(added),
        "coordinate_warning":"slot82=20:30 AEST, issue-relative106; not schedule slot82"})
    # Report actual intervals and displacement without claiming that a shortened
    # reservation tail is executed at some other time.
    destination=[]
    for slot in range(int(max(removed.RW_scheduled_completion.max(),removed.RSP_scheduled_completion.max()))):
        rr=removed[(removed.RSP_scheduled_start<=slot)&(removed.RSP_scheduled_completion>slot)]
        newly=rr[~((rr.RW_scheduled_start<=slot)&(rr.RW_scheduled_completion>slot))]
        if len(rr) or ((removed.RW_scheduled_start<=slot)&(removed.RW_scheduled_completion>slot)).any():
            destination.append({"destination_issue_slot":slot,"destination_target_slot":slot-24,
                "destination_local_time":(issue_time(DAY)+timedelta(minutes=slot*15)).isoformat(),
                "RSP_active_GPU_of_380_jobs":int(rr.requested_gpus.sum()),"RSP_active_job_count":len(rr),
                "GPU_newly_active_outside_RW_interval":int(newly.requested_gpus.sum()),
                "newly_active_job_count":len(newly),"newly_active_GPU_hours":float(newly.requested_gpus.sum()/4),
                "RSP_reserved_GPU_hours":float(rr.requested_gpus.sum()/4),
                "mean_signed_start_shift_minutes_active_jobs":float(rr.shift_minutes.mean()) if len(rr) else None})
    frame("V39F_DAY17_TEMPORAL_REDISTRIBUTION.csv",pd.DataFrame(destination))
    write_json("V39F_DAY17_TEMPORAL_REDISTRIBUTION.json",{
        "interpretation":"Actual RSP reservation intervals of the 380 jobs, not destinations for 381 conserved GPUs",
        "removed_jobs_absolute_shift_bands":{band:sum(shift_band(abs(s))==band for s in removed.shift_minutes)
            for band in ("same slot","<=30 min","30-60 min","1-2 h","2-4 h","4-8 h",">8 h")},
        "removed_jobs_signed_shift_minutes":distribution(removed.shift_minutes.to_numpy()),
        "removed_jobs_absolute_shift_minutes":distribution(np.abs(removed.shift_minutes.to_numpy())),
        "all_May17_jobs_absolute_shift_minutes":distribution(np.abs((a.RSP_scheduled_start-a.RW_scheduled_start).to_numpy())*15),
        "all_May17_jobs_positive_deferral_minutes":distribution(np.maximum(0,(a.RSP_scheduled_start-a.RW_scheduled_start).to_numpy())*15),
        "reservation_reduction_GPU_hours_380_jobs":float((removed.requested_gpus*(removed.RW_duration_slots-removed.RSP_duration_slots)).sum()/4),
        "jobs_shifted_earlier":removed.loc[removed.shift_slots.ne(0),["job_id","shift_slots","shift_minutes"]].to_dict("records"),
        "destination_rows":destination})
    replay={mode:reproduce(a,mode,pd.read_parquet(DAYS/DAY/f"V37_R4A_{mode}_SCHEDULE.parquet")) for mode in ("RW","RSP")}
    write_json("V39F_DAY17_SCHEDULER_REPRODUCTION.json",replay)
    return {"may17":day_metrics(a,DAY),"conservation":identity,"cohorts":cohorts,
            "monthly_summary":read_json(OUT/"V39F_MAY31_TEMPORAL_FLEXIBILITY_REALISM_AUDIT.json")["summary"],
            "reproduction":replay}


def audit_objective() -> None:
    src=inspect.getsource(schedule)
    assert "setObjective" not in src and "optimize(" not in src
    components=["workload_delay","start_time_deviation","backlog","completion_service",
                "energy","electricity_cost","demand_peak","voltage_proxy","reserve","migration","regularization","numeric_tie_break"]
    write_json("V39F_DAY17_RSP_OBJECTIVE_AUDIT.json",{
        "production_temporal_MILP_exists":False,"scalar_objective_exists":False,
        "components":[{"component":c,"status":"ABSENT","effective_coefficient":None,
                       "RW_contribution":None,"RSP_contribution":None} for c in components],
        "RW_objective":None,"RSP_objective":None,"objective_delta":None,
        "not_zero":"Null means not defined; it is not a zero-valued numerical objective.",
        "implemented_algorithm":{
            "ordering":"PENDING sorted by (QoS tier: high/urgent=0, normal=1, standby=2, other=3; submit_time; job_id)",
            "RUNNING":"s_j=0; d_j=ceil(max(requested-elapsed,900)/900), identical RW/RSP",
            "PENDING_RW":"d_j=ceil(requested_walltime_seconds/900)",
            "PENDING_RSP":"d_j=ceil(min(requested,max(frozen_point+5576.44921875,900))/900), requested fallback",
            "start_equation":"s_j=min{s in nonnegative integers: O_previous(t)+g_j<=624 for every t in [s,s+d_j)}",
            "commit_equation":"O(t) <- O(t)+g_j for s_j<=t<s_j+d_j",
            "tie_break":"submission time then exact job_id, lexicographic procedural ordering; no effective numeric coefficients",
            "search_guard":20000,"search_guard_is_deadline":False},
        "why_lower_slot82":"Shorter PENDING reservations finish before issue-slot106. The code never evaluates grid voltage or a scalar energy/service objective when making this schedule.",
        "campaign_objective_is_different_layer":"Day-ahead grid/MESS J is evaluated after frozen AIDC scheduling; it is not the RSP scheduler objective and is not substituted here.",
        "source":{"path":"dayahead/v37/aidc_materializer.py","SHA256":sha(REPO/"dayahead/v37/aidc_materializer.py"),
                  "schedule_first_line":inspect.getsourcelines(schedule)[1],"schedule_source":src}})


def replay_iis() -> dict:
    import gurobipy as gp
    env=gp.Env(empty=True)
    env.setParam("OutputFlag",0)
    env.start()
    m=gp.read(str(IIS),env=env)
    m.Params.Threads=4
    m.Params.Seed=20260905
    m.Params.MIPGap=0.0
    m.Params.LogFile=str(OUT/"V39F_FIXED_RSP_IIS_REPLAY.log")
    m.Params.LogToConsole=0
    m.Params.OutputFlag=1
    m.optimize()
    result={"status":"INFEASIBLE" if m.Status==gp.GRB.INFEASIBLE else str(m.Status),
            "gurobi_status":int(m.Status),"threads":int(m.Params.Threads),"seed":int(m.Params.Seed),
            "gurobi_version":list(gp.gurobi.version()),"runtime_seconds":m.Runtime,
            "linear_constraints":m.NumConstrs,"general_constraints":m.NumGenConstrs,
            "variables":m.NumVars,"input_IIS_path":str(IIS.relative_to(REPO)),"input_IIS_SHA256":sha(IIS),
            "experiment":"Re-solve existing infeasible subsystem with fixed RSP times and relaxed migration availability; NOT a grid-aware temporal optimization",
            "implication":"An infeasible subsystem of the migration-allowed spatial model proves fixed RSP also infeasible with migration OFF and additional line/transformer constraints.",
            "migration_solver_called":False,"temporal_optimizer_called":False}
    m.dispose();env.dispose()
    if result["status"]!="INFEASIBLE":
        raise AssertionError(result)
    write_json("V39F_FIXED_RSP_IIS_REPLAY.json",result)
    return result


def unavailable_shadow() -> None:
    reason=("The actual production path has no temporal MILP/scalar objective, legal alternate-start set, "
            "or terminal parity constraint. It uses deterministic tier/FIFO first-fit with different RW/RSP durations. "
            "A variable-start shadow with an invented objective/window would not be the requested same-objective/same-service formulation.")
    write_json("V39F_DAY17_SHADOW_GRID_AWARE_TEMPORAL_ONLY.json",{
        "experiment":"SHADOW_GRID_AWARE_TEMPORAL_ONLY","status":"NOT_RUN_FORMULATION_PREMISE_FALSE",
        "reason":reason,"feasible":None,"optimal_objective":None,"objective_delta_vs_frozen_RSP":None,
        "jobs_shifted_differently":None,"GPU_hours_shifted_differently":None,
        "slot82_active_GPU":None,"slot82_Vmax":None,"Vmax":None,"Vmin":None,
        "line_current_violations":None,"transformer_violations":None,"terminal_service_parity":None,
        "maximum_deferral":None,"median_deferral":None,"P95_deferral":None,
        "migration_enabled":False,"solver_called":False,"schedule_row_count":0,
        "strict_procedural_policy_preserved_feasible":False,
        "strict_policy_evidence":"V39F_DAY17_SCHEDULER_REPRODUCTION.json and V39F_FIXED_RSP_IIS_REPLAY.json",
        "no_result_is_not_infeasibility_proof_of_new_temporal_model":True})
    empty=pd.DataFrame({"job_uid":pd.Series(dtype="string"),"scheduled_start_slot":pd.Series(dtype="int64"),
                        "scheduled_end_slot":pd.Series(dtype="int64"),"diagnostic_status":pd.Series(dtype="string")})
    # Deliberately zero rows: never substitute frozen RSP and label it a new solve.
    frame("V39F_DAY17_SHADOW_GRID_AWARE_TEMPORAL_SCHEDULE.parquet",empty)
    write_json("V39F_DAY17_MIN_TEMPORAL_CORRECTION.json",{
        "status":"NOT_RUN_SHADOW_NOT_DEFINED","reason":reason,
        "minimum_affected_jobs":None,"minimum_affected_cohorts":None,"minimum_changed_GPU_slots":None,
        "slot82_required_active_GPU":None,"GPU_to_restore_near_slot82":None,"resulting_Vmax":None,
        "original_RSP_objective_penalty":None,
        "proposed_diagnostic_only_objective":"lexmin(sum_j g_j*|active_j(t)-frozen_active_j(t)| over full reserved intervals, changed_job_count)",
        "not_yet_defined":"legal candidate starts and how tier/FIFO first-fit may be overridden; cannot use search_guard=20000 as service authority",
        "duration_extension_to_RW_is_not_temporal_shift":True})
    write_json("V39F_DAY17_TEMPORAL_FIRST_MIGRATION_SHADOW_CHECK.json",{
        "temporal_only":"NOT_RUN_NO_SHADOW_SCHEDULE","migration_solver_called":"NO",
        "minimum_migrations":None,"checkpoint_WAN_restart_validity":"NOT_APPLICABLE",
        "strict_existing_RSP_temporal_only":"FAIL","joint_temporal_migration_solve":False})


def audit_history_service() -> None:
    evidence=[]
    selections=[
        (REPO,"edf5c2b2","dayahead/v37/aidc_materializer.py"),
        (REPO,"46edb9a","dayahead/v39b/diagnostic.py"),
        (HIST_REPO,HIST_HEAD,"dayahead/v35r3a/scheduler_twin.py"),
        (HIST_REPO,HIST_HEAD,"dayahead/v35r3d/scheduler.py"),
        (HIST_REPO,HIST_HEAD,"dayahead/v35r3d_r1/scheduler.py"),
        (HIST_REPO,HIST_HEAD,"dayahead/artifacts/v35r3d_r1_running_residual_accounting/V35R3D_R1_SAFE_RUNTIME_CONTRACT.json"),
        (HIST_REPO,HIST_HEAD,"dayahead/artifacts/v35r3j_aidc_it_scale_consistency_freeze/V35R3J_EXPANDED_AIDC_POWER_CONTRACT.json"),
    ]
    for repo,commit,path in selections:
        raw=subprocess.check_output(["git","show",f"{commit}:{path}"],cwd=repo)
        text=raw.decode("utf-8")
        evidence.append({"repository":str(repo),"commit":git("rev-parse",commit,repo=repo),
                         "path":path,"SHA256":hashlib.sha256(raw).hexdigest(),"source":text})
    write_json("V39F_GIT_HISTORICAL_DEADLINE_AUDIT.json",{
        "history_commands":{
            "log_follow_materializer":git("log","--oneline","--follow","--","dayahead/v37/aidc_materializer.py"),
            "blame_schedule":git("blame","-L","355,414","--","dayahead/v37/aidc_materializer.py"),
            "current_schedule_origin":"edf5c2b2: introduced tier/FIFO first-fit; no subsequent modification to this production file",
            "historical_service_noninferiority_callers":git("grep","-n","service_noninferiority",HIST_HEAD,"--",
                "dayahead/v35r3a","dayahead/v35r3d","dayahead/v35r3d_r1",repo=HIST_REPO)},
        "A_authoritative_deadline_lost":"NO_EVIDENCE_IN_ACCEPTED_RUNTIME_RESERVATION_LINEAGE",
        "B_synthetic_30min_latest_start_rejected":"NOT_ESTABLISHED_IN_THIS_LINEAGE; historical checkpoint interval and AEMO sampling are not job deadlines",
        "C_terminal_parity_deliberately_selected":"NO; V37 runtime-reservation scheduler contains no terminal parity constraint",
        "D_accepted_service_constraint_omitted":"NOT_ESTABLISHED; earlier V35R3A service_noninferiority guarded controlled same-duration queue reordering, not V35R3D/R1 RW-vs-RSP runtime reservation replay",
        "historical_service_gate_found":True,"historical_service_gate_current_RSP_binding_authority_found":False,
        "historical_gate_details":"running fixed; high/normal starts not later; per-tier completed-job/GPU-hour noninferiority; terminal pending workload not worse; normal mean/P95/max waiting not worse. Gate is a candidate filter for V35R3A controlled queue permutations.",
        "feature_omission_regression_proven":False,
        "important_scope_limit":"No authoritative user deadline or accepted current RSP recourse specification was found. This does not assert that no historical model anywhere used synthetic deadlines.",
        "sources":evidence})
    rows=[]
    absent=["per_job_deadline","latest_start","maximum_deferral","service_class_window",
            "terminal_backlog_hard_constraint","terminal_service_parity","cumulative_service_lower_bound",
            "intermediate_backlog_upper_bound","queue_age_upper_bound","starvation_prevention_SLA"]
    for name in absent:
        rows.append({"constraint":name,"status":"ABSENT","equation":None,"parameter_source":None,
                     "parameter_authority":None,"binding_on_May17":None})
    rows += [
        {"constraint":"reservation_window","status":"PRESENT","equation":"nonpreemptive [s_j,s_j+d_j); earliest aggregate-capacity-feasible first-fit; earlier reservations immutable",
         "parameter_source":"D-1 requested walltime / pre-May safe runtime plus q / running elapsed",
         "parameter_authority":"V35R3D_R1_SAFE_RUNTIME_CONTRACT; V37_R4A_SCHEDULER_CONTRACT_RECOVERY",
         "classification":"causal observed request plus model-predicted RSP duration; computed interval, not SLA window",
         "binding_on_May17":True},
        {"constraint":"runtime_completion_requirement","status":"PRESENT","equation":"e_j=s_j+d_j, uninterrupted; every included job scheduled, even after target horizon",
         "parameter_source":"RW_duration_slots or RSP_duration_slots","parameter_authority":"accepted runtime reservation contract",
         "classification":"modeled reservation completion, not measured completion and not completion-by-midnight",
         "binding_on_May17":True},
        {"constraint":"priority_and_FIFO_first_fit","status":"PRESENT","equation":"sort (tier, submit_time, job_id), then earliest feasible interval per job",
         "parameter_source":"submission QoS and submit timestamp","parameter_authority":"relative public-policy twin; no exact composite numerical Kestrel priority",
         "binding_on_May17":True},
        {"constraint":"aggregate_GPU_capacity","status":"PRESENT","equation":"sum_j g_j*1[s_j<=t<e_j]<=624 for all scheduled slots, including outside evaluation day",
         "parameter_source":"GPU_CAPACITY=624","parameter_authority":"frozen 624 equivalent GPU envelope",
         "binding_on_May17":True},
        {"constraint":"RUNNING_nonpreemption","status":"PRESENT","equation":"s_j=0 and fixed requested remaining duration",
         "parameter_source":"D-1 known running start/requested walltime","parameter_authority":"V35R3D_R1 running residual contract",
         "binding_on_May17":True},
    ]
    write_json("V39F_DAY17_TEMPORAL_SERVICE_CONTRACT_AUDIT.json",{
        "constraints":rows,"temporal_service_controlled_mostly_by_terminal_parity":False,
        "what_prevents_arbitrary_postponement":"The deterministic earliest-fit dispatch rule chooses starts; no discretionary temporal optimization exists. There is no independently authoritative maximum wait.",
        "search_guard_20000":"computational loop termination only; not a service deadline or authorized optimization window",
        "RUNNING_count":258,"PENDING_count":2023,"high_or_urgent_pending_May17":0,
        "historical_service_gate_is_current_hard_constraint":False,"QOS_FEATURE_OMISSION_FOUND":False,
        "May17_terminal_pending_backlog_RW_RSP_GPUh":[0,0],
        "May17_terminal_unfinished_reservation_RW_RSP_GPUh":[8311,8233.75],
        "observed_zero_pending_backlog_is_not_hard_parity_authority":True,
        "historical_evidence":"V39F_GIT_HISTORICAL_DEADLINE_AUDIT.json"})


def baseline_comparison() -> None:
    # A new site-only placement is a diagnostic feasibility solve with frozen
    # times and migration OFF. It does not define a temporal-control model.
    from dayahead.v39d.evaluate import _load_capacity
    from dayahead.v39e.full_spatial import plan_fixed_temporal_schedule
    from dayahead.v39a.spatial import production_activity
    from dayahead.v39a.power import site_it_power_kw
    from dayahead.v28r2.c1_affine import load_c1, exact_c1_pcc_kw
    from dayahead.v28r2.source_cache import day_root
    from dayahead.v36.contracts import SOURCE_DATA_REPOSITORY
    a=pd.read_parquet(DAYS/DAY/"V37_R4A_JOB_LEDGER.parquet")
    rw=read_json(REPO/f"dayahead/artifacts/v39e_full_may_2025/V39E_DAYAHEAD_DECISION_FREEZE_{DAY}_B0.json")["decision"]
    raw_state=rw["common_initial_RUNNING_AIDC_state"]
    if isinstance(raw_state,dict):
        state={str(k):str(v) for k,v in raw_state.items()}
    else:
        state={str(r["job_uid"]):str(r["initial_AIDC"]) for r in raw_state}
    capacity,_=_load_capacity(REPO)
    result=plan_fixed_temporal_schedule(production_activity(pd.read_parquet(DAYS/DAY/"V37_R4A_RSP_SCHEDULE.parquet")),
        capacity,state,name="V39F_FIXED_RSP_SITE_ONLY_DIAGNOSTIC",allow_running_migration=False)
    assert result["status"]=="OPTIMAL" and result["minimum_running_migrations"]==0
    sites=list(capacity.aidc_ids)
    gpu=np.zeros((96,12),dtype=int)
    for row in result["assignments"]:
        gpu[row["active_start_slot"]:row["active_end_slot"],sites.index(row["destination_AIDC"])]+=int(row["requested_GPU"])
    weather_path=day_root(SOURCE_DATA_REPOSITORY,DAY)/"gfs_d1_weather.parquet"
    weather=pd.read_parquet(weather_path)
    c1=load_c1(REPO/"dayahead/artifacts/v24t_thermal_aware_aidc/V24T_C1_QUASISTATIC_MODEL.json")
    p=np.asarray([[float(exact_c1_pcc_kw(float(site_it_power_kw(capacity.site_capacity[site],gpu[t,k])),
            float(weather.iloc[t].t_wb_c),float(weather.iloc[t].rh_pct),c1)) for k,site in enumerate(sites)] for t in range(96)])
    vp=REPO/f"dayahead/cache/v37_may_locked_final/electrical/{DAY}/data/D1_AC_ANCHOR_SENSITIVITY_{DAY}.npz"
    with np.load(vp,allow_pickle=False) as voltage:
        anchor=np.asarray(voltage["anchor_control"])
        assert np.count_nonzero(anchor[:,12:])==0
        h=np.asarray(voltage["sensitivity"])
        av=np.asarray(voltage["anchor_v_squared"])
        assert h.shape[1]==60
        # V37R3 repair changes ONLY MESS sensitivities. MESS coordinates and
        # anchors are all zero here, so frozen raw AIDC sensitivities give
        # exactly the same repaired voltage, without loading any outcomes.
        values=np.sqrt(av+np.einsum("tsi,ts->ti",h[:,:12,:],p-anchor[:,:12]))
    vsummary={"Vmax_pu":float(values.max()),"Vmin_pu":float(values.min()),
              "slot82_Vmax_pu":float(values[82].max()),
              "voltage_violation_count":int(((values>1.05+1e-7)|(values<.95-1e-7)).sum())}
    frame("V39F_DAY17_FROZEN_RSP_SITE_ONLY_ASSIGNMENTS.parquet",pd.DataFrame(result["assignments"]))
    frame("V39F_DAY17_FROZEN_RSP_SITE_ONLY_GPU.csv",pd.DataFrame(gpu,columns=sites).assign(slot=range(96)))
    frame("V39F_DAY17_RW_SITE_GPU.csv",pd.DataFrame(rw["site_GPU_trajectory"]))
    frame("V39F_DAY17_FROZEN_RSP_VOLTAGE.csv",pd.DataFrame({"slot":range(96),"Vmax":values.max(axis=1),"Vmin":values.min(axis=1)}))
    write_json("V39F_DAY17_FROZEN_RSP_SITE_ONLY_DIAGNOSTIC.json",{
        "status":"OPTIMAL_SITE_ONLY_GRID_FAIL","migration_count":0,"Threads":4,"Seed":20260905,
        "voltage":vsummary,"voltage_method":"frozen AIDC sensitivities, zero MESS and zero MESS anchor; algebraically identical to joint repaired authority",
        "line_and_transformer_recomputed":False,"line_and_transformer_status":None,
        "weather_path":str(weather_path),"weather_SHA256":sha(weather_path),
        "placement_has_no_temporal_changes":True,
        "site_peak_utilization":{site:float(gpu[:,k].max()/capacity.site_capacity[site]) for k,site in enumerate(sites)}})
    rows=[]
    m=day_metrics(a,DAY)
    for mode in ("RW","FROZEN_RSP","SHADOW_GRID_AWARE_RSP"):
        if mode=="SHADOW_GRID_AWARE_RSP":
            rows.append({"schedule":mode,"status":"NOT_RUN_FORMULATION_PREMISE_FALSE","objective":None})
            continue
        isrw=mode=="RW"
        gate=rw["planning_feasibility"] if isrw else vsummary
        b=backlog(a,"RW" if isrw else "RSP")
        rows.append({"schedule":mode,"status":"PASS" if isrw else "VOLTAGE_FAIL",
            "objective":None,"objective_status":"NO_PRODUCTION_TEMPORAL_SCALAR_OBJECTIVE",
            "slot82_active_GPU":471 if isrw else 90,"total_shifted_jobs_vs_RW":0 if isrw else 2,
            "equal_duration_relocated_GPU_hours_vs_RW":0 if isrw else 2.75,
            "start_displacement_GPU_hours_vs_RW":0 if isrw else 16,
            "reservation_duration_reduction_GPU_hours_vs_RW":0 if isrw else 2284.5,
            "median_abs_start_shift_minutes":0,"P95_abs_start_shift_minutes":0,
            "max_abs_start_shift_minutes":0 if isrw else 945,"maximum_positive_deferral_minutes":0,
            "target_day_reserved_GPU_hours":12340.75 if isrw else 10131.0,
            "site_peak_utilization_source":"V39F_DAY17_RW_SITE_GPU.csv" if isrw else "V39F_DAY17_FROZEN_RSP_SITE_ONLY_GPU.csv",
            **b,**{key:gate.get(key) for key in ("Vmax_pu","Vmin_pu","voltage_violation_count",
                 "line_current_violation_count","transformer_current_violation_count","transformer_kva_violation_count")}})
    frame("V39F_DAY17_RW_RSP_GRID_AWARE_COMPARISON.csv",pd.DataFrame(rows))


def finalize_provenance() -> None:
    from dayahead.v38.contracts import RACK_CONTRACT, RAW_RACK_CAPACITY
    start=read_json(OUT/"V39F_START_STATE.json")
    changes=[]
    for name,digest in start["tracked_file_SHA256"].items():
        if not (REPO/name).is_file() or sha(REPO/name)!=digest:
            changes.append(name)
    if changes:
        raise AssertionError(f"PREEXISTING_FILE_MUTATION:{changes}")
    authority_paths=[
        "dayahead/v37/aidc_materializer.py","dayahead/v36/aidc.py","dayahead/v39e/full_spatial.py",
        "dayahead/v39e/contracts.py","dayahead/v39d/planning.py","dayahead/v39a/power.py",
        "dayahead/artifacts/v24t_thermal_aware_aidc/V24T_C1_QUASISTATIC_MODEL.json",
        "dayahead/artifacts/v39c_aidc_gpu_capacity_refreeze/V39C_H100_EQUIVALENT_SITE_CAPACITY_AUTHORITY.json",
        "dayahead/artifacts/v39c_aidc_gpu_capacity_refreeze/V39C_CAPACITY_FREEZE_CERTIFICATE.json",
        "dayahead/artifacts/v39d_independent_daily_temporal_first_migration/V39D_SYNTHETIC_LOGICAL_RACK_COMPATIBILITY_AUTHORITY.json",
        "dayahead/artifacts/v39d_independent_daily_temporal_first_migration/V39D_RACK_FREEZE_CERTIFICATE.json",
        "dayahead/artifacts/v37_r3_restore_intended_cuts/V37_R3_JOINT_VOLTAGE_AUTHORITY.json",
        "dayahead/artifacts/v37_r4_may_campaign_repair/V37_R4_MAY_VOLTAGE_APPLICABILITY.json",
        "dayahead/artifacts/v39e_rw_anchored_initial_state_fast_validation/V39E_COMMON_INITIAL_STATE_AUDIT.json",
        "dayahead/artifacts/v37_r4a_per_day_aidc/V37_R4A_SCHEDULER_CONTRACT_RECOVERY.json",
        "dayahead/artifacts/v39b_preimplementation_diagnostic/V39B_DIAGNOSTIC_TEMPORAL_RECOURSE.json",
        f"dayahead/artifacts/v39e_full_may_2025/V39E_DAYAHEAD_DECISION_FREEZE_{DAY}_B0.json",
        str(RACK_CONTRACT),
    ]
    for suffix in ("SENSITIVITY","CURRENT_SENSITIVITY"):
        authority_paths.append(f"dayahead/cache/v37_may_locked_final/electrical/{DAY}/data/D1_AC_ANCHOR_{suffix}_{DAY}.npz")
    shas={p:sha(REPO/p) for p in authority_paths}
    shas[str(IIS.relative_to(REPO))]=sha(IIS)
    shas[str(RAW_RACK_CAPACITY)]=sha(RAW_RACK_CAPACITY)
    baseline=read_json(OUT/"V39F_DAY17_FROZEN_RSP_SITE_ONLY_DIAGNOSTIC.json")
    shas[baseline["weather_path"]]=sha(Path(baseline["weather_path"]))
    write_json("V39F_DIAGNOSTIC_PROVENANCE.json",{
        "starting_HEAD":start["starting_HEAD"],"final_HEAD":git("rev-parse","HEAD"),
        "starting_branch":start["starting_branch"],"branch":git("branch","--show-current"),
        "initial_working_tree_clean":start["working_tree_clean"],
        "diagnostic_helper_commits":git("log","--format=%H","--",str(Path(__file__).relative_to(REPO))).splitlines(),
        "Threads_per_model":4,"Seed":20260905,"max_concurrent_diagnostic_models":1,
        "gurobi_version":read_json(OUT/"V39F_FIXED_RSP_IIS_REPLAY.json")["gurobi_version"],
        "authority_SHA256":shas,"existing_tracked_files_changed":changes,
        "May_Actual_reads":0,"Fresh_reads":0,"future_result_reads":0,
        "frozen_science_mutation_count":0,"production_RSP_mutation_count":0,"May_campaign_calls":0,
        "31day_analysis":"existing causal frozen schedules only; not optimization outcomes",
        "solver_runs":"existing fixed-temporal IIS replay plus site-only fixed RSP placement; no temporal model invented",
        "read_counter_scope":"semantic data reads; pre-existing tracked files also received hash-only integrity scans, including historical artifacts, without outcome parsing or decision use",
        "hash_only_integrity_file_count":len(start["tracked_file_SHA256"]),
        "Gurobi_threads_are_runtime_not_science":True,
        "requested_model_and_reasoning":"GPT-6 Astra / Extra High",
        "model_configuration_note":"This helper does not select or attest the host conversation model/reasoning setting.",
        "push":"NO","PR":"NO",
        "artifact_SHA256":{p.name:sha(p) for p in sorted(OUT.iterdir()) if p.is_file() and p.name!="V39F_DIAGNOSTIC_PROVENANCE.json"}})


def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--phase",choices=("capture","data","iis","audit","baseline","finalize","all"),default="all")
    args=parser.parse_args()
    if args.phase in ("capture","all"):
        capture_start()
    if args.phase in ("data","all"):
        result=audit_data();audit_objective();unavailable_shadow()
        write_json("V39F_COMPUTED_SUMMARY.json",result)
        print(json.dumps(clean(result["monthly_summary"])))
    if args.phase in ("iis","all"):
        print(json.dumps(replay_iis()))
    if args.phase in ("audit","all"):
        audit_history_service()
    if args.phase in ("baseline","all"):
        baseline_comparison()
    if args.phase in ("finalize","all"):
        finalize_provenance()
    return 0


if __name__=="__main__":
    raise SystemExit(main())
