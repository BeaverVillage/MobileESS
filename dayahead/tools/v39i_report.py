"""Read-only scientific assembly for V39I; never constructs or solves a model."""
from __future__ import annotations
import argparse
from datetime import timedelta, timezone
from pathlib import Path
import sys
REPO=Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:sys.path.insert(0,str(REPO))
import numpy as np
import pandas as pd
from dayahead.tools import run_v39i_minmax as i
h=i.h
ROOT=i.ROOT
CLASSIFICATIONS={"A":"LONG_DELAY_WAS_TIEBREAK_ARTIFACT","B":"LONG_DELAY_PARTLY_REDUCIBLE","C":"LONG_DELAY_REQUIRED_ON_PRIMARY_OPTIMAL_FACE"}


def issue_time(day):
    return pd.Timestamp(day,tz=timezone(timedelta(hours=10)))-pd.Timedelta(hours=6)


def timestamp(day,slot):
    return (issue_time(day)+pd.Timedelta(minutes=15*int(slot))).isoformat()


def interval_parts(starts,ends,gpus):
    """Exact half-open interval partition in GPU-slots, without grid extrapolation."""
    starts=np.asarray(starts,dtype=np.int64);ends=np.asarray(ends,dtype=np.int64)
    gpus=np.asarray(gpus,dtype=np.int64)
    assert np.all(ends>=starts)
    before=np.maximum(np.minimum(ends,24)-starts,0)*gpus
    within=np.maximum(np.minimum(ends,120)-np.maximum(starts,24),0)*gpus
    after=np.maximum(ends-np.maximum(starts,120),0)*gpus
    assert np.array_equal(before+within+after,(ends-starts)*gpus)
    return before,within,after


def domain_audit(day,b):
    pre,inside,post=interval_parts(b.scheduled_start_slot,b.scheduled_end_slot,b.requested_gpus)
    moved=b.start_delay_slots.to_numpy()>0
    moved_total=int(((b.scheduled_end_slot-b.scheduled_start_slot)*b.requested_gpus).to_numpy()[moved].sum())
    outside=int(pre.sum()+post.sum());moved_outside=int((pre+post)[moved].sum())
    latest=int(b.scheduled_end_slot.max());last_moved=int(b.loc[moved,"scheduled_end_slot"].max()) if moved.any() else None
    return {
        "classification":"RESERVATION_EXTENDS_BEYOND_ACCEPTED_GRID_DOMAIN" if outside else "WITHIN_ACCEPTED_GRID_DOMAIN",
        "slot_minutes":15,"interval_convention":"half-open [start,end)","issue_time_fixed_AEST":issue_time(day).isoformat(),
        "earliest_modeled_issue_slot":0,"earliest_reservation_start_slot":int(b.scheduled_start_slot.min()),
        "latest_reservation_completion_slot":latest,"latest_reservation_completion_AEST":timestamp(day,latest),
        "complete_reservation_accounting_domain":[0,max(120,int((b.latest_start+b.RSP_duration_slots).max()))],
        "operating_day_grid_domain_start_slot":24,"operating_day_grid_domain_end_slot_exclusive":120,
        "operating_day_grid_domain_start_AEST":timestamp(day,24),"operating_day_grid_domain_end_AEST":timestamp(day,120),
        "moved_jobs_extending_beyond_grid_domain_end":int((moved & b.scheduled_end_slot.gt(120)).sum()),
        "moved_jobs_starting_at_or_beyond_grid_domain_end":int((moved & b.scheduled_start_slot.ge(120)).sum()),
        "reservation_GPU_h_before_grid_domain":int(pre.sum())/4,"reservation_GPU_h_inside_grid_domain":int(inside.sum())/4,
        "reservation_GPU_h_after_grid_domain":int(post.sum())/4,"reservation_GPU_h_outside_grid_domain":outside/4,
        "moved_jobs_reservation_GPU_h":moved_total/4,"moved_jobs_reservation_GPU_h_outside_grid_domain":moved_outside/4,
        "moved_jobs_reservation_GPU_h_after_grid_domain":int(post[moved].sum())/4,
        "moved_jobs_outside_reservation_fraction":moved_outside/moved_total if moved_total else 0,
        "maximum_completion_beyond_grid_domain_end_min":max(0,latest-120)*15,
        "latest_moved_job_completion_slot":last_moved,
        "maximum_moved_job_completion_beyond_grid_domain_end_min":max(0,last_moved-120)*15 if last_moved is not None else 0,
        "outside_domain_site_assignment_physically_verified":False,"outside_domain_portions_reservation_accounting_only":True,
        "outside_domain_aggregate_624_GPU_capacity_still_enforced":True,
        "warning":"No off-domain site/grid authority or realized-computation claim. Reservation extension is evidence, not automatic failure."}


def service_audit(a,b):
    assert a.job_uid.is_unique and b.job_uid.is_unique
    b=b.set_index("job_uid").loc[a.job_uid].reset_index()
    changed=b.start_delay_slots.gt(0)
    exact={"job_set_equal":set(a.job_uid)==set(b.job_uid),
        "GPU_requests_equal":np.array_equal(a.requested_gpus,b.requested_gpus),
        "safe_duration_slots_equal":np.array_equal(a.RSP_duration_slots,b.duration_slots),
        "safe_duration_seconds_equal":np.array_equal(a.RSP_duration_seconds,b.RSP_duration_seconds),
        "contiguous_duration_equal":np.array_equal(b.scheduled_end_slot-b.scheduled_start_slot,a.RSP_duration_slots),
        "eligible_mask_equal":np.array_equal(a.eligible,b.eligible)}
    assert all(exact.values())
    violations=int((changed & b.scheduled_end_slot.gt(b.RW_scheduled_completion)).sum())
    preexisting=a.RSP_scheduled_completion.gt(a.RW_scheduled_completion).to_numpy()
    newly=int((b.scheduled_end_slot.gt(b.RW_scheduled_completion).to_numpy() & ~preexisting).sum())
    gpu_slots_before=int((a.requested_gpus*a.RSP_duration_slots).sum())
    gpu_slots_after=int((b.requested_gpus*b.duration_slots).sum())
    assert gpu_slots_before==gpu_slots_after
    safe_seconds_before=float((a.requested_gpus*a.RSP_duration_seconds).sum())
    safe_seconds_after=float((b.requested_gpus*b.RSP_duration_seconds).sum())
    assert safe_seconds_before==safe_seconds_after
    return {**exact,"safe_reservation_GPU_slots_before":gpu_slots_before,"safe_reservation_GPU_slots_after":gpu_slots_after,
        "safe_reservation_GPU_h_before":gpu_slots_before/4,"safe_reservation_GPU_h_after":gpu_slots_after/4,
        "safe_duration_seconds_GPU_h_before":safe_seconds_before/3600,"safe_duration_seconds_GPU_h_after":safe_seconds_after/3600,
        "shifted_jobs_RW_completion_violations":violations,"new_RW_completion_violations":newly,
        "eligible_RW_completion_violations":int((b.eligible & b.scheduled_end_slot.gt(b.RW_scheduled_completion)).sum()),
        "preexisting_RSP_completion_later_than_RW_jobs":int(preexisting.sum()),
        "all_jobs_completion_later_than_RW_jobs":int(b.scheduled_end_slot.gt(b.RW_scheduled_completion).sum()),
        "noneligible_time_changes":int((~b.eligible & b.start_delay_slots.ne(0)).sum()),
        "negative_delays":int(b.start_delay_slots.lt(0).sum()),
        "RUNNING_site_changes":int((b.state_at_issue.eq("RUNNING") & b.AIDC.ne(b.initial_AIDC)).sum()),
        "RW_is_counterfactual_completion_not_user_deadline":True,"modeled_reservation_not_measured_or_realized_computation":True,
        "RW_completion_noninferiority_pass":violations==newly==0,"frozen_safe_runtime_preserved":all(exact.values())}


def comparison(day,label,b,result,domain):
    delta=b.start_delay_slots.to_numpy(dtype=int)*15
    changed=delta[delta>0];eligible=delta[b.eligible.to_numpy()]
    grid=result["audit"]["grid"]
    return {"day":day,"witness":label,"primary_GPU_slots":int(b.occupancy_deviation_GPU_slots.sum()),
        "primary_exact_status":"GLOBALLY_CERTIFIED_REUSED","changed_jobs":len(changed),"eligible_jobs":len(eligible),
        "max_added_delay_min":int(delta.max()),"median_changed_delay_min":float(np.median(changed)) if len(changed) else 0,
        "P95_changed_delay_min":float(np.quantile(changed,.95)) if len(changed) else 0,
        "median_eligible_delay_min":float(np.median(eligible)),"P95_eligible_delay_min":float(np.quantile(eligible,.95)),
        "total_added_delay_min":int(delta.sum()),"GPU_weighted_delay_GPU_slots":int((b.requested_gpus*b.start_delay_slots).sum()),
        "GPU_weighted_delay_GPU_minutes":int((b.requested_gpus*b.start_delay_slots).sum())*15,
        **{f"jobs_delay_gt_{hours}h":int((delta>hours*60).sum()) for hours in (4,8,12,24,48,72)},
        "Vmax_pu":grid["Vmax"],"Vmin_pu":grid["Vmin"],"upper_voltage_headroom_pu":1.05-grid["Vmax"],
        "lower_voltage_headroom_pu":grid["Vmin"]-.95,"critical_issue_slot":grid["critical_issue_slot"],
        "critical_target_slot":grid["critical_target_slot"],"critical_voltage_bus_phase":grid["critical_voltage_bus_phase"],
        "RUNNING_migrations":result["audit"]["RUNNING_site_changes"],"WAN_transfers":result["audit"]["WAN_transfer_count"],
        "safe_reservation_GPU_h":int((b.requested_gpus*b.duration_slots).sum())/4,
        "safe_duration_seconds_GPU_h":float((b.requested_gpus*b.RSP_duration_seconds).sum()/3600),
        "outside_grid_reservation_GPU_h":domain["reservation_GPU_h_outside_grid_domain"],
        "moved_jobs_outside_grid_reservation_GPU_h":domain["moved_jobs_reservation_GPU_h_outside_grid_domain"],
        "delay_quantile_convention":"linear; changed jobs only in changed columns; eligible includes zeros"}


def max_jobs(day,old,new):
    snapshots=pd.read_parquet(REPO/f"dayahead/artifacts/v37_r4a_per_day_aidc/days/{day}/V37_R4A_D1_SNAPSHOT.parquet")
    submits=dict(zip(snapshots.id.astype(str),snapshots.submit_time.astype(str)))
    old=old.set_index("job_uid");new=new.set_index("job_uid")
    oldmax=int(old.start_delay_slots.max());newmax=int(new.start_delay_slots.max())
    selected=sorted(set(old.index[old.start_delay_slots.eq(oldmax)])|set(new.index[new.start_delay_slots.eq(newmax)]))
    rows=[]
    for uid in selected:
        a=old.loc[uid];b=new.loc[uid];slack=int(a.latest_start-a.RSP_scheduled_start)
        row={"day":day,"job_uid":uid,"QoS_tier":a.qos,"requested_GPU":int(a.requested_gpus),"submit_time":submits[uid],
            "frozen_RSP_start_slot":int(a.RSP_scheduled_start),"frozen_RSP_start_AEST":timestamp(day,a.RSP_scheduled_start),
            "frozen_safe_duration_slots":int(a.RSP_duration_slots),"frozen_safe_duration_seconds":float(a.RSP_duration_seconds),
            "RW_modeled_start_slot":int(a.RW_scheduled_start),"RW_modeled_completion_slot":int(a.RW_scheduled_completion),
            "RW_modeled_start_AEST":timestamp(day,a.RW_scheduled_start),"RW_modeled_completion_AEST":timestamp(day,a.RW_scheduled_completion),
            "latest_admissible_start_slot":int(a.latest_start),"latest_admissible_start_AEST":timestamp(day,a.latest_start),
            "admissible_slack_slots":slack,"admissible_slack_min":slack*15,
            "attains_old_maximum":int(a.start_delay_slots)==oldmax,"attains_new_maximum":int(b.start_delay_slots)==newmax,
            "individual_UID_necessity_globally_proven":False}
        for prefix,r in (("old_V39H",a),("new_V39I",b)):
            row.update({f"{prefix}_start_slot":int(r.scheduled_start_slot),f"{prefix}_start_AEST":timestamp(day,r.scheduled_start_slot),
                f"{prefix}_added_delay_min":int(r.start_delay_slots)*15,f"{prefix}_completion_slot":int(r.scheduled_end_slot),
                f"{prefix}_completion_AEST":timestamp(day,r.scheduled_end_slot),
                f"{prefix}_completion_margin_to_RW_min":int(r.RW_scheduled_completion-r.scheduled_end_slot)*15,
                f"{prefix}_slack_consumption_fraction":float(r.start_delay_slots/slack) if slack else 0,
                f"{prefix}_site":r.AIDC})
        rows.append(row)
    return pd.DataFrame(rows)


def resource_observations(b):
    horizon=max(120,int((b.latest_start+b.duration_slots).max()));occ=np.zeros(horizon,dtype=int)
    for r in b.itertuples(index=False):occ[r.scheduled_start_slot:r.scheduled_end_slot]+=int(r.requested_gpus)
    return {"aggregate_capacity_GPU":624,"max_aggregate_reserved_GPU":int(occ.max()),
        "aggregate_capacity_tight_issue_slots":np.flatnonzero(occ==624).tolist(),
        "cause_attribution":"Observed binding rows only. Global min-max lower bound is for the joint frozen model; no individual-UID or resource-family necessity counterfactual was solved."}


def preservation():
    start=h.read(ROOT/"V39I_START_STATE.json")
    current=h.v39g.source_hashes();metadata_h=i.metadata(h.ROOT)
    final_head=h.v39g.git("rev-parse","HEAD")
    head_delta=h.v39g.git("diff","--name-only",start["starting_HEAD"],final_head).splitlines()
    checks={"production_source_SHA256_unchanged":current==start["production_source_SHA256"],
        "V39E_F_G_metadata_unchanged":h.preserved_metadata()==start["V39E_F_G_metadata"],
        "V39H_all_metadata_unchanged":metadata_h==start["V39H_metadata"],
        "V39H_required_SHA256_unchanged":all(h.grid.sha(h.ROOT/p)==sha for p,sha in start["V39H_required_SHA256"].items())}
    assert all(checks.values()),checks
    return {**checks,"production_files_checked":len(current),"V39H_required_SHA_files_checked":len(start["V39H_required_SHA256"]),
        "V39H_metadata_files_checked":len(metadata_h),"starting_HEAD":start["starting_HEAD"],"final_HEAD":final_head,
        "starting_branch":start["starting_branch"],"final_branch":h.v39g.git("branch","--show-current"),
        "external_HEAD_changed":final_head!=start["starting_HEAD"],"HEAD_delta_paths":head_delta,
        "HEAD_delta_working_files_match_start_SHA":all(p in start["production_source_SHA256"] and h.grid.sha(REPO/p)==start["production_source_SHA256"][p] for p in head_delta),
        "git_context_note":"During V39I, an external checkout/commit recorded the pre-existing dirty monitor script. V39I did not commit or restore branches; actual working scientific source bytes remain the start-state authority.",
        "recent_reflog":h.v39g.git("reflog","-6","--date=iso"),
        "Gurobi_version":start["Gurobi_version"],"max_day_workers":2,"Threads_per_model":4,"Seed":20260905,"MIPGap":0,
        "primary_optimization_reruns":0,"migration_MILP_reruns":0,"other_V39H_day_reruns":0,
        "full_preflight_calls":0,"May_campaign_calls":0,"Actual_reads":0,"Fresh_reads":0,
        "May01_05_result_content_reads":0,"May01_05_result_writes":0,
        "preservation_scope":"Production source bytes plus E/F/G/H size/mtime inventories and all required H SHA certificates; no Actual/Fresh result content access.",
        "source_files_SHA256":{str(p.relative_to(REPO)):h.grid.sha(p) for p in (Path(i.__file__),Path(__file__),REPO/"tests/dayahead/test_v39i_minmax.py")}}


def assemble():
    rows=[];days={}
    for day in i.DAYS:
        out=ROOT/"days"/day
        a,_,_=h.inputs(day)
        old=pd.read_parquet(h.ROOT/"days"/day/"V39H_SHADOW_SCHEDULE.parquet")
        new=pd.read_parquet(out/"V39I_MINMAX_DELAY_SCHEDULE.parquet")
        oldresult=h.read(h.ROOT/"days"/day/"V39H_SHADOW_A_RESULT.json")
        result=h.read(out/"V39I_MINMAX_DELAY_RESULT.json")
        assert result["D_MAX_exact_optimality"] and result["primary_equality_exact"]
        assert int(new.occupancy_deviation_GPU_slots.sum())==int(old.occupancy_deviation_GPU_slots.sum())==i.PRIMARY[day]
        grid_certificate=h.read(out/"V39I_GRID_VERIFICATION.json")
        capacity,_=h._load_capacity(REPO);sites=list(capacity.aidc_ids)
        with np.load(out/"V39I_VERIFIED_WITNESS.npz") as witness:
            occ=witness["GPU_complete"];pcc=witness["PCC_target"]
        with np.load(out/"V39G_C1_INTEGER_TABLES.npz") as tables:
            expected=np.array([[tables[s][t,occ[t+24,k]] for k,s in enumerate(sites)] for t in range(96)])
        assert np.array_equal(expected,pcc) and np.isfinite(pcc).all()
        bus,phase=grid_certificate["grid"]["critical_voltage_bus_phase"].rsplit(".",1)
        grid_certificate.update(C1_PCC_integer_lookup_violations=0,C1_PCC_nonfinite_values=0,
            C1_PCC_max_absolute_lookup_residual=float(np.abs(expected-pcc).max()),
            critical_day=day,critical_bus=bus,critical_phase=phase,physical_verification_slot_count=96)
        i.atomic(out/"V39I_GRID_VERIFICATION.json",grid_certificate)
        domain={"day":day,"old_V39H":domain_audit(day,old),"new_V39I":domain_audit(day,new)}
        i.atomic(out/"V39I_TIME_DOMAIN_AUDIT.json",domain)
        jobs=max_jobs(day,old,new);jobs.to_csv(out/"V39I_MAX_DELAY_JOB_AUDIT.csv",index=False,encoding="utf-8-sig")
        work={"old_V39H":service_audit(a,old),"new_V39I":service_audit(a,new)}
        rows.extend([comparison(day,"V39H",old,oldresult,domain["old_V39H"]),comparison(day,"V39I_MINMAX",new,result,domain["new_V39I"])])
        days[day]={"service_work":work,"resource_observations":resource_observations(new),
            "old_max_delay_min":int(old.start_delay_slots.max())*15,"new_exact_max_delay_min":result["D_MAX_minutes"],
            "maximum_delay_reduction_min":int(old.start_delay_slots.max())*15-result["D_MAX_minutes"],
            "max_attaining_job_UIDs_old":jobs.loc[jobs.attains_old_maximum,"job_uid"].tolist(),
            "max_attaining_job_UIDs_new":jobs.loc[jobs.attains_new_maximum,"job_uid"].tolist(),
            "named_UID_necessity_proven":False,"global_joint_D_MAX_lower_bound_certified":True}
    pd.DataFrame(rows).to_csv(ROOT/"V39I_V39H_VS_MINMAX_COMPARISON.csv",index=False,encoding="utf-8-sig")
    i.atomic(ROOT/"V39I_SERVICE_DELAY_AUDIT.json",{"days":days,"Q5_caveat":"Maximum-attaining UIDs are not necessarily uniquely forced across the primary-optimal face. No such per-UID necessity claim is made.",
        "quantiles":"Linear interpolation; both changed-job-only and all-eligible populations are separately labeled.",
        "no_arbitrary_service_acceptability_threshold":True})
    i.atomic(ROOT/"V39I_DIAGNOSTIC_PROVENANCE.json",{**preservation(),"direct_D_MAX_optimization_attempts":2,
        "direct_D_MAX_attempts_interrupted_by_user_requested_runtime_switch":2,"direct_D_MAX_optimization_reruns":0,
        "threshold_feasibility_optimization_calls_by_day":{day:h.read(ROOT/"days"/day/"V39I_MINMAX_DELAY_RESULT.json")["threshold_optimization_calls"] for day in i.DAYS},
        "exactness_method":"T* FEASIBLE plus T*-1 INFEASIBLE; constant-zero feasibility queries only",
        "witness_selection_secondary_optimization_calls":0,"completed_at":h.now()})


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.parse_args();assemble()
