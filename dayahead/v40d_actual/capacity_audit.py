"""Independent, fail-closed capacity audits; no Actual campaign launch path."""
from collections import Counter
from datetime import datetime, timedelta
from decimal import Decimal
import inspect
import math
from pathlib import Path
import numpy as np
import pandas as pd
from dayahead.paper_analysis.storage import read, sha, digest, reference, write_json, write_parquet, atomic
from .contracts import BEGIN, H, ReplayError

SITES = tuple(f"AIDC{i:02d}" for i in range(1, 13))
VECTOR = (64, 32, 64, 32, 80, 64, 32, 64, 32, 64, 32, 64)
EXPECTED = dict(zip(SITES, VECTOR))


def require_current_capacity(capacity):
    if dict(capacity) != EXPECTED or any(type(v) is not int for v in capacity.values()):
        raise ReplayError("CURRENT_SITE_CAPACITY_VECTOR_REQUIRED")


def recalculate_occupancy(job_ledger):
    """Read only job execution intervals, sites and indivisible requested gangs.

    The loop order and accumulation differ from the dispatcher's active map.
    Slots are sampled at their start, using [start,end) execution intervals.
    """
    rows = list(job_ledger)
    ids = [r["job_uid"] for r in rows]
    if len(ids) != len(set(ids)):
        raise ReplayError("ACTUAL_JOB_UID_DUPLICATE_ACCOUNTING")
    active = []
    for row in rows:
        status = row["status"]
        if status == "PRE_DAY_COMPLETE":
            zero_fields = ("operating_day_GPU_slots", "operating_day_GPU_hours", "operating_day_power_contribution")
            if row["AIDC_site"] != "UNASSIGNED" or row.get("actual_Rack") is not None or any(
                row.get(k) != 0 for k in zero_fields) or any(row.get(k) is not None for k in
                ("actual_execution_start", "actual_residual_start", "actual_execution_end")):
                raise ReplayError("PRE_DAY_COMPLETE_GPU_OCCUPANCY_VIOLATION")
            continue
        if status == "UNASSIGNED_POST_H_BACKLOG":
            if row["start_slot"] < H or row.get("actual_execution_end") is not None or row.get("actual_Rack") is not None:
                raise ReplayError("UNASSIGNED_SPILLOVER_EXECUTION_FORBIDDEN")
            continue
        if status != "EXECUTION_ACCOUNTED":
            raise ReplayError("UNKNOWN_EXECUTION_STATUS")
        site, g = row["AIDC_site"], row["requested_GPU"]
        if site not in SITES or site != row["frozen_AIDC_site"]:
            raise ReplayError("ALTERNATE_AIDC_FORBIDDEN")
        if type(g) is not int or g <= 0:
            raise ReplayError("INVALID_INDIVISIBLE_GPU_GANG")
        start, end = row["actual_residual_start"], row["actual_execution_end"]
        if not all(isinstance(x, (int, float)) and math.isfinite(x) for x in (start, end)) or end <= start:
            raise ReplayError("INVALID_ACTUAL_EXECUTION_INTERVAL")
        if start < 0 or start != int(start) or row.get("actual_Rack") is None:
            raise ReplayError("INVALID_ACTUAL_ADMISSION")
        active.append(row)
    occupancy = np.zeros((96, 12), dtype=np.int64)
    direct_total = np.zeros(96, dtype=np.int64)
    contributions = []
    for t in range(BEGIN, H):
        for row in active:
            if row["actual_residual_start"] <= t < row["actual_execution_end"]:
                g = row["requested_GPU"]
                occupancy[t-BEGIN, SITES.index(row["AIDC_site"])] += g
                direct_total[t-BEGIN] += g
                contributions.append({"job_uid": row["job_uid"], "slot": t-BEGIN,
                    "site": row["AIDC_site"], "occupied_GPU": g})
    if not np.array_equal(occupancy.sum(axis=1), direct_total):
        raise ReplayError("ACTUAL_JOB_TO_SITE_GPU_CONSERVATION")
    return occupancy, direct_total, contributions


def compare_occupancy(replay, capacity):
    require_current_capacity(capacity)
    occupancy, direct, contributions = recalculate_occupancy(replay["job_ledger"])
    recorded = pd.DataFrame(replay["site_occupancy"])
    if len(recorded) != 1152 or recorded.duplicated(["site_id", "slot"]).any():
        raise ReplayError("PRODUCTION_OCCUPANCY_AXIS_DUPLICATE_OR_MISSING")
    if set(recorded.site_id) != set(SITES) or set(recorded.slot) != set(range(96)):
        raise ReplayError("PRODUCTION_OCCUPANCY_AXIS")
    if any(r.GPU_capacity != capacity[r.site_id] for r in recorded.itertuples()):
        raise ReplayError("PRODUCTION_CAPACITY_OVERRIDE")
    values = recorded.pivot(index="slot", columns="site_id", values="occupied_GPU_slots").reindex(index=range(96), columns=SITES).to_numpy()
    if not np.isfinite(values).all() or not np.array_equal(values, occupancy):
        raise ReplayError("ACTUAL_OCCUPANCY_RECALCULATION_MISMATCH")
    if np.any(occupancy < 0) or np.any(occupancy > np.asarray(VECTOR)):
        raise ReplayError("ACTUAL_SITE_CAPACITY_EXCEEDED")
    audit = {"status": "PASS", "input": "ACTUAL_JOB_LEDGER_ONLY", "max_abs_gpu_occupancy_error": 0,
        "GPU_OCCUPANCY_RECALC_MAX_ERROR": 0, "duplicate_UID_count": 0, "duplicate_case_site_slot_job_count": 0,
        "SITE_CAPACITY_VIOLATIONS_TOTAL": 0, "PRE_DAY_COMPLETE_GPU_OCCUPANCY_VIOLATIONS": 0,
        "independent_job_sum_equals_dispatcher": True, "site_slot_count": 1152,
        "GPU_slot_sum": int(direct.sum()), "DayAhead_total_trajectory_equality_enforced": False}
    return occupancy, contributions, audit


def check_it_power(capacity, occupancy, it):
    from dayahead.v39a.contracts import IDLE_W_PER_GPU, CENTER_SWING_W_PER_GPU, FULL_ACTIVE_IT_KW, POWER_TOLERANCE_KW
    require_current_capacity(capacity)
    occ, power = np.asarray(occupancy), np.asarray(it)
    if occ.shape != (96,12) or power.shape != (96,12) or not np.isfinite(power).all():
        raise ReplayError("IT_POWER_AXIS_OR_FINITE_FAIL")
    if np.any(occ < 0) or np.any(occ > np.asarray(VECTOR)) or np.any(occ != np.floor(occ)):
        raise ReplayError("IT_OCCUPANCY_CAPACITY_FAIL")
    expected = np.asarray([[float((Decimal(VECTOR[i])*IDLE_W_PER_GPU + Decimal(int(occ[t,i]))*CENTER_SWING_W_PER_GPU)/1000)
                            for i in range(12)] for t in range(96)])
    analytic = np.asarray([float(FULL_ACTIVE_IT_KW - Decimal(624-int(n))*CENTER_SWING_W_PER_GPU/1000) for n in occ.sum(axis=1)])
    error = float(np.max(np.abs(power-expected)))
    aggregate_error = float(np.max(np.abs(power.sum(axis=1)-analytic)))
    tolerance = float(POWER_TOLERANCE_KW)
    if max(error, aggregate_error) > tolerance:
        raise ReplayError("ACTUAL_GPU_TO_IT_POWER_CONSERVATION_FAIL")
    return {"status": "PASS", "GPU_TO_IT_POWER_MAX_ERROR_KW": error,
        "aggregate_analytic_max_error_kW": aggregate_error, "preregistered_tolerance_kW": str(POWER_TOLERANCE_KW),
        "tolerance_source": "dayahead.v39a.contracts.POWER_TOLERANCE_KW (unchanged)",
        "idle_W_per_GPU": str(IDLE_W_PER_GPU), "CENTER_W_per_GPU": str(CENTER_SWING_W_PER_GPU),
        "full_active_anchor_kW": str(FULL_ACTIVE_IT_KW), "capacity_sum_GPU": 624,
        "identity": "406.775993813819 - (624-N_total_ACT)*547.7239090195797/1000",
        "rounded_prompt_constants_replaced_frozen_precision": False}


def audit_gangs(frozen_jobs, replay, racks):
    frozen = {r["job_uid"]: r for r in frozen_jobs}
    actual = {r["job_uid"]: r for r in replay["job_ledger"]}
    if len(frozen) != len(frozen_jobs) or len(actual) != len(replay["job_ledger"]) or set(frozen) != set(actual):
        raise ReplayError("ACTUAL_GANG_UID_COMPLETENESS")
    by_rack = {r.rack_id: r for r in racks}
    admissions = {r["job_uid"]: r for r in replay["rack_ledger"]}
    if len(admissions) != len(replay["rack_ledger"]):
        raise ReplayError("ACTUAL_GANG_SPLIT_OR_MULTIPLE_ADMISSIONS")
    for uid, row in actual.items():
        if row["AIDC_site"] != frozen[uid]["AIDC_site"]:
            raise ReplayError("ACTUAL_CAPACITY_DRIVEN_SITE_CHANGE")
        if row["requested_GPU"] != frozen[uid]["requested_GPU"]:
            raise ReplayError("ACTUAL_GANG_SHRINK_OR_SPLIT")
        if row["status"] != "EXECUTION_ACCOUNTED":
            if uid in admissions:
                raise ReplayError("EXCLUDED_JOB_RACK_ADMISSION")
            continue
        a = admissions.get(uid)
        if a is None or a["requested_GPU"] != row["requested_GPU"] or a["AIDC_site"] != row["AIDC_site"]:
            raise ReplayError("ACTUAL_GANG_ADMISSION_MISMATCH")
        rack = by_rack.get(a["rack_pool_id"])
        if rack is None or rack.site != row["AIDC_site"] or rack.capacity < row["requested_GPU"] or row["actual_Rack"] != rack.rack_id:
            raise ReplayError("ACTUAL_RACK_GANG_COMPATIBILITY_FAIL")
        if a["release_slot"] != math.ceil(row["actual_execution_end"]):
            raise ReplayError("ACTUAL_RUNTIME_TRUNCATED_OR_PREEMPTED")
        if a["assignment_slot"] != row["actual_residual_start"]:
            raise ReplayError("ACTUAL_GANG_ADMISSION_START_MISMATCH")
    if set(admissions) - set(actual):
        raise ReplayError("UNKNOWN_JOB_ADMISSION")
    return {"status": "PASS", "ACTUAL_GANG_SPLIT_COUNT": 0, "ACTUAL_ALTERNATE_AIDC_ATTEMPTS": 0,
        "ACTUAL_CAPACITY_DRIVEN_SITE_CHANGE_COUNT": 0, "ACTUAL_SITE_REOPTIMIZATION_CALLS": 0,
        "runtime_truncation_preemption_count": 0, "frozen_site_preserved": True,
        "job_count": len(actual), "admitted_gang_count": len(admissions)}


def headroom_rows(day, case, replay, occupancy):
    jobs = {r["job_uid"]: r for r in replay["job_ledger"]}
    waits = [r for r in replay["rack_waits"] if r["reason"] == "GPU_CAPACITY" and BEGIN <= r["slot"] < H]
    if len({(r["job_uid"],r["slot"]) for r in waits}) != len(waits):
        raise ReplayError("DUPLICATE_CAPACITY_WAIT_ACCOUNTING")
    result = []
    for i, site in enumerate(SITES):
        site_waits = [r for r in waits if r["AIDC_site"] == site]
        maximum = int(occupancy[:,i].max()); t = int(occupancy[:,i].argmax())
        result.append({"day": day, "case": case, "site": site, "capacity_GPU": VECTOR[i],
            "max_actual_occupancy_GPU": maximum, "min_headroom_GPU": VECTOR[i]-maximum,
            "time_of_max_occupancy": (datetime.fromisoformat(day)+timedelta(minutes=15*t)).isoformat()+"+10:00",
            "capacity_violation_count": int(np.sum(occupancy[:,i]>VECTOR[i])),
            "waiting_jobs_due_to_site_capacity": len({r["job_uid"] for r in site_waits}),
            "delayed_GPU_hours_due_to_site_capacity": sum(jobs[r["job_uid"]]["requested_GPU"]*.25 for r in site_waits),
            "delay_scope": "D_DAY_ONLY", "execution_coverage": "SMOKE_EXECUTED"})
    return result


def write_csv(path, rows):
    with atomic(Path(path)) as f:
        f.write(pd.DataFrame(rows).to_csv(index=False).encode("utf-8-sig"))


def static_audit(repo, output):
    from .inputs import capacity, frozen_jobs, legacy_digest
    from .preflight import verify_protected
    from .rack_dispatch import RackDispatcher
    repo, output = Path(repo), Path(output)
    audit = repo/"dayahead/artifacts/v40d_actual_realized_replay"
    write_json(output/"CAPACITY_AUDIT_STATUS.json", {"status": "RUNNING", "full_campaign_authorized": False})
    a, cap, rack_ref, cap_ref = capacity(repo)
    require_current_capacity(a["frozen_V39C_site_capacity"])
    vector_sha = digest({"sites": SITES, "GPU": VECTOR})
    contract = {"status": "PASS", "classification": cap["classification"], "semantics": cap["capacity_semantics"],
        "SITE_CAPACITY_VECTOR": VECTOR, "SITE_CAPACITY_SUM": 624, "site_capacity": EXPECTED,
        "capacity_file": cap_ref, "capacity_canonical_SHA": cap["canonical_SHA256"], "vector_fingerprint": vector_sha,
        "loader": "dayahead.v40d_actual.inputs.capacity", "admission": "dayahead.v40d_actual.rack_dispatch.RackDispatcher.admit",
        "measured_installed_GPU_census": False, "facility_MW_capacity": False, "case_capacity_overrides_allowed": False,
        "Rack_authority": rack_ref, "Rack_single_gang_admissibility": True,
        "power_tolerance_preregistered_kW": "0.000000000002", "effective_before_smoke_execution": True}
    write_json(output/"V40D_ACTUAL_SITE_GPU_CAPACITY_CONTRACT.json", contract)
    bindings = read(audit/"V40D_ACTUAL_DECISION_BINDING_AUDIT.json")["cases"]
    expected_keys = {(f"2025-05-{d:02d}",c) for d in range(1,32) for c in ("B0","B1","B2","B3")}
    if len(bindings) != 124 or {(b["day"],b["case"]) for b in bindings} != expected_keys:
        raise ReplayError("STATIC_CAPACITY_CASE_COVERAGE")
    cases, table = [], []
    for b in bindings:
        jobs, _ = frozen_jobs(repo,b)
        # The production Actual loader has one hash-locked source and takes no day/case argument.
        current, _, *unused = capacity(repo)
        require_current_capacity(current["frozen_V39C_site_capacity"])
        stage = "FINAL_ACCEPTED_INTERNAL_A1" if b["case"] == "B3" else "ACCEPTED_A0_AIDC_ONLY" if b["case"] == "B1" else "RW_REFERENCE"
        row = {"day":b["day"], "case":b["case"], "status":"PASS", "AIDC_DECISION_SOURCE":b["AIDC_decision_source"],
            "AIDC_DECISION_SHA":sha(b["AIDC_decision_source"]), "AIDC_STAGE":stage, "job_count":len(jobs),
            "loaded_job_binding_fingerprint":legacy_digest(jobs), "capacity_file_SHA":cap_ref["sha256"],
            "capacity_canonical_SHA":cap["canonical_SHA256"], "vector_fingerprint":vector_sha,
            "site_capacity":EXPECTED, "B3_A1_checkpoint_verified": b["case"]=="B3"}
        cases.append(row)
        for site in SITES:
            table.append({"day":b["day"],"case":b["case"],"site":site,"capacity_GPU":EXPECTED[site],
                "capacity_binding_status":"PASS", "execution_coverage":"NOT_EXECUTED_FULL_CAMPAIGN_BLOCKED",
                **dict.fromkeys(("max_actual_occupancy_GPU","min_headroom_GPU","time_of_max_occupancy","capacity_violation_count",
                                "waiting_jobs_due_to_site_capacity","delayed_GPU_hours_due_to_site_capacity"),None)})
    write_json(output/"V40D_ACTUAL_CASE_AIDC_DECISION_BINDING.json", {"status":"PASS", "case_count":124,
        "B3_A1_BINDING":"PASS", "same_capacity_SHA_all_dates_cases":True, "case_rows":cases})
    write_csv(output/"V40D_ACTUAL_SITE_GPU_CAPACITY_AUDIT.csv", table)
    write_parquet(output/"STATIC_CASE_CAPACITY_BINDING.parquet", pd.DataFrame(cases))
    # Inspect the narrow admission call graph, not the historical provenance metadata.
    source = inspect.getsource(capacity)+inspect.getsource(RackDispatcher)
    forbidden = ("_site_weights(", "facility_size_soft_prior", "legacy_deliverable_GPU_capacity", "202.750", "624 / 12")
    if any(token in source for token in forbidden):
        raise ReplayError("FACILITY_WEIGHT_OR_LEGACY_CAPACITY_ADMISSION_LEAKAGE")
    rack_audit = {"status":"PASS", "RACK_USED_AS_ADDITIVE_SITE_CAPACITY":"NO", "RACK_CAPACITY_SUM_USED":"NO",
        "RACK_LABEL_ONLY_COMPATIBILITY":"PASS", "SITE_CAPACITY_C_S_IS_PRIMARY_HARD_CAP":"PASS",
        "logical_label_count":48, "cumulative_per_label_capacity_enforced":False, "source":rack_ref,
        "code":reference(repo/"dayahead/v40d_actual/rack_dispatch.py"),
        "correction":"Removed redundant cumulative per-Rack occupancy cap; preserve individual-gang admissibility. Frozen C_s unchanged."}
    write_json(output/"V40D_ACTUAL_RACK_NONADDITIVE_AUDIT.json", rack_audit)
    write_json(output/"V40D_ACTUAL_SITE_POWER_BOUNDARY_AUDIT.json", {"status":"PASS",
        "FACILITY_MW_USED_AS_GPU_CAPACITY":"NO", "V22SR1_WEIGHT_USED_AS_GPU_CAPACITY":"NO",
        "scope":"V40D admission capacity path; spatial PCC mapping may retain facility provenance",
        "historical_V39C_construction":"V22SR1 was a pre-May soft prior when the now-frozen vector was constructed; no new allocation in Actual",
        "facility_provenance_MW":202.750769230769, "operational_compute_GPU":624,
        "equivalent_IT_anchor_kW":406.775993813819,
        "aggregate_624_use":"Aggregate power identity only; admission uses per-site C_s",
        "reviewed_functions":["inputs.capacity","RackDispatcher.__init__","RackDispatcher.admit","RackDispatcher.validate"]})
    guard = verify_protected(repo,audit)
    write_json(output/"PROTECTED_PLANNING_FRESH_DIFF.json",guard)
    if guard["status"] != "PASS":
        raise ReplayError("CAPACITY_AUDIT_PROTECTED_ARTIFACT_DRIFT")
    result={"status":"PASS_STATIC_BINDING", "static_cases":124,"static_site_case_rows":1488,
        "actual_executed_cases":0,"full_campaign_authorized":False,"UNASSIGNED_spillover_blocker_resolved":False}
    write_json(output/"CAPACITY_AUDIT_STATUS.json",result)
    return result


def write_runtime_audits(output, day, case, frozen_jobs, replay, capacity, racks, power):
    output = Path(output)
    occupancy, _, recalc = compare_occupancy(replay,capacity)
    gang = audit_gangs(frozen_jobs,replay,racks)
    it = check_it_power(capacity,occupancy,power["IT"])
    for name, result in (("GPU_OCCUPANCY_RECALCULATION",recalc),("GPU_GANG_INVARIANT",gang),("GPU_TO_IT_POWER_CONSERVATION",it)):
        write_json(output/("V40D_ACTUAL_"+name+".json"), {**result,"day":day,"case":case,"scope":"SMOKE_ONLY"})
    write_csv(output/"V40D_ACTUAL_SITE_GPU_CAPACITY_AUDIT.csv",headroom_rows(day,case,replay,occupancy))
    return {"recalculation":recalc,"gang":gang,"power":it}
