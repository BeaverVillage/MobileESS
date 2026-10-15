"""Compile all 31 public date cases and audit 124 production dispatch bindings.

This is a Native0 audit, not an execution driver. Its contexts come from the
real date and E1 compilers; no copied May01 manifest or fixture engine is used.
All artifacts are created under a fresh append-only output directory.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
import gc
import hashlib
import importlib
import inspect
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
DAYS = tuple(f"2025-05-{n:02d}" for n in range(1, 32))
ARMS = ("B0", "B1", "B2", "B3")
DEFAULT = ROOT / "docs/v42_unified_aidc_mess_research_20261014/RELEASE_RECOVERY_20261015/RC04/TABLE_V/PR230_REPAIR_20261015/MONTH_NATIVE0_01"


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def record(path):
    path = Path(path)
    return dict(path=str(path.resolve()), sha256=hashlib.sha256(path.read_bytes()).hexdigest(), bytes=path.stat().st_size)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
        allow_nan=False).encode()).hexdigest()


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


@contextmanager
def native0_guard():
    """Fail on model creation, solver execution, geometry, Actual or private IO."""
    import gurobipy as gp
    import v42_native  # Install the normal production backstop before guards.
    counts = Counter(model_builds=0, Native_calls=0, geometry_materializations=0,
        Actual_calls=0, AC_calls=0, private_future_reads=0)
    originals = []
    state = dict(active=True, public_data_read_paths=set(), provenance_actual_bundle_byte_paths=set(),
        approved_forecast_weather_parquet_paths=set())

    def forbidden(kind):
        def reject(*args, **kwargs):
            counts[kind] += 1
            raise RuntimeError("TABLE_V_MONTH_NATIVE0_FORBIDDEN:" + kind)
        return reject

    def patch(owner, name, kind):
        originals.append((owner, name, getattr(owner, name)))
        setattr(owner, name, forbidden(kind))

    patch(gp.Model, "__init__", "model_builds")
    patch(gp.Model, "optimize", "Native_calls")
    patch(gp.Env, "__init__", "model_builds")
    patch(gp, "read", "model_builds")
    previous_profile = sys.getprofile()

    def profile(frame, event, arg):
        if event != "call":
            return
        module = frame.f_globals.get("__name__", "")
        if frame.f_code.co_name == "read_parquet":
            caller = frame.f_back
            if (caller is None or caller.f_globals.get("__name__") != "v42_integration.production_case"
                    or caller.f_code.co_name != "planning_power"):
                forbidden("private_future_reads")()
            # planning_power has just validated this original forecast-weather
            # receipt with _checked; it is a public C1 input, not a job outcome.
            state["approved_forecast_weather_parquet_paths"].add(str(frame.f_locals.get("path")))
        if not module.startswith("v42_"):
            return
        name = frame.f_code.co_name
        if name in {"read", "read_json", "checked_json"}:
            candidate = frame.f_locals.get("path", frame.f_locals.get("receipt"))
            candidate = candidate.get("path") if isinstance(candidate, dict) else candidate
            if candidate is not None and Path(str(candidate)).name.upper() == "ACTUAL_INPUT_BUNDLE.JSON":
                forbidden("private_future_reads")()
        if name in {"physical_domain", "authorized_geometry", "authorized_data", "materialize_physical"}:
            forbidden("geometry_materializations")()
        if name in {"build_native_model", "build_d0_native_model", "build_flex_native_model"}:
            forbidden("model_builds")()
        if name in {"run_actual", "run_fullflex_actual", "run_production_actual"}:
            forbidden("Actual_calls")()

    def io_audit(event, args):
        if not state["active"] or event != "open" or not args or not isinstance(args[0], (str, bytes)):
            return
        path = str(args[0]).replace("\\", "/")
        lower = path.lower()
        if lower.endswith((".py", ".pyc", ".pyd", ".dll")):
            return
        if any(token in lower for token in ("private_truth", "actual_truth", "realized_duration", "future_request_bank", "runtime_truth")):
            forbidden("private_future_reads")()
        if lower.endswith((".json", ".gz", ".csv", ".npz", ".pkl", ".parquet")):
            mode = args[1] if len(args) > 1 else None
            if mode is None or "r" in str(mode):
                state["public_data_read_paths"].add(path)
                if Path(path).name.upper() == "ACTUAL_INPUT_BUNDLE.JSON":
                    state["provenance_actual_bundle_byte_paths"].add(path)

    sys.addaudithook(io_audit)
    sys.setprofile(profile)
    try:
        yield counts, state
    finally:
        state["active"] = False
        sys.setprofile(previous_profile)
        for owner, name, original in reversed(originals):
            setattr(owner, name, original)


def validate_context(context, day, *, flex):
    """Reject cross-date records and future job metadata before dispatch checks."""
    from v42_integration.d0_a_planning import input_fingerprint
    manifest, state = context["manifest"], context["state"]
    if day not in DAYS or state["day"] != day or context.get("day", day) != day:
        raise ValueError("MONTH_CONTEXT_DAY_MISMATCH")
    if manifest.get("day", day) != day:
        raise ValueError("MONTH_MANIFEST_DAY_MISMATCH")
    if manifest["identity"]["initial_state_sha"] != state["common_initial_state_sha"]:
        raise ValueError("MONTH_INITIAL_STATE_IDENTITY_MISMATCH")
    if manifest["source_native_record"]["path"].replace("\\", "/").split("/")[-2] != day:
        raise ValueError("MONTH_NATIVE_SOURCE_IS_NOT_INDEPENDENT_SAME_DAY")
    axis = manifest["time_axis"]
    begin = state["begin_epoch_seconds"]
    if (axis["evaluation_begin_seconds"] != begin or axis["evaluation_end_seconds"] != begin + 86400
            or axis["native_slot_zero_seconds"] != begin - 21600 or axis["slots"] != 96
            or axis["native_model_slots"] != [24, 120]):
        raise ValueError("MONTH_INDEPENDENT_96_SLOT_DATE_AXIS_REQUIRED")
    if any(r["submit_seconds"] > begin for key in ("running", "pending") for r in state[key]):
        raise ValueError("MONTH_FUTURE_UNKNOWN_UID_IN_PLANNING")
    forecast = manifest["forecast_receipt"]
    if (forecast["target_day"] != day or forecast["day_begin_seconds"] != begin
            or forecast["forecast_source_available_seconds"] > begin or forecast["actual_future_UIDs_used"] is not False):
        raise ValueError("MONTH_CAUSAL_SAME_DAY_CC4_REQUIRED")
    if context["input_audit"]["a_input_sha"] != input_fingerprint(context["data"]):
        raise ValueError("MONTH_ACTUAL_TYPED_INPUT_SHA_DRIFT")
    if context["data"][5] or context["data"][6]:
        raise ValueError("MONTH_NATIVE0_GEOMETRY_MUST_REMAIN_UNMATERIALIZED")
    if flex:
        spec = context["tablev_flex"]["spec"]
        if (spec["scenario"], spec["participation"], spec["R2"], spec["P2_calls"]) != ("E1", "FLEX30", "HOLD", 0):
            raise ValueError("MONTH_ORIGINAL_E1_FLEX30_R1_R2_POLICY_DRIFT")
        if manifest["identity"]["case_sha"] == manifest["parent_basic_manifest"]["identity"]["case_sha"]:
            raise ValueError("MONTH_BASIC_AND_FLEX_PROBLEMS_MUST_REMAIN_DISTINCT")
        if any(t < 24 or t >= 120 for starts in context["windows"].values() for t in starts):
            raise ValueError("MONTH_COMPILED_DOMAIN_GRANTS_PAST_OR_POST_D0_START")
    return dict(day=day, source_identity=manifest["identity"], source_sha=manifest["source_sha"],
        initial_record=manifest["initial_record"], native_record=manifest["source_native_record"],
        initial_state_sha=state["common_initial_state_sha"], typed_input_sha=context["input_audit"]["a_input_sha"],
        forecast_receipt_sha=forecast["forecast_receipt_sha"], public_D0_epoch_seconds=begin,
        observed_running_UIDs=len(state["running"]), observed_pending_UIDs=len(state["pending"]),
        positive_remaining_UIDs=len(context["data"][1]), public_job_UIDs=len(context["data"][4]),
        slots=96, future_Unknown_UIDs_used=False, future_Actual_realizations_parsed_or_used=False,
        native_geometry_materialized=False)


def validate_month_rows(rows, days=DAYS):
    expected = {(day, arm) for day in days for arm in ARMS}
    keys = [(row["day"], row["arm"]) for row in rows]
    if len(keys) != len(expected) or set(keys) != expected:
        raise ValueError("MONTH_REQUIRES_EXACTLY_ONE_BINDING_PER_DATE_AND_ARM")
    by_day = {day: [r for r in rows if r["day"] == day] for day in days}
    for day, records in by_day.items():
        if len({r["initial_state_sha"] for r in records}) != 1 or len({r["source_identity"]["case_sha"] for r in records}) != 1:
            raise ValueError("MONTH_FOUR_ARMS_MUST_SHARE_CURRENT_DATE_CASE_AND_INITIAL_STATE")
    for key in ("initial_state_sha", "typed_input_sha", "public_D0_epoch_seconds"):
        if len({records[0][key] for records in by_day.values()}) != len(days):
            raise ValueError("MONTH_DATES_MUST_NOT_CLONE_INITIAL_OR_INPUT_OR_AXIS:" + key)
    if len({records[0]["source_identity"]["case_sha"] for records in by_day.values()}) != len(days):
        raise ValueError("MONTH_DATE_CASE_SHA_MUST_BE_INDEPENDENT")
    return True


def validate_dispatch(dispatch, context_check, arm):
    """Independently check actual handler names, stages, source and date binding."""
    for key in ("day", "source_sha", "source_identity", "initial_state_sha"):
        if dispatch.get(key) != context_check[key]:
            raise ValueError("MONTH_PRODUCTION_DISPATCH_BINDING_DRIFT:" + key)
    if dispatch.get("arm") != arm or dispatch.get("input_sha") != context_check["typed_input_sha"]:
        raise ValueError("MONTH_PRODUCTION_DISPATCH_ARM_OR_INPUT_DRIFT")
    expected_stages = dict(B0=["ACTUAL96", "FRESH_AC96"], B1=["A1", "ACTUAL96", "FRESH_AC96"],
        B2=["M1", "K48_M1", "ACTUAL96", "FRESH_AC96"],
        B3=["A1", "M1", "K48_M1", "A2", "M2", "K48_M2", "ACTUAL96", "FRESH_AC96"])
    if dispatch.get("stages") != expected_stages[arm]:
        raise ValueError("MONTH_PRODUCTION_DISPATCH_STAGE_SEQUENCE_DRIFT")
    expected_targets = dict(A="v42_integration.table_v_a:execute_current_a",
        M="v42_integration.table_v_mess:TableVMessStages",
        K48="v42_integration.table_v_k48:run_current_k48",
        ACTUAL=("v42_integration.tablev_fullflex_actual:run_fullflex_actual" if arm in ("B1", "B3")
            else "v42_integration.tablev_actual:run_tablev_actual"),
        FRESH="v42_integration.tablev_actual:run_tablev_fresh",
        ARM="v42_integration.table_v_run:run_arm")
    if dispatch.get("executors") != expected_targets:
        raise ValueError("MONTH_PRODUCTION_REAL_EXECUTOR_TARGETS_REQUIRED")
    if (dispatch.get("slots"), dispatch.get("slot_seconds"), dispatch.get("P2_calls"),
            dispatch.get("Worker"), dispatch.get("Threads"), dispatch.get("R2")) != (96, 900, 0, 1, 1, "HOLD"):
        raise ValueError("MONTH_PRODUCTION_PHYSICAL_OR_SERIAL_POLICY_DRIFT")
    sources = {}
    for key, target in expected_targets.items():
        module, name = target.split(":")
        handler = getattr(importlib.import_module(module), name)
        if not callable(handler) or handler.__module__ != module:
            raise ValueError("MONTH_PRODUCTION_CALLABLE_MODULE_DRIFT:" + target)
        sources[key] = dict(target=target, callable_qualname=handler.__qualname__,
            source=record(inspect.getsourcefile(handler)))
    claimed_sources = dispatch.get("executor_source_records")
    expected_sources = list({value["source"]["path"]: value["source"] for value in sources.values()}.values())
    if claimed_sources != expected_sources:
        raise ValueError("MONTH_PRODUCTION_EXECUTOR_SOURCE_SHA_RECORD_DRIFT")
    return sources


def audit_month(output, *, days=DAYS):
    """Use real compiler callables and production describe_case, never execute."""
    from v42_integration.release_date_case import compile_date_case
    from v42_integration.table_v_flex_planning import compile_table_v_flex_context
    from v42_integration.table_v_campaign import describe_case, preflight_table_v_plan, executor_sources
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError("MONTH_NATIVE0_APPEND_ONLY_OUTPUT_REQUIRED:" + str(output))
    output.mkdir(parents=True)
    began = time.perf_counter()
    source_names = ("v42_integration/release_date_case.py", "v42_integration/table_v_flex_planning.py",
        "v42_integration/table_v_campaign.py", "v42_integration/table_v_dates.py", "tools/audit_v42_table_v_month.py")
    pinned = list({r["path"]: r for r in [record(ROOT / name) for name in source_names] + executor_sources()}.values())
    rows, date_rows, case_bindings, execution_roots, failures = [], [], {}, {}, []
    with native0_guard() as (operations, io):
        for day in days:
            day_root = output / "CASES" / day
            execution_roots[day] = str(day_root)
            basic, flex, basic_check, flex_check = None, None, None, None
            try:
                basic = compile_date_case(day, output=day_root / "INPUTS/BASIC", call_cap=5400.)
                basic_check = validate_context(basic, day, flex=False)
                flex = compile_table_v_flex_context(basic, output=day_root / "INPUTS/FULL_FLEX", call_cap=5400.)
                flex_check = validate_context(flex, day, flex=True)
                current_rows = []
                for arm in ARMS:
                    dispatch = describe_case(flex, arm)
                    callable_sources = validate_dispatch(dispatch, flex_check, arm)
                    current_rows.append(dict(flex_check, arm=arm, dispatch=dispatch,
                        production_callable_dispatched=True, callable_sources=callable_sources,
                        production_compilers_used=True, execution_performed=False, status="PASS_NATIVE0_BINDING"))
                rows.extend(current_rows)
                date_rows.append(dict(day=day, status="PASS_NATIVE0_BINDING", BASIC=basic_check, FULL_FLEX=flex_check,
                    checked_arms=list(ARMS), independent_source_initial_input=True))
                case_bindings[day] = {k: flex_check[k] for k in ("day", "source_sha", "source_identity")}
                print(json.dumps(dict(day=day, status="PASS_NATIVE0_BINDING", arms=4,
                    Known_UIDs=flex_check["public_job_UIDs"], case_sha=flex_check["source_identity"]["case_sha"])), flush=True)
            except Exception as error:
                # Preserve original failed/partial compiler artifacts; the next
                # independent date still receives its own four explicit entries.
                failure = dict(day=day, status="NOT_CERTIFIED_INPUT_OR_BINDING_UNAVAILABLE",
                    error_type=type(error).__name__, reason=str(error), BASIC=basic_check, FULL_FLEX=flex_check,
                    approved_initial_receipt=str(ROOT / "docs/v42_unified_aidc_mess_research_20261014/RELEASE_RECOVERY_20261015/RC02/INITIAL_STATES" / day / "INITIAL_STATE_RECEIPT.json"),
                    partial_artifacts_preserved=True, no_domain_or_authority_extension_applied=True)
                failures.append(failure)
                date_rows.append(failure)
                for arm in ARMS:
                    rows.append(dict(day=day, arm=arm, status=failure["status"], reason=str(error),
                        source_identity=flex_check["source_identity"] if flex_check else None,
                        execution_performed=False, production_compilers_used=True,
                        production_callable_dispatched=False))
                print(json.dumps(dict(day=day, status=failure["status"], reason=str(error))), flush=True)
            finally:
                write_new(day_root / "NATIVE0_DATE_BINDING_AUDIT.json", date_rows[-1])
                del basic, flex
                gc.collect()
        successful_days = tuple(r["day"] for r in date_rows if r["status"] == "PASS_NATIVE0_BINDING")
        if successful_days:
            validate_month_rows([r for r in rows if r["status"] == "PASS_NATIVE0_BINDING"], days=successful_days)
        plan = dict(schema="TABLE_V_FOUR_ARM_PRODUCTION_PLAN_V1", dates=list(days),
            execution_roots=execution_roots, case_bindings=case_bindings,
            execution_scope="PREPARED_ONLY", heavy_launch_enabled=False, automatic_start=False,
            P2_calls=0, Worker=1, Threads=1, R2="HOLD")
        write_new(output / "PRODUCTION_PLAN.json", plan)
        preflight = preflight_table_v_plan(plan)
    source_byte_match = pinned == [record(r["path"]) for r in pinned]
    passed = (not failures and source_byte_match and all(value == 0 for value in operations.values())
        and preflight.get("blockers") == [] and preflight.get("status") == "PASS_NATIVE0_WIRING")
    assert len(rows) == len(days) * len(ARMS)
    report = dict(schema="TABLE_V_MONTH_NATIVE0_PRODUCTION_BINDING_AUDIT_V1",
        status=("PASS_NATIVE0_124_CASES" if tuple(days) == DAYS else "PASS_NATIVE0_SELECTED_DATES") if passed else "NOT_CERTIFIED_NATIVE0_MONTH",
        created_utc=datetime.now(timezone.utc).isoformat(), dates=list(days), arms=list(ARMS),
        case_count=len(rows), independent_dates=len(date_rows), successful_dates=len(successful_days),
        blocked_dates=failures, all_pinned_source_bytes_equal=source_byte_match, cases=rows, date_inputs=date_rows,
        May02_May10_May12_checks=[r for r in date_rows if r["day"] in ("2025-05-02", "2025-05-10", "2025-05-12")],
        production_plan=record(output / "PRODUCTION_PLAN.json"), plan_preflight=preflight,
        operations=dict(operations), Gurobi_imported_for_immutable_type_metadata=True,
        source_provenance_and_public_data_read_paths=sorted(io["public_data_read_paths"]), pinned_source=pinned,
        approved_forecast_weather_parquet_paths=sorted(io["approved_forecast_weather_parquet_paths"]),
        original_provenance_ACTUAL_bundle_byte_hash_paths=sorted(io["provenance_actual_bundle_byte_paths"]),
        provenance_byte_hashes_are_future_realization_parsing=False,
        authorized_execution_scope="PREPARED_ONLY_NO_HEAVY_EXECUTION", May02_31_auto_launch_enabled=False,
        limitations=["Dispatch/typed input validation is not FULL feasibility or DW pricing certification.",
            "No model, optimizer, Actual96, Fresh96, AC, or future private realization parsing was executed.",
            "The original compiler verifies source receipt SHA by hashing original ACTUAL bundle and raw archive bytes; no such future records are parsed or used.",
            "All date contexts are independently compiled from their approved public D0 initial state and same-day forecast."],
        wall_seconds=time.perf_counter() - began)
    write_new(output / "MONTH_NATIVE0_AUDIT.json", report)
    with (output / "KO.md").open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(f"# Table V 날짜별 Native0 생산 바인딩 감사\n\n상태: {report['status']}. "
            f"{len(days)}일 × 4 Arm = {len(rows)} Case를 기록했고 날짜별 PASS {len(successful_days)}, 미인증 {len(failures)}일이다. "
            "실제 날짜별 compiler와 E1/FLEX30 compiler를 사용해 독립 준비하고 production dispatch 바인딩을 검사했다. "
            "May02·May10·May12는 날짜·초기상태·Native 원본·CC4·Typed Input SHA를 개별 기록했다. "
            "96슬롯·원본 물리권한·R1·R2 HOLD·P2 0회가 유지된다.\n\n"
            "Native/model build/geometry/Actual/AC/미래 실현정보 parsing은 모두 0회다. "
            "원본 source receipt의 SHA 확인은 ACTUAL bundle·raw archive byte hashing을 포함하며, 미래 정보 사용과 구분했다. "
            "계획 범위는 PREPARED_ONLY이며, 이 감사가 May02–31 자동 실행이나 예산 추가를 허용하지 않는다.\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT)
    parser.add_argument("--dates", nargs="+", choices=DAYS)
    args = parser.parse_args()
    days = tuple(args.dates) if args.dates else DAYS
    if len(set(days)) != len(days):
        parser.error("dates must be unique")
    report = audit_month(args.output, days=days)
    print(json.dumps(dict(status=report["status"], case_count=report["case_count"],
        Native_calls=report["operations"]["Native_calls"], wall_seconds=report["wall_seconds"])))


if __name__ == "__main__":
    main()
