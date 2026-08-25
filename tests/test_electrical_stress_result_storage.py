import json
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from pfr.result_storage import (
    CAMPAIGN_REQUIRED_COLUMNS,
    EVENT_REQUIRED_COLUMNS,
    ISSUE_REQUIRED_COLUMNS,
    JOB_REQUIRED_COLUMNS,
    MESS_REQUIRED_COLUMNS,
    materialize_campaign_summary,
    materialize_method_results,
    materialize_period_summary,
)


def _record(issue: int = 0) -> dict:
    return {
        "issue": issue,
        "comparison_method_id": "B09",
        "method_order": 9,
        "objective_id": "ELECTRICAL_STRESS_OBJECTIVE_V1",
        "plan_id": "B09-0-1",
        "replan_id": 1,
        "plan_origin_issue": 0,
        "plan_age_steps": issue,
        "predicted_worst_electrical_stress_pu": 0.82,
        "predicted_electrical_stress_exposure_pu_hours": 1.1,
        "predicted_voltage_stress_max": 0.61,
        "predicted_line_stress_max": 0.82,
        "predicted_transformer_stress_max": 0.74,
        "predicted_worst_stress_type": "LINE",
        "predicted_worst_element_id": "n1->n2",
        "predicted_worst_phase": None,
        "status": "PASS_COMMITTED",
        "commit_marker": True,
        "full_replan_executed": True,
        "replan_causes": ("OPPORTUNITY",),
        "risk_raw_components": {"R_SOC": 0.2, "R_voltage": 0.4},
        "risk_calibrated_components": {"R_SOC": 0.1, "R_voltage": 0.3},
        "active_jobs": 0,
        "queued_jobs": 0,
        "completed_jobs": 0,
        "deadline_misses": 0,
        "remaining_work_gpu_hours": 0.0,
        "compute_debt_gpu_hours": 0.0,
        "energy_debt_kwh": 0.0,
        "terminal_recovery_feasible": True,
        "facility_p_kw_total": 100.0,
        "mess_p_kw_total": 10.0,
        "price_aud_per_mwh": 80.0,
        "realized_grid_cost_aud": 1.0,
        "cumulative_grid_cost_aud": 1.0 + issue,
        "slow_solver_time_s": 2.0,
        "fast_recourse_runtime_seconds": 0.2,
        "safety_filter_runtime_seconds": 0.1,
        "runtime_seconds": 2.4,
        "communication_bytes_cumulative": 123,
        "safety_filter_intervention": False,
        "safety_filter_stage": "NONE",
        "safety_filter_escalation_count": 0,
        "safety_action_delta_norm": 0.0,
        "attempt_id": "attempt-1",
        "parent_attempt_id": None,
        "retry_count": 0,
        "mess_energy_kwh": {"MESS01": 900.0},
        "mess_location": {"MESS01": "S01"},
        "mess_in_transit": {"MESS01": False},
        "mess_route_destination": {"MESS01": None},
        "mess_route_rank": {"MESS01": None},
        "mobility_started_events": (),
        "mobility_completed": {"MESS01": False},
        "planned_control": {
            "mess_charge_kw": {"MESS01": 0.0},
            "mess_discharge_kw": {"MESS01": 10.0},
            "mess_q_kvar": {"MESS01": 2.0},
            "job_compute_rate_fraction": {},
        },
        "accepted_control": {
            "mess_charge_kw": {"MESS01": 0.0},
            "mess_discharge_kw": {"MESS01": 9.0},
            "mess_q_kvar": {"MESS01": 1.5},
            "job_compute_rate_fraction": {},
        },
        "job_states": {},
        "wan_transferred_bytes_cumulative": 0,
        "wan_bytes_transferred_step": 0,
        "realized_exact_electrical_stress": {
            "worst_electrical_stress_pu": 0.84,
            "voltage_stress_pu": 0.60,
            "line_stress_pu": 0.84,
            "transformer_stress_pu": 0.72,
        },
        "exact_ac": {
            "timestamp_utc_ns": 1735689600000000000 + issue * 300_000_000_000,
            "voltage_min_pu": 0.97,
            "voltage_max_pu": 1.01,
            "voltage_min_bus_node": "b1.1",
            "voltage_max_bus_node": "b2.2",
            "voltage_min_phase": 1,
            "voltage_max_phase": 2,
            "voltage_violation_count": 0,
            "line_max_loading_pu": 0.84,
            "line_max_loading_name": "L12",
            "line_max_current_a": 120.0,
            "line_max_phase": 2,
            "line_violation_count": 0,
            "transformer_max_current_loading_pu": 0.72,
            "transformer_max_current_loading_name": "T1",
            "transformer_max_current_a": 80.0,
            "transformer_max_kva_loading_pu": 0.70,
            "transformer_max_kva_loading_name": "T1",
            "transformer_max_kva": 350.0,
            "transformer_max_phase": 1,
            "transformer_current_violation_count": 0,
            "transformer_kva_violation_count": 0,
            "root_import_p_kw": 1200.0,
            "root_export_p_kw": 0.0,
            "hard_constraint_pass": True,
        },
    }


class ElectricalStressResultStorageTests(unittest.TestCase):
    def test_method_tables_are_written_and_read_back_with_empty_job_schema(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw) / "B09"
            root.mkdir()
            materialize_method_results(root, [_record(0), _record(1)], {})
            expected = {
                "ISSUE_RESULT.parquet": (2, ISSUE_REQUIRED_COLUMNS),
                "MESS_TRAJECTORY.parquet": (2, MESS_REQUIRED_COLUMNS),
                "JOB_WAN_TRAJECTORY.parquet": (0, JOB_REQUIRED_COLUMNS),
                "EVENT_CONTROL_LOG.parquet": (2, EVENT_REQUIRED_COLUMNS),
            }
            for filename, (rows, columns) in expected.items():
                with self.subTest(filename=filename):
                    frame = pd.read_parquet(root / filename)
                    self.assertEqual(len(frame), rows)
                    self.assertTrue(set(columns).issubset(frame.columns))
            issue = pd.read_parquet(root / "ISSUE_RESULT.parquet")
            self.assertEqual(issue["predicted_worst_stress_z"].tolist(), [0.82, 0.82])
            self.assertEqual(issue["ac_worst_stress_z"].tolist(), [0.84, 0.84])
            audit = json.loads((root / "RESULT_STORAGE_AUDIT.json").read_text())
            self.assertEqual(audit["status"], "PASS")

    def test_job_table_persists_prestart_wan_progress_by_job(self):
        record = _record(0)
        record["job_states"] = {
            "job-1": {
                "lifecycle": "QUEUED",
                "arrival_issue": 0,
                "deadline_issue": 20,
                "remaining_work_gpu_hours": 2.0,
                "required_gpu": 4,
                "origin_idc": "IDC01",
                "destination_idc": "IDC02",
                "planned_idc": "IDC02",
                "planned_start_issue": 3,
                "compute_rate_fraction": 0.0,
                "checkpoint_state": "NOT_STARTED",
                "restart_remaining_steps": 0,
                "prestart_wan_target_idc": "IDC02",
                "prestart_wan_required_bytes": 8_000_000_000,
                "prestart_wan_transferred_bytes": 3_000_000_000,
            }
        }
        record["prestart_wan_bytes_transferred_step_by_job"] = {
            "job-1": 1_000_000_000
        }
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw) / "B09"
            root.mkdir()
            materialize_method_results(root, [record], {})
            jobs = pd.read_parquet(root / "JOB_WAN_TRAJECTORY.parquet")
            self.assertEqual(jobs["job_id"].tolist(), ["job-1"])
            self.assertEqual(jobs["prestart_wan_target_idc"].tolist(), ["IDC02"])
            self.assertEqual(jobs["prestart_wan_required_gb"].tolist(), [8.0])
            self.assertEqual(jobs["prestart_wan_transferred_gb"].tolist(), [3.0])
            self.assertEqual(jobs["prestart_wan_transfer_gb_step"].tolist(), [1.0])
            self.assertEqual(jobs["prestart_wan_data_ready"].tolist(), [False])

    def test_campaign_summary_is_exactly_ten_ordered_rows(self):
        summaries = []
        for index in range(10):
            method = f"B{index:02d}"
            summaries.append({
                "comparison_method_id": method,
                "status": "PASS",
                "factorial_energy": {"B00": 0, "B01": 1, "B04": 0, "B06": 1}.get(method),
                "factorial_compute": {"B00": 0, "B01": 0, "B04": 1, "B06": 1}.get(method),
                "realized_exact_electrical_stress": {
                    "worst_electrical_stress_pu": 0.9,
                    "electrical_stress_exposure_pu_hours": 2.0,
                },
                "daily_peak_root_import_kw": 1000.0,
                "deadline_miss_count": 0,
                "mobility_started_route_count": 0,
                "migration_count": 0,
                "full_replan_count": 1,
                "grid_cost_aud": 20.0,
                "solver_time_p95_s": 1.0,
            })
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            materialize_campaign_summary(root, summaries)
            frame = pd.read_parquet(root / "CAMPAIGN_SUMMARY.parquet")
            self.assertEqual(frame["method_id"].tolist(), [f"B{i:02d}" for i in range(10)])
            self.assertEqual(len(frame), 10)
            self.assertTrue(set(CAMPAIGN_REQUIRED_COLUMNS).issubset(frame.columns))
            audit = json.loads((root / "CAMPAIGN_STORAGE_AUDIT.json").read_text())
            self.assertEqual(audit["status"], "PASS")

    def test_campaign_summary_rejects_missing_or_reordered_method(self):
        summaries = [
            {
                "comparison_method_id": method,
                "status": "PASS",
                "realized_exact_electrical_stress": {},
            }
            for method in (["B01", "B00"] + [f"B{i:02d}" for i in range(2, 10)])
        ]
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(RuntimeError, "method order mismatch"):
                materialize_campaign_summary(Path(raw), summaries)

    def test_period_summary_is_one_ordered_ten_row_campaign_table(self):
        dates = ("2025-03-01", "2025-03-02")
        methods = tuple(f"B{i:02d}" for i in range(10))
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            for day_index, calendar_date in enumerate(dates, start=1):
                for method_index, method in enumerate(methods):
                    method_root = root / calendar_date / method
                    method_root.mkdir(parents=True)
                    daily = {
                        "status": "PASS",
                        "factorial_energy": None,
                        "factorial_compute": None,
                        "daily_max_ac_stress": 0.8 + method_index / 100.0,
                        "daily_ac_stress_exposure": float(day_index),
                        "daily_max_voltage_stress": 0.7,
                        "daily_max_line_stress": 0.8,
                        "daily_max_transformer_stress": 0.6,
                        "daily_peak_root_import_kw": 1000.0 + day_index,
                        "daily_rebound_peak_kw": None,
                        "daily_rebound_energy_kwh": None,
                        "deadline_miss_count": 0,
                        "mess_move_count": 1,
                        "mobility_completed_count": 1,
                        "workload_temporal_shift_count": 2,
                        "workload_migration_count": 3,
                        "checkpoint_count": 4,
                        "wan_transfer_gb": 5.0,
                        "full_replan_count": 6,
                        "fast_recourse_count": 288,
                        "safety_filter_intervention_count": 0,
                        "communication_bytes": 100,
                        "grid_cost_aud": 20.0,
                    }
                    (method_root / "DAILY_SUMMARY.json").write_text(
                        json.dumps(daily), encoding="utf-8"
                    )
                    pd.DataFrame(
                        {
                            "slow_solver_time_s": [0.0, float(day_index)],
                            "total_control_time_s": [1.0, 2.0],
                        }
                    ).to_parquet(method_root / "ISSUE_RESULT.parquet", index=False)
            materialize_period_summary(
                root, calendar_dates=dates, method_ids=methods
            )
            result = pd.read_parquet(root / "CAMPAIGN_SUMMARY.parquet")
            self.assertEqual(result["method_id"].tolist(), list(methods))
            self.assertEqual(result["aggregation_scope"].unique().tolist(), ["PERIOD"])
            self.assertEqual(result["calendar_day_count"].unique().tolist(), [2])
            self.assertEqual(result.loc[0, "daily_ac_stress_exposure"], 3.0)
            self.assertEqual(result.loc[0, "grid_cost_aud"], 40.0)
            audit = json.loads((root / "PERIOD_SUMMARY_AUDIT.json").read_text())
            self.assertEqual(audit["status"], "PASS")


if __name__ == "__main__":
    unittest.main()
