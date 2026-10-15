"""Derive RC01 AIDC CSVs from a completed, immutable C0/C1 replay.

This stdlib-only postprocessor never imports a controller, simulator, AC engine,
or optimizer. It creates new reports and never changes an input artifact.
"""
import argparse
from collections import defaultdict
import csv
import hashlib
import io
import json
import math
from pathlib import Path


INPUT_NAMES = (
    "INITIAL_PLACEMENT_LEDGER.json", "ACTUAL_START_LEDGER.json",
    "QUEUE_LEDGER.json", "PENDING_PRE_SITE_LEDGER.json",
    "KNOWN_CORRECTIVE_PREPLACEMENT.json", "ACTUAL_RESULT.json",
    "PUBLIC_EPISODE_STATE.json",
)
OUTPUT_NAMES = (
    "AIDC_ACTUAL_ALLOCATION_RESULTS.csv", "PRE_SITE_CANDIDATE_FUNNEL.csv",
    "KNOWN_CORRECTIVE_PREPLACEMENT.csv", "AIDC_RESULTS_DERIVATION.json",
)
ALLOCATION_FIELDS = (
    "policy", "uid", "release_case_sha", "policy_sha",
    "window_begin_seconds", "window_end_seconds", "submit_seconds",
    "initial_placement_seconds", "basic_site", "initial_placement_allowed",
    "initial_authority", "source_customer_permission_claim", "can_prestart_place",
    "source_site", "GPU", "Q50_seconds", "actual_started", "actual_site",
    "actual_start_seconds", "completion_observed_seconds", "latest_state",
    "PreSiteChanged", "observed_compute_GPUh", "changed_compute_GPUh",
    "queue_reason", "queue_reason_source", "last_candidate_seconds", "last_chosen_site",
    "last_STAY_feasible", "last_STAY_reason", "PRE_SITE_candidate_attempts",
    "feasible_PRE_SITE_candidate_attempts",
)
FUNNEL_FIELDS = (
    "policy", "count_type", "reason", "event_count", "unique_UID_count",
    "count_scope", "actual_change_claim",
)
CORRECTIVE_FIELDS = (
    "policy", "source_row", "uid", "row_kind", "command_type", "status",
    "trigger_seconds", "original_planned_site", "original_planned_start_seconds",
    "actual_site", "actual_start_seconds", "actual_started", "executed_site_change",
    "GPU_capacity_conflict", "ready_at_seconds", "transfer_seconds",
    "preparation_seconds", "source_sha", "planning_command_sha",
    "planning_command_modified", "qos_preparation_budget_used_seconds",
    "shared_qos_budget_seconds", "reason", "rejected_candidates", "source_row_json",
)


def file_record(path):
    path = Path(path).resolve()
    content = path.read_bytes()
    return {"path": str(path), "bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest()}


def load(path, receipts):
    before = file_record(path)
    def reject_constant(value):
        raise ValueError("NONFINITE_INPUT_JSON:" + value)
    document = json.loads(Path(path).read_text(encoding="utf-8-sig"),
                          parse_constant=reject_constant)
    if file_record(path) != before:
        raise ValueError("INPUT_CHANGED_WHILE_READING:" + str(path))
    receipts.append(before)
    return document


def number(value, name, *, nullable=False):
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("FINITE_NUMERIC_FIELD_REQUIRED:" + name)
    return value


def unique(rows, key, name):
    if not isinstance(rows, list):
        raise ValueError("LEDGER_ARRAY_REQUIRED:" + name)
    result = {}
    for row in rows:
        uid = str(row[key])
        if uid in result:
            raise ValueError("DUPLICATE_UID:" + name + ":" + uid)
        result[uid] = row
    return result


def cell(value):
    # CSV null is explicit; zero and False remain real observations.
    if value is None:
        return "null"
    if isinstance(value, (dict, list, tuple, bool)):
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return value


def csv_bytes(rows, fields):
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction="raise")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: cell(row.get(key)) for key in fields})
    return buffer.getvalue().encode("utf-8")


def derive_policy(label, documents):
    metrics = documents["ACTUAL_RESULT.json"]
    if metrics.get("policy") != label or metrics.get("status") != "EXECUTED_DIAGNOSTIC":
        raise ValueError("COMPLETED_CANONICAL_POLICY_RESULT_REQUIRED:" + label)
    state = documents["PUBLIC_EPISODE_STATE.json"]
    window_end = number(state["at_seconds"], label + ".at_seconds")
    slots = number(metrics["slots"], label + ".slots")
    if type(slots) is not int or not 0 < slots <= 96:
        raise ValueError("EXPLICIT_POSITIVE_SLOT_COUNT_REQUIRED:" + label)
    window_begin = window_end - slots * 900
    initial = unique(documents["INITIAL_PLACEMENT_LEDGER.json"], "uid", label + ".initial")
    queue = unique(documents["QUEUE_LEDGER.json"], "job_uid", label + ".queue")
    starts = unique(documents["ACTUAL_START_LEDGER.json"], "uid", label + ".starts")
    requests, metadata = state.get("requests", {}), state.get("metadata", {})
    events = documents["PENDING_PRE_SITE_LEDGER.json"]
    corrective = documents["KNOWN_CORRECTIVE_PREPLACEMENT.json"]
    if not isinstance(events, list) or not isinstance(corrective, list):
        raise ValueError("CANDIDATE_AND_CORRECTIVE_ARRAYS_REQUIRED:" + label)
    events_by_uid = defaultdict(list)
    for event in events:
        events_by_uid[str(event["uid"])].append(event)
    queued_events = defaultdict(list)
    for event in state.get("job_event_ledger", []):
        if event.get("event") == "QUEUED" and event.get("reason") is not None:
            queued_events[str(event["uid"])].append(event)
    unknown = {uid: row for uid, row in queue.items() if row.get("origin_unknown") is True}
    if set(initial) != set(unknown):
        raise ValueError("INITIAL_UNKNOWN_ROSTER_MISMATCH:" + label)
    if set(events_by_uid) - set(unknown):
        raise ValueError("UNOBSERVED_UID_IN_UNKNOWN_CANDIDATES:" + label)
    allocations = []
    for uid, row in sorted(unknown.items(), key=lambda item: (item[1]["submit_time"], item[0])):
        placement = initial[uid]
        request, public = requests.get(uid, {}), metadata.get(uid, {})
        start = row.get("admitted_time")
        actual_start = starts.get(uid)
        if (start is not None) != (actual_start is not None):
            raise ValueError("UNKNOWN_START_LEDGER_MISMATCH:" + label + ":" + uid)
        if actual_start is not None:
            if (actual_start.get("origin_unknown") is not True or actual_start.get("site") != row.get("site")
                    or actual_start.get("time_seconds") != start
                    or actual_start.get("basic_site") != placement.get("basic_site")):
                raise ValueError("UNKNOWN_START_DETAILS_MISMATCH:" + label + ":" + uid)
            if not window_begin <= number(start, uid + ".start") < window_end:
                raise ValueError("ACTUAL_START_OUTSIDE_OBSERVED_WINDOW:" + label + ":" + uid)
        completion = number(row.get("completion_observed_time"), uid + ".completion", nullable=True)
        if completion is not None and (completion > window_end or start is None or completion < start):
            raise ValueError("UNOBSERVED_OR_INVALID_COMPLETION:" + label + ":" + uid)
        gpu = number(row.get("GPU_gang"), uid + ".GPU", nullable=True)
        q50 = number(request.get("q50", public.get("t50_seconds")), uid + ".Q50", nullable=True)
        if gpu is not None and gpu < 0 or q50 is not None and q50 < 0:
            raise ValueError("NEGATIVE_PUBLIC_JOB_QUANTITY:" + label + ":" + uid)
        if request.get("gpu", gpu) != gpu or public.get("gpu", gpu) != gpu:
            raise ValueError("PUBLIC_GPU_JOIN_MISMATCH:" + label + ":" + uid)
        basic, site = placement.get("basic_site"), row.get("site")
        changed = False if start is None else None if basic is None or site is None else site != basic
        work = (0. if start is None else None if gpu is None else
                gpu * max(0., min(window_end, window_end if completion is None else completion)
                          - max(window_begin, start)) / 3600.)
        changed_work = None if changed is None or work is None else work if changed else 0.
        history = sorted(events_by_uid[uid], key=lambda item: item["time_seconds"])
        latest = history[-1] if history else {}
        stay = next((c for c in latest.get("candidates", []) if c.get("kind") == "STAY"), {})
        alternatives = [c for event in history for c in event.get("candidates", []) if c.get("kind") == "PRE_SITE"]
        if start is None:
            queue_reason = (stay.get("reason") if latest.get("chosen_site") is None else
                            "SELECTED_CANDIDATE_NOT_OBSERVED_STARTED") if history else "NO_CONTROL_TICK_CANDIDATE_OBSERVED"
            reason_source = "LAST_STAY_CANDIDATE" if history else "NO_CANDIDATE_OBSERVED"
            last_queued = max(queued_events[uid], key=lambda item: item["time_seconds"], default=None)
            if last_queued is not None and last_queued["time_seconds"] >= latest.get("time_seconds", -math.inf):
                queue_reason = last_queued["reason"]
                reason_source = "PUBLIC_EPISODE_STATE.job_event_ledger.QUEUED"
        else:
            queue_reason = None
            reason_source = None
        allocations.append(dict(
            policy=label, uid=uid, release_case_sha=metrics.get("release_case_sha"),
            policy_sha=metrics.get("policy_sha"), window_begin_seconds=window_begin,
            window_end_seconds=window_end, submit_seconds=row.get("submit_time"),
            initial_placement_seconds=placement.get("time_seconds"), basic_site=basic,
            initial_placement_allowed=placement.get("allowed"), initial_authority=placement.get("authority"),
            source_customer_permission_claim=placement.get("source_customer_permission_claim"),
            can_prestart_place=placement.get("can_prestart_place"), source_site=request.get("source_site"),
            GPU=gpu, Q50_seconds=q50, actual_started=start is not None, actual_site=site,
            actual_start_seconds=start, completion_observed_seconds=completion, latest_state=row.get("latest_state"),
            PreSiteChanged=changed, observed_compute_GPUh=work, changed_compute_GPUh=changed_work,
            queue_reason=queue_reason, queue_reason_source=reason_source,
            last_candidate_seconds=latest.get("time_seconds"),
            last_chosen_site=latest.get("chosen_site"), last_STAY_feasible=stay.get("feasible"),
            last_STAY_reason=stay.get("reason"), PRE_SITE_candidate_attempts=len(alternatives),
            feasible_PRE_SITE_candidate_attempts=sum(c.get("feasible") is True for c in alternatives)))

    funnel = []
    def count(kind, rows, *, reason=None, scope="EVENT_ROWS", actual_change=False):
        funnel.append(dict(policy=label, count_type=kind, reason=reason, event_count=len(rows),
                           unique_UID_count=len({str(r["uid"]) for r in rows}),
                           count_scope=scope, actual_change_claim=actual_change))
    count("UNKNOWN_SUBMITTED", [{"uid": uid} for uid in unknown], scope="OBSERVED_UIDS")
    count("INITIAL_PLACEMENT", list(initial.values()), scope="DESIGNATION_NOT_GPU_START")
    count("INITIAL_ALLOWED", [r for r in initial.values() if r.get("allowed") is True], scope="DESIGNATION_NOT_GPU_START")
    for authority in sorted({r.get("authority") for r in initial.values() if r.get("authority") is not None}):
        count("INITIAL_AUTHORITY", [r for r in initial.values() if r.get("authority") == authority],
              reason=authority, scope="DESIGNATION_NOT_GPU_START")
    for kind, selected in (
        ("UNKNOWN_ACTUAL_STARTED", [r for r in allocations if r["actual_started"]]),
        ("UNKNOWN_STAY_ACTUAL_STARTED", [r for r in allocations if r["actual_started"] and r["PreSiteChanged"] is False]),
        ("UNKNOWN_PRE_SITE_ACTUAL_CHANGED", [r for r in allocations if r["PreSiteChanged"] is True]),
        ("UNKNOWN_UNSTARTED_AT_WINDOW_END", [r for r in allocations if not r["actual_started"]]),
    ):
        count(kind, selected, scope="OBSERVED_ACTUAL_UIDS", actual_change=kind == "UNKNOWN_PRE_SITE_ACTUAL_CHANGED")
    expanded = [dict(c, uid=str(event["uid"])) for event in events for c in event.get("candidates", [])]
    for kind in ("STAY", "PRE_SITE"):
        candidates = [c for c in expanded if c.get("kind") == kind]
        count(kind + "_CANDIDATE_ATTEMPTS", candidates, scope="CANDIDATE_SITE_TICK_ROWS_NOT_CHANGES")
        count(kind + "_FEASIBLE_CANDIDATE_ATTEMPTS", [c for c in candidates if c.get("feasible") is True],
              scope="CANDIDATE_SITE_TICK_ROWS_NOT_CHANGES")
        reasons = sorted({c.get("reason") for c in candidates if c.get("feasible") is not True and c.get("reason") is not None})
        for reason in reasons:
            count(kind + "_REJECTED_CANDIDATE_ATTEMPTS", [c for c in candidates if c.get("reason") == reason],
                  reason=reason, scope="CANDIDATE_SITE_TICK_ROWS_NOT_CHANGES")

    corrections = []
    for ordinal, row in enumerate(corrective):
        uid = str(row["uid"])
        if uid not in queue or queue[uid].get("origin_unknown") is not False:
            raise ValueError("KNOWN_CORRECTIVE_UID_JOIN_MISMATCH:" + label + ":" + uid)
        command = row.get("command_type") == "ACTUAL_CORRECTIVE_COMMAND"
        if not command and not (row.get("status") == "QUEUE" and row.get("reason") == "NO_SAFE_CORRECTIVE_SITE"):
            raise ValueError("UNRECOGNIZED_KNOWN_CORRECTIVE_ROW:" + label + ":" + uid)
        executed = command and row.get("actual_start_seconds") is not None
        if executed:
            event = starts.get(uid, {})
            if (event.get("time_seconds") != row["actual_start_seconds"]
                    or event.get("site") != row.get("actual_site")):
                raise ValueError("CORRECTIVE_COMMAND_NOT_OBSERVED_EXECUTED:" + label + ":" + uid)
        changed = (False if not executed else None if row.get("original_planned_site") is None
                   or row.get("actual_site") is None else row["actual_site"] != row["original_planned_site"])
        corrections.append({**{key: row.get(key) for key in CORRECTIVE_FIELDS},
                            "policy": label, "source_row": ordinal, "uid": uid,
                            "row_kind": "ACTUAL_CORRECTIVE_COMMAND" if command else "FAILED_CONFLICT_ATTEMPT",
                            "actual_started": bool(executed), "executed_site_change": changed,
                            "source_row_json": row})
    commands = [r for r in corrections if r["row_kind"] == "ACTUAL_CORRECTIVE_COMMAND"]
    failures = [r for r in corrections if r["row_kind"] == "FAILED_CONFLICT_ATTEMPT"]
    count("KNOWN_CORRECTIVE_COMMAND_ISSUED", commands, scope="COMMAND_ROWS_NOT_EXECUTED_CHANGES")
    count("KNOWN_CORRECTIVE_EXECUTED_SITE_CHANGE", [r for r in commands if r["executed_site_change"] is True],
          scope="OBSERVED_ACTUAL_COMMAND_EXECUTIONS", actual_change=True)
    count("KNOWN_FAILED_CONFLICT_ATTEMPT", failures, scope="FAILED_ATTEMPT_ROWS_NOT_CHANGES")

    derived = dict(
        Unknown_submitted_UIDs=len(unknown), Unknown_initial_placed_UIDs=sum(r.get("allowed") is True for r in initial.values()),
        Unknown_started_UIDs=sum(r["actual_started"] for r in allocations),
        PreSite_candidate_UIDs=len({c["uid"] for c in expanded if c.get("kind") == "PRE_SITE"}),
        authorized_ready_alternative_UIDs=len({c["uid"] for c in expanded if c.get("kind") == "PRE_SITE" and c.get("feasible") is True}),
        PreSite_changed_UIDs=sum(r["PreSiteChanged"] is True for r in allocations),
        changed_GPUh=None if any(r["changed_compute_GPUh"] is None for r in allocations) else sum(r["changed_compute_GPUh"] for r in allocations),
        Unknown_STAY_started_UIDs=sum(r["actual_started"] and r["PreSiteChanged"] is False for r in allocations),
        Unknown_queued_UIDs=sum(not r["actual_started"] for r in allocations))
    reconciliation = []
    for name, calculated in derived.items():
        reported = metrics.get(name)
        agreement = None if reported is None or calculated is None else math.isclose(
            number(reported, label + "." + name), number(calculated, "derived." + name), rel_tol=1e-9, abs_tol=1e-9)
        if agreement is False:
            raise ValueError("OBSERVED_METRIC_RECONCILIATION_MISMATCH:" + label + ":" + name)
        reconciliation.append(dict(metric=name, reported=reported, derived=calculated,
                                   agreement=agreement, status="NOT_REPORTED" if reported is None else
                                   "DERIVATION_UNAVAILABLE" if calculated is None else "MATCH"))
    return allocations, funnel, corrections, dict(
        window_begin_seconds=window_begin, window_end_seconds=window_end, slots=slots,
        metrics_from_ACTUAL_RESULT=metrics, derived_observed_metrics=derived,
        reconciliation=reconciliation, corrective_command_rows=len(commands),
        failed_conflict_attempt_rows=len(failures),
        corrective_executed_site_changes=sum(r["executed_site_change"] is True for r in commands))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="Completed AIDC/REPLAY02 folder")
    args = parser.parse_args()
    root = args.root.resolve(strict=True)
    postprocessor = file_record(Path(__file__))
    targets = [root / name for name in OUTPUT_NAMES]
    for target in targets:
        if target.exists():
            raise FileExistsError("DERIVED_REPORT_MUST_NOT_OVERWRITE:" + str(target))
    receipts = []
    completed = load(root / "COMPARISON_COMPLETE.json", receipts)
    if completed.get("status") != "COMPARISON_COMPLETE":
        raise ValueError("COMPLETED_C0_C1_REPLAY_REQUIRED")
    common_path = root / "COMMON_RUN_INPUTS.json"
    common = load(common_path, receipts) if common_path.is_file() else None
    allocations, funnel, corrections, policies = [], [], [], {}
    for label in ("C0", "C1"):
        documents = {name: load(root / label / name, receipts) for name in INPUT_NAMES}
        rows, counts, commands, detail = derive_policy(label, documents)
        allocations.extend(rows); funnel.extend(counts); corrections.extend(commands); policies[label] = detail
        metrics = detail["metrics_from_ACTUAL_RESULT"]
        if metrics.get("release_case_sha") != completed.get("release_case_sha"):
            raise ValueError("COMPLETED_CASE_IDENTITY_MISMATCH:" + label)
        if completed.get("results", {}).get(label) != metrics:
            raise ValueError("COMPLETED_POLICY_RESULT_BYTES_SEMANTICS_MISMATCH:" + label)
        if common is not None and metrics.get("release_case_sha") != common.get("release_case_sha"):
            raise ValueError("COMMON_CASE_IDENTITY_MISMATCH:" + label)
    if any(policies["C0"][key] != policies["C1"][key] for key in ("window_begin_seconds", "window_end_seconds", "slots")):
        raise ValueError("C0_C1_OBSERVED_WINDOW_MISMATCH")
    for key in ("release_case_sha", "historical_case_sha", "MESS_plan_sha"):
        if policies["C0"]["metrics_from_ACTUAL_RESULT"].get(key) != policies["C1"]["metrics_from_ACTUAL_RESULT"].get(key):
            raise ValueError("C0_C1_FIXED_IDENTITY_MISMATCH:" + key)
    contents = [csv_bytes(allocations, ALLOCATION_FIELDS), csv_bytes(funnel, FUNNEL_FIELDS),
                csv_bytes(corrections, CORRECTIVE_FIELDS)]
    if file_record(Path(__file__)) != postprocessor:
        raise ValueError("POSTPROCESSOR_CHANGED_DURING_DERIVATION")
    for receipt in receipts:
        if file_record(receipt["path"]) != receipt:
            raise ValueError("DERIVATION_INPUT_CHANGED:" + receipt["path"])
    for target in targets:
        if target.exists():
            raise FileExistsError("DERIVED_REPORT_MUST_NOT_OVERWRITE:" + str(target))
    # The JSON receipt is written last; its presence marks completed derivation.
    outputs = []
    for target, content in zip(targets[:3], contents):
        with target.open("xb") as stream:
            stream.write(content)
        outputs.append(file_record(target))
    report = dict(
        schema="RC01_AIDC_OBSERVED_REPORT_DERIVATION_V1", status="DERIVED_FROM_COMPLETED_REPLAY",
        root=str(root), release_case_sha=completed.get("release_case_sha"),
        input_files=receipts, postprocessor=postprocessor, output_files=outputs,
        policies=policies, allocation_rows=len(allocations), funnel_rows=len(funnel),
        corrective_rows=len(corrections), nullable_CSV_encoding="literal null; observed zero is 0",
        changed_GPUh_formula="GPU * observed overlap([actual_start, observed_completion_or_window_end), observed_window) / 3600; only actual_site != basic_site",
        corrective_attempts_are_not_executed_changes=True,
        Q50_source="PUBLIC_EPISODE_STATE.requests[UID].q50; metadata.t50_seconds fallback; absent remains null",
        window_source="PUBLIC_EPISODE_STATE.at_seconds minus ACTUAL_RESULT.slots*900",
        additional_Actual_runs=0, additional_AC_calls=0, additional_Native_calls=0,
        Fresh_AC_evaluated_by_postprocessor=False, physical_safety_certified_by_postprocessor=False,
        inherited_metrics_not_reinterpreted=True, original_sources_or_controller_files_modified=False)
    with targets[3].open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps(dict(status=report["status"], root=str(root), allocation_rows=len(allocations),
                          corrective_rows=len(corrections), outputs=[str(p) for p in targets]), ensure_ascii=False))


if __name__ == "__main__":
    main()
