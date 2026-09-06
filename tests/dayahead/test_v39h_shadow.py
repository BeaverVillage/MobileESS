"""Exactness and user-prescreen guardrail tests; no production runs."""
import itertools
import math
from pathlib import Path
import numpy as np
import pandas as pd
from dayahead.tools import run_v39h_shadow as h
from dayahead.v38.authority import CapacityAuthority,RackPool

def toy_cap():
    return CapacityAuthority(site_capacity={"AIDC01":4,"AIDC02":4},historical_site_capacity={"AIDC01":4.,"AIDC02":4.},rack_pools=(RackPool("AIDC01","R1",4.),RackPool("AIDC02","R2",4.)),source_sha256="toy")

def toy_rows(rows):
    return pd.DataFrame([dict(job_uid=uid,state_at_issue=state,initial_AIDC=site,requested_gpus=g,RSP_duration_slots=2,RSP_scheduled_start=24,latest_start=26 if eligible else 24,eligible=eligible) for uid,state,site,g,eligible in rows])

def test_no_extra_dates_and_four_by_four():
    assert len(h.DAYS)==13 and sum(x or 0 for x in h.BASE_COUNTS.values())==105
    assert h.MAX_PARALLEL_DAY_WORKERS*h.GUROBI_THREADS_PER_MODEL==16
    assert not set(h.DAYS)&{f"2025-05-{i:02d}" for i in range(1,6)}

def test_all_dates_universal_eligibility_and_frozen_pending_site_freedom():
    for day in h.DAYS:
        a,_,_=h.inputs(day)
        assert a.eligible.equals(h.v39g.eligible_mask(a))
        assert a.loc[a.state_at_issue.eq("PENDING"),"initial_AIDC"].eq("").all()
        assert a.loc[~a.eligible,"latest_start"].eq(a.loc[~a.eligible,"RSP_scheduled_start"]).all()
        assert (a.loc[a.eligible,"latest_start"]+a.loc[a.eligible,"RSP_duration_slots"]<=a.loc[a.eligible,"RW_scheduled_completion"]).all()

def test_event_recurrence_equals_complete_direct_occupancy():
    for intervals in itertools.product([(0,2,1),(2,4,2),(1,6,4)],repeat=3):
        direct=np.zeros(10,int);events=np.zeros(11,int)
        for start,d,g in intervals:
            direct[start:start+d]+=g;events[start]+=g;events[start+d]-=g
        assert np.array_equal(direct,np.cumsum(events)[:10])

def test_objective_is_exact_V39G_complete_interval_rule():
    for start,d,delay,g in itertools.product((0,100,120),(1,25,150),(0,1,50,200),(1,4)):
        original=set(range(start,start+d));new=set(range(start+delay,start+delay+d))
        assert h.v39g.occupancy_cost(start,d,start+delay,g)==g*len(original^new)

def test_outside_domain_site_elimination_preserves_all_times():
    c={"lo":0,"hi":130,"d":5};sites=("AIDC01","AIDC02")
    options=list(h.candidate_options(c,sites))
    assert {s for site,s in options}==set(range(131))
    for t in range(131):assert [site for site,s in options if s==t]==list(sites if t<120 and t+5>24 else sites[:1])

def test_fixed_voltage_fail_is_not_prescreen_infeasibility(tmp_path,monkeypatch):
    monkeypatch.setattr(h,"_load_capacity",lambda _: (toy_cap(),{}))
    def forbidden(*args,**kwargs):raise AssertionError("Voltage must never be evaluated in resource-only prescreen")
    monkeypatch.setattr(h.grid,"evaluate",forbidden);monkeypatch.setattr(h.grid,"inequalities",forbidden)
    a=toy_rows([("r","RUNNING","AIDC01",4,False),("n","PENDING","",4,False),("s","PENDING","",1,True)])
    r=h.capacity_relaxation(a,tmp_path)
    assert r["status"]=="OPTIMAL" and not r["planning_voltage_used_in_prescreen"]
    assert r["PENDING_initial_sites_remain_free"]  # normal must use AIDC02

def test_irrecoverable_capacity_IIS_allows_skip(tmp_path,monkeypatch):
    monkeypatch.setattr(h,"_load_capacity",lambda _: (toy_cap(),{}))
    a=toy_rows([("r1","RUNNING","AIDC01",3,False),("r2","RUNNING","AIDC02",1,False),("n1","PENDING","",2,False),("n2","PENDING","",2,False),("s","PENDING","",1,True)])
    r=h.capacity_relaxation(a,tmp_path)
    assert r["status"]=="INFEASIBLE"
    audit=h.read(tmp_path/"V39H_SHADOW_A_IIS_SUMMARY.json")
    assert audit["full_shadow_infeasibility_proven"] and audit["IIS_minimal"]
    assert not any("voltage" in n for n in audit["constraints"])

def test_atomic_progress_and_day_isolation(tmp_path):
    for day in h.DAYS[:2]:h.atomic(tmp_path/day/"progress.json",{"day":day,"resumable":True})
    assert h.read(tmp_path/h.DAYS[0]/"progress.json")["day"]==h.DAYS[0]
    assert h.read(tmp_path/h.DAYS[1]/"progress.json")["day"]==h.DAYS[1]
    assert not list(tmp_path.rglob("*.tmp"))

def test_final_results_work_no_migration_and_optimality():
    for day in h.DAYS:
        path=h.ROOT/"days"/day/"V39H_SHADOW_A_RESULT.json"
        assert path.exists(),f"Final evidence missing: {day}"
        r=h.read(path);w=h.read(path.parent/"V39H_WORK_PRESERVATION_AUDIT.json")
        assert r["RW_completion_noninferiority_violations"]==0
        assert w["safe_duration_slots_equal"] and w["GPU_requests_equal"] and w["safe_seconds_equal"]
        if r["temporal_repair_sufficient"]:
            assert r["post_candidate_migration_count"]==0 and r["RUNNING_migration_calls_in_temporal_shadow"]==0
            assert r["audit"]["all_hard_constraints_pass"]
            # Exact integer-bound proof, not a floating equality/tolerance:
            # May24's saved 107.9999999999996 bound rules out every integer <108.
            assert all(x["optimal"] and x["gap"]==0 and x["objective"]==math.ceil(x["bound"]) for x in r["stages"])
            if r.get("fast_close_primary_only"):
                assert day in ("2025-05-25","2025-05-26")
                assert r["shadow_status"]=="PRIMARY_OPTIMAL_FEASIBLE" and not r["exact_full_lex"]
                expected=29568 if day=="2025-05-25" else 13086
                assert r["PRIMARY_TEMPORAL_INTERVENTION_OPTIMAL"]=="YES"
                assert r["stages"][1]["objective"]==r["symmetric_occupancy_deviation_GPU_slots"]==expected
                assert all(s["status"]==11 and not s["optimal"] for s in r["interrupted_tie_break_stages"])
                assert r["SECONDARY_CHANGED_JOB_OPTIMALITY"]==("BEST_FEASIBLE_NOT_GLOBALLY_CERTIFIED" if day=="2025-05-25" else "YES")
                assert r["TERTIARY_DELAY_OPTIMALITY"]==("NOT_REQUIRED" if day=="2025-05-25" else "BEST_FEASIBLE_NOT_GLOBALLY_CERTIFIED")
                if day=="2025-05-26":assert r["changed_jobs"]==r["stages"][2]["objective"]==8
                cert=h.read(path.parent/"V39H_FAST_CLOSE_WITNESS_CERTIFICATE.json")
                assert cert["independent_verifier_pass"] and cert["new_optimization_calls"]==0
                assert cert["newly_introduced_RW_completion_violations"]==0
                assert h.grid.sha(path.parent/"V39H_SHADOW_SCHEDULE.parquet")==cert["final_schedule_SHA256"]
                assert r["Vmax"]<=1.05 and r["Vmin"]>=.95
            else:assert h.read(path.parent/"V39H_EXACT_LEX_CERTIFICATES.json")["all_stages_optimal"]
        else:
            confirm=h.read(path.parent/"V39H_EXISTING_MIGRATION_CONFIRMATION.json")
            assert confirm["current_migration_solver_calls"]==0 and confirm["original_frozen_RSP_starts_ends_exact"]
            reuse=h.read(path.parent/"V39H_MIGRATION_SHA_MODEL_AUTHORITY_EQUIVALENCE.json")
            assert reuse["status"]=="PASS" and reuse["new_optimization_calls"]==0
            assert reuse["original_base_RSP_file_SHA_verified"]

def test_saved_migration_equivalence_cannot_call_solver(tmp_path,monkeypatch):
    from dayahead.tools import v39h_shadow_report as report
    monkeypatch.setattr(h,"ROOT",tmp_path)
    def forbidden(*args,**kwargs):raise AssertionError("Migration reuse must not construct an optimization model")
    monkeypatch.setattr(h.gp,"Model",forbidden)
    result=report.migration_authority_equivalence("2025-05-06")
    assert result["status"]=="PASS" and result["new_optimization_calls"]==0
    assert result["B1_B3_DA_and_migration_identity"]

def test_may06_full_option_IIS_is_not_fixed_only_voltage_screen():
    out=h.ROOT/"days/2025-05-06"
    proof=h.read(out/"V39H_SHADOW_A_IIS_SUMMARY.json")
    assert proof["all_eligible_temporal_options_retained"]
    assert proof["full_shadow_infeasibility_proven"] and proof["IIS_minimal"]
    assert not proof["fixed_only_voltage_screen"]
    assert h.grid.sha(out/"V39H_SHADOW_A_IIS.ilp")==h.grid.sha(out/"full_option_LP_IIS/V39H_SHADOW_A_IIS.ilp")

def test_completed_grid_witness_reuse_is_bound_to_schedule(tmp_path,monkeypatch):
    import shutil
    import pytest
    from dayahead.tools import v39h_shadow_report as report
    day="2025-05-24";source=h.ROOT;out=tmp_path/"days"/day;out.mkdir(parents=True)
    shutil.copy2(source/"V39H_PRE_ASSEMBLY_FORMULATION_SHA.json",tmp_path)
    for name in ("V39H_INPUT_AUTHORITY.json","V39H_SHADOW_A_RESULT.json","V39H_SHADOW_SCHEDULE.parquet","V39H_EXACT_LEX_CERTIFICATES.json","V39H_OBJECTIVE_CERTIFICATES.json","V39G_C1_INTEGER_TABLES.npz","V39H_WITNESS.npz","V39H_DAY_PROGRESS.json"):
        shutil.copy2(source/"days"/day/name,out/name)
    monkeypatch.setattr(h,"ROOT",tmp_path)
    def forbidden(*args,**kwargs):raise AssertionError("Matching completed grid witness must not recompute grid coefficients")
    monkeypatch.setattr(h.grid,"load_coefficients",forbidden)
    report.assemble_day(day)
    assert h.read(out/"V39H_SHADOW_A_RESULT.json")["completed_independent_grid_audit_reused_same_witness"]
    b=pd.read_parquet(out/"V39H_SHADOW_SCHEDULE.parquet")
    index=b.index[b.scheduled_start_slot.lt(120)&b.scheduled_end_slot.gt(24)][0]
    b.loc[index,"AIDC"]="AIDC02" if b.loc[index,"AIDC"]=="AIDC01" else "AIDC01"
    b.to_parquet(out/"V39H_SHADOW_SCHEDULE.parquet",index=False)
    with pytest.raises((AssertionError,IndexError)):
        report.assemble_day(day)

def test_generic_may17_reproduces_V39G_without_special_rules():
    path=h.ROOT/"days/2025-05-17/V39H_SHADOW_SCHEDULE.parquet"
    if not path.exists():return
    got=pd.read_parquet(path);ref=pd.read_parquet(h.v39g.OUT/"V39G_MAY17_SHADOW_A_SCHEDULE.parquet")
    cols=["job_uid","AIDC","scheduled_start_slot","scheduled_end_slot","duration_slots"]
    assert np.array_equal(got[cols],ref[cols])
    result=h.read(path.parent/"V39H_SHADOW_A_RESULT.json")
    assert result["changed_jobs"]==62 and abs(result["Vmax"]-1.0499957352951175)<1e-12

def test_existing_sources_and_old_artifacts_not_mutated():
    start=h.read(h.ROOT/"V39H_START_STATE.json")
    assert start["production_source_SHA256"]==h.v39g.source_hashes()
    assert start["preserved_artifact_metadata"]==h.preserved_metadata()
