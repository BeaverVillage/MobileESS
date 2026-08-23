import tempfile
from pathlib import Path
import unittest

from pfr.methods import ComparisonMethod, ExperimentAuthority, MethodFactory
from pfr.power import H100UtilizationPowerCurve
from pfr.runtime import (
    CausalExperimentFrame,
    OperationalTrainingJob,
    PhysicalCommit,
    PfrRuntimeRunner,
    RuntimeInitialState,
    NativeGridControlDecision,
)
from pfr.safety import ExactAcResult


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
        job = OperationalTrainingJob("j1", "IDC01", 100, 102, 110, 1, 3600, 0.01, None, "source-j1")
        self.frames = (
            CausalExperimentFrame(100, 100, 50, 1000, 100, (job,), "d" * 64),
            CausalExperimentFrame(101, 20, 50, 1000, 100, (), "e" * 64),
        )

    def test_b0_b7_matrix_commits_every_issue_with_fresh_exact_gate(self):
        physical = FakePhysical()
        with tempfile.TemporaryDirectory() as temporary:
            summary = PfrRuntimeRunner(power_curve=self.curve, physical_backend=physical).run_matrix(
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
    def test_missing_payload_blocks_spatial_action_without_fabricating_zero(self):
        config = next(item for item in self.configs if item.comparison_method_id is ComparisonMethod.B3)
        with tempfile.TemporaryDirectory() as temporary:
            PfrRuntimeRunner(power_curve=self.curve, physical_backend=FakePhysical()).run_method(
                config=config, frames=self.frames[:1], initial=self.initial,
                representative_week_id="TEST", output=Path(temporary),
            )
            marker = __import__("json").loads(
                (Path(temporary) / "B3/issue_000100/COMMIT_MARKER.json").read_text()
            )
        self.assertEqual(marker["spatial_actions_blocked_missing_payload"], 1)
        self.assertEqual(marker["migration_payload_authority"], "NULL_INPUT_BYTES_BLOCKS_MIGRATION")

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
                power_curve=self.curve, physical_backend=physical
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
                power_curve=self.curve, physical_backend=physical
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
                power_curve=self.curve, physical_backend=physical
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
