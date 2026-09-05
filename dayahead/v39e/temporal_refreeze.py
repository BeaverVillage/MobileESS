"""Promote saved V39H primary certificates with minimum safe recomputation.

No optimization entry point exists here. Changed schedules come only from
independently verified, primary-optimal V39H artifacts; failed repairs never
become migration inputs. Existing production replay adapters remain unchanged.
"""
from __future__ import annotations
from concurrent.futures import ProcessPoolExecutor, as_completed
from copy import deepcopy
from decimal import Decimal
import json
import math
from pathlib import Path
import shutil
from typing import Any
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits
from dayahead.v38.authority import canonical_sha256
from dayahead.v39c.freeze import atomic_json, sha256_file
from dayahead.v39a.power import site_it_power_kw, site_pcc_power, validate_power_conservation
from dayahead.v39a.spatial import production_activity
from dayahead.v39d.actual import validate_actual_fixed_replay
from dayahead.v39d.planning import planning_feasibility_gate
from dayahead.v39e.full_preflight import FULL_ROOT, FAST_ROOT, CASES, _freeze, _frame_records, _fresh_loader_audit
from dayahead.v39e.full_spatial import deterministic_rack_labels
from dayahead.v39e.contracts import EXPECTED_DATES, RACK_AUTHORITY_SHA256, CAPACITY_FILE_SHA256

CLOSE_ROOT=Path("dayahead/artifacts/v39h_production_refreeze_may_close")
H_ROOT=Path("dayahead/artifacts/v39h_13day_temporal_repair_migration_shadow")
CHANGED_DAYS=("2025-05-17","2025-05-23","2025-05-24","2025-05-25","2025-05-26")
MAY01_05=tuple(f"2025-05-{day:02d}" for day in range(1,6))
PRIMARY={"2025-05-17":2216,"2025-05-23":8,"2025-05-24":108,"2025-05-25":29568,"2025-05-26":13086}


def read(path):return json.loads(Path(path).read_text(encoding="utf-8"))


def source_fingerprint(repo):
    inputs={"initial_authority_SHA256":sha256_file(repo/FAST_ROOT/"V39E_COMMON_INITIAL_STATE_AUDIT.json"),
        "Rack_authority_SHA256":RACK_AUTHORITY_SHA256,"site_capacity_SHA256":CAPACITY_FILE_SHA256,
        "source_SHA256":{p.name:sha256_file(p) for p in sorted((repo/"dayahead/v39e").glob("*.py"))}}
    return inputs,canonical_sha256(inputs)


def materialize_day(repo_text,day):
    """D-1 inputs and saved H proofs only; no Actual/Fresh result namespace."""
    from dayahead.tools import run_v39h_shadow as h
    from dayahead.tools import v39h_shadow_report as hr
    repo=Path(repo_text);root=repo/CLOSE_ROOT;out=root/"days"/day;out.mkdir(parents=True,exist_ok=True)
    assert day in CHANGED_DAYS
    hr.equivalent_formulation()
    saved_path=out/"SELECTIVE_PREFLIGHT_CERTIFICATE.json"
    if saved_path.exists() and all((out/f"V39E_DAYAHEAD_DECISION_FREEZE_{day}_{case}.json").exists() for case in ("B1","B3")):
        saved=read(saved_path)
        if (saved["status"]=="PASS" and saved["H_schedule_SHA256"]==sha256_file(repo/H_ROOT/"days"/day/"V39H_SHADOW_SCHEDULE.parquet")
            and all(sha256_file(Path(p))==sha for p,sha in saved["frozen_input_SHA256"].items())):
            return {"day":day,"status":"PASS","Vmax":saved["independent_schedule_grid_audit"]["grid"]["Vmax"],
                "primary_optimum":saved["primary_optimum_GPU_slots"],"optimization_calls":0,"verification_reused":True}
    a,_,inputs=h.inputs(day)
    hday=repo/H_ROOT/"days"/day;result=read(hday/"V39H_SHADOW_A_RESULT.json")
    b=pd.read_parquet(hday/"V39H_SHADOW_SCHEDULE.parquet")
    cert=read(hday/"V39H_OBJECTIVE_CERTIFICATES.json")["stages"][1]
    assert result["temporal_repair_sufficient"] and result["audit"]["all_hard_constraints_pass"]
    assert cert["optimal"] and cert["gap"]==0 and cert["objective"]==math.ceil(cert["bound"])==PRIMARY[day]
    for column in a:assert np.array_equal(a[column].fillna("<NA>"),b[column].fillna("<NA>")),column
    assert int((2*b.requested_gpus*np.minimum(b.start_delay_slots,b.duration_slots)).sum())==PRIMARY[day]
    capacity,_=h._load_capacity(repo);sites=tuple(capacity.aidc_ids)
    coeff,nodes=h.grid.load_coefficients(hday)
    with np.load(hday/"V39G_C1_INTEGER_TABLES.npz") as raw:tables={s:raw[s].copy() for s in sites}
    bundle={"sites":sites,"capacity":capacity,"coefficients":coeff,"nodes":nodes,"tables":tables}
    audit,occ,expected_pcc=h.cloned_v39g(out).audit_schedule(b,bundle)
    assert audit["all_hard_constraints_pass"]
    base=pd.read_parquet(repo/f"dayahead/artifacts/v37_r4a_per_day_aidc/days/{day}/V37_R4A_RSP_SCHEDULE.parquet")
    indexed=b.set_index("job_uid").loc[base.job_id.astype(str)]
    assert set(base.job_id.astype(str))==set(b.job_uid)
    assert np.array_equal(base.duration_slots,indexed.duration_slots)
    assert np.array_equal(base.requested_gpus,indexed.requested_gpus)
    temporal=base.copy()
    temporal["scheduled_start_slot"]=indexed.scheduled_start_slot.to_numpy(int)
    temporal["scheduled_end_slot"]=indexed.scheduled_end_slot.to_numpy(int)
    temporal_path=out/"PRODUCTION_PRIMARY_OPTIMAL_RSP_SCHEDULE.parquet"
    temporal.to_parquet(temporal_path,index=False)
    lookup=b.set_index("job_uid");assignments=[]
    for job in production_activity(temporal):
        row=lookup.loc[job.job_uid];site=str(row.AIDC);running=job.state_at_issue=="RUNNING"
        initial=str(row.initial_AIDC) if running else site
        assert not running or site==initial
        assignments.append({"job_uid":job.job_uid,"state_at_issue":job.state_at_issue,"requested_GPU":job.requested_GPU,
            "active_start_slot":job.active_start_slot,"active_end_slot":job.active_end_slot,
            "initial_AIDC":initial,"current_AIDC":site,"source_AIDC":initial if running else None,"destination_AIDC":site,
            "migration_selected":False,"logical_Rack_compatibility_label":str(row.logical_Rack_compatibility_label)})
    assignments.sort(key=lambda row:row["job_uid"])
    gpu_rows=[];it_rows=[];max_power_error=Decimal(0)
    for t in range(96):
        active=dict(zip(sites,map(int,occ[t+24])))
        power=validate_power_conservation(capacity.site_capacity,active)
        assert power["status"]=="PASS"
        max_power_error=max(max_power_error,Decimal(power["absolute_error_kW"]))
        for site in sites:
            row={"operating_day":day,"temporal_mode":"RSP","slot":t,"AIDC":site,
                "active_GPU":active[site],"AIDC_GPU_capacity":int(capacity.site_capacity[site])}
            gpu_rows.append(row);it_rows.append({**row,"IT_power_kW":float(site_it_power_kw(capacity.site_capacity[site],active[site])),
                "CENTER_increment_W_per_GPU":547.7239090195797,"idle_equivalent_W_per_GPU":104.1606964512843})
    gpu=pd.DataFrame(gpu_rows);it=pd.DataFrame(it_rows);pcc=site_pcc_power(repo,day,it)
    matrix=pcc.sort_values(["slot","AIDC"]).PCC_P_kW.to_numpy(float).reshape(96,12)
    assert np.allclose(matrix,expected_pcc,rtol=0,atol=1e-12)
    planning=planning_feasibility_gate(str(repo),day,{"RSP":matrix.tolist()})["RSP"]
    assert planning["status"]=="PASS" and planning["planning_pass"]
    rack=deterministic_rack_labels(assignments,capacity);assert rack["status"]=="PASS"
    before_slots=int((a.requested_gpus*a.RSP_duration_slots).sum());after_slots=int((b.requested_gpus*b.duration_slots).sum())
    assert before_slots==after_slots and np.array_equal(a.RSP_duration_seconds,b.RSP_duration_seconds)
    assert (b.loc[b.start_delay_slots.gt(0),"scheduled_end_slot"]<=b.loc[b.start_delay_slots.gt(0),"RW_scheduled_completion"]).all()
    proof={"status":"PASS","day":day,"scientific_claim":"PRIMARY_MINIMUM_TEMPORAL_INTERVENTION_ONLY",
        "primary_optimum_GPU_slots":PRIMARY[day],"primary_certificate_reused":cert,
        "secondary_changed_job_global_optimality_required":False,"tertiary_delay_global_optimality_required":False,
        "H_schedule_SHA256":sha256_file(hday/"V39H_SHADOW_SCHEDULE.parquet"),
        "H_objective_certificate_SHA256":sha256_file(hday/"V39H_OBJECTIVE_CERTIFICATES.json"),
        "H_grid_audit_SHA256":sha256_file(hday/"V39H_GRID_MARGIN_AUDIT.json"),"frozen_input_SHA256":inputs,
        "production_temporal_schedule_SHA256":sha256_file(temporal_path),"independent_schedule_grid_audit":audit,
        "production_planning_verifier":planning,"rack_labels":rack,"safe_reservation_GPU_slots_before":before_slots,
        "safe_reservation_GPU_slots_after":after_slots,"safe_seconds_per_job_unchanged":True,"job_set_unchanged":True,
        "GPU_requests_unchanged":True,"RW_completion_noninferiority_PASS":True,"new_RW_completion_violations":0,
        "changed_jobs":int(b.start_delay_slots.gt(0).sum()),"max_added_delay_min":int(b.start_delay_slots.max())*15,
        "max_added_delay_is_not_a_service_SLA":True,"site_to_aggregate_IT_power_max_error_kW":str(max_power_error),
        "C1_PCC_vs_H_lookup_max_error_kW":float(np.abs(matrix-expected_pcc).max()),
        "accepted_grid_domain_issue_slots":[24,120],"outside_domain_site_grid_physical_claim":False,
        "primary_optimization_calls":0,"migration_MILP_calls":0,"Actual_result_reads_during_DA_construction":0,"Fresh_result_reads_during_DA_construction":0}
    atomic_json(out/"SELECTIVE_PREFLIGHT_CERTIFICATE.json",proof)
    zero_migration={"status":"PASS","WAN_transfer_count":0,"checkpoint_transfer_count":0,"restart_count":0,"WAN_transfer_slots_used":0}
    reference=read(root/"before_refreeze"/f"V39E_DAYAHEAD_DECISION_FREEZE_{day}_B0.json")["decision"]
    for case in ("B1","B3"):
        decision=deepcopy(reference)
        decision.update(status="PASS",case=case,temporal_mode="RSP",temporal_schedule_SHA256=sha256_file(temporal_path),
            temporal_schedule=_frame_records(temporal),AIDC_assignments=assignments,migration_state=zero_migration,
            site_GPU_trajectory=_frame_records(gpu),site_IT_power_trajectory=_frame_records(it),site_PCC_power_trajectory=_frame_records(pcc),
            planning_feasibility=planning,Fresh_used_as_DA_decision_oracle=False,MESS_feedback_to_AIDC=0,
            temporal_repair_authority={"policy":"BASE_RSP_THEN_PRIMARY_OPTIMAL_STANDBY_TEMPORAL_REPAIR_THEN_ORIGINAL_RSP_MINIMUM_MIGRATION",
                "base_RSP_planning_status":"FAIL","temporal_repair_status":"PASS","primary_optimum_GPU_slots":PRIMARY[day],
                "secondary_tertiary_global_optimality_claim":False,"certificate_path":str((out/"SELECTIVE_PREFLIGHT_CERTIFICATE.json").relative_to(repo)),
                "certificate_SHA256":sha256_file(out/"SELECTIVE_PREFLIGHT_CERTIFICATE.json"),
                "temporal_schedule_authority_path":str(temporal_path.relative_to(repo)),"new_maximum_delay_SLA_or_deadline":None})
        freeze,digest=_freeze(out/f"V39E_DAYAHEAD_DECISION_FREEZE_{day}_{case}.json",decision)
        assert validate_actual_fixed_replay(freeze,digest)["status"]=="PASS"
    return {"day":day,"status":"PASS","Vmax":audit["grid"]["Vmax"],"primary_optimum":PRIMARY[day],"optimization_calls":0}


def selective_preflight(repo):
    root=repo/CLOSE_ROOT;results=[]
    with ProcessPoolExecutor(max_workers=4) as pool:
        futures={pool.submit(materialize_day_limited,str(repo),day):day for day in CHANGED_DAYS}
        for future in as_completed(futures):
            result=future.result();results.append(result)
            atomic_json(root/"PRODUCTION_CLOSE_PROGRESS.json",{"phase":"SELECTIVE_PREFLIGHT","completed":results,
                "changed_day_count":5,"primary_optimization_calls":0,"migration_MILP_calls":0})
            print("SELECTIVE_PREFLIGHT_PASS",result,flush=True)
    atomic_json(root/"SELECTIVE_PREFLIGHT_SUMMARY.json",{"status":"PASS","dates":sorted(results,key=lambda r:r["day"]),
        "expensive_optimization_calls":0,"changed_DA_dates_only":True,"full_31_day_preflight_rerun":False})


def materialize_day_limited(repo_text,day):
    with threadpool_limits(limits=4):return materialize_day(repo_text,day)


def audit_earlier_result_reuse(repo):
    """Post-construction reuse audit, separated from the D-1 construction worker."""
    from .campaign_adapter import configure_v37_runner, build_day
    runner=configure_v37_runner();root=repo/CLOSE_ROOT;state=read(root/"PRODUCTION_CLOSE_START_STATE.json")
    old_preflight=read(root/"before_refreeze/V39E_FULL_PREFLIGHT.json")
    rows=[];protected={}
    for day in MAY01_05:
        previous=next(r for r in old_preflight["days"] if r["operating_day"]==day)
        assert previous["status"]=="READY" and previous["RSP_temporal"]=="PASS" and previous["migration_escalation"]=="NOT_NEEDED"
        result_path=repo/FULL_ROOT/"dates"/f"{day}.json"
        cert_path=repo/FULL_ROOT/"certificates"/f"V39E_MAY_DAY_CERTIFICATE_{day}.json"
        cert=read(cert_path);result=read(result_path)
        assert cert["status"]==result["status"]=="PASS" and cert["terminal"] and cert["case_count"]==4
        assert result["Fresh_96_of_96_PASS"] and result["physical_gates_PASS"]
        assert cert["result_file_SHA256"]==sha256_file(result_path)
        paths=[result_path,cert_path];case_rows=[];freeze_shas={}
        for case in CASES:
            name=f"V39E_DAYAHEAD_DECISION_FREEZE_{day}_{case}.json";path=repo/FULL_ROOT/name
            assert sha256_file(path)==state["before_refreeze_SHA256"][name]==cert["DA_freeze_file_SHA256"][case]
            freeze_shas[case]=sha256_file(path);paths.append(path)
            replay_case={"B2":"B0","B3":"B1"}.get(case,case)
            if replay_case!=case:
                paired=read(repo/FULL_ROOT/f"V39E_DAYAHEAD_DECISION_FREEZE_{day}_{replay_case}.json")["decision"]
                own=read(path)["decision"]
                assert canonical_sha256({k:v for k,v in paired.items() if k!="case"})==canonical_sha256({k:v for k,v in own.items() if k!="case"})
            # Match the accepted runner exactly: B2 shares B0's trajectory
            # object/DA fingerprint, and B3 shares B1's; only the MESS case differs.
            trajectory=build_day(repo,day,replay_case)
            fp=runner.case_execution_fingerprint(repo,day,case,trajectory)
            cached=runner._valid_case_checkpoint(repo,day,case,fp)
            assert cached is not None,f"NO_EXACT_COMPLETED_CASE_CHECKPOINT:{day}:{case}"
            checkpoint=runner._checkpoint_path(repo,day,case);payload=read(checkpoint);paths.append(checkpoint)
            case_root=runner._case_root(repo,day,case)
            paths.extend(case_root/f["relative_path"] for f in payload["files"])
            case_rows.append({"case":case,"execution_fingerprint_sha256":fp["execution_fingerprint_sha256"],
                "production_replay_trajectory_case":replay_case,
                "checkpoint_SHA256":sha256_file(checkpoint),"exact_checkpoint_and_all_file_SHA_match":True,
                "DA_byte_equivalent":True,"temporal_repair_calls":0,"migration_calls":0,
                "Actual_Fresh_replay_semantics_unchanged":True})
        for path in paths:
            st=path.stat();protected[str(path.relative_to(repo))]={"SHA256":sha256_file(path),"size":st.st_size,"mtime_ns":st.st_mtime_ns}
        rows.append({"day":day,"status":"PASS","MAY01_05_REUSE":"YES","cases":case_rows,
            "old_campaign_classification":cert["campaign_classification"],"target_campaign_classification":"AUTHORITATIVE_V39E_MAY_CAMPAIGN",
            "original_certificate_SHA256":sha256_file(cert_path),"original_result_SHA256":sha256_file(result_path),"DA_freeze_file_SHA256":freeze_shas,
            "original_result_and_certificate_files_modified":False,"new_runtime_only_Threads_4_invalidates_historical_exact_results":False})
        print("MAY01_05_EXACT_REUSE_PASS",day,flush=True)
    result={"status":"PASS","MAY01_05_REUSE":"YES","days":rows,"protected_files":protected,
        "audit_phase":"POST_DA_CONSTRUCTION_REUSE_EQUIVALENCE_ONLY","no_Actual_Fresh_result_used_to_select_DA":True,
        "source_replay_adapter_unchanged":sha256_file(repo/"dayahead/v39e/campaign_adapter.py")==state["production_source_SHA256"]["dayahead/v39e/campaign_adapter.py"],
        "no_May01_05_execution_or_result_rewrite":True}
    assert result["source_replay_adapter_unchanged"]
    atomic_json(root/"MAY01_05_REUSE_EQUIVALENCE.json",result);return result


def equivalent_completed_day(repo,day,classification):
    if day not in MAY01_05 or classification!="AUTHORITATIVE_V39E_MAY_CAMPAIGN":return False
    root=repo/CLOSE_ROOT;path=root/"MAY01_05_REUSE_EQUIVALENCE.json";authority_path=root/"PRODUCTION_REFREEZE_AUTHORITY.json"
    if not path.exists() or not authority_path.exists():return False
    try:
        authority=read(authority_path);reuse=read(path)
        if authority.get("status")!="PASS" or authority.get("MAY01_05_reuse_certificate_SHA256")!=sha256_file(path):return False
        row=next(r for r in reuse["days"] if r["day"]==day)
        return (row["status"]=="PASS" and row["original_result_SHA256"]==sha256_file(repo/FULL_ROOT/"dates"/f"{day}.json")
            and row["original_certificate_SHA256"]==sha256_file(repo/FULL_ROOT/"certificates"/f"V39E_MAY_DAY_CERTIFICATE_{day}.json")
            and all(row["DA_freeze_file_SHA256"][case]==sha256_file(repo/FULL_ROOT/f"V39E_DAYAHEAD_DECISION_FREEZE_{day}_{case}.json") for case in CASES))
    except (KeyError,ValueError,OSError,StopIteration):return False


def assert_protected_results(repo):
    audit=read(repo/CLOSE_ROOT/"MAY01_05_REUSE_EQUIVALENCE.json")
    for name,info in audit["protected_files"].items():
        path=repo/name;st=path.stat()
        assert st.st_size==info["size"] and st.st_mtime_ns==info["mtime_ns"] and sha256_file(path)==info["SHA256"],name
    return len(audit["protected_files"])


def commit_refreeze(repo):
    """Commit only ten staged DA artifacts; original files remain backed up."""
    root=repo/CLOSE_ROOT;state=read(root/"PRODUCTION_CLOSE_START_STATE.json")
    assert read(root/"SELECTIVE_PREFLIGHT_SUMMARY.json")["status"]=="PASS"
    assert read(root/"MAY01_05_REUSE_EQUIVALENCE.json")["status"]=="PASS"
    hmanifest=state["V39H_required_SHA256"]
    assert all(sha256_file(repo/H_ROOT/name)==sha for name,sha in hmanifest.items())
    old=read(root/"before_refreeze/V39E_FULL_PREFLIGHT.json")
    in_progress={**old,"status":"FAIL_CLOSED","MAY_CAMPAIGN_LAUNCH_READY":"NO","first_blocker":"ATOMIC_PRODUCTION_REFREEZE_ASSEMBLY"}
    atomic_json(repo/FULL_ROOT/"V39E_FULL_PREFLIGHT.json",in_progress)
    for day in CHANGED_DAYS:
        for case in ("B1","B3"):
            name=f"V39E_DAYAHEAD_DECISION_FREEZE_{day}_{case}.json";source=root/"days"/day/name;destination=repo/FULL_ROOT/name
            data=read(source);assert canonical_sha256(data["decision"])==data["DA_decision_SHA256"]
            atomic_json(destination,data)
            assert sha256_file(source)==sha256_file(destination)
    for suffix,field in (("GPU","site_GPU_trajectory"),("IT_POWER","site_IT_power_trajectory"),("PCC_POWER","site_PCC_power_trajectory")):
        # Preserve the existing filename capitalization.
        name={"GPU":"V39E_SITE_GPU_TRAJECTORIES.parquet","IT_POWER":"V39E_SITE_IT_POWER_TRAJECTORIES.parquet","PCC_POWER":"V39E_SITE_PCC_POWER_TRAJECTORIES.parquet"}[suffix]
        old_frame=pd.read_parquet(root/"before_refreeze"/name)
        keep=~(old_frame.operating_day.isin(CHANGED_DAYS)&old_frame["case"].isin(("B1","B3")))
        frames=[old_frame.loc[keep].copy()]
        for day in CHANGED_DAYS:
            for case in ("B1","B3"):
                frame=pd.DataFrame(read(repo/FULL_ROOT/f"V39E_DAYAHEAD_DECISION_FREEZE_{day}_{case}.json")["decision"][field]);frame["case"]=case;frames.append(frame)
        combined=pd.concat(frames,ignore_index=True).sort_values(["operating_day","case","slot","AIDC"]).reset_index(drop=True)
        assert len(combined)==31*4*96*12
        temporary=repo/FULL_ROOT/(name+".refreeze.tmp");combined.to_parquet(temporary,index=False);temporary.replace(repo/FULL_ROOT/name)
    inputs,fingerprint=source_fingerprint(repo)
    preflight=deepcopy(old);rows=[];identity={};replays=[];routes=[];da_files={};migration_total=0;reuse_count=0;migration_reuse=[]
    for day in EXPECTED_DATES:
        previous=next(r for r in old["days"] if r["operating_day"]==day)
        row=deepcopy(previous)
        hpath=repo/H_ROOT/"days"/day/"V39H_SHADOW_A_RESULT.json"
        hresult=read(hpath) if hpath.exists() else None
        is_changed=day in CHANGED_DAYS
        if is_changed:
            row.update(status="READY",RSP_temporal="PASS",RSP_base_planning="FAIL",RSP_temporal_repair="PASS",
                migration_escalation="NOT_NEEDED",DA_freeze="PASS",Actual_fixed_replay_loader="PASS",exact_blocker=None)
        else:
            assert previous["status"]=="READY"
            row.update(RSP_base_planning=previous["RSP_temporal"],RSP_temporal_repair="INFEASIBLE" if hresult else "NOT_REQUIRED",
                DA_reused_byte_identical=True)
        rows.append(row);identity[day]={}
        for case in CASES:
            name=f"V39E_DAYAHEAD_DECISION_FREEZE_{day}_{case}.json";path=repo/FULL_ROOT/name
            freeze=read(path);decision=freeze["decision"]
            assert decision["status"]=="PASS" and canonical_sha256(decision)==freeze["DA_decision_SHA256"]
            if not is_changed or case in ("B0","B2"):
                assert sha256_file(path)==state["before_refreeze_SHA256"][name];reuse_count+=1
            da_files[name]=sha256_file(path)
            identity[day][case]=canonical_sha256({"assignments":decision["AIDC_assignments"],"gpu":decision["site_GPU_trajectory"]})
            assert validate_actual_fixed_replay(freeze,freeze["DA_decision_SHA256"])["status"]=="PASS"
            replays.append({"operating_day":day,"case":case,"status":"PASS","DA_freeze_SHA256":freeze["DA_decision_SHA256"],
                "DA_freeze_SHA_verified_before_replay":True,"Actual_temporal_reoptimization_calls":0,"Actual_AIDC_reoptimization_calls":0,
                "Actual_migration_reoptimization_calls":0,"Actual_WAN_reroute_calls":0})
        rsp=read(repo/FULL_ROOT/f"V39E_DAYAHEAD_DECISION_FREEZE_{day}_B1.json")["decision"]
        count=sum(bool(r.get("migration_selected")) for r in rsp["AIDC_assignments"]);migration_total+=count
        assert count==rsp["migration_state"]["WAN_transfer_count"]
        if hresult and not is_changed:
            proof=read(repo/H_ROOT/"days"/day/"V39H_EXISTING_MIGRATION_CONFIRMATION.json")
            assert count==proof["solver_proven_minimum_migrations"] and proof["original_frozen_RSP_starts_ends_exact"]
            preserved_sources={}
            for p,sha in proof["source_SHA256"].items():
                path=Path(p);backup=root/"before_refreeze"/path.name
                if backup.exists() and sha256_file(backup)==sha:resolved=backup
                else:resolved=path
                assert sha256_file(resolved)==sha
                preserved_sources[str(resolved.relative_to(repo))]=sha
            base_path=repo/f"dayahead/artifacts/v37_r4a_per_day_aidc/days/{day}/V37_R4A_RSP_SCHEDULE.parquet"
            assert rsp["temporal_schedule_SHA256"]==sha256_file(base_path)
            migration_reuse.append({"day":day,"status":"PASS","minimum_RUNNING_migrations":count,
                "original_base_RSP_schedule_SHA256":sha256_file(base_path),"preserved_solver_proof_sources_SHA256":preserved_sources,
                "production_B1_DA_file_SHA256":da_files[f"V39E_DAYAHEAD_DECISION_FREEZE_{day}_B1.json"],
                "H_confirmation_SHA256":sha256_file(repo/H_ROOT/"days"/day/"V39H_EXISTING_MIGRATION_CONFIRMATION.json"),
                "partial_infeasible_repair_passed_to_migration":False,"new_migration_MILP_calls":0})
        routes.append({"operating_day":day,"base_RSP_status":previous["RSP_temporal"],"temporal_only_status":"PASS" if count==0 else "FAIL",
            "temporal_repair_status":"PASS" if is_changed else "INFEASIBLE" if hresult else "NOT_REQUIRED",
            "solver_proven_minimum_RUNNING_migrations":count,"migration_solver_calls":0,"temporal_solver_calls":0,
            "saved_primary_certificate_reused":is_changed,"saved_migration_certificate_reused":count>0,
            "original_base_RSP_retained_before_migration":count>0,"final_status":"PASS"})
    assert reuse_count==114 and migration_total==76 and sum(r["solver_proven_minimum_RUNNING_migrations"]>0 for r in routes)==8
    atomic_json(root/"MIGRATION_REUSE_EQUIVALENCE.json",{"status":"PASS","days":migration_reuse,"minimum_migrations":76,"new_migration_MILP_calls":0})
    assert all(x["B0"]==x["B2"] and x["B1"]==x["B3"] for x in identity.values())
    atomic_json(repo/FULL_ROOT/"V39E_B0_B3_IDENTITY_AUDIT.json",{"artifact_id":"V39E_B0_B3_IDENTITY_AUDIT_V1","status":"PASS",
        "B0_equals_B2_AIDC_schedule":True,"B1_equals_B3_AIDC_schedule":True,"B0_B1_B2_B3_initial_state_identity":True,"MESS_feedback_to_AIDC_count":0,"days":identity})
    atomic_json(repo/FULL_ROOT/"V39E_ACTUAL_FIXED_REPLAY_AUDIT.json",{"artifact_id":"V39E_ACTUAL_FIXED_REPLAY_AUDIT_V1","status":"PASS","cases":replays,
        "Actual_temporal_reoptimization_calls":0,"Actual_AIDC_reoptimization_calls":0,"Actual_migration_reoptimization_calls":0,"Actual_WAN_reroute_calls":0})
    atomic_json(repo/FULL_ROOT/"V39E_TEMPORAL_FIRST_MIGRATION_AUDIT.json",{"artifact_id":"V39E_V39H_TEMPORAL_FIRST_MIGRATION_AUDIT_V1","status":"PASS",
        "temporal_only_days":23,"migration_escalated_days":8,"solver_proven_migration_count":76,"unnecessary_migration_count":0,
        "new_migration_solver_calls":0,"new_temporal_primary_solver_calls":0,"days":routes})
    power=read(root/"before_refreeze/V39E_POWER_CONSERVATION_AUDIT.json")
    power.update(status="PASS",site_GPU_rows=31*4*96*12,site_IT_power_rows=31*4*96*12,site_PCC_power_rows=31*4*96*12,
        expected_rows=31*4*96*12,site_capacity_violations=0,verification="114 unchanged case-authorities plus 10 independently verified temporal-repair case-authorities")
    atomic_json(repo/FULL_ROOT/"V39E_POWER_CONSERVATION_AUDIT.json",power)
    preflight.update(status="PASS",READY=31,NOT_READY=0,missing=0,V39E_READY="YES",MAY_CAMPAIGN_LAUNCH_READY="YES",
        PRECHECK_BYPASSED="NO",MAY_STARTED="NO",first_blocker=None,days=rows,implementation_fingerprint_inputs=inputs,
        final_implementation_fingerprint_sha256=fingerprint,assembly_mode="SELECTIVE_V39H_PRIMARY_REPAIR_REFREEZE_PLUS_EQUIVALENCE_REUSE",
        full_31_day_optimization_calls=0,selective_preflight_dates=list(CHANGED_DAYS),unchanged_DA_case_authorities_reused=114)
    atomic_json(repo/FULL_ROOT/"V39E_FULL_PREFLIGHT.json",preflight)
    authority={"status":"PASS","policy":"BASE_RSP_GRID_THEN_STANDBY_PRIMARY_MINIMUM_INTERVENTION_THEN_UNCHANGED_BASE_RSP_EXACT_MINIMUM_MIGRATION",
        "DA_freeze_file_SHA256":da_files,"production_preflight_SHA256":sha256_file(repo/FULL_ROOT/"V39E_FULL_PREFLIGHT.json"),
        "MAY01_05_reuse_certificate_SHA256":sha256_file(root/"MAY01_05_REUSE_EQUIVALENCE.json"),
        "selective_preflight_certificate_SHA256":{day:sha256_file(root/"days"/day/"SELECTIVE_PREFLIGHT_CERTIFICATE.json") for day in CHANGED_DAYS},
        "implementation_fingerprint_sha256":fingerprint,"primary_optimality_is_only_temporal_optimization_claim":True,
        "new_service_SLA_or_deadline":None,"V39I_dependency":False,"full_31_day_optimization_rerun":False,
        "MAX_PARALLEL_DAY_WORKERS":4,"GUROBI_THREADS_PER_MODEL":4,"RUNNING_migration_days":8,"minimum_RUNNING_migrations":76}
    atomic_json(root/"PRODUCTION_REFREEZE_AUTHORITY.json",authority)
    assert_protected_results(repo)
    return load_ready_refreeze(repo)


def load_ready_refreeze(repo,progress=None):
    """Cheap authority/loader/provenance assembly only; never optimize."""
    from .campaign_adapter import build_day
    root=repo/CLOSE_ROOT;authority=read(root/"PRODUCTION_REFREEZE_AUTHORITY.json")
    preflight_path=repo/FULL_ROOT/"V39E_FULL_PREFLIGHT.json";preflight=read(preflight_path)
    assert authority["status"]=="PASS" and sha256_file(preflight_path)==authority["production_preflight_SHA256"]
    inputs,fingerprint=source_fingerprint(repo)
    assert inputs==preflight["implementation_fingerprint_inputs"] and fingerprint==authority["implementation_fingerprint_sha256"]
    assert read(root/"MAY01_05_REUSE_EQUIVALENCE.json")["status"]=="PASS"
    rows=[]
    for day in EXPECTED_DATES:
        for case in CASES:
            name=f"V39E_DAYAHEAD_DECISION_FREEZE_{day}_{case}.json";path=repo/FULL_ROOT/name;freeze=read(path)
            assert sha256_file(path)==authority["DA_freeze_file_SHA256"][name]
            assert freeze["decision"]["status"]=="PASS" and canonical_sha256(freeze["decision"])==freeze["DA_decision_SHA256"]
            trajectory=build_day(repo,day,case)
            assert trajectory.pcc_p_kw.shape==(96,12) and np.isfinite(trajectory.pcc_p_kw).all()
            assert trajectory.fingerprints["V39E_DA_decision_SHA256"]==freeze["DA_decision_SHA256"]
            if day in CHANGED_DAYS and case in ("B1","B3"):
                binding=freeze["decision"]["temporal_repair_authority"]
                assert sha256_file(repo/binding["certificate_path"])==binding["certificate_SHA256"]
                assert sha256_file(repo/binding["temporal_schedule_authority_path"])==freeze["decision"]["temporal_schedule_SHA256"]
        rows.append({"day":day,"status":"READY","four_DA_authorities_SHA_and_loader_PASS":True})
    assert _fresh_loader_audit(repo)["status"]=="PASS"
    assert len(rows)==31 and preflight["READY"]==31 and preflight["NOT_READY"]==preflight["missing"]==0
    readiness={"status":"PASS","READY":31,"NOT_READY":0,"MISSING":0,"rows":rows,"optimization_calls":0,
        "method":"SHA_AUTHORITY_LOADER_CERTIFICATE_PROVENANCE_ASSEMBLY_ONLY","V39I_dependency":False,
        "production_authority_SHA256":sha256_file(root/"PRODUCTION_REFREEZE_AUTHORITY.json")}
    atomic_json(root/"CHEAP_31_DAY_READINESS.json",readiness)
    if progress is not None:progress.update(phase="PREFLIGHT",preflight_READY=31,preflight_NOT_READY=0,preflight_missing=0,exact_current_blocker=None)
    return preflight
