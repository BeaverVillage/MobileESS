"""Read-only May23 targeted audit. Writes only a separate worktree report.

D+1 snapshot/DA is an explicitly requested retrospective comparison, never
an input to May23 construction, feasibility, or terminal-site authority.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import sys
from datetime import datetime, timezone

WORK = Path(__file__).resolve().parents[2]
LIVE = Path(r"C:\codex_mobileess_workspace\MobileESS_v39a_causal_aidc")
OUT = WORK / "dayahead/artifacts/v39j_may23_targeted_terminal_audit"
FULL = LIVE / "dayahead/artifacts/v39e_full_may_2025"
CLOSE = LIVE / "dayahead/artifacts/v39h_production_refreeze_may_close"
HROOT = LIVE / "dayahead/artifacts/v39h_13day_temporal_repair_migration_shadow"
DAY = "2025-05-23"
IDS = tuple(str(x) for x in range(9062282, 9062287))
H = 120
sys.path.insert(0, str(WORK))
sys.dont_write_bytecode = True
os.environ.update(OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", MKL_NUM_THREADS="1")

import numpy as np
import pandas as pd
import gurobipy as gp
from dayahead.tools import run_v39j_terminal_repair as j
from dayahead.v39j import terminal as t
from dayahead.v38.authority import canonical_sha256, load_wan_authority, checkpoint_slots
from dayahead.v38.wan import validate_fixed_path_transfers
from dayahead.v39c.evaluate import _elapsed_seconds


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def clean(value):
    return j.h.v39g.clean(value)


def save(name, value):
    path = OUT / name
    path.write_text(json.dumps(clean(value), indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def guard(event, args):
    if event == "open":
        path, mode, flags = args
        if isinstance(path, int):
            return
        p = Path(path).resolve()
        writing = bool((flags or 0) & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
        if writing and not p.is_relative_to(OUT):
            raise PermissionError(f"MAY23_AUDIT_WRITE_OUTSIDE_REPORT:{p}")
        if not writing and p.suffix.lower() in (".json", ".parquet", ".npz", ".csv", ".h5"):
            name = p.as_posix().lower()
            if any(x in name for x in ("/actual/", "/fresh/", "_actual_", "_fresh_", "/dates/")):
                raise PermissionError(f"MAY23_AUDIT_RESULT_READ:{p}")
    elif event in ("os.remove", "os.rmdir", "os.mkdir", "os.rename", "os.replace"):
        paths = args[:2] if event in ("os.rename", "os.replace") else args[:1]
        for path in paths:
            if not Path(path).resolve().is_relative_to(OUT):
                raise PermissionError(f"MAY23_AUDIT_MUTATION_OUTSIDE_REPORT:{path}")


def forbidden_solver(*args, **kwargs):
    raise AssertionError("NO_SOLVER_MODEL_OR_OPTIMIZATION_ALLOWED")


def freeze(folder, day, case):
    path = folder / f"V39E_DAYAHEAD_DECISION_FREEZE_{day}_{case}.json"
    f = read(path)
    assert canonical_sha256(f["decision"]) == f["DA_decision_SHA256"]
    return path, f["decision"]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    sys.addaudithook(guard)
    gp.Model = forbidden_solver
    gp.Env = forbidden_solver
    manifest = read(j.ROOT / "V39J_SOURCE_AUTHORITY_MANIFEST.json")
    before_source = {p: sha(LIVE / p) for p in manifest["live_source_SHA256"]}
    assert before_source == manifest["live_source_SHA256"]
    before_da = {p.name: sha(p) for p in FULL.glob("V39E_DAYAHEAD_DECISION_FREEZE_*.json")}
    assert len(before_da) == 124
    gate_path = LIVE / "dayahead/artifacts/v39h_terminal_state_audit/TERMINAL_AUDIT_LAUNCH_GATE.json"
    gate_sha = sha(gate_path)
    seal = read(CLOSE / "PRODUCTION_CLOSE_START_STATE.json")
    basepath, base = freeze(CLOSE / "before_refreeze", DAY, "B1")
    livepath, repair = freeze(FULL, DAY, "B1")
    assert sha(basepath) == seal["before_refreeze_SHA256"][basepath.name]
    authority = read(CLOSE / "PRODUCTION_REFREEZE_AUTHORITY.json")
    assert sha(livepath) == authority["DA_freeze_file_SHA256"][livepath.name]
    certpath = LIVE / repair["temporal_repair_authority"]["certificate_path"]
    cert = read(certpath)
    assert sha(certpath) == repair["temporal_repair_authority"]["certificate_SHA256"]
    assert sha(LIVE / repair["temporal_repair_authority"]["temporal_schedule_authority_path"]) == repair["temporal_schedule_SHA256"]
    provenance = {str(basepath): sha(basepath), str(livepath): sha(livepath), str(certpath): sha(certpath)}
    for raw, expected in cert["frozen_input_SHA256"].items():
        assert sha(raw) == expected, raw
        provenance[raw] = expected
    hseal = read(HROOT / "V39H_REQUIRED_ARTIFACT_SHA_MANIFEST.json")["SHA256"]
    for name in ("V39H_SHADOW_SCHEDULE.parquet", "V39G_C1_INTEGER_TABLES.npz", "V39G_FROZEN_GRID_COEFFICIENTS.npz"):
        rel = f"days/{DAY}/{name}"
        expected = next((v for k, v in hseal.items() if k.replace("\\", "/") == rel), None)
        if expected is not None:
            assert sha(HROOT / rel) == expected
        else:
            assert name.endswith(".npz")  # Derived caches; newly captured, not falsely claimed sealed.
        provenance[str(HROOT / rel)] = sha(HROOT / rel)
    old = pd.read_parquet(HROOT / "days" / DAY / "V39H_SHADOW_SCHEDULE.parquet").sort_values("job_uid").reset_index(drop=True)
    a = old.copy()
    baseline = {r["job_id"]: r for r in base["temporal_schedule"]}
    current = {r["job_id"]: r for r in repair["temporal_schedule"]}
    ba = {r["job_uid"]: r for r in base["AIDC_assignments"]}
    ra = {r["job_uid"]: r for r in repair["AIDC_assignments"]}
    initial = {r["job_uid"]: r["initial_AIDC"] for r in repair["common_initial_RUNNING_AIDC_state"]}
    assert set(baseline) == set(current) == set(old.job_uid)
    rows = []
    for r in old.itertuples(index=False):
        b, c = baseline[r.job_uid], current[r.job_uid]
        assert (b["scheduled_start_slot"], b["scheduled_end_slot"], b["duration_slots"]) == (r.RSP_scheduled_start, r.RSP_scheduled_completion, r.RSP_duration_slots)
        assert (c["scheduled_start_slot"], c["scheduled_end_slot"]) == (r.scheduled_start_slot, r.scheduled_end_slot)
        assert c["duration_slots"] == b["duration_slots"] and c["requested_gpus"] == b["requested_gpus"]
        cross = b["scheduled_start_slot"] < H < b["scheduled_end_slot"]
        base_state = (initial[r.job_uid] if r.state_at_issue == "RUNNING" else ba[r.job_uid]["destination_AIDC"]) if cross else "UNASSIGNED"
        repair_state = ra[r.job_uid]["destination_AIDC"] if cross else "UNASSIGNED"
        if r.RSP_scheduled_start >= H:
            assert r.job_uid not in ba and r.job_uid not in ra
        if cross and r.state_at_issue == "RUNNING":
            assert repair_state == initial[r.job_uid]
        tail_same = (b["scheduled_start_slot"], b["scheduled_end_slot"]) == (c["scheduled_start_slot"], c["scheduled_end_slot"]) if b["scheduled_end_slot"] > H else c["scheduled_end_slot"] <= H
        rows.append(dict(job_uid=r.job_uid, qos=r.qos, state_at_issue=r.state_at_issue,
            V39H_temporal_eligible=bool(r.eligible), requested_GPU=int(r.requested_gpus),
            RSP_start=b["scheduled_start_slot"], RSP_end=b["scheduled_end_slot"],
            repair_start=c["scheduled_start_slot"], repair_end=c["scheduled_end_slot"],
            cross_boundary=cross, baseline_terminal_site=base_state, repair_terminal_site=repair_state,
            terminal_timing_equal=tail_same, terminal_site_equal=base_state == repair_state,
            post_H_occupied_slots=max(0,b["scheduled_end_slot"]-max(H,b["scheduled_start_slot"]))))
    audit = pd.DataFrame(rows)
    bad = audit.loc[~audit.terminal_site_equal].copy()
    assert set(bad.job_uid) == set(IDS) and audit.terminal_timing_equal.all()
    assert not bad.V39H_temporal_eligible.any()
    # D+1 is used here only after the May23 verdict is established.
    snap24path = LIVE / "dayahead/artifacts/v37_r4a_per_day_aidc/days/2025-05-24/V37_R4A_D1_SNAPSHOT.parquet"
    snap24 = pd.read_parquet(snap24path)
    provenance[str(snap24path)] = sha(snap24path)
    dplus = {}
    for folder in (FULL, CLOSE / "before_refreeze"):
        for case in ("B0", "B1", "B2", "B3"):
            p, dec = freeze(folder, "2025-05-24", case)
            provenance[str(p)] = sha(p)
            dplus[folder.name + "_" + case] = dec
    targeted = []
    for r in bad.to_dict("records"):
        uid = r["job_uid"]
        s = snap24.loc[snap24.id.astype(str).eq(uid)]
        r.update(frozen_base_RSP_site=ba[uid]["destination_AIDC"],repair_site=ra[uid]["destination_AIDC"],
            post_H_occupancy_interval=[H,r["RSP_end"]],
            terminal_site_authority="SAME_DAY_FROZEN_CROSS_BOUNDARY_LABEL_PRESERVATION; NOT_POST_H_GRID_CERTIFICATION",
            DA_physical_active_interval=[ba[uid]["active_start_slot"], ba[uid]["active_end_slot"]],
            target_slot_offset_from_issue=24,
            Dplus1_snapshot_present=len(s)==1,
            Dplus1_snapshot_state=s.iloc[0].state_at_issue if len(s) else "ABSENT_NOT_PROOF_OF_COMPLETION_OR_UNASSIGNED",
            Dplus1_snapshot_issue_AEST=str(s.iloc[0].issue_time_fixed_AEST) if len(s) else "2025-05-23T18:00:00+10:00",
            Dplus1_snapshot_measured_site_field_present=False,
            Dplus1_DA={k:[{x:q.get(x) for x in ("state_at_issue","initial_AIDC","destination_AIDC","migration_selected")} for q in dec["AIDC_assignments"] if q["job_uid"]==uid] for k,dec in dplus.items()},
            verdict="CROSS_BOUNDARY_TERMINAL_SITE_STATE_CHANGED")
        targeted.append(r)
    audit.to_csv(OUT / "MAY23_ALL_JOB_TERMINAL_COMPARISON.csv", index=False)
    pd.DataFrame(targeted).to_csv(OUT / "MAY23_FIVE_JOB_COMPARISON.csv", index=False)
    save("MAY23_FIVE_JOB_COMPARISON.json", targeted)
    result = dict(MAY23_TERMINAL_CONSISTENCY="FAIL", audited_jobs=len(audit),
        cross_boundary_PENDING_jobs=int((audit.cross_boundary & audit.state_at_issue.eq("PENDING")).sum()),
        terminal_site_changed_jobs=len(bad), terminal_timing_changed_jobs=0,
        incremental_post_midnight_GPU_h=0,
        per_job_site_symmetric_post_H_deviation_GPU_h=float((bad.requested_GPU*bad.post_H_occupied_slots*2).sum()/4),
        contract="BASELINE_RELATIVE_PER_JOB_TERMINAL_STATE_PRESERVATION",
        normal_qos_is_not_terminal_site_exemption=True,
        clipped_physical_trajectory_is_not_terminal_UNASSIGNED_evidence=True,
        Dplus1_is_independent_day_retrospective_only=True,
        Dplus1_snapshot_precedes_May23_H_by_hours=6,
        Dplus1_absence_does_not_establish_completed_or_UNASSIGNED=True,
        terminal_site_verdict_requires_no_future_data=True,
        earlier_May23_terminal_consistent_claim_superseded=True,
        candidate_101_not_final=True, no_exception_allowlist=True,
        optimization_calls=0, Actual_result_reads=0, Fresh_result_reads=0,
        physical_grid_domain_issue_slots=[24,120], new_post_H_grid_authority=False)
    save("MAY23_TERMINAL_AUDIT_RESULT.json",result)
    print("MAY23_TERMINAL_CONSISTENCY=FAIL; site differences=5; timing differences=0", flush=True)
    # Verify the already-selected original four-migration witness, unchanged.
    bundle = j.verifier_bundle(HROOT / "days" / DAY)
    cap, sites = bundle["capacity"], bundle["sites"]
    occ = np.zeros((96,len(sites)), dtype=np.int64)
    assert len(ba) == len(base["AIDC_assignments"])
    for q in ba.values():
        site, g = q["destination_AIDC"], int(q["requested_GPU"])
        assert cap.eligible_racks(site,g)
        occ[q["active_start_slot"]:q["active_end_slot"],sites.index(site)] += g
    assert (occ <= np.array([cap.site_capacity[s] for s in sites])).all()
    saved_gpu = pd.DataFrame(base["site_GPU_trajectory"]).pivot(index="slot",columns="AIDC",values="active_GPU").loc[range(96),list(sites)].to_numpy(int)
    assert np.array_equal(saved_gpu,occ)
    pcc = np.array([[bundle["tables"][s][slot,occ[slot,k]] for k,s in enumerate(sites)] for slot in range(96)])
    oldpcc = pd.DataFrame(base["site_PCC_power_trajectory"]).pivot(index="slot",columns="AIDC",values="PCC_P_kW").loc[range(96),list(sites)].to_numpy(float)
    assert np.allclose(pcc,oldpcc,atol=1e-8,rtol=0)
    grid = j.h.grid.evaluate(bundle["coefficients"],bundle["nodes"],pcc)
    assert grid["pass"]
    assert abs(grid["Vmax"]-base["planning_feasibility"]["Vmax_pu"]) < 1e-10
    assert abs(grid["Vmin"]-base["planning_feasibility"]["Vmin_pu"]) < 1e-10
    selected = [q for q in ba.values() if q.get("migration_selected")]
    ma = CLOSE / "before_refreeze/V39E_TEMPORAL_FIRST_MIGRATION_AUDIT.json"
    assert sha(ma) == seal["before_refreeze_SHA256"][ma.name]
    record = next(r for r in read(ma)["days"] if r["operating_day"]==DAY)
    assert len(selected)==4==record["solver_proven_minimum_RUNNING_migrations"]
    assert base["migration_state"]["WAN_transfer_count"]==4
    wan = load_wan_authority(WORK)
    snap23 = pd.read_parquet(LIVE / f"dayahead/artifacts/v37_r4a_per_day_aidc/days/{DAY}/V37_R4A_D1_SNAPSHOT.parquet")
    transfers=[]
    for q in selected:
        assert q["state_at_issue"]=="RUNNING" and q["source_AIDC"]!=q["destination_AIDC"]
        amounts = q["WAN_bytes_by_slot"]
        slots = [k for k,n in enumerate(amounts) if n]
        assert len(amounts)==96 and all(int(n)==n and n>=0 for n in amounts)
        assert sum(amounts)==wan.payload_bytes(q["requested_GPU"])
        assert q["fixed_WAN_path_id"]==wan.path_id(q["source_AIDC"],q["destination_AIDC"])
        assert tuple(q["fixed_WAN_path_links"])==wan.path(q["source_AIDC"],q["destination_AIDC"])
        assert q["migration_checkpoint_slot"]<=min(slots)<=max(slots)==q["WAN_transfer_complete_slot"]
        assert q["destination_READY_slot"]==max(slots)+1
        assert q["restart_complete_slot"]==q["destination_READY_slot"]+1
        assert q["migration_checkpoint_slot"] in checkpoint_slots(_elapsed_seconds(snap23,q["job_uid"]),q["active_end_slot"]-q["active_start_slot"])
        transfers.append(dict(job_uid=q["job_uid"],source_AIDC=q["source_AIDC"],destination_AIDC=q["destination_AIDC"],bytes_by_slot=amounts))
    wancheck=validate_fixed_path_transfers(wan,transfers)
    assert wancheck["status"]=="PASS"
    b3path,b3=freeze(CLOSE/"before_refreeze",DAY,"B3")
    assert sha(b3path)==seal["before_refreeze_SHA256"][b3path.name]
    assert {k:v for k,v in b3.items() if k!="case"}=={k:v for k,v in base.items() if k!="case"}
    fallback=dict(status="PASS_EXISTING_FALLBACK_AVAILABLE_NOT_INTEGRATED",day=DAY,
        existing_solver_proven_minimum_RUNNING_migrations=4,original_solver_certificate=record,
        original_B1_SHA256=sha(basepath),original_B3_SHA256=sha(b3path),original_migration_audit_SHA256=sha(ma),
        base_RSP_timing_runtime_GPU_exact=True,existing_migration_witness_exact=True,
        site_capacity="PASS",Rack_compatibility="PASS",gang_splits=0,
        derived_grid_cache_SHA_scope="CAPTURED_AT_AUDIT; raw D1 inputs verified against sealed production certificate; replay agrees with sealed original planning verdict",
        C1_max_error_kW=float(np.max(np.abs(pcc-oldpcc))),grid=grid,WAN_checkpoint_restart=wancheck,
        terminal_incremental_GPU_h=0,terminal_site_changes_vs_original_fallback=0,
        no_new_migration_solution=True,optimization_calls=0,migration_MILP_calls=0,
        revised_four_day_fallback_candidate_migrations=105,previous_101_candidate_superseded=True,
        live_migration_accounting_not_changed=True,
        does_not_prove_no_alternative_terminal_safe_May23_repair=True)
    save("MAY23_EXISTING_FOUR_MIGRATION_FALLBACK_CHECK.json",fallback)
    provenance[str(b3path)]=sha(b3path);provenance[str(ma)]=sha(ma)
    save("MAY23_AUDIT_SOURCE_PROVENANCE.json",dict(status="PASS",SHA256=provenance,
        accepted_production_fingerprint=manifest["accepted_implementation_fingerprint_sha256"],
        diagnostic_script_SHA256=sha(__file__)))
    assert before_da=={p.name:sha(p) for p in FULL.glob("V39E_DAYAHEAD_DECISION_FREEZE_*.json")}
    assert before_source=={p:sha(LIVE/p) for p in before_source}
    assert gate_sha==sha(gate_path)
    save("MAY23_READ_ONLY_PRESERVATION.json",dict(status="PASS",completed_at=datetime.now(timezone.utc).isoformat(),
        live_DA_SHA256=before_da,live_source_SHA256=before_source,launch_gate_SHA256=gate_sha,
        DA_authorities_changed=0,live_source_changes=0,live_gate_changes=0,
        optimization_calls=0,Actual_result_reads=0,Fresh_result_reads=0,Dplus1_reads="EXPLICIT_RETROSPECTIVE_AUDIT_ONLY"))
    print("MAY23_FALLBACK=PASS; minimum migrations=4; revised candidate=105; live writes=0",flush=True)


if __name__ == "__main__":
    main()
