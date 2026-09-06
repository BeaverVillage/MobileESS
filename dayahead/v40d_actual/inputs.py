"""Read accepted final decisions before realized data. No optimizer imports."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import pandas as pd
from dayahead.paper_analysis.storage import read, sha, reference
from .contracts import ReplayError
from .rack_dispatch import Rack


def legacy_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def capacity(repo):
    from dayahead.v39d.contracts import CAPACITY_FILE_SHA256, CAPACITY_CANONICAL_SHA256, EXPECTED_GPU_CAPACITY
    root = Path(repo) / "dayahead/artifacts/v39d_independent_daily_temporal_first_migration"
    path = root / "V39D_SYNTHETIC_LOGICAL_RACK_COMPATIBILITY_AUTHORITY.json"
    a = read(path)
    cert = read(root / "V39D_RACK_FREEZE_CERTIFICATE.json")
    payload = dict(a)
    recorded = payload.pop("rack_canonical_SHA256")
    if sha(path) != cert["rack_authority_SHA256"] or legacy_digest(payload) != recorded:
        raise ReplayError("RACK_AUTHORITY_HASH_DRIFT")
    cap_path = Path(repo) / "dayahead/artifacts/v39c_aidc_gpu_capacity_refreeze/V39C_H100_EQUIVALENT_SITE_CAPACITY_AUTHORITY.json"
    cap = read(cap_path)
    if sha(cap_path) != CAPACITY_FILE_SHA256 or cap["canonical_SHA256"] != CAPACITY_CANONICAL_SHA256:
        raise ReplayError("CURRENT_V39C_CAPACITY_AUTHORITY_DRIFT")
    if a["frozen_V39C_site_capacity"] != EXPECTED_GPU_CAPACITY:
        raise ReplayError("CURRENT_SITE_CAPACITY_VECTOR_DRIFT")
    if sha(cap_path) != a["site_capacity_authority_file_SHA256"]:
        raise ReplayError("SITE_CAPACITY_AUTHORITY_SHA_DRIFT")
    if [a["frozen_V39C_site_capacity"][s] for s in sorted(a["frozen_V39C_site_capacity"])] != cap["canonical_GPU_vector"]:
        raise ReplayError("SITE_RACK_CAPACITY_MISMATCH")
    pools = a["logical_Rack_pools"]
    if a["logical_Rack_limits_are_additive_capacity"] or len(pools) != 48 or any(
        p["semantics"] != "NON_ADDITIVE_SINGLE_GANG_COMPATIBILITY_ENVELOPE"
        or p["aggregate_capacity_contribution_GPU"] != 0
        or p["compatibility_GPU_limit"] != EXPECTED_GPU_CAPACITY[p["aidc_id"]] for p in pools):
        raise ReplayError("RACK_NONADDITIVE_AUTHORITY_DRIFT")
    return a, cap, reference(path), reference(cap_path)


def frozen_jobs(repo, binding):
    """Return every frozen temporal job; never drop pre-day or post-H rows."""
    if sha(binding["certificate"]) != binding["certificate_SHA"]:
        raise ReplayError("FINAL_CERTIFICATE_SHA_MISMATCH")
    day, case = binding["day"], binding["case"]
    ledger_path = Path(repo) / "dayahead/artifacts/v37_r4a_per_day_aidc/days" / day / "V37_R4A_JOB_LEDGER.parquet"
    ledger = pd.read_parquet(ledger_path)
    base = {str(r["job_id"]): r for r in ledger.to_dict("records")}
    path = Path(binding["AIDC_decision_source"])
    x = read(path)
    if case == "B3":
        cert = read(binding["certificate"])
        if path.name != "FINAL_JOINT_DECISION_PAYLOAD.json" or sha(path) != cert["files"].get(path.name):
            raise ReplayError("B3_FINAL_A1_SOURCE_BINDING_FAIL")
        checkpoint = path.parent / "COOPT_PLANNING_CHECKPOINT.json"
        if sha(checkpoint) != cert["files"].get(checkpoint.name):
            raise ReplayError("B3_A1_CHECKPOINT_BINDING_FAIL")
        selected = x["AIDC_decision"]
        if legacy_digest(selected) != legacy_digest(read(checkpoint)["a1"]):
            raise ReplayError("B3_FINAL_A1_DECISION_MISMATCH")
    else:
        d = x["decision"]
        if legacy_digest(d) != x["DA_decision_SHA256"]:
            raise ReplayError("FROZEN_DECISION_DIGEST_MISMATCH")
        expected_case = "B0" if case == "B2" else case
        if binding["AIDC_source_case"] != expected_case or x["DA_decision_SHA256"] != binding["binding_components"]["DA_decision_SHA"]:
            raise ReplayError("CASE_AIDC_DECISION_BINDING_FAIL")
        placements = {str(r["job_uid"]): r for r in d["AIDC_assignments"]}
        selected = []
        for r in d["temporal_schedule"]:
            uid = str(r["job_id"])
            p = placements.get(uid, {})
            selected.append({"job_uid": uid, "state_at_issue": r["state_at_issue"],
                "qos": r["qos"], "requested_GPU": int(r["requested_gpus"]),
                "start_slot": int(r["scheduled_start_slot"]), "end_slot": int(r["scheduled_end_slot"]),
                "AIDC_site": p.get("destination_AIDC", "UNASSIGNED"),
                "Rack_label": p.get("logical_Rack_compatibility_label"),
                "migration_selected": bool(p.get("migration_selected", False)),
                "accepted_A0_assignment_and_WAN": p})
    if len(selected) != len(base) or {str(r["job_uid"]) for r in selected} != set(base):
        raise ReplayError("FINAL_JOB_UID_SET_MISMATCH")
    jobs = [{**r, "job_uid": str(r["job_uid"]), "submit_time": base[str(r["job_uid"])]["submit_time"],
             "partition": base[str(r["job_uid"])]["partition"],
             "requested_walltime_seconds": float(base[str(r["job_uid"])]["requested_walltime_seconds"])}
            for r in selected]
    issue = datetime.fromisoformat(day).replace(tzinfo=timezone(timedelta(hours=10))) - timedelta(hours=6)
    return jobs, issue


def observations(audit_root):
    frame = pd.read_parquet(Path(audit_root) / "V40D_FROZEN_JOB_OBSERVATIONS.parquet")
    if frame.id.astype(str).duplicated().any():
        raise ReplayError("OBSERVED_UID_DUPLICATE")
    return {str(r["id"]): r for r in frame.to_dict("records")}
