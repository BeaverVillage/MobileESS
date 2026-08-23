import unittest
from types import SimpleNamespace

from pfr.safety import (
    AcSafetyFilter,
    EscalatedCandidate,
    ExactAcResult,
    FilterMetricsSummary,
    ProjectionCandidate,
    ProjectionCertificate,
    SafetyFilterContractError,
)
from pfr.slow_fast import FastControl, FastLayerState, SlowDiscretePlan


def control(discharge=10.0, q=0.0, compute=1.0):
    return FastControl({"m1": 0.0}, {"m1": discharge}, {"m1": q}, {"j1": compute}, {"idc1": 1.0})


def plan(plan_id="p1"):
    return SlowDiscretePlan(plan_id, 0, {"m1": "b1"}, {"m1": 1}, {"j1": "idc1"}, {"j1": None}, {"j1": ("g1",)}, {"j1": 0}, {"m1": (0.0,)})


CERT = ProjectionCertificate("CONVEX_CONTINUOUS_QP", True, True, True, True, True, True, True, True)


class Projector:
    def __init__(self, projected=None, certificate=CERT, wrong_fingerprint=False):
        self.projected = projected
        self.certificate = certificate
        self.wrong_fingerprint = wrong_fingerprint

    def project(self, *, nominal, state, slow_plan):
        candidate = self.projected or nominal
        return ProjectionCandidate(candidate, self.certificate, "wrong" if self.wrong_fingerprint else slow_plan.fingerprint, 10.0, 11.0, 0.01)


class Verifier:
    def __init__(self, passed=True, fresh=True):
        self.passed = passed
        self.fresh = fresh

    def verify_fresh(self, **kwargs):
        return ExactAcResult(
            self.passed, "PASS" if self.passed else "VOLTAGE_FAIL", self.fresh, True,
            0.97 if self.passed else 0.94, 1.03, 0.8, 0.7, 0 if self.passed else 1,
        )


class AlternatingNativeVerifier:
    def __init__(self):
        self.native_decision = SimpleNamespace(
            states={"c83": (1,)}, regulator_taps={"creg4a": 5}
        )
        self.selections = 0

    def select_native_control(self, *, control):
        del control
        self.selections += 1
        self.native_decision = SimpleNamespace(
            states={"c83": (0,)}, regulator_taps={"creg4a": 4}
        )
        return self.native_decision

    def verify_fresh(self, **kwargs):
        del kwargs
        passed = self.selections > 0
        return ExactAcResult(
            passed,
            "PASS" if passed else "VOLTAGE_FAIL",
            True,
            True,
            0.97,
            1.049 if passed else 1.051,
            0.8,
            0.7,
            0 if passed else 1,
        )


class SafetyFilterTests(unittest.TestCase):
    def setUp(self):
        self.state = FastLayerState(0, {"m1": 0.5}, {"j1": 1.0})

    def test_safe_nominal_is_accepted_with_fresh_exact_authority(self):
        result = AcSafetyFilter(projector=Projector(), verifier=Verifier()).filter(
            nominal=control(), state=self.state, slow_plan=plan()
        )
        self.assertTrue(result.accepted)
        self.assertFalse(result.intervention)
        self.assertEqual(result.exact_ac.final_ac_violation_count, 0)

    def test_intervention_metrics_include_p_q_compute_and_objective(self):
        result = AcSafetyFilter(projector=Projector(control(5, 2, 0.5)), verifier=Verifier()).filter(
            nominal=control(10, 0, 1), state=self.state, slow_plan=plan()
        )
        self.assertTrue(result.intervention)
        self.assertEqual(result.delta_p_kw, 5)
        self.assertEqual(result.delta_q_kvar, 2)
        self.assertEqual(result.compute_throttling_fraction, 0.5)
        self.assertEqual(result.objective_degradation, 1)

    def test_projection_must_be_convex_continuous(self):
        bad = ProjectionCertificate("HEURISTIC_PQ_CORRECTION", True, True, True, True, True, True, True, True)
        with self.assertRaises(SafetyFilterContractError):
            AcSafetyFilter(projector=Projector(certificate=bad), verifier=Verifier()).filter(
                nominal=control(), state=self.state, slow_plan=plan()
            )

    def test_projection_cannot_change_slow_state(self):
        with self.assertRaises(SafetyFilterContractError):
            AcSafetyFilter(projector=Projector(wrong_fingerprint=True), verifier=Verifier()).filter(
                nominal=control(), state=self.state, slow_plan=plan()
            )

    def test_fresh_exact_instance_is_mandatory(self):
        with self.assertRaises(SafetyFilterContractError):
            AcSafetyFilter(projector=Projector(), verifier=Verifier(fresh=False)).filter(
                nominal=control(), state=self.state, slow_plan=plan()
            )

    def test_unresolved_exact_violation_fails_closed(self):
        result = AcSafetyFilter(projector=Projector(), verifier=Verifier(passed=False)).filter(
            nominal=control(), state=self.state, slow_plan=plan()
        )
        self.assertFalse(result.accepted)
        self.assertIsNone(result.safe_control)

    def test_projected_control_reselects_common_native_grid_state(self):
        verifier = AlternatingNativeVerifier()
        result = AcSafetyFilter(
            projector=Projector(control(5)), verifier=verifier
        ).filter(nominal=control(10), state=self.state, slow_plan=plan())

        self.assertTrue(result.accepted)
        self.assertEqual(verifier.selections, 1)
        self.assertEqual(verifier.native_decision.regulator_taps, {"creg4a": 4})

    def test_escalation_requires_full_replan_and_fast_recourse(self):
        filt = AcSafetyFilter(projector=Projector(), verifier=Verifier(passed=False))
        with self.assertRaises(SafetyFilterContractError):
            filt.filter(
                nominal=control(), state=self.state, slow_plan=plan(),
                escalate_full_replan=lambda: EscalatedCandidate(plan("p2"), self.state, control(), False, True),
            )

    def test_metrics_summary_reports_runtime_and_zero_final_violations(self):
        filt = AcSafetyFilter(projector=Projector(control(5)), verifier=Verifier())
        results = [filt.filter(nominal=control(), state=self.state, slow_plan=plan()) for _ in range(3)]
        summary = FilterMetricsSummary.from_results(results)
        self.assertEqual(summary.intervention_count, 3)
        self.assertEqual(summary.final_ac_violations, 0)
        self.assertGreaterEqual(summary.runtime_max_seconds, summary.runtime_p95_seconds)


if __name__ == "__main__":
    unittest.main()
