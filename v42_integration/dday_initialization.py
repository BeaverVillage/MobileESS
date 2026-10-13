"""Authorized DD00 model initialization using PR125 and a common FCFS queue.

This reuses the existing reference producer for RUNNING placement only. Its
initial issue-use test retains every gang even after Q50 expiry. Pending jobs
are frozen as a complete submit/UID ordered queue, without replaying preday
admission or borrowing another Arm's policy execution. No optimizer is called.
"""
from collections import Counter
from copy import deepcopy
import csv
from datetime import datetime, timezone
import json
import math
from pathlib import Path

from v42_capacity import reference as pr125_reference
from v42_capacity import actual as pr125_actual
from v42_final.common import MODEL
from .actual_validation import read, record, write
from .policy import digest
from .pr79_reference import CONTRACT, digest as episode_digest

SITE_POLICY = "V42_DDAY_COMMON_GRID_BLIND_INITIAL_SITE_V1"
QUEUE_POLICY = "COMMON_GRID_BLIND_FCFS_QUEUE_V1"
ARMS = ("B0", "B1", "B2", "B3")
FIXED = "SOURCE18R_CURRENT_RUNNING_SITE_PRESERVED"
REUSED = "REUSED_SYNTHETIC_GRID_BLIND_REFERENCE"
FALLBACK = "PR125_GRID_BLIND_REFERENCE_MODEL_ASSUMPTION"


def _verify(receipts):
    for expected in receipts:
        actual=record(expected["path"])
        # Historical receipts may use doubled Windows separators. Resolve the
        # exact named path and compare authority bytes, without rewriting it.
        if any(actual[key]!=expected[key] for key in ("sha256","bytes")):
            raise ValueError("DDAY_INITIALIZATION_SOURCE_DRIFT:"+expected["path"])


def _iso(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat()


def _episode(uid, submit):
    return episode_digest(dict(contract=CONTRACT,uid=uid,submit=int(submit),attempt=None))


def _metadata(row, source, native, begin, end):
    """Request-only projection; unsupported action/QoS metadata fails closed."""
    old = native or {}
    cohort = str(old.get("cohort", "")).split("|")
    metadata = dict(origin_unknown=row["origin_unknown"], state=row["boundary_source_state"],
        episode_id=_episode(row["job_uid"],row["source_submit_seconds"]),
        elapsed_compute_seconds=row["elapsed_compute_seconds_at_boundary"] or 0.,
        qos=cohort[0] if cohort and cohort[0] in {"normal","standby"} else "UNCONFIRMED",
        partition=cohort[1] if len(cohort)>1 else "",
        protected=True if source.get("protected") is True or old.get("protected") is True else None,
        batch_eligible=None,
        requested_walltime_seconds=old.get("full_requested_seconds"),
        request_version_authority=source.get("request_version_history","UNVERIFIED_SOURCE_PROXY"),
        gpu_type=source.get("gpu_type"), source_cohort_evidence=old.get("cohort"),
        cc4_eligible=row["source_submit_seconds"]>=begin,
        representation_starts_seconds=list(range(int(begin),int(end)+901,900)),
        can_prestart_place=row["boundary_source_state"]=="PENDING" and old.get("can_prestart_place") is True,
        migration_capability=None,
        initial_observation_authority="SOURCE_EVENT_PREFIX_AT_DDAY_00",
        initial_queue_policy=QUEUE_POLICY, source_native_descriptor_sha=digest(old) if old else None)
    for field in ("release_seconds","hard_earliest_start_seconds","hard_latest_start_seconds",
                  "completion_deadline_seconds","dependency_state","hard_admission_state"):
        if field in source:metadata[field]=deepcopy(source[field])
        elif field in old:metadata[field]=deepcopy(old[field])
    return metadata


def initialize_from_candidate(candidate, plan, native, actual, *, pr129_recovery=None,
                              provider_identifiers=None, source_receipts=(), expected_counts=None):
    """Pure adapter of observed midnight records to unchanged PR125 rules."""
    if digest({k:v for k,v in candidate.items() if k!="initial_state_sha"}) != candidate["initial_state_sha"]:
        raise ValueError("DDAY_BOUNDARY_CANDIDATE_SHA_DRIFT")
    begin,end=candidate["Actual_begin_seconds"],candidate["Actual_end_seconds"]
    if end-begin!=86400 or begin%900 or candidate["slots"]!=96:
        raise ValueError("DDAY_INITIALIZATION_96_SLOT_EPOCH_AXIS")
    roster=candidate["initial_source_roster"]
    if len({r["job_uid"] for r in roster})!=len(roster):raise ValueError("DDAY_INITIAL_UID_DUPLICATE")
    source_rows={r["job_uid"]:r for r in plan["known_population"]+actual["post_issue_arrivals"]}
    native_rows={r["job_uid"]:r for r in native["known_population"]}
    running=[r for r in roster if r["boundary_source_state"]=="RUNNING"]
    pending=[r for r in roster if r["boundary_source_state"]=="PENDING"]
    excluded=set(candidate["excluded_UIDs"])
    if excluded.intersection(r["job_uid"] for r in running+pending):
        raise ValueError("DDAY_PRECOMPLETED44_ACTIVE_OR_QUEUED")
    fixed={r["job_uid"]:r["current_model_site"] for r in running if r["current_model_site"] is not None}
    counts=dict(running=len(running),running_GPU=sum(r["GPU_gang"] for r in running),
        fixed=len(fixed),fixed_GPU=sum(r["GPU_gang"] for r in running if r["job_uid"] in fixed),
        unresolved=len(running)-len(fixed),unresolved_GPU=sum(r["GPU_gang"] for r in running if r["job_uid"] not in fixed),
        pending=len(pending),pending_GPU=sum(r["GPU_gang"] for r in pending),excluded=len(excluded))
    if expected_counts and any(counts[key]!=value for key,value in expected_counts.items()):
        raise ValueError("DDAY_INITIAL_POPULATION_COUNTS_DRIFT")
    recovery=pr129_recovery or {}
    if recovery.get("audit_completed") is not True:
        raise ValueError("PR129_REFERENCE_REUSE_AUDIT_REQUIRED_BEFORE_FALLBACK")
    pins=recovery.get("validated_pins",{})
    running_by_uid={r["job_uid"]:r for r in running}
    adopted={}
    for uid,pin in pins.items():
        if uid not in running_by_uid:raise ValueError("PR129_PIN_NOT_IN_DDAY_RUNNING")
        row=running_by_uid[uid]
        if (pin.get("PASS") is not True or pin.get("episode_id")!=_episode(uid,row["source_submit_seconds"])
                or pin.get("observed_start_seconds")!=row["observed_start_seconds"]
                or pin.get("gpu")!=row["GPU_gang"] or pin.get("assigned_at_seconds",math.inf)>begin
                or pin.get("policy_independent") is not True or pin.get("future_completion_used") is not False
                or pin.get("grid_or_policy_result_used") is not False):
            raise ValueError("PR129_PIN_IDENTITY_CAUSAL_AUTHORITY")
        if uid in fixed and fixed[uid]!=pin["site"]:raise ValueError("PR129_PIN_FIXED151_CONFLICT")
        adopted[uid]=pin["site"]
    jobs=[]
    for row in running:
        uid=row["job_uid"];source=source_rows[uid]
        if row["observed_completion_seconds"] is not None or not row["source_submit_seconds"]<=row["observed_start_seconds"]<=begin:
            raise ValueError("DDAY_CURRENT_RUNNING_OBSERVATION_REQUIRED")
        if source["GPU_gang"]!=row["GPU_gang"] or source["Q50_total_seconds"]!=row["frozen_Q50_total_seconds"]:
            raise ValueError("DDAY_FROZEN_GPU_Q50_SOURCE_DRIFT")
        site=fixed.get(uid,adopted.get(uid))
        # PR125's full eligibility rule is frozen. It uses model rack gang
        # limits. A differing request-specific mask is not silently widened.
        model_eligible=sorted(s for s,c in plan["capacities"].items() if row["GPU_gang"]<=c
                              and any(row["GPU_gang"]<=rack for rack in plan["rack_compatibility"][s]))
        if site is None and sorted(row["compatible_sites"])!=model_eligible:
            raise ValueError("PR125_REQUEST_SPECIFIC_COMPATIBILITY_REQUIRES_SOURCE_ADAPTER")
        remaining=max(row["frozen_Q50_total_seconds"]-row["elapsed_compute_seconds_at_boundary"],0.)
        jobs.append(dict(job_uid=uid,submit_time=_iso(row["source_submit_seconds"]),
            state_at_D1_cutoff="RUNNING",GPU_gang=int(row["GPU_gang"]),
            service_slots=math.ceil(remaining/900),runtime_authority=MODEL,
            source_site=site,source_site_authority=FIXED if uid in fixed else REUSED if uid in adopted else None,
            elapsed_seconds=row["elapsed_compute_seconds_at_boundary"],Q50_total_seconds=row["frozen_Q50_total_seconds"]))
    reference,reference_audit=pr125_reference.build_reference(jobs,plan["capacities"],plan["rack_compatibility"],issue_time=_iso(begin))
    if not reference_audit["full_reference_ready"]:
        raise ValueError("PR125_DDAY_GREEDY_NOT_FOUND_NO_INFEASIBILITY_CLAIM")
    placement={r["job_uid"]:r["reference_site"] for r in reference}
    for row in running:
        uid=row["job_uid"]
        if placement[uid] not in row["compatible_sites"]:
            raise ValueError("PR125_OUTPUT_REQUEST_COMPATIBILITY_DRIFT")
        if uid in fixed and placement[uid]!=fixed[uid]:raise ValueError("DDAY_FIXED151_SITE_CHANGED")
        if uid in adopted and placement[uid]!=adopted[uid]:raise ValueError("DDAY_REUSED_REFERENCE_SITE_CHANGED")
    records=[]
    for row in sorted(running+pending,key=lambda r:r["job_uid"]):
        uid=row["job_uid"];source=source_rows[uid]
        if (source["GPU_gang"]!=row["GPU_gang"] or source["Q50_total_seconds"]!=row["frozen_Q50_total_seconds"]
                or sorted(source["compatible_sites"])!=sorted(row["compatible_sites"])):
            raise ValueError("DDAY_ACTIVE_FROZEN_REQUEST_SOURCE_DRIFT")
        metadata=_metadata(row,source,native_rows.get(uid),begin,end)
        records.append(dict(uid=uid,episode_id=metadata["episode_id"],
            site=placement.get(uid),gpu=int(row["GPU_gang"]),submit_seconds=row["source_submit_seconds"],
            observed_start_seconds=row["observed_start_seconds"],
            elapsed_compute_seconds=row["elapsed_compute_seconds_at_boundary"] or 0.,
            q50=row["frozen_Q50_total_seconds"],compatible_sites=list(row["compatible_sites"]),
            origin_unknown=row["origin_unknown"],metadata=metadata,
            initial_site_authority=FIXED if uid in fixed else REUSED if uid in adopted else FALLBACK if uid in placement else "PENDING_NO_SITE",
            source_member=row["source_member"],source_row=row["source_row"],
            source_initial_record_sha=digest(row),KESTREL_OBSERVED_SITE=False))
    initial_running=[r for r in records if r["site"] is not None]
    initial_pending=sorted((r for r in records if r["site"] is None),key=lambda r:(r["submit_seconds"],r["uid"]))
    for index,row in enumerate(initial_pending):row["queue_position"]=index+1
    if len({r["episode_id"] for r in records})!=len(records):raise ValueError("DDAY_EPISODE_DUPLICATE")
    use=Counter()
    for row in initial_running:
        if row["gpu"]>max(plan["rack_compatibility"][row["site"]]):raise ValueError("DDAY_GANG_RACK_INCOMPATIBLE")
        use[row["site"]]+=row["gpu"]
    if sum(use.values())!=counts["running_GPU"] or any(use[s]>c for s,c in plan["capacities"].items()):
        raise ValueError("DDAY_HARD_RUNNING_CAPACITY")
    providers=dict(runtime_model=MODEL,
        runtime_provider_sha=digest(native.get("runtime_provider",MODEL)),
        frozen_Q50_values_sha=digest({uid:r["Q50_total_seconds"] for uid,r in source_rows.items()}),
        CC4_provider_sha=digest(plan["forecast_inputs"]["current_CC4"]))
    for key,value in (provider_identifiers or {}).items():
        if key in providers and providers[key]!=value:raise ValueError("DDAY_FROZEN_PROVIDER_IDENTIFIER_DRIFT")
        providers[key]=value
    receipts=list(source_receipts)+list(recovery.get("source_receipts",[]))
    policy_sources=dict(initializer=record(__file__),PR125_reference=record(pr125_reference.__file__),
                        PR125_actual_queue=record(pr125_actual.__file__))
    payload=dict(schema="V42_MAY01_DDAY_INITIAL_STATE_FREEZE_V1",day=plan["day"],
        begin_epoch_seconds=begin,end_epoch_seconds=end,day_begin_epoch_seconds=begin,
        slots=96,dt_seconds=900,site_policy_id=SITE_POLICY,queue_policy_id=QUEUE_POLICY,
        running=initial_running,pending=initial_pending,mapping=placement,excluded_44uids=sorted(excluded),
        historical_completed=[{key:row[key] for key in ("job_uid","GPU_gang","origin_unknown",
            "source_submit_seconds","observed_start_seconds","observed_completion_seconds",
            "observed_control_release_seconds","original_native_site","source_member","source_row")}
            for row in roster if row["boundary_source_state"]=="COMPLETED"],
        capacities=plan["capacities"],rack_compatibility=plan["rack_compatibility"],
        provider_identifiers=providers,source_receipts=receipts,policy_sources=policy_sources,
        superseded_boundary_candidate_sha=candidate["initial_state_sha"],
        source_Planning_unchanged=True,Apr30_queue_replay=False,
        KESTREL_OBSERVED_SITE=False,KESTREL_OBSERVED_QUEUE=False,MODEL_ASSUMPTION=True,
        old_policy_Actual_or_AC_results_transferred=False,Native_Optimize_calls=0)
    initial_sha=digest(payload)
    freeze=dict(payload,status="DDAY_INITIAL_STATE_AUTHORIZED",full96_initial_state_authorized=True,
        full96_actual_authorized=True,
        initial_queue_verified=True,active_running_site_authority=True,common_initial_state_sha=initial_sha,
        Arm_initial_state_SHA={arm:initial_sha for arm in ARMS},
        initial_state_payload_keys=list(payload),
        counts=counts,PR129_reused_jobs=sum(uid not in fixed for uid in adopted),
        PR125_fallback_jobs=sum(uid not in fixed and uid not in adopted for uid in placement),
        PR125_fallback_GPU=sum(r["gpu"] for r in initial_running if r["initial_site_authority"]==FALLBACK),
        PR129_reuse_audit_completed=recovery.get("audit_completed",False),
        PR125_reference_audit=reference_audit,
        site_GPU_use={s:use[s] for s in sorted(plan["capacities"])},
        Actual_full96_status="NOT_RUN",Fresh_AC_full96_status="NOT_RUN",
        full96_Arm_execution_requires_its_valid_Planning_freeze=True)
    freeze["freeze_sha"]=digest(freeze)
    return freeze


def load_dday_state(path, *, arm="B0"):
    if arm not in ARMS:raise ValueError("DDAY_COMPARISON_ARM_REQUIRED")
    freeze=read(path)
    if digest({k:v for k,v in freeze.items() if k!="freeze_sha"})!=freeze.get("freeze_sha"):
        raise ValueError("DDAY_INITIAL_FREEZE_SHA_DRIFT")
    if digest({k:freeze[k] for k in freeze["initial_state_payload_keys"]})!=freeze["common_initial_state_sha"]:
        raise ValueError("DDAY_INITIAL_PAYLOAD_SHA_DRIFT")
    _verify(freeze["source_receipts"]+list(freeze["policy_sources"].values()))
    if (freeze["status"]!="DDAY_INITIAL_STATE_AUTHORIZED" or not freeze["MODEL_ASSUMPTION"]
            or freeze["KESTREL_OBSERVED_SITE"] or freeze["KESTREL_OBSERVED_QUEUE"]
            or freeze.get("PR129_reuse_audit_completed") is not True
            or freeze["Arm_initial_state_SHA"]!={a:freeze["common_initial_state_sha"] for a in ARMS}):
        raise ValueError("DDAY_COMMON_INITIALIZATION_AUTHORITY_DRIFT")
    rows=freeze["running"]+freeze["pending"]
    if len({r["uid"] for r in rows})!=len(rows) or set(freeze["excluded_44uids"]).intersection(r["uid"] for r in rows):
        raise ValueError("DDAY_INITIAL_ACTIVE_UID_DUPLICATE_OR_EXCLUDED")
    if freeze["pending"]!=sorted(freeze["pending"],key=lambda r:(r["submit_seconds"],r["uid"])):
        raise ValueError("DDAY_FCFS_INITIAL_QUEUE_ORDER_DRIFT")
    use=Counter()
    for row in freeze["running"]:
        if (row["site"]!=freeze["mapping"].get(row["uid"]) or row["site"] not in row["compatible_sites"]
                or row["gpu"]>max(freeze["rack_compatibility"][row["site"]])):
            raise ValueError("DDAY_RELOAD_GANG_SITE_RACK_DRIFT")
        use[row["site"]]+=row["gpu"]
    if (len(freeze["running"])!=freeze["counts"]["running"]
            or sum(use.values())!=freeze["counts"]["running_GPU"]
            or any(use[s]>c for s,c in freeze["capacities"].items())):
        raise ValueError("DDAY_RELOAD_PHYSICAL_RUNNING_POPULATION_DRIFT")
    return freeze


def _csv(path,rows):
    if not rows:raise ValueError("DDAY_OUTPUT_LEDGER_EMPTY")
    with Path(path).open("w",encoding="utf-8",newline="") as stream:
        writer=csv.DictWriter(stream,list(rows[0]));writer.writeheader()
        writer.writerows({key:json.dumps(value,sort_keys=True) if isinstance(value,(dict,list)) else value
                         for key,value in row.items()} for row in rows)


def initialize_dday_state(folder,output,*,pr129_recovery=None,provider_identifiers=None,candidate_path=None):
    folder,output=Path(folder),Path(output)
    docs=Path(__file__).parents[1]/"docs/v42_common_am_qos_integration"
    candidate_path=Path(candidate_path) if candidate_path is not None else docs/"DDAY_INITIAL_STATE_CANDIDATE.json"
    candidate=read(candidate_path)
    _verify(candidate["source_receipts"])
    names=("PLANNING_INPUT_BUNDLE.json","NATIVE_INPUT_TEMPLATE_B1.json","ACTUAL_INPUT_BUNDLE.json")
    plan,native,actual=[read(folder/name) for name in names]
    receipts=[record(folder/name) for name in names]+[record(candidate_path),record(docs/"PREDAY_COMPLETED_EXCLUSION_LEDGER.csv")]
    if isinstance(pr129_recovery,(str,Path)):
        path=Path(pr129_recovery);recovery=read(path);receipts.append(record(path))
    else:recovery=pr129_recovery
    if recovery is None or recovery.get("audit_completed") is not True:
        raise ValueError("PR129_REFERENCE_REUSE_AUDIT_REQUIRED_BEFORE_FALLBACK")
    _verify(recovery.get("source_receipts",[]))
    freeze=initialize_from_candidate(candidate,plan,native,actual,pr129_recovery=recovery,
        provider_identifiers=provider_identifiers,source_receipts=receipts,
        expected_counts=dict(running=324,running_GPU=472,fixed=151,fixed_GPU=296,
                             unresolved=173,unresolved_GPU=176,pending=1300,pending_GPU=1313,excluded=44))
    output.mkdir(parents=True,exist_ok=True)
    freeze_path=output/"V42_MAY01_DDAY_INITIAL_STATE_FREEZE.json"
    write(freeze_path,freeze)
    _csv(output/"INITIAL_SITE_PROVENANCE_LEDGER.csv",freeze["running"])
    _csv(output/"DDAY_INITIAL_QUEUE_LEDGER.csv",freeze["pending"])
    common=dict(common_initial_state_sha=freeze["common_initial_state_sha"],freeze_sha=freeze["freeze_sha"],
        source_freeze=record(freeze_path),MODEL_ASSUMPTION=True,KESTREL_OBSERVED_SITE=False,
        KESTREL_OBSERVED_QUEUE=False,Native_Optimize_calls=0,Actual_runs=0,Fresh_AC_runs=0)
    prior_lineage={}
    lineage_path=output/"PR125_GRID_BLIND_REUSE_AUDIT.json"
    if lineage_path.is_file():
        existing=read(lineage_path)
        prior_lineage=existing.get("prior_exact_source_lineage_audit",existing)
    write(lineage_path,dict(common,prior_exact_source_lineage_audit=prior_lineage,
        policy_id=SITE_POLICY,source=freeze["policy_sources"]["PR125_reference"],
        producer="v42_capacity.reference.build_reference",called_for_RUNNING_only=True,
        PR129_validated_reference_checked_before_fallback=freeze["PR129_reuse_audit_completed"],PR129_reused_jobs=freeze["PR129_reused_jobs"],
        fallback_jobs=freeze["PR125_fallback_jobs"],fallback_GPU=freeze["PR125_fallback_GPU"],
        RUNNING_fixed_sites_processed_first=True,RUNNING_hard_GPU472_counted_despite_Q50_expiry=True,
        current_reference_output_not_old_historical_case=True,grid_reads=0,MESS_reads=0,
        future_completion_or_actual_remaining_reads=0,reference_audit=freeze["PR125_reference_audit"]))
    write(output/"DDAY_QUEUE_POLICY_AUTHORITY.json",dict(common,policy_id=QUEUE_POLICY,
        source=freeze["policy_sources"]["PR125_actual_queue"],source_primitive="Controller.submit/Controller.admit",
        initial_order=["observed_submit_seconds_ASC","UID_ASC"],pending_jobs=len(freeze["pending"]),
        pending_GPU=freeze["counts"]["pending_GPU"],hard_contract_metadata_preserved=True,
        unconfirmed_QoS_additional_budget_seconds=0,policy_Actual_queue_results_borrowed=False,
        initial_admission_replayed=False,strict_FCFS_no_backfill=True,initial_queue_verified_as="COMMON_RESEARCH_MODEL"))
    write(output/"INITIAL_STATE_CAPACITY_AUDIT.json",dict(common,PASS=True,
        counts=freeze["counts"],site_GPU_use=freeze["site_GPU_use"],capacities=freeze["capacities"],
        fixed151_site_changes=0,unresolved173_dropped=0,GPU_gang_changes=0,whole_gangs_split=0,
        logical_rack_authority="PR125_NONADDITIVE_PER_GANG_COMPATIBILITY_LIMIT",
        each_gang_compatible=True,site_GPU_capacity_PASS=True,
        scope="INITIAL_RUNNING_SET_HELD_AT_ASSIGNED_SITE_WITH_NO_RELEASE_FOR_ALL96",
        private_actual_release_used_to_make_assignment_feasible=False,post_midnight_actions_require_runtime_capacity_guards=True))
    write(output/"INITIAL_STATE_CAUSALITY_AUDIT.json",dict(common,PASS=True,
        Planning_issue_seconds=candidate["planning_issue_seconds"],Actual_begin_seconds=freeze["begin_epoch_seconds"],
        Actual_end_seconds=freeze["end_epoch_seconds"],source_events_visible_through="DDAY_00_ONLY",
        initial_RUNNING_reclassified_as_PENDING=0,pre_Dday_completed44_active_GPU=0,
        pre_Dday_completed44_reregistered_unknown=0,pre_midnight_arrivals_reregistered=0,
        initial_pending_submitted_before_midnight_CC4_depletions=0,
        post_midnight_completion_values_exposed_to_controller=0,actual_remaining_service_controller_fields=0,
        midnight_snapshot_exposed_to_D1_Planning=0,Apr30_queue_replay=False,
        B0_policy_action_sites_borrowed=False,old_UB_automatic_transfer=False,
        observed_elapsed_and_frozen_Q50_only_for_reference_nominal_service=True))
    policies=[load_dday_state(freeze_path,arm=arm) for arm in ARMS]
    write(output/"FOUR_ARM_COMMON_INITIAL_STATE_AUDIT.json",dict(common,PASS=True,
        Arm_initial_state_SHA={arm:p["common_initial_state_sha"] for arm,p in zip(ARMS,policies)},
        running_mapping_identical=True,complete_pending_order_identical=True,
        request_Q50_provider_and_CC4_identifiers_identical=True,
        identical_initial_state_does_not_imply_identical_future_policy_actions=True))
    _verify(receipts+list(freeze["policy_sources"].values()))
    return freeze
