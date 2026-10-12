"""Final read-only audit after the sole authorized compact Window execution.

The earlier three-Snapshot resource audit and ledger copies are never written.
This tool imports no solver and is run only after the root confirms completion.
"""
from __future__ import annotations
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.time_decomposed_lb.resources import DOCS, digest, read, write, timestamp


def run():
    directory = DOCS / "window360"
    result = read(directory / "RESULT.json")
    post_path = DOCS / "WINDOW_POST_RUN_RESOURCE_SOURCE_AUDIT.json"
    post = read(post_path)
    snapshot = read(DOCS / "SNAPSHOT_FINAL_RESOURCE_B1_AUDIT.json")
    snapshot_ledger = read(DOCS / "SNAPSHOT_NATIVE_LEDGER.json")
    snapshot_preservation = read(DOCS / "SNAPSHOT_LEDGER_PRESERVATION_BEFORE_WINDOW.json")
    override = read(DOCS / "USER_WINDOW_360_OVERRIDE.json")
    ledger = read(DOCS / "NATIVE_LEDGER.json")
    readback = read(directory / "NATIVE_READBACK.json")
    native0 = read(directory / "NATIVE0.json")
    admission = read(directory / "MEMORY_RESOURCE_ADMISSION.json")
    trace = read(directory / "RESOURCE_TRACE.json")
    memory_trace = read(directory / "MEMORY_TRACE.json")
    started = read(directory / "PILOT_STARTED.json")
    execution = read(directory / "EXECUTION_SOURCES.json")
    certificate = read(directory / "INDEPENDENT_CERTIFICATE.json")
    compact = read(DOCS / "window_compact_native0/COMPACT_WINDOW_NATIVE0.json")
    originals = []
    # Compare every snapshot result, readback, admission and source-copy receipt
    # to its frozen pre-Window audit. This cannot silently rewrite history.
    snapshot_preserved = []
    for stage in snapshot["stages"]:
        slot = stage["slot"]
        checks = []
        for name, item in stage["evidence"].items():
            path = DOCS / f"slot{slot:02d}" / name
            checks.append(dict(name=name, expected_sha256=item["sha256"], current_sha256=digest(path)["sha256"],
                               unchanged=digest(path)["sha256"] == item["sha256"]))
        cert = stage["independent_certificate"]
        cert_path = DOCS / f"slot{slot:02d}" / "INDEPENDENT_CERTIFICATE.json"
        checks.append(dict(name="INDEPENDENT_CERTIFICATE.json", expected_sha256=cert["sha256"],
                           current_sha256=digest(cert_path)["sha256"], unchanged=digest(cert_path)["sha256"] == cert["sha256"]))
        snapshot_preserved.append(dict(slot=slot, PASS=all(item["unchanged"] for item in checks), files=checks))
    copies = []
    for name, expected in execution.items():
        copied = directory / f"EXECUTED_{name}.txt"
        current = ROOT / "tools/time_decomposed_lb" / name
        copies.append(dict(name=name, expected_execution_sha256=expected,
                           saved_copy_sha256=digest(copied)["sha256"], exact_execution_copy=digest(copied)["sha256"] == expected,
                           current_source_sha256=digest(current)["sha256"],
                           current_source_matches_execution=digest(current)["sha256"] == expected))
    original_native_files = []
    for name, expected in started["files"].items():
        original_native_files.append(dict(path=str(directory/name), expected_sha256=expected,
            observed_sha256=digest(directory/name)["sha256"], unchanged=digest(directory/name)["sha256"] == expected))
    for name, expected in started["source_records"].items():
        path = Path(name)
        original_native_files.append(dict(path=str(path), expected_sha256=expected,
            observed_sha256=digest(path)["sha256"], unchanged=digest(path)["sha256"] == expected))
    samples = memory_trace["samples"]
    floors = all(sample["system"]["RAM_available"] >= 4*1024**3
                 and sample["system"]["Commit_available"] >= 6*1024**3 for sample in samples)
    stage_rows = [stage["result"] for stage in snapshot["stages"]] + [result]
    fourth = ledger["calls"][3] if len(ledger["calls"]) == 4 else {}
    scientific_source_names = ("resources.py", "window_pilot.py", "pilot.py", "grid.py", "window_grid.py", "compact_window.py", "window_audit.py")
    scientific_copies = [item for item in copies if item["name"] in scientific_source_names]
    checks = dict(
        final_all_seven_local_remote_sources_B1_stopped_tasks_automations_PASS=post["PASS"],
        immutable_Snapshot_post_audit_and_ledger_bytes_preserved=(digest(DOCS/"SNAPSHOT_NATIVE_LEDGER.json")["sha256"]
            == snapshot_preservation["immutable_copy"]["sha256"] and all(item["PASS"] for item in snapshot_preserved)),
        exact_original_three_snapshot_ledger_prefix=ledger["calls"][:3] == snapshot_ledger["calls"],
        exact_four_calls_one_Window_total450_requested_seconds=(len(ledger["calls"]) == 4
            and fourth.get("kind") == "WINDOW" and fourth.get("window") == [88,96]
            and fourth.get("TimeLimit") == 360 and sum(item["TimeLimit"] for item in ledger["calls"]) == 450),
        explicit_360_second_single_Window_user_authority=(override["Window_TimeLimit_seconds"] == 360
            and override["Window_Optimize_maximum_calls"] == 1 and override["total_maximum_calls"] == 4
            and override["total_maximum_requested_seconds"] == 450
            and started["user_override_sha256"] == digest(DOCS/"USER_WINDOW_360_OVERRIDE.json")["sha256"]),
        Source18r_compact_Node_Mode_896_binary_original1500_cap_PASS=(native0["physical_representation"] == "compact_node_activity"
            and result["Binary"] == compact["physical_dimensions"]["binary"] == 896 and result["Binary"] <= 1500),
        complete_Window_size_Rows_NNZ_caps_PASS=(result["Rows"] == 95472 and result["Columns"] == 28561
            and result["NNZ"] == 1382625 and result["Rows"] <= 100000 and result["NNZ"] <= 1500000),
        Window_actual_native_readback_PASS=readback["PASS"],
        Window_fresh_post_build_memory_source_resource_admission_PASS=admission["PASS"],
        Window_singlethread_actual_TimeLimit360_contract=(result["Threads"] == 1 and result["TimeLimit"] == 360
            and result["Native_optimize_calls"] == 1 and started["parameters"]["Threads"] == 1
            and started["parameters"]["TimeLimit"] == 360),
        all_recorded_Window_RAM_Commit_floors_PASS=floors,
        no_observed_Window_callback_Heavy_memory_or_numeric_stops=(not trace["stops"] and not trace["callback_errors"]
            and not result["memory_stops"] and not result["numeric_errors"] and not result["resource_stops"]
            and result["optimize_error"] is None),
        exact_archived_execution_source_copies=execution == started["execution_source_sha256"]
            and all(item["exact_execution_copy"] for item in copies),
        scientific_Native_sources_still_match_execution=bool(scientific_copies)
            and all(item["current_source_matches_execution"] for item in scientific_copies),
        all_sealed_executed_Native_matrices_physical_and_grid_packets_preserved=all(item["unchanged"] for item in original_native_files),
        independent_Window_Global_Solver_Bound_certificate_PASS=certificate["PASS"],
        no_B1_Full96_MILP_campaign_or_incumbent_UB_Pass_promotion=(result["B1_launches"] == result["full_MILP_calls"]
            == result["campaign_calls"] == 0 and not result["incumbent_is_original_FULL_UB"] and not result["Actual_AC_PASS"]),
    )
    receipt = dict(schema="V42_TIME_DECOMPOSITION_FINAL_WINDOW_RESOURCE_B1_AUDIT_V1", PASS=all(checks.values()),
        checks=checks, **timestamp(), fresh_final_source_audit=digest(post_path),
        Snapshot_pre_Window_audit=digest(DOCS/"SNAPSHOT_FINAL_RESOURCE_B1_AUDIT.json"),
        preserved_Snapshot_stage_files=snapshot_preserved, preserved_Snapshot_ledger=digest(DOCS/"SNAPSHOT_NATIVE_LEDGER.json"),
        native_ledger=ledger, native_ledger_digest=digest(DOCS/"NATIVE_LEDGER.json"),
        user_override=digest(DOCS/"USER_WINDOW_360_OVERRIDE.json"), compact_Window=digest(DOCS/"window_compact_native0/COMPACT_WINDOW_NATIVE0.json"),
        Window_result=result, Window_execution_sources=copies, sealed_executed_packets=original_native_files,
        Window_independent_certificate=digest(directory/"INDEPENDENT_CERTIFICATE.json"),
        Window_evidence={name:digest(directory/name) for name in ("RESULT.json", "MEMORY_RESOURCE_ADMISSION.json", "NATIVE_READBACK.json", "MEMORY_TRACE.json", "RESOURCE_TRACE.json", "PILOT_STARTED.json", "EXECUTION_SOURCES.json")},
        original_sources=post["originals"],
        total_actual_Native_Runtime_seconds=sum(item["Runtime"] for item in stage_rows),
        total_optimize_wall_seconds=sum(item["optimize_wall_seconds"] for item in stage_rows),
        total_callback_seconds=sum(item["callback_seconds"] for item in stage_rows),
        peak_process_RSS_bytes=max(item["peak_process_RSS_bytes"] for item in stage_rows),
        peak_private_commit_bytes=max(item["peak_private_commit_bytes"] for item in stage_rows),
        minimum_system_RAM_available_bytes=min(item["minimum_RAM_available"] for item in stage_rows),
        minimum_system_commit_available_bytes=min(item["minimum_commit_available"] for item in stage_rows),
        maximum_Gurobi_MaxMemUsed_GB=max(item["MaxMemUsed_GB"] for item in stage_rows),
        B1_launches_by_this_study=0, source_result_process_schedule_automation_mutations=0,
        Full96_MILP_calls=0, official_campaign_calls=0, extra_or_repeated_Native_calls=0,
        audits_Native_calls=0, audits_solver_imports=0,
        all_instants_no_Heavy_concurrency_certified=False,
        note="Fresh admissions and periodic callback observations passed. No continuous all-instant concurrency proof is claimed. Stored Snapshot receipts and exact three-call ledger copy stay immutable. Native Runtime, wall, callback overhead and private system commit are recorded separately; no formulation-only speedup inference is made from elapsed time.")
    write(DOCS/"WINDOW_FINAL_RESOURCE_B1_AUDIT.json",receipt)
    print(json.dumps(dict(PASS=receipt["PASS"],checks=checks,Runtime=receipt["total_actual_Native_Runtime_seconds"],
                         wall=receipt["total_optimize_wall_seconds"],peak_RSS=receipt["peak_process_RSS_bytes"],
                         peak_Private=receipt["peak_private_commit_bytes"]),ensure_ascii=False))


if __name__ == "__main__":
    run()
