"""Complete case-job lineage without materializing any missing site."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import pandas as pd
from dayahead.paper_analysis.storage import read,reference,write_json,write_parquet
from dayahead.v40d_actual.inputs import legacy_digest
from dayahead.v40d_actual.capacity_audit import write_csv


def build(repo):
    audit=repo/"dayahead/artifacts/v40d_actual_realized_replay"
    out=audit/"site_authority_audit"
    failed=pd.read_parquet(audit/"pre_day_complete_preflight/PRE_DAY_COMPLETE_CLASSIFICATIONS.parquet")
    failed=failed[failed.status.ne("PRE_DAY_COMPLETE")]
    rows=[]
    for (day,case),part in failed.groupby(["day","case"]):
        paths={c:repo/f"dayahead/artifacts/v39e_full_may_2025/V39E_DAYAHEAD_DECISION_FREEZE_{day}_{c}.json" for c in ("B0","B1","B3")}
        freeze={c:read(p) for c,p in paths.items()}
        for c,x in freeze.items():
            if x["DA_decision_SHA256"]!=legacy_digest(x["decision"]):raise RuntimeError("UPSTREAM_DECISION_HASH_DRIFT")
        d={c:x["decision"] for c,x in freeze.items()}
        own=d["B0" if case=="B2" else case]
        maps={c:{str(r["job_id"]):r for r in x["temporal_schedule"]} for c,x in d.items()}
        assignments={c:{str(r["job_uid"]):r for r in x["AIDC_assignments"]} for c,x in d.items()}
        initial={str(r["job_uid"]):r for r in own["common_initial_RUNNING_AIDC_state"]}
        own_assign={str(r["job_uid"]):r for r in own["AIDC_assignments"]}
        for r in part.to_dict("records"):
            uid=r["job_uid"];rw=maps["B0"][uid];rsp=maps["B1"][uid]
            row={"day":day,"case":case,"job_uid":uid,"state_at_issue":r["state_at_issue"],
                "RW_reservation_start":rw["scheduled_start_slot"],"RW_reservation_end":rw["scheduled_end_slot"],
                "RSP_reservation_start":rsp["scheduled_start_slot"],"RSP_reservation_end":rsp["scheduled_end_slot"],
                "D1_common_initial_state_present":uid in initial,"D1_common_initial_site":initial.get(uid,{}).get("initial_AIDC"),
                "accepted_A0_temporal_row_present":uid in maps["B3" if case=="B3" else "B0" if case=="B2" else case],
                "accepted_A0_site_assignment_present":uid in own_assign,
                "accepted_A0_site":own_assign.get(uid,{}).get("destination_AIDC"),
                "RW_comparator_site":assignments["B0"].get(uid,{}).get("destination_AIDC"),
                "Rack_WAN_migration_witness_present_in_own_assignment":uid in own_assign,
                "final_export_site":"UNASSIGNED",
                "RW_source":reference(paths["B0"]),"RSP_source":reference(paths["B1"]),
                "own_A0_source":reference(paths["B3" if case=="B3" else "B0" if case=="B2" else case]),
                "recovery_status":"MISSING_PRE_DAY_SPATIAL_EXECUTION_AUTHORITY",
                "reason":"PENDING has no common RUNNING initial site; temporal jobs completing before D00 are removed from D-day placement before an own-case site/Rack/WAN assignment is produced"}
            if row["D1_common_initial_state_present"] or row["accepted_A0_site_assignment_present"]:
                raise RuntimeError("LINEAGE_FOUND_OWN_CASE_AUTHORITY_REQUIRES_REVIEW")
            rows.append(row)
    write_parquet(out/"V40D_UNASSIGNED_SPILLOVER_FULL_LINEAGE.parquet",pd.DataFrame(rows))
    csv=[{k:(str(v) if isinstance(v,dict) else v) for k,v in r.items()} for r in rows]
    write_csv(out/"V40D_UNASSIGNED_SPILLOVER_FULL_LINEAGE.csv",csv)
    write_json(out/"V40D_PRE_DAY_PLACEMENT_AUTHORITY_DESIGN_ONLY.json",{
        "status":"DESIGN_ONLY_NOT_EXECUTED","all_pre_day_jobs_required":True,"observed_spillover_subset_selection_allowed":False,
        "population":"Every D1-visible job with pre-D00 planned execution under each frozen temporal policy, including jobs whose realized runtime later stays pre-day",
        "inputs":"D1 job ledger, requested/safe duration and reservations, frozen V39C capacities, non-additive V39D gang compatibility; no observed end, traffic or grid outcomes",
        "mechanics":"Reuse the existing deterministic ordering and spatial/gang constraints to materialize a complete pre-day execution witness; freeze UID-site-Rack and state-transition provenance before Actual reads",
        "must_define_before_execution":["scope of common versus case-specific pre-day placement","pre-day running/queued boundary state and migration readiness","immutable authority and input SHA","no May-result objective or site selection","repeat and permutation invariance gates"],
        "old_artifacts":"Do not patch the historical accepted Planning/Fresh freeze; any new scientific authority must be separately versioned and authorized",
        "needs_new_scientific_authority":True,"full_campaign_authorized":False,"new_site_assignments":0,
        "source_evidence":[reference(repo/"dayahead/v39a/spatial.py"),reference(repo/"dayahead/v39e/initial_state.py"),
            reference(repo/"dayahead/v39e/full_spatial.py"),reference(repo/"dayahead/v40a/accepted_initial.py")],
        "root_cause":"production_activity clips to [24,120) and skips jobs ending before/equal 24; common initialization returns RUNNING sites, while PENDING assignments are case-specific. A different comparator's D-day site is not an authority for this job's pre-day execution."})
    print({"lineage_rows":len(rows),"unique_jobs":failed.job_uid.nunique(),"own_case_sites_recovered":0})

if __name__=="__main__":build(Path(__file__).resolve().parents[2])
