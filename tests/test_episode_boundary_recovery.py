import unittest

from pfr.persistent_bounded_milp import _episode_terminal_debt_rhs


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


if __name__ == "__main__":
    unittest.main()
