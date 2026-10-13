"""Read-only, issue-causal recovery of prior modeled RUNNING episode sites.

No Actual trace/end, policy outcome, grid or MESS result is opened. The failed
PR79 full Reference is evidence only. A prior row can be accepted solely after
new scoped identity, chronology, continuity and current occupancy checks.
"""
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path

from .m_engine import file_record, _write
from .policy import digest


PR79_CONTRACT = "V42_EPISODE_REFERENCE_V1"
PR79_CODE_SHA = "9aadfbb991c59cfd0357b861576638cbc117370c5e1e3549bf5903183d9cf555"
PR79_LEDGER_SHA = "6c99a28463443aced7d234568575efa6355663e3e694a0089cd3d56162105441"


def _seconds(value):
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()


def episode_id(uid, submit_seconds):
    value = dict(contract=PR79_CONTRACT, uid=str(uid), submit=int(submit_seconds), attempt=None)
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def scoped_prior_check(observed, prior_rows, fixed_running, capacities, racks, *, issue_seconds,
                       canonical_receipt, source_record_hash):
    """Seven requirements on one episode; current instant only, no release grant."""
    uid = str(observed["job_uid"])
    submit = _seconds(observed["submit_time"])
    known_start = issue_seconds - float(observed["elapsed_seconds"])
    ep = episode_id(uid, submit)
    gpu = int(observed["GPU_gang"])
    candidates = [r for r in prior_rows if r.get("reference_AIDC_site") is not None
                  and r.get("state_at_issue") == "RUNNING"]
    candidates.sort(key=lambda r: r["issue_seconds"])
    latest = candidates[-1] if candidates else None
    if latest is None:
        return dict(PASS=False, job_uid=uid, episode_id=ep, recovered_site=None,
                    status="SOURCE_AUTHORITY_UNRESOLVED",
                    reason="NO_PRIOR_ASSIGNED_RUNNING_EPISODE_ROW", checks={}), None
    same = [r for r in candidates if r["episode_id"] == ep]
    first = next((r for r in same if r.get("reference_site_origin") == "NEW_SYNTHETIC_ASSIGNMENT"), None)
    site = latest["reference_AIDC_site"]
    rack = latest.get("reference_rack")
    site_use = sum(int(r["GPU_gang"]) for r in fixed_running
                   if r["current_site_if_running"] == site)
    rack_match = next((r for r in racks if r["rack_pool_id"] == rack and r["aidc_id"] == site), None)
    checks = dict(
        SAME_UID_AND_RUNNING_EPISODE=bool(latest["job_uid"] == uid and latest["episode_id"] == ep
            and latest["submit_seconds"] == submit and latest["known_start_seconds"] == known_start
            and latest["source_record_hash"] == source_record_hash and latest["boundary_status"] == "RESOLVED"),
        ASSIGNED_BEFORE_CURRENT_ISSUE=bool(first and first["issue_seconds"] < issue_seconds
            and first["capacity_feasible"] is True and first["rack_compatible"] is True
            and latest["issue_seconds"] == issue_seconds-86400),
        SOURCE_PROVENANCE_SHA_PRESENT=bool(canonical_receipt.get("sha256") == PR79_LEDGER_SHA
            and latest.get("snapshot_sha256") and source_record_hash),
        NO_OTHER_ARM_POLICY_RESULT=bool(same and all(r["policy_output_used"] is False
            and r["grid_information_used"] is False for r in same)),
        NO_FUTURE_OUTCOME_SITE_SELECTION=bool(same and all(r["future_outcome_used"] is False for r in same)),
        RUNNING_SITE_CONTINUITY=bool(same and len({r["reference_AIDC_site"] for r in same}) == 1
            and all(r["known_start_seconds"] == known_start and r["requested_GPU"] == gpu
                    and r["source_record_hash"] == source_record_hash
                    and r["boundary_status"] == "RESOLVED" for r in same)
            and all(b["issue_seconds"]-a["issue_seconds"] == 86400 for a,b in zip(same,same[1:]))),
        WHOLE_GANG_RACK_AND_CURRENT_SITE_CAPACITY=bool(site in capacities and rack_match
            and gpu <= rack_match["compatibility_GPU_limit"] and site_use+gpu <= capacities[site]
            and latest["capacity_feasible"] is True and latest["rack_compatible"] is True),
    )
    passed = all(checks.values())
    assessment = dict(PASS=passed, job_uid=uid, episode_id=ep,
        status="EXACT_PRIOR_SITE_RECOVERED" if passed else "SOURCE_AUTHORITY_UNRESOLVED",
        recovered_site=site if passed else None, recovered_rack=rack if passed else None,
        checks=checks, current_site_GPU_before=site_use, requested_GPU=gpu,
        current_site_GPU_after=site_use+gpu, capacity_GPU=capacities.get(site),
        current_capacity_scope="OBSERVED_ISSUE_INSTANT_WITH_IMMUTABLE_210_ONLY; NO_FUTURE_RELEASE",
        prior_assignment_issue_seconds=first["issue_seconds"] if first else None,
        prior_assignment_day=first["assignment_day"] if first else None,
        prior_last_issue_seconds=latest["issue_seconds"], prior_row=latest,
        prior_whole_day_ready=latest["day_reference_ready"], PR79_global_ready=False,
        failed_full_PR79_promoted=False, source_record_hash=source_record_hash,
        initial_site_source="PRIOR_SYNTHETIC_REFERENCE_MODEL_SITE", KESTREL_OBSERVED_SITE=False,
        SOURCE18R_NUMERICALLY_IDENTICAL=False, OLD_PR220_UB_AUTOMATIC_REUSE=False)
    pin = None
    if passed:
        pin = dict(episode_id=ep, site=site, assigned_at_seconds=first["issue_seconds"],
            known_start_seconds=known_start, source_receipt=canonical_receipt,
            policy_independent=True, episode_capacity_validated=True,
            kind="VERIFIED_PRIOR_REFERENCE_EPISODE_SITE", rack=rack,
            scoped_checks_sha=digest(assessment), KESTREL_OBSERVED_SITE=False,
            INITIAL_SITE_SOURCE="PRIOR_SYNTHETIC_REFERENCE_MODEL_SITE")
    return assessment, pin


def recover_sites(native_path, descriptors_path, snapshot_path, r0_path, canonical_path,
                  pr79_code_path, pr79_freeze_path, provenance_path, *, output, lineage_sources=()):
    """Audit every missing UID and produce immutable pin inputs for all Arms."""
    import pandas as pd
    paths = [Path(p) for p in (native_path, descriptors_path, snapshot_path, r0_path,
        canonical_path, pr79_code_path, pr79_freeze_path, provenance_path, *lineage_sources)]
    receipts = [file_record(p) for p in paths]
    by_path = {r["path"]: r for r in receipts}
    native = json.loads(Path(native_path).read_text(encoding="utf8"))
    descriptors = json.loads(Path(descriptors_path).read_text(encoding="utf8"))
    provenance = json.loads(Path(provenance_path).read_text(encoding="utf8"))
    if file_record(pr79_code_path)["sha256"] != PR79_CODE_SHA:
        raise ValueError("PR79_CODE_SOURCE_DRIFT")
    canonical_receipt = file_record(canonical_path)
    if canonical_receipt["sha256"] != PR79_LEDGER_SHA:
        raise ValueError("PR79_CANONICAL_SOURCE_DRIFT")
    freeze = json.loads(Path(pr79_freeze_path).read_text(encoding="utf8"))
    issue = _seconds(native["issue_time"])
    running = [r for r in native["known_population"] if r["state"] == "RUNNING"]
    fixed = [r for r in running if r.get("current_site_if_running") in native["capacities"]]
    missing = [r for r in running if r not in fixed]
    if (len(running), len(fixed), len(missing), sum(r["GPU_gang"] for r in missing)) != (254,210,44,59):
        raise ValueError("ORIGINAL_254_210_44_59_COUNTS_DRIFT")
    if len({r["job_uid"] for r in running}) != len(running):
        raise ValueError("INITIAL_RUNNING_UID_DUPLICATE")
    current = {r["job_uid"]: r for r in descriptors["known_population"]}
    # This projection has no future start/end/outcome, unlike the private truth.
    snapshot = pd.read_parquet(snapshot_path, columns=["id", "submit_time", "known_running_start",
        "state_at_issue", "gpus_requested", "source_member", "qos", "partition"])
    snapshot["uid"] = snapshot.id.astype(str)
    snapshot = snapshot.set_index("uid")
    r0 = {r["job_uid"]: r for r in json.loads(Path(r0_path).read_text(encoding="utf8"))}
    canonical = pd.read_parquet(canonical_path, filters=[("job_uid", "in", [r["job_uid"] for r in missing])])
    # Roundtrip pandas scalars/NaN into ordinary JSON booleans and nulls.
    rows = json.loads(canonical.to_json(orient="records"))
    reports = []
    pins = {}
    for observed in missing:
        uid = observed["job_uid"]
        raw = current[uid]
        snap = snapshot.loc[uid]
        expected_start = issue-float(observed["elapsed_seconds"])
        if (raw["state"] != "RUNNING" or raw["GPU_gang"] != observed["GPU_gang"]
            or str(snap.state_at_issue) != "RUNNING" or int(snap.gpus_requested) != observed["GPU_gang"]
            or snap.known_running_start.timestamp() != expected_start
            or snap.submit_time.timestamp() != _seconds(observed["submit_time"])
            or raw["source_member"] != snap.source_member):
            raise ValueError("CURRENT_ISSUE_OBSERVATION_IDENTITY_DRIFT:"+uid)
        source_record_hash = hashlib.sha256((provenance["archive"]["sha256"]+"|"+
            raw["source_member"]+"|"+str(raw["source_row"])+"|"+uid).encode()).hexdigest()
        prior = [r for r in rows if r["job_uid"] == uid]
        report, pin = scoped_prior_check(observed, prior, fixed, native["capacities"], native["racks"],
            issue_seconds=issue, canonical_receipt=canonical_receipt, source_record_hash=source_record_hash)
        original = r0[uid]
        report.update(original_source_site=None, original_R0_site=original["AIDC_site"],
            original_R0_start_issue_slot=original["start_slot"], original_R0_end_issue_slot=original["end_slot"],
            original_R0_duration_authority=original["duration_authority"],
            original_R0_safe_seconds=original["safe_duration_seconds"],
            current_Q50_total_seconds=observed["V10_Q50_total_seconds"],
            current_Q50_reference_end_issue_slot=observed["reference_end"],
            old_requested_remaining_external_end_slot=observed["unresolved_external_source_service_end"],
            reference_end_is_observed_completion=False, future_completion_reads=0,
            requested_GPU=observed["GPU_gang"], known_start_seconds=expected_start,
            submit_seconds=_seconds(observed["submit_time"]),
            source_member=raw["source_member"], source_row=raw["source_row"],
            previous_canonical_rows=prior, canonical_source=canonical_receipt,
            original_R0_source=file_record(r0_path), native_source=file_record(native_path),
            observation_source=file_record(snapshot_path), descriptor_source=file_record(descriptors_path))
        if pin:
            pins[uid] = pin
        reports.append(report)
    fixed_mapping = {r["job_uid"]: r["current_site_if_running"] for r in fixed}
    counts = Counter(r["status"] if "status" in r else "SOURCE_AUTHORITY_UNRESOLVED" for r in reports)
    gpu_counts = {status:sum(r["requested_GPU"] for r in reports
                            if r.get("status", "SOURCE_AUTHORITY_UNRESOLVED") == status) for status in counts}
    doc = dict(schema="SCOPED_PRIOR_RUNNING_SITE_RECOVERY_V1", issue_seconds=issue,
        counts=dict(running=254,fixed=210,missing=44,missing_GPU=59),
        recovery_counts=dict(counts), recovery_GPU=gpu_counts,
        exact_prior_model_site_recovered_jobs=len(pins), recovered_GPU=sum(r["requested_GPU"] for r in reports if r["job_uid"] in pins),
        unrecovered_jobs=44-len(pins), unrecovered_GPU=59-sum(r["requested_GPU"] for r in reports if r["job_uid"] in pins),
        prior_verified_pins=pins, fixed_210_sites=fixed_mapping, fixed_210_sha=digest(fixed_mapping),
        initial_210_site_changes=0, whole_case_EXACT_SITE_RECOVERY_PASS=False,
        PR79_full_reference_ready=freeze.get("ready",False), PR79_full_reference_promoted=False,
        KESTREL_OBSERVED_SITE=False, SOURCE18R_NUMERICALLY_IDENTICAL=False,
        new_current_frame_validation=True, original_source_files_modified=0,
        actual_end_reads=0, future_queue_reads=0, grid_reads=0, MESS_reads=0,
        scope="Individual prior reference model sites only; remaining unresolved sites require path B or C",
        source_receipts=receipts, per_job=reports)
    audit = dict(schema="SITE_RECOVERY_SOURCE_AUDIT_V1", sources=receipts,
        source_identity_construction="sha256(raw_archive_SHA|member|row|UID), provenance only, never a placement seed",
        first_verified_omission=dict(module="dayahead/v39a/spatial.py::production_activity",
            trigger="Reference scheduled interval ends at/before issue slot24", behavior="Clip to [24,120); skip start>=end",
            next_stage="dayahead/v40d_actual/inputs.py::frozen_jobs preserves every temporal UID; absent destination becomes UNASSIGNED",
            PR93="v42_may01.prepare.job_ledger preserves REQUESTED_REMAINING RUNNING when original end_slot<=24 in external source ledger",
            later_Q50="v42_final.native_inputs replaces nominal reference_end with Q50 residual while retaining original requestedremaining external end",
            current_blocker="Full issue-origin physical Actual needs all observed RUNNING gangs at a model site; old admitted D-day scope did not establish that full prefix"),
        duration_evidence=dict(original_reference_end="REQUESTED_REMAINING, not observed completion",
            new_nominal_reference_end="Frozen V10 Q50 residual, not observed completion",
            actual_completion="Excluded from this source recovery function; separate simulator event boundary audit"),
        seven_check_scope="New observed current issue frame, same prior episode, no acceptance of failed complete PR79 placement",
        per_job=reports, classification_counts=dict(counts), classification_GPU=gpu_counts)
    output = Path(output)
    output.mkdir(parents=True,exist_ok=True)
    for name, value in (("R0_REFERENCE_SITE_RECOVERY.json",doc),("SITE_RECOVERY_SOURCE_AUDIT.json",audit)):
        if (output/name).exists():
            raise FileExistsError("RECOVERY_ARTIFACT_ALREADY_EXISTS:"+str(output/name))
        _write(output/name,value)
    return doc
