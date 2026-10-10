"""Saved source/log audit only; imports no science and runs no solver or ops."""
import csv
import hashlib
import io
import json
from collections import Counter
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path

DEST = Path(__file__).parent
CAMPAIGN = Path(r"D:\v42_may_restart_20261010_02")
SAVED = Path(r"D:\v42_first_sweep_fairness_actual_independent_audit_20261010_01")
ROOT35 = Path(r"D:\v42run35")
ROOT36 = Path(r"D:\v42run36")


def record(path, data=None):
    data = Path(path).read_bytes() if data is None else data
    return {"path": str(path), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_new(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(data)


def json_new(path, value):
    write_new(path, (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


copies = []


def saved_copy(path, relative, scope):
    data = Path(path).read_bytes()
    source = record(path, data)
    target = DEST / relative
    write_new(target, data)
    assert record(target)["sha256"] == source["sha256"]
    copies.append({"source": source, "copy": record(target), "scope": scope})
    return data


source_files = [
    "v42_may_campaign_native90/m_stage.py", "v42_m1_anytime/algorithms.py",
    "v42_m1_anytime/core.py", "v42_m1_hybrid/blocks.py", "v42_m1_hybrid/pricing.py",
    "v42_m1_hybrid/dw.py", "v42_m1_hybrid/bound.py", "v42_m1_hybrid/verify.py",
    "v42_m1_research/check_lb.py",
]
manifests = {35: read(CAMPAIGN / "B2_V35_ZERO_START_DEPLOYMENT_MANIFEST.json"),
             36: read(CAMPAIGN / "B2_V36_ZERO_START_DEPLOYMENT_MANIFEST.json")}
assert manifests[35]["builder_original_sources"] == manifests[36]["builder_original_sources"]
assert len(manifests[35]["builder_original_sources"]) == 1007
source_pairs = {}
for relative in source_files:
    pair = {}
    for version, root in [(35, ROOT35), (36, ROOT36)]:
        data = saved_copy(root / relative, f"source{version}/{relative}", "Original source text only; never imported or executed.")
        rec = record(root / relative, data)
        declared = manifests[version]["builder_original_sources"] | manifests[version]["execution_sources"]
        assert declared[relative] == rec["sha256"]
        pair[str(version)] = rec
    assert pair["35"]["sha256"] == pair["36"]["sha256"]
    source_pairs[relative] = pair
saved_copy(ROOT35 / "v42_autonomous_b2/worker.py", "source35/v42_autonomous_b2/worker.py", "Current lazy hook wiring; source text only.")
saved_copy(ROOT36 / "v42_autonomous_b2/rmp_presolve.py", "source36/v42_autonomous_b2/rmp_presolve.py", "Conditional computational Method0 policy and strict guards; source text only.")

days = {}
for suffix, attempt in [("01", "repair_b2_v35_01_s3"), ("02", "repair_b2_v35_01_s1"), ("03", "repair_b2_v35_01_s2")]:
    day = "2025-05-" + suffix
    base = CAMPAIGN / "dates/B2" / day / "attempts" / attempt
    output = base / "output"
    request = json.loads(saved_copy(base / "request.json", f"actual/{day}/request.json", "Existing sealed Source35 current-attempt request; no request or process actions."))
    assert request["implementation_SHA"] == manifests[35]["execution_SHA"]
    schedule = json.loads(saved_copy(output / "ADAPTIVE_SCHEDULER_AUDIT.json", f"actual/{day}/ADAPTIVE_SCHEDULER_AUDIT.json", "Timestamped saved adaptive trace; naturally evolving source not expected to stay unchanged."))
    frontier = json.loads(saved_copy(output / "frontier/CURRENT_CERTIFIED_STATE.json", f"actual/{day}/CURRENT_CERTIFIED_STATE.json", "Last saved certified event state; its own UTC is retained, not asserted current."))
    events_data = saved_copy(output / "frontier/FRONTIER_EVENTS.csv", f"actual/{day}/FRONTIER_EVENTS.csv", "Saved certified Frontier event log only; no replay/checker run.")
    events = list(csv.DictReader(io.StringIO(events_data.decode("utf-8-sig"))))
    native = json.loads(saved_copy(SAVED / f"B2_2025-05-{suffix}_CURRENT_NATIVE_RAW.json", f"actual/{day}/PRIOR_SAVED_NATIVE_PREFIX.json", "Already preserved read-only fairness audit Native prefix; historical UTC, not current Native Runtime."))
    lb_results = {}
    certificates = {}
    for round_name in ("004_L1_00", "007_L4_00"):
        for name in ("LB_RESULT.json", "INDEPENDENT_GLOBAL_LB_CERTIFICATE.json", "PRICING_RESULT.json", "INDEPENDENT_FULL_ORIGINAL_DUAL_EXACT.json"):
            data = saved_copy(output / round_name / name, f"actual/{day}/{round_name}/{name}", "Existing completed original pricing/certificate packet; no fresh mathematical replay.")
            if name == "LB_RESULT.json": lb_results[round_name] = json.loads(data)
            if name == "INDEPENDENT_GLOBAL_LB_CERTIFICATE.json": certificates[round_name] = json.loads(data)
    one, four = lb_results["004_L1_00"], lb_results["007_L4_00"]
    cert1, cert4 = certificates["004_L1_00"], certificates["007_L4_00"]
    assert one["adopted"] is True and one["certified_gain"] > 0
    assert four["adopted"] is False and four["certified_gain"] == 0
    assert Fraction(cert1["exact_Global_LB"]) == Fraction(cert4["exact_Global_LB"])
    assert one["full_dual_sha256"] == four["full_dual_sha256"]
    assert frontier["LB_certificate_sha256"] == one["certificate_sha256"]
    rmps = []
    for round_name in ("005_L2_00_MASTER", "006_L3_00_MASTER"):
        rmp = json.loads(saved_copy(output / round_name / "RMP_RESULT.json", f"actual/{day}/{round_name}/RMP_RESULT.json", "Completed original RMP call result; status11/Sol0 and missing Pi are diagnostic, not a global bound."))
        assert rmp["full_original_dual"] is None and rmp["dual_status"] == "NO_FINITE_PI_FOLLOWUP_PRICING_NOT_RUN"
        n = rmp["native"]
        assert n["Native_status"] == 11 and n["Native_SolCount"] == 0
        rmps.append({"round": round_name, "dual_status": rmp["dual_status"],
                     "Native_status": n["Native_status"], "Native_SolCount": n["Native_SolCount"],
                     "Native_Runtime": n["Native_Runtime"], "effective_TimeLimit": n["effective_TimeLimit"]})
    counts = Counter(row["method"] for row in schedule["history"])
    assert counts["L1"] == counts["L2"] == counts["L3"] == counts["L4"] == 1
    assert all(row["method"].startswith("U") for row in schedule["choices"][8:])
    lb_rows = [{k: row.get(k) for k in ("method", "certified_gain", "status", "candidate_LB", "adopted", "wall_seconds")} for row in schedule["history"] if row["method"].startswith("L")]
    assert all(row["status"] == "NOT_RUN_NO_FINITE_RMP_PI" for row in lb_rows if row["method"] in ("L2", "L3"))
    days[day] = {
        "attempt_id": attempt, "request_source_SHA": request["implementation_SHA"], "case_sha": schedule["case_sha"],
        "scheduler_choices_snapshot_count": len(schedule["choices"]), "scheduler_completed_history_count": len(schedule["history"]),
        "history_method_counts": dict(counts), "post_pilot_choices_are_UB_only": True,
        "last_saved_scheduler_choice": schedule["choices"][-1], "LB_history": lb_rows,
        "RMPs": rmps, "first_L1_exact_LB": cert1["exact_Global_LB"], "first_L1_float_LB": one["certified_LB"],
        "L4_exact_LB_equal_L1": True, "L4_full_original_dual_SHA_equal_L1": one["full_dual_sha256"],
        "L4_adopted": False, "L4_gain": 0,
        "saved_frontier_state_UTC": frontier["UTC"], "saved_frontier_state_LB_certificate_SHA": frontier["LB_certificate_sha256"],
        "saved_certified_LB_event_count": sum(row.get("event") == "LB_CERTIFIED_IMPROVEMENT" for row in events),
        "historical_native_prefix_UTC": native["UTC"], "historical_measured_Native_Runtime": native["measured_Native_Runtime"],
        "historical_call_counts_by_track": dict(Counter(c["track"] for c in native["calls"])),
        "original_remaining_scheduler_L2_selections_max": 1, "original_remaining_scheduler_L3_selections_max": 1,
        "remaining_L2_L3_selection_is_not_guaranteed": True,
    }

references = {
    "original_pilot_gain_score_and_selection_caps": {"path": "v42_m1_anytime/core.py", "lines": [174, 193]},
    "noPi_current_track_only_continue_and_success_path": {"path": "v42_may_campaign_native90/m_stage.py", "lines": [215, 270]},
    "finitePi_mapping_noNativeObjectiveAuthority": {"path": "v42_m1_hybrid/dw.py", "lines": [84, 118]},
    "original_price_checker_adoption_integerClosure_limits": {"path": "v42_m1_anytime/algorithms.py", "lines": [150, 213]},
    "original_price_exactsum_nonunit_fullchecker_gate": {"path": "v42_m1_hybrid/pricing.py", "lines": [345, 371]},
    "strict_frontier_certificate_case_SHA_exactvalue_bracket": {"path": "v42_m1_anytime/core.py", "lines": [135, 149]},
    "same_lazy_original_worker_hooks": {"path": "v42_autonomous_b2/worker.py", "version": 35, "lines": [163, 201]},
    "conditional_Source36_currentStart_method": {"path": "v42_autonomous_b2/rmp_presolve.py", "version": 36, "lines": [203, 224]},
}
for relative, pair in source_pairs.items():
    assert record(ROOT35 / relative) == pair["35"] and record(ROOT36 / relative) == pair["36"]

json_new(DEST / "SOURCE35_BOUND_SCHEDULE_READONLY_EVIDENCE.json", {
    "schema": "V42_SOURCE35_BOUND_SCHEDULE_SOURCE_AND_SAVED_ARTIFACT_READONLY_EVIDENCE_V1",
    "PASS": True, "PASS_scope": "source-byte and saved-log consistency only; no scientific replay or final PASS qualification",
    "UTC": datetime.now(timezone.utc).isoformat(), "Source35_execution_SHA": manifests[35]["execution_SHA"],
    "Source36_execution_SHA": manifests[36]["execution_SHA"], "original1007_manifest_maps_identical": True,
    "nine_original_flow_source_pairs_SHA_identical35_36": source_pairs, "source_pairs_unchanged_start_end": True,
    "source_references": references, "actual_saved_days": days,
    "observed_RMP_timeLimit_does_not_abort_overall_original_adaptive_loop": True,
    "actual35_noPi_skips_only_current_L2_L3_price_call": True,
    "Source36_usable_Pi_or_certified_improvement_or_performance_observed_by_this_audit": False,
    "Source36_only_changes_computational_choice_original_followup_flow_retained": True,
    "uncertainties": ["Pi availability and quality under Source36 conditionalMethod0 remain unobserved by this audit.",
                      "Finite Pi, including an empty exact dual, is only a computational price input, not a GlobalLB or closure proof.",
                      "Each L2/L3 has at most one further selection after its first pilot; gain/cost ranking, UB diversification and remaining Native reserve govern whether it occurs.",
                      "No iterative LB continuation beyond original per-track counts or new fullLP continuation is implied.",
                      "Snapshots have their own UTC and completed-prefix scope; healthy writers may continue after capture."],
    "Native_optimize_calls": 0, "real_Native_model_constructions": 0,
    "science_modules_imported_or_original_functions_executed": False,
    "new_probe_replay_test_repair_or_scientific_code_changes": 0,
    "queue_lease_process_production_runtime_Git_actions": 0,
    "final_Global_Gap_FULL_Actual_Fresh_PASS_claimed": False,
})
json_new(DEST / "PROVENANCE_SHA_INDEX.json", {"schema": "V42_SOURCE35_BOUND_SCHEDULE_SAVED_COPIES_V1", "copies": copies})

rows = "\n".join(f"| {day} | {v['first_L1_float_LB']:.12f} | {v['scheduler_choices_snapshot_count']} | {v['history_method_counts'].get('L1',0)}/{v['history_method_counts'].get('L2',0)}/{v['history_method_counts'].get('L3',0)}/{v['history_method_counts'].get('L4',0)} | {v['RMPs'][0]['Native_Runtime']:.3f}/{v['RMPs'][1]['Native_Runtime']:.3f} |" for day, v in days.items())
report = """# Source35 양수 LB 이후 스케줄의 읽기 전용 근거

세 날짜에서 RMP 시간 제한은 전체 알고리즘을 중단하지 않았다. L2·L3의 실제 결과는 status11/Sol0와 `NO_FINITE_PI_FOLLOWUP_PRICING_NOT_RUN`이며, 원본 호출자는 그 선택에 gain0 기록을 추가한 뒤 `continue`한다. 이후 L4 가격·검증과 UB 작업이 실제로 진행됐다. 이 보고서는 원본 소스와 이미 기록된 호출·선택·인증 파일만 읽고 복사했다. 새로운 solver, 모델, checker replay, 테스트, 프로세스 조회나 운영 변경을 하지 않았다.

| 날짜 | 첫 L1 인증 LB | 저장 선택 수 | 완료 L1/L2/L3/L4 수 | L2/L3 실제 Native 초 |
|---|---:|---:|---|---|
""" + rows + """

각 날짜 L4는 L1과 **동일한 exact rational LB 및 full-original-dual SHA**를 만들었고 adoptedfalse/gain0이었다. 저장 Frontier의 LB 인증 SHA는 첫 L1이며, 해당 이벤트 CSV에는 양수 LB 개선 이벤트가 하나뿐이다. L4의 MILP 가격 결과도 원본 algorithms171–187에서 exact integer closure를 NOT_PROVEN으로 기록한다. Native OPTIMAL/ObjBound를 새 LB로 승격하지 않는다. 이는 저장 파일의 비교이며 독립 수학 checker를 새로 실행한 결과가 아니다.

원본 `core.py174–193`의 처음8선택은 U1/U2/U3/U4/L1/L2/L3/L4이다. 이후 점수는 각 track 최근3개 인증 gain 합/실제 wall 비용이다. **line184는 L1·L4를 완료 history count<1, L2·L3를 count<2일 때만 eligible로 둔다.** 따라서 첫 L1의 양수 점수가 남아 있어도 재선택할 수 없다. 실제 L2·L3 gain0은 eligible 점수0이다. 다른 eligible 양수 점수가 없으면185–187은 최소 사용 UB만 선택하고,188–190의 주기적 다양화도 UB만 고른다. 실제 세 trace의 pilot 이후 선택은 전부 UB이다. RMP 실패에 따른 전체 abort나 인증값 상실이 아니라, 이 원본 count 제한과 gain/비용 선택이 계속된 결과다.

Source35와36의 관련 원본9파일 SHA 및 원본1007 manifest map은 같다. Source36 `rmp_presolve.py203–224`는 complete same-current P/D와 original/Native-scaled rows/bounds가 literal1e-9 이내일 때 기존 단일30초 RMP 경계의 computationalMethod0만 선택한다. Original budget admission1, cold/ineligible/nonfeasible1, total5400, precision/physics/domain와 후속 코드는 유지된다. RMP는 **feedback_master 호출당 한30초**이지 attempt당 한 호출이 아니다. 실제35는 L2에 Pi가 없어 L3가 다시 RMP를 호출했다.

향후36에서 finite Pi가 나오면 `dw.py99–113`이 row transport 후 원본 부호를 처리하고 정확 dual/convexity packet을 만든다. OPTIMAL이나 SolCount가 이 분기의 조건은 아니며, None만 건너뛰고 {}도 입력으로 진행한다. `m_stage247–251`은 L2에는 RMP dual, L3에는 retained certified dual과의1/8·1/4·1/2 혼합을 기존 가격 호출에 보낸다. `algorithms156–170`의 원본 four45초 unit LP 가격 → selected exact unit dual → independent full signed checker → producer/fullsum 일치 → Frontier strict case/SHA/exact value/bracket 검증이 그대로 필요하다. 실제 강한 인증 개선이 채택됐을 때만 retained authoritative dual이 바뀐다. L2의 추가 missing-column 검증도 RMP objective를 GlobalLB로 만들지 않는다.

L2·L3 첫 pilot 이후 각 track에는 원본상 **최대 한 번의 추가 선택**만 남는다. 양수 certified gain/cost 점수가 생겨야 일반 순위에서 경쟁할 수 있고, UB 다양화·Native reserve(일반LB600/L4 1000)·전체Gap/예산 종료 조건도 적용된다. Pi만 나왔다고 개선이나 추가 선택을 보장하지 않는다. 오류266–270은 전체 루프를 종료할 수 있지만, 이번 관측의 missingPi는245–246의 current-track continue였다. 새로운 무한 LB 반복이나 후속 fullLP continuation은 없다.

파일별 원본 경로·SHA·크기와 소스 line 범위는 JSON과 provenance index에 있다. Native prefix는 이전 fairness audit의 자체 UTC를 보존했으며 현재 Runtime0/최종 Runtime으로 주장하지 않는다. Source36의 실제 usable Pi, 인증 LB 개선, 속도와 finalGlobalGap<=.03/FULL/Actual/Fresh PASS는 본 점검에서 미관측이다.
"""
write_new(DEST / "REPORT.md", report.encode("utf-8"))
files = {p.relative_to(DEST).as_posix(): record(p) for p in sorted(DEST.rglob("*")) if p.is_file()}
json_new(DEST / "SHA_INVENTORY.json", {"schema": "V42_SOURCE35_BOUND_SCHEDULE_READONLY_DOC_INVENTORY_V1", "PASS": True, "files": files})
print(json.dumps({"PASS": True, "evidence": record(DEST / "SOURCE35_BOUND_SCHEDULE_READONLY_EVIDENCE.json"),
                  "report": record(DEST / "REPORT.md"), "inventory": record(DEST / "SHA_INVENTORY.json"),
                  "snapshot_counts": {d: v["scheduler_choices_snapshot_count"] for d, v in days.items()}}, ensure_ascii=False))
