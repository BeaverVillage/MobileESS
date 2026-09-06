"""Audit all accepted cases. Failure records remain separate from science outputs."""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import io
from pathlib import Path
import zipfile
import pandas as pd
import pyarrow.parquet as pq
from dayahead.paper_analysis.storage import read, sha, reference, write_json, write_parquet
from .contracts import write_contracts, ReplayError
from .inputs import capacity, frozen_jobs, observations
from .job_replay import validate_jobs, timestamp
from .pre_day_complete import classify


def verify_protected(repo, audit):
    rows = read(Path(audit) / "V40D_PROTECTED_PLANNING_MANIFEST.json")["files"]
    def check(item):
        p, r = item
        return None if Path(p).is_file() and sha(p) == r["sha256"] else p
    with ThreadPoolExecutor(max_workers=4) as pool:
        mismatches = [p for p in pool.map(check, rows.items()) if p]
    return {"status": "PASS" if not mismatches else "FAIL_CLOSED", "checked_files": len(rows),
            "changed_files": mismatches, "changed_count": len(mismatches)}


def recheck_observations(audit, output):
    old = read(Path(audit) / "V40D_WORKLOAD_COMPLETENESS.json")
    source = old["source"]
    if sha(source["path"]) != source["sha256"]:
        raise ReplayError("KESTREL_ARCHIVE_SHA_CHANGED")
    recorded = pd.read_parquet(Path(audit) / "V40D_FROZEN_JOB_OBSERVATIONS.parquet")
    frames = []
    columns = list(recorded.columns.drop("source_member"))
    ids = set(recorded.id.astype(str))
    with zipfile.ZipFile(source["path"]) as z:
        for member in sorted(recorded.source_member.unique()):
            f = pq.read_table(io.BytesIO(z.read(member)), columns=columns).to_pandas()
            f = f[f.id.astype(str).isin(ids)].copy()
            f["source_member"] = member
            frames.append(f)
    actual = pd.concat(frames, ignore_index=True)
    for f in (actual, recorded):
        f["id"] = f.id.astype(str)
    pd.testing.assert_frame_equal(actual.sort_values("id").reset_index(drop=True)[recorded.columns],
                                  recorded.sort_values("id").reset_index(drop=True), check_dtype=False)
    result = {"status": "PASS", "unique_jobs": len(actual), "raw_archive": reference(source["path"]),
        "matched_members": sorted(recorded.source_member.unique()),
        "stored_observations": reference(Path(audit) / "V40D_FROZEN_JOB_OBSERVATIONS.parquet"),
        "raw_values_recompared": True, "previous_complete_member_scan_bound_by_archive_SHA": True}
    write_json(Path(output) / "RUNTIME_RAW_RECHECK.json", result)
    return result


def run(repo, output, *, raw=True):
    repo, output = Path(repo), Path(output)
    audit = repo / "dayahead/artifacts/v40d_actual_realized_replay"
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "PREFLIGHT_STATUS.json", {"status": "RUNNING", "campaign_authorized": False})
    write_contracts(repo, output / "contracts")
    protected = verify_protected(repo, audit)
    write_json(output / "PROTECTED_REFERENCE_RECHECK.json", protected)
    if protected["status"] != "PASS":
        raise ReplayError("PROTECTED_PLANNING_FRESH_MODIFICATION")
    binding = read(audit / "V40D_ACTUAL_DECISION_BINDING_AUDIT.json")
    if binding["status"] != "PASS" or len(binding["cases"]) != 124:
        raise ReplayError("INCOMPLETE_ACCEPTED_DECISIONS")
    # Bind every decision first, before observations or other realized files are opened.
    admitted = [(b, *frozen_jobs(repo, b)) for b in binding["cases"]]
    print("Accepted final decisions verified: 124/124", flush=True)
    a, cap, *refs = capacity(repo)
    capacities = a["frozen_V39C_site_capacity"]
    obs = observations(audit)
    cases, errors, classifications = [], [], []
    for b, jobs, issue in admitted:
        failures = validate_jobs(jobs, obs, capacities, issue)
        by_uid = {j["job_uid"]: j for j in jobs}
        for r in jobs:
            if r["AIDC_site"] == "UNASSIGNED" and r["start_slot"] < 120:
                classifications.append({**classify(r, obs.get(r["job_uid"], {}), issue),
                    "day": b["day"], "case": b["case"], "requested_GPU": r["requested_GPU"],
                    "planned_start_slot": r["start_slot"], "planned_end_slot": r["end_slot"],
                    "state_at_issue": r["state_at_issue"]})
        for row in failures:
            r = by_uid[row["job_uid"]]
            o = obs.get(row["job_uid"])
            row.update(day=b["day"], case=b["case"], issue_time=issue.isoformat(),
                frozen_end_before_operating_day=r["end_slot"] <= 24,
                observed_end_before_operating_day=bool(o is not None and timestamp(o["end_time"]) <= issue + timedelta(hours=6)))
        errors.extend(failures)
        cases.append({"day": b["day"], "case": b["case"], "status": "PASS" if not failures else "FAIL_CLOSED",
            "jobs": len(jobs), "errors": len(failures), "reasons": dict(Counter(r["reason"] for r in failures)),
            "final_accepted_joint_SHA": b["final_executed_joint_sha"],
            "actual_job_replay_executed": False, "actual_grid_executed": False})
    write_parquet(output / "JOB_PREFLIGHT_ERRORS.parquet", pd.DataFrame(errors))
    classified = pd.DataFrame(classifications)
    write_parquet(output / "PRE_DAY_COMPLETE_CLASSIFICATIONS.parquet", classified)
    eligible = classified[classified.status.eq("PRE_DAY_COMPLETE")]
    rejected = classified[~classified.status.eq("PRE_DAY_COMPLETE")]
    exception_audit = {"status": "PASS" if not len(rejected) else "FAIL_CLOSED",
        "audited_case_job_rows": len(classified), "audited_unique_jobs": classified.job_uid.nunique(),
        "audited_unique_day_jobs": len(classified[["day", "job_uid"]].drop_duplicates()),
        "PRE_DAY_COMPLETE_job_count": len(eligible), "PRE_DAY_COMPLETE_unique_job_count": eligible.job_uid.nunique(),
        "PRE_DAY_COMPLETE_unique_day_job_count": len(eligible[["day", "job_uid"]].drop_duplicates()),
        "PRE_DAY_COMPLETE_GPU_count": int(eligible.requested_GPU.sum()),
        "PRE_DAY_COMPLETE_operating_day_GPU_hours": 0, "PRE_DAY_COMPLETE_operating_day_power_kWh": 0,
        "UNASSIGNED_with_operating_day_overlap_count": int((classified.observed_overlap_seconds.fillna(0) > 0).sum()),
        "UNASSIGNED_fail_closed_count": len(rejected), "UNASSIGNED_fail_closed_unique_job_count": rejected.job_uid.nunique(),
        "UNASSIGNED_fail_closed_unique_day_job_count": len(rejected[["day", "job_uid"]].drop_duplicates()),
        "failed_conditions": dict(Counter(k for r in classifications for k in r["failed_conditions"])),
        "count_units": "job_count and GPU_count include date/case duplicates; unique UID and unique day/UID counts provided separately",
        "May01_B3": {"case_job_rows": int(((classified.day == '2025-05-01') & (classified.case == 'B3')).sum()),
            "PRE_DAY_COMPLETE_rows": int(((eligible.day == '2025-05-01') & (eligible.case == 'B3')).sum())},
        "rule_amendment_changes_DA_results": False}
    write_json(output / "PRE_DAY_COMPLETE_AUDIT.json", exception_audit)
    write_json(output / "JOB_PREFLIGHT.json", {"cases": cases, "errors_by_reason": dict(Counter(r["reason"] for r in errors)),
        "status": "PASS" if not errors else "FAIL_CLOSED", "capacity_references": refs})
    data = {}
    if raw:
        # Reuse read-only audit math; route writes to the new output atomically.
        from dayahead.tools import audit_v40d_actual_replay as legacy
        original_out, original_write = legacy.OUT, legacy.write
        legacy.OUT = output
        legacy.write = lambda name, value: write_json(output / name, value)
        try:
            for name, function in (("traffic", legacy.traffic_audit), ("aemo", legacy.aemo_audit), ("weather", legacy.weather_audit)):
                print("Raw input recheck: " + name, flush=True)
                data[name] = function()
            data["runtime"] = recheck_observations(audit, output)
            write_json(output / "INPUT_SOURCE_MANIFEST.json", {"files": legacy.READ_FILES})
        finally:
            legacy.OUT, legacy.write = original_out, original_write
    def passed(v):
        return all(passed(x) for x in v.values() if isinstance(x, dict)) and v.get("status", "PASS") == "PASS"
    result = {"status": "PASS" if not errors and raw and passed(data) else "FAIL_CLOSED",
        "accepted_cases": 124, "job_preflight_pass_cases": sum(c["status"] == "PASS" for c in cases),
        "failed_cases": sum(c["status"] != "PASS" for c in cases),
        "errors_by_reason": dict(Counter(r["reason"] for r in errors)),
        "PRE_DAY_COMPLETE_audit": exception_audit,
        "input_raw_recheck": "PASS" if raw and passed(data) else "NOT_PASS",
        "protected_changed_count": protected["changed_count"],
        "Actual_execution_count": 0, "campaign_authorized": False,
        "reason": "Run and report smoke before requesting full campaign approval",
        "missing_authority_request_resolved": False}
    write_json(output / "PREFLIGHT_STATUS.json", result)
    return result
