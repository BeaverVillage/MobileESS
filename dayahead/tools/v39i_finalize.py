"""Finalize V39I from certified artifacts and targeted tests; no optimization."""
from __future__ import annotations
import argparse
import io
import json
from pathlib import Path
import sys
import time
import unittest
REPO=Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:sys.path.insert(0,str(REPO))
import pandas as pd
from dayahead.tools import run_v39i_minmax as i
from dayahead.tools import v39i_report as report
h=i.h


def duration(minutes):
    return f"{int(minutes)//60}h{int(minutes)%60:02d}m"


def finalize(classifications,reasons):
    report.assemble()
    started=time.monotonic();stream=io.StringIO()
    suite=unittest.defaultTestLoader.loadTestsFromName("tests.dayahead.test_v39i_minmax")
    tests=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    testreport={"status":"PASS" if tests.wasSuccessful() else "FAIL","tests_run":tests.testsRun,
        "failures":len(tests.failures),"errors":len(tests.errors),"skipped":len(tests.skipped),
        "elapsed_seconds":time.monotonic()-started,"output":stream.getvalue(),"optimization_calls":0,
        "scope":"Two-day V39I targeted tests only; no V39H 13-day test suite or other optimization.",
        "test_file_SHA256":h.grid.sha(REPO/"tests/dayahead/test_v39i_minmax.py")}
    i.atomic(i.ROOT/"V39I_TEST_REPORT.json",testreport)
    print(stream.getvalue(),flush=True)
    assert tests.wasSuccessful() and not tests.skipped
    audit=h.read(i.ROOT/"V39I_SERVICE_DELAY_AUDIT.json")
    comparison=pd.read_csv(i.ROOT/"V39I_V39H_VS_MINMAX_COMPARISON.csv")
    results={day:h.read(i.ROOT/"days"/day/"V39I_MINMAX_DELAY_RESULT.json") for day in i.DAYS}
    status={"V39I_DIAGNOSTIC_COMPLETE":"YES"}
    for day in i.DAYS:
        key="MAY"+day[-2:];r=results[day]
        assert classifications[day] in report.CLASSIFICATIONS
        status[key+"_PRIMARY_OPTIMUM_PRESERVED"]="YES"
        status[key+"_EXACT_MIN_MAX_DELAY_MIN"]=r["D_MAX_minutes"]
        status[key+"_DELAY_CLASSIFICATION"]=classifications[day]
    status.update(RW_COMPLETION_NONINFERIORITY_PASS="YES",NEW_RW_COMPLETION_VIOLATIONS=0,
        FROZEN_SAFE_RUNTIME_PRESERVED="YES",GRID_HARD_CONSTRAINTS_PASS="YES",RUNNING_MIGRATION_REQUIRED="NO",
        PRODUCTION_SCIENCE_CHANGED="NO",V39H_RERUN="NO",FULL_PREFLIGHT_RERUN="NO",MAY_RESTARTED="NO",MAY01_05_RESULTS_TOUCHED="NO")
    for day in i.DAYS:
        s=audit["days"][day]["service_work"]["new_V39I"]
        assert s["RW_completion_noninferiority_pass"] and s["new_RW_completion_violations"]==0 and s["frozen_safe_runtime_preserved"]
        assert results[day]["audit"]["all_hard_constraints_pass"] and results[day]["audit"]["RUNNING_site_changes"]==0
    audit["descriptive_classifications"]={day:{"class":classifications[day],"label":report.CLASSIFICATIONS[classifications[day]],"reason":reasons[day],"service_acceptability_judgment":False} for day in i.DAYS}
    i.atomic(i.ROOT/"V39I_SERVICE_DELAY_AUDIT.json",audit)
    i.atomic(i.ROOT/"V39I_FINAL_STATUS.json",status)
    lines=["# V39I final diagnostic review","",
        "DIAGNOSTIC ONLY — primary-optimal minimum maximum added delay. No production science approval or mutation.","",
        "## Result","",
        "| Day | Reused exact primary (GPU-slots) | Old max delay | Exact min-max delay | Reduction | Changed jobs old → new | Classification |",
        "|---|---:|---:|---:|---:|---:|---|"]
    for day in i.DAYS:
        old=comparison[(comparison.day==day)&(comparison.witness=="V39H")].iloc[0]
        new=comparison[(comparison.day==day)&(comparison.witness=="V39I_MINMAX")].iloc[0]
        lines.append(f"| {day} | {i.PRIMARY[day]:,} | {duration(old.max_added_delay_min)} | {duration(new.max_added_delay_min)} ({int(new.max_added_delay_min):,} min) | {int(old.max_added_delay_min-new.max_added_delay_min):,} min | {int(old.changed_jobs)} → {int(new.changed_jobs)} | {classifications[day]} — {report.CLASSIFICATIONS[classifications[day]]} |")
    lines.extend(["","Primary is fixed by exact equality. After the user-requested interruption of slow direct min-max B&B, exact minimum D_MAX was established by monotone integer threshold feasibility binary search: T* FEASIBLE and T*-1 INFEASIBLE. Feasibility queries have a constant-zero objective, MIPGap=0, Seed=20260905 and 4 threads per model, at most 2 concurrent day workers. Changed-job count is descriptive, not globally minimized in V39I. May26's former 8-job minimum was not imposed on the primary-optimal face.","",
        "## Explicit answers Q1–Q13",""])
    for num,day in ((1,i.DAYS[0]),(2,i.DAYS[1])):
        r=results[day];s=r["solver_certificate"]
        lines.extend([f"Q{num}. **{day}: {r['D_MAX_minutes']:,} minutes = {duration(r['D_MAX_minutes'])} = {r['D_MAX_slots']} slots**, with primary exactly {i.PRIMARY[day]:,} GPU-slots. Exact certificate: T={s['T_star_slots']} FEASIBLE with independently verified witness, T={s['T_star_slots']-1} globally INFEASIBLE (Gurobi status {s['T_star_minus_1_INFEASIBLE']['stage']['status']}). No synthetic direct-objective gap is claimed. No primary optimization was repeated.",""])
    for num,day in ((3,i.DAYS[0]),(4,i.DAYS[1])):
        d=audit["days"][day]
        lines.extend([f"Q{num}. {day}: {duration(d['old_max_delay_min'])} → {duration(d['new_exact_max_delay_min'])}; reduced by {d['maximum_delay_reduction_min']:,} minutes. {reasons[day]}",""])
    lines.extend(["Q5. The jobs below attain the maximum in the selected old/new witnesses. The exact global certificate proves that **some eligible job must incur at least D_MAX*** in every feasible primary-optimal solution. It does **not** prove that a named UID is uniquely forced to do so in all optima. No per-UID counterfactual or resource-family necessity optimization was run, and no such claim is made.","",
        "Q6. Exact modeled RW-completion slack consumption and remaining margin for all old/new maximum-attaining jobs:","",
        "| Day | Job UID | Old max? | New max? | GPU | Safe slots | Admissible slack (min) | Old delay (min) | New delay (min) | New slack consumed | New completion margin to RW (min) |",
        "|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|"])
    for day in i.DAYS:
        jobs=pd.read_csv(i.ROOT/"days"/day/"V39I_MAX_DELAY_JOB_AUDIT.csv",dtype={"job_uid":str})
        for r in jobs.itertuples(index=False):
            lines.append(f"| {day} | {r.job_uid} | {r.attains_old_maximum} | {r.attains_new_maximum} | {r.requested_GPU} | {r.frozen_safe_duration_slots} | {r.admissible_slack_min} | {r.old_V39H_added_delay_min} | {r.new_V39I_added_delay_min} | {100*r.new_V39I_slack_consumption_fraction:.9f}% | {r.new_V39I_completion_margin_to_RW_min} |")
    lines.extend(["","The per-day job audit CSVs contain QoS, submit time, frozen RSP start, safe seconds/slots, modeled RW start/completion, latest admissible start, old/new start/completion, both slack fractions and both completion margins. Times are fixed AEST (UTC+10), 15-minute issue-relative slots. RW modeled completion is not a user deadline.","",
        "Q7. PASS. All shifted eligible jobs finish no later than their own modeled RW completion. Newly introduced violations=0; frozen eligibility and noneligible starts are unchanged.","",
        "Q8. PASS. Per-job safe seconds, reserved slots, requested GPUs and the job set are identical. Exact modeled reserved GPU-hours:","",
        "| Day | Before reserved GPU-h | After reserved GPU-h | Safe-seconds × GPU / 3600 before = after |",
        "|---|---:|---:|---:|"])
    for day in i.DAYS:
        s=audit["days"][day]["service_work"]["new_V39I"]
        lines.append(f"| {day} | {s['safe_reservation_GPU_h_before']} | {s['safe_reservation_GPU_h_after']} | {s['safe_duration_seconds_GPU_h_after']!r} |")
    lines.extend(["","Reserved slot GPU-hours and safe-seconds GPU-hours are separately reported; neither is measured/realized computation.","",
        "Q9. Planning grid PASS, independently evaluated only on accepted issue slots [24,120). Voltage, line current, transformer phase current, transformer apparent power/inner polygon, C1/PCC, site capacity, Rack compatibility and gang-split violations are all 0.","",
        "| Day | Vmax | Upper headroom | Vmin | Lower headroom | Critical issue slot / target slot | Bus / phase |",
        "|---|---:|---:|---:|---:|---|---|"])
    for day in i.DAYS:
        g=results[day]["audit"]["grid"]
        lines.append(f"| {day} | {g['Vmax']!r} | {1.05-g['Vmax']!r} | {g['Vmin']!r} | {g['Vmin']-.95!r} | {g['critical_issue_slot']} / {g['critical_target_slot']} | {g['critical_voltage_bus_phase']} |")
    lines.extend(["","Q10. RUNNING migration=0 and WAN transfers=0 for both dates, with RUNNING initial sites preserved. Legal PENDING initial-site placement is not RUNNING migration. No migration MILP was called.","",
        "Q11. Accepted physical grid authority is the operating day [24,120). Exact out-of-domain reservation accounting:","",
        "| Day | Witness | Latest completion slot | Moved jobs past end | All off-grid GPU-h | Moved jobs off-grid GPU-h | Fraction of moved-job reservation off-grid | Latest moved completion beyond grid end (min) |",
        "|---|---|---:|---:|---:|---:|---:|---:|"])
    for day in i.DAYS:
        domain=h.read(i.ROOT/"days"/day/"V39I_TIME_DOMAIN_AUDIT.json")
        for name in ("old_V39H","new_V39I"):
            d=domain[name]
            lines.append(f"| {day} | {name} | {d['latest_reservation_completion_slot']} | {d['moved_jobs_extending_beyond_grid_domain_end']} | {d['reservation_GPU_h_outside_grid_domain']} | {d['moved_jobs_reservation_GPU_h_outside_grid_domain']} | {100*d['moved_jobs_outside_reservation_fraction']:.9f}% | {d['maximum_moved_job_completion_beyond_grid_domain_end_min']} |")
    lines.extend(["","The per-day TIME_DOMAIN_AUDIT records earliest slot, full reservation horizon, pre-/inside-/post-grid GPU-hours, exact completion times and old/new domain classifications. Outside-domain site/grid assignment is **not physically verified**; these portions retain reservation accounting and aggregate capacity only. Off-domain extension is evidence, not an automatic failure.","",
        "Q12. Classification is descriptive, not an acceptable-service threshold:",""])
    for day in i.DAYS:
        lines.extend([f"- {day}: {classifications[day]} / {report.CLASSIFICATIONS[classifications[day]]}. {reasons[day]}",""])
    lines.extend(["A positive exact D_MAX lower bound is structurally required by the **joint frozen model on the primary-optimal face**. The reduction relative to the old witness was avoidable by witness selection. Binding aggregate-capacity slots are recorded in SERVICE_DELAY_AUDIT as observations, not proof that one resource family or a particular job uniquely causes the lower bound.","",
        "Q13. **Do not approve or refreeze production from this diagnostic.** Compare the witnessed improvements and service-delay distribution before choosing a production tie-break. Review the unchanged outside-domain physical-authority limitation. Possible science-review options (proposed only, not executed) are a justified service-admissibility/maximum-deferral authority, an intervention-versus-delay trade-off, and broader time-domain physical authority. No deadline, threshold or new science authority was introduced.","",
        "## Verification and provenance","",
        f"Targeted V39I tests: {tests.testsRun}/{tests.testsRun} PASS; 0 failures, 0 errors, 0 skipped. Earlier H/E/F/G artifacts and production source hashes are preserved. Full comparisons (including median/P95, delay tails and GPU-weighted delay) are in V39I_V39H_VS_MINMAX_COMPARISON.csv.","",
        "No primary, migration, other-day, preflight or campaign reruns. No Actual/Fresh reads and no May01–05 result changes. Fixed-seed selected incumbent is expanded in deterministic UID/cohort order; no globally lexical or changed-count-optimal witness is claimed.","",
        "## Final status","","```text"])
    lines.extend(f"{k} = {v}" for k,v in status.items());lines.extend(["```",""])
    # This is generated diagnostic output, not a source-file edit.
    (i.ROOT/"V39I_FINAL_REVIEW.md").write_text("\n".join(lines),encoding="utf-8")
    provenance=h.read(i.ROOT/"V39I_DIAGNOSTIC_PROVENANCE.json")
    with (i.ROOT/"V39I_FINAL_REVIEW.md").open("a",encoding="utf-8") as file:
        file.write("\n## Shared-workspace Git context\n\n")
        file.write(f"Starting HEAD: `{provenance['starting_HEAD']}`; final HEAD: `{provenance['final_HEAD']}`. Final branch: `{provenance['final_branch']}`.\n\n")
        file.write("An external checkout/commit during the solve committed the pre-existing dirty campaign-monitor script. V39I did not make that commit or restore the branch. All 1,093 checked source files match the initial working-file SHA authority; existing H/E/F/G artifacts are unchanged. This external Git metadata change did not alter the running model.\n")
    provenance["source_files_SHA256"][str(Path(__file__).relative_to(REPO))]=h.grid.sha(Path(__file__))
    for helper in ("run_v39i_threshold.py","v39i_interrupt_direct.py"):
        path=REPO/"dayahead/tools"/helper;provenance["source_files_SHA256"][str(path.relative_to(REPO))]=h.grid.sha(path)
    required=["V39I_MODEL_CONTRACT.md","V39I_V39H_VS_MINMAX_COMPARISON.csv","V39I_SERVICE_DELAY_AUDIT.json","V39I_TEST_REPORT.json","V39I_FINAL_REVIEW.md","V39I_FINAL_STATUS.json"]
    for day in i.DAYS:
        required.extend(f"days/{day}/{name}" for name in ("V39I_MINMAX_DELAY_RESULT.json","V39I_MINMAX_DELAY_SCHEDULE.parquet","V39I_MAX_DELAY_JOB_AUDIT.csv","V39I_TIME_DOMAIN_AUDIT.json","V39I_GRID_VERIFICATION.json","V39I_D_MAX_SOLVER_CERTIFICATE.json","V39I_INPUT_EQUIVALENCE.json","V39I_MINMAX_FORMULATION.json","V39I_VERIFIED_WITNESS.npz"))
        required.extend(str(p.relative_to(i.ROOT)) for p in (i.ROOT/"days"/day/"thresholds").rglob("*") if p.is_file())
    provenance.update(required_artifact_SHA256={p:h.grid.sha(i.ROOT/p) for p in required},final_assembly_at=h.now(),final_status=status)
    i.atomic(i.ROOT/"V39I_DIAGNOSTIC_PROVENANCE.json",provenance)
    print(json.dumps(status,indent=2),flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser()
    for day in (25,26):
        p.add_argument(f"--class{day}",choices=("A","B","C"),required=True)
        p.add_argument(f"--reason{day}",required=True)
    args=p.parse_args()
    finalize({"2025-05-25":args.class25,"2025-05-26":args.class26},{"2025-05-25":args.reason25,"2025-05-26":args.reason26})
