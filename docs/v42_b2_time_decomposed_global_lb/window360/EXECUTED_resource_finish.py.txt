"""Read-only final process/source/resource and capped-call evidence audit."""
from pathlib import Path
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.time_decomposed_lb.resources import DOCS, digest, read, write, timestamp


def run():
    post = read(DOCS / "POST_RUN_RESOURCE_SOURCE_AUDIT.json")
    frozen = read(DOCS / "PROTECTED_BASELINE.json")
    ledger = read(DOCS / "NATIVE_LEDGER.json")
    calls = ledger["calls"]
    stages = []
    intervals = []
    for slot in (75, 82, 94):
        directory = DOCS / f"slot{slot:02d}"
        result = read(directory / "RESULT.json")
        trace = read(directory / "RESOURCE_TRACE.json")
        memory_trace = read(directory / "MEMORY_TRACE.json")
        admission = read(directory / "MEMORY_RESOURCE_ADMISSION.json")
        readback = read(directory / "NATIVE_READBACK.json")
        started = read(directory / "PILOT_STARTED.json")
        certificate = read(directory / "INDEPENDENT_CERTIFICATE.json")
        execution = read(directory / "EXECUTION_SOURCES.json")
        copies = []
        for name, expected in execution.items():
            path = directory / f"EXECUTED_{name}.txt"
            saved = digest(path)
            current = ROOT / "tools/time_decomposed_lb" / name
            copies.append(dict(name=name, expected_execution_sha256=expected, saved_copy_sha256=saved["sha256"],
                               exact_execution_copy=saved["sha256"] == expected,
                               current_source_sha256=digest(current)["sha256"],
                               current_source_matches_execution=digest(current)["sha256"] == expected))
        assert execution == started["execution_source_sha256"]
        samples = memory_trace["samples"]
        floors = all(sample["system"]["RAM_available"] >= 4*1024**3
                     and sample["system"]["Commit_available"] >= 6*1024**3 for sample in samples)
        stage_checks = dict(
            native_readback_PASS=readback["PASS"], fresh_post_build_source_resource_admission_PASS=admission["PASS"],
            exact_single_thread_30_second_parameter_contract=(result["Threads"] == 1 and result["TimeLimit"] == 30
                and started["parameters"]["Threads"] == 1 and started["parameters"]["TimeLimit"] == 30),
            consumed_one_Optimize_call=result["Native_optimize_calls"] == 1,
            no_observed_callback_resource_errors=not trace["stops"] and not trace["callback_errors"],
            no_memory_or_numeric_stop=not result["memory_stops"] and not result["numeric_errors"]
                and not result["resource_stops"] and result["optimize_error"] is None,
            actual_sampled_memory_floors_PASS=floors,
            execution_source_copy_hashes_exact=all(item["exact_execution_copy"] for item in copies),
            independent_Global_Solver_Bound_certificate_PASS=certificate["PASS"],
            no_Full96_MILP_campaign_B1_launch=result["full_MILP_calls"] == result["campaign_calls"] == result["B1_launches"] == 0,
            incumbent_not_FULL_UB_or_Actual_PASS=not result["incumbent_is_original_FULL_UB"] and not result["Actual_AC_PASS"],
        )
        stages.append(dict(slot=slot, PASS=all(stage_checks.values()), checks=stage_checks,
                           result=result, execution_source_copies=copies, independent_certificate=digest(directory / "INDEPENDENT_CERTIFICATE.json"),
                           evidence={name:digest(directory/name) for name in ("RESULT.json", "MEMORY_RESOURCE_ADMISSION.json", "NATIVE_READBACK.json", "MEMORY_TRACE.json", "RESOURCE_TRACE.json", "PILOT_STARTED.json", "EXECUTION_SOURCES.json")},
                           continuous_all_instants_no_conflict_certified=False,
                           note="Fresh admission and periodic structured callback observation passed. Periodic samples do not prove continuous absence of peers between samples; no peer is forcibly stopped by this study."))
        call = next(item for item in calls if item["slot"] == slot and item["kind"] == "SNAPSHOT")
        intervals.append(dict(slot=slot, start=call["time"], conservative_stop=call["time"]+result["optimize_wall_seconds"]))
    window = read(DOCS / "window_native0/WINDOW_NATIVE0_DESIGN.json")
    checks = dict(
        fresh_all_seven_local_remote_sources_and_current_B1_stopped_state_PASS=post["PASS"],
        exact_three_preregistered_sequential_snapshot_calls=len(calls) == 3 and [item["slot"] for item in calls] == [75, 82, 94]
            and all(item["kind"] == "SNAPSHOT" for item in calls),
        exact_90_second_snapshot_requested_budget=sum(item["TimeLimit"] for item in calls) == 90,
        no_overlapping_snapshot_optimize_intervals=all(left["conservative_stop"] < right["start"] for left,right in zip(intervals, intervals[1:])),
        all_stage_native_readback_source_copy_admission_and_resource_checks_PASS=all(stage["PASS"] for stage in stages),
        Window_not_executed_and_literal_binary_cap_failure_preserved=window["Window_Optimize_calls"] == 0
            and not window["Window_Native_authorized"] and window["physical_dimensions"]["binary"] == 16236
            and window["safety_gates"]["binary_cap"] is False,
        no_candidate_Bound_material_trigger=all(stage["result"]["ObjBound"] < 0.46498486997548166+0.001 for stage in stages),
        B1_user_stop_ledger_result_bytes_and_original_task_contracts_preserved=post["checks"]["protected_source_result_Native_ledger_bytes_unchanged"]
            and post["checks"]["all_prior_task_enabled_and_action_contracts_unchanged"],
    )
    result = dict(schema="V42_TIME_DECOMPOSITION_FINAL_RESOURCE_B1_SOURCE_AUDIT_V1", PASS=all(checks.values()),
                  checks=checks, **timestamp(), final_readonly_audit=digest(DOCS / "POST_RUN_RESOURCE_SOURCE_AUDIT.json"),
                  protected_baseline=digest(DOCS / "PROTECTED_BASELINE.json"), protected_file_count=len(frozen["protected_files"]),
                  protected_file_bytes=sum(item["bytes"] for item in frozen["protected_files"]),
                  protected_task_contract_count=len(frozen["scheduled_tasks"]), originals=post["originals"],
                  native_ledger=ledger, native_ledger_digest=digest(DOCS / "NATIVE_LEDGER.json"), stages=stages,
                  total_actual_Native_Runtime_seconds=sum(stage["result"]["Runtime"] for stage in stages),
                  total_optimize_wall_seconds=sum(stage["result"]["optimize_wall_seconds"] for stage in stages),
                  total_callback_seconds=sum(stage["result"]["callback_seconds"] for stage in stages),
                  peak_process_RSS_bytes=max(stage["result"]["peak_process_RSS_bytes"] for stage in stages),
                  peak_private_commit_bytes=max(stage["result"]["peak_private_commit_bytes"] for stage in stages),
                  minimum_system_RAM_available_bytes=min(stage["result"]["minimum_RAM_available"] for stage in stages),
                  minimum_system_commit_available_bytes=min(stage["result"]["minimum_commit_available"] for stage in stages),
                  maximum_Gurobi_MaxMemUsed_GB=max(stage["result"]["MaxMemUsed_GB"] for stage in stages),
                  B1_launches_by_this_study=0, B1_source_result_process_schedule_automation_mutations=0,
                  Full96_MILP_calls=0, official_campaign_calls=0, Window_Native_calls=0,
                  audits_Native_calls=0, audits_solver_imports=0,
                  runtime_comparison_limitation="Actual Solver Runtime, wall and callback cost are recorded separately. A smaller model or different elapsed Native time does not isolate a formulation-only speedup across differing solve tasks or monitoring overhead.")
    write(DOCS / "FINAL_RESOURCE_B1_AUDIT.json", result)
    print(json.dumps(dict(PASS=result["PASS"], checks=checks, Runtime=result["total_actual_Native_Runtime_seconds"],
                          wall=result["total_optimize_wall_seconds"], peak_RSS=result["peak_process_RSS_bytes"],
                          peak_Private=result["peak_private_commit_bytes"]), ensure_ascii=False))


if __name__ == "__main__":
    run()
