"""Independent Native-0 acceptance of every prepared D0 and literal CC4 row."""
import argparse
import csv
from datetime import datetime
import hashlib
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from v42_integration import release_initial_states as api
from tools.audit_v42_release_preservation import original_prediction_row


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--folder", default=str(ROOT / "docs/v42_unified_aidc_mess_research_20261014/RELEASE_RECOVERY_20261015/RC02/INITIAL_STATES"))
    args = parser.parse_args()
    folder = Path(args.folder)
    started = time.perf_counter()
    summary = api.read(folder / "MAY31_INITIAL_STATE_PREPARATION.json")
    source_snapshot = api.read(folder / "EXECUTED_SOURCE.json")
    for expected in source_snapshot["files"]:
        if api.record(expected["path"]) != expected:
            raise ValueError("EXECUTED_INITIAL_COMPILER_SOURCE_DRIFT")
    old_root = Path("D:/MobileESS_V42/docs/v42_may_b0_zero_margin_holdout")
    binding_path = old_root / "MAY_CC4_BINDING.json"
    binding = api.read(binding_path)
    sources = {role: api.checked(binding["interface"][role]) for role in ("prediction", "ledger", "selection")}
    with sources["ledger"].open(encoding="utf-8-sig", newline="") as stream:
        date_ledger = list(csv.DictReader(stream))
    cc4_rows, state_rows = [], []
    for entry in summary["days"]:
        day = entry["day"]
        daily = api.read(old_root / "CC4" / ("DAY_" + day.replace("-", "") + ".json"))
        idx = daily["prediction_index"]
        q50, q90, raw, shape = original_prediction_row(sources["prediction"], idx)
        literal = q50 == daily["Q50_GPUh"] and q90 == daily["Q90_GPUh"] and shape == binding["array_shape"]
        row_match = idx in binding["indices"] and date_ledger[idx]["target_day"] == day and (
            datetime.fromisoformat(date_ledger[idx]["issue_time"]) == datetime.fromisoformat(daily["issue_time"]))
        causal = api.seconds(daily["issue_time"]) <= api.midnight(day)
        if not literal or not row_match or not causal or daily["future_job_ids"] != []:
            raise ValueError("CC4_LITERAL_SOURCE_ROW_OR_ISSUE_MISMATCH:" + day)
        cc4_rows.append(dict(day=day, PASS=True, prediction_index=idx,
            literal_float64_row_sha256=hashlib.sha256(raw).hexdigest(), original_prediction_row_equal=True,
            original_DAY_LEDGER_day_and_issue_equal=True, issue_seconds=api.seconds(daily["issue_time"]),
            D0_seconds=api.midnight(day), daily_file=api.record(old_root / "CC4" / ("DAY_" + day.replace("-", "") + ".json"))))
        if entry["status"] != "INPUT_READY":
            state_rows.append(dict(day=day, status=entry["status"], PASS=False))
            continue
        state = api.load_initial_state(entry["initial_state"])
        events = api.read(folder / day / "PUBLIC_EVENT_PREFIX.json.gz")
        raw_folder = Path("D:/v42_may_joint_repair_campaign_20261013/raw") / day
        plan, native, actual = [api.read(raw_folder / name) for name in (
            "PLANNING_INPUT_BUNDLE.json", "NATIVE_INPUT_TEMPLATE_B1.json", "ACTUAL_INPUT_BUNDLE.json")]
        begin = api.midnight(day)
        public = api.public_population(plan, actual, begin)
        if set(events) != {r["job_uid"] for r in public}:
            raise ValueError("PUBLIC_PREFIX_ROSTER_NOT_EXACT_SOURCE_D0_FILTER:" + day)
        if any(any(value is not None and value > begin for value in (r["submit_seconds"],
            r["observed_start_seconds"], r["observed_completion_seconds"])) for r in events.values()):
            raise ValueError("PUBLIC_PREFIX_FUTURE_EVENT_VALUE:" + day)
        expected_running = {uid for uid, r in events.items() if r["observed_start_seconds"] is not None
            and r["observed_completion_seconds"] is None}
        expected_pending = {uid for uid, r in events.items() if r["observed_start_seconds"] is None}
        expected_completed = {uid for uid, r in events.items() if r["observed_completion_seconds"] is not None}
        if ({r["uid"] for r in state["running"]} != expected_running or {r["uid"] for r in state["pending"]} != expected_pending
            or {r["job_uid"] for r in state["historical_completed"]} != expected_completed):
            raise ValueError("INITIAL_POPULATION_NOT_EXACT_OBSERVED_EVENT_STATE:" + day)
        if day != "2025-05-01":
            recovery = api.read(folder / day / "PRIOR_REFERENCE_REUSE_AUDIT.json")
            receipts = state["source_receipts"][:5]
            rebuilt, _, _ = api.compile_state(day, dict(plan=plan, native=native, actual=actual), events, recovery, receipts)
            if rebuilt != state:
                raise ValueError("ORIGINAL_INITIALIZATION_RECOMPILE_OBJECT_MISMATCH:" + day)
        source_gpu = {r["job_uid"]: r["GPU_gang"] for r in public}
        occupancy = {site: 0 for site in state["capacities"]}
        for row in state["running"]:
            if row["gpu"] != source_gpu[row["uid"]] or row["site"] not in row["compatible_sites"]:
                raise ValueError("RUNNING_GANG_OR_COMPATIBILITY_DRIFT:" + day)
            occupancy[row["site"]] += row["gpu"]
        if any(occupancy[s] > state["capacities"][s] for s in occupancy) or occupancy != state["site_GPU_use"]:
            raise ValueError("RUNNING_PHYSICAL_GPU_OCCUPANCY_DRIFT:" + day)
        state_rows.append(dict(day=day, PASS=True, initial_semantic_sha=state["common_initial_state_sha"],
            running_UIDs=len(expected_running), pending_UIDs=len(expected_pending), previous_completed_UIDs=len(expected_completed),
            running_GPU=sum(occupancy.values()), source_population_equal=True, original_initializer_recompile_equal=True,
            Q50_expired_running_GPU_physically_retained=sum(r["gpu"] for r in state["running"]
                if r["elapsed_compute_seconds"] >= r["q50"]), future_Unknown_UIDs_in_Planning=0,
            future_completion_values_in_Planning=0, previous_day_Actual_carry_used=False))
    cc4_audit = dict(PASS=len(cc4_rows) == 31, days=cc4_rows, binding_file=api.record(binding_path),
        original_source_files={role: api.record(path) for role, path in sources.items()},
        selected_model=binding["interface"]["model"], new_fit_calls=0,
        inherited_model_selection_retrospective=binding["inherited_model_selection_retrospective"],
        unexported_fit_ingestion_receipts_not_certified=binding["unexported_fit_ingestion_receipts_not_certified"],
        inherited_science_limitations_removed=False)
    api.write_json(folder / "CC4_31_DAY_LITERAL_ROW_AUDIT.json", cc4_audit)
    acceptance = dict(PASS=len(state_rows) == 31 and all(r["PASS"] for r in state_rows) and cc4_audit["PASS"],
        days=state_rows, CC4_literal_row_audit=api.record(folder / "CC4_31_DAY_LITERAL_ROW_AUDIT.json"),
        Native_Optimize_calls=0, P2_calls=0, AC_solves=0, Actual_runs=0,
        source_model_policy_unchanged=True, original_initial_bytes_preserved=True,
        downstream_Date_specific_D0_Planning_compiler_certified=False,
        public_initial_state_does_not_expose_future_UIDs_or_completion=True,
        wall_seconds=time.perf_counter() - started,
        audit_source=api.record(__file__))
    api.write_json(folder / "INDEPENDENT_INITIAL_STATE_ACCEPTANCE.json", acceptance)
    print("INDEPENDENT_INITIAL_STATE_ACCEPTANCE", acceptance["PASS"], len(state_rows), acceptance["wall_seconds"])


if __name__ == "__main__":
    main()
