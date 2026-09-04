from __future__ import annotations

import inspect
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from dayahead.v37 import aidc as aidc_module
from dayahead.v37 import manifest as manifest_module
from dayahead.v37 import sources as sources_module
from dayahead.v37.aidc import build_day, validate_cohort_contract
from dayahead.v37.aidc_materializer import (
    GPU_CAPACITY, Q_SELECTED_SECONDS, R4A_DAY_ROOT, R4A_ROOT, issue_time,
    snapshot_at_issue,
)
from dayahead.v37.contracts import EXPECTED_DATES, FIREWALL, PASS_ID
from dayahead.v37.preflight import validate_preflight_manifest


REPO = Path(__file__).resolve().parents[2]


def _manifest(day: str) -> dict:
    return json.loads((REPO / R4A_DAY_ROOT / day / "V37_R4A_DAY_MANIFEST.json").read_text(encoding="utf-8"))


def _ledger(day: str) -> pd.DataFrame:
    return pd.read_parquet(REPO / R4A_DAY_ROOT / day / "V37_R4A_JOB_LEDGER.parquet")


def test_apr01_exact_scheduler_reproduction() -> None:
    result = json.loads((REPO / R4A_ROOT / "V37_R4A_APR01_EXACT_REGRESSION.json").read_text(encoding="utf-8"))
    assert result["status"] == "PASS"
    assert all(result["checks"].values())


def test_apr01_accepted_census() -> None:
    result = json.loads((REPO / R4A_ROOT / "V37_R4A_APR01_EXACT_REGRESSION.json").read_text(encoding="utf-8"))
    assert result["evidence"] == {
        "temporal_jobs": 339,
        "temporal_requested_GPU_hours": 14832.0,
        "PARTIAL_shared_temporal_jobs": 336,
        "PARTIAL_shared_temporal_requested_GPU_hours": 14256.0,
    }


def test_may01_and_may02_have_independent_snapshots() -> None:
    first, second = _manifest("2025-05-01"), _manifest("2025-05-02")
    assert first["source_snapshot_sha256"] != second["source_snapshot_sha256"]
    assert first["D_minus_1_issue_time"] == issue_time("2025-05-01").isoformat()
    assert second["D_minus_1_issue_time"] == issue_time("2025-05-02").isoformat()


def test_may_production_source_has_no_apr01_helper_replay() -> None:
    source = inspect.getsource(aidc_module.build_day)
    assert "_apr01_power" not in source
    assert "_apr01_ledger" not in source


@pytest.mark.parametrize("day", ("2025-05-01", "2025-05-15", "2025-05-31"))
def test_running_requested_remaining_rule(day: str) -> None:
    running = _ledger(day).query("state_at_issue == 'RUNNING'")
    expected = np.maximum(
        running["requested_walltime_seconds"].to_numpy(float)
        - running["elapsed_seconds_at_issue"].to_numpy(float), 900.0,
    )
    assert np.array_equal(running["RSP_duration_seconds"].to_numpy(float), expected)
    assert running["duration_authority"].eq("REQUESTED_REMAINING").all()


@pytest.mark.parametrize("day", ("2025-05-01", "2025-05-15", "2025-05-31"))
def test_pending_safe_or_fail_closed_rule(day: str) -> None:
    pending = _ledger(day).query("state_at_issue == 'PENDING'")
    safe = pending["duration_authority"].eq("SAFE_CAUSAL_RUNTIME_PENDING")
    expected = np.minimum(
        pending.loc[safe, "requested_walltime_seconds"].to_numpy(float),
        np.maximum(
            pending.loc[safe, "diagnostic_point_total_seconds"].to_numpy(float) + Q_SELECTED_SECONDS,
            900.0,
        ),
    )
    assert np.allclose(pending.loc[safe, "RSP_duration_seconds"], expected, rtol=0, atol=1e-12)
    fallback = ~safe
    assert np.array_equal(
        pending.loc[fallback, "RSP_duration_seconds"].to_numpy(float),
        pending.loc[fallback, "requested_walltime_seconds"].to_numpy(float),
    )


def test_unknown_gpu_fail_closed_exclusions_are_preserved() -> None:
    exclusions = pd.read_parquet(REPO / R4A_DAY_ROOT / "2025-05-06" / "V37_R4A_EXCLUSIONS.parquet")
    assert set(exclusions["reason"]).issubset({"UNKNOWN_GPU_REQUEST", "INVALID_RESOURCE_REQUEST"})
    assert _manifest("2025-05-01")["cohort_census"]["unknown_GPU_request_exclusions"] >= 0


def test_partial_shared_rule() -> None:
    ledger = _ledger("2025-05-01")
    assert np.array_equal(
        ledger["PARTIAL_shared"].to_numpy(bool),
        (ledger["requested_gpus"] < 4 * ledger["requested_nodes"]).to_numpy(bool),
    )


@pytest.mark.parametrize("day", EXPECTED_DATES)
def test_gpu_capacity_and_day_ready(day: str) -> None:
    trajectory = pd.read_parquet(REPO / R4A_DAY_ROOT / day / "V37_R4A_GPU_IT_TRAJECTORY.parquet")
    assert len(trajectory) == 96
    assert trajectory[["N_active_RW", "N_active_RSP"]].to_numpy(float).min() >= 0
    assert trajectory[["N_active_RW", "N_active_RSP"]].to_numpy(float).max() <= GPU_CAPACITY
    assert _manifest(day)["status"] == "READY"


def test_no_shared_per_job_electrical_power_attribution() -> None:
    ledger = _ledger("2025-05-01")
    assert not ({"PCC_P_kW", "PCC_Q_kvar", "per_job_power_kW"} & set(ledger.columns))


@pytest.mark.parametrize("day", ("2025-05-01", "2025-05-02"))
def test_b0_b2_and_b1_b3_identity(day: str) -> None:
    b0, b2 = build_day(REPO, day, "B0"), build_day(REPO, day, "B2")
    b1, b3 = build_day(REPO, day, "B1"), build_day(REPO, day, "B3")
    assert np.array_equal(b0.pcc_p_kw, b2.pcc_p_kw)
    assert np.array_equal(b1.pcc_p_kw, b3.pcc_p_kw)
    assert validate_cohort_contract(b1.ledger, day)["rule_validation"] == "PASS"


def test_weather_and_c1_trajectories_are_day_specific() -> None:
    assert _manifest("2025-05-01")["C1_PCC_P_trajectory_sha256"] != _manifest("2025-05-02")["C1_PCC_P_trajectory_sha256"]


def test_causality_firewall() -> None:
    audit = json.loads((REPO / R4A_ROOT / "V37_R4A_AIDC_CAUSALITY_AUDIT.json").read_text(encoding="utf-8"))
    assert audit["future_runtime_labels_used"] is False
    assert audit["Actual_grid_or_PV_used"] is False
    assert audit["May_optimization_results_used"] is False


def test_old_template_checkpoint_namespace_is_invalidated() -> None:
    assert PASS_ID == "MAY_2025_R4A_PER_DAY_FINAL"
    assert PASS_ID != "MAY_2025_LOCKED_FINAL"


def test_all_31_days_preflight_pass() -> None:
    payload = json.loads((REPO / R4A_ROOT / "V37_R4A_MAY_AIDC_31DAY_PREFLIGHT.json").read_text(encoding="utf-8"))
    assert payload["status"] == "PASS"
    assert payload["ready_dates"] == 31
    assert payload["not_ready_dates"] == 0


def test_source_global_pass_requires_every_requested_day(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    days = ("2025-05-01", "2025-05-02")

    def aemo(_repo: Path, _days: tuple[str, ...]):
        root = sources_module.day_root(_repo, days[0])
        root.mkdir(parents=True, exist_ok=True)
        (root / "aemo_forecast.json").write_text("{}", encoding="utf-8")
        return ({days[-1]: "MISSING"}, {})

    def gfs(_repo: Path, *_args, **_kwargs):
        (sources_module.day_root(_repo, days[0]) / "gfs_d1_weather.parquet").write_bytes(b"gfs")
        return {}

    def kestrel(_repo: Path, *_args, **_kwargs):
        (sources_module.day_root(_repo, days[0]) / "kestrel_d1_scheduler_snapshot.parquet").write_bytes(b"kestrel")
        return {}, {}

    monkeypatch.setattr(sources_module, "_materialize_aemo", aemo)
    monkeypatch.setattr(sources_module, "_materialize_gfs", gfs)
    monkeypatch.setattr(sources_module, "_materialize_kestrel", kestrel)
    result = sources_module.materialize_sources(tmp_path, days)
    assert result["status"] == "FAIL"
    assert result["requested_count"] == 2
    assert result["runnable_count"] == 1
    assert result["failed_count"] == 1


def test_manifest_global_pass_requires_31_runnable_zero_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    eligibility = tmp_path / "eligibility.json"
    monkeypatch.setattr(manifest_module, "ELIGIBILITY", Path("eligibility.json"))
    monkeypatch.setattr(manifest_module, "build_may01_amendment", lambda _repo: {
        "May01_manifest_status": "RUNNABLE_CROSS_MONTH_CAUSAL_VINTAGE",
    })
    common = {"candidate_periods": {"MAY_PRIMARY": list(EXPECTED_DATES)}, "excluded": []}
    eligibility.write_text(json.dumps({
        **common,
        "included": [{"period": "MAY_PRIMARY", "operating_day": day} for day in EXPECTED_DATES],
    }), encoding="utf-8")
    passed = manifest_module.build_date_manifest(tmp_path)
    assert (passed["status"], passed["runnable_count"], passed["missing_count"]) == ("PASS", 31, 0)
    eligibility.write_text(json.dumps({
        **common,
        "included": [{"period": "MAY_PRIMARY", "operating_day": day} for day in EXPECTED_DATES[:-1]],
        "excluded": [{"period": "MAY_PRIMARY", "operating_day": EXPECTED_DATES[-1], "reasons": ["TEST"]}],
    }), encoding="utf-8")
    failed = manifest_module.build_date_manifest(tmp_path)
    assert (failed["status"], failed["runnable_count"], failed["missing_count"]) == ("FAIL", 30, 1)


def test_may01_snapshot_includes_april_origin_jobs() -> None:
    snapshot = pd.read_parquet(REPO / R4A_DAY_ROOT / "2025-05-01" / "V37_R4A_D1_SNAPSHOT.parquet")
    assert snapshot["source_member"].str.contains("year=2025/month=4/").any()
    audit = _manifest("2025-05-01")["Kestrel_D1_snapshot_audit"]
    assert audit["running_jobs_carried_across_month_boundary"] > 0
    assert audit["pending_jobs_carried_across_month_boundary"] > 0


def test_future_execution_does_not_define_d1_membership() -> None:
    frame = pd.DataFrame({
        "id": ["pending", "future-submit", "completed"],
        "submit_time": pd.to_datetime([
            "2025-04-30T00:00:00Z", "2025-04-30T12:00:00Z", "2025-04-29T00:00:00Z",
        ]),
        "start_time": pd.to_datetime([
            "2025-05-01T00:00:00Z", "2025-05-01T01:00:00Z", "2025-04-29T01:00:00Z",
        ]),
        "end_time": pd.to_datetime([
            "2025-05-01T02:00:00Z", "2025-05-01T03:00:00Z", "2025-04-29T02:00:00Z",
        ]),
        "source_member": ["april", "april", "april"],
    })
    frame.attrs["source_members_opened"] = ["april", "may"]
    snapshot = snapshot_at_issue(frame, "2025-05-01")
    assert snapshot["id"].tolist() == ["pending"]
    assert snapshot.iloc[0]["state_at_issue"] == "PENDING"
    assert "start_time" not in snapshot and "end_time" not in snapshot


def test_actual_traffic_authority_is_mandatory_and_placeholder_is_not_proof() -> None:
    source = inspect.getsource(__import__("dayahead.v37.preflight", fromlist=["production_loader_dry_run"]).production_loader_dry_run)
    assert "TRAFFIC_FORECAST.npz" in source
    assert "ROUTE_TABLE.json.gz" in source
    assert "traffic_mobility.json" not in source
    assert "structural_traffic_placeholder_accepted_as_readiness" in source


def test_no_stale_apr_template_provenance_or_universal_count_gate() -> None:
    stale = json.loads((REPO / R4A_ROOT / "V37_R4A_STALE_APR_TEMPLATE_REFERENCE_AUDIT.json").read_text(encoding="utf-8"))
    counts = json.loads((REPO / R4A_ROOT / "V37_R4A_APR01_CONSTANT_USAGE_AUDIT.json").read_text(encoding="utf-8"))
    assert stale["status"] == "PASS" and stale["production_hits"] == []
    assert counts["status"] == "PASS" and counts["universal_May_gate_hits"] == []


def test_per_day_aidc_fingerprint_is_complete_and_changes_cache_identity() -> None:
    first = build_day(REPO, "2025-05-01", "B1").fingerprints
    second = build_day(REPO, "2025-05-02", "B1").fingerprints
    required = {
        "operating_day", "source_snapshot_sha256", "ledger_sha256", "RW_schedule_sha256",
        "RSP_schedule_sha256", "RW_active_GPU_trajectory_sha256",
        "RSP_active_GPU_trajectory_sha256", "CENTER_IT_power_trajectory_sha256",
        "C1_PCC_P_trajectory_sha256", "C1_PCC_Q_trajectory_sha256",
        "runtime_authority_sha256",
    }
    assert set(first) == required
    assert first != second


def test_stale_readiness_without_r4a_gates_cannot_pass() -> None:
    stale = {
        "expected_dates": 31, "ready_dates": 31, "not_ready_dates": 0,
        "missing_dates": 0, "MAY_STARTED": "NO", "MAY_CAMPAIGN_LAUNCH_READY": "YES",
        "dates": [{"operating_day": day, "status": "READY"} for day in EXPECTED_DATES],
        "launch_fingerprints": [{"path": "old", "sha256": "a" * 64}],
    }
    failures = validate_preflight_manifest(stale)
    assert "PER_DAY_AIDC_NOT_31_OF_31" in failures
    assert "TRUE_PRODUCTION_LOADER_PREFLIGHT_NOT_31_OF_31" in failures


def test_fresh_role_semantics_distinguish_initial_decision_and_restoration() -> None:
    assert FIREWALL["Fresh_used_for_AIDC_or_MESS_initial_decisions"] == "NO"
    assert FIREWALL["Fresh_used_for_post_selection_AC_feasibility_detection"] == "YES"
    assert FIREWALL["Fresh_used_by_frozen_fixed_discrete_PQ_restoration"] == "YES"
    assert FIREWALL["Fresh_changes_MESS_destination_route_departure_or_move"] == "NO"
