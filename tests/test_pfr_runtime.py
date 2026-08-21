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


if __name__ == "__main__":
    unittest.main()
