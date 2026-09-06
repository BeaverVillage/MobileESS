"""Independent full-population service conservation at D00 and H; no replay."""
from pathlib import Path
import sys
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
import numpy as np
import pandas as pd
from dayahead.paper_analysis.storage import read, reference, write_json, write_parquet


def main():
    root = REPO / "dayahead/artifacts/v40d_actual_realized_replay"
    smoke = root / "smoke/2025-05-01"
    out = root / "service_equivalence/2025-05-01"
    out.mkdir(parents=True, exist_ok=True)
    observed_path = root / "V40D_FROZEN_JOB_OBSERVATIONS.parquet"
    observations = pd.read_parquet(observed_path)
    observations["id"] = observations.id.astype(str)
    if observations.id.duplicated().any():
        raise RuntimeError("DUPLICATE_OBSERVED_UID")
    observations = observations.set_index("id")
    issue = pd.Timestamp("2025-04-30T18:00:00+10:00")
    D00, H = 6 * 3600, 30 * 3600
    cases, frames, sources = [], {}, {}
    for case in ("B0", "B1", "B2", "B3"):
        folder = smoke / case
        raw = pd.read_parquet(folder / "job_ledger.parquet")
        if raw.job_uid.duplicated().any():
            raise RuntimeError("DUPLICATE_CASE_UID")
        contributions = pd.read_parquet(folder / "job_GPU_contributions.parquet")
        if contributions.duplicated(["job_uid", "slot"]).any():
            raise RuntimeError("DUPLICATE_GPU_EXECUTION")
        slot_hours = contributions.groupby("job_uid").occupied_GPU.sum() * .25
        records = []
        pending_end_exact_checked = 0
        pending_start_shifted_from_history = 0
        for r in raw.to_dict("records"):
            uid = str(r["job_uid"])
            o = observations.loc[uid]
            os = (pd.Timestamp(o.start_time) - issue).total_seconds()
            oe = (pd.Timestamp(o.end_time) - issue).total_seconds()
            duration = oe - os
            gpu = int(r["requested_GPU"])
            if duration <= 0 or gpu != o.gpus_requested or duration != r["actual_runtime_seconds"]:
                raise RuntimeError("RUNTIME_GPU_AUTHORITY_MISMATCH:" + uid)
            status = r["status"]
            if status == "UNASSIGNED_POST_H_BACKLOG":
                if r["start_slot"] < 120 or pd.notna(r["actual_execution_start"]) or uid in slot_hours:
                    raise RuntimeError("UNASSIGNED_POSTH_EXECUTION")
                start = end = None
                pre = day = 0.0
                post = backlog = duration
                completed = False
                boundary00 = boundaryH = False
                start_delay = None
            else:
                if status == "PRE_DAY_COMPLETE":
                    start, end = os, oe
                    if end > D00 or uid in slot_hours:
                        raise RuntimeError("PRE_DAY_COMPLETE_LEAK")
                    start_delay = None
                elif status == "EXECUTION_ACCOUNTED":
                    start = os if r["state_at_issue"] == "RUNNING" else r["actual_residual_start"] * 900
                    end = start + duration
                    if abs(end - r["actual_execution_end"] * 900) > 1e-7:
                        raise RuntimeError("ASYMMETRIC_OR_TRUNCATED_END:" + uid)
                    if r["state_at_issue"] == "PENDING":
                        if r["actual_execution_start"] + duration / 900 != r["actual_execution_end"]:
                            raise RuntimeError("PENDING_END_NOT_EXACT_START_PLUS_RUNTIME:" + uid)
                        pending_end_exact_checked += 1
                        pending_start_shifted_from_history += int(start != os)
                    start_delay = float(r["start_delay_seconds"]) if r["state_at_issue"] == "PENDING" else None
                else:
                    raise RuntimeError("UNKNOWN_EXECUTION_STATE")
                pre = max(0., min(end, D00) - start) if start < D00 else 0.
                day = max(0., min(end, H) - max(start, D00))
                post = max(0., end - max(start, H))
                backlog = duration if start >= H else 0.
                completed = end <= H
                boundary00 = start < D00 < end
                boundaryH = start < H < end
                # Independently derive sampled occupancy from the full execution interval.
                expected_slots = sum(start <= t * 900 < end for t in range(24, 120))
                if gpu * expected_slots * .25 != slot_hours.get(uid, 0.):
                    raise RuntimeError("JOB_SLOT_OCCUPANCY_MISMATCH:" + uid)
            conservation = duration - pre - day - post
            if abs(conservation) > 1e-7 or abs(post * gpu / 3600 - r["remaining_GPU_hours_at_H"]) > 1e-7:
                raise RuntimeError("FULL_SERVICE_CONSERVATION:" + uid)
            if abs(backlog * gpu / 3600 - r.get("backlog_GPU_hours", 0.)) > 1e-7:
                raise RuntimeError("BACKLOG_CONSERVATION:" + uid)
            records.append({"job_uid": uid, "requested_GPU": gpu, "realized_runtime_seconds": duration,
                            "state_at_issue": r["state_at_issue"], "status": status,
                            "frozen_start_slot": int(r["start_slot"]),
                            "actual_start_issue_relative_seconds": start, "actual_end_issue_relative_seconds": end,
                            "actual_start": None if start is None else (issue + pd.Timedelta(seconds=start)).isoformat(),
                            "actual_end": None if end is None else (issue + pd.Timedelta(seconds=end)).isoformat(),
                            "pre_D00_GPU_hours": pre * gpu / 3600,
                            "Dday_GPU_hours": day * gpu / 3600,
                            "Dday_GPU_slot_hours": float(slot_hours.get(uid, 0.)),
                            "postH_GPU_hours": post * gpu / 3600,
                            "backlog_GPU_hours_at_H": backlog * gpu / 3600,
                            "full_population_service_GPU_hours": duration * gpu / 3600,
                            "completed_by_H": completed, "unfinished_at_H": not completed,
                            "crosses_D00": boundary00, "crosses_H": boundaryH,
                            "actual_start_delay_seconds": start_delay,
                            "start_occurred_by_H": start is not None and start < H,
                            "service_conservation_error_seconds": conservation})
        frame = pd.DataFrame(records).sort_values("job_uid").reset_index(drop=True)
        frames[case] = frame
        x = pd.read_parquet(folder / "aidc_site_timeseries.parquet")
        pending_delays = frame.loc[frame.actual_start_delay_seconds.notna(), "actual_start_delay_seconds"]
        beforeHdelays = frame.loc[frame.actual_start_delay_seconds.notna() & frame.start_occurred_by_H, "actual_start_delay_seconds"]
        metrics = {"case": case, "job_count": len(frame),
                   "sum_realized_runtime_seconds": float(frame.realized_runtime_seconds.sum()),
                   **{k: float(frame[k].sum()) for k in ("full_population_service_GPU_hours", "pre_D00_GPU_hours", "Dday_GPU_hours", "Dday_GPU_slot_hours", "postH_GPU_hours", "backlog_GPU_hours_at_H")},
                   "completed_jobs_by_H": int(frame.completed_by_H.sum()), "unfinished_jobs_at_H": int(frame.unfinished_at_H.sum()),
                   "Dday_IT_energy_kWh": float(x.P_IT_kW.sum() * .25), "Dday_PCC_energy_kWh": float(x.P_PCC_kW.sum() * .25),
                   "actual_start_delay_mean_seconds_assigned_pending_including_postH": float(pending_delays.mean()),
                   "actual_start_delay_max_seconds_assigned_pending_including_postH": float(pending_delays.max()),
                   "actual_start_delay_denominator": len(pending_delays),
                   "actual_start_delay_mean_seconds_started_by_H": float(beforeHdelays.mean()),
                   "actual_start_delay_max_seconds_started_by_H": float(beforeHdelays.max()),
                   "actual_start_delay_started_by_H_denominator": len(beforeHdelays),
                   "crosses_D00_job_count": int(frame.crosses_D00.sum()), "crosses_H_job_count": int(frame.crosses_H.sum()),
                   "boundary_crossing_unique_job_count": int((frame.crosses_D00 | frame.crosses_H).sum()),
                   "never_started_postH_backlog_job_count": int(frame.status.eq("UNASSIGNED_POST_H_BACKLOG").sum()),
                   "PENDING_end_exact_identity_checked_count": pending_end_exact_checked,
                   "PENDING_shifted_start_from_historical_count": pending_start_shifted_from_history,
                   "PENDING_end_exact_identity_failure_count": 0,
                   "service_conservation_max_error_seconds": float(frame.service_conservation_error_seconds.abs().max())}
        cases.append(metrics)
        write_parquet(out / (case + "_SERVICE_PARTITION.parquet"), frame)
        sources[case] = [reference(folder / name) for name in ("job_ledger.parquet", "job_GPU_contributions.parquet", "aidc_site_timeseries.parquet")]
    a, b = frames["B0"].set_index("job_uid"), frames["B1"].set_index("job_uid")
    identity = {key: a[key].equals(b[key]) for key in ("requested_GPU", "realized_runtime_seconds")}
    if not a.index.equals(b.index) or not all(identity.values()):
        raise RuntimeError("CASE_SPECIFIC_SERVICE")
    paired = a[["requested_GPU", "realized_runtime_seconds"]].copy()
    for c, f in (("B0", a), ("B1", b)):
        for key in ("status", "frozen_start_slot", "actual_start", "actual_end", "pre_D00_GPU_hours", "Dday_GPU_hours", "Dday_GPU_slot_hours", "postH_GPU_hours", "backlog_GPU_hours_at_H"):
            paired[c + "_" + key] = f[key]
    paired["Delta_Dday_GPU_h"] = b.Dday_GPU_hours - a.Dday_GPU_hours
    paired["Delta_pre_D00_GPU_h"] = b.pre_D00_GPU_hours - a.pre_D00_GPU_hours
    paired["Delta_postH_GPU_h"] = b.postH_GPU_hours - a.postH_GPU_hours
    paired["delta_partition_balance_GPU_h"] = paired.Delta_Dday_GPU_h + paired.Delta_pre_D00_GPU_h + paired.Delta_postH_GPU_h
    write_parquet(out / "B0_B1_PAIRED_JOB_LEDGER.parquet", paired.reset_index())
    paired.reset_index().to_csv(out / "B0_B1_PAIRED_JOB_LEDGER.csv", index=False, encoding="utf-8-sig", float_format="%.15g")
    deltas = {k: float(paired[k].sum()) for k in ("Delta_Dday_GPU_h", "Delta_pre_D00_GPU_h", "Delta_postH_GPU_h", "delta_partition_balance_GPU_h")}
    deltas["Delta_Dday_GPU_slot_h"] = cases[1]["Dday_GPU_slot_hours"] - cases[0]["Dday_GPU_slot_hours"]
    deltas["Delta_slot_minus_exact_GPU_h"] = deltas["Delta_Dday_GPU_slot_h"] - deltas["Delta_Dday_GPU_h"]
    result = {"ACTUAL_SERVICE_EQUIVALENCE": "PASS", "same_job_uid_population": True,
              "same_realized_runtime_each_job": identity["realized_runtime_seconds"], "same_requested_GPU_each_job": identity["requested_GPU"],
              "duplicated_execution_count": 0, "missing_service_accounting_count": 0,
              "case_specific_runtime_count": 0, "asymmetric_clipping_count": 0,
              "historical_absolute_end_combined_with_shifted_start_count": 0,
              "cases": cases, "deltas_B1_minus_B0": deltas,
              "boundary_convention": "Half-open [D00,H); full service also includes observed pre-issue RUNNING history. Unstarted UNASSIGNED post-H service stays in remaining/backlog; no site or execution time is invented.",
              "GPU_hours_definition": "Exact execution seconds times requested GPU / 3600. GPU_slot_hours separately uses 15-minute sampled occupancy and drives frozen power.",
              "backlog_is_subset_of_postH_remaining_do_not_add_twice": True,
              "classification_service_axis": "C. HORIZON_BOUNDARY_REDISTRIBUTION",
              "overall_classification_requires_power_scale_and_same_exogenous_audit": True,
              "scientific_performance_interpretation_authorized": False, "full_campaign_authorized": False,
              "sources": sources, "observations": reference(observed_path)}
    write_json(out / "V40D_ACTUAL_SERVICE_EQUIVALENCE_AUDIT.json", result)
    print({"ACTUAL_SERVICE_EQUIVALENCE": result["ACTUAL_SERVICE_EQUIVALENCE"], "cases": cases[:2], "deltas": deltas}, flush=True)


if __name__ == "__main__":
    main()
