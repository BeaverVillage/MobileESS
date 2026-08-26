import unittest

from pfr.persistent_bounded_milp import (
    _episode_terminal_debt_rhs,
    _recovery_zero_boundary,
)


class EpisodeBoundaryRecoveryTests(unittest.TestCase):
    def test_real_boundary_not_virtual_h54_is_active(self):
        rhs = _episode_terminal_debt_rhs(3, 54)
        self.assertEqual(rhs[2], 0.0)
        self.assertNotEqual(rhs[53], 0.0)
        self.assertEqual(sum(value == 0.0 for value in rhs), 1)

    def test_full_horizon_keeps_h54_terminal(self):
        rhs = _episode_terminal_debt_rhs(54, 54)
        self.assertEqual(rhs[-1], 0.0)

    def test_fixed_recovery_deadline_does_not_roll_with_horizon(self):
        rhs = _episode_terminal_debt_rhs(
            54, 54, additional_zero_boundaries=(7,)
        )
        self.assertEqual(rhs[6], 0.0)
        self.assertEqual(rhs[53], 0.0)
        self.assertEqual(sum(value == 0.0 for value in rhs), 2)

    def test_transit_defers_expired_recovery_until_charge_is_possible(self):
        boundary = _recovery_zero_boundary(
            effective_steps=54,
            due_issue=9738,
            current_issue=9738,
            debt_kwh=10.0,
            transit_remaining_steps=1,
        )
        self.assertEqual(boundary, 2)

    def test_transit_deferral_includes_all_required_charge_steps(self):
        boundary = _recovery_zero_boundary(
            effective_steps=54,
            due_issue=9738,
            current_issue=9738,
            debt_kwh=100.0,
            transit_remaining_steps=2,
        )
        self.assertEqual(boundary, 5)

    def test_transit_does_not_shorten_a_later_recovery_deadline(self):
        boundary = _recovery_zero_boundary(
            effective_steps=54,
            due_issue=9744,
            current_issue=9738,
            debt_kwh=10.0,
            transit_remaining_steps=1,
        )
        self.assertEqual(boundary, 7)


if __name__ == "__main__":
    unittest.main()
