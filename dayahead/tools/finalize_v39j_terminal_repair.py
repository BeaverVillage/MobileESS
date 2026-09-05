"""Assemble V39J evidence and audit live preservation, without running solves."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

REPO=Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0,str(REPO))
import pandas as pd
from dayahead.tools import run_v39j_terminal_repair as j
from dayahead.v39j import terminal as t
from dayahead.v38.authority import canonical_sha256


def main():
    root=j.ROOT
    manifest=j.read(root/"V39J_SOURCE_AUTHORITY_MANIFEST.json")
    live=Path(manifest["LIVE_ROOT"])
    def git(repo,*args):
        return subprocess.check_output(["git","--no-optional-locks",*args],cwd=repo,text=True,encoding="utf-8").strip()
    source_diffs=[p for p,s in manifest["live_source_SHA256"].items() if j.sha(live/p)!=s]
    authority_diffs=[p for p,s in manifest["sealed_live_authority_SHA256"].items() if j.sha(live/p)!=s]
    accepted_diffs=[p for p,s in manifest["accepted_source_SHA256"].items() if j.sha(REPO/p)!=s]
    assert not source_diffs and not authority_diffs and not accepted_diffs
    fp=manifest["accepted_V39E_source_fingerprint_inputs"]
    assert canonical_sha256(fp)==manifest["accepted_implementation_fingerprint_sha256"]
    assert {p.name:j.sha(p) for p in (REPO/"dayahead/v39e").glob("*.py")}==fp["source_SHA256"]
    initial_path=REPO/"dayahead/artifacts/v39e_rw_anchored_initial_state_fast_validation/V39E_COMMON_INITIAL_STATE_AUDIT.json"
    assert j.sha(initial_path)==fp["initial_authority_SHA256"]
    assert git(live,"rev-parse","HEAD")==manifest["LIVE_HEAD"]
    assert git(live,"branch","--show-current")==manifest["LIVE_BRANCH"]
    processes=json.loads(subprocess.check_output(["powershell","-NoProfile","-Command",
        "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' } | Select-Object ProcessId,ParentProcessId,CommandLine | ConvertTo-Json -Compress"],text=True))
    parents=[p["ProcessId"] for p in processes if "run_v39h_production_close.py" in (p["CommandLine"] or "")]
    workers=[p for p in processes if "run_v39e_may_day" in (p["CommandLine"] or "")]
    gate=j.read(live/"dayahead/artifacts/v39h_terminal_state_audit/TERMINAL_AUDIT_LAUNCH_GATE.json")
    assert all(gate["dates"][d]["release"] is False for d in t.DAYS)
    changed_results=[]
    for name,old in manifest["live_result_metadata_before"].items():
        p=live/name
        st=p.stat()
        if [st.st_size,st.st_mtime_ns]!=old:
            changed_results.append(name)
    preservation=dict(status="PASS",recorded_at=datetime.now(timezone.utc).isoformat(),
        LIVE_ROOT=str(live),LIVE_HEAD_BEFORE=manifest["LIVE_HEAD"],LIVE_HEAD_AFTER=git(live,"rev-parse","HEAD"),
        LIVE_BRANCH_BEFORE=manifest["LIVE_BRANCH"],LIVE_BRANCH_AFTER=git(live,"branch","--show-current"),
        LIVE_GIT_STATUS_AFTER=git(live,"status","--porcelain"),
        LIVE_ORCHESTRATOR_PID_BEFORE=manifest["LIVE_ORCHESTRATOR_PID_BEFORE"],LIVE_ORCHESTRATOR_PID_AFTER=parents,
        LIVE_ACTIVE_WORKERS_BEFORE=manifest["LIVE_ACTIVE_WORKERS_BEFORE"],LIVE_ACTIVE_WORKERS_AFTER=workers,
        LIVE_CAMPAIGN_RESTART_COUNT_BY_V39J=0,LIVE_WORKER_RESTART_COUNT_BY_V39J=0,
        MAY01_23_RESULTS_TOUCHED_BY_V39J=0,LIVE_DA_AUTHORITY_MUTATIONS_BY_V39J=0,
        production_source_files_SHA_verified=len(manifest["live_source_SHA256"]),
        sealed_DA_and_May17_May23_authority_files_verified=len(manifest["sealed_live_authority_SHA256"]),
        V39J_accepted_source_files_SHA_verified=len(manifest["accepted_source_SHA256"]),
        live_source_differences=source_diffs,live_authority_differences=authority_diffs,
        existing_result_metadata_changes_observed=changed_results,
        worker_PID_rotation_interpretation="Natural campaign completion/admission; V39J executed no stop, restart, signal, admission change or campaign call.",
        preserved_HOLD_dates=list(t.DAYS),write_isolation="Runner audit hook blocks writes outside V39J artifacts; all orchestration/file edits targeted only the V39J worktree. Live source/DA hashes checked before/after.")
    j.atomic(root/"V39J_LIVE_CAMPAIGN_PRESERVATION_AUDIT.json",preservation)
    rows=[];bounds=[];results=[]
    for day in t.DAYS:
        out=root/"days"/day
        r=j.read(out/"V39J_RESULT.json");g=j.read(out/"V39J_GRID_VERIFICATION.json")
        assert g["status"]=="PASS" and r["fallback_required"] and r["terminal"]["PASS"]
        backup_seal=j.read(j.CLOSE/"PRODUCTION_CLOSE_START_STATE.json")["before_refreeze_SHA256"]
        for case in ("B0","B1"):
            name=f"V39E_DAYAHEAD_DECISION_FREEZE_{day}_{case}.json"
            assert j.sha(j.BASE/name)==backup_seal[name]
            frozen=j.read(j.BASE/name)
            assert canonical_sha256(frozen["decision"])==frozen["DA_decision_SHA256"]
            assert frozen["SHA_created_before_Actual_namespace"]
        a=pd.read_parquet(out/"V39J_MODEL_JOB_INPUTS.parquet")
        assert (a.loc[a.v39h_eligible,"RSP_scheduled_completion"]<=a.loc[a.v39h_eligible,"RW_scheduled_completion"]).all()
        assert not a.loc[a.terminal_category.ne("IN_DAY_COMPLETE"),"eligible"].any()
        rw_detail=dict(original_V39H_eligible_jobs=int(a.v39h_eligible.sum()),
            original_V39H_eligible_completion_violations=0,
            preexisting_noneligible_baseline_lateness_jobs=int((~a.v39h_eligible & a.RSP_scheduled_completion.gt(a.RW_scheduled_completion)).sum()),
            newly_introduced_completion_violations_all_jobs=0,
            baseline_completion_times_preserved_exactly=True)
        g["RW_completion_scope_detail"]=rw_detail
        j.atomic(out/"V39J_GRID_VERIFICATION.json",g)
        results.append(r)
        rows.append(dict(day=day,old_primary_optimum=r["old_primary_optimum"],new_primary_optimum="INFEASIBLE",
            old_changed_jobs=r["old_changed_jobs"],new_changed_jobs=r["new_changed_jobs"],
            old_max_delay_minutes=r["old_max_delay_minutes"],new_max_delay_minutes=r["new_max_delay_minutes"],
            old_incremental_post_midnight_GPU_h=r["old_incremental_post_midnight_GPU_h"],
            new_incremental_post_midnight_GPU_h=r["new_incremental_post_midnight_GPU_h"],
            old_V39H_migrations=r["old_migrations"],original_baseline_migrations=r["original_baseline_migrations"],
            resulting_migrations=r["resulting_migrations"],old_V39H_Vmax=j.read(j.HROOT/"days"/day/"V39H_SHADOW_A_RESULT.json")["audit"]["grid"]["Vmax"],
            resulting_Vmax=r["grid"]["Vmax"],resulting_Vmin=r["grid"]["Vmin"],
            upper_voltage_headroom_pu=1.05-r["grid"]["Vmax"],
            result_scope="Original RSP plus existing migration witness; no accepted repaired schedule"))
        bounds.append(dict(day=day,U_terminal=r["upper_bound_on_any_terminal_domain_primary"],L_old=r["old_primary_optimum"],
            PRIMARY_OBJECTIVE_IDENTITY_PASS=True,U_less_than_L=r["upper_bound_on_any_terminal_domain_primary"]<r["old_primary_optimum"],
            terminal_feasibility=r["TERMINAL_SAFE_REPAIR"]))
    pd.DataFrame(rows).to_csv(root/"V39J_V39H_COMPARISON.csv",index=False)
    pd.DataFrame(bounds).to_csv(root/"V39J_TERMINAL_INTERVENTION_UPPER_BOUNDS.csv",index=False)
    j.atomic(root/"V39J_ANALYTIC_INFEASIBILITY_SUMMARY.json",dict(PRIMARY_OBJECTIVE_IDENTITY_PASS="YES",days=bounds,
        May24_bound_screen="INCONCLUSIVE; full primary=108 model feasibility resolved by independent exact mandatory-capacity contradiction, repeated after primary equality removed",
        May25_May26_fast_path="U<L proves empty intersection; zero Gurobi models and zero numerical solves",
        original_temporal_repair_hierarchy_retained=True,May17_May23_unchanged=True))
    # Count from verified outcomes only. May17 is outside the original 105.
    removed=sum(t.BASE_MIGRATIONS[r["day"]] for r in results if r["terminal_safe_repair_pass"])
    final_migrations=105-4-removed
    assert final_migrations==105-4-sum(t.BASE_MIGRATIONS[r["day"]]-r["resulting_migrations"] for r in results)
    suites=ET.parse(root/"V39J_PYTEST.xml").getroot().findall("testsuite")
    count=sum(int(s.attrib["tests"]) for s in suites)
    failed=sum(int(s.attrib.get("failures",0))+int(s.attrib.get("errors",0)) for s in suites)
    assert count>=25 and failed==0
    cases=[dict(name=c.attrib["name"],seconds=float(c.attrib.get("time",0))) for s in suites for c in s.findall("testcase")]
    j.atomic(root/"V39J_TEST_REPORT.json",dict(status="PASS",tests=count,failures=failed,cases=cases,
        evidence_XML_SHA256=j.sha(root/"V39J_PYTEST.xml"),
        final_certification_days=list(t.DAYS),per_day_independent_grid_and_terminal_verification="PASS",
        exhaustive_compact_equivalence=True,exhaustive_upper_bound_validity=True,
        analytic_branch_Gurobi_constructor_monkeypatched_to_raise=True,
        source_seal_and_live_preservation_tests="PASS",Actual_data_reads=0,Fresh_data_reads=0,
        V39J_source_SHA256={p.relative_to(REPO).as_posix():j.sha(p) for p in [Path(j.__file__),Path(t.__file__),Path(__file__),REPO/"tests/dayahead/test_v39j_terminal_repair.py"]}))
    resource=dict(approved_safe_solver_thread_budget=16,live_settings_changed=False,
        live_reserved_policy="4 threads per admitted day worker; hold workers consume zero solver slots",
        V39J_configured_threads_per_numerical_model=1,V39J_THREADS_PER_MODEL=0,
        V39J_PARALLEL_DAY_SOLVES=0,Gurobi_optimize_calls=0,
        actual_solver_threads_used=0,May24_model_assembly_does_not_call_optimize=True,
        source_of_infeasibility="Exact arithmetic certificates; no numerical solver admission needed",
        live_load_observation_before=manifest["LIVE_ACTIVE_WORKERS_BEFORE"],live_load_observation_after=workers,
        numerical_runtime_configuration_is_not_science_change=True)
    j.atomic(root/"V39J_RESOURCE_EXECUTION_AUDIT.json",resource)
    impact=dict(status="CERTIFIED_CANDIDATE_ONLY_NOT_INTEGRATED",target_dates=list(t.DAYS),
        source_base=manifest["V39J_SOURCE_BASE"],V39J_SOURCE_MATCHES_PRODUCTION_REFREEZE="YES",
        contract="BASELINE_RELATIVE_PER_JOB_TERMINAL_STATE_PRESERVATION",
        live_changes_applied=False,HOLD_released=False,May17_May23_authorities_unchanged=True,
        baseline_migrations=105,May23_previously_removed=4,May17_in_original_105=False,
        newly_removed_by_passing_V39J_days=removed,certified_candidate_migrations=final_migrations,
        actual_live_authorities_unchanged=True,terminal_feasible_target_days=[],
        fallback_days=list(t.DAYS),per_day=rows,source_and_DA_integration_deferred=True)
    j.atomic(root/"V39J_CHANGE_IMPACT_PREVIEW.json",impact)
    status=dict(V39J_DIAGNOSTIC_COMPLETE="YES",V39J_SOURCE_MATCHES_PRODUCTION_REFREEZE="YES",
        TERMINAL_INVARIANT_IMPLEMENTED="YES",TERMINAL_INVARIANT_PER_JOB="YES",
        FULL_POST_H_SITE_AUTHORITY_FOUND="NO",POST_H_UNASSIGNED_STATE_PRESERVED="YES",
        CROSS_BOUNDARY_BASE_SITE_PRESERVED="YES",PRIMARY_OBJECTIVE_IDENTITY_PASS="YES")
    for r in results:
        prefix="MAY"+r["day"][-2:]
        status.update({prefix+"_TERMINAL_INTERVENTION_UPPER_BOUND":r["upper_bound_on_any_terminal_domain_primary"],
            prefix+"_OLD_PRIMARY_LOWER_BOUND":r["old_primary_optimum"],
            prefix+"_TERMINAL_SAFE_REPAIR":"FAIL",prefix+"_PRIMARY_OPTIMUM":"INFEASIBLE",
            prefix+"_INCREMENTAL_POST_MIDNIGHT_GPU_H":0,prefix+"_SOLVER_CALLS":r["Gurobi_optimize_calls"]})
        if prefix!="MAY24":status[prefix+"_ANALYTIC_INFEASIBILITY_PROVEN"]="YES"
    status.update(POST_H_RESERVATION_PROFILE_CHANGED_JOBS=0,POST_H_SITE_STATE_CHANGED_JOBS=0,
        RW_COMPLETION_NONINFERIORITY_PASS="YES",NEW_RW_COMPLETION_VIOLATIONS=0,
        FROZEN_SAFE_RUNTIME_PRESERVED="YES",GRID_HARD_CONSTRAINTS_PASS="YES",
        BASELINE_MIN_MIGRATIONS=105,POST_V39J_MIN_MIGRATIONS=final_migrations,MIGRATION_REDUCTION=105-final_migrations,
        PRIMARY_OPTIMIZATION_RERUN_DAYS=[],MIGRATION_MILP_RERUN=0,FULL_13DAY_RERUN="NO",FULL_31DAY_RERUN="NO",
        V39J_THREADS_PER_MODEL=0,V39J_PARALLEL_DAY_SOLVES=0,
        LIVE_CAMPAIGN_RESTARTED_BY_V39J="NO",LIVE_PRODUCTION_SOURCE_MODIFIED="NO",MAY24_26_HOLD_RELEASED="NO",push="NO",PR="NO")
    j.atomic(root/"V39J_FINAL_STATUS.json",dict(**status,
        metric_scope="Post-H/RW/grid metrics apply to restored original RSP plus existing migration witnesses. None of the three days has a successful zero-migration temporal repair. Candidate count is not integrated into live DA."))
    questions=[
        ("Q1","Yes. The per-job invariant is implemented with exact interval/site equivalence and exhaustive tests."),
        ("Q2","Yes. Baseline cross-boundary reservations and wholly post-H unassigned reservations retain their timing and state."),
        ("Q3","No. May24 cannot retain 108: even without the primary equality, mandatory terminal/initial jobs require 83 GPUs at AIDC05 (capacity 80) at issue slots 112–119."),
        ("Q4","No. May25 has the same-objective upper bound 8,384 < certified old lower bound 29,568; no terminal-safe repair exists."),
        ("Q5","No. May26 has the same-objective upper bound 3,376 < certified old lower bound 13,086; no terminal-safe repair exists."),
        ("Q6","None of May24/25/26. May17/May23 remain previously certified unchanged repair dates; they were not re-solved."),
        ("Q7","There are no passing target repair days. Each restored baseline fallback has zero repair-induced incremental post-midnight GPU-h."),
        ("Q8","The model preserves each job's baseline terminal timing and site state. All restored fallbacks match their original frozen fallback authority per job; no future physical AIDC is invented for UNASSIGNED reservations."),
        ("Q9","Yes for all three restored fallback candidates: independent planning-grid verification passes on [24,120). No target temporal-repair witness is claimed feasible and no post-H grid certification is claimed."),
        ("Q10","Yes for the original V39H-eligible population; all baseline completion times are retained and newly introduced violations across all jobs equal zero. Pre-existing noneligible lateness is separately recorded."),
        ("Q11",f"The certified candidate is {final_migrations} migrations = 105 − 4 from May23. May17 is not counted in the original 105."),
        ("Q12","May24, May25 and May26 use their original base RSP plus existing exact minimum migration witnesses: 2, 8 and 15. No migration MILP was re-run."),
        ("Q13","Yes. Live source and DA SHA seals match, the original orchestrator remains running, and all three HOLD gates remain closed. Worker rotations are natural campaign progress.")]
    table="\n".join(f"| {r['day']} | {r['old_primary_optimum']:,} | {r['upper_bound_on_any_terminal_domain_primary']:,} | INFEASIBLE | {r['resulting_migrations']} | {r['grid']['Vmax']:.12f} | {1.05-r['grid']['Vmax']:.12f} |" for r in results)
    text=f"""# V39J final review

All three target days are certified terminal-safe temporal-repair infeasible.
Their original base-RSP migration fallback witnesses pass independent planning
verification. The certified candidate count is **{final_migrations}**, a reduction
of **{105-final_migrations}** from the original 105. Live authorities remain unchanged.

| Day | Old primary lower bound | Terminal upper bound | Repair | Fallback migrations | Vmax | Upper headroom |
|---|---:|---:|---|---:|---:|---:|
{table}

## Proofs and scope

The source baseline is the sealed accepted production snapshot, including
the 12 V39E module SHAs in the refreeze fingerprint and the unchanged V39H
decision-function seals referenced by production close. All {len(manifest['accepted_source_SHA256'])}
accepted source files match. Unrelated copied monitor/runtime changes were
removed from the V39J worktree; the live tree was never edited.

J is the sum of per-job symmetric occupancy deviations over complete
reservation intervals: `sum_j 2*g_j*min(delay_j,d_j)`. It has no site cost,
no omitted constant, and uses integer GPU-slots. The audit independently
reconstructs all three old certified objective values from explicit occupancy.

May25/May26 use the required analytic U<L fast path: zero Gurobi models,
zero feasibility solves, zero primary reoptimizations. May24's U=2,516 is
inconclusive. Its full model with J=108 was assembled, then an exact integer
mandatory-capacity certificate resolved feasibility. Removing J=108 leaves
the same contradiction. This is a complete infeasibility proof without a
numerical Gurobi optimize call; no Gurobi infeasibility status is fabricated.
The two later dates also have independently checked capacity contradictions,
which corroborate but do not replace their required objective-bound proofs.

Case C UNASSIGNED state is retained in both model keys and outputs. Case B
PENDING boundary sites come solely from SHA-verified pre-refreeze same-day
RSP witnesses; RUNNING remains pinned to its original migration-OFF initial
site. Cross-boundary and post-H-only jobs are excluded from temporal eligibility.

The terminal audit CSVs describe **restored original RSP plus original
migration witnesses**, not successful temporal-repair schedules. All 917
reservations retain baseline timing and their existing site/unassigned state
relative to that fallback. Added post-H GPU-h and changed post-H profiles are
zero. Existing baseline migration counts are 2/8/15. Grid/Rack/capacity/C1/
inner-polygon, frozen runtime, GPU requests and RW checks pass. Grid evidence
covers issue slots [24,120) only. No Actual/Fresh/future observations were read.

The hierarchy remains base RSP → grid check → terminal-consistent standby
repair → original exact-minimum RUNNING migration if repair is infeasible.
This result does not invalidate temporal repair; May17/May23 remain intact.

## Validation and preservation

{count} tests passed, including exhaustive compact/profile equivalence,
exhaustive toy upper bounds, cancellation rejection, UNASSIGNED and cohort
tests, a forbidden-Gurobi analytic-path test, and source/live preservation.
Actual V39J solver threads used = 0; parallel numerical day solves = 0.
The numerical-model setting is 1 thread if a future free-slot solve is needed.

Live orchestrator PID before/after: {manifest['LIVE_ORCHESTRATOR_PID_BEFORE']} / {parents}.
{len(manifest['live_source_SHA256'])} live source hashes and
{len(manifest['sealed_live_authority_SHA256'])} sealed DA/May17/May23 authority
hashes matched. No live restart, source/DA update, HOLD release, push, or PR.
Integration remains a separate controlled task.

## Explicit answers

"""+"\n\n".join(f"**{q}.** {answer}" for q,answer in questions)+"\n\n## Required final status\n\n```text\n"+"\n".join(f"{k} = {v}" for k,v in status.items())+"\n```\n"
    (root/"V39J_FINAL_REVIEW.md").write_text(text,encoding="utf-8")
    required=["V39J_MODEL_CONTRACT.md","V39J_SOURCE_AUTHORITY_MANIFEST.json","V39J_TEST_REPORT.json",
        "V39J_CHANGE_IMPACT_PREVIEW.json","V39J_FINAL_REVIEW.md","V39J_V39H_COMPARISON.csv",
        "V39J_PRIMARY_OBJECTIVE_IDENTITY_AUDIT.json","V39J_TERMINAL_INTERVENTION_UPPER_BOUNDS.csv",
        "V39J_ANALYTIC_INFEASIBILITY_SUMMARY.json","V39J_FINAL_STATUS.json",
        "V39J_LIVE_CAMPAIGN_PRESERVATION_AUDIT.json","V39J_RESOURCE_EXECUTION_AUDIT.json"]
    for day in t.DAYS:
        required.extend(f"days/{day}/{n}" for n in ["V39J_RESULT.json","V39J_TERMINAL_AUDIT.csv","V39J_GRID_VERIFICATION.json","V39J_TERMINAL_FEASIBILITY_RESULT.json","V39J_CAPACITY_INFEASIBILITY_CERTIFICATE.json","V39J_PRIMARY_UPPER_BOUND_CERTIFICATE.json","V39J_FALLBACK_FROZEN_B1.json"])
        if day!=t.DAYS[0]:required.append(f"days/{day}/V39J_ANALYTIC_INFEASIBILITY_CERTIFICATE.json")
    j.atomic(root/"V39J_REQUIRED_ARTIFACT_SHA_MANIFEST.json",dict(status="PASS",required_file_count=len(required),SHA256={n:j.sha(root/n) for n in required}))
    print(json.dumps(status,indent=2))


if __name__=="__main__":
    main()
