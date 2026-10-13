"""Read-only PR93/R0 versus private completion/D00 authority evidence.

No source site is generated here. Retrospective completion is simulator-only;
neither a policy-specific replay nor requested/Q50 completion is promoted into
an independent observed midnight queue or synthetic AIDC site snapshot.
"""
from collections import Counter
import argparse
from pathlib import Path

import pandas as pd

from .actual_validation import read, record, checked, write

NATIVE_ROOT = Path("C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance")
SNAPSHOT_ROOT = Path("C:/codex_mobileess_workspace/MobileESS_v40a_bounded_iterative_coopt/dayahead/artifacts/v37_r4a_per_day_aidc/days")
CANONICAL = Path("C:/Users/kjw39/OneDrive/문서/ChatGPT/Mobile ESS 2/v42_reference_episode_pr/docs/v42_aidc_reference_episode_continuity/CANONICAL_REFERENCE_LEDGER.parquet")


def iso(seconds, zone="UTC"):
    return pd.Timestamp(seconds, unit="s", tz="UTC").tz_convert(zone).isoformat()


def initial_headroom_witness(plan, native, prior_local_sites):
    """Two hypothetical complete initial layouts; neither is adopted authority.

    Inputs are issue-observed requests, fixed sites and approved rack/site
    compatibility only. No realized duration/end, grid or policy outcome input.
    """
    capacities = plan["capacities"]
    source = {r["job_uid"]: r for r in plan["known_population"]}
    running = [r for r in native["known_population"] if r["state"] == "RUNNING"]
    fixed = {r["job_uid"]: r["current_site_if_running"] for r in running if r["current_site_if_running"] is not None}
    unresolved = [r for r in running if r["current_site_if_running"] is None]
    # A locally valid prior Episode candidate is held the same in both probes;
    # this precaution does not declare its recovery approved.
    held = {r["job_uid"]: prior_local_sites[r["job_uid"]] for r in unresolved if r["job_uid"] in prior_local_sites}
    def allowed(row, site):
        gpu = row["GPU_gang"]
        return (site in source[row["job_uid"]]["compatible_sites"] and gpu <= capacities[site]
                and gpu <= max(plan["rack_compatibility"][site]))
    for row in unresolved:
        if row["job_uid"] in held and not allowed(row, held[row["job_uid"]]):
            raise ValueError("PRIOR_LOCAL_SITE_WITNESS_INCOMPATIBLE")
    alternatives = []
    for direction in ("ASCENDING", "DESCENDING"):
        assignment = dict(fixed, **held)
        use = Counter()
        for row in running:
            if row["job_uid"] in assignment:
                use[assignment[row["job_uid"]]] += row["GPU_gang"]
        for row in sorted(unresolved, key=lambda r: r["job_uid"]):
            uid, gpu = row["job_uid"], row["GPU_gang"]
            if uid in held:
                continue
            candidates = sorted(capacities, reverse=direction == "DESCENDING")
            site = next((s for s in candidates if allowed(row, s) and use[s]+gpu <= capacities[s]), None)
            if site is None:
                return dict(status="GREEDY_SENSITIVITY_WITNESS_NOT_FOUND_NO_INFEASIBILITY_CLAIM",
                    source_inputs_only=True, solver_calls=0, hypothetical_not_adopted=True)
            assignment[uid] = site
            use[site] += gpu
        if any(assignment[uid] != site for uid, site in fixed.items()) or sum(use.values()) != 468:
            raise ValueError("SENSITIVITY_FIXED_210_OR_FULL_GANG_CONSERVATION")
        alternatives.append(dict(direction=direction, assignments=assignment,
            use_GPU={s:use[s] for s in sorted(capacities)},
            headroom_GPU={s:capacities[s]-use[s] for s in sorted(capacities)},
            initial_running_jobs=254, initial_GPU=468, original_210_changed=0,
            unknown44_GPU=59, all_whole_gangs_compatible=True, capacity_feasible=True))
    probe = None
    for site in sorted(capacities):
        a, b = (r["headroom_GPU"][site] for r in alternatives)
        if a == b:
            continue
        pending = sorted((r for r in plan["known_population"] if r["state"] == "PENDING"
                          and site in r["compatible_sites"]), key=lambda r: (r["submit_time"], r["job_uid"]))
        batch, gpu = [], 0
        for row in pending:
            if row["GPU_gang"] > max(plan["rack_compatibility"][site]):
                continue
            batch.append(row["job_uid"])
            gpu += row["GPU_gang"]
            if min(a, b) < gpu <= max(a, b):
                probe = dict(site=site, observed_pending_UIDs=batch, whole_gang_GPU=gpu,
                    layout_ascending_headroom_GPU=a, layout_descending_headroom_GPU=b,
                    admissible_by_instantaneous_capacity_in_ascending=gpu <= a,
                    admissible_by_instantaneous_capacity_in_descending=gpu <= b,
                    execution_or_full_continuous_service_permission_claimed=False,
                    purpose="SITE_CAPACITY_START_ADMISSION_CAN_DIFFER_AT_ISSUE")
                break
        if probe is not None:
            break
    return dict(status="SITE_HEADROOM_AND_PENDING_ADMISSION_SENSITIVITY_PROVEN" if probe else "HEADROOM_ONLY_SENSITIVITY_PROVEN",
        hypothetical_not_adopted=True, prior_local_episode_candidates_held_fixed=held,
        original_source_site_restoration_claim=False, independent_D00_no_effect_proof=False,
        observed_pending_probe=probe, layouts=alternatives,
        future_completion_reads=0, realized_duration_reads=0, grid_reads=0, policy_result_reads=0,
        solver_calls=0, raw_or_original_files_modified=0)


def audit(folder, output, *, private_audit):
    folder, output = Path(folder), Path(output)
    output.mkdir(parents=True, exist_ok=True)
    names = ("PLANNING_INPUT_BUNDLE.json", "ACTUAL_INPUT_BUNDLE.json", "SOURCE_PROVENANCE.json", "NATIVE_INPUT_TEMPLATE_B1.json")
    plan, actual, provenance, native = [read(folder/name) for name in names]
    sources = [record(folder/name) for name in names]
    private = read(private_audit)
    if private["day"] != plan["day"]:
        raise ValueError("BOUNDARY_PRIVATE_AUDIT_DAY_MISMATCH")
    sources.append(record(private_audit))
    recovery_path = output/"SITE_RECOVERY_SOURCE_AUDIT.json"
    recovery_rows = {}
    if recovery_path.is_file():
        recovery = read(recovery_path)
        for item in recovery["sources"]:
            if record(item["path"])["sha256"] != item["sha256"]:
                raise ValueError("SCOPED_PRIOR_SITE_RECOVERY_SOURCE_DRIFT")
        recovery_rows = {row["job_uid"]: row for row in recovery["per_job"]
                         if row.get("PASS") is True and row.get("status") == "EXACT_PRIOR_SITE_RECOVERED"}
        sources.append(record(recovery_path))
    for item in private["source_receipts"]:
        if record(item["path"]) != item:
            raise ValueError("BOUNDARY_PRIVATE_AUDIT_SOURCE_DRIFT")
    r0_path = checked(native["reference"])
    snapshot_path = checked(provenance["snapshot"])
    sources += [record(r0_path), record(snapshot_path), record(CANONICAL)]
    r0 = {r["job_uid"]: r for r in read(r0_path)}
    snapshot = pd.read_parquet(snapshot_path)
    snapshot["uid"] = snapshot.id.astype(str)
    snapshot = snapshot.set_index("uid")
    source_known = {r["job_uid"]: r for r in plan["known_population"]}
    raw_actual = {r["uid"]: r for r in private["assigned_rows"]+private["missing_rows"]}
    issue = pd.Timestamp(plan["issue_time"]).timestamp()
    begin = pd.Timestamp(plan["day"], tz="Etc/GMT-10").timestamp()
    end = begin+86400
    initial = [r for r in native["known_population"] if r["state"] == "RUNNING"]
    if len(initial) != 254 or len({r["job_uid"] for r in initial}) != 254:
        raise ValueError("INITIAL_254_IDENTITY_DRIFT")
    uids = {r["job_uid"] for r in initial}
    canonical = pd.read_parquet(CANONICAL)
    canonical.job_uid = canonical.job_uid.astype(str)
    canonical = canonical[canonical.job_uid.isin(uids)&canonical.issue_seconds.le(issue)]
    canonical = canonical.sort_values(["job_uid", "issue_seconds", "operating_day"])
    previous = {uid: group.iloc[-1].to_dict() for uid, group in canonical.groupby("job_uid")}
    rows = []
    for original in initial:
        uid = original["job_uid"]
        descriptor, observed, base, actual_row = source_known[uid], snapshot.loc[uid], r0[uid], raw_actual[uid]
        before = previous.get(uid, {})
        submit = pd.Timestamp(observed.submit_time).timestamp()
        start = pd.Timestamp(observed.known_running_start).timestamp()
        actual_end = actual_row["source_end_seconds"]
        completion_slot = (actual_end-issue)/900
        release = 900*__import__("math").ceil(actual_end/900)
        native_site = original["current_site_if_running"]
        same_episode = bool(before and pd.notna(before.get("known_start_seconds")) and abs(before["known_start_seconds"]-start) <= 1e-6)
        candidate_site = before.get("reference_AIDC_site")
        if candidate_site == "UNASSIGNED" or not isinstance(candidate_site, str):
            candidate_site = None
        prior_local_valid = bool(same_episode and before.get("state_at_issue") == "RUNNING"
            and before.get("status") in {"REFERENCE_ASSIGNED", "NEW_RESERVED", "INHERITED_RESERVED"}
            and before.get("capacity_feasible")
            and before.get("rack_compatible") and not before.get("grid_information_used")
            and not before.get("policy_output_used") and not before.get("future_outcome_used"))
        recovered = recovery_rows.get(uid)
        if recovered is not None and (native_site is not None or recovered["episode_id"] != before.get("episode_id")
                or not prior_local_valid):
            raise ValueError("BOUNDARY_SCOPED_RECOVERED_EPISODE_SITE_MISMATCH")
        predicted_end = issue+base["end_slot"]*900
        prefix = max(0., min(actual_end, begin)-max(start, issue))
        daily = max(0., min(actual_end, end)-max(start, begin))
        actual_duration = actual_end-start
        row = dict(job_uid=uid, episode_id=before.get("episode_id"),
            episode_id_source="PR79_DERIVED_REFERENCE_EPISODE" if before else None,
            episode_running_start_matches_source=same_episode, submit_time_utc=iso(submit),
            issue_time_utc=iso(issue), issue_time_fixed_AEST=iso(issue, "Etc/GMT-10"), issue_state="RUNNING",
            observed_running_start_utc=iso(start), observed_running_start_seconds=start,
            requested_GPU=original["GPU_gang"], qos=str(observed.qos), GPU_type_request_partition=str(observed.partition),
            GPU_type_to_AIDC_mapping="NO_RAW_KESTREL_TO_SYNTHETIC_AIDC_LOCATION_MAPPING",
            requested_walltime_seconds=float(observed.wallclock_seconds),
            request_version_authority="D1_FINAL_ACCOUNTING_PROXY_UNVERIFIED_REQUEST_VERSION",
            frozen_Q50_total_seconds=descriptor["Q50_total_seconds"],
            Q50_nominal_remaining_seconds=descriptor["nominal_remaining_seconds"],
            R0_start_issue_slot=base["start_slot"], R0_expected_end_issue_slot=base["end_slot"],
            R0_expected_end_utc=iso(predicted_end), R0_duration_authority=base["duration_authority"],
            R0_expected_end_is_observed_completion=False, Source18r_Q50_reference_end_slot=original["reference_end"],
            retained_unresolved_external_source_end_slot=original.get("unresolved_external_source_service_end"),
            actual_completion_event_utc=iso(actual_end), actual_completion_issue_slot=completion_slot,
            simulator_event_publication_utc=iso(actual_end), real_scheduler_observation_watermark_utc=None,
            completion_observation_contract="SOURCE_TRACE_END_EVENT_PUBLISHED_ONLY_WHEN_SIMULATOR_CLOCK_REACHES_END",
            controller_knows_completion_at_issue=False, actual_end_minus_R0_expected_end_seconds=actual_end-predicted_end,
            actual_release_control_utc=iso(release), actual_D00_source_state="COMPLETED" if actual_end <= begin else "RUNNING",
            D00_physical_GPU=0 if release <= begin else original["GPU_gang"],
            original_native_AIDC_site=native_site, raw_KESTREL_observed_AIDC_site=None,
            raw_Kestrel_site_observed=False, native_site_authority="SOURCE18R_FROZEN_CASE_MODELED_SITE" if native_site else "UNRESOLVED",
            previous_canonical_reference_site=candidate_site,
            previous_episode_locally_valid_site=candidate_site if prior_local_valid else None,
            previous_snapshot_verified_site=None, previous_issue_utc=None if not before else iso(before["issue_seconds"]),
            previous_reference_status=before.get("status"), previous_whole_reference_ready=None if not before else bool(before.get("day_reference_ready")),
            previous_site_not_automatically_promoted=True,
            pre_issue_service_GPUh=max(0., issue-start)*original["GPU_gang"]/3600,
            pre_D00_service_after_issue_GPUh=prefix*original["GPU_gang"]/3600,
            Dday_source_service_GPUh=daily*original["GPU_gang"]/3600,
            full_source_realized_service_GPUh=actual_duration*original["GPU_gang"]/3600,
            no_Dday_source_occupancy_proven=daily == 0 and release <= begin,
            own_UID_queue_at_D00="COMPLETED" if actual_end <= begin else "RUNNING",
            own_UID_future_CC4_depletion=0, origin_unknown=False,
            pre_D00_capacity_or_queue_effect_requires_site=native_site is None and prefix > 0,
            D00_other_jobs_queue_effect="NOT_ESTABLISHED_WITHOUT_PREFIX_SITE_OR_INDEPENDENT_BOUNDARY",
            D00_independent_modeled_site_queue_snapshot=False,
            classification="EXACT_PRIOR_SITE_RECOVERED" if recovered else "PREDAY_STATE_EFFECT_REQUIRES_SITE" if native_site is None and prefix > 0 else "SOURCE_AUTHORITY_UNRESOLVED" if native_site is None else "SOURCE18R_FIXED_SITE_PRESERVED",
            recovery_status="EXACT_PRIOR_SITE_RECOVERED" if recovered else "NOT_PROMOTED_PRIOR_SITE_CANDIDATE" if prior_local_valid and native_site is None else "SOURCE_SITE_UNRESOLVED" if native_site is None else "ORIGINAL_210_SITE_UNCHANGED",
            recovered_model_site=None if recovered is None else recovered["recovered_site"],
            recovered_model_rack=None if recovered is None else recovered["recovered_rack"],
            recovered_site_is_Kestrel_observed=False, recovery_scope="SCOPED_PRIOR_REFERENCE_EPISODE_ONLY" if recovered else None,
            recovery_source_audit_path=str(recovery_path) if recovered else None,
            recovery_source_audit_sha=record(recovery_path)["sha256"] if recovered else None,
            scoped_seven_check_sha=None if recovered is None else recovered.get("scoped_checks_sha"),
            source_member=descriptor["source_member"], source_row=descriptor["source_row"],
            actual_event_source_path=private["archive"]["path"], actual_event_source_sha=private["archive"]["sha256"],
            issue_snapshot_source_path=str(snapshot_path), issue_snapshot_source_sha=record(snapshot_path)["sha256"],
            R0_reference_source_path=str(r0_path), R0_reference_source_sha=record(r0_path)["sha256"],
            native_current_site_source_path=str(folder/"NATIVE_INPUT_TEMPLATE_B1.json"), native_current_site_source_sha=record(folder/"NATIVE_INPUT_TEMPLATE_B1.json")["sha256"],
            prior_canonical_source_path=str(CANONICAL), prior_canonical_source_sha=record(CANONICAL)["sha256"])
        rows.append(row)
    frame = pd.DataFrame(rows)
    missing = frame[frame.original_native_AIDC_site.isna()].copy()
    if len(missing) != 44 or int(missing.requested_GPU.sum()) != 59 or int(frame.requested_GPU.sum()) != 468:
        raise ValueError("INITIAL_RUNNING_254_44_59GPU_CONSERVATION")
    frame.to_csv(output/"INITIAL_RUNNING_254_AUDIT.csv", index=False, lineterminator="\n")
    missing.to_csv(output/"UNASSIGNED_RUNNING_44_LEDGER.csv", index=False, lineterminator="\n")
    prior_candidates = {row.job_uid: row.previous_episode_locally_valid_site
                        for row in missing.itertuples() if isinstance(row.previous_episode_locally_valid_site, str)}
    sensitivity = initial_headroom_witness(plan, native, prior_candidates)
    write(output/"PREDAY_INITIAL_LAYOUT_SENSITIVITY.json", sensitivity)
    inventory = []
    for day in ("2025-05-01", "2025-05-02"):
        path = SNAPSHOT_ROOT/day/"V37_R4A_D1_SNAPSHOT.parquet"
        observed = pd.read_parquet(path, columns=["issue_time_fixed_AEST", "state_at_issue"])
        clocks = sorted(map(str, observed.issue_time_fixed_AEST.unique()))
        inventory.append(dict(source=record(path), issue_times=clocks, jobs=len(observed),
            independent_D00_observation=any(pd.Timestamp(t).timestamp() == begin for t in clocks),
            use="D1_PLANNING_SNAPSHOT_WITHOUT_SYNTHETIC_AIDC_SITE_OR_QUEUE"))
    old_replays = []
    for arm in ("B0", "B1", "B2", "B3"):
        path = NATIVE_ROOT/f"frozen_artifacts/v41r4_actual_eta95_qsafe_robust_v2/common_inputs/2025-05-01/{arm}/ACTUAL_JOB_REPLAY.json"
        if not path.is_file():
            continue
        replay = read(path)
        jobs = {r["job_uid"]: r for r in replay["job_ledger"]}
        found = [jobs[uid] for uid in missing.job_uid if uid in jobs]
        old_replays.append(dict(source=record(path), arm=arm, missing_UIDs_present=len(found),
            missing_UIDs_execution_not_established=sum(r.get("EXECUTION_STATUS") == "FROZEN_UNSELECTED_BACKLOG" for r in found),
            independent_D00_state=False, policy_specific_frozen_DA_replay=True,
            other_Arm_pre_execution_authority=False, new_Actual_completion_PASS_transferred=False))
    boundary = dict(day=plan["day"], issue_UTC=iso(issue), issue_AEST=iso(issue, "Etc/GMT-10"),
        DDAY_00_UTC=iso(begin), DDAY_00_AEST=iso(begin, "Etc/GMT-10"), Dday_issue_slot=24,
        grid_axis_conversion="issue slots [24,120) -> Dday slots [0,96)", initial_RUNNING_jobs=254,
        initial_GPU=468, fixed_site_jobs=210, fixed_site_GPU=409, fixed_sites_changed=0,
        missing_site_jobs=44, missing_site_GPU=59,
        missing_actual_completion_before_D00_jobs=int(missing.no_Dday_source_occupancy_proven.sum()),
        missing_Dday_occupation_jobs=int((missing.D00_physical_GPU > 0).sum()),
        missing_prefix_occupation_jobs=int(missing.pre_D00_capacity_or_queue_effect_requires_site.sum()),
        missing_prefix_actual_GPUh=float(missing.pre_D00_service_after_issue_GPUh.sum()),
        missing_full_historical_service_GPUh=float(missing.full_source_realized_service_GPUh.sum()),
        missing_Dday_GPUh=float(missing.Dday_source_service_GPUh.sum()),
        expected_reference_end_was_requested_remaining=True, expected_reference_end_was_actual_observation=False,
        Q50_expiry_is_not_actual_completion=True, latest_missing_actual_completion_UTC=str(missing.actual_completion_event_utc.max()),
        R0_expected_completion_and_actual_completion_separated=True,
        individual_zero_Dday_occupation="PROVEN_FROM_PRIVATE_TRACE_COMPLETION_AND_CONTROL_RELEASE",
        real_scheduler_observation_watermark="UNAVAILABLE", simulator_publication="AT_ACTUAL_COMPLETION_EVENT_ONLY",
        independent_D00_state_inventory=inventory, historical_policy_replays=old_replays,
        modeled_AIDC_D00_queue_and_episode_state_independent="NOT_ESTABLISHED",
        pre_D00_site_dependent_queue_effect="NOT_ESTABLISHED_WITHOUT_SITE",
        site_headroom_sensitivity=record(output/"PREDAY_INITIAL_LAYOUT_SENSITIVITY.json"),
        B_resolution_status="NOT_ESTABLISHED_INDEPENDENT_D00_QUEUE_AUTHORITY",
        individual_status_counts=dict(Counter(missing.classification)),
        individual_status_GPU={k:int(g.requested_GPU.sum()) for k,g in missing.groupby("classification")},
        null_original_sites_preserved=True, controller_future_event_reads=0,
        old_B0_B1_B3_replay_transferred=False, source_receipts=sources,
        outputs=[record(output/"INITIAL_RUNNING_254_AUDIT.csv"), record(output/"UNASSIGNED_RUNNING_44_LEDGER.csv")],
        Raw_or_original_files_modified=0, solver_calls=0)
    write(output/"PREDAY_DDAY_BOUNDARY_AUDIT.json", boundary)
    events = dict(schema="INITIAL_RUNNING_PRIVATE_EVENT_CAUSALITY_AUDIT_V1", status="CONTRACT_AND_SOURCE_EVENTS_ONLY_FULL_REPLAY_NOT_EXECUTED",
        issue_UTC=iso(issue), DDAY_00_UTC=iso(begin), known_RUNNING_jobs=254,
        unknown_reclassification_of_known_44=0, CC4_depletion_of_known_44=0,
        distinct_UIDs=254, duplicated_UIDs=0, original_native_sites_210_unchanged=True,
        completion_event_source=record(private_audit), real_scheduler_observation_watermarks_verified=False,
        real_scheduler_observation_watermark=None,
        simulator_publication_rule="Private completion is emitted at source actual-end event, only when event clock reaches it",
        controller_future_completion_fields_allowed=False, controller_actual_runtime_fields_allowed=False,
        completion_before_D00_used_as_issue_time_knowledge=False, Q50_expiry_GPU_release_allowed=False,
        latest_missing_completion_UTC=str(missing.actual_completion_event_utc.max()),
        last_missing_GPU_control_release_UTC=str(missing.actual_release_control_utc.max()),
        known_44_actual_source_Dday_GPUh=0., known_44_historical_service_preserved=True,
        full_population_Actual_event_execution="NOT_EXECUTED_UNTIL_INITIAL_SITE_AUTHORITY_ADMITTED",
        source_receipts=sources, solver_calls=0, original_files_modified=0)
    write(output/"ACTUAL_EVENT_CAUSALITY_AUDIT.json", events)
    if any(record(r["path"]) != r for r in sources):
        raise ValueError("BOUNDARY_INPUT_SOURCE_MUTATED")
    return boundary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--folder", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--private-audit", required=True)
    args = parser.parse_args()
    result = audit(args.folder, args.output, private_audit=args.private_audit)
    print({k:result[k] for k in ("missing_site_jobs", "missing_site_GPU", "missing_prefix_actual_GPUh", "missing_Dday_GPUh", "B_resolution_status")})


if __name__ == "__main__":
    main()
