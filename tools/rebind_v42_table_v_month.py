"""Rebind previously audited immutable date inputs to final production sources.

Saved public records are deserialized into typed contexts with exact original
input SHA checks. The original loader is a fail-closed fallback for a typed
serialization mismatch. No optimization or Actual runs.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import wraps
import argparse
import gc
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.audit_v42_table_v_month import (ARMS, DAYS, digest, native0_guard, read, record,
    validate_context, validate_dispatch, validate_month_rows, write_new)
from tools.table_v_frozen_context import load_frozen_typed_context


@contextmanager
def checked_public_serialization():
    """Avoid profiler overhead in unchanged public serialization functions only.

    Constructor/optimizer and IO guards remain installed. These original
    serialization/fingerprint functions never dispatch a solver or controller.
    No compiler, descriptor, writer source bytes or result values are changed.
    """
    from v42_integration import d0_a_planning, d0_case, m_engine, release_initial_states, table_v_flex_planning
    originals = []
    for module, name in ((d0_case, "_write"), (m_engine, "_write"),
            (table_v_flex_planning, "_write"), (release_initial_states, "write_json"),
            (d0_a_planning, "input_fingerprint"), (table_v_flex_planning, "input_fingerprint")):
        original = getattr(module, name)

        @wraps(original)
        def write(*args, _original=original, **kwargs):
            prior = sys.getprofile()
            sys.setprofile(None)
            try:
                return _original(*args, **kwargs)
            finally:
                sys.setprofile(prior)

        originals.append((module, name, original))
        setattr(module, name, write)
    try:
        yield
    finally:
        for module, name, original in reversed(originals):
            setattr(module, name, original)


def completed_input_proof(audit_root, output):
    """Separate completed independent inputs from later executor source changes."""
    from v42_integration.table_v_flex_planning import require_flex_case
    audit_root, output = Path(audit_root).resolve(), Path(output).resolve()
    original_path = audit_root / "MONTH_NATIVE0_AUDIT.json"
    original = read(original_path)
    if (original.get("dates") != list(DAYS) or original.get("case_count") != 124
            or original.get("successful_dates") != 31 or original.get("blocked_dates")
            or any(original.get("operations", {}).values())
            or any(r.get("status") != "PASS_NATIVE0_BINDING" for r in original.get("cases", []))):
        raise ValueError("COMPLETED_124_INDEPENDENT_TYPED_INPUTS_REQUIRED")
    validate_month_rows(original["cases"])
    plan = read(audit_root / "PRODUCTION_PLAN.json")
    records, scientific_sources = [], {}
    with native0_guard() as (operations, _):
        for day in DAYS:
            root = Path(plan["execution_roots"][day])
            path = root / "INPUTS/FULL_FLEX/TABLE_V_FLEX_CASE_MANIFEST.json"
            manifest = require_flex_case(read(path))
            input_path = root / "INPUTS/FULL_FLEX/TABLE_V_FLEX_INPUT_AUDIT.json"
            audit = read(input_path)
            matching = [r for r in original["cases"] if r["day"] == day]
            if (len(matching) != 4 or any(r["source_identity"] != manifest["identity"]
                    or r["typed_input_sha"] != audit["a_input_sha"]
                    or r["typed_input_sha"] != manifest["full_flex_input_sha"] for r in matching)):
                raise ValueError("COMPLETED_DATE_INPUT_EVIDENCE_DRIFT:" + day)
            for source in manifest["source_freeze"]["files"]:
                scientific_sources[source["path"]] = source
            for source in manifest["parent_basic_manifest"].get("date_compiler_source", []):
                scientific_sources[source["path"]] = source
            records.append(dict(day=day, manifest=record(path), input_audit=record(input_path),
                identity=manifest["identity"], typed_input_sha=audit["a_input_sha"], checked_arms=list(ARMS)))
        assert all(record(r["path"]) == r for r in scientific_sources.values())
    assert all(v == 0 for v in operations.values())
    changes = [dict(previous=r, current=record(r["path"])) for r in original["pinned_source"]
        if record(r["path"]) != r]
    proof = dict(schema="TABLE_V_MONTH_COMPLETED_INDEPENDENT_INPUT_PROOF_V1",
        status="PASS_31_DATES_124_TYPED_INPUT_CASES", original_input_audit=record(original_path),
        original_aggregate_status=original["status"], executor_source_status="FINAL_REBIND_REQUIRED",
        dates=list(DAYS), case_count=124, independent_initial_state_SHAs=31, independent_case_SHAs=31,
        independent_typed_input_SHAs=31, date_records=records,
        frozen_scientific_input_sources=list(scientific_sources.values()), scientific_input_source_bytes_unchanged=True,
        executor_source_changes_after_input_audit_started=changes, operations=dict(operations),
        execution_performed=False, physical_or_launch_certificate=False)
    write_new(output, proof)
    return proof


def rebind(audit_root, output):
    from v42_integration.table_v_campaign import describe_case, executor_sources, preflight_table_v_plan
    from v42_integration.table_v_flex_planning import load_table_v_context
    audit_root, output = Path(audit_root).resolve(), Path(output).resolve()
    if output.exists():
        raise FileExistsError("MONTH_REBIND_APPEND_ONLY_OUTPUT_REQUIRED:" + str(output))
    original_path = audit_root / "MONTH_NATIVE0_AUDIT.json"
    original = read(original_path)
    if (original.get("dates") != list(DAYS) or original.get("case_count") != 124
            or original.get("successful_dates") != 31 or original.get("blocked_dates")
            or any(original.get("operations", {}).values())):
        raise ValueError("ORIGINAL_NATIVE0_124_INPUT_BINDINGS_MUST_ALL_PASS_BEFORE_REBIND")
    if any(row.get("status") != "PASS_NATIVE0_BINDING" for row in original["cases"]):
        raise ValueError("ORIGINAL_124_DATE_ARM_INPUT_ROWS_MUST_ALL_PASS")
    protected_input_sources = {"experimental_qos.py", "experimental_planning.py", "experimental_policy.py",
        "qos.py", "table_v_flex_planning.py", "table_v_dates.py", "d0_case.py", "d0_a_planning.py",
        "release_date_case.py", "release_initial_states.py", "a_engine.py", "d0_actual_inputs.py",
        "v42_job_capability.py", "domain.py", "service.py", "producer.py", "generator.py",
        "audit_v42_table_v_month.py"}
    comparisons = [dict(expected=r, current=record(r["path"]),
        exact_bytes_equal=r == record(r["path"])) for r in original["pinned_source"]]
    if any(not r["exact_bytes_equal"] and Path(r["expected"]["path"]).name in protected_input_sources for r in comparisons):
        raise ValueError("PUBLIC_COMPILER_OR_SCIENTIFIC_INPUT_SOURCE_CHANGED_REQUIRES_NEW_INPUT_AUDIT")
    allowed_changes = {Path(r["expected"]["path"]).name for r in comparisons if not r["exact_bytes_equal"]}
    plan_path = audit_root / "PRODUCTION_PLAN.json"
    plan = read(plan_path)
    if plan.get("execution_scope") != "PREPARED_ONLY" or plan.get("automatic_start") is not False:
        raise ValueError("FINAL_METADATA_REBIND_IS_PREPARED_ONLY")
    output.mkdir(parents=True)
    began = time.perf_counter()
    pins = list({r["path"]: r for r in executor_sources() + [record(__file__),
        record(ROOT / "tools/audit_v42_table_v_month.py"), record(ROOT / "tools/table_v_frozen_context.py"),
        record(ROOT / "v42_integration/table_v_flex_planning.py"),
        record(ROOT / "v42_integration/release_date_case.py")]}.values())
    write_new(output / "SOURCES_AT_BEGIN.json", dict(schema="TABLE_V_REBIND_BEGIN_SOURCE_PINS_V1",
        created_utc=datetime.now(timezone.utc).isoformat(), records=pins,
        original_input_audit=record(original_path), plan=record(plan_path)))
    previous_days = {r["day"]: r for r in original["date_inputs"]}
    rows, input_records, fallback_records = [], [], []
    with native0_guard() as (operations, io):
        with checked_public_serialization():
            for day in DAYS:
                root = Path(plan["execution_roots"][day])
                frozen = sorted((root / "INPUTS").rglob("*"))
                before = [record(path) for path in frozen if path.is_file()]
                try:
                    context = load_frozen_typed_context(root)
                except ValueError as error:
                    if not str(error).startswith(("FROZEN_TYPED_BASIC_INPUT_FINGERPRINT_MISMATCH",
                            "FROZEN_TYPED_FULL_FLEX_INPUT_FINGERPRINT_MISMATCH")):
                        raise
                    # A serialization mismatch cannot be waived: the original
                    # loader must reproduce and byte-compare the saved records.
                    context = load_table_v_context(root / "INPUTS/FULL_FLEX")
                    fallback_records.append(dict(day=day, reason=str(error), original_loader_exact_recheck=True))
                checked = validate_context(context, day, flex=True)
                if checked != previous_days[day]["FULL_FLEX"]:
                    raise ValueError("ORIGINAL_TYPED_DATE_INPUT_CHANGED_DURING_EXECUTOR_REBIND:" + day)
                for arm in ARMS:
                    dispatch = describe_case(context, arm)
                    callable_sources = validate_dispatch(dispatch, checked, arm)
                    rows.append(dict(checked, arm=arm, status="PASS_FINAL_SOURCE_NATIVE0_BINDING",
                        dispatch=dispatch, callable_sources=callable_sources,
                        original_typed_input_unchanged=True, execution_performed=False))
                assert before == [record(r["path"]) for r in before], "SAVED_PUBLIC_INPUTS_CHANGED"
                input_records.extend(before)
                write_new(output / "DATES" / day / "TYPED_EXECUTOR_BINDING.json",
                    dict(schema="TABLE_V_REBIND_DATE_TYPED_BINDING_V1", day=day,
                        status="PASS_DATE_TYPED_BINDING_AWAITING_FINAL_SOURCE_BYTE_CHECK",
                        cases=rows[-len(ARMS):], source_records_at_begin=pins,
                        saved_public_input_records=before, operations=dict(operations),
                        original_typed_input_unchanged=True, execution_performed=False))
                print(day + " PASS_FINAL_SOURCE_NATIVE0_BINDING", flush=True)
                del context
                gc.collect()
        validate_month_rows(rows)
        preflight = preflight_table_v_plan(plan)
        if preflight.get("blockers") != [] or preflight.get("status") != "PASS_NATIVE0_WIRING":
            raise ValueError("FINAL_PRODUCTION_PREFLIGHT_WIRING_BLOCKERS:" + str(preflight))
    source_comparison = [dict(expected=r, current=record(r["path"]),
        exact_bytes_equal=r == record(r["path"])) for r in pins]
    all_source_bytes_equal = all(r["exact_bytes_equal"] for r in source_comparison)
    assert all(value == 0 for value in operations.values()), operations
    report = dict(schema="TABLE_V_MONTH_FINAL_EXECUTOR_NATIVE0_REBIND_V1",
        status="PASS_FINAL_SOURCE_NATIVE0_124_CASES" if all_source_bytes_equal else "NOT_CERTIFIED_EXECUTOR_SOURCE_CHANGED_DURING_REBIND",
        created_utc=datetime.now(timezone.utc).isoformat(), dates=list(DAYS), case_count=len(rows), cases=rows,
        original_input_audit=record(original_path), original_audit_source_comparison=comparisons,
        allowed_supervisor_source_changes=sorted(allowed_changes), original_typed_inputs_unchanged=True,
        existing_public_artifacts_unchanged=True, saved_public_input_records=input_records,
        plan=record(plan_path), final_plan_preflight=preflight, pinned_final_source=pins,
        all_final_source_bytes_equal=all_source_bytes_equal,
        final_source_byte_comparison=source_comparison, operations=dict(operations),
        approved_forecast_weather_parquet_paths=sorted(io["approved_forecast_weather_parquet_paths"]),
        original_provenance_ACTUAL_bundle_byte_hash_paths=sorted(io["provenance_actual_bundle_byte_paths"]),
        typed_context_loader="tools.table_v_frozen_context.load_frozen_typed_context",
        original_loader_fallback="v42_integration.table_v_flex_planning.load_table_v_context",
        original_loader_fallback_dates=fallback_records,
        loader_semantics="Deserialize already audited public records into typed descriptors; BASIC and FULL_FLEX fingerprints must exactly match saved/audited SHA before dispatch.",
        profiling_suspended_only_for_unchanged_original_public_JSON_and_fingerprint_serializers=True,
        physical_or_launch_certificate=False, May02_31_heavy_launch_enabled=False,
        limitations=["Final source metadata binding does not prove DW pricing, FULL feasibility or Actual/Fresh96.",
            "Original provenance byte hashing is separate from parsing or consuming future realizations."],
        wall_seconds=time.perf_counter() - began)
    write_new(output / "FINAL_EXECUTOR_REBIND.json", report)
    with (output / "KO.md").open("x", encoding="utf-8", newline="\n") as stream:
        stream.write("# Table V 최종 생산 소스 Native0 재바인딩\n\n" + report["status"] + "\n\n"
            "31일 × 4 Arm = 124 Case를 최종 생산 executor 소스에 재바인딩했다. "
            "기존 typed 공개입력은 저장 domain_mask·receipts·reference·public native로 복원하고 원본 input_fingerprint의 정확 일치를 확인했다. "
            "검토 후 변경된 executor 파일은 이전 소스와 구분했고, 최종 executor 파일 SHA를 다시 고정했다.\n\n"
            "Native/model build/geometry/Actual/AC/미래 실현정보 parsing은 0회다. "
            "계획은 PREPARED_ONLY이며 31일 Heavy 실행 또는 물리 결과 인증이 아니다.\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = rebind(args.audit_root, args.output)
    print(result["status"] + " cases=" + str(result["case_count"]))
    if not result["all_final_source_bytes_equal"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
