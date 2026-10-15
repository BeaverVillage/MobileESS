"""Native-0 source-event reconstruction for 31 independent May midnights."""
import argparse
from copy import deepcopy
from datetime import date, timedelta
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from v42_integration import release_initial_states as api
from v42_integration.dday_boundary import build_boundary_candidate


def inputs(folder):
    return {key: api.read(folder / name) for key, name in (
        ("plan", "PLANNING_INPUT_BUNDLE.json"), ("native", "NATIVE_INPUT_TEMPLATE_B1.json"),
        ("actual", "ACTUAL_INPUT_BUNDLE.json"), ("provenance", "SOURCE_PROVENANCE.json"))}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(ROOT / "docs/v42_unified_aidc_mess_research_20261014/RELEASE_RECOVERY_20261015/RC02/INITIAL_STATES"))
    args = parser.parse_args()
    output = Path(args.output)
    if output.exists():
        raise FileExistsError("INITIAL_STATE_PREPARATION_OUTPUT_ALREADY_EXISTS:" + str(output))
    output.mkdir(parents=True)
    started = time.perf_counter()
    raw_root = Path("D:/v42_may_joint_repair_campaign_20261013/raw")
    old_docs = Path("D:/v42_common_am_qos_integration_20261013/docs/v42_common_am_qos_integration")
    old_root = Path("D:/MobileESS_V42/docs/v42_may_b0_zero_margin_holdout")
    initial_path = old_docs / "V42_MAY01_DDAY_INITIAL_STATE_FREEZE.json"
    source_records = [api.record(ROOT / path) for path in (
        "v42_integration/release_initial_states.py", "tools/prepare_v42_release_initial_states.py",
        "v42_integration/dday_initialization.py", "v42_integration/dday_boundary.py",
        "v42_integration/pr129_recovery.py", "v42_capacity/reference.py", "v42_capacity/actual.py")]
    api.write_json(output / "EXECUTED_SOURCE.json", dict(files=source_records, Native_Optimize_calls=0))
    reproduction = api.reproduce_may01(initial_path, raw_root, old_docs)
    api.write_json(output / "MAY01_EXACT_INITIALIZER_REPRODUCTION.json", reproduction)
    print("May01 original initializer exact object and semantic SHA reproduced", flush=True)
    days = [(date(2025, 5, 1) + timedelta(days=i)).isoformat() for i in range(31)]
    small_inputs, unavailable = {}, {}
    archive = None
    for day in days:
        try:
            folder = raw_root / day
            plan, actual, prov = [api.read(folder / n) for n in (
                "PLANNING_INPUT_BUNDLE.json", "ACTUAL_INPUT_BUNDLE.json", "SOURCE_PROVENANCE.json")]
            if plan["day"] != day or actual["day"] != day or prov["day"] != day or plan["capacities"] != actual["capacities"]:
                raise ValueError("SOURCE_BUNDLE_DAY_OR_CAPACITY_MISMATCH")
            if archive is None:
                archive = prov["archive"]
            if any(prov["archive"][k] != archive[k] for k in ("sha256", "bytes")):
                raise ValueError("KESTREL_ARCHIVE_IDENTITY_DRIFT")
            begin = api.midnight(day)
            rows = api.public_population(plan, actual, begin)
            minimal = [{k: row[k] for k in ("job_uid", "submit_time", "GPU_gang", "source_member", "source_row")} for row in rows]
            small_inputs[day] = dict(plan=dict(known_population=minimal), actual=dict(post_issue_arrivals=[]))
        except (OSError, ValueError, KeyError) as error:
            unavailable[day] = str(error)
    # No private truth cache is created; event projection drops future times
    # inside each selected raw row before it can enter a Planning argument.
    events, requests, archive_record = api.project_archive(archive, small_inputs)
    del small_inputs
    print("Kestrel archive source-prefix extraction finished; compiling independent dates", flush=True)
    table = []
    for day in days:
        row = dict(day=day, status="INPUT_UNAVAILABLE", Native_Optimize_calls=0,
            independent_date=True, previous_day_Actual_carry_used=False, future_Unknown_UIDs_in_Planning=0,
            future_completion_values_in_Planning=0, source_state_is_modeled_not_observed_12AIDC_placement=True)
        folder, dest = raw_root / day, output / day
        try:
            if day in unavailable:
                raise ValueError(unavailable[day])
            data = inputs(folder)
            receipts = [api.record(folder / n) for n in (
                "PLANNING_INPUT_BUNDLE.json", "NATIVE_INPUT_TEMPLATE_B1.json", "ACTUAL_INPUT_BUNDLE.json", "SOURCE_PROVENANCE.json")]
            receipts.append(archive_record)
            cc4 = api.verify_cc4(day, data["plan"], old_root / "CC4" / ("DAY_" + day.replace("-", "") + ".json"))
            row["CC4"] = cc4
            row["source_sha"] = api.digest(receipts)
            begin = api.midnight(day)
            public_actual = dict(post_issue_arrivals=[r for r in data["actual"]["post_issue_arrivals"]
                if api.seconds(r["submit_time"]) <= begin])
            excluded = {r["job_uid"] for r in data["native"]["known_population"] if r["state"] == "RUNNING"
                and r.get("current_site_if_running") is None
                and events[day][r["job_uid"]]["observed_completion_seconds"] is not None}
            candidate, boundary_audit, _ = build_boundary_candidate(data["plan"], data["native"], public_actual,
                events[day], excluded, source_receipts=receipts)
            running = [r for r in candidate["initial_source_roster"] if r["boundary_source_state"] == "RUNNING"]
            pending = [r for r in candidate["initial_source_roster"] if r["boundary_source_state"] == "PENDING"]
            row.update(running=len(running), running_GPU=sum(r["GPU_gang"] for r in running), pending=len(pending),
                completed_before_D0=sum(r["boundary_source_state"] == "COMPLETED" for r in candidate["initial_source_roster"]),
                D1_unknown_reclassified_public_at_D0=sum(r["origin_unknown"] for r in running + pending))
            old_day = old_root / "BUNDLE" / ("DAY_" + day.replace("-", ""))
            old_input = old_root / "INPUT/BUNDLE" / ("DAY_" + day.replace("-", ""))
            prior_path = old_day / "REFERENCE.json"
            prior_freeze_path = old_day / "PLANNING_FREEZE.json"
            old_plan_path = old_input / "PLANNING_INPUT_BUNDLE.json"
            if api.record(old_plan_path)["sha256"] != receipts[0]["sha256"]:
                raise ValueError("PRIOR_REFERENCE_CURRENT_REQUEST_INPUT_SHA_MISMATCH")
            prior_prov_path = old_input / "SOURCE_PROVENANCE.json"
            old_prov = api.read(prior_prov_path)
            if old_prov["archive"]["sha256"] != archive_record["sha256"]:
                raise ValueError("PRIOR_REFERENCE_RAW_REQUEST_ARCHIVE_MISMATCH")
            recovery = api.prior_reference_pins(candidate, data["plan"], data["native"], api.read(prior_path),
                api.read(prior_freeze_path), reference_record=api.record(prior_path),
                receipts=[api.record(p) for p in (prior_path, prior_freeze_path, old_plan_path, prior_prov_path)])
            if day == "2025-05-01":
                approved = api.read(initial_path)
                old_candidate = api.read(old_docs / "DDAY_INITIAL_STATE_CANDIDATE.json")
                if candidate["initial_source_roster"] != old_candidate["initial_source_roster"]:
                    raise ValueError("MAY01_NEW_RAW_PREFIX_NOT_EQUAL_ORIGINAL_ROSTER")
                old_pins = api.read(old_docs / "PR129_REFERENCE_SITE_RECOVERY.json")["validated_pins"]
                if {u: p["site"] for u, p in recovery["validated_pins"].items()} != {u: p["site"] for u, p in old_pins.items()}:
                    raise ValueError("MAY01_PRIOR_REFERENCE_REUSE_RULE_DRIFT")
                state = approved
                initial_record = api.record(initial_path)
                row["preserved_original_May01_bytes"] = True
            else:
                state, _, _ = api.compile_state(day, data, events[day], recovery, receipts)
                initial_record = api.write_json(dest / "INITIAL_STATE.json.gz", state, compressed=True)
                if api.load_initial_state(initial_record) != state:
                    raise ValueError("COMPILED_INITIAL_STATE_LOAD_ROUNDTRIP")
            api.write_json(dest / "PUBLIC_EVENT_PREFIX.json.gz", events[day], compressed=True)
            api.write_json(dest / "PUBLIC_REQUEST_SOURCE.json.gz", sorted(requests[day], key=lambda r: r["uid"]), compressed=True)
            api.write_json(dest / "PRIOR_REFERENCE_REUSE_AUDIT.json", recovery)
            active = state["running"] + state["pending"]
            row.update(status="INPUT_READY", initial_state=initial_record,
                initial_semantic_sha=state["common_initial_state_sha"], initial_freeze_sha=state["freeze_sha"],
                prior_model_site_reused=len(recovery["validated_pins"]),
                PR125_fallback_jobs=state["PR125_fallback_jobs"], site_GPU_use=state["site_GPU_use"],
                QoS_UNCONFIRMED=sum(r["metadata"].get("qos") == "UNCONFIRMED" for r in active),
                raw_request_version_history="UNVERIFIED_SOURCE_PROXY", Running_migration_authorized=False,
                window_contract="SOURCE_FIELDS_ONLY; absent hard windows are not invented",
                no_future_UID_or_completion_proof=dict(max_submit_seconds=max(r["submit_seconds"] for r in active),
                    D0_seconds=begin, all_observed_start_seconds_at_or_before_D0=all(
                        r["observed_start_seconds"] is None or r["observed_start_seconds"] <= begin for r in active),
                    active_rows_contain_no_observed_completion_fields=all("observed_completion_seconds" not in r for r in active),
                    historical_completion_only_before_D0=all(r["observed_completion_seconds"] <= begin for r in state["historical_completed"]),
                    future_Unknown_descriptors_filtered_before_source_extraction=True))
            api.write_json(dest / "INITIAL_STATE_RECEIPT.json", row)
            print(day, row["status"], row["running"], row["running_GPU"], row["pending"], flush=True)
        except (OSError, ValueError, KeyError) as error:
            row["missing_or_invalid_input_reasons"] = [str(error)]
            if "candidate" in locals() and candidate.get("day") == day:
                api.write_json(dest / "UNAVAILABLE_BOUNDARY_CANDIDATE.json.gz", candidate, compressed=True)
            api.write_json(dest / "INPUT_UNAVAILABLE.json", row)
            print(day, row["status"], str(error), flush=True)
        table.append(row)
    for expected in source_records:
        if api.record(expected["path"]) != expected:
            raise ValueError("INITIAL_COMPILER_SOURCE_CHANGED_DURING_EXECUTION")
    if api.record(initial_path)["sha256"] != api.INITIAL_SHA:
        raise ValueError("ORIGINAL_INITIAL_BYTES_CHANGED")
    summary = dict(schema=api.POLICY, days=table, dates=len(table),
        ready=sum(r["status"] == "INPUT_READY" for r in table),
        unavailable=sum(r["status"] == "INPUT_UNAVAILABLE" for r in table),
        Native_Optimize_calls=0, P2_calls=0, source_archive=archive_record,
        May01_exact_reproduction=reproduction, wall_seconds=time.perf_counter() - started,
        source_files_unchanged_after=True, old_Raw_or_Actual_result_modified=False,
        previous_day_Actual_carry_used=False, models_and_12AIDC_sites_are_approved_research_assumptions=True,
        Kestrel_observed_12AIDC_sites=False, historical_ingestion_time_certified=False,
        Science_policy_changed=False, downstream_date_specific_D0_case_compiler_certified=False,
        production_case_compiler_scope="INITIAL_STATE_AND_SOURCE_READY_ONLY; original D0 planning adapter remains May01-specific")
    api.write_json(output / "MAY31_INITIAL_STATE_PREPARATION.json", summary)
    lines = ["# 2025년 5월 독립 D0 초기 상태 재구성", "",
        "원본 May01 initializer 전체 객체·semantic SHA 재현을 먼저 통과했다. 이후 날짜는 해당 날짜 원본 이벤트의 00:00 UTC+10 이하 Prefix와 같은 PR125/PR129/FCFS 규칙으로 각각 생성했다. 전날 Actual Carry와 미래 Completion·Unknown UID는 사용하지 않았다.", "",
        "| 날짜 | 상태 | Running UID | Running GPU | Pending UID | 이전 완료 UID | 정확한 누락 사유 |", "|---|---|---:|---:|---:|---:|---|"]
    for row in table:
        lines.append("| " + " | ".join(str(row.get(k, "")) for k in ("day", "status", "running", "running_GPU", "pending", "completed_before_D0"))
            + " | " + "; ".join(row.get("missing_or_invalid_input_reasons", [])) + " |")
    lines += ["", "Source SHA, 초기 상태 byte/semantic SHA, CC4 Forecast SHA·예측 행·issue time은 날짜별 INITIAL_STATE_RECEIPT.json과 통합 JSON에 저장했다. 새 초기 상태는 lossless gzip이며 어댑터 load_initial_state로 검증 후 읽는다. May01 공인 파일은 그대로 참조한다.", "",
        "12 AIDC Site는 관측된 Kestrel 위치가 아니라 기존 승인된 연구 배치 모델이다. Request version history와 historical ingestion 시각은 원래 계약대로 미확인이다. 원본의 UNCONFIRMED QoS·누락 hard window를 새 SLA로 채우지 않았다. Raw QoS/partition/requested walltime은 별도 공개 Request ledger에 보존하고 정책 권한으로 승격하지 않았다.", "",
        "이 결과는 Initial State/CC4/Raw 준비 증거다. 날짜별 D0 Planning Case Compiler, P1-only 전체 단계, Actual96/Fresh AC, 추가 Native 예산 및 Campaign Gate 통과를 대신하지 않는다. Native Optimize와 P2 호출은 모두 0회다."]
    with (output / "MAY31_INPUT_READINESS_KO.md").open("x", encoding="utf8", newline="\n") as stream:
        stream.write("\n".join(lines) + "\n")
    print("SUMMARY", summary["ready"], summary["unavailable"], summary["wall_seconds"], flush=True)


if __name__ == "__main__":
    main()
