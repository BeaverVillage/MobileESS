"""Run only the time-limited V39E RW-anchored fast gate."""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed
import json
from pathlib import Path
import subprocess
from typing import Any, Mapping

import pandas as pd

from dayahead.v38.authority import canonical_sha256
from dayahead.v39a.spatial import active_gpu_profile, production_activity
from dayahead.v39c.freeze import atomic_json, sha256_file
from dayahead.v39d.rack_freeze import load_v39d_rack_authority

from .contracts import (
    ARTIFACT_ROOT,
    BRANCH,
    CAPACITY_FILE_SHA256,
    EXPECTED_DATES,
    EXPECTED_GPU_CAPACITY,
    IMPLEMENTATION_ID,
    MAX_PARALLEL_DAY_WORKERS,
    RACK_AUTHORITY_PATH,
    RACK_AUTHORITY_SHA256,
    RACK_FREEZE_COMMIT,
    START_HEAD,
    V37_DAY_ROOT,
)
from .initial_state import build_rw_anchored_initial_state


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=repo, text=True, encoding="utf-8"
    ).strip()


def _write_review(root: Path, result: Mapping[str, Any]) -> None:
    blocker = result.get("first_blocker") or "NONE"
    review = f"""# V39E fast initial-state review

This time-limited validation changes only the independent-day common synthetic
initial-state generator.  Each state is anchored to the causally available RW
Day-Ahead reference schedule and then shared byte-identically by B0/B1/B2/B3.
It does not run RSP, migration, WAN witness, power/PCC, Fresh, production
preflight, or the May campaign.

- Initial states PASS: {result['initial_states_PASS']}/31
- RW reference spatial/Rack PASS: {result['RW_REFERENCE_PASS']}/31
- B0/B1/B2/B3 initial SHA identity: {result['B0_B1_B2_B3_initial_SHA_identity']}
- Inter-day state carries: {result['inter_day_state_carry_count']}
- Cross-day result reads: {result['cross_day_result_read_count']}
- Migration solver calls today: {result['migration_solver_calls_today']}
- Frozen Rack authority SHA: `{RACK_AUTHORITY_SHA256}`
- Rack freeze commit: `{RACK_FREEZE_COMMIT}`
- First blocker: {blocker}

V39E_INITIALIZATION_CORRECTION_PASS = {result['V39E_INITIALIZATION_CORRECTION_PASS']}
FULL_V39E_PREFLIGHT_DEFERRED = YES
V39E_READY = NOT_YET_EVALUATED
MAY_CAMPAIGN_LAUNCH_READY = NO
MAY_STARTED = NO
"""
    (root / "V39E_FAST_INITIAL_STATE_REVIEW.md").write_text(
        review, encoding="utf-8", newline="\n"
    )


def _construct_initial_day(
    repo_text: str, day: str, capacity: Any,
) -> tuple[str, dict[str, Any]]:
    repo = Path(repo_text)
    source_root = repo / V37_DAY_ROOT / day
    ledger = pd.read_parquet(source_root / "V37_R4A_JOB_LEDGER.parquet")
    running = ledger.loc[ledger["state_at_issue"].eq("RUNNING")]
    running_jobs = tuple(
        (str(row.job_id), int(row.requested_GPUs))
        for row in running.itertuples(index=False)
    )
    rw_path = source_root / "V37_R4A_RW_SCHEDULE.parquet"
    rw_jobs = production_activity(pd.read_parquet(rw_path))
    constructed = build_rw_anchored_initial_state(
        running_jobs,
        rw_jobs,
        capacity,
        name=f"V39E_RW_ANCHORED_INITIAL_{day}",
        planning_repo=repo,
        operating_day=day,
    )
    if constructed["status"] != "PASS":
        return day, constructed
    rows = [
        {
            "operating_day": day,
            "job_uid": uid,
            "requested_GPU": gpu,
            "initial_AIDC": constructed["initial_state"][uid],
            "initialization_class": "RW_REFERENCE_ANCHORED_SYNTHETIC",
            "D1_visible": True,
            "synthetic_site_claim": True,
            "measured_site_claim": False,
        }
        for uid, gpu in sorted(running_jobs)
    ]
    initial_sha = canonical_sha256(rows)
    return day, {
        **constructed,
        "operating_day": day,
        "initial_state_SHA256": initial_sha,
        "B0_initial_state_SHA": initial_sha,
        "B1_initial_state_SHA": initial_sha,
        "B2_initial_state_SHA": initial_sha,
        "B3_initial_state_SHA": initial_sha,
        "B0_B1_B2_B3_SHA_identity": True,
        "RW_reference_schedule_SHA256": sha256_file(rw_path),
        "initial_rows": rows,
    }


def evaluate(repo: Path) -> dict[str, Any]:
    repo = repo.resolve()
    if _git(repo, "branch", "--show-current") != BRANCH:
        raise RuntimeError("V39E_BRANCH_MISMATCH")
    if _git(repo, "merge-base", "HEAD", START_HEAD) != START_HEAD:
        raise RuntimeError("V39E_START_HEAD_ANCESTRY")
    root = repo / ARTIFACT_ROOT
    root.mkdir(parents=True, exist_ok=True)

    authority_sha_before = sha256_file(repo / RACK_AUTHORITY_PATH)
    capacity_path = (
        repo / "dayahead/artifacts/v39c_aidc_gpu_capacity_refreeze/"
        "V39C_H100_EQUIVALENT_SITE_CAPACITY_AUTHORITY.json"
    )
    capacity_sha_before = sha256_file(capacity_path)
    if authority_sha_before != RACK_AUTHORITY_SHA256:
        raise RuntimeError("V39E_RACK_AUTHORITY_SHA_DRIFT")
    if capacity_sha_before != CAPACITY_FILE_SHA256:
        raise RuntimeError("V39E_SITE_CAPACITY_SHA_DRIFT")
    capacity, rack_source = load_v39d_rack_authority(repo)
    if dict(capacity.site_capacity) != EXPECTED_GPU_CAPACITY:
        raise RuntimeError("V39E_SITE_CAPACITY_VECTOR_DRIFT")
    if rack_source["certificate"]["rack_freeze_commit"] != RACK_FREEZE_COMMIT:
        raise RuntimeError("V39E_RACK_FREEZE_COMMIT_DRIFT")

    day_results: dict[str, dict[str, Any]] = {}
    initial_days: list[dict[str, Any]] = []
    first_blocker: str | None = None
    with ProcessPoolExecutor(max_workers=MAX_PARALLEL_DAY_WORKERS) as pool:
        futures = {
            pool.submit(_construct_initial_day, str(repo), day, capacity): day
            for day in EXPECTED_DATES
        }
        for future in as_completed(futures):
            day, result = future.result()
            day_results[day] = result

    for day in EXPECTED_DATES:
        result = day_results[day]
        if result["status"] != "PASS":
            if first_blocker is None:
                first_blocker = f"{day}:{result.get('reason', 'INITIAL_STATE_FAILED')}"
            continue
        rows = result["initial_rows"]
        initial_days.append({
            key: result[key] for key in (
                "operating_day",
                "initial_state_SHA256",
                "B0_initial_state_SHA",
                "B1_initial_state_SHA",
                "B2_initial_state_SHA",
                "B3_initial_state_SHA",
                "B0_B1_B2_B3_SHA_identity",
                "RW_reference_schedule_SHA256",
                "D1_snapshot_load_GPU",
                "maximum_RW_load_GPU_by_AIDC",
                "site_capacity_violations",
                "rack_compatibility_failures",
                "gang_split_count",
            )
        } | {"initial_rows": rows})

    common_audit = {
        "artifact_id": "V39E_COMMON_INITIAL_STATE_AUDIT_V1",
        "status": "PASS" if len(initial_days) == 31 else "FAIL_CLOSED",
        "implementation_id": IMPLEMENTATION_ID,
        "initial_state_authority": "D1_AVAILABLE_RW_DAYAHEAD_REFERENCE",
        "initial_states_PASS": len(initial_days),
        "expected_days": 31,
        "B0_B1_B2_B3_initial_SHA_identity": all(
            row["B0_B1_B2_B3_SHA_identity"] for row in initial_days
        ) and len(initial_days) == 31,
        "inter_day_state_carry_count": 0,
        "cross_day_result_read_count": 0,
        "cross_day_AIDC_state_read_count": 0,
        "cross_day_migration_state_read_count": 0,
        "RSP_reads": 0,
        "Actual_reads": 0,
        "Fresh_reads": 0,
        "grid_Actual_reads": 0,
        "migration_result_reads": 0,
        "previous_simulated_day_reads": 0,
        "site_capacity": dict(capacity.site_capacity),
        "capacity_SHA256": capacity_sha_before,
        "Rack_authority_SHA256": authority_sha_before,
        "Rack_freeze_commit": RACK_FREEZE_COMMIT,
        "days": initial_days,
        "MAY_STARTED": "NO",
    }
    # The common state artifact is frozen before the separate RW witness replay
    # below.  No RSP or migration path is imported or called.
    atomic_json(root / "V39E_COMMON_INITIAL_STATE_AUDIT.json", common_audit)

    rw_days: list[dict[str, Any]] = []
    if len(initial_days) == 31:
        for day in EXPECTED_DATES:
            result = day_results[day]
            witness = result["RW_witness"]
            initial_state = result["initial_state"]
            active_jobs = production_activity(pd.read_parquet(
                repo / V37_DAY_ROOT / day / "V37_R4A_RW_SCHEDULE.parquet"
            ))
            by_uid = {row["job_uid"]: row for row in witness}
            initial_mismatch = sum(
                job.state_at_issue == "RUNNING"
                and by_uid[job.job_uid]["destination_AIDC"]
                != initial_state[job.job_uid]
                for job in active_jobs
            )
            aggregate_expected = active_gpu_profile(active_jobs)
            aggregate_witness = [0] * 96
            site_load = {
                site: [0] * 96 for site in capacity.aidc_ids
            }
            rack_failures = 0
            for row in witness:
                start, end = row["active_start_slot"], row["active_end_slot"]
                if start is None or end is None:
                    continue
                site = row["destination_AIDC"]
                gpu = int(row["requested_GPU"])
                rack_failures += int(not capacity.eligible_racks(site, gpu))
                for slot in range(int(start), int(end)):
                    aggregate_witness[slot] += gpu
                    site_load[site][slot] += gpu
            aggregate_error = max(
                abs(int(left) - int(right))
                for left, right in zip(aggregate_expected, aggregate_witness, strict=True)
            )
            site_violations = sum(
                value > int(capacity.site_capacity[site])
                for site, values in site_load.items() for value in values
            )
            status = (
                "PASS"
                if initial_mismatch == aggregate_error == site_violations == rack_failures == 0
                else "FAIL"
            )
            rw_days.append({
                "operating_day": day,
                "status": status,
                "initial_state_SHA256": result["initial_state_SHA256"],
                "post_freeze_replay_method": "CONSTRAINT_REPLAY_NO_SOLVER_CALL",
                "RUNNING_initial_AIDC_mismatch_count": int(initial_mismatch),
                "aggregate_GPU_max_error": int(aggregate_error),
                "site_capacity_violation_count": int(site_violations),
                "Rack_compatibility_failure_count": int(rack_failures),
                "gang_split_count": 0,
                "RW_schedule_mutation_count": 0,
                "migration_solver_calls": 0,
            })
            if status != "PASS":
                first_blocker = f"{day}:RW_REFERENCE_SPATIAL_RACK_REPLAY_FAILED"
                break
    rw_pass = sum(row["status"] == "PASS" for row in rw_days)
    correction_pass = len(initial_days) == rw_pass == 31
    fast_gate = {
        "artifact_id": "V39E_RW_31DAY_FAST_GATE_V1",
        "status": "PASS" if correction_pass else "FAIL_CLOSED",
        "initial_states_PASS": len(initial_days),
        "RW_REFERENCE_PASS": rw_pass,
        "expected_days": 31,
        "first_blocker": first_blocker,
        "migration_solver_calls_today": 0,
        "RSP_temporal_only_full_evaluation_calls": 0,
        "migration_escalation_MILP_calls": 0,
        "minimum_RUNNING_migration_optimum_calls": 0,
        "WAN_migration_witness_materialization_calls": 0,
        "DA_freeze_regeneration_count": 0,
        "power_PCC_regeneration_count": 0,
        "Fresh_restoration_campaign_calls": 0,
        "full_production_preflight_calls": 0,
        "May_campaign_calls": 0,
        "Rack_capacity_summed_as_site_capacity": False,
        "site_capacity_violations": sum(
            row["site_capacity_violation_count"] for row in rw_days
        ),
        "capacity_created_by_Rack_layer_GPU": 0,
        "V39E_INITIALIZATION_CORRECTION_PASS": "YES" if correction_pass else "NO",
        "FULL_V39E_PREFLIGHT_DEFERRED": "YES",
        "V39E_READY": "NOT_YET_EVALUATED",
        "MAY_CAMPAIGN_LAUNCH_READY": "NO",
        "MAY_STARTED": "NO",
        "days": rw_days,
    }
    atomic_json(root / "V39E_RW_31DAY_FAST_GATE.json", fast_gate)

    if sha256_file(repo / RACK_AUTHORITY_PATH) != authority_sha_before:
        raise RuntimeError("V39E_RACK_AUTHORITY_MUTATED")
    if sha256_file(capacity_path) != capacity_sha_before:
        raise RuntimeError("V39E_SITE_CAPACITY_MUTATED")
    summary = {
        "initial_states_PASS": len(initial_days),
        "RW_REFERENCE_PASS": rw_pass,
        "B0_B1_B2_B3_initial_SHA_identity": (
            "PASS" if common_audit["B0_B1_B2_B3_initial_SHA_identity"] else "FAIL"
        ),
        "inter_day_state_carry_count": 0,
        "cross_day_result_read_count": 0,
        "migration_solver_calls_today": 0,
        "first_blocker": first_blocker,
        "V39E_INITIALIZATION_CORRECTION_PASS": "YES" if correction_pass else "NO",
        "FULL_V39E_PREFLIGHT_DEFERRED": "YES",
        "V39E_READY": "NOT_YET_EVALUATED",
        "MAY_CAMPAIGN_LAUNCH_READY": "NO",
        "MAY_STARTED": "NO",
    }
    _write_review(root, summary)
    return summary


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    args = parser.parse_args()
    result = evaluate(args.repo)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["evaluate"]
