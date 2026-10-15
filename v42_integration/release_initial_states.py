"""Independent May D0 states from source events and the approved PR125 policy.

This adapter performs no admission replay, solver call, AC solve or new site
optimization. Future event times are projected away before the original
boundary/initialization functions receive any input.
"""
from collections import Counter
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import gzip
import hashlib
import json
from pathlib import Path
from unittest.mock import patch
import zipfile

from .policy import digest
from .dday_boundary import build_boundary_candidate
from . import dday_initialization as initializer
from .source_recovery import episode_id

INITIAL_SHA = "d8aae451858d7ab8579f087ac9811d04f83a8c10bd7e6fc1b2156e35b2db7003"
INITIAL_SEMANTIC = "5df25289619221a8ed1f7ee6d13a00e73ad5a4e38ac0cf08228e93c3fb67c573"
POLICY = "V42_INDEPENDENT_MAY_D0_ORIGINAL_EVENT_PREFIX_PR125_V1"
EXPECTED_SOURCE = {
    "dday_initialization.py": "7436e318b2377858fc1655c94061f863b3e7b36730f71d4b510c52eb950f5005",
    "reference.py": "2baf1e03c9328676d94a1dc83bc6b75143e385efa988cc24c333eab1bf73df04",
    "actual.py": "2343d8b3f169d3009cb99b07157bce1cdb3c4fb13c76d10602491ce36305a294",
}


def read(path):
    path = Path(path)
    data = gzip.decompress(path.read_bytes()) if path.suffix == ".gz" else path.read_bytes()
    return json.loads(data.decode("utf-8-sig"))


def record(path):
    path = Path(path)
    sha = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            sha.update(block)
    return dict(path=str(path.resolve()), sha256=sha.hexdigest(), bytes=path.stat().st_size)


def checked(receipt):
    path = Path(receipt["path"])
    text = str(path).replace("\\", "/")
    candidates = [path]
    for prefix, replacement in [
        ("C:/Users/kjw39/OneDrive/문서/ChatGPT/Mobile ESS 2", "D:/ChatGPT/Mobile ESS 2"),
        ("C:/codex_mobileess_workspace", "D:/codex_mobileess_workspace"),
    ]:
        if text.startswith(prefix):
            candidates.append(Path(replacement + text[len(prefix):]))
    for candidate in candidates:
        if candidate.is_file():
            actual = record(candidate)
            if all(actual[k] == receipt[k] for k in ("sha256", "bytes")):
                return candidate
    raise ValueError("EXACT_SOURCE_UNAVAILABLE:" + str(path))


def midnight(day):
    return datetime.fromisoformat(day).replace(tzinfo=timezone(timedelta(hours=10))).timestamp()


def seconds(value):
    if value is None:
        return None
    return float(value) if isinstance(value, (int, float)) else datetime.fromisoformat(str(value)).timestamp()


def causal_event(row, source, boundary):
    """Only source events already observed at this D0 can leave this function."""
    uid = str(row["id"])
    submit, start, end = (seconds(row.get(k)) for k in ("submit_time", "start_time", "end_time"))
    if uid != source["job_uid"] or submit != seconds(source["submit_time"]):
        raise ValueError("RAW_REQUEST_UID_OR_SUBMIT_MISMATCH")
    if submit > boundary:
        raise ValueError("FUTURE_UNKNOWN_REQUEST_AT_D0")
    if start is not None and start < submit or end is not None and (start is None or end < start):
        raise ValueError("RAW_EVENT_ORDER")
    if row.get("gpus_requested") is None or float(row["gpus_requested"]) != source["GPU_gang"]:
        raise ValueError("RAW_IMMUTABLE_GPU_REQUEST_MISMATCH")
    return dict(submit_seconds=submit,
        observed_start_seconds=start if start is not None and start <= boundary else None,
        observed_completion_seconds=end if end is not None and end <= boundary else None,
        event_source_member=source["source_member"], event_source_row=int(source["source_row"]))


def public_population(plan, actual, boundary):
    """Discard future UID descriptors before source extraction and compilation."""
    rows = plan["known_population"] + [r for r in actual["post_issue_arrivals"]
        if seconds(r["submit_time"]) <= boundary]
    if any(seconds(r["submit_time"]) > boundary for r in rows):
        raise ValueError("PLANNING_REQUEST_NOT_PUBLIC_AT_D0")
    if len({r["job_uid"] for r in rows}) != len(rows):
        raise ValueError("D0_PUBLIC_UID_DUPLICATE")
    return rows


def project_archive(archive, day_inputs):
    """Single sequential read; public outputs never retain future completion."""
    import pyarrow.parquet as pq
    import pandas as pd
    path = checked(archive)
    wanted = {}
    for day, data in day_inputs.items():
        for source in public_population(data["plan"], data["actual"], midnight(day)):
            key = (source["source_member"], int(source["source_row"]))
            wanted.setdefault(key, []).append((day, source))
    events = {d: {} for d in day_inputs}
    requests = {d: [] for d in day_inputs}
    members = sorted({key[0] for key in wanted})
    columns = ["id", "submit_time", "start_time", "end_time", "gpus_requested", "qos", "partition", "wallclock_req"]
    with zipfile.ZipFile(path) as archive_file:
        for member in members:
            if not any(f"/year=2025/month={m}/" in member for m in (4, 5)):
                raise ValueError("SOURCE_EVENT_MONTH_OUTSIDE_APPROVED_APRIL_MAY")
            indices = {key[1] for key in wanted if key[0] == member}
            with archive_file.open(member) as stream:
                offset = 0
                for batch in pq.ParquetFile(stream).iter_batches(columns=columns, batch_size=32768, use_threads=False):
                    frame = batch.to_pandas()
                    selected = [i - offset for i in indices if offset <= i < offset + len(frame)]
                    for local in selected:
                        row = frame.iloc[local].to_dict()
                        for name in ("submit_time", "start_time", "end_time"):
                            row[name] = None if pd.isna(row[name]) else row[name].isoformat()
                        for day, source in wanted[(member, offset + local)]:
                            uid = source["job_uid"]
                            if uid in events[day]:
                                raise ValueError("RAW_SOURCE_UID_DUPLICATE")
                            events[day][uid] = causal_event(row, source, midnight(day))
                            requests[day].append(dict(uid=uid, source_member=member, source_row=offset + local,
                                request_GPU_gang=int(source["GPU_gang"]), raw_qos=row["qos"], raw_partition=row["partition"],
                                requested_walltime_seconds=None if pd.isna(row["wallclock_req"]) else row["wallclock_req"].total_seconds(),
                                request_version_authority="UNVERIFIED_SOURCE_PROXY",
                                source_state_and_realized_duration_fields_not_exported=True))
                    offset += len(frame)
    for day, data in day_inputs.items():
        if set(events[day]) != {r["job_uid"] for r in public_population(data["plan"], data["actual"], midnight(day))}:
            raise ValueError("RAW_PREFIX_SOURCE_JOIN_INCOMPLETE:" + day)
    return events, requests, record(path)


def prior_reference_pins(candidate, plan, native, prior_reference, prior_freeze, *, reference_record, receipts=()):
    """The May01 PR129 checks, with date/count constants made case specific."""
    issue, begin = seconds(plan["issue_time"]), candidate["Actual_begin_seconds"]
    if prior_freeze.get("day") != plan["day"] or not prior_freeze.get("freeze_before_Actual_truth"):
        raise ValueError("PRIOR_REFERENCE_NOT_SAME_DAY_PRE_ACTUAL_FREEZE")
    expected = prior_freeze["reference"]
    if any(expected[k] != reference_record[k] for k in ("sha256", "bytes")):
        raise ValueError("PRIOR_REFERENCE_FREEZE_SHA_MISMATCH")
    audit = prior_reference["audit"]
    if any(audit.get(k) != 0 for k in ("actual_reads", "voltage_reads", "optimizer_calls")) or not audit.get("full_reference_ready"):
        raise ValueError("PRIOR_REFERENCE_NOT_GRID_BLIND_COMPLETE")
    refs = {r["job_uid"]: r for r in prior_reference["rows"]}
    if set(refs) != {r["job_uid"] for r in plan["known_population"]} or len(refs) != len(prior_reference["rows"]):
        raise ValueError("PRIOR_REFERENCE_CURRENT_KNOWN_UID_MISMATCH")
    running = [r for r in candidate["initial_source_roster"] if r["boundary_source_state"] == "RUNNING"]
    fixed = {r["job_uid"]: r["current_model_site"] for r in running if r["current_model_site"] is not None}
    fixed_use, proposed_use = Counter(), Counter()
    for row in running:
        uid = row["job_uid"]
        if uid in fixed:
            fixed_use[fixed[uid]] += row["GPU_gang"]
        elif uid in refs:
            proposed_use[refs[uid]["reference_site"]] += row["GPU_gang"]
    overloaded = {s for s, cap in plan["capacities"].items() if fixed_use[s] + proposed_use[s] > cap}
    pins, rejected = {}, []
    for row in running:
        uid = row["job_uid"]
        if uid in fixed:
            continue
        old = refs.get(uid)
        same_request = bool(old and old["source_member"] == row["source_member"] and int(old["source_row"]) == row["source_row"]
            and seconds(old["submit_time"]) == row["source_submit_seconds"] and old["GPU_gang"] == row["GPU_gang"]
            and old["Q50_total_seconds"] == row["frozen_Q50_total_seconds"])
        same_episode = bool(same_request and ((old["state_at_D1_cutoff"] == "RUNNING"
            and issue - old["elapsed_seconds"] == row["observed_start_seconds"])
            or (old["state_at_D1_cutoff"] == "PENDING" and issue <= row["observed_start_seconds"] <= begin)))
        site = old.get("reference_site") if old else None
        allowed = bool(site in row["compatible_sites"] and site in plan["capacities"]
            and any(row["GPU_gang"] <= limit for limit in plan["rack_compatibility"].get(site, ())))
        passed = bool(same_episode and begin - issue == 21600 and allowed and site not in overloaded
            and old.get("site_authority_source") == "USER_DEFINED_GRID_BLIND_REFERENCE_PLACEMENT")
        if passed:
            pins[uid] = dict(PASS=True, episode_id=episode_id(uid, row["source_submit_seconds"]), site=site,
                observed_start_seconds=row["observed_start_seconds"], gpu=row["GPU_gang"], assigned_at_seconds=issue,
                policy_independent=True, future_completion_used=False, grid_or_policy_result_used=False,
                KESTREL_OBSERVED_SITE=False, source_receipt=reference_record)
        else:
            rejected.append(dict(uid=uid, reason="ENTIRE_PRIOR_SITE_GROUP_OVERLOAD" if site in overloaded else
                "NO_SAME_PUBLIC_REQUEST_EPISODE_REFERENCE_AUTHORITY"))
    return dict(audit_completed=True, validated_pins=pins, source_receipts=list(receipts),
        policy="ORIGINAL_PR129_EPISODE_IDENTITY_AND_JOINT_CAPACITY_REUSE_CHECKS",
        overloaded_reference_site_groups_rejected_entirely=sorted(overloaded), rejected=rejected,
        independent_D0=True, previous_day_Actual_carry_used=False, Native_Optimize_calls=0)


def compile_state(day, data, events, recovery, source_receipts):
    plan, native = data["plan"], data["native"]
    begin = midnight(day)
    public_actual = dict(post_issue_arrivals=[r for r in data["actual"]["post_issue_arrivals"]
        if seconds(r["submit_time"]) <= begin])
    excluded = {r["job_uid"] for r in native["known_population"] if r["state"] == "RUNNING"
        and r.get("current_site_if_running") is None
        and events[r["job_uid"]]["observed_completion_seconds"] is not None}
    candidate, audit, _ = build_boundary_candidate(plan, native, public_actual, events, excluded,
        source_receipts=source_receipts)
    result = initializer.initialize_from_candidate(candidate, plan, native, public_actual,
        pr129_recovery=recovery, source_receipts=source_receipts)
    active = result["running"] + result["pending"]
    if any(r["submit_seconds"] > begin or r.get("observed_start_seconds") is not None and r["observed_start_seconds"] > begin for r in active):
        raise ValueError("COMPILED_STATE_FUTURE_EVENT_LEAK")
    if result["day"] != day or result["begin_epoch_seconds"] != begin:
        raise ValueError("COMPILED_STATE_DAY_AXIS_MISMATCH")
    return result, candidate, audit


def reproduce_may01(original_path, raw_root, original_docs):
    original = read(original_path)
    if record(original_path)["sha256"] != INITIAL_SHA or original["common_initial_state_sha"] != INITIAL_SEMANTIC:
        raise ValueError("APPROVED_MAY01_INITIAL_SOURCE_DRIFT")
    source = original["policy_sources"]
    for expected in source.values():
        checked(expected)
    actual_sources = [record(initializer.__file__), record(initializer.pr125_reference.__file__), record(initializer.pr125_actual.__file__)]
    if any(EXPECTED_SOURCE[Path(row["path"]).name] != row["sha256"] for row in actual_sources):
        raise ValueError("ORIGINAL_INITIALIZATION_POLICY_SOURCE_DRIFT")
    folder = Path(raw_root) / "2025-05-01"
    plan, native, actual = [read(folder / n) for n in ("PLANNING_INPUT_BUNDLE.json", "NATIVE_INPUT_TEMPLATE_B1.json", "ACTUAL_INPUT_BUNDLE.json")]
    candidate = read(Path(original_docs) / "DDAY_INITIAL_STATE_CANDIDATE.json")
    recovery = read(Path(original_docs) / "PR129_REFERENCE_SITE_RECOVERY.json")
    original_records = {Path(v["path"]).name: v for v in source.values()}
    # Reuse the historical path strings for byte-identical semantic replay;
    # every local implementation byte was independently checked above.
    with patch.object(initializer, "record", side_effect=lambda p: deepcopy(original_records[Path(p).name])):
        rebuilt = initializer.initialize_from_candidate(candidate, plan, native, actual,
            pr129_recovery=recovery, source_receipts=original["source_receipts"][:6], expected_counts=original["counts"])
    if rebuilt != original:
        raise ValueError("MAY01_ORIGINAL_INITIALIZER_EXACT_REPRODUCTION_FAILED")
    return dict(PASS=True, original=record(original_path), semantic_sha=INITIAL_SEMANTIC,
        complete_object_equal=True, running=324, running_GPU=472, pending=1300,
        original_source_bytes=actual_sources, Native_Optimize_calls=0,
        historical_receipt_path_strings_preserved_for_exact_reproduction=True)


def verify_cc4(day, plan, cc4_path):
    cc4 = read(cc4_path)
    if cc4 != plan["forecast_inputs"]["current_CC4"] or cc4["target_day"] != day or cc4["future_job_ids"] != []:
        raise ValueError("CC4_FROZEN_DAY_ROW_OR_ANONYMITY_MISMATCH")
    issue = seconds(cc4["issue_time"])
    if issue > seconds(plan["issue_time"]) or issue > midnight(day):
        raise ValueError("CC4_FUTURE_ISSUE")
    if len(cc4["Q50_GPUh"]) != 24 or len(cc4["nominal_unknown_GPU_96"]) != 96:
        raise ValueError("CC4_ROW_DIMENSION")
    return dict(PASS=True, day=day, file=record(cc4_path), semantic_sha=digest(cc4),
        prediction_index=cc4["prediction_index"], issue_seconds=issue, D0_seconds=midnight(day),
        future_Unknown_UIDs_present=False, retrospective_model_selection_contract_preserved=True)


def write_json(path, value, *, compressed=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n").encode("utf8")
    encoded = gzip.compress(raw, compresslevel=6, mtime=0) if compressed else raw
    with path.open("xb") as stream:
        stream.write(encoded)
    if compressed and gzip.decompress(encoded) != raw:
        raise ValueError("LOSSLESS_INITIAL_STATE_ROUNDTRIP")
    return dict(record(path), decoded_sha256=hashlib.sha256(raw).hexdigest(), decoded_bytes=len(raw))


def load_initial_state(receipt):
    path = checked(receipt)
    value = read(path)
    if digest({k: value[k] for k in value["initial_state_payload_keys"]}) != value["common_initial_state_sha"]:
        raise ValueError("D0_INITIAL_STATE_SEMANTIC_SHA_MISMATCH")
    if digest({k: v for k, v in value.items() if k != "freeze_sha"}) != value["freeze_sha"]:
        raise ValueError("D0_INITIAL_STATE_FREEZE_SHA_MISMATCH")
    return value
