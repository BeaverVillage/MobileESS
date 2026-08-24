import tempfile
from pathlib import Path
import unittest

from pfr.migration import load_migration_authority
from pfr.methods import ComparisonMethod, ExperimentAuthority, MethodFactory
from pfr.power import H100UtilizationPowerCurve
from pfr.optimization import FastOptimizationCertificate, OptimizedFastControl
from pfr.runtime import (
    CausalExperimentFrame,
    OperationalTrainingJob,
    PhysicalCommit,
    PfrRuntimeRunner,
    RuntimeContractError,
    RuntimeInitialState,
    NativeGridControlDecision,
)
from pfr.safety import ExactAcResult
from pfr.slow_fast import FastControl


class FakePhysical:
    def __init__(self):
        self.calls = 0

    def verify_fresh(self, **kwargs):
        self.calls += 1
        raw = {
            "root_import_p_kw": 100.0,
            "voltage_min_pu": 0.98,
            "voltage_max_pu": 1.02,
            "line_max_loading_pu": 0.5,
            "transformer_max_kva_loading_pu": 0.5,
            "transformer_max_current_loading_pu": 0.5,
            "hard_constraint_pass": True,
        }
        return PhysicalCommit(
            ExactAcResult(True, "PASS", True, True, 0.98, 1.02, 0.5, 0.5, 0),
            raw,
            False,
            True,
        )


class NativeControlPhysical(FakePhysical):
    def __init__(self):
        super().__init__()
        self.selected = 0
        self.verified_states = []

    def select_native_control(self, **kwargs):
        self.selected += 1
        return NativeGridControlDecision(
            {"c83": (0,)},
            {"status": "TEST_COMMON_NATIVE_TRANSITION"},
            True,
            True,
        )

    def verify_fresh(self, **kwargs):
        self.verified_states.append(dict(kwargs["native_capacitor_states"]))
        return super().verify_fresh(**kwargs)


class MessOnlyRescuePhysical(FakePhysical):
    def __init__(self):
        super().__init__()
        self.mess_controls = []

    def verify_fresh(self, **kwargs):
        self.calls += 1
        controls = tuple(kwargs["mess_p_kw"]) + tuple(kwargs["mess_q_kvar"])
        self.mess_controls.append(controls)
        rescued = any(abs(float(value)) > 1e-12 for value in controls)
        raw = {
            "root_import_p_kw": 100.0,
            "voltage_min_pu": 0.96 if rescued else 0.94,
            "voltage_max_pu": 1.02,
            "line_max_loading_pu": 0.5,
            "transformer_max_kva_loading_pu": 0.5,
            "transformer_max_current_loading_pu": 0.5,
            "hard_constraint_pass": rescued,
        }
        return PhysicalCommit(
            ExactAcResult(
                rescued,
                "PASS" if rescued else "VOLTAGE_LOW",
                True,
                True,
                raw["voltage_min_pu"],
                1.02,
                0.5,
                0.5,
                0 if rescued else 1,
            ),
            raw,
            False,
            True,
        )


class RaiseOncePhysical(FakePhysical):
    def verify_fresh(self, **kwargs):
        if self.calls == 0:
            self.calls += 1
            raise RuntimeError("synthetic B0 backend failure")
        return super().verify_fresh(**kwargs)


class RaiseAfterOneCommittedIssuePhysical(FakePhysical):
    def __init__(self):
        super().__init__()
        self.raised = False

    def verify_fresh(self, **kwargs):
        if self.calls == 2 and not self.raised:
            self.raised = True
            raise RuntimeError("synthetic failure after one committed issue")
        return super().verify_fresh(**kwargs)


class UnauthorizedComputeModulatingOptimizer:
    def optimize(self, *, nominal, state, limits, context):
        return OptimizedFastControl(
            FastControl(
                dict(nominal.mess_charge_kw),
                dict(nominal.mess_discharge_kw),
                dict(nominal.mess_q_kvar),
                {uid: 0.0 for uid in nominal.job_compute_rate_fraction},
                dict(nominal.site_throughput_fraction),
            ),
            FastOptimizationCertificate(
                solver="SYNTHETIC_UNAUTHORIZED",
                status="SYNTHETIC",
                actual_gurobi_used=False,
                solution_count=1,
                objective_value=0.0,
                maximum_constraint_violation=0.0,
                runtime_seconds=0.0,
            ),
        )


class PfrRuntimeTests(unittest.TestCase):
    def setUp(self):
        hashes = [format(index, "064x") for index in range(1, 8)]
        self.configs = MethodFactory(ExperimentAuthority(*hashes)).all()
        self.curve = H100UtilizationPowerCurve((0.0, 1.0), (0.1, 0.65), "a" * 64, ("b" * 64,))
        self.initial = RuntimeInitialState(
            100, "c" * 64,
            {f"MESS{i:02d}": 760.0 for i in range(1, 5)},
            {f"MESS{i:02d}": f"STA{i:02d}" for i in range(1, 5)},
        )
        self.migration_authority = load_migration_authority(
            Path(__file__).parents[1]
            / "pfr/contracts/IDC_MIGRATION_AUTHORITY_V1.json"
        )
        job = OperationalTrainingJob(
            "j1", "IDC01", 100, 102, 110, 1, 3600, 0.01, None, "source-j1",
            self.migration_authority.checkpoint_payload_bytes(1),
            self.migration_authority.fingerprint,
        )
        self.frames = (
            CausalExperimentFrame(100, 100, 50, 1000, 100, (job,), "d" * 64),
            CausalExperimentFrame(101, 20, 50, 1000, 100, (), "e" * 64),
        )

    def test_b0_b7_matrix_commits_every_issue_with_fresh_exact_gate(self):
        physical = FakePhysical()
        with tempfile.TemporaryDirectory() as temporary:
            summary = PfrRuntimeRunner(
                power_curve=self.curve,
                physical_backend=physical,
                migration_authority=self.migration_authority,
            ).run_matrix(
                configs=self.configs, frames=self.frames, initial=self.initial,
                representative_week_id="TEST", output=Path(temporary),
            )
        self.assertEqual(summary["status"], "PASS")
        self.assertEqual(summary["valid_commit_markers"], 16)
        self.assertEqual(physical.calls, 32)
        self.assertTrue(summary["all_state_chains_complete"])

    def test_b8_replans_every_five_minute_issue(self):
        b8 = MethodFactory(
            ExperimentAuthority(*[format(index, "064x") for index in range(1, 8)])
        ).create(ComparisonMethod.B8)
        with tempfile.TemporaryDirectory() as temporary:
            summary = PfrRuntimeRunner(
                power_curve=self.curve,
                physical_backend=FakePhysical(),
                migration_authority=self.migration_authority,
            ).run_method(
                config=b8,
                frames=self.frames,
                initial=self.initial,
                representative_week_id="TEST_B8_PERIODIC_5MIN",
                output=Path(temporary),
            )
            rows = [
                __import__("json").loads(path.read_text(encoding="utf-8"))
                for path in sorted(
                    (Path(temporary) / "B8").glob("issue_*/COMMIT_MARKER.json")
                )
            ]
        self.assertEqual(summary["status"], "PASS")
        self.assertEqual(summary["full_replan_count"], len(self.frames))
        self.assertEqual(rows[0]["replan_causes"], ["INITIAL_PLAN"])
        self.assertEqual(
            rows[1]["replan_causes"], ["PERIODIC_5_MINUTE_REFRESH"]
        )

    def test_b0_late_arrival_is_admitted_without_full_replan(self):
        late_job = OperationalTrainingJob(
            "late-j1", "IDC01", 101, 103, 120, 1, 3600, 0.01, None,
            "source-late-j1", self.migration_authority.checkpoint_payload_bytes(1),
            self.migration_authority.fingerprint,
        )
        frames = (
            CausalExperimentFrame(100, 100, 50, 1000, 100, (), "d" * 64),
            CausalExperimentFrame(101, 100, 50, 1000, 100, (late_job,), "e" * 64),
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            summary = PfrRuntimeRunner(
                power_curve=self.curve,
                physical_backend=FakePhysical(),
                migration_authority=self.migration_authority,
            ).run_method(
                config=self.configs[0],
                frames=frames,
                initial=self.initial,
                representative_week_id="TEST_B0_LATE_ARRIVAL",
                output=root,
            )
            first = __import__("json").loads(
                (root / "B0/issue_000100/COMMIT_MARKER.json").read_text()
            )
            second = __import__("json").loads(
                (root / "B0/issue_000101/COMMIT_MARKER.json").read_text()
            )
        self.assertEqual(summary["status"], "PASS")
        self.assertEqual(summary["full_replan_count"], 1)
        self.assertEqual(summary["admission_plan_revision_count"], 1)
        self.assertEqual(first["facility_p_kw_total"], 0.0)
        self.assertGreater(second["facility_p_kw_total"], 0.0)
        self.assertEqual(second["active_jobs"], 1)
        self.assertTrue(second["admission_plan_revision_executed"])
        self.assertEqual(
            second["admission_plan_events"][0]["decision_authority"],
            "DETERMINISTIC_ORIGIN_ADMISSION_NO_OPTIMIZATION",
        )

    def test_late_arrival_is_executable_across_b0_b8(self):
        late_job = OperationalTrainingJob(
            "common-late-j1", "IDC01", 101, 103, 120, 1, 3600, 0.01,
            None, "source-common-late-j1",
            self.migration_authority.checkpoint_payload_bytes(1),
            self.migration_authority.fingerprint,
        )
        frames = (
            CausalExperimentFrame(100, 100, 50, 1000, 100, (), "d" * 64),
            CausalExperimentFrame(101, 100, 50, 1000, 100, (late_job,), "e" * 64),
        )
        b8 = MethodFactory(
            ExperimentAuthority(*[format(index, "064x") for index in range(1, 8)])
        ).create(ComparisonMethod.B8)
        for config in (*self.configs, b8):
            with self.subTest(method=config.comparison_method_id.value):
                with tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    summary = PfrRuntimeRunner(
                        power_curve=self.curve,
                        physical_backend=FakePhysical(),
                        migration_authority=self.migration_authority,
                    ).run_method(
                        config=config,
                        frames=frames,
                        initial=self.initial,
                        representative_week_id="TEST_COMMON_LATE_ARRIVAL",
                        output=root,
                    )
                    marker = __import__("json").loads(
                        (
                            root
                            / config.comparison_method_id.value
                            / "issue_000101/COMMIT_MARKER.json"
                        ).read_text()
                    )
                self.assertEqual(summary["status"], "PASS")
                self.assertGreater(marker["facility_p_kw_total"], 0.0)
                self.assertEqual(marker["active_jobs"], 1)

    def test_b0_rejects_unauthorized_fast_compute_modulation(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(
                RuntimeContractError,
                "without temporal flexibility",
            ):
                PfrRuntimeRunner(
                    power_curve=self.curve,
                    physical_backend=FakePhysical(),
                    fast_optimizer=UnauthorizedComputeModulatingOptimizer(),
                    migration_authority=self.migration_authority,
                ).run_method(
                    config=self.configs[0],
                    frames=self.frames[:1],
                    initial=self.initial,
                    representative_week_id="TEST_B0_COMPUTE_AUTHORITY",
                    output=Path(temporary),
                )

    def test_b0_allows_only_physical_last_step_work_clipping(self):
        short_job = OperationalTrainingJob(
            "short-j1", "IDC01", 100, 102, 110, 1, 60, 0.01, None,
            "source-short-j1",
            self.migration_authority.checkpoint_payload_bytes(1),
            self.migration_authority.fingerprint,
        )
        frame = CausalExperimentFrame(
            100, 100, 50, 1000, 100, (short_job,), "f" * 64
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            summary = PfrRuntimeRunner(
                power_curve=self.curve,
                physical_backend=FakePhysical(),
                migration_authority=self.migration_authority,
            ).run_method(
                config=self.configs[0],
                frames=(frame,),
                initial=self.initial,
                representative_week_id="TEST_B0_LAST_STEP_CLIP",
                output=root,
            )
            marker = __import__("json").loads(
                (root / "B0/issue_000100/COMMIT_MARKER.json").read_text()
            )
        self.assertEqual(summary["status"], "PASS")
        self.assertEqual(marker["completed_jobs"], 1)
        self.assertGreater(marker["facility_p_kw_total"], 0.0)

    def test_b0_capacity_burst_is_queued_without_hiding_work(self):
        jobs = tuple(
            OperationalTrainingJob(
                f"burst-{index:03d}", "IDC01", 100, 105, 140, 1, 3600,
                0.01, None, f"source-burst-{index:03d}",
                self.migration_authority.checkpoint_payload_bytes(1),
                self.migration_authority.fingerprint,
            )
            for index in range(346)
        )
        frame = CausalExperimentFrame(
            100, 100, 50, 1000, 100, jobs, "a" * 64
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            summary = PfrRuntimeRunner(
                power_curve=self.curve,
                physical_backend=FakePhysical(),
                migration_authority=self.migration_authority,
            ).run_method(
                config=self.configs[0],
                frames=(frame,),
                initial=self.initial,
                representative_week_id="TEST_B0_CAPACITY_QUEUE",
                output=root,
            )
            marker = __import__("json").loads(
                (root / "B0/issue_000100/COMMIT_MARKER.json").read_text()
            )
        self.assertEqual(summary["status"], "PASS")
        self.assertEqual(marker["active_jobs"], 256)
        self.assertEqual(marker["queued_jobs"], 90)
        self.assertEqual(marker["running_gpu_by_site"]["IDC01"], 256)
        self.assertEqual(marker["queued_gpu_by_site"]["IDC01"], 90)
        self.assertTrue(marker["capacity_blocked_queue"])
        self.assertEqual(summary["final_queued_jobs"], 90)
        self.assertAlmostEqual(
            marker["remaining_work_gpu_hours"], 346.0 - 256 / 12
        )

    def test_b0_capacity_queue_drains_after_completed_gangs_release_gpus(self):
        jobs = tuple(
            OperationalTrainingJob(
                f"short-burst-{index:03d}", "IDC01", 100, 105, 140, 1, 60,
                0.01, None, f"source-short-burst-{index:03d}",
                self.migration_authority.checkpoint_payload_bytes(1),
                self.migration_authority.fingerprint,
            )
            for index in range(300)
        )
        frames = (
            CausalExperimentFrame(100, 100, 50, 1000, 100, jobs, "a" * 64),
            CausalExperimentFrame(101, 100, 50, 1000, 100, (), "b" * 64),
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            summary = PfrRuntimeRunner(
                power_curve=self.curve,
                physical_backend=FakePhysical(),
                migration_authority=self.migration_authority,
            ).run_method(
                config=self.configs[0],
                frames=frames,
                initial=self.initial,
                representative_week_id="TEST_B0_CAPACITY_QUEUE_DRAIN",
                output=root,
            )
            first = __import__("json").loads(
                (root / "B0/issue_000100/COMMIT_MARKER.json").read_text()
            )
            second = __import__("json").loads(
                (root / "B0/issue_000101/COMMIT_MARKER.json").read_text()
            )
        self.assertEqual(summary["status"], "PASS")
        self.assertEqual(first["completed_jobs"], 256)
        self.assertEqual(first["queued_jobs"], 44)
        self.assertEqual(second["workload_started_jobs"], 44)
        self.assertEqual(second["completed_jobs"], 300)
        self.assertEqual(second["queued_jobs"], 0)
        self.assertEqual(summary["final_queued_jobs"], 0)

    def test_spatial_arm_preplaces_burst_without_reserving_queued_gpus(self):
        config = next(
            item
            for item in self.configs
            if item.comparison_method_id is ComparisonMethod.B3
        )
        jobs = tuple(
            OperationalTrainingJob(
                f"spatial-burst-{index:03d}", "IDC01", 100, 105, 140,
                1, 3600, 0.01, None, f"source-spatial-burst-{index:03d}",
                self.migration_authority.checkpoint_payload_bytes(1),
                self.migration_authority.fingerprint,
            )
            for index in range(324)
        )
        frame = CausalExperimentFrame(
            100, 100, 50, 1000, 100, jobs, "a" * 64
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            summary = PfrRuntimeRunner(
                power_curve=self.curve,
                physical_backend=FakePhysical(),
                migration_authority=self.migration_authority,
            ).run_method(
                config=config,
                frames=(frame,),
                initial=self.initial,
                representative_week_id="TEST_B3_BURST_PRESTART",
                output=root,
            )
            marker = __import__("json").loads(
                (root / "B3/issue_000100/COMMIT_MARKER.json").read_text()
            )
        self.assertEqual(summary["status"], "PASS")
        self.assertEqual(marker["active_jobs"], 324)
        self.assertEqual(marker["queued_jobs"], 0)
        self.assertLessEqual(max(marker["running_gpu_by_site"].values()), 256)

    def test_common_native_binary_transition_precedes_and_is_fixed_during_safety(self):
        physical = NativeControlPhysical()
        with tempfile.TemporaryDirectory() as temporary:
            PfrRuntimeRunner(
                power_curve=self.curve,
                physical_backend=physical,
                native_control_initial_states={"c83": (1,)},
                native_control_minimum_dwell_steps=6,
            ).run_method(
                config=self.configs[0],
                frames=self.frames[:1],
                initial=self.initial,
                representative_week_id="TEST_NATIVE_CONTROL",
                output=Path(temporary),
            )
        self.assertEqual(physical.selected, 1)
        self.assertTrue(physical.verified_states)
        self.assertTrue(
            all(states == {"c83": (0,)} for states in physical.verified_states)
        )
    def test_spatial_method_fails_closed_without_frozen_migration_authority(self):
        config = next(item for item in self.configs if item.comparison_method_id is ComparisonMethod.B3)
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(RuntimeContractError):
                PfrRuntimeRunner(
                    power_curve=self.curve, physical_backend=FakePhysical()
                ).run_method(
                    config=config, frames=self.frames[:1], initial=self.initial,
                    representative_week_id="TEST", output=Path(temporary),
                )

    def test_spatial_arm_executes_checkpoint_migration_and_accounts_wan_bytes(self):
        config = next(
            item
            for item in self.configs
            if item.comparison_method_id is ComparisonMethod.B5
        )
        jobs = tuple(
            OperationalTrainingJob(
                f"j{index}", "IDC01", 100, 102, 130, 1, 7200, 0.01,
                None, f"source-j{index}",
                self.migration_authority.checkpoint_payload_bytes(1),
                self.migration_authority.fingerprint,
            )
            for index in (1, 2)
        )
        frames = tuple(
            CausalExperimentFrame(
                issue,
                100.0,
                100.0,
                1000.0,
                100.0,
                jobs if issue == 100 else (),
                format(issue, "064x"),
                workload_reserve_gpu={
                    site: (20.0 if issue >= 106 and site == "IDC01" else 0.0)
                    for site in self.migration_authority.idc_to_wan_node
                },
            )
            for issue in range(100, 109)
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            summary = PfrRuntimeRunner(
                power_curve=self.curve,
                physical_backend=FakePhysical(),
                migration_authority=self.migration_authority,
            ).run_method(
                config=config,
                frames=frames,
                initial=self.initial,
                representative_week_id="TEST_B5_MIGRATION",
                output=root,
            )
            marker = __import__("json").loads(
                (root / "B5/issue_000106/COMMIT_MARKER.json").read_text(
                    encoding="utf-8"
                )
            )
            initial_marker = __import__("json").loads(
                (root / "B5/issue_000100/COMMIT_MARKER.json").read_text(
                    encoding="utf-8"
                )
            )
            restart_marker = __import__("json").loads(
                (root / "B5/issue_000107/COMMIT_MARKER.json").read_text(
                    encoding="utf-8"
                )
            )
        self.assertEqual(summary["status"], "PASS")
        self.assertEqual(summary["migration_count"], 1)
        self.assertEqual(summary["wan_transferred_bytes"], 80_000_000_000)
        self.assertEqual(marker["wan_bytes_transferred_step"], 80_000_000_000)
        self.assertEqual(len(marker["migration_started"]), 1)
        self.assertGreaterEqual(
            marker["migration_started"][0]["checkpoint_steps_at_start"],
            marker["migration_started"][0]["checkpoint_interval_steps"],
        )
        self.assertEqual(
            marker["migration_started"][0]["required_transfer_restart_steps"],
            2,
        )
        self.assertEqual(len(marker["migration_completed"]), 1)
        self.assertEqual(len(initial_marker["prestart_spatial_placements"]), 1)
        self.assertEqual(initial_marker["wan_bytes_transferred_step"], 0)
        self.assertEqual(len(restart_marker["migration_restarts_completed"]), 1)
        self.assertEqual(
            marker["migration_payload_authority"],
            self.migration_authority.fingerprint,
        )

    def test_empty_job_slow_plan_is_valid(self):
        frame = CausalExperimentFrame(100, 10, 10, 1000, 100, (), "f" * 64)
        with tempfile.TemporaryDirectory() as temporary:
            summary = PfrRuntimeRunner(power_curve=self.curve, physical_backend=FakePhysical()).run_method(
                config=self.configs[0], frames=(frame,), initial=self.initial,
                representative_week_id="TEST", output=Path(temporary),
            )
        self.assertEqual(summary["status"], "PASS")

    def test_b0_fail_closed_never_uses_mess_as_common_emergency_override(self):
        physical = MessOnlyRescuePhysical()
        with tempfile.TemporaryDirectory() as temporary:
            summary = PfrRuntimeRunner(
                power_curve=self.curve,
                physical_backend=physical,
                migration_authority=self.migration_authority,
            ).run_method(
                config=self.configs[0], frames=self.frames[:1], initial=self.initial,
                representative_week_id="TEST", output=Path(temporary),
            )
        self.assertEqual(summary["status"], "FAIL_CLOSED")
        self.assertTrue(physical.mess_controls)
        self.assertTrue(all(
            all(abs(float(value)) <= 1e-12 for value in controls)
            for controls in physical.mess_controls
        ))

    def test_matrix_isolates_one_method_exception_and_runs_remaining_methods(self):
        physical = RaiseOncePhysical()
        with tempfile.TemporaryDirectory() as temporary:
            summary = PfrRuntimeRunner(
                power_curve=self.curve,
                physical_backend=physical,
                migration_authority=self.migration_authority,
            ).run_matrix(
                configs=self.configs, frames=self.frames[:1], initial=self.initial,
                representative_week_id="TEST", output=Path(temporary),
            )
        self.assertEqual(summary["status"], "FAIL_CLOSED")
        self.assertEqual(summary["failed_methods"], ["B0"])
        self.assertEqual(len(summary["method_summaries"]), 8)
        self.assertTrue(summary["continue_to_next_method_after_failure"])
        self.assertEqual(
            summary["method_execution_order"],
            [f"B{index}" for index in range(8)],
        )
        self.assertTrue(all(
            row["status"] == "PASS" for row in summary["method_summaries"][1:]
        ))

    def test_exception_summary_preserves_and_counts_prior_commit_markers(self):
        physical = RaiseAfterOneCommittedIssuePhysical()
        with tempfile.TemporaryDirectory() as temporary:
            summary = PfrRuntimeRunner(
                power_curve=self.curve,
                physical_backend=physical,
                migration_authority=self.migration_authority,
            ).run_matrix(
                configs=self.configs,
                frames=self.frames,
                initial=self.initial,
                representative_week_id="TEST",
                output=Path(temporary),
            )
            b0 = summary["method_summaries"][0]
            failure = __import__("json").loads(
                (Path(temporary) / "B0/FAILURE.json").read_text()
            )

        self.assertEqual(b0["status"], "FAIL_CLOSED")
        self.assertEqual(b0["committed_issues"], 1)
        self.assertEqual(b0["commit_marker_count"], 1)
        self.assertTrue(b0["state_chain_complete"])
        self.assertEqual(failure["issue"], 101)
        self.assertEqual(failure["valid_partial_commit_markers"], 1)


if __name__ == "__main__":
    unittest.main()
