"""V39K authority-only integration; no optimizer, campaign, or worker launcher.

Phases: snapshot -> prepare (isolated staging) -> apply -> release.
All live replacements are backed up and explicitly whitelisted. HOLD is the
last mutation and requires live authority/readiness/preservation checks.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from types import FunctionType

WORK = Path(__file__).resolve().parents[2]
LIVE = Path(r"C:\codex_mobileess_workspace\MobileESS_v39a_causal_aidc")
REL = Path("dayahead/artifacts/v39k_may23_26_fallback_live_integration")
ROOT = WORK / REL
STAGE = ROOT / "stage"
FULL = Path("dayahead/artifacts/v39e_full_may_2025")
CLOSE = Path("dayahead/artifacts/v39h_production_refreeze_may_close")
HROOT = Path("dayahead/artifacts/v39h_13day_temporal_repair_migration_shadow")
GATE = Path("dayahead/artifacts/v39h_terminal_state_audit/TERMINAL_AUDIT_LAUNCH_GATE.json")
COUNTS = {f"2025-05-{d}": n for d,n in [(23,4),(24,2),(25,8),(26,15)]}
DAYS = tuple(COUNTS)
AXIS = tuple(f"2025-05-{i:02}" for i in range(1,32))
CASES = ("B0","B1","B2","B3")
sys.path.insert(0,str(WORK))
sys.dont_write_bytecode=True
os.environ.update(OPENBLAS_NUM_THREADS="1",OMP_NUM_THREADS="1",MKL_NUM_THREADS="1")
import numpy as np
import pandas as pd
import gurobipy as gp
from dayahead.tools import run_v39j_terminal_repair as j
from dayahead.v38.authority import canonical_sha256,load_wan_authority,checkpoint_slots
from dayahead.v38.wan import validate_fixed_path_transfers
from dayahead.v39c.evaluate import _elapsed_seconds
from dayahead.v39e import campaign_adapter as adapter
from dayahead.v39e.temporal_refreeze import source_fingerprint,load_ready_refreeze
from dayahead.v39e.full_preflight import _fresh_loader_audit
from dayahead.v39d.actual import validate_actual_fixed_replay
from dayahead.v39a.power import validate_power_conservation


def no_solver(*args,**kwargs):
    raise AssertionError("V39K_OPTIMIZATION_OR_MODEL_CONSTRUCTION_FORBIDDEN")


gp.Model=gp.Env=no_solver


def read(p):return json.loads(Path(p).read_text(encoding="utf-8"))
def sha(p):
    h=hashlib.sha256()
    with Path(p).open("rb") as f:
        for block in iter(lambda:f.read(1024*1024),b""):h.update(block)
    return h.hexdigest()
def now():return datetime.now(timezone.utc).isoformat()
def save(p,value):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_name(p.name+".v39k.tmp")
    tmp.write_text(json.dumps(j.h.v39g.clean(value),indent=2,ensure_ascii=False,allow_nan=False)+"\n",encoding="utf-8")
    os.replace(tmp,p)
def fname(day,case):return f"V39E_DAYAHEAD_DECISION_FREEZE_{day}_{case}.json"
def decision(p):
    f=read(p);assert canonical_sha256(f["decision"])==f["DA_decision_SHA256"]
    return f
def resolve(rel):return STAGE/rel if (STAGE/rel).is_file() else LIVE/rel
def git(*args):return subprocess.check_output(["git","--no-optional-locks",*args],cwd=LIVE,text=True).strip()
def is_monitor_process(row):
    return bool(re.search(r'(?i)\s-File\s+"?[^"\r\n]*monitor_v39e_may_campaign\.ps1(?:"|\s|$)',row.get("CommandLine") or ""))
def processes():
    script="Get-CimInstance Win32_Process | Where-Object { ($_.Name -eq 'python.exe' -and $_.CommandLine -match 'run_v39h_production_close|run_v39e_may_day') -or ($_.Name -eq 'powershell.exe' -and $_.CommandLine -match 'monitor_v39e_may_campaign.ps1') } | Select-Object ProcessId,ParentProcessId,CommandLine | ConvertTo-Json -Compress"
    rows=json.loads(subprocess.check_output(["powershell","-NoProfile","-Command",script],text=True))
    # The CIM query contains the monitor filename in its own -Command string.
    # Only an actual -File invocation is a monitor process.
    rows=[r for r in rows if "monitor_v39e_may_campaign.ps1" not in (r["CommandLine"] or "") or is_monitor_process(r)]
    for r in rows:
        m=re.search(r"--day (2025-05-\d{2})",r["CommandLine"] or "")
        if m:r["day"]=m[1]
    return rows
def source_shas():
    names=read(j.ROOT/"V39J_SOURCE_AUTHORITY_MANIFEST.json")["live_source_SHA256"]
    return {p:sha(LIVE/p) for p in names}
def da_shas():return {p.name:sha(p) for p in (LIVE/FULL).glob("V39E_DAYAHEAD_DECISION_FREEZE_*.json")}
def check_changed_cases(before,after):
    assert set(before)==set(after),"Missing or additional DA authority"
    expected={fname(d,c) for d in DAYS for c in ("B1","B3")}
    changed={n for n,s in after.items() if s!=before[n]}
    assert changed==expected,"Unexpected or missing changed day-case"
    return changed
def invalid_actual():
    roots=[LIVE/"frozen_artifacts/v36_final_schema/MAY_2025_V39E_FROZEN_DA",LIVE/"dayahead/cache/v37_may_locked_final/MAY_2025_V39E_FROZEN_DA"]
    found=[]
    for root in roots:
        if root.exists():
            for p in root.rglob("*"):
                if p.is_file() and any(d in p.parts for d in DAYS):found.append(str(p.relative_to(LIVE)))
    for day in DAYS:
        for rel in [FULL/"dates"/f"{day}.json",FULL/"certificates"/f"V39E_MAY_DAY_CERTIFICATE_{day}.json"]:
            if (LIVE/rel).exists():found.append(str(rel))
    return found


def snapshot():
    ROOT.mkdir(parents=True,exist_ok=True)
    assert not (ROOT/"V39K_PREINTEGRATION_LIVE_SNAPSHOT.json").exists(),"Snapshot immutable"
    statuses={p.stem:read(p) for p in (LIVE/FULL/"status").glob("*.json")}
    completed=[d for d,v in statuses.items() if v.get("status")=="PASS"]
    protected={}
    for day in completed:
        paths=[LIVE/FULL/"dates"/f"{day}.json",LIVE/FULL/"certificates"/f"V39E_MAY_DAY_CERTIFICATE_{day}.json",LIVE/FULL/"status"/f"{day}.json"]
        for case in CASES:
            cp=LIVE/f"dayahead/cache/v37_may_locked_final/MAY_2025_V39E_FROZEN_DA/case_checkpoints/{day}/{case}.json"
            paths.append(cp)
            for row in read(cp)["files"]:
                raw=LIVE/f"frozen_artifacts/v36_final_schema/MAY_2025_V39E_FROZEN_DA/{day}/{case}"/row["relative_path"]
                assert sha(raw)==row["sha256"];paths.append(raw)
        for p in paths:
            s=p.stat();protected[p.relative_to(LIVE).as_posix()]={"SHA256":sha(p),"size":s.st_size,"mtime_ns":s.st_mtime_ns}
    fp,digest=source_fingerprint(LIVE)
    pre=read(LIVE/FULL/"V39E_FULL_PREFLIGHT.json")
    assert fp==pre["implementation_fingerprint_inputs"] and digest==pre["final_implementation_fingerprint_sha256"]
    gate=read(LIVE/GATE);assert all(gate["dates"][d]["release"] is False for d in DAYS)
    ps=processes();workers=[r for r in ps if "day" in r]
    assert len({r["day"] for r in workers})==len(workers)
    bad=invalid_actual();assert not bad,bad
    snap=dict(LIVE_ROOT=str(LIVE),LIVE_BRANCH=git("branch","--show-current"),LIVE_HEAD=git("rev-parse","HEAD"),captured_at=now(),
        accepted_production_source_fingerprint=digest,implementation_fingerprint_inputs=fp,live_source_SHA256=source_shas(),
        processes=ps,orchestrator_PID=[r["ProcessId"] for r in ps if "run_v39h_production_close.py" in r["CommandLine"]],
        monitor_PID=[r["ProcessId"] for r in ps if "monitor_v39e_may_campaign.ps1" in r["CommandLine"]],active_workers=workers,
        completed_dates=completed,running_dates=[r["day"] for r in workers],HOLD_dates=list(DAYS),failed_dates=[d for d,v in statuses.items() if v.get("status")=="FAIL"],
        all_124_DA_freeze_SHA256=da_shas(),May23_26_authority_SHA256={fname(d,c):sha(LIVE/FULL/fname(d,c)) for d in DAYS for c in CASES},
        protected_result_SHA256=protected,protected_result_read_scope="CHECKSUM_PRESERVATION_ONLY; NOT_DA_INPUT",launch_gate_SHA256=sha(LIVE/GATE),
        production_refreeze_authority_SHA256=sha(LIVE/CLOSE/"PRODUCTION_REFREEZE_AUTHORITY.json"),INVALID_ACTUAL_OUTPUT_PRESENT=False,
        MAX_PARALLEL_DAY_WORKERS=4,GUROBI_THREADS_PER_MODEL=4)
    assert len(snap["all_124_DA_freeze_SHA256"])==124
    save(ROOT/"V39K_PREINTEGRATION_LIVE_SNAPSHOT.json",snap)
    print("SNAPSHOT PASS",len(completed),"completed; protected files",len(protected),flush=True)


def install_stage_guard():
    def guard(event,args):
        if event=="open":
            p,mode,flags=args
            if isinstance(p,int):return
            p=Path(p).resolve();writing=bool((flags or 0)&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND))
            if writing and not p.is_relative_to(ROOT):raise PermissionError(f"V39K_STAGE_WRITE:{p}")
            if not writing and p.suffix.lower() in (".parquet",".npz",".json",".csv"):
                s=p.as_posix().lower()
                if any(x in s for x in ("/actual/","/fresh/","/dates/","/case_checkpoints/","/frozen_artifacts/")):
                    raise PermissionError(f"V39K_DA_OBSERVATION_READ:{p}")
        elif event in ("os.remove","os.rmdir","os.mkdir","os.rename","os.replace"):
            for p in args[:2] if event in ("os.rename","os.replace") else args[:1]:
                if not Path(p).resolve().is_relative_to(ROOT):raise PermissionError(f"V39K_STAGE_MUTATION:{p}")
    sys.addaudithook(guard)


def verify_day(day):
    print(day,"VERIFY_EXISTING_FALLBACK",flush=True)
    seal=read(LIVE/CLOSE/"PRODUCTION_CLOSE_START_STATE.json")["before_refreeze_SHA256"]
    originals={c:LIVE/CLOSE/"before_refreeze"/fname(day,c) for c in ("B1","B3")}
    for c,p in originals.items():assert sha(p)==seal[p.name]
    freezes={c:decision(p) for c,p in originals.items()};dec=freezes["B1"]["decision"]
    assert {k:v for k,v in dec.items() if k!="case"}=={k:v for k,v in freezes["B3"]["decision"].items() if k!="case"}
    assert "temporal_repair_authority" not in dec
    if day=="2025-05-23":
        auditroot=WORK/"dayahead/artifacts/v39j_may23_targeted_terminal_audit"
        certfile=auditroot/"MAY23_EXISTING_FOUR_MIGRATION_FALLBACK_CHECK.json"
        expected=read(auditroot/"MAY23_REQUIRED_ARTIFACT_SHA_MANIFEST.json")["SHA256"][certfile.name]
        assert sha(certfile)==expected and read(certfile)["original_B1_SHA256"]==sha(originals["B1"])
        cache=LIVE/HROOT/"days"/day
    else:
        certfile=j.ROOT/"days"/day/"V39J_GRID_VERIFICATION.json"
        expected=read(j.ROOT/"V39J_REQUIRED_ARTIFACT_SHA_MANIFEST.json")["SHA256"][f"days/{day}/{certfile.name}"]
        assert sha(certfile)==expected and read(certfile)["original_witness_SHA256"]==sha(originals["B1"])
        cache=j.ROOT/"days"/day
    d1=LIVE/f"dayahead/artifacts/v37_r4a_per_day_aidc/days/{day}"
    oldcert=read(LIVE/CLOSE/"days"/day/"SELECTIVE_PREFLIGHT_CERTIFICATE.json")
    inputshas={}
    for raw,s in oldcert["frozen_input_SHA256"].items():assert sha(raw)==s;inputshas[raw]=s
    ledger=pd.read_parquet(d1/"V37_R4A_JOB_LEDGER.parquet");ledger["job_uid"]=ledger.job_id.astype(str)
    schedule=pd.DataFrame(dec["temporal_schedule"]).set_index("job_id").loc[ledger.job_uid]
    assert np.array_equal(schedule.scheduled_start_slot,ledger.RSP_scheduled_start)
    assert np.array_equal(schedule.scheduled_end_slot,ledger.RSP_scheduled_completion)
    assert np.array_equal(schedule.duration_slots,ledger.RSP_duration_slots)
    assert np.array_equal(schedule.requested_gpus,ledger.requested_gpus)
    assert sha(d1/"V37_R4A_RSP_SCHEDULE.parquet")==dec["temporal_schedule_SHA256"]
    cutoff=pd.Timestamp(day,tz="Australia/Brisbane")-pd.Timedelta(hours=6)
    ledger["D1_visible"]=pd.to_datetime(ledger.submit_time,utc=True)<=cutoff.tz_convert("UTC")
    assert ledger.D1_visible.all()
    elig=j.h.v39g.eligible_mask(ledger)
    assert (ledger.loc[elig,"RSP_scheduled_completion"]<=ledger.loc[elig,"RW_scheduled_completion"]).all()
    bundle=j.verifier_bundle(cache);cap=bundle["capacity"];sites=bundle["sites"]
    occ=np.zeros((96,12),dtype=np.int64);rows=dec["AIDC_assignments"]
    assert len({r["job_uid"] for r in rows})==len(rows)
    for r in rows:
        g=int(r["requested_GPU"]);s=r["destination_AIDC"]
        assert cap.eligible_racks(s,g)
        occ[r["active_start_slot"]:r["active_end_slot"],sites.index(s)]+=g
    assert (occ<=np.array([cap.site_capacity[s] for s in sites])).all()
    def matrix(field,value):return pd.DataFrame(dec[field]).pivot(index="slot",columns="AIDC",values=value).loc[range(96),list(sites)].to_numpy()
    assert np.array_equal(matrix("site_GPU_trajectory","active_GPU"),occ)
    it=matrix("site_IT_power_trajectory","IT_power_kW")
    for slot in range(96):
        p=validate_power_conservation(cap.site_capacity,dict(zip(sites,map(int,occ[slot]))))
        # Scalar site power is checked against the accepted conservation function below.
        assert p["status"]=="PASS"
    from dayahead.v39a.power import site_it_power_kw
    it_expected=np.array([[float(site_it_power_kw(cap.site_capacity[s],int(occ[slot,k]))) for k,s in enumerate(sites)] for slot in range(96)])
    assert np.allclose(it,it_expected,atol=1e-8,rtol=0)
    pcc=np.array([[bundle["tables"][s][slot,occ[slot,k]] for k,s in enumerate(sites)] for slot in range(96)])
    saved=matrix("site_PCC_power_trajectory","PCC_P_kW")
    assert np.allclose(saved,pcc,atol=1e-8,rtol=0)
    print(day,"GRID_FIXED_WITNESS_CHECK",flush=True)
    grid=j.h.grid.evaluate(bundle["coefficients"],bundle["nodes"],pcc)
    assert grid["pass"]
    assert abs(grid["Vmax"]-dec["planning_feasibility"]["Vmax_pu"])<1e-10
    selected=[r for r in rows if r.get("migration_selected")];assert len(selected)==COUNTS[day]
    auditpath=LIVE/CLOSE/"before_refreeze/V39E_TEMPORAL_FIRST_MIGRATION_AUDIT.json"
    assert sha(auditpath)==seal[auditpath.name]
    oldrow=next(r for r in read(auditpath)["days"] if r["operating_day"]==day)
    assert oldrow["solver_proven_minimum_RUNNING_migrations"]==len(selected)==dec["migration_state"]["WAN_transfer_count"]
    snapshot=pd.read_parquet(d1/"V37_R4A_D1_SNAPSHOT.parquet")
    cutoff=pd.Timestamp(day,tz="Australia/Brisbane")-pd.Timedelta(hours=6)
    assert (pd.to_datetime(snapshot.submit_time,utc=True)<=cutoff.tz_convert("UTC")).all()
    wan=load_wan_authority(LIVE);transfers=[]
    for r in selected:
        assert r["state_at_issue"]=="RUNNING" and r["source_AIDC"]!=r["destination_AIDC"]
        amounts=r["WAN_bytes_by_slot"];slots=[i for i,v in enumerate(amounts) if v]
        assert len(amounts)==96 and all(int(v)==v and v>=0 for v in amounts)
        assert sum(amounts)==wan.payload_bytes(r["requested_GPU"])
        assert r["fixed_WAN_path_id"]==wan.path_id(r["source_AIDC"],r["destination_AIDC"])
        assert tuple(r["fixed_WAN_path_links"])==wan.path(r["source_AIDC"],r["destination_AIDC"])
        assert r["migration_checkpoint_slot"]<=min(slots)<=max(slots)==r["WAN_transfer_complete_slot"]
        assert r["destination_READY_slot"]==max(slots)+1 and r["restart_complete_slot"]==max(slots)+2
        assert r["migration_checkpoint_slot"] in checkpoint_slots(_elapsed_seconds(snapshot,r["job_uid"]),r["active_end_slot"]-r["active_start_slot"])
        transfers.append(dict(job_uid=r["job_uid"],source_AIDC=r["source_AIDC"],destination_AIDC=r["destination_AIDC"],bytes_by_slot=amounts))
    wancheck=validate_fixed_path_transfers(wan,transfers);assert wancheck["status"]=="PASS"
    cert=dict(status="PASS",day=day,authority_kind="ORIGINAL_BASE_RSP_PLUS_EXISTING_EXACT_MINIMUM_MIGRATION",TEMPORAL_REPAIR_USED=False,
        REPAIR_INDUCED_INCREMENTAL_POST_MIDNIGHT_GPU_H=0,POST_H_RESERVATION_PROFILE_CHANGED_JOBS_FROM_BASE_RSP=0,
        POST_H_SITE_STATE_CHANGED_JOBS_FROM_BASE_RSP=0,terminal_comparison="Original baseline fallback including its frozen migration witness; not a zero-migration temporal repair",
        baseline_RSP_SHA256=dec["temporal_schedule_SHA256"],original_freeze_SHA256={c:sha(p) for c,p in originals.items()},
        original_decision_SHA256={c:f["DA_decision_SHA256"] for c,f in freezes.items()},
        exact_migration_witness_SHA256=canonical_sha256(dec["AIDC_assignments"]),existing_solver_certificate=oldrow,
        migration_count=COUNTS[day],safe_runtime_GPU_and_RSP_timing_exact=True,RW_completion_noninferiority="PASS_NO_NEW_VIOLATIONS",
        preexisting_noneligible_RSP_later_than_RW=int((~elig & ledger.RSP_scheduled_completion.gt(ledger.RW_scheduled_completion)).sum()),
        site_capacity="PASS",Rack_compatibility="PASS",gang_splits=0,C1_PCC_max_error_kW=float(np.max(np.abs(saved-pcc))),
        IT_power_max_error_kW=float(np.max(np.abs(it-it_expected))),grid=grid,WAN_checkpoint_READY_restart=wancheck,
        source_input_SHA256=inputshas,prior_certification_path=str(certfile),prior_certification_SHA256=sha(certfile),
        derived_cache_SHA256={p.name:sha(p) for p in cache.glob("*.npz")},derived_cache_scope="Captured cache hashes; raw frozen inputs sealed; computed verdict agrees with original planning certificate",
        Actual_observation_reads=0,Fresh_observation_reads=0,future_day_inputs=0,optimization_calls=0,migration_MILP_calls=0,
        physical_grid_domain=[24,120],post_H_physical_grid_claim=False,inter_day="independent",intra_day="stateful")
    certrel=REL/"days"/day/"V39K_FALLBACK_CERTIFICATE.json";save(STAGE/certrel,cert)
    for case,f in freezes.items():
        restored=deepcopy(f);d=restored["decision"]
        # Legacy compatibility key binds fallback evidence, never an old repair witness.
        d["temporal_repair_authority"]={"authority_kind":"V39K_CERTIFIED_ORIGINAL_RSP_MIGRATION_FALLBACK","TEMPORAL_REPAIR_USED":False,
            "temporal_repair_status":"REJECTED_TERMINAL_STATE_FAIL" if day=="2025-05-23" else "TERMINAL_SAFE_REPAIR_INFEASIBLE",
            "primary_optimum_GPU_slots":None,"certificate_path":certrel.as_posix(),"certificate_SHA256":sha(STAGE/certrel),
            "temporal_schedule_authority_path":(d1/"V37_R4A_RSP_SCHEDULE.parquet").relative_to(LIVE).as_posix(),
            "original_freeze_SHA256":sha(originals[case]),"policy":"RESTORE_EXISTING_BASE_RSP_AND_EXACT_MIGRATION_WITNESS"}
        assert {k:v for k,v in d.items() if k!="temporal_repair_authority"}==f["decision"]
        restored["DA_decision_SHA256"]=canonical_sha256(d)
        save(STAGE/FULL/fname(day,case),restored)
    print(day,"SELECTIVE_SCIENCE_PASS migrations",COUNTS[day],flush=True)
    return cert


def loader(day,case,staged=True):
    ns=dict(adapter.build_day.__globals__)
    ns["freeze_path"]=lambda repo,d,c:resolve(FULL/fname(d,c)) if staged else LIVE/FULL/fname(d,c)
    return FunctionType(adapter.build_day.__code__,ns)(LIVE,day,case)


def prepare():
    before=read(ROOT/"V39K_PREINTEGRATION_LIVE_SNAPSHOT.json")
    assert source_shas()==before["live_source_SHA256"] and da_shas()==before["all_124_DA_freeze_SHA256"]
    install_stage_guard()
    certs=[verify_day(d) for d in DAYS]
    rows=[];freezehash={};ident=read(LIVE/FULL/"V39E_B0_B3_IDENTITY_AUDIT.json");replay=read(LIVE/FULL/"V39E_ACTUAL_FIXED_REPLAY_AUDIT.json")
    for day in AXIS:
        for case in CASES:
            rel=FULL/fname(day,case);p=resolve(rel);f=decision(p);d=f["decision"];tr=loader(day,case)
            assert np.isfinite(tr.pcc_p_kw).all() and tr.pcc_p_kw.shape==(96,12)
            assert tr.fingerprints["V39E_DA_freeze_SHA256"]==sha(p)
            assert tr.fingerprints["V39E_DA_decision_SHA256"]==f["DA_decision_SHA256"]
            assert validate_actual_fixed_replay(f,f["DA_decision_SHA256"])["status"]=="PASS"
            changed=day in DAYS and case in ("B1","B3")
            if not changed:assert sha(p)==before["all_124_DA_freeze_SHA256"][p.name]
            binding=d.get("temporal_repair_authority")
            if binding:
                assert sha(resolve(Path(binding["certificate_path"])))==binding["certificate_SHA256"]
                assert sha(resolve(Path(binding["temporal_schedule_authority_path"])))==d["temporal_schedule_SHA256"]
            if changed:
                assert binding["TEMPORAL_REPAIR_USED"] is False
                assert "v39h" not in binding["certificate_path"].lower()
                assert "v37_r4a" in binding["temporal_schedule_authority_path"]
                ident["days"][day][case]=canonical_sha256({"assignments":d["AIDC_assignments"],"gpu":d["site_GPU_trajectory"]})
                next(r for r in replay["cases"] if r["operating_day"]==day and r["case"]==case)["DA_freeze_SHA256"]=f["DA_decision_SHA256"]
            freezehash[p.name]=sha(p)
            rows.append(dict(day=day,case=case,classification="CHANGED" if changed else "REUSED_EQUIVALENT",
                before_SHA256=before["all_124_DA_freeze_SHA256"][p.name],after_SHA256=sha(p),DA_decision_SHA256=f["DA_decision_SHA256"],loader="PASS",certificate="PASS",
                temporal_repair_calls=0,migration_optimization_calls=0,common_initial_state_SHA256=d["common_initial_state_SHA256"],temporal_schedule_SHA256=d["temporal_schedule_SHA256"]))
    assert sum(r["classification"]=="CHANGED" for r in rows)==8
    assert all(r["B0"]==r["B2"] and r["B1"]==r["B3"] for r in ident["days"].values())
    assert _fresh_loader_audit(LIVE)["status"]=="PASS"
    save(STAGE/FULL/"V39E_B0_B3_IDENTITY_AUDIT.json",ident);save(STAGE/FULL/"V39E_ACTUAL_FIXED_REPLAY_AUDIT.json",replay)
    aggregatechecks=[]
    for name,field in [("V39E_SITE_GPU_TRAJECTORIES.parquet","site_GPU_trajectory"),("V39E_SITE_IT_POWER_TRAJECTORIES.parquet","site_IT_power_trajectory"),("V39E_SITE_PCC_POWER_TRAJECTORIES.parquet","site_PCC_power_trajectory")]:
        old=pd.read_parquet(LIVE/FULL/name);keep=~(old.operating_day.isin(DAYS)&old["case"].isin(("B1","B3")))
        frames=[old.loc[keep].copy()]
        for day in DAYS:
            for case in ("B1","B3"):
                df=pd.DataFrame(decision(STAGE/FULL/fname(day,case))["decision"][field]);df["case"]=case;frames.append(df)
        new=pd.concat(frames,ignore_index=True).sort_values(["operating_day","case","slot","AIDC"]).reset_index(drop=True)
        kept=new.loc[~(new.operating_day.isin(DAYS)&new["case"].isin(("B1","B3")))].reset_index(drop=True)
        pd.testing.assert_frame_equal(old.loc[keep].sort_values(["operating_day","case","slot","AIDC"]).reset_index(drop=True),kept)
        assert len(new)==142848
        new.to_parquet(STAGE/FULL/name,index=False);aggregatechecks.append({"file":name,"unchanged_case_slices":116,"status":"PASS"})
    ma=read(LIVE/FULL/"V39E_TEMPORAL_FIRST_MIGRATION_AUDIT.json")
    for row in ma["days"]:
        if row["operating_day"] in DAYS:
            day=row["operating_day"]
            row.update(temporal_repair_status="REJECTED_TERMINAL_STATE_FAIL" if day==DAYS[0] else "INFEASIBLE",temporal_only_status="FAIL",
                solver_proven_minimum_RUNNING_migrations=COUNTS[day],saved_primary_certificate_reused=False,saved_migration_certificate_reused=True,
                original_base_RSP_retained_before_migration=True,final_status="PASS",migration_solver_calls=0,temporal_solver_calls=0)
    assert sum(r["solver_proven_minimum_RUNNING_migrations"] for r in ma["days"])==105
    ma.update(artifact_id="V39K_CERTIFIED_PRODUCTION_FALLBACK_MIGRATION_ACCOUNTING",solver_proven_migration_count=105,migration_escalated_days=12,temporal_only_days=19,
        certified_production_fallback_migrations=105,migration_reduction_from_original_105=0,new_global_terminal_formulation_minimum_claim=False)
    save(STAGE/FULL/"V39E_TEMPORAL_FIRST_MIGRATION_AUDIT.json",ma)
    power=read(LIVE/FULL/"V39E_POWER_CONSERVATION_AUDIT.json");power["verification"]="116 unchanged case authorities plus 8 independently verified original-RSP migration fallback authorities"
    save(STAGE/FULL/"V39E_POWER_CONSERVATION_AUDIT.json",power)
    pre=read(LIVE/FULL/"V39E_FULL_PREFLIGHT.json")
    for row in pre["days"]:
        if row["operating_day"] in DAYS:
            day=row["operating_day"];row.update(RSP_temporal_repair="REJECTED_TERMINAL_STATE_FAIL" if day==DAYS[0] else "INFEASIBLE",migration_escalation="PASS_EXISTING_EXACT_WITNESS",
                RSP_temporal="PASS_WITH_EXISTING_MIGRATION",status="READY",DA_freeze="PASS",Actual_fixed_replay_loader="PASS",exact_blocker=None)
    pre.update(assembly_mode="V39K_FOUR_DAY_EXISTING_FALLBACK_AUTHORITY_ONLY",selective_preflight_dates=list(DAYS),unchanged_DA_case_authorities_reused=116,
        certified_production_fallback_migrations=105,superseding_integration_authority=(REL/"V39K_PRODUCTION_INTEGRATION_AUTHORITY.json").as_posix())
    save(STAGE/FULL/"V39E_FULL_PREFLIGHT.json",pre)
    auth=read(LIVE/CLOSE/"PRODUCTION_REFREEZE_AUTHORITY.json")
    auth.update(DA_freeze_file_SHA256=freezehash,production_preflight_SHA256=sha(STAGE/FULL/"V39E_FULL_PREFLIGHT.json"),minimum_RUNNING_migrations=105,RUNNING_migration_days=12,
        authority_kind="V39K_CERTIFIED_FALLBACK_PRODUCTION_AUTHORITY",policy="ORIGINAL_BASE_RSP_PLUS_EXISTING_EXACT_MIGRATION_WITNESSES_ON_MAY23_26; MAY17_REPAIR_REUSED",
        certified_production_fallback_migrations=105,new_global_terminal_formulation_minimum_claim=False,
        superseding_integration_authority=(REL/"V39K_PRODUCTION_INTEGRATION_AUTHORITY.json").as_posix(),
        previous_authority_SHA256=before["production_refreeze_authority_SHA256"],previous_authority_archive=(REL/"before_integration"/CLOSE/"PRODUCTION_REFREEZE_AUTHORITY.json").as_posix())
    for day in DAYS:auth["selective_preflight_certificate_SHA256"][day]=sha(STAGE/REL/"days"/day/"V39K_FALLBACK_CERTIFICATE.json")
    auth["selective_preflight_certificate_paths"]={d:(REL/"days"/d/"V39K_FALLBACK_CERTIFICATE.json").as_posix() for d in DAYS}
    save(STAGE/REL/"V39K_PRODUCTION_INTEGRATION_AUTHORITY.json",auth)
    save(STAGE/CLOSE/"PRODUCTION_REFREEZE_AUTHORITY.json",auth)
    pd.DataFrame(rows).to_csv(STAGE/REL/"V39K_CHANGED_DAY_CASES.csv",index=False)
    save(STAGE/REL/"V39K_CHANGE_IMPACT_AUDIT.json",dict(status="PASS",EXPECTED_CHANGED_DAY_CASES=8,ACTUAL_CHANGED_DAY_CASES=8,UNEXPECTED_CHANGED_DAY_CASES=0,
        reused_equivalent=116,May17_reused=True,B0_B2_byte_identical=True,rows=rows,aggregate_checks=aggregatechecks,optimization_calls=0))
    summary=dict(status="PASS",dates=[dict(day=c["day"],status="PASS",migration_count=c["migration_count"],loader_binding="PASS",certificate_binding="PASS",optimization_calls=0) for c in certs],optimization_calls=0)
    save(STAGE/REL/"V39K_SELECTIVE_PREFLIGHT_SUMMARY.json",summary)
    save(STAGE/REL/"V39K_31DAY_READINESS.json",dict(status="PASS",phase="STAGED_HOLD_RETAINED",READY=31,NOT_READY=0,MISSING=0,
        canonical_and_loader_cases_checked=124,certified_production_fallback_migrations=105,optimization_calls=0,invalid_repair_dependencies=0,gate_state="HOLD_UNTIL_LIVE_VERIFICATION"))
    save(STAGE/REL/"V39K_FALLBACK_AUTHORITY_MANIFEST.json",dict(status="PASS",baseline_migrations=105,certified_production_fallback_migrations=105,new_global_minimum_claim=False,
        dates={d:dict(migration_count=COUNTS[d],certificate_SHA256=sha(STAGE/REL/"days"/d/"V39K_FALLBACK_CERTIFICATE.json"),B1_SHA256=freezehash[fname(d,"B1")],B3_SHA256=freezehash[fname(d,"B3")]) for d in DAYS},
        original_science_fields_exact=True,decision_metadata_note="Only a truthful fallback provenance binding is added under the legacy temporal_repair_authority compatibility key. It contains no V39H repair schedule or objective dependency.",
        historical_V39H_76_and_V39J_101_retained=True,common_source_changed=False))
    files={p.relative_to(STAGE).as_posix():sha(p) for p in STAGE.rglob("*") if p.is_file()}
    save(ROOT/"V39K_STAGING_SHA_MANIFEST.json",dict(status="PASS",files=files,optimization_calls=0))
    print("STAGING PASS: 8 changed, 116 equivalent, READY 31/31, migrations 105",flush=True)


def protected_check(before):
    for rel,info in before["protected_result_SHA256"].items():
        p=LIVE/rel;s=p.stat()
        assert sha(p)==info["SHA256"] and s.st_size==info["size"] and s.st_mtime_ns==info["mtime_ns"],rel
    return len(before["protected_result_SHA256"])


def copy_atomic(src,dst):
    dst.parent.mkdir(parents=True,exist_ok=True)
    temp=dst.with_name(dst.name+".v39k.tmp")
    shutil.copyfile(src,temp);os.replace(temp,dst)
    assert sha(src)==sha(dst)


def apply():
    before=read(ROOT/"V39K_PREINTEGRATION_LIVE_SNAPSHOT.json");staged=read(ROOT/"V39K_STAGING_SHA_MANIFEST.json")["files"]
    assert read(ROOT/"V39K_TEST_REPORT.json")["status"]=="PASS"
    assert source_shas()==before["live_source_SHA256"] and da_shas()==before["all_124_DA_freeze_SHA256"]
    assert sha(LIVE/GATE)==before["launch_gate_SHA256"]
    protected_check(before);assert not invalid_actual()
    assert all(sha(STAGE/rel)==s for rel,s in staged.items())
    assert all(not read(LIVE/GATE)["dates"][d]["release"] for d in DAYS)
    assert read(STAGE/REL/"V39K_CHANGE_IMPACT_AUDIT.json")["status"]=="PASS"
    assert read(STAGE/REL/"V39K_31DAY_READINESS.json")["READY"]==31
    allowed={str(FULL/fname(d,c)).replace("\\","/") for d in DAYS for c in ("B1","B3")}
    allowed|={(FULL/n).as_posix() for n in ["V39E_B0_B3_IDENTITY_AUDIT.json","V39E_ACTUAL_FIXED_REPLAY_AUDIT.json","V39E_SITE_GPU_TRAJECTORIES.parquet","V39E_SITE_IT_POWER_TRAJECTORIES.parquet","V39E_SITE_PCC_POWER_TRAJECTORIES.parquet","V39E_TEMPORAL_FIRST_MIGRATION_AUDIT.json","V39E_POWER_CONSERVATION_AUDIT.json","V39E_FULL_PREFLIGHT.json"]}
    allowed.add((CLOSE/"PRODUCTION_REFREEZE_AUTHORITY.json").as_posix())
    for rel in staged:assert rel in allowed or Path(rel).is_relative_to(REL),rel
    backups={}
    for rel in staged:
        if (LIVE/rel).exists():
            b=ROOT/"before_integration"/rel;b.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(LIVE/rel,b);backups[rel]=sha(b)
    # Preserve every replaced current record as immutable historical bytes.
    for rel,s in backups.items():copy_atomic(ROOT/"before_integration"/rel,LIVE/REL/"before_integration"/rel)
    copy_atomic(ROOT/"V39K_PREINTEGRATION_LIVE_SNAPSHOT.json",LIVE/REL/"V39K_PREINTEGRATION_LIVE_SNAPSHOT.json")
    save(ROOT/"V39K_REPLACEMENT_BACKUP_MANIFEST.json",backups)
    ordered=sorted(staged,key=lambda r: 0 if Path(r).is_relative_to(REL) else 3 if r==(CLOSE/"PRODUCTION_REFREEZE_AUTHORITY.json").as_posix() else 2 if r==(FULL/"V39E_FULL_PREFLIGHT.json").as_posix() else 1)
    for rel in ordered:copy_atomic(STAGE/rel,LIVE/rel)
    save(ROOT/"V39K_APPLY_RECEIPT.json",dict(status="APPLIED_GATE_STILL_HOLD",files=staged,backup_SHA256=backups,source_changes=0,at=now()))
    verify_live(before)
    # Exercise the existing cheap resume/readiness path with its compatibility bindings.
    oldcheap=LIVE/CLOSE/"CHEAP_31_DAY_READINESS.json"
    if oldcheap.exists():copy_atomic(oldcheap,LIVE/REL/"before_integration"/CLOSE/oldcheap.name)
    load_ready_refreeze(LIVE)
    live_ready=read(oldcheap);assert live_ready["READY"]==31
    save(LIVE/REL/"V39K_31DAY_READINESS.json",dict(**live_ready,phase="LIVE_HOLD_RETAINED",certified_production_fallback_migrations=105,
        invalid_repair_dependencies=0,gate_state="FOUR_HOLDS_RETAINED_PENDING_RELEASE"))
    print("LIVE APPLY AND NATIVE CHEAP READINESS PASS; four HOLDs retained",flush=True)


def verify_live(before):
    assert source_shas()==before["live_source_SHA256"]
    assert git("rev-parse","HEAD")==before["LIVE_HEAD"] and git("branch","--show-current")==before["LIVE_BRANCH"]
    current=da_shas();expected=check_changed_cases(before["all_124_DA_freeze_SHA256"],current)
    staged=read(ROOT/"V39K_STAGING_SHA_MANIFEST.json")["files"]
    for n in expected:assert current[n]==staged[(FULL/n).as_posix()]
    protected_check(before)
    auth=read(LIVE/CLOSE/"PRODUCTION_REFREEZE_AUTHORITY.json")
    assert auth["DA_freeze_file_SHA256"]==current and auth["minimum_RUNNING_migrations"]==105
    assert sha(LIVE/FULL/"V39E_FULL_PREFLIGHT.json")==auth["production_preflight_SHA256"]
    total=0
    for day in AXIS:
        for case in CASES:
            f=decision(LIVE/FULL/fname(day,case));tr=loader(day,case,False)
            assert tr.fingerprints["V39E_DA_decision_SHA256"]==f["DA_decision_SHA256"]
            if day in DAYS and case in ("B1","B3"):
                d=f["decision"];b=decision(LIVE/CLOSE/"before_refreeze"/fname(day,case))["decision"]
                assert {k:v for k,v in d.items() if k!="temporal_repair_authority"}==b
                bind=d["temporal_repair_authority"]
                assert bind["TEMPORAL_REPAIR_USED"] is False and sha(LIVE/bind["certificate_path"])==bind["certificate_SHA256"]
        total+=sum(r.get("migration_selected",False) for r in f["decision"]["AIDC_assignments"])
    assert total==105
    return current


def release():
    before=read(ROOT/"V39K_PREINTEGRATION_LIVE_SNAPSHOT.json")
    assert read(LIVE/REL/"V39K_TEST_REPORT.json")["status"]=="PASS"
    verify_live(before)
    for d in DAYS:assert read(LIVE/REL/"days"/d/"V39K_FALLBACK_CERTIFICATE.json")["status"]=="PASS"
    assert read(LIVE/REL/"V39K_SELECTIVE_PREFLIGHT_SUMMARY.json")["status"]=="PASS"
    assert read(LIVE/REL/"V39K_CHANGE_IMPACT_AUDIT.json")["UNEXPECTED_CHANGED_DAY_CASES"]==0
    assert read(LIVE/REL/"V39K_31DAY_READINESS.json")["READY"]==31
    assert not invalid_actual()
    ps=processes();workers=[r for r in ps if "day" in r]
    assert len({r["day"] for r in workers})==len(workers)
    assert [r["ProcessId"] for r in ps if "run_v39h_production_close.py" in r["CommandLine"]]==before["orchestrator_PID"]
    old=read(LIVE/GATE);assert sha(LIVE/GATE)==before["launch_gate_SHA256"]
    copy_atomic(LIVE/GATE,LIVE/REL/"before_integration"/GATE)
    ns={};exec(compile((LIVE/"dayahead/tools/v39h_terminal_launch_gate.py").read_text(),"gate","exec"),ns)
    assert all(ns["admission"](LIVE,d)["release"] is False for d in DAYS)
    new=deepcopy(old)
    new.update(audit_complete=True,classification="V39K_CERTIFIED_FALLBACK_INTEGRATED_READY_31",V39J_integration_status="SUPERSEDED_BY_V39K_COMPLETE",
        superseding_authority=(REL/"V39K_PRODUCTION_INTEGRATION_AUTHORITY.json").as_posix(),superseding_authority_SHA256=sha(LIVE/REL/"V39K_PRODUCTION_INTEGRATION_AUTHORITY.json"))
    for day in DAYS:
        new["dates"][day].update(release=True,status="RELEASE_V39K_CERTIFIED_BASE_RSP_MIGRATION_FALLBACK",fallback_migrations=COUNTS[day],
            certificate_path=(REL/"days"/day/"V39K_FALLBACK_CERTIFICATE.json").as_posix(),certificate_SHA256=sha(LIVE/REL/"days"/day/"V39K_FALLBACK_CERTIFICATE.json"),released_at=now())
    save(LIVE/GATE,new)
    assert all(ns["admission"](LIVE,d)["release"] is True for d in AXIS)
    receipt=dict(status="PASS",released_days=list(DAYS),before_gate_SHA256=before["launch_gate_SHA256"],after_gate_SHA256=sha(LIVE/GATE),released_at=now(),
        selective_preflight="FOUR_PASS",change_impact="PASS",READY=31,duplicate_day_workers=0,
        held_workers_before=[r for r in workers if r["day"] in DAYS],held_worker_behavior="Existing worker entry waits before runtime/Actual and rereads JSON every 10s; no held workers present at release" if not any(r["day"] in DAYS for r in workers) else "Waiting worker dynamically rereads gate; no restart",
        process_adjustments=0,orchestrator_restart=False,invalid_Actual_output_present=False,entry_policy="Corrected frozen authority from day entry; no invalid checkpoint resume")
    save(LIVE/REL/"V39K_HOLD_RELEASE_RECEIPT.json",receipt)
    readiness=read(LIVE/REL/"V39K_31DAY_READINESS.json");readiness.update(phase="LIVE_RELEASED",gate_state="MAY23_26_RELEASED",release_gate_SHA256=sha(LIVE/GATE));save(LIVE/REL/"V39K_31DAY_READINESS.json",readiness)
    print("RELEASE PASS: May23-26 dynamically admitted, no process restarts",flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("phase",choices=["snapshot","prepare","apply","release"]);args=parser.parse_args()
    globals()[args.phase]()
