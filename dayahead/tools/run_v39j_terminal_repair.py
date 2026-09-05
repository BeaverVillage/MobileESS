"""Three-day V39J certification. Every write is confined to its own artifacts.

Exact integer infeasibility certificates are checked before reserving any
Gurobi capacity. There is no campaign, refreeze, or migration-solver caller.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import inspect
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from types import FunctionType, SimpleNamespace

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits
from dayahead.tools import run_v39h_shadow as h
from dayahead.v39j import terminal as t

ROOT = REPO / "dayahead/artifacts/v39j_terminal_consistent_temporal_repair"
HROOT = REPO / "dayahead/artifacts/v39h_13day_temporal_repair_migration_shadow"
CLOSE = REPO / "dayahead/artifacts/v39h_production_refreeze_may_close"
BASE = CLOSE / "before_refreeze"
THREADS = 1
SAFE_SOLVER_BUDGET = 16


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic(path, data):
    path = Path(path).resolve()
    assert path.is_relative_to(ROOT.resolve()), path
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(h.v39g.clean(data), indent=2, ensure_ascii=False,
                               allow_nan=False) + "\n", encoding="utf-8")
    os.replace(temp, path)


def guard_path(path, writing=False):
    if isinstance(path, int):
        return
    p = Path(path).resolve()
    if writing and not p.is_relative_to(ROOT.resolve()):
        raise PermissionError(f"V39J_WRITE_OUTSIDE_ARTIFACTS:{p}")
    if not writing and p.suffix.lower() in (".json", ".parquet", ".npz", ".csv", ".h5", ".npy"):
        name = str(p).replace("\\", "/").lower()
        if any(k in name for k in ("/actual/", "/fresh/", "_actual_", "_fresh_", "/dates/")):
            raise PermissionError(f"V39J_FORBIDDEN_RESULT_READ:{p}")
        if not p.is_relative_to(ROOT.resolve()):
            dates = set(re.findall(r"2025-05-\d{2}", name))
            if dates - set(t.DAYS):
                raise PermissionError(f"V39J_OTHER_DAY_INPUT_READ:{p}")


def install_io_guard():
    """Guard runner writes and data reads, including imported dependencies."""
    def audit(event, args):
        if event == "open":
            path, mode, flags = args
            writing = bool((flags or 0) & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
            guard_path(path, writing)
        elif event in ("os.remove", "os.rmdir", "os.mkdir"):
            guard_path(args[0], True)
        elif event in ("os.rename", "os.replace"):
            guard_path(args[0], True)
            guard_path(args[1], True)
    sys.addaudithook(audit)


def prepare(day):
    assert day in t.DAYS
    out = ROOT / "days" / day
    out.mkdir(parents=True, exist_ok=True)
    manifest = read(ROOT / "V39J_SOURCE_AUTHORITY_MANIFEST.json")
    pinned = manifest["copied_authority_SHA256"]
    for rel, expected in pinned.items():
        # Other target dates are allowed frozen authorities, not future
        # observations; each day uses only its own data for its model.
        if day in rel or not re.search(r"2025-05-\d{2}", rel):
            assert sha(REPO / rel) == expected, rel
    source_pins = manifest["accepted_source_SHA256"]
    for module in (Path(h.__file__), Path(h.v39g.__file__), Path(h.grid.__file__),
                   REPO / "dayahead/tools/v39g_shadow_grid.py"):
        assert sha(module) == source_pins[module.relative_to(REPO).as_posix()]
    authority = read(HROOT / "V39H_REQUIRED_ARTIFACT_SHA_MANIFEST.json")["SHA256"]
    for name, expected in authority.items():
        if f"days/{day}/" in name.replace("\\", "/") and (HROOT / name).is_file():
            assert sha(HROOT / name) == expected, name
    dr = REPO / f"dayahead/artifacts/v37_r4a_per_day_aidc/days/{day}"
    a = pd.read_parquet(dr / "V37_R4A_JOB_LEDGER.parquet")
    a["job_uid"] = a.job_id.astype(str)
    a = a.sort_values("job_uid").reset_index(drop=True)
    snapshot = pd.read_parquet(dr / "V37_R4A_D1_SNAPSHOT.parquet")
    snapshot["job_uid"] = snapshot.id.astype(str)
    excluded = pd.read_parquet(dr / "V37_R4A_EXCLUSIONS.parquet")
    excluded_ids = set(excluded.job_id.astype(str)) if len(excluded) else set()
    assert a.job_uid.is_unique and snapshot.job_uid.is_unique
    assert set(a.job_uid) | excluded_ids == set(snapshot.job_uid)
    assert not set(a.job_uid) & excluded_ids
    snapshot = snapshot.set_index("job_uid").loc[a.job_uid]
    issue = pd.Timestamp(day, tz=timezone(timedelta(hours=10))) - pd.Timedelta(hours=6)
    a["D1_visible"] = (pd.to_datetime(snapshot.submit_time, utc=True) <= issue.tz_convert("UTC")).to_numpy()
    assert a.D1_visible.all() and set(snapshot.issue_time_fixed_AEST) == {issue.isoformat()}
    assert np.array_equal(a.qos, snapshot.qos) and np.array_equal(a.state_at_issue, snapshot.state_at_issue)
    a["eligible"] = h.v39g.eligible_mask(a)
    a["latest_start"] = np.where(a.eligible, a.RW_scheduled_completion-a.RSP_duration_slots,
                                  a.RSP_scheduled_start).astype(int)
    rw = read(BASE / f"V39E_DAYAHEAD_DECISION_FREEZE_{day}_B0.json")["decision"]
    rsp = read(BASE / f"V39E_DAYAHEAD_DECISION_FREEZE_{day}_B1.json")["decision"]
    backup_seal=read(CLOSE/"PRODUCTION_CLOSE_START_STATE.json")["before_refreeze_SHA256"]
    for case in ("B0","B1"):
        name=f"V39E_DAYAHEAD_DECISION_FREEZE_{day}_{case}.json"
        assert sha(BASE/name)==backup_seal[name]
        freeze=read(BASE/name)
        from dayahead.v38.authority import canonical_sha256
        assert canonical_sha256(freeze["decision"])==freeze["DA_decision_SHA256"]
        assert freeze["SHA_created_before_Actual_namespace"]
    assert rw["temporal_mode"] == "RW" and rsp["temporal_mode"] == "RSP"
    initial = {r["job_uid"]: r["initial_AIDC"] for r in rw["common_initial_RUNNING_AIDC_state"]}
    a["initial_AIDC"] = a.job_uid.map(initial).fillna("")
    old = pd.read_parquet(HROOT / "days" / day / "V39H_SHADOW_SCHEDULE.parquet")
    for col in a:
        assert np.array_equal(a[col].fillna("<NA>"), old[col].fillna("<NA>")), col
    assert np.array_equal(a.RSP_scheduled_start+a.RSP_duration_slots, a.RSP_scheduled_completion)
    assert np.array_equal(a.RW_scheduled_start+a.RW_duration_slots, a.RW_scheduled_completion)
    assert (a.RSP_duration_slots > 0).all()
    saved = pd.DataFrame(rsp["temporal_schedule"]).set_index("job_id").loc[a.job_uid]
    assert np.array_equal(saved.scheduled_start_slot, a.RSP_scheduled_start)
    assert np.array_equal(saved.scheduled_end_slot, a.RSP_scheduled_completion)
    assert np.array_equal(saved.duration_slots, a.RSP_duration_slots)
    assert np.array_equal(saved.requested_gpus, a.requested_gpus)
    assignment = {r["job_uid"]: r for r in rsp["AIDC_assignments"]}
    sites, reasons = [], []
    for r in a.itertuples(index=False):
        if r.RSP_scheduled_completion <= t.H:
            site, reason = t.UNASSIGNED, "EMPTY_POST_H_PROFILE"
        elif r.state_at_issue == "RUNNING":
            site, reason = initial[r.job_uid], "MIGRATION_OFF_FROZEN_INITIAL_SITE"
        elif r.RSP_scheduled_start < t.H:
            frozen = assignment[r.job_uid]
            assert frozen["state_at_issue"] == "PENDING" and not frozen["migration_selected"]
            assert frozen["requested_GPU"] == r.requested_gpus
            site, reason = frozen["destination_AIDC"], "PRE_REFREEZE_RSP_PENDING_SITE"
        else:
            assert r.job_uid not in assignment
            site, reason = t.UNASSIGNED, "FROZEN_UNASSIGNED_STATE_USER_CONFIRMED"
        sites.append(site)
        reasons.append(reason)
    a["baseline_terminal_site"], a["baseline_terminal_site_authority"] = sites, reasons
    a["v39h_eligible"] = a.eligible
    a["terminal_category"] = [t.terminal_category(s,e) for s,e in zip(a.RSP_scheduled_start,a.RSP_scheduled_completion)]
    a["eligible"] = a.v39h_eligible & a.terminal_category.eq("IN_DAY_COMPLETE")
    cert = read(HROOT / "days" / day / "V39H_OBJECTIVE_CERTIFICATES.json")["stages"][1]
    assert cert["optimal"] and cert["gap"] == 0
    assert abs(cert["objective"]-t.OLD_PRIMARY[day]) < 1e-6
    assert abs(cert["bound"]-t.OLD_PRIMARY[day]) < 1e-6
    assert int(old.occupancy_deviation_GPU_slots.sum()) == t.OLD_PRIMARY[day]
    for name in ("V39G_FROZEN_GRID_COEFFICIENTS.npz", "V39G_C1_INTEGER_TABLES.npz"):
        src, dst = HROOT / "days" / day / name, out / name
        if not dst.exists():
            shutil.copyfile(src, dst)
        assert sha(src) == sha(dst)
    a.to_parquet(out / "V39J_MODEL_JOB_INPUTS.parquet", index=False)
    atomic(out / "V39J_INPUT_AUTHORITY.json", dict(day=day, old_primary_certificate=cert,
        eligible_jobs=int(a.eligible.sum()), baseline_overnight_jobs=int(a.RSP_scheduled_completion.gt(t.H).sum()),
        wholly_post_H_unassigned_jobs=int(a.RSP_scheduled_start.ge(t.H).sum()),
        original_V39H_eligibility_preserved_in_column="v39h_eligible",
        eligibility_change="Exclude CROSS_BOUNDARY and POST_H_ONLY as explicitly required by addendum",
        actual_reads=0, fresh_reads=0, future_observation_reads=0,
        source_overlay_pinned=True, old_schedule_SHA256=sha(HROOT / "days" / day / "V39H_SHADOW_SCHEDULE.parquet")))
    return a, old, rsp, out


def objective_identity():
    """Reconstruct the actual V39H objective from sealed source and witnesses."""
    manifest=read(ROOT / "V39J_SOURCE_AUTHORITY_MANIFEST.json")
    evidence=manifest["accepted_H_formulation_equivalence"]
    for name,expected in evidence["unchanged_formulation_function_SHA"].items():
        assert h.digest(inspect.getsource(getattr(h,name))) == expected
    assert sha(Path(h.v39g.__file__)) == evidence["V39G_helper_SHA"]
    assert sha(Path(h.grid.__file__)) == evidence["grid_helper_SHA"]
    function=inspect.getsource(h.v39g.occupancy_cost)
    builder=inspect.getsource(h.build_model)
    assert "return 2*gpu*min(start-start0,duration)" in function
    assert 'v39g.occupancy_cost(c["lo"],c["d"],start,c["g"])' in builder
    assert 'for obj,weight in zip(objs,' in builder and 'obj.addTerms(weight,v)' in builder
    witnesses=[]
    for day in t.DAYS:
        oldpath=HROOT/"days"/day/"V39H_SHADOW_SCHEDULE.parquet"
        certpath=HROOT/"days"/day/"V39H_OBJECTIVE_CERTIFICATES.json"
        b=pd.read_parquet(oldpath)
        horizon=max(int(b.RSP_scheduled_completion.max()),int(b.scheduled_end_slot.max()))
        explicit=0
        for r in b.itertuples(index=False):
            base=np.zeros(horizon,dtype=np.int64)
            repaired=np.zeros(horizon,dtype=np.int64)
            base[int(r.RSP_scheduled_start):int(r.RSP_scheduled_completion)]=int(r.requested_gpus)
            repaired[int(r.scheduled_start_slot):int(r.scheduled_end_slot)]=int(r.requested_gpus)
            per_job=int(np.abs(base-repaired).sum())
            assert per_job == h.v39g.occupancy_cost(int(r.RSP_scheduled_start),int(r.duration_slots),int(r.scheduled_start_slot),int(r.requested_gpus))
            explicit += per_job
        c=read(certpath)["stages"][1]
        assert c["optimal"] and c["gap"]==0 and math.ceil(c["bound"])==t.OLD_PRIMARY[day]
        assert explicit == t.OLD_PRIMARY[day] == int(b.occupancy_deviation_GPU_slots.sum())
        witnesses.append(dict(day=day,explicit_per_job_symmetric_occupancy_GPU_slots=explicit,
            certified_global_lower_bound=t.OLD_PRIMARY[day],saved_raw_lower_bound=c["bound"],
            schedule_SHA256=sha(oldpath),certificate_SHA256=sha(certpath)))
    audit=dict(PRIMARY_OBJECTIVE_IDENTITY_PASS="YES",
        exact_J="sum_j sum_t g_j * abs(1_[s0_j,s0_j+d_j)(t) - 1_[s_j,s_j+d_j)(t)) = sum_j 2*g_j*min(s_j-s0_j,d_j)",
        absolute_value_inside_job_sum=True,aggregate_net_load_absolute_value=False,
        aggregation="Per-job symmetric reservation deviation summed; identical cohort counts multiply the same coefficient",
        GPU_weighting="Immutable integer requested GPUs",slot_weighting="1 per integer 15-minute slot",
        time_domain="Complete reservation intervals, including pre-day and post-H; no clipping to [24,120)",
        site_dimension_in_objective=False,site_placement_change_objective_cost=0,
        factor_of_two=True,one_way_GPU_slots="J/2",symmetric_GPU_hours="J/4",
        one_way_GPU_hours="J/8",omitted_constant_terms=0,
        upper_bound="For each job, delta_max=max allowed start minus RSP start; U=sum_j 2*g_j*min(delta_max,d_j). Monotone per-job cost, relaxation of all coupling constraints: a rigorous upper bound, not a lower bound.",
        source_function=function,source_builder=builder,
        source_function_SHA256=h.digest(function),source_builder_SHA256=h.digest(builder),
        source_seal=manifest["accepted_H_model_source_hashes"],witnesses=witnesses)
    atomic(ROOT/"V39J_PRIMARY_OBJECTIVE_IDENTITY_AUDIT.json",audit)
    return audit


def verifier_bundle(out):
    cap,_=h._load_capacity(REPO)
    coeff,nodes=h.grid.load_coefficients(out)
    with np.load(out/"V39G_C1_INTEGER_TABLES.npz") as z:
        tables={s:z[s].copy() for s in cap.aidc_ids}
    return dict(capacity=cap,sites=tuple(cap.aidc_ids),coefficients=coeff,nodes=nodes,tables=tables)


def configure(model, out, name):
    model.Params.Threads = THREADS
    model.Params.Seed = h.SEED
    model.Params.MIPGap = model.Params.MIPGapAbs = 0
    model.Params.FeasibilityTol = 1e-8
    model.Params.IntFeasTol = 1e-9
    model.Params.LogToConsole = 0
    model.Params.LogFile = str(out / f"{name}.log")


def terminal_options(cohort, sites):
    if cohort["terminal_category"] == "POST_H_ONLY" and cohort["terminal_site"] == t.UNASSIGNED:
        assert cohort["lo"] == cohort["hi"] and cohort["lo"] >= t.H
        yield t.UNASSIGNED, cohort["lo"]
    else:
        yield from h.candidate_options(cohort, sites)


def build_model(a, out):
    """Use frozen V39H science with only exact terminal-domain refinement."""
    ns = dict(h.build_model.__globals__)
    original_api = dict(h.v39g.__dict__)
    original_api["cohorts"] = t.terminal_cohorts
    def model_atomic(path,data):
        if "outside_domain_site_elimination" in data:
            data={**data,"outside_domain_site_elimination":"POST_H_ONLY retains UNASSIGNED; no physical AIDC variable. No off-domain grid constraint is introduced."}
        atomic(path,data)
    ns.update(v39g=SimpleNamespace(**original_api), configure=configure,
              atomic=model_atomic,candidate_options=terminal_options)
    builder = FunctionType(h.build_model.__code__, ns, h.build_model.__name__, h.build_model.__defaults__)
    bundle = builder(a, out, "V39J_TERMINAL_MODEL")
    for (k, site, start), var in bundle["variables"].items():
        c = bundle["cohorts"][k]
        state = c["terminal_site"] if c["lo"] >= t.H else site
        assert t.compact_allowed(c["lo"], c["d"], c["terminal_site"], start, state)
    atomic(out / "V39J_FORMULATION.json", dict(model_variables=bundle["model"].NumVars,
        model_constraints=bundle["model"].NumConstrs, cohorts=len(bundle["cohorts"]),
        full_V39H_builder_reused=True, per_job_terminal_options_checked=True,
        configured_threads_per_model=THREADS, optimize_calls=0,
        outside_domain_site_label="UNASSIGNED in both model keys and exported state; no invented AIDC",
        physical_grid_domain=[24,120], migration_variables=0))
    return bundle


def expand_schedule(a,bundle):
    """Bijective whole-job expansion including explicitly unassigned tails."""
    selected={}
    for k,c in enumerate(bundle["cohorts"]):
        options=[]
        for (group,site,start),var in sorted(bundle["variables"].items()):
            if group==k:
                count=round(var.X)
                assert abs(var.X-count)<1e-6
                options.extend([(site,start)]*count)
        assert len(options)==len(c["members"])
        selected.update(zip(sorted(c["members"]),options))
    assert set(selected)==set(a.job_uid)
    b=a.copy()
    b["AIDC"]=[selected[u][0] for u in b.job_uid]
    b["scheduled_start_slot"]=[selected[u][1] for u in b.job_uid]
    b["duration_slots"]=b.RSP_duration_slots.astype(int)
    b["scheduled_end_slot"]=b.scheduled_start_slot+b.duration_slots
    b["start_delay_slots"]=b.scheduled_start_slot-b.RSP_scheduled_start
    b["terminal_site_state"]=b.AIDC
    b["occupancy_deviation_GPU_slots"]=[h.v39g.occupancy_cost(int(r.RSP_scheduled_start),int(r.duration_slots),int(r.scheduled_start_slot),int(r.requested_gpus)) for r in b.itertuples()]
    assert t.terminal_audit(a,b)[1]["PASS"]
    return b


def verify_capacity_proof(a, rsp, proof, capacity):
    """Independent checker: raw rows/authorities, no cohort or option helper."""
    lookup = a.set_index("job_uid")
    assignments = {r["job_uid"]: r for r in rsp["AIDC_assignments"]}
    assert proof["status"] == "INFEASIBLE" and proof["violations"]
    for row in proof["violations"]:
        slot, site = row["issue_slot"], row["site"]
        assert 24 <= slot < 120 and row["site_capacity"] == capacity[site]
        assert len({j["job_uid"] for j in row["jobs"]}) == len(row["jobs"])
        total = 0
        for j in row["jobs"]:
            r = lookup.loc[j["job_uid"]]
            assert r.RSP_scheduled_start <= slot < r.RSP_scheduled_completion
            assert j["start"] == r.RSP_scheduled_start and j["end"] == r.RSP_scheduled_completion
            assert j["requested_GPU"] == r.requested_gpus
            if r.state_at_issue == "RUNNING":
                assert r.initial_AIDC == site and not r.eligible
            else:
                # Post-H nonempty profile plus immutable duration forces the
                # complete original interval/site, including its in-day part.
                assert r.RSP_scheduled_completion > 120
                b = assignments[j["job_uid"]]
                assert b["state_at_issue"] == "PENDING" and not b["migration_selected"]
                assert b["destination_AIDC"] == site
            total += int(r.requested_gpus)
        assert total == row["mandatory_GPU"] and total > capacity[site]
    return dict(status="PASS", all_rows_independently_checked=len(proof["violations"]),
                integer_arithmetic=True, cohort_builder_used=False, solver_needed=False)


def verify_fallback(a, rsp, out, bundle, day):
    # Reuse the original frozen witness validator with a read-only BASE path;
    # this function contains no optimize or migration-solver invocation.
    ns = dict(h.migration_confirmation.__globals__)
    ns.update(BASE=BASE, atomic=lambda p,d: atomic(Path(p).with_name(Path(p).name.replace("V39H", "V39J")), d))
    confirm = FunctionType(h.migration_confirmation.__code__, ns)
    migration = confirm(day, a, out)
    cap, sites = bundle["capacity"], bundle["sites"]
    occ = np.zeros((96,12), dtype=np.int64)
    assignments = rsp["AIDC_assignments"]
    assert len({r["job_uid"] for r in assignments}) == len(assignments)
    rack_fail = 0
    for r in assignments:
        s, g = r["destination_AIDC"], int(r["requested_GPU"])
        occ[int(r["active_start_slot"]):int(r["active_end_slot"]), sites.index(s)] += g
        rack_fail += not bool(cap.eligible_racks(s,g))
    saved_gpu = pd.DataFrame(rsp["site_GPU_trajectory"]).pivot(index="slot",columns="AIDC",values="active_GPU").loc[range(96),list(sites)].to_numpy(int)
    assert np.array_equal(occ,saved_gpu) and not rack_fail
    assert (occ <= np.array([cap.site_capacity[s] for s in sites])).all()
    pcc = np.asarray([[bundle["tables"][s][slot,occ[slot,k]] for k,s in enumerate(sites)] for slot in range(96)])
    saved_pcc = pd.DataFrame(rsp["site_PCC_power_trajectory"]).pivot(index="slot",columns="AIDC",values="PCC_P_kW").loc[range(96),list(sites)].to_numpy(float)
    assert np.allclose(saved_pcc,pcc,atol=1e-8,rtol=0)
    grid = h.grid.evaluate(bundle["coefficients"],bundle["nodes"],pcc)
    assert grid["pass"] and grid["Vmax"] <= 1.05 and grid["Vmin"] >= .95
    # Terminal audit describes original RSP + its original migration witness.
    # It is NOT a successful zero-migration repair or a partially repaired input.
    baseline = a.copy()
    amap = {r["job_uid"]: r["destination_AIDC"] for r in assignments}
    baseline["baseline_terminal_site"] = [amap.get(r.job_uid,t.UNASSIGNED) if r.RSP_scheduled_completion > t.H else t.UNASSIGNED for r in a.itertuples(index=False)]
    b = baseline.copy()
    b["scheduled_start_slot"] = a.RSP_scheduled_start
    b["scheduled_end_slot"] = a.RSP_scheduled_completion
    b["duration_slots"] = a.RSP_duration_slots
    b["terminal_site_state"] = baseline.baseline_terminal_site
    rows, terminal = t.terminal_audit(baseline,b)
    assert terminal["PASS"]
    pd.DataFrame(rows).assign(scope="ORIGINAL_RSP_PLUS_ORIGINAL_MIGRATION_WITNESS_NO_REPAIR").to_csv(out / "V39J_TERMINAL_AUDIT.csv",index=False)
    # Exact frozen artifact bytes are the fallback deliverable authority.
    src = BASE / f"V39E_DAYAHEAD_DECISION_FREEZE_{day}_B1.json"
    shutil.copyfile(src,out / "V39J_FALLBACK_FROZEN_B1.json")
    assert sha(src) == sha(out / "V39J_FALLBACK_FROZEN_B1.json")
    result = dict(status="PASS", candidate="UNCHANGED_BASE_RSP_PLUS_EXISTING_MINIMUM_MIGRATION",
        grid=grid, site_capacity="PASS", Rack_compatibility="PASS", gang_splits=0,
        C1_inner_polygon="PASS", frozen_C1_max_error_kW=float(np.max(np.abs(saved_pcc-pcc))),
        upper_voltage_headroom_pu=1.05-grid["Vmax"], lower_voltage_headroom_pu=grid["Vmin"]-.95,
        safe_runtime_exact_preservation=True, GPU_request_preservation=True,
        RW_completion_noninferiority=True, newly_introduced_RW_completion_violations=0,
        RUNNING_migrations=t.BASE_MIGRATIONS[day], RUNNING_migration_solver_calls=0,
        Actual_reads=0, Fresh_reads=0, future_observation_reads=0,
        physical_grid_certification_domain=[24,120], outside_domain_grid_certification=False,
        terminal_repair_success_claim=False, terminal_audit_scope="FALLBACK_RELATIVE_TO_ORIGINAL_FALLBACK",
        original_witness_SHA256=sha(src), frozen_migration_validation=migration,
        terminal=terminal)
    atomic(out / "V39J_GRID_VERIFICATION.json",result)
    return result


def numerical_capacity_available(live_workers, held_days):
    """Conservative reserved budget; do not borrow transient idle CPU time."""
    admitted = sum(w["day"] not in held_days for w in live_workers)
    return admitted * 4 + THREADS <= SAFE_SOLVER_BUDGET


def run_day(day):
    identity=read(ROOT/"V39J_PRIMARY_OBJECTIVE_IDENTITY_AUDIT.json")
    assert identity["PRIMARY_OBJECTIVE_IDENTITY_PASS"]=="YES"
    a, old, rsp, out = prepare(day)
    cap,_ = h._load_capacity(REPO)
    capacity_proof = t.mandatory_capacity_certificate(a,cap.site_capacity)
    objective_proof = t.primary_upper_certificate(a,t.OLD_PRIMARY[day])
    atomic(out / "V39J_PRIMARY_UPPER_BOUND_CERTIFICATE.json",objective_proof)
    analytic=objective_proof["infeasible_by_lower_greater_than_upper"]
    model=None
    if analytic:
        # Addendum fast path: no Gurobi model or old-primary feasibility solve.
        bundle=verifier_bundle(out)
        atomic(out/"V39J_ANALYTIC_INFEASIBILITY_CERTIFICATE.json",dict(
            label="TERMINAL_SAFE_REPAIR_ANALYTIC_INFEASIBILITY_CERTIFICATE",
            proof_classification="EMPTY_INTERSECTION_BY_OLD_GLOBAL_LOWER_BOUND_AND_TERMINAL_DOMAIN_UPPER_BOUND",
            day=day,L_old=t.OLD_PRIMARY[day],U_terminal=objective_proof["terminal_domain_objective_upper"],
            strict_inequality=True,PRIMARY_OBJECTIVE_IDENTITY_PASS="YES",
            exact_J=identity["exact_J"],provenance=next(w for w in identity["witnesses"] if w["day"]==day),
            derivation=objective_proof,no_solver_called=True))
    else:
        # May24: instantiate primary=108 plus all hard constraints; the exact
        # mandatory-row presolver resolves feasibility without numerical search.
        bundle = build_model(a,out)
        model = bundle["model"]
        equality = model.addConstr(bundle["objectives"][0] == t.OLD_PRIMARY[day],name="OLD_CERTIFIED_PRIMARY_EXACT_EQUALITY")
        model.setObjective(0,h.GRB.MINIMIZE)
        model.update()
        assert equality.RHS == t.OLD_PRIMARY[day] and equality.Sense == "="
    assert capacity_proof["status"] == "INFEASIBLE", "No exact presolve proof: numerical feasibility requires a free reserved production slot."
    check = verify_capacity_proof(a,rsp,capacity_proof,cap.site_capacity)
    atomic(out / "V39J_CAPACITY_INFEASIBILITY_CERTIFICATE.json",dict(**capacity_proof,independent_verification=check))
    stage_a = dict(stage="A_OLD_PRIMARY_FEASIBILITY",status="SKIPPED_ANALYTIC_EMPTY_SET" if analytic else "INFEASIBLE",
        old_primary_exact_equality=t.OLD_PRIMARY[day], objective="CONSTANT_ZERO",
        method=capacity_proof["method"], Gurobi_status=None, optimize_calls=0,
        proof_file="V39J_CAPACITY_INFEASIBILITY_CERTIFICATE.json",independently_verified=True)
    atomic(out / "V39J_STAGE_A_FEASIBILITY.json",stage_a)
    if model is not None:
        model.remove(equality)
        model.update()
        assert not any(c.ConstrName == "OLD_CERTIFIED_PRIMARY_EXACT_EQUALITY" for c in model.getConstrs())
    stage_b = dict(stage="B_ANY_TERMINAL_SAFE_REPAIR_FEASIBILITY",status="INFEASIBLE",
        primary_equality_removed=True,objective="CONSTANT_ZERO",method=capacity_proof["method"],
        Gurobi_status=None,optimize_calls=0,proof_independent_of_primary=True,
        independent_objective_bound_contradiction=objective_proof["infeasible_by_lower_greater_than_upper"],
        proof_file="V39J_CAPACITY_INFEASIBILITY_CERTIFICATE.json")
    atomic(out / "V39J_STAGE_B_FEASIBILITY.json",stage_b)
    atomic(out/"V39J_TERMINAL_FEASIBILITY_RESULT.json",dict(day=day,status="INFEASIBLE_PROVEN_ANALYTICALLY" if analytic else "INFEASIBLE_PROVEN_BY_EXACT_CAPACITY_PRESOLVE",stage_a=stage_a,stage_b=stage_b,solver_calls=0))
    (out / "V39J_FEASIBILITY_CERTIFICATION.log").write_text(
        f"{day}\nStage A: exact integer mandatory-capacity contradiction, INFEASIBLE.\n"
        "Stage B: remove primary equality; same contradiction, INFEASIBLE.\n"
        "Gurobi optimize calls: 0. No Gurobi infeasibility status claimed.\n"
        "Primary optimization and migration MILP calls: 0.\n",encoding="utf-8")
    verified = verify_fallback(a,rsp,out,bundle,day)
    old_delta = sum(int(r.requested_gpus)*(max(0,int(r.scheduled_end_slot)-max(120,int(r.scheduled_start_slot)))-max(0,int(r.RSP_scheduled_completion)-max(120,int(r.RSP_scheduled_start)))) for r in old.itertuples(index=False))/4
    result = dict(day=day,status="CERTIFIED_INFEASIBLE_FALLBACK_VERIFIED",
        TERMINAL_SAFE_REPAIR="INFEASIBLE_PROVEN_ANALYTICALLY" if analytic else "INFEASIBLE_PROVEN_BY_EXACT_CAPACITY_PRESOLVE",terminal_safe_repair_pass=False,
        old_primary_optimum=t.OLD_PRIMARY[day],new_primary_optimum=None,
        old_primary_retained=False, primary_optimality="NO_TERMINAL_SAFE_FEASIBLE_SET",
        old_changed_jobs=int(old.start_delay_slots.gt(0).sum()),new_changed_jobs=0,
        old_max_delay_minutes=int(old.start_delay_slots.max())*15,new_max_delay_minutes=0,
        old_incremental_post_midnight_GPU_h=old_delta,new_incremental_post_midnight_GPU_h=0,
        old_migrations=0,original_baseline_migrations=t.BASE_MIGRATIONS[day],
        resulting_migrations=t.BASE_MIGRATIONS[day],fallback_required=True,
        stage_a=stage_a,stage_b=stage_b,first_capacity_contradiction=capacity_proof["violations"][0],
        upper_bound_on_any_terminal_domain_primary=objective_proof["terminal_domain_objective_upper"],
        terminal=verified["terminal"],grid=verified["grid"],
        terminal_audit_scope="UNCHANGED_BASE_RSP_PLUS_EXISTING_MIGRATION; NO_REPAIR_CANDIDATE_ACCEPTED",
        primary_optimization_calls=0,migration_MILP_calls=0,full_13day_rerun=False,full_31day_rerun=False,
        Gurobi_models_assembled=int(model is not None),Gurobi_optimize_calls=0,actual_solver_threads=0,
        source_model_fingerprint=int(model.Fingerprint) if model is not None else None, completed_at=datetime.now(timezone.utc).isoformat())
    atomic(out / "V39J_RESULT.json",result)
    if model is not None:
        model.dispose()
    print(day,result["status"],"migrations",result["resulting_migrations"],flush=True)
    return result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--day",choices=t.DAYS)
    args=parser.parse_args()
    ROOT.mkdir(parents=True,exist_ok=True)
    tmp=ROOT/"temp"
    tmp.mkdir(exist_ok=True)
    os.environ.update(TEMP=str(tmp),TMP=str(tmp),PYTHONDONTWRITEBYTECODE="1")
    sys.dont_write_bytecode=True
    install_io_guard()
    with threadpool_limits(limits=1):
        objective_identity()
        for day in (args.day,) if args.day else t.DAYS:
            run_day(day)


if __name__ == "__main__":
    main()
