"""Final requested-field assembly. No optimization or grid recomputation."""
from pathlib import Path
import sys
REPO=Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:sys.path.insert(0,str(REPO))
import pandas as pd
from dayahead.tools import run_v39h_shadow as h
from dayahead.tools import v39h_shadow_report as report

def record_resume():
    path=h.ROOT/"V39H_11_OF_13_RESUME_EVIDENCE.json"
    if path.exists():return h.read(path)
    completed={}
    for day in h.DAYS:
        if day in ("2025-05-25","2025-05-26"):continue
        out=h.ROOT/"days"/day
        names=["V39H_SHADOW_A_RESULT.json","V39H_SHADOW_SCHEDULE.parquet","V39H_CHANGED_JOBS.csv","V39H_GRID_MARGIN_AUDIT.json","V39H_WORK_PRESERVATION_AUDIT.json","V39H_ASSEMBLY_EQUIVALENCE.json"]
        names += ["V39H_EXACT_LEX_CERTIFICATES.json","V39H_OBJECTIVE_CERTIFICATES.json"] if h.read(out/names[0])["temporal_repair_sufficient"] else ["V39H_SHADOW_A_IIS.ilp","V39H_SHADOW_A_IIS_SUMMARY.json","V39H_EXISTING_MIGRATION_CONFIRMATION.json","V39H_MIGRATION_SHA_MODEL_AUTHORITY_EQUIVALENCE.json"]
        completed[day]={name:h.grid.sha(out/name) for name in names}
    stages={d:h.read(h.ROOT/"days"/d/"V39H_OBJECTIVE_CERTIFICATES.json")["stages"] for d in ("2025-05-25","2025-05-26")}
    assert stages["2025-05-25"][1]["objective"]==stages["2025-05-25"][1]["bound"]==29568
    assert stages["2025-05-26"][1]["objective"]==stages["2025-05-26"][1]["bound"]==13086
    evidence={"recorded_at":h.now(),"completed_day_SHA256":completed,"already_certified_stages":stages,
        "attached_existing_workers":{"2025-05-25":7200,"2025-05-26":44608},
        "primary_optimization_restarts":0,"migration_MILP_restarts":0,"production_refreeze":False,"campaign_restart":False}
    h.atomic(path,evidence);return evidence

def closeout():
    resume=h.read(h.ROOT/"V39H_11_OF_13_RESUME_EVIDENCE.json")
    flags=h.read(h.ROOT/"V39H_FINAL_STATUS.json")
    flags.pop("labels",None)
    assert flags["V39H_DIAGNOSTIC_COMPLETE"]=="YES" and flags["AFFECTED_DAYS_EVALUATED"]=="13/13"
    assert h.read(h.ROOT/"V39H_TEST_REPORT.json")["status"]=="PASS"
    for day,files in resume["completed_day_SHA256"].items():
        for name,sha in files.items():assert h.grid.sha(h.ROOT/"days"/day/name)==sha,(day,name)
    for day,prefix in resume["already_certified_stages"].items():
        final=h.read(h.ROOT/"days"/day/"V39H_OBJECTIVE_CERTIFICATES.json")["stages"]
        assert final[:len(prefix)]==prefix,day
    delay=h.read(h.ROOT/"V39H_DELAY_REALISM_AUDIT.json")
    flags["NEWLY_INTRODUCED_RW_COMPLETION_VIOLATIONS"]=delay["RW_completion_noninferiority_violations_moved_jobs"]
    assert flags["NEWLY_INTRODUCED_RW_COMPLETION_VIOLATIONS"]==0
    h.atomic(h.ROOT/"V39H_FINAL_STATUS.json",flags)
    rows=[]
    for day in h.DAYS:
        out=h.ROOT/"days"/day;r=report.claim_status(h.read(out/"V39H_SHADOW_A_RESULT.json"));success=r["temporal_repair_sufficient"]
        if success:vmax=r["Vmax"];basis="TEMPORAL_SHADOW_INDEPENDENT_VERIFIER"
        else:
            vmax=h.read(out/"V39H_EXISTING_MIGRATION_CONFIRMATION.json")["planning_feasibility"]["Vmax_pu"]
            basis="REUSED_FROZEN_MINIMUM_MIGRATION_WITNESS"
        ds=delay["per_day"][day]["delay"]
        rows.append({"day":day,"base_RSP_status":r["base_RSP_status"],"temporal_repair":"PASS" if success else "FAIL_INFEASIBLE","changed_jobs":r["changed_jobs"],
            "primary_optimum_GPU_slots":r["PRIMARY_TEMPORAL_INTERVENTION_OPTIMUM"],"primary_optimality_status":r["PRIMARY_TEMPORAL_INTERVENTION_OPTIMAL"],
            "secondary_optimality_status":r["SECONDARY_CHANGED_JOB_OPTIMALITY"],"tertiary_optimality_status":r["TERTIARY_DELAY_OPTIMALITY"],"existing_migration_count":r["existing_migration_count"],"post_candidate_migration_count":r["post_candidate_migration_count"],
            "added_delay_total_min":r["sum_start_delay_minutes"],"added_delay_median_min":ds["median"],"added_delay_P95_min":ds["P95"],"added_delay_max_min":r["max_added_delay_min"],
            "complete_occupancy_deviation_GPU_slots":r["symmetric_occupancy_deviation_GPU_slots"],"GPU_weighted_delay_slots":r["GPU_weighted_start_delay_slots"],
            "Vmax":vmax,"upper_voltage_headroom_pu":1.05-vmax,"grid_margin_basis":basis,
            "reused_minimum_migration_count":r["post_candidate_migration_count"],"newly_introduced_RW_completion_violations":r["RW_completion_noninferiority_violations"]})
    pd.DataFrame(rows).to_csv(h.ROOT/"V39H_PER_DAY_FINAL_RESULTS.csv",index=False,encoding="utf-8-sig")
    table="| Date | Temporal repair | Changed jobs | Added delay total / max (min) | Vmax (pu) | Upper headroom (pu) | Reused minimum migrations |\n|---|---|---:|---:|---:|---:|---:|\n"
    for r in rows:
        table+=f"| {r['day']} | {r['temporal_repair']} | {r['changed_jobs']} | {r['added_delay_total_min']} / {r['added_delay_max_min']} | {r['Vmax']:.12f} | {r['upper_voltage_headroom_pu']:.12g} | {r['reused_minimum_migration_count']} |\n"
    review_path=h.ROOT/"V39H_FINAL_REVIEW.md";review=review_path.read_text(encoding="utf-8")
    marker="\n## Requested 13/13 resume closeout\n"
    if marker in review:review=review.split(marker)[0]
    review+=marker+"\nAll 11 previously completed days are byte-identical to the resume SHA manifest. Already certified May25/26 objective-stage rows are unchanged prefixes of the final certificates. No primary or migration optimization was restarted.\n\n"+table
    review+="\nPASS rows show the independently verified temporal shadow. FAIL rows show the retained, SHA/model/authority-equivalent minimum-migration witness; they do not claim a feasible temporal shadow. The final MIN_UPPER_VOLTAGE_HEADROOM_PU statistic concerns successful temporal-repair days only. Added delays concern newly moved standby jobs; unchanged fallback days have zero added temporal delay.\n\n```text\n"+"\n".join(f"{k} = {v}" for k,v in flags.items())+"\n```\n"
    review_path.write_text(review,encoding="utf-8")
    reuse={"status":"PASS","completed_days_reused_byte_identically":11,"certified_primary_stages_reused":2,
        "May26_changed_job_minimum_certificate_reused":True,"primary_optimization_restarts":0,"migration_MILP_restarts":0,
        "newly_introduced_RW_completion_violations":0,"source_resume_evidence_SHA256":h.grid.sha(h.ROOT/"V39H_11_OF_13_RESUME_EVIDENCE.json"),"finished_at":h.now()}
    h.atomic(h.ROOT/"V39H_RESUME_COMPLETION_AUDIT.json",reuse)
    provenance_path=h.ROOT/"V39H_DIAGNOSTIC_PROVENANCE.json";provenance=h.read(provenance_path)
    provenance["resume_completion"]=reuse
    for path in (Path(__file__),h.REPO/"dayahead/tools/v39h_finish_active.py",h.REPO/"dayahead/tools/v39h_fast_close.py",h.REPO/"dayahead/tools/v39h_interrupt_lex.py"):
        provenance["source_SHA"][str(path.relative_to(h.REPO))]=h.grid.sha(path)
    h.atomic(provenance_path,provenance)
    manifest_path=h.ROOT/"V39H_REQUIRED_ARTIFACT_SHA_MANIFEST.json";manifest=h.read(manifest_path)
    names=list(manifest["SHA256"])+["V39H_PER_DAY_FINAL_RESULTS.csv","V39H_11_OF_13_RESUME_EVIDENCE.json","V39H_RESUME_COMPLETION_AUDIT.json","V39H_FAST_CLOSE_PROTECTED_CHECKPOINTS.json","V39H_FAST_CLOSE_INTERRUPT_ATTEMPTS.json"]
    manifest["SHA256"]={n:h.grid.sha(h.ROOT/n) for n in dict.fromkeys(names)};manifest["required_file_count"]=len(manifest["SHA256"])
    h.atomic(manifest_path,manifest)
    print(table);print("\n".join(f"{k} = {v}" for k,v in flags.items()))

if __name__=="__main__":
    record_resume() if "--record-resume" in sys.argv else closeout()
