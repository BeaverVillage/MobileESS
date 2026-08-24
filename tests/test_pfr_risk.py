import unittest

from pfr.risk import (
    EventAudit,
    EventMetricsSummary,
    PlanValidityRiskMonitor,
    ReplanCost,
    RiskConstraint,
    RiskContractError,
    RiskFamily,
)


def constraints(raw_margin=-0.1, calibrated_increment=0.0):
    return tuple(
        RiskConstraint(
            family.value,
            family,
            raw_margin,
            0.1,
            calibrated_increment,
        )
        for family in RiskFamily
    )


class RiskMonitorTests(unittest.TestCase):
    def test_normalizes_before_cross_family_maximum(self):
        items = list(constraints())
        items[0] = RiskConstraint("soc", RiskFamily.SOC, 2.0, 4.0)
        items[1] = RiskConstraint("deadline", RiskFamily.DEADLINE, 1.0, 1.0)
        decision = PlanValidityRiskMonitor(calibrated=False, maximum_refresh_steps=12).evaluate(
            constraints=items,
            expected_replan_benefit=0.0,
            replan_cost=ReplanCost(1.0, 1.0, 1.0, 0.1),
            plan_age_steps=0,
        )
        self.assertEqual(decision.raw_risk, 1.0)

    def test_safety_trigger_is_exactly_positive_risk(self):
        monitor = PlanValidityRiskMonitor(calibrated=False, maximum_refresh_steps=12)
        zero = monitor.evaluate(
            constraints=constraints(raw_margin=0.0), expected_replan_benefit=0.0,
            replan_cost=ReplanCost(1, 1, 1, 0), plan_age_steps=0,
        )
        positive = monitor.evaluate(
            constraints=constraints(raw_margin=0.001), expected_replan_benefit=0.0,
            replan_cost=ReplanCost(1, 1, 1, 0), plan_age_steps=0,
        )
        self.assertFalse(zero.request_full_replan)
        self.assertTrue(positive.request_full_replan)

    def test_raw_and_calibrated_interfaces_separate_b6_b7(self):
        items = constraints(raw_margin=-0.1, calibrated_increment=0.2)
        b6 = PlanValidityRiskMonitor(calibrated=False, maximum_refresh_steps=12).evaluate(
            constraints=items, expected_replan_benefit=0, replan_cost=ReplanCost(1, 1, 1, 0), plan_age_steps=0,
        )
        b7 = PlanValidityRiskMonitor(calibrated=True, maximum_refresh_steps=12).evaluate(
            constraints=items, expected_replan_benefit=0, replan_cost=ReplanCost(1, 1, 1, 0), plan_age_steps=0,
        )
        self.assertFalse(b6.request_full_replan)
        self.assertTrue(b7.request_full_replan)
        self.assertEqual(b7.active_risk_interface, "CALIBRATED")

    def test_opportunity_trigger_uses_full_cost(self):
        monitor = PlanValidityRiskMonitor(calibrated=False, maximum_refresh_steps=12)
        decision = monitor.evaluate(
            constraints=constraints(), expected_replan_benefit=4.1,
            replan_cost=ReplanCost(1, 1, 1, 1), plan_age_steps=0,
        )
        self.assertIn("OPPORTUNITY_NET_BENEFIT_POSITIVE", decision.trigger_causes)

    def test_maximum_refresh_is_independent(self):
        decision = PlanValidityRiskMonitor(calibrated=False, maximum_refresh_steps=12).evaluate(
            constraints=constraints(), expected_replan_benefit=0,
            replan_cost=ReplanCost(1, 1, 1, 0), plan_age_steps=12,
        )
        self.assertEqual(decision.trigger_causes, ("MAXIMUM_REFRESH",))

    def test_all_six_families_are_mandatory(self):
        with self.assertRaises(RiskContractError):
            PlanValidityRiskMonitor(calibrated=True, maximum_refresh_steps=12).evaluate(
                constraints=constraints()[:-1], expected_replan_benefit=0,
                replan_cost=ReplanCost(1, 1, 1, 0), plan_age_steps=0,
            )

    def test_outcome_selected_scale_is_rejected(self):
        bad = list(constraints())
        bad[0] = RiskConstraint("soc", RiskFamily.SOC, 0, 1, scale_authority="POST_OUTCOME")
        with self.assertRaises(RiskContractError):
            PlanValidityRiskMonitor(calibrated=False, maximum_refresh_steps=12).evaluate(
                constraints=bad, expected_replan_benefit=0,
                replan_cost=ReplanCost(1, 1, 1, 0), plan_age_steps=0,
            )

    def test_event_metrics_include_false_and_late_audit(self):
        monitor = PlanValidityRiskMonitor(calibrated=False, maximum_refresh_steps=12)
        trigger = monitor.evaluate(
            constraints=constraints(raw_margin=0.1), expected_replan_benefit=0,
            replan_cost=ReplanCost(1, 1, 1, 0), plan_age_steps=0,
        )
        quiet = monitor.evaluate(
            constraints=constraints(), expected_replan_benefit=0,
            replan_cost=ReplanCost(1, 1, 1, 0), plan_age_steps=0,
        )
        summary = EventMetricsSummary.from_audits((
            EventAudit(trigger, 128, False, 2.0),
            EventAudit(quiet, 0, True, 3.0),
        ))
        self.assertEqual(summary.full_replan_count, 1)
        self.assertEqual(summary.false_trigger_count, 1)
        self.assertEqual(summary.late_trigger_count, 1)
        self.assertEqual(summary.event_regret, 5.0)


if __name__ == "__main__":
    unittest.main()
