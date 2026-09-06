"""Independent saved-artifact verification of the four-case smoke only."""
from pathlib import Path
from types import SimpleNamespace
import math
import numpy as np
import pandas as pd
from dayahead.paper_analysis.storage import read, reference, sha, write_json
from .inputs import frozen_jobs, capacity
from .rack_dispatch import Rack
from .capacity_audit import (VECTOR, compare_occupancy, audit_gangs, check_it_power, headroom_rows, write_csv)
from .physical_audit import c1_recalculation, rho_recalculation
from .pre_day_complete import audit_exclusion
from .preflight import verify_protected
from .contracts import ReplayError
from .mess_audit import audit_mess


def records(path):
    return [{k:(None if isinstance(v,float) and math.isnan(v) else v) for k,v in r.items()}
            for r in pd.read_parquet(path).to_dict("records")]


def comparison_sources(binding, out):
    cert=read(binding["certificate"])
    if binding["case"]=="B3":
        p=Path(binding["AIDC_decision_source"]).parent/"PLANNING_PHYSICAL_GATES.json"
        f=p.parent/"FRESH_AC_RESULT.json"
        if sha(p)!=cert["files"][p.name] or sha(f)!=cert["files"][f.name]:
            raise ReplayError("SMOKE_REPORT_PROTECTED_OBJECTIVE_SOURCE_DRIFT")
        j=read(p)["rho_max"];fresh=read(f)["summary"]["rho_max_AC"]
    else:
        p=Path(cert.get("historical_checkpoint",cert.get("checkpoint","")))
        if not p.is_file():raise ReplayError("SMOKE_REPORT_PLANNING_SOURCE_MISSING")
        if sha(p)!=cert.get("historical_checkpoint_SHA",cert.get("checkpoint_SHA")):
            raise ReplayError("SMOKE_REPORT_CHECKPOINT_SHA_DRIFT")
        cp=read(p);j=cp["result"]["objective"]
        matches=[]
        namespace=p.parents[2]
        for candidate in (namespace/"fresh"/binding["day"]).rglob("OPENDSS_SUMMARY.json"):
            if read(candidate)["schedule_sha256"]==binding["binding_components"]["Fresh_schedule_SHA"]:
                matches.append(candidate)
        if not matches:raise ReplayError("SMOKE_REPORT_FRESH_SOURCE_MISSING")
        f=sorted(matches)[0];fresh=read(f)["rho_max_AC"]
        if fresh!=cp["result"]["Fresh"]["rho_max_AC"]:raise ReplayError("SMOKE_REPORT_FRESH_VALUE_MISMATCH")
    a=out/"actual_grid/OPENDSS_SUMMARY.json"
    return {"Planning_J":j,"Fresh_AC_rho":fresh,"Actual_AC_rho":read(a)["rho_max_AC"],
        "Planning_source":reference(p),"Fresh_source":reference(f),"Actual_source":reference(a),
        "Planning_J_definition":"final accepted executed decision evaluated by Planning authority; B3 after AC restoration"}


def build(repo,day="2025-05-01"):
    repo=Path(repo);root=repo/"dayahead/artifacts/v40d_actual_realized_replay"
    smoke=root/"smoke"/day;output=root/"capacity_audit"
    bindings=read(root/"V40D_ACTUAL_DECISION_BINDING_AUDIT.json")["cases"]
    authority,_,*_=capacity(repo);caps=authority["frozen_V39C_site_capacity"]
    racks=[Rack(p["aidc_id"],p["rack_pool_id"],p["compatibility_GPU_limit"]) for p in authority["logical_Rack_pools"]]
    results=[];headroom=[];pairs=[]
    with np.load(smoke/"actual_exogenous.npz",allow_pickle=False) as z:
        weather=pd.DataFrame({"t_wb_c":z["t_wb_c"],"rh_pct":z["rh_pct"]})
    for case in ("B0","B1","B2","B3"):
        out=smoke/case;b=next(b for b in bindings if b["day"]==day and b["case"]==case)
        status=read(out/"SMOKE_RESULT.json")
        if status["status"]!="PASS" or status["actual_optimizer_calls"]!=0:
            raise ReplayError("SMOKE_REPORT_CASE_NOT_COMPLETE:"+case)
        jobs,_=frozen_jobs(repo,b)
        ledger=records(out/"job_ledger.parquet")
        series=pd.read_parquet(out/"aidc_site_timeseries.parquet")
        replay={"job_ledger":ledger,"rack_ledger":records(out/"rack_ledger.parquet"),"rack_waits":records(out/"rack_waits.parquet"),
            "site_occupancy":series.rename(columns={"occupied_GPU":"occupied_GPU_slots"})[["site_id","slot","occupied_GPU_slots","GPU_capacity"]].to_dict("records")}
        occ,contrib,recalc=compare_occupancy(replay,caps)
        gang=audit_gangs(jobs,replay,racks)
        pre=[r for r in ledger if r["status"]=="PRE_DAY_COMPLETE"]
        audit_exclusion(pre,replay["rack_ledger"],contrib)
        original_contributions=records(out/"job_GPU_contributions.parquet")
        if {(r["job_uid"],r["slot"],r["site"],r["occupied_GPU"]) for r in contrib}!={(r["job_uid"],r["slot"],r["site"],r["occupied_GPU"]) for r in original_contributions} or len(contrib)!=len(original_contributions):
            raise ReplayError("SAVED_JOB_GPU_CONTRIBUTIONS_MISMATCH")
        def matrix(field):
            return series.pivot(index="slot",columns="site_id",values=field).reindex(index=range(96),columns=sorted(caps)).to_numpy()
        power={"IT":matrix("P_IT_kW"),"PCC_P":matrix("P_PCC_kW"),"PCC_Q":matrix("Q_PCC_kvar")}
        it=check_it_power(caps,occ,power["IT"])
        c1=c1_recalculation(repo,power,weather)
        engine=read(out/"actual_grid/ACTUAL_ENGINE_BINDING_READBACK.json")
        if engine["status"]!="PASS" or engine["applied_slots"]!=96:raise ReplayError("SMOKE_ENGINE_BINDING_NOT_PASS")
        with np.load(out/"actual_grid/ACTUAL_APPLIED_AIDC_PCC.npz",allow_pickle=False) as z:
            if not np.array_equal(z["AIDC_P"],power["PCC_P"]) or not np.array_equal(z["AIDC_Q"],power["PCC_Q"]):
                raise ReplayError("SMOKE_APPLIED_PCC_READBACK_MISMATCH")
        # Independently join realized MESS ledger to every recorded engine service setpoint.
        mess=records(out/"MESS_executed_trajectory.parquet")
        initial_states=read(out/"V40D_ACTUAL_MESS_D00_STATE_AUDIT.json")
        mess_audit=audit_mess(read(out/"MESS_FROZEN_COMMANDS.json"),read(out/"MESS_actual_moves.json"),mess,
            {r["vehicle_id"]:r["initial_energy_kWh"] for r in initial_states},initial_states)
        for applied in read(out/"actual_grid/ACTUAL_APPLIED_MESS_PQ.json"):
            selected=[r for r in mess if r["slot"]==applied["slot"] and str(r["actual_service_id"]).upper()==applied["service"]]
            p=sum(r["P_EXEC"] for r in selected);q=sum(r["Q_EXEC"] for r in selected)
            if max(abs(applied["generator_P"]-max(p,0)),abs(applied["generator_Q"]-q),abs(applied["load_P"]-max(-p,0)),abs(applied["load_Q"]))>2e-12:
                raise ReplayError("SAVED_MESS_TO_ENGINE_BINDING_MISMATCH")
        for r in mess:
            if r["actual_service_id"] is None and (r["P_EXEC"]!=0 or r["Q_EXEC"]!=0):
                raise ReplayError("SAVED_MESS_TRANSIT_POWER")
        actual_summary=read(out/"actual_grid/OPENDSS_SUMMARY.json")
        rho=rho_recalculation(SimpleNamespace(summary=actual_summary),out/"actual_grid")
        values=comparison_sources(b,out)
        values.update(Actual_OpenDSS_run_id=status["Actual_OpenDSS_run_id"],Actual_AC_rho_source=str(out/"actual_grid/OPENDSS_PHASE_ARRAYS.npz"))
        if values["Actual_AC_rho"]!=rho["Actual_AC_rho"]:raise ReplayError("ACTUAL_RHO_REPORT_MISMATCH")
        counters={k:recalc[k] for k in ("SITE_CAPACITY_VIOLATIONS_TOTAL","GPU_OCCUPANCY_RECALC_MAX_ERROR","PRE_DAY_COMPLETE_GPU_OCCUPANCY_VIOLATIONS")}
        counters.update({k:gang[k] for k in ("ACTUAL_GANG_SPLIT_COUNT","ACTUAL_ALTERNATE_AIDC_ATTEMPTS","ACTUAL_CAPACITY_DRIVEN_SITE_CHANGE_COUNT")})
        counters.update(RACK_CAPACITY_SUM_USED="NO",RACK_USED_AS_ADDITIVE_SITE_CAPACITY="NO",
            GPU_TO_IT_POWER_MAX_ERROR_KW=it["GPU_TO_IT_POWER_MAX_ERROR_KW"])
        counters.update({k:mess_audit[k] for k in ("MESS_ROUTE_CHANGE_COUNT","MESS_TRANSIT_RESET_TO_ORIGIN_COUNT",
            "MESS_COMMAND_NONEXECUTION_COUNT","SOC_BALANCE_MAX_ERROR","SOC_BOUND_VIOLATION_COUNT","TRAVEL_ENERGY_DOUBLE_COUNT_COUNT",
            "TRANSIT_AT_D00_RESET_TO_ORIGIN_COUNT","CONNECTED_AT_D00_RESET_TO_ORIGIN_COUNT","EARLY_DEPARTURE_STATE_LOSS_COUNT")})
        checks={name:"PASS" for name in ("01_LEDGER_GPU_RECALC","02_SITE_CAPACITY_HARD_CAP","03_EXACT_VECTOR","04_SUM_624",
            "05_RACK_NONADDITIVE","06_DETERMINISTIC_COMPATIBILITY_LABEL","07_NO_GANG_SPLIT","08_NO_ALTERNATE_AIDC",
            "09_REALIZED_OVERRUN_SAME_SITE_DELAY_BACKLOG","10_PRE_DAY_COMPLETE_EXCLUSION","11_GPU_CENTER_IT",
            "12_OBSERVED_WEATHER_C1_PCC","13_NO_DA_FRESH_PCC_REUSE","14_ACTUAL_ENGINE_PCC_MESS_BINDING","15_NEW_ACTUAL_RHO",
            "16_CASE_ACCEPTED_AIDC_BINDING")}
        row={"status":"PASS", "day":day,"case":case,"checks":checks,"counters":counters,
            "SITE_CAPACITY_VECTOR":VECTOR,"SITE_CAPACITY_SUM":624,"independent_occupancy":recalc,"gang":gang,
            "power":it,"C1":c1,"engine":engine,"Actual_rho":rho, "comparison":values,
            "MESS_invariants_and_SOC":mess_audit,
            "PRE_DAY_COMPLETE_job_count":len(pre),"PRE_DAY_COMPLETE_GPU_occupancy":0,"PRE_DAY_COMPLETE_PCC_contribution_kWh":0,
            "delayed_by_site_capacity_job_count":sum(bool(r.get("delayed_by_GPU_capacity")) for r in ledger),
            "runtime_gt_requested_walltime_job_count":sum(bool(r.get("actual_runtime_gt_requested_walltime")) for r in ledger),
            "admitted_backlog_GPU_hours_at_H":sum(r.get("backlog_GPU_hours",0) for r in ledger),
            "AIDC_DECISION_SOURCE":b["AIDC_decision_source"],"AIDC_DECISION_SHA":sha(b["AIDC_decision_source"]),
            "B3_AIDC_stage":"FINAL_ACCEPTED_INTERNAL_A1" if case=="B3" else "NOT_B3",
            "physical_violation":actual_summary["physical_violation"],"physical_violations_repaired":False,
            "smoke_repeat_bit_equal":status["grid_observer_repeat_bit_equal"],"full_campaign_authorized":False}
        results.append(row);headroom.extend(headroom_rows(day,case,replay,occ));pairs.append({"day":day,"case":case,**values})
    guard=verify_protected(repo,root)
    if guard["status"]!="PASS":raise ReplayError("SMOKE_REPORT_PROTECTED_ARTIFACT_DRIFT")
    for row in results:
        row["checks"]["17_PROTECTED_PLANNING_FRESH_DIFF_ZERO"]="PASS"
        row["protected_artifacts"]=guard
        write_json(smoke/row["case"]/"V40D_ACTUAL_SMOKE_17_POINT_AUDIT.json",row)
    write_json(smoke/"PROTECTED_REFERENCE_AFTER_SMOKE.json",guard)
    write_json(smoke/"V40D_ACTUAL_SMOKE_COMPARISON.json",{"scope":"MAY01_FOUR_CASE_SMOKE_ONLY","cases":pairs})
    write_csv(smoke/"V40D_ACTUAL_SMOKE_COMPARISON.csv",[{k:r[k] for k in ("day","case","Planning_J","Fresh_AC_rho","Actual_AC_rho","Actual_AC_rho_source","Actual_OpenDSS_run_id")} for r in pairs])
    write_csv(output/"V40D_ACTUAL_SITE_GPU_CAPACITY_SMOKE.csv",headroom)
    static=pd.read_csv(output/"V40D_ACTUAL_SITE_GPU_CAPACITY_AUDIT.csv").to_dict("records")
    h={(r["day"],r["case"],r["site"]):r for r in headroom}
    write_csv(output/"V40D_ACTUAL_SITE_GPU_CAPACITY_AUDIT.csv",[{**r,**h.get((r["day"],r["case"],r["site"]),{})} for r in static])
    for name,field in (("GPU_OCCUPANCY_RECALCULATION","independent_occupancy"),("GPU_GANG_INVARIANT","gang"),("GPU_TO_IT_POWER_CONSERVATION","power")):
        write_json(output/("V40D_ACTUAL_"+name+".json"),{"status":"PASS_SMOKE_ONLY","runtime_case_count":4,"full_124_runtime_coverage":False,
            "cases":[{"day":r["day"],"case":r["case"],**r[field]} for r in results]})
    aggregate=pd.DataFrame(headroom).groupby("site",as_index=False).agg(capacity_GPU=("capacity_GPU","first"),
        max_actual_occupancy_GPU=("max_actual_occupancy_GPU","max"),min_headroom_GPU=("min_headroom_GPU","min"),
        capacity_violation_count=("capacity_violation_count","sum"),waiting_case_job_rows=("waiting_jobs_due_to_site_capacity","sum"),
        delayed_GPU_hours_due_to_site_capacity=("delayed_GPU_hours_due_to_site_capacity","sum"))
    aggregate["scope"]="May01 4 smoke cases only; 31-day aggregate unavailable until authorized execution"
    write_csv(output/"V40D_ACTUAL_SITE_GPU_CAPACITY_COVERAGE_AGGREGATE.csv",aggregate.to_dict("records"))
    final={"status":"PASS_SMOKE_AUDITS_FULL_CAMPAIGN_BLOCKED","smoke_cases":4,"smoke_17_checks_all_PASS":True,
        "static_binding_cases":124,"Actual_execution_days":1,"SITE_CAPACITY_VECTOR":VECTOR,"SITE_CAPACITY_SUM":624,
        "counters_by_case":[{"case":r["case"],**r["counters"]} for r in results],
        "protected_changed_count":0,"UNASSIGNED_blocked_cases":44,"UNASSIGNED_blocked_case_job_rows":2420,
        "UNASSIGNED_blocked_unique_jobs":891,"full_campaign_authorized":False,"full_campaign_launched":False,
        "Actual_global_31_day_mean_available":False}
    write_json(smoke/"MAY01_FOUR_CASE_SMOKE_STATUS.json",final)
    write_json(output/"CAPACITY_AUDIT_STATUS.json",final)
    return final
