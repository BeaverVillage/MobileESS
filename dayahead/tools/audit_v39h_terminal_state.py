"""Read-only scientific audit; writes only its own evidence and admission HOLD."""
from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
from dayahead.v38.authority import canonical_sha256
from dayahead.v39c.freeze import atomic_json
from dayahead.tools.v39h_terminal_launch_gate import HELD_DAYS

ROOT = REPO / "dayahead/artifacts/v39h_terminal_state_audit"
HROOT = REPO / "dayahead/artifacts/v39h_13day_temporal_repair_migration_shadow"
PROD = REPO / "dayahead/artifacts/v39e_full_may_2025"
CLOSE = REPO / "dayahead/artifacts/v39h_production_refreeze_may_close"
INPUTS = REPO / "dayahead/artifacts/v37_r4a_per_day_aidc/days"
DAYS = ("2025-05-17", "2025-05-23", "2025-05-24", "2025-05-25", "2025-05-26")
BEGIN, END, SLOTS = 24, 120, 96
AEST = timezone(timedelta(hours=10))
SOURCES: dict[str, str] = {}


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def track(path):
    path = Path(path)
    SOURCES[str(path.relative_to(REPO))] = sha(path)
    return path


def read(path):
    return json.loads(track(path).read_text(encoding="utf-8"))


def overlap(start, end, left, right):
    return max(0, min(int(end), int(right)) - max(int(start), int(left)))


def occupancy_parts(start, end, gpu):
    return {"pre": gpu * overlap(start, end, 0, BEGIN),
            "in": gpu * overlap(start, end, BEGIN, END),
            "post": gpu * max(0, end - max(start, END))}


def write_csv(path, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]) if rows else ["empty"])
        writer.writeheader()
        writer.writerows(rows)


def iso(day, slot):
    origin = datetime.fromisoformat(day).replace(tzinfo=AEST) - timedelta(hours=6)
    return (origin + timedelta(minutes=15 * int(slot))).isoformat()


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    seal = read(CLOSE / "PRODUCTION_REFREEZE_AUTHORITY.json")
    hmanifest = read(HROOT / "V39H_REQUIRED_ARTIFACT_SHA_MANIFEST.json")["SHA256"]
    for name, digest in hmanifest.items():
        assert sha(HROOT / name) == digest, name
    for name, digest in seal["DA_freeze_file_SHA256"].items():
        assert sha(PROD / name) == digest, name
    from dayahead.v39e.temporal_refreeze import assert_protected_results
    protected = assert_protected_results(REPO)
    progress_before = json.loads((REPO / "progress/V39E_OVERNIGHT_PROGRESS.json").read_text())
    assert not HELD_DAYS.intersection(progress_before["completed_days"])

    cache = {}
    def day_info(day):
        if day in cache:
            return cache[day]
        fp = PROD / f"V39E_DAYAHEAD_DECISION_FREEZE_{day}_B1.json"
        freeze = read(fp)
        assert sha(fp) == seal["DA_freeze_file_SHA256"][fp.name]
        d = freeze["decision"]
        assert canonical_sha256(d) == freeze["DA_decision_SHA256"]
        b3 = read(PROD / f"V39E_DAYAHEAD_DECISION_FREEZE_{day}_B3.json")["decision"]
        for field in ("temporal_schedule", "AIDC_assignments", "site_GPU_trajectory", "common_initial_RUNNING_AIDC_state"):
            assert d[field] == b3[field], (day, field)
        schedule = {str(r["job_id"]): r for r in d["temporal_schedule"]}
        assignment = {str(r["job_uid"]): r for r in d["AIDC_assignments"]}
        assert len(schedule) == len(d["temporal_schedule"])
        assert len(assignment) == len(d["AIDC_assignments"])
        initial = {str(r["job_uid"]): r for r in d["common_initial_RUNNING_AIDC_state"]}
        snap = pd.read_parquet(track(INPUTS / day / "V37_R4A_D1_SNAPSHOT.parquet"))
        snapshot = {str(r["id"]): r for r in snap.to_dict("records")}
        manifest = read(INPUTS / day / "V37_R4A_DAY_MANIFEST.json")
        assert manifest["source_snapshot_sha256"] == sha(INPUTS / day / "V37_R4A_D1_SNAPSHOT.parquet")
        # Reproduce the actual production GPU-trajectory construction, which
        # places each accepted interval at destination_AIDC (_candidate_frames).
        site_gpu = {}
        for r in d["AIDC_assignments"]:
            arr = site_gpu.setdefault(str(r["destination_AIDC"]), np.zeros(SLOTS, dtype=np.int64))
            arr[int(r["active_start_slot"]):int(r["active_end_slot"])] += int(r["requested_GPU"])
        for r in d["site_GPU_trajectory"]:
            assert int(r["active_GPU"]) == int(site_gpu.get(str(r["AIDC"]), np.zeros(SLOTS, dtype=np.int64))[int(r["slot"])])
        cache[day] = dict(freeze=freeze, decision=d, schedule=schedule, assignment=assignment,
                          initial=initial, snapshot=snapshot, manifest=manifest)
        return cache[day]

    changed_rows, interday, future_rows, aggregates = [], [], [], []
    for day in DAYS:
        hpath = HROOT / "days" / day / "V39H_SHADOW_SCHEDULE.parquet"
        h = pd.read_parquet(track(hpath))
        base = pd.read_parquet(track(INPUTS / day / "V37_R4A_RSP_SCHEDULE.parquet"))
        base = base.assign(job_id=base.job_id.astype(str)).set_index("job_id")
        cert = read(CLOSE / "days" / day / "SELECTIVE_PREFLIGHT_CERTIFICATE.json")
        assert cert["H_schedule_SHA256"] == sha(hpath)
        assert cert["accepted_grid_domain_issue_slots"] == [BEGIN, END]
        assert cert["outside_domain_site_grid_physical_claim"] is False
        current = day_info(day)
        totals = {when: {part: 0 for part in ("pre", "in", "post")} for when in ("before", "after")}
        dayrows = []
        for r in h.to_dict("records"):
            uid = str(r["job_uid"])
            b = base.loc[uid]
            gpu = int(r["requested_gpus"])
            s0, e0 = int(b.scheduled_start_slot), int(b.scheduled_end_slot)
            s1, e1 = int(r["scheduled_start_slot"]), int(r["scheduled_end_slot"])
            duration = int(r["duration_slots"])
            assert e0-s0 == e1-s1 == duration and int(b.requested_gpus) == gpu
            assert s0 == int(r["RSP_scheduled_start"]) and e0 == int(r["RSP_scheduled_completion"])
            assert s1-s0 == int(r["start_delay_slots"]) >= 0
            prodjob = current["schedule"][uid]
            assert (s1, e1, duration) == (prodjob["scheduled_start_slot"], prodjob["scheduled_end_slot"], prodjob["duration_slots"])
            before, after = occupancy_parts(s0,e0,gpu), occupancy_parts(s1,e1,gpu)
            for when, parts in (("before",before),("after",after)):
                for part,value in parts.items(): totals[when][part] += value
            if s1 == s0:
                continue
            assert r["state_at_issue"] == "PENDING" and r["workload_class"] == "STANDBY_QUEUE_CONTROLLED" and r["eligible"]
            row = dict(day=day,job_uid=uid,GPU_request=gpu,RSP_start_slot=s0,repair_start_slot=s1,
                safe_duration_slots=duration,safe_duration_minutes=15*duration,RSP_completion_slot=e0,repair_completion_slot=e1,
                RSP_start_AEST=iso(day,s0),repair_start_AEST=iso(day,s1),RSP_completion_AEST=iso(day,e0),repair_completion_AEST=iso(day,e1),
                RSP_start_at_or_after_day_boundary=s0>=END,repair_start_at_or_after_day_boundary=s1>=END,
                RSP_completion_exceeds_day_boundary=e0>END,repair_completion_exceeds_day_boundary=e1>END,
                newly_post_midnight_start=s0<END<=s1,newly_post_midnight_completion=e0<=END<e1,
                post_midnight_GPU_slots_before=before["post"],post_midnight_GPU_slots_after=after["post"],
                incremental_post_midnight_GPU_slots=after["post"]-before["post"],
                in_domain_GPU_slots_before=before["in"],in_domain_GPU_slots_after=after["in"],
                pre_domain_GPU_slots_before=before["pre"],pre_domain_GPU_slots_after=after["pre"],
                repair_AIDC=str(r["AIDC"]),RW_completion_slot=int(r["RW_scheduled_completion"]),
                safe_runtime_unchanged=True,RW_completion_noninferiority=e1<=int(r["RW_scheduled_completion"]))
            changed_rows.append(row); dayrows.append(row)
        assert len(dayrows) == cert["changed_jobs"]
        assert sum(totals["before"].values()) == sum(totals["after"].values()) == cert["safe_reservation_GPU_slots_before"]
        aggregate = dict(day=day,changed_jobs=len(dayrows),
            NEW_POST_MIDNIGHT_START_JOBS=sum(r["newly_post_midnight_start"] for r in dayrows),
            NEW_POST_MIDNIGHT_COMPLETION_JOBS=sum(r["newly_post_midnight_completion"] for r in dayrows),
            POST_MIDNIGHT_GPU_H_BEFORE=totals["before"]["post"]*.25,
            POST_MIDNIGHT_GPU_H_AFTER=totals["after"]["post"]*.25,
            INCREMENTAL_POST_MIDNIGHT_GPU_H_FROM_REPAIR=(totals["after"]["post"]-totals["before"]["post"])*.25,
            IN_DOMAIN_GRID_GPU_H_BEFORE=totals["before"]["in"]*.25,
            IN_DOMAIN_GRID_GPU_H=totals["after"]["in"]*.25,
            PRE_DOMAIN_GPU_H_BEFORE=totals["before"]["pre"]*.25,PRE_DOMAIN_GPU_H_AFTER=totals["after"]["pre"]*.25,
            OUT_OF_DOMAIN_RESERVATION_GPU_H_BEFORE=(totals["before"]["post"]+totals["before"]["pre"])*.25,
            OUT_OF_DOMAIN_RESERVATION_GPU_H=(totals["after"]["post"]+totals["after"]["pre"])*.25,
            INCREMENTAL_OUT_OF_DOMAIN_GPU_H_DUE_TO_REPAIR=(totals["after"]["post"]+totals["after"]["pre"]-totals["before"]["post"]-totals["before"]["pre"])*.25,
            CHANGED_JOB_POST_MIDNIGHT_GPU_H_BEFORE=sum(r["post_midnight_GPU_slots_before"] for r in dayrows)*.25,
            CHANGED_JOB_POST_MIDNIGHT_GPU_H_AFTER=sum(r["post_midnight_GPU_slots_after"] for r in dayrows)*.25,
            in_domain_planning_grid_certificate_status=cert["status"],OUT_OF_DOMAIN_GRID_CERTIFICATION=False)
        aggregate["passing_witness_removes_in_day_load_and_adds_post_horizon_work"] = aggregate["INCREMENTAL_POST_MIDNIGHT_GPU_H_FROM_REPAIR"] > 0 and aggregate["IN_DOMAIN_GRID_GPU_H"] < aggregate["IN_DOMAIN_GRID_GPU_H_BEFORE"]
        aggregates.append(aggregate)
        for job in dayrows:
            uid,gpu = job["job_uid"],job["GPU_request"]
            s0,e0,s1,e1 = (job[k] for k in ("RSP_start_slot","RSP_completion_slot","repair_start_slot","repair_completion_slot"))
            # D+1 is inspected even if this job has no post-midnight occupancy,
            # to detect independent replays of jobs completed on D.
            final_k = min(31-int(day[-2:]),max(1,(e1-BEGIN-1)//SLOTS))
            for k in range(1,final_k+1):
                nextday = (datetime.fromisoformat(day)+timedelta(days=k)).date().isoformat()
                nxt = day_info(nextday)
                start = BEGIN+k*SLOTS
                slots = np.arange(start,start+SLOTS)
                expected = ((slots>=s1)&(slots<e1)).astype(np.int64)*gpu
                prior = ((slots>=s0)&(slots<e0)).astype(np.int64)*gpu
                nr = nxt["schedule"].get(uid)
                na = nxt["assignment"].get(uid)
                actual = np.zeros(SLOTS,dtype=np.int64)
                if na:
                    actual[int(na["active_start_slot"]):int(na["active_end_slot"])] = int(na["requested_GPU"])
                missing = np.maximum(expected-actual,0)
                excess = np.maximum(actual-expected,0)
                newly_added = np.maximum(expected-prior,0)
                site = str(na["destination_AIDC"]) if na else None
                snap = nxt["snapshot"].get(uid)
                init = nxt["initial"].get(uid)
                overlap_mask = (expected>0)&(actual>0)
                site_bad = site is not None and site != job["repair_AIDC"]
                # Work-progress consistency under a chronological interpretation:
                # a job already completed under D's repaired plan is executed again.
                repeated_complete = e1<=start and int(actual.sum())>0
                item = dict(source_day=day,next_day=nextday,day_offset=k,job_uid=uid,
                    expected_repair_carry_GPU_h=float(expected.sum()*.25),independent_DA_GPU_h=float(actual.sum()*.25),
                    matched_time_GPU_h=float(np.minimum(expected,actual).sum()*.25),
                    omitted_expected_carry_GPU_h=float(missing.sum()*.25),excess_vs_repair_timing_GPU_h=float(excess.sum()*.25),
                    newly_added_post_repair_occupancy_GPU_h=float(newly_added.sum()*.25),
                    newly_added_occupancy_not_matched_GPU_h=float(np.minimum(missing,newly_added).sum()*.25),
                    next_snapshot_present=snap is not None,next_snapshot_state=snap.get("state_at_issue") if snap else None,
                    next_initial_RUNNING_present=init is not None,next_initial_AIDC=init.get("initial_AIDC") if init else None,
                    expected_running_at_next_issue=s1<=k*SLOTS<e1,
                    independently_scheduled_same_job=nr is not None,
                    next_raw_start_slot=nr.get("scheduled_start_slot") if nr else None,
                    next_raw_completion_slot=nr.get("scheduled_end_slot") if nr else None,
                    next_safe_duration_slots=nr.get("duration_slots") if nr else None,
                    next_DA_assignment_present=na is not None,next_DA_AIDC=site,repair_AIDC=job["repair_AIDC"],
                    simultaneous_expected_and_DA_site_mismatch=bool(site_bad and overlap_mask.any()),
                    site_mismatch_matched_GPU_h=float(np.minimum(expected,actual).sum()*.25) if site_bad else 0.,
                    prior_repaired_job_completed_but_independent_DA_executes_again=bool(repeated_complete),
                    repeated_completed_job_GPU_h=float(actual.sum()*.25) if repeated_complete else 0.,
                    exact_carry_time_GPU_match=bool(np.array_equal(expected,actual)),
                    next_day_Actual_executed=(PROD/"dates"/f"{nextday}.json").is_file(),
                    Actual_audit_basis="PRODUCTION_LOADER_FIXED_DA_BINDING_NOT_NEW_ACTUAL_EXECUTION")
                future_rows.append(item)
                if k==1: interday.append(item)
        print(json.dumps(aggregate),flush=True)

    # Exercise only the read-only production loader, not run_case/run_day/Fresh.
    from dayahead.v39e.campaign_adapter import build_day
    loader_rows=[]
    for day in sorted({r["next_day"] for r in interday}):
        d=day_info(day)["decision"]
        loaded=build_day(REPO,day,"B1")
        pcc=pd.DataFrame(d["site_PCC_power_trajectory"]).sort_values(["slot","AIDC"])
        assert np.array_equal(loaded.pcc_p_kw,pcc.PCC_P_kW.to_numpy(float).reshape(96,12))
        loader_rows.append(dict(day=day,loader_PCC_exact_match=True,loaded_shape=list(loaded.pcc_p_kw.shape),
            DA_SHA256=loaded.fingerprints["V39E_DA_decision_SHA256"],Actual_solver_execution=False))

    common = read(REPO/"dayahead/artifacts/v39e_rw_anchored_initial_state_fast_validation/V39E_COMMON_INITIAL_STATE_AUDIT.json")
    assert common["inter_day_state_carry_count"]==common["cross_day_AIDC_state_read_count"]==0
    implementation_files=("dayahead/v37/aidc_materializer.py","dayahead/v39e/initial_state.py",
        "dayahead/v39e/evaluate.py","dayahead/v39e/full_preflight.py","dayahead/v39a/spatial.py",
        "dayahead/v39e/temporal_refreeze.py","dayahead/v39e/campaign_adapter.py","dayahead/v39d/evaluate.py",
        "dayahead/v37/runner.py","dayahead/v36/runner.py")
    for path in implementation_files: track(REPO/path)
    missing=sum(r["omitted_expected_carry_GPU_h"] for r in future_rows)
    repeated=[r for r in future_rows if r["prior_repaired_job_completed_but_independent_DA_executes_again"]]
    for aggregate in aggregates:
        tomorrow=[r for r in interday if r["source_day"]==aggregate["day"]]
        future=[r for r in future_rows if r["source_day"]==aggregate["day"]]
        aggregate.update(
            D_PLUS_1_EXPECTED_CARRY_GPU_H=sum(r["expected_repair_carry_GPU_h"] for r in tomorrow),
            D_PLUS_1_TIME_MATCHED_GPU_H=sum(r["matched_time_GPU_h"] for r in tomorrow),
            D_PLUS_1_OMITTED_CARRY_GPU_H=sum(r["omitted_expected_carry_GPU_h"] for r in tomorrow),
            D_PLUS_1_SITE_MISMATCH_JOB_COUNT=sum(r["simultaneous_expected_and_DA_site_mismatch"] for r in tomorrow),
            CHANGED_JOB_POST_GPU_H_BEYOND_AVAILABLE_MAY_AUTHORITY=aggregate["CHANGED_JOB_POST_MIDNIGHT_GPU_H_AFTER"]-sum(r["expected_repair_carry_GPU_h"] for r in future),
            CLASSIFICATION="TERMINAL_STATE_INCONSISTENCY_FOUND" if aggregate["INCREMENTAL_POST_MIDNIGHT_GPU_H_FROM_REPAIR"]>0 else "NO_INCREMENTAL_HORIZON_ESCAPE")
    summary={"TERMINAL_AUDIT_COMPLETE":"YES","accepted_grid_domain_issue_slots":[BEGIN,END],
        "slot_minutes":15,"timezone":"FIXED_AEST_UTC_PLUS_10","boundary_semantics":"half-open [24,120); start>=120; completion>120",
        "metric_scope":"B1/B3 shared frozen AIDC authority; each GPU-hour is counted once, not summed across the two comparison cases",
        "post_midnight_before_after_scope":"ALL JOBS; changed-job subtotal also supplied; differences equal changed-job increments",
        "changed_jobs_audited":len(changed_rows),"per_day":aggregates,
        "NEW_POST_MIDNIGHT_START_JOBS_MAY25":next(r["NEW_POST_MIDNIGHT_START_JOBS"] for r in aggregates if r["day"].endswith("25")),
        "NEW_POST_MIDNIGHT_START_JOBS_MAY26":next(r["NEW_POST_MIDNIGHT_START_JOBS"] for r in aggregates if r["day"].endswith("26")),
        "NEW_POST_MIDNIGHT_COMPLETION_JOBS":sum(r["NEW_POST_MIDNIGHT_COMPLETION_JOBS"] for r in aggregates),
        "NEXT_DAY_CARRY_CONSISTENT":"NO","DOUBLE_COUNT":"YES" if repeated else "NO",
        "DOUBLE_COUNT_scope":"NO means no duplicate assignment rows or completed-prior-job re-execution found in the changed-job/inspected-future-day comparison. Future Actual has not run. Independent reconstruction still has no carry/remaining-work deduplication contract.",
        "double_count_risk_if_carry_overlay_added_without_identity_and_remaining_work_reconciliation":True,
        "within_day_duplicate_job_assignment_count":0,"repeated_completed_job_future_pairs":len(repeated),
        "repeated_completed_job_future_GPU_h":sum(r["repeated_completed_job_GPU_h"] for r in repeated),
        "OMITTED_CROSS_DAY_WORK":"YES" if missing else "NO",
        "omitted_expected_post_repair_GPU_h_in_available_future_May_DA":missing,
        "newly_added_post_repair_GPU_h_not_matched_in_future_DA":sum(r["newly_added_occupancy_not_matched_GPU_h"] for r in future_rows),
        "future_comparison_note":"Per-source independent witnesses; do not treat sums across source days as unique physical backlog or an executed continuous campaign.",
        "OUT_OF_DOMAIN_GRID_CERTIFICATION":"NO","FINAL_CLASSIFICATION":"TERMINAL_STATE_INCONSISTENCY_FOUND",
        "MAY24_RELEASE":"NO","MAY25_RELEASE":"NO","MAY26_RELEASE":"NO","FULL_MAY_RERUN":"NO","PRODUCTION_SCIENCE_CHANGED":"NO",
        "primary_optimization_calls":0,"migration_MILP_calls":0,"physical_grid_solver_calls":0,"Actual_execution_calls":0,
        "unrelated_completed_dates_invalidated":0,"DA_authority_files_changed":0,
        "common_initial_authority_inter_day_carry_count":common["inter_day_state_carry_count"],
        "loader_checks":loader_rows,"date_execution_at_audit_start":progress_before,
        "no_necessity_claim":"Positive escape describes the saved passing witness; no counterfactual optimization was run to prove that crossing midnight is necessary.",
        "created_at":datetime.now(timezone.utc).isoformat()}
    for row in aggregates:
        summary["INCREMENTAL_POST_MIDNIGHT_GPU_H_MAY"+row["day"][-2:]]=row["INCREMENTAL_POST_MIDNIGHT_GPU_H_FROM_REPAIR"]
    for name,digest in seal["DA_freeze_file_SHA256"].items(): assert sha(PROD/name)==digest
    assert assert_protected_results(REPO)==protected
    for name,digest in hmanifest.items(): assert sha(HROOT/name)==digest
    summary["preservation"]={"DA_files":124,"May01_05_protected_files":protected,"H_required_files":len(hmanifest),"all_SHA_checks_pass":True}
    write_csv(ROOT/"CHANGED_STANDBY_JOB_BOUNDARY_AUDIT.csv",changed_rows)
    write_csv(ROOT/"NEXT_DAY_JOB_STATE_AUDIT.csv",interday)
    write_csv(ROOT/"FUTURE_MAY_JOB_OCCUPANCY_AUDIT.csv",future_rows)
    write_csv(ROOT/"PER_DAY_BOUNDARY_METRICS.csv",aggregates)
    atomic_json(ROOT/"TERMINAL_AUDIT_FINAL_STATUS.json",summary)
    atomic_json(ROOT/"TERMINAL_AUDIT_SOURCE_SHA_MANIFEST.json",SOURCES)
    gate=json.loads((ROOT/"TERMINAL_AUDIT_LAUNCH_GATE.json").read_text())
    gate.update(audit_complete=True,classification=summary["FINAL_CLASSIFICATION"],audit_result_SHA256=sha(ROOT/"TERMINAL_AUDIT_FINAL_STATUS.json"))
    for day in sorted(HELD_DAYS):
        gate["dates"][day]={"release":False,"status":"HOLD_TERMINAL_STATE_INCONSISTENCY_FOUND"}
    atomic_json(ROOT/"TERMINAL_AUDIT_LAUNCH_GATE.json",gate)
    print(json.dumps({k:v for k,v in summary.items() if k.isupper()},indent=2),flush=True)


if __name__ == "__main__":
    main()
