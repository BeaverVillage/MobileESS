"""Actual-side fixed replay and deterministic intra-AIDC Rack assignment."""

from __future__ import annotations

from typing import Any, Iterable, Mapping

import numpy as np

from dayahead.v38.authority import CapacityAuthority, canonical_sha256

from .contracts import SLOTS


def deterministic_rack_assignment(
    assignments: Iterable[Mapping[str, Any]],
    capacity: CapacityAuthority,
) -> dict[str, Any]:
    """Use stable Rack-ID first-fit without changing a frozen site or time.

    Failure is explicit.  There is intentionally no alternate-site, time-shift,
    migration, or WAN fallback.
    """

    rows = [dict(row) for row in assignments]
    load = {
        pool.rack_pool_id: np.zeros(SLOTS, dtype=np.int64)
        for pool in capacity.rack_pools
    }
    pool_by_id = {pool.rack_pool_id: pool for pool in capacity.rack_pools}
    output: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    ordered = sorted(
        rows,
        key=lambda row: (
            int(row["active_start_slot"]), str(row["job_uid"]),
        ),
    )
    for row in ordered:
        site = str(row["destination_AIDC"])
        gpu = int(row["requested_GPU"])
        start = int(row["active_start_slot"])
        end = int(row["active_end_slot"])
        candidates = sorted(
            pool.rack_pool_id for pool in capacity.eligible_racks(site, gpu)
        )
        selected = next((
            rack for rack in candidates
            if np.all(
                load[rack][start:end] + gpu
                <= pool_by_id[rack].historical_gpu_capacity + 1e-9
            )
        ), None)
        if selected is None:
            failures.append({
                "job_uid": str(row["job_uid"]),
                "frozen_AIDC": site,
                "frozen_start_slot": start,
                "frozen_end_slot": end,
                "requested_GPU": gpu,
                "reason": "NO_COMPATIBLE_RACK_UNDER_STABLE_FIRST_FIT",
                "alternate_AIDC_attempted": False,
                "time_shift_attempted": False,
            })
            continue
        load[selected][start:end] += gpu
        output.append({
            "job_uid": str(row["job_uid"]),
            "destination_AIDC": site,
            "rack_pool_id": selected,
            "requested_GPU": gpu,
            "active_start_slot": start,
            "active_end_slot": end,
            "assignment_method": "STABLE_RACK_ID_FIRST_FIT",
        })
    return {
        "status": "PASS" if not failures else "FAIL_CLOSED",
        "method": "DETERMINISTIC_FEASIBLE_RACK_ASSIGNMENT_STABLE_RACK_ID_FIRST_FIT",
        "assignments": output,
        "assignment_SHA256": canonical_sha256(output),
        "failures": failures,
        "failure_count": len(failures),
        "DA_selected_AIDC_mutation_count": 0,
        "DA_selected_time_mutation_count": 0,
        "fallback_AIDC_reoptimization_calls": 0,
        "fallback_temporal_reoptimization_calls": 0,
    }


def validate_actual_fixed_replay(
    freeze_payload: Mapping[str, Any], expected_sha: str,
) -> dict[str, Any]:
    decision = dict(freeze_payload["decision"])
    actual = canonical_sha256(decision)
    if actual != expected_sha:
        raise RuntimeError("V39D_DA_FREEZE_SHA_MISMATCH")
    return {
        "status": "PASS",
        "DA_decision_SHA_expected": expected_sha,
        "DA_decision_SHA_verified": actual,
        "Actual_temporal_reoptimization_calls": 0,
        "Actual_AIDC_reoptimization_calls": 0,
        "Actual_migration_reoptimization_calls": 0,
        "Actual_WAN_rerouting_calls": 0,
        "Actual_realized_inputs_used_to_change_DA_decisions": 0,
    }


__all__ = ["deterministic_rack_assignment", "validate_actual_fixed_replay"]

