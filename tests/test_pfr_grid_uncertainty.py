from __future__ import annotations

import unittest

import numpy as np

from pfr.grid_uncertainty import GridUncertaintyError, audit_grid_quantile_envelope


class GridUncertaintyTests(unittest.TestCase):
    def test_valid_causal_quantile_axis(self):
        q50 = np.ones((2, 54, 3), dtype=np.float32)
        audit = audit_grid_quantile_envelope(
            np.arange(2, dtype=np.int32),
            q50 - 0.5,
            q50,
            q50 + 0.5,
            ("demand_mw", "rooftop_pv_mw", "rrp_aud_per_mwh"),
        )
        self.assertEqual(audit.quantile_crossings, 0)
        self.assertEqual(audit.issue_count, 2)

    def test_quantile_crossing_is_fail_closed(self):
        q50 = np.ones((1, 54, 3), dtype=np.float32)
        with self.assertRaises(GridUncertaintyError):
            audit_grid_quantile_envelope(
                np.arange(1, dtype=np.int32),
                q50 + 1.0,
                q50,
                q50 + 0.5,
                ("demand_mw", "rooftop_pv_mw", "rrp_aud_per_mwh"),
            )


if __name__ == "__main__":
    unittest.main()
