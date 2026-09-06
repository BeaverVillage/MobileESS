from pathlib import Path
import json

import numpy as np
import pandas as pd

from dayahead.tools.run_v39f_day17_diagnostic import (
    OUT, DAYS, DAY, backlog, interval_difference, profile, shift_band,
)


def test_shorter_reservation_is_not_relocated_work() -> None:
    # Same start, shorter reservation: removed capacity has no destination.
    assert interval_difference(63, 48, 63, 25, 1) == (23, 0)
    # Equal-duration advance: relocation conserves the shifted service.
    assert interval_difference(64, 25, 63, 25, 1) == (1, 1)


def test_slot82_decomposition_requires_issue_offset() -> None:
    a = pd.read_parquet(DAYS / DAY / "V37_R4A_JOB_LEDGER.parquet")
    rw = profile(a, "RW_scheduled_start", "RW_duration_slots")
    duration_only = profile(a, "RW_scheduled_start", "RSP_duration_slots")
    rsp = profile(a, "RSP_scheduled_start", "RSP_duration_slots")
    assert (rw[82], duration_only[82], rsp[82]) == (471, 90, 90)
    assert rw[82] - duration_only[82] == 381
    assert duration_only[82] - rsp[82] == 0


def test_exact_job_cohort_conservation() -> None:
    data = json.loads((OUT / "V39F_DAY17_SLOT82_SHIFT_DECOMPOSITION.json").read_text(encoding="utf-8"))
    jobs = [uid for cohort in data["cohorts"] for uid in cohort["job_uids"]]
    assert len(jobs) == len(set(jobs)) == 380
    assert sum(c["GPU_removed"] for c in data["cohorts"]) == 381
    assert data["conservation"]["gross_added_GPU"] == 0


def test_pending_backlog_is_not_unfinished_running_reservation() -> None:
    a = pd.read_parquet(DAYS / DAY / "V37_R4A_JOB_LEDGER.parquet")
    assert backlog(a, "RW")["terminal_pending_GPU_hours"] == 0
    assert backlog(a, "RSP")["terminal_pending_GPU_hours"] == 0
    assert backlog(a, "RW")["terminal_unfinished_reservation_GPU_hours"] == 8311
    assert backlog(a, "RSP")["terminal_unfinished_reservation_GPU_hours"] == 8233.75


def test_absolute_shift_does_not_mean_positive_deferral() -> None:
    a = pd.read_parquet(DAYS / DAY / "V37_R4A_JOB_LEDGER.parquet")
    delta = a.RSP_scheduled_start - a.RW_scheduled_start
    assert int((delta > 0).sum()) == 0
    assert int((delta < 0).sum()) == 2
    assert int(np.abs(delta).max() * 15) == 945
    assert shift_band(30) == "<=30 min"
    assert shift_band(60) == "30-60 min"
    assert shift_band(480) == "4-8 h"
    assert shift_band(495) == ">8 h"


def test_undefined_shadow_is_not_faked_as_feasible_or_infeasible() -> None:
    obj = json.loads((OUT / "V39F_DAY17_RSP_OBJECTIVE_AUDIT.json").read_text(encoding="utf-8"))
    shadow = json.loads((OUT / "V39F_DAY17_SHADOW_GRID_AWARE_TEMPORAL_ONLY.json").read_text(encoding="utf-8"))
    assert obj["scalar_objective_exists"] is False
    assert obj["RSP_objective"] is None
    assert shadow["solver_called"] is False
    assert shadow["feasible"] is None
    assert pd.read_parquet(OUT / "V39F_DAY17_SHADOW_GRID_AWARE_TEMPORAL_SCHEDULE.parquet").empty


def test_month_audit_preserves_sign_and_population() -> None:
    a = pd.read_csv(OUT / "V39F_MAY31_TEMPORAL_FLEXIBILITY_REALISM_AUDIT.csv")
    assert len(a) == 31
    assert int(a.jobs.sum()) == 47009
    assert int(a.delayed_jobs.sum()) == 46
    assert int(a.advanced_jobs.sum()) == 35694
    assert (a.shifted_jobs == a.delayed_jobs + a.advanced_jobs).all()
    late = pd.read_csv(OUT / "V39F_MAY31_POSITIVE_DEFERRAL_JOBS.csv")
    assert len(late) == 46
    assert int((late.positive_deferral_minutes > 480).sum()) == 2


def test_frozen_rsp_voltage_reproduced_without_temporal_change() -> None:
    a = json.loads((OUT / "V39F_DAY17_FROZEN_RSP_SITE_ONLY_DIAGNOSTIC.json").read_text(encoding="utf-8"))
    assert a["placement_has_no_temporal_changes"] is True
    assert a["Threads"] == 4
    assert a["voltage"]["voltage_violation_count"] == 4
    assert abs(a["voltage"]["Vmax_pu"] - 1.051067054291103) < 1e-12
