"""Authorized V39H production refreeze, selective preflight and May resume."""
from __future__ import annotations
import argparse
import io
from pathlib import Path
import shutil
import sys
import unittest
REPO=Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:sys.path.insert(0,str(REPO))
from dayahead.tools import run_v39h_shadow as h
from dayahead.v38.authority import canonical_sha256

ROOT=REPO/"dayahead/artifacts/v39h_production_refreeze_may_close"


def initialize():
    ROOT.mkdir(parents=True,exist_ok=True);state_path=ROOT/"PRODUCTION_CLOSE_START_STATE.json"
    if state_path.exists():return h.read(state_path)
    final=h.read(h.ROOT/"V39H_FINAL_STATUS.json");assert final["V39H_DIAGNOSTIC_COMPLETE"]=="YES"
    source_manifest=h.read(h.ROOT/"V39H_REQUIRED_ARTIFACT_SHA_MANIFEST.json")["SHA256"]
    assert all(h.grid.sha(h.ROOT/p)==sha for p,sha in source_manifest.items())
    selected=list(h.BASE.glob("V39E_DAYAHEAD_DECISION_FREEZE_*.json"))
    selected.extend(h.BASE/name for name in ("V39E_FULL_PREFLIGHT.json","V39E_SITE_GPU_TRAJECTORIES.parquet",
        "V39E_SITE_IT_POWER_TRAJECTORIES.parquet","V39E_SITE_PCC_POWER_TRAJECTORIES.parquet",
        "V39E_B0_B3_IDENTITY_AUDIT.json","V39E_ACTUAL_FIXED_REPLAY_AUDIT.json","V39E_TEMPORAL_FIRST_MIGRATION_AUDIT.json",
        "V39E_POWER_CONSERVATION_AUDIT.json","V39E_FRESH_RESTORATION_LOADER_AUDIT.json"))
    backups={}
    for source in selected:
        destination=ROOT/"before_refreeze"/source.name
        if not destination.exists():
            destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,destination)
        assert h.grid.sha(source)==h.grid.sha(destination)
        backups[source.name]=h.grid.sha(source)
    state={"started_at":h.now(),"starting_HEAD":h.v39g.git("rev-parse","HEAD"),"starting_branch":h.v39g.git("branch","--show-current"),
        "production_source_SHA256":h.v39g.source_hashes(),"V39H_required_SHA256":source_manifest,"before_refreeze_SHA256":backups,
        "original_dirty_state":h.v39g.git("status","--porcelain"),"Actual_Fresh_result_contents_read_during_DA_construction":0}
    h.atomic(state_path,{"labels":["AUTHORIZED_PRODUCTION_REFREEZE","MINIMUM_SAFE_RECOMPUTATION"],**state})
    rows=[]
    for day in (f"2025-05-{d:02d}" for d in range(1,32)):
        hresult=h.read(h.ROOT/"days"/day/"V39H_SHADOW_A_RESULT.json") if day in h.DAYS else None
        for case in ("B0","B1","B2","B3"):
            saved=h.read(ROOT/"before_refreeze"/f"V39E_DAYAHEAD_DECISION_FREEZE_{day}_{case}.json")
            assert canonical_sha256(saved["decision"])==saved["DA_decision_SHA256"]
            changed=case in ("B1","B3") and hresult is not None and hresult["temporal_repair_sufficient"]
            rows.append({"day":day,"case":case,"DA_change_required":changed,"old_DA_SHA256":saved["DA_decision_SHA256"],
                "action":"MATERIALIZE_SAVED_PRIMARY_OPTIMAL_TEMPORAL_REPAIR" if changed else "REUSE_BYTE_IDENTICAL_DA",
                "temporal_outcome":"PASS" if hresult and hresult["temporal_repair_sufficient"] else "INFEASIBLE" if hresult else "NOT_REQUIRED",
                "new_primary_optimization_calls":0,"new_migration_MILP_calls":0})
    changed_days=sorted({r["day"] for r in rows if r["DA_change_required"]})
    assert changed_days==["2025-05-17","2025-05-23","2025-05-24","2025-05-25","2025-05-26"]
    h.atomic(ROOT/"PRODUCTION_CHANGE_IMPACT_AUDIT.json",{"labels":["AUTHORIZED_PRODUCTION_REFREEZE"],"status":"PASS",
        "changed_days":changed_days,"changed_day_case_count":sum(r["DA_change_required"] for r in rows),"unchanged_day_case_count":sum(not r["DA_change_required"] for r in rows),
        "rows":rows,"full_31_day_optimization_rerun":False,"V39I_dependency":False})
    print("CHANGE_IMPACT: 5 dates / 10 RSP day-cases changed; 114 DA day-cases reused",flush=True)
    return state


def test_close():
    stream=io.StringIO();suite=unittest.defaultTestLoader.loadTestsFromName("tests.dayahead.test_v39h_production_refreeze")
    result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    h.atomic(ROOT/"PRODUCTION_CLOSE_TEST_REPORT.json",{"labels":["AUTHORIZED_PRODUCTION_REFREEZE"],"status":"PASS" if result.wasSuccessful() else "FAIL",
        "tests_run":result.testsRun,"failures":len(result.failures),"errors":len(result.errors),"skipped":len(result.skipped),
        "optimization_calls":0,"output":stream.getvalue()})
    print(stream.getvalue(),flush=True);assert result.wasSuccessful() and not result.skipped


def resume():
    from dayahead.v39e.temporal_refreeze import load_ready_refreeze, MAY01_05
    from dayahead.v39e.campaign import run_campaign, _reusable
    from dayahead.v39e.progress import ProgressTracker
    from dayahead.v39e.overnight import _write_final_report
    assert h.read(ROOT/"PRODUCTION_CLOSE_TEST_REPORT.json")["status"]=="PASS"
    preflight=load_ready_refreeze(REPO)
    assert preflight["status"]=="PASS" and preflight["READY"]==31 and preflight["NOT_READY"]==preflight["missing"]==0
    assert all(_reusable(REPO,day,"AUTHORITATIVE_V39E_MAY_CAMPAIGN") for day in MAY01_05)
    tracker=ProgressTracker(REPO,h.v39g.git("rev-parse","HEAD"),h.v39g.git("branch","--show-current"))
    tracker.start_heartbeat()
    tracker.update(phase="MAY_ACTUAL",campaign_classification="AUTHORITATIVE",preflight_READY=31,preflight_NOT_READY=0,preflight_missing=0,
        repair_summary="V39H_PRIMARY_OPTIMAL_TEMPORAL_REPAIR_SELECTIVE_REFREEZE",rerun_mode="MINIMUM_SAFE_SELECTIVE_RECOMPUTATION",
        reusable_count=5,invalidated_count=0,rerun_count=0,temporal_only_days=23,migration_escalated_days=8,total_migrations_from_frozen_DA=76,
        PRECHECK_BYPASSED="NO",MAX_PARALLEL_DAY_WORKERS=4,GUROBI_THREADS_PER_MODEL=4,V39I_PRODUCTION_BLOCKER="NO")
    try:
        result=run_campaign(REPO,tracker,preflight)
        _write_final_report(REPO,preflight,result)
        print("MAY_CAMPAIGN_TERMINAL",result["PASS_dates"],result["FAIL_dates"],flush=True)
    finally:tracker.close()


def record_resume(monitor_pid):
    """Capture the immediate production-close outcome without rerunning any gate."""
    import ast
    import ctypes
    from ctypes import wintypes
    from datetime import datetime, timezone
    from dayahead.v39e.temporal_refreeze import assert_protected_results, source_fingerprint, MAY01_05
    from dayahead.v39e.campaign import _reusable

    kernel=ctypes.WinDLL("kernel32",use_last_error=True)
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
    kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.GetExitCodeProcess.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD)]
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    def alive(pid):
        handle=kernel.OpenProcess(0x1000,False,int(pid))
        if not handle:return False
        try:
            code=wintypes.DWORD()
            return bool(kernel.GetExitCodeProcess(handle,ctypes.byref(code))) and code.value==259
        finally:kernel.CloseHandle(handle)

    progress=h.read(REPO/"progress/V39E_OVERNIGHT_PROGRESS.json")
    assert progress["phase"]=="MAY_ACTUAL" and progress["campaign_classification"]=="AUTHORITATIVE"
    assert (datetime.now(timezone.utc)-datetime.fromisoformat(progress["last_update"])).total_seconds()<120
    assert not progress["failed_days"] and 1<=len(progress["running_days"])<=4
    assert set(MAY01_05)<=set(progress["completed_days"])
    assert not set(MAY01_05)&set(progress["running_days"])
    assert all(alive(pid) for pid in progress["worker_PIDs"]) and alive(monitor_pid)
    assert progress["MAX_PARALLEL_DAY_WORKERS"]==progress["GUROBI_THREADS_PER_MODEL"]==4
    runtime={}
    for day in progress["running_days"]:
        path=REPO/"logs/v39e_may_2025"/f"{day}.log"
        with path.open("rb") as stream:
            stream.seek(max(0,path.stat().st_size-1024*1024))
            lines=stream.read().decode("utf-8",errors="replace").splitlines()
        lines=[line for line in lines if line.startswith("V39H_RUNTIME_AUTHORITY ")]
        assert lines,day
        runtime[day]=ast.literal_eval(lines[-1].split(" ",1)[1])
        assert runtime[day]["Threads_per_model"]==4 and runtime[day]["active_solvers_per_day_max"]==1
        assert runtime[day]["max_concurrent_solver_threads"]==16
    protected=assert_protected_results(REPO)
    assert all(_reusable(REPO,day,"AUTHORITATIVE_V39E_MAY_CAMPAIGN") for day in MAY01_05)
    start=h.read(ROOT/"PRODUCTION_CLOSE_START_STATE.json")
    assert all(h.grid.sha(h.ROOT/path)==sha for path,sha in start["V39H_required_SHA256"].items())
    authority=h.read(ROOT/"PRODUCTION_REFREEZE_AUTHORITY.json")
    preflight=h.read(h.BASE/"V39E_FULL_PREFLIGHT.json")
    inputs,fingerprint=source_fingerprint(REPO)
    assert inputs==preflight["implementation_fingerprint_inputs"]
    assert fingerprint==authority["implementation_fingerprint_sha256"]
    assert h.grid.sha(h.BASE/"V39E_FULL_PREFLIGHT.json")==authority["production_preflight_SHA256"]
    assert authority["status"]=="PASS" and not authority["V39I_dependency"]
    readiness=h.read(ROOT/"CHEAP_31_DAY_READINESS.json")
    assert (readiness["READY"],readiness["NOT_READY"],readiness["MISSING"])==(31,0,0)
    assert h.read(ROOT/"PRODUCTION_CLOSE_TEST_REPORT.json")["status"]=="PASS"
    deferred=h.read(REPO/"dayahead/artifacts/v39i_may25_26_primary_optimal_minmax_delay/V39I_DEFERRED_FINAL_STATUS.json")
    assert deferred["solver_processes_stopped"] and deferred["V39I_DIAGNOSTIC_COMPLETE"]=="NO"
    assert all(row["outcome"]=="UNKNOWN" for row in deferred["unfinished_threshold_outcomes"].values())
    names=("PRODUCTION_CHANGE_IMPACT_AUDIT.json","PRODUCTION_REFREEZE_AUTHORITY.json",
        "SELECTIVE_PREFLIGHT_SUMMARY.json","CHEAP_31_DAY_READINESS.json","MAY01_05_REUSE_EQUIVALENCE.json",
        "MIGRATION_REUSE_EQUIVALENCE.json","PRODUCTION_CLOSE_TEST_REPORT.json")
    result={"recorded_at":h.now(),"PRODUCTION_REFREEZE_COMPLETE":"YES","SELECTIVE_PREFLIGHT_COMPLETE":"YES",
        "READINESS":"31/31","NOT_READY":0,"MISSING":0,"MAY01_05_REUSE":"YES","MAY01_05_RESULTS_TOUCHED":"NO",
        "MAY_CAMPAIGN_RESUMED":"YES","MAY_CAMPAIGN_COMPLETE":"NO","MAX_PARALLEL_DAY_WORKERS":4,"GUROBI_THREADS_PER_MODEL":4,
        "new_primary_optimization_calls":0,"new_migration_MILP_calls":0,"full_31_day_optimization_rerun":False,
        "changed_DA_dates":["2025-05-17","2025-05-23","2025-05-24","2025-05-25","2025-05-26"],
        "changed_DA_day_cases":10,"byte_identical_DA_day_cases_reused":114,"minimum_migration_days":8,"minimum_RUNNING_migrations":76,
        "V39I_DIAGNOSTIC_COMPLETE":"NO","V39I_STOP_REASON":deferred["V39I_STOP_REASON"],"V39I_PRODUCTION_BLOCKER":"NO",
        "PRODUCTION_SCIENCE_CHANGED_AT_V39I_STOP":"NO","V39H_frozen_hard_constraints_changed":False,
        "secondary_tertiary_global_optimality_required":False,"new_service_SLA_or_deadline":None,
        "May25_saved_witness_max_delay_min":5745,"May26_saved_witness_max_delay_min":3840,"exact_minmax_delay_certified":False,
        "May01_05_protected_files_verified_after_resume":protected,"V39H_required_SHA_files_verified":len(start["V39H_required_SHA256"]),
        "runtime_authority_by_running_day":runtime,"visible_monitor_PID":monitor_pid,
        "progress_snapshot":progress,"evidence_SHA256":{name:h.grid.sha(ROOT/name) for name in names},"push":"NO","PR":"NO"}
    h.atomic(ROOT/"PRODUCTION_CLOSE_FINAL_STATUS.json",result)
    print({k:result[k] for k in ("PRODUCTION_REFREEZE_COMPLETE","SELECTIVE_PREFLIGHT_COMPLETE","READINESS","MAY01_05_REUSE","MAY_CAMPAIGN_RESUMED")},flush=True)
    print("Protected May01-05 files:",protected,"; immutable V39H SHA files:",len(start["V39H_required_SHA256"]),flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--init",action="store_true");parser.add_argument("--test",action="store_true");parser.add_argument("--resume",action="store_true");parser.add_argument("--record-resume",action="store_true");parser.add_argument("--monitor-pid",type=int);args=parser.parse_args()
    initialize()
    if args.test:test_close()
    if args.resume:resume()
    if args.record_resume:
        assert args.monitor_pid is not None
        record_resume(args.monitor_pid)
