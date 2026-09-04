"""Build reporting-only Apr-04 workload miss decomposition from frozen schedules."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from dayahead.v28r2.actual_replay import _mapping, _residuals
from dayahead.v28r2.reference_compute import CASE_CAPACITY_GPU
from dayahead.v28r2.workload_replay import materialize_actual_workload, replay_workload
from dayahead.v29r1.source_resume import write_csv
from dayahead.v29r2.anchor_forensic import OUT_REL
from dayahead.v29r2.apr04_runner import DAY, _actual_carryin


def main() -> None:
    repo = Path(__file__).resolve().parents[2]
    out = repo / OUT_REL
    review = json.loads((out / "V29R2_APR04_DEVELOPMENT_REVIEW.json").read_text(encoding="utf-8"))
    if review["RESULT_CLASSIFICATION"] != "V29R2_APR04_DEVELOPMENT_CHECKPOINT_PASS":
        raise RuntimeError("V29R2_WORKLOAD_REPORT_REQUIRES_PASS_REVIEW")
    actual = materialize_actual_workload(repo, DAY)
    initial, _service = _actual_carryin(repo, actual.cohort_ids)
    _rack_ids, _rack_aidc, _power_weights, gpu_weights = _mapping(repo)
    _p_res, g_res = _residuals(actual, _power_weights, gpu_weights)
    rack_gpu_capacity = CASE_CAPACITY_GPU * gpu_weights
    capacity = np.maximum(0.0, (rack_gpu_capacity[None, :] - g_res) * .25 / 4.0)
    rows = []
    for case in ("B0", "B1", "B2", "B3"):
        schedule = json.loads((out / f"V29R2_APR04_DAYAHEAD_{case}_SCHEDULE.json").read_text(encoding="utf-8"))
        da = np.asarray(schedule["workload_service_tensor"], dtype=float)
        unlimited = np.full((96, 48), float(da.sum() + initial.sum() + actual.arrivals_nodeh.sum() + 1.0))
        source_only = replay_workload(da, actual.arrivals_nodeh, unlimited, initial)
        realized = replay_workload(da, actual.arrivals_nodeh, capacity, initial)
        planned = float(da.sum())
        executed = float(realized.executed_nodeh.sum())
        source_executable = float(source_only.executed_nodeh.sum())
        source_miss = planned - source_executable
        rack_miss = source_executable - executed
        total_miss = planned - executed
        identity_error = total_miss - source_miss - rack_miss
        if min(source_miss, rack_miss, total_miss) < -1e-8 or abs(identity_error) > 1e-8:
            raise RuntimeError(f"V29R2_WORKLOAD_MISS_DECOMPOSITION:{case}")
        rows.append({
            "day": DAY,
            "case": case,
            "planned_workload_nodeh": planned,
            "executed_workload_nodeh": executed,
            "missed_workload_nodeh": total_miss,
            "source_availability_miss_nodeh": source_miss,
            "rack_capacity_miss_nodeh": rack_miss,
            "terminal_backlog_nodeh": float(realized.backlog_nodeh[-1].sum()),
            "decomposition_identity_error_nodeh": identity_error,
            "decomposition_order": "source availability counterfactual first; incremental rack-capacity loss second",
            "actual_optimizer_calls": 0,
        })
    write_csv(out / "V29R2_APR04_WORKLOAD_DECOMPOSITION.csv", rows)
    print(json.dumps({"status": "PASS", "case_count": len(rows), "B3": rows[-1]}))


if __name__ == "__main__":
    main()
