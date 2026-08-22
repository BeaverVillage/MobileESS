from __future__ import annotations

import copy
import unittest

from pfr.daily import DailyInitializationError, build_daily_pre_artifacts
from pfr.tools.run_pfr_matrix import _runtime_initial_state


AUTHORITY_SHA = "ccba214d7a8bf6c142b34cf6f0abc3ce70bae00b9bfd23fe5152506e552e599d"


class JanuaryDailyInitializationTests(unittest.TestCase):
    def test_31_by_8_independent_daily_population(self):
        manifest, certificate = build_daily_pre_artifacts(AUTHORITY_SHA)
        self.assertEqual(manifest["daily_episode_count"], 248)
        self.assertEqual(manifest["committed_scored_issue_target"], 71424)
        self.assertEqual(certificate["calendar_date_count"], 31)
        self.assertTrue(certificate["same_date_b0_b7_pre_identity"])
        self.assertTrue(certificate["daily_state_reset"])
        self.assertFalse(certificate["cross_day_state_carryover"])

    def test_canonical_pre_matches_v13_2(self):
        manifest, _ = build_daily_pre_artifacts(AUTHORITY_SHA)
        state = manifest["canonical_pre"]
        self.assertEqual(state["mess_energy_kwh"], (760.0, 760.0, 760.0, 760.0))
        self.assertEqual(state["mess_locations"], ("STA09", "IDC12", "STA07", "STA11"))
        self.assertEqual(state["compute_debt_gpu_hours"], 0.0)
        self.assertEqual(state["energy_debt_kwh"], 0.0)
        self.assertIsNone(state["active_slow_plan"])

    def test_same_date_method_identity_is_fail_closed(self):
        manifest, _ = build_daily_pre_artifacts(AUTHORITY_SHA)
        corrupted = copy.deepcopy(manifest)
        corrupted["episodes"][1]["method_independent_pre_sha256"] = "0" * 64
        from pfr.daily import certify_daily_pre_identity

        with self.assertRaises(DailyInitializationError):
            certify_daily_pre_identity(corrupted)

    def test_runtime_rejects_nonboundary_or_noncanonical_daily_soc(self):
        manifest, _ = build_daily_pre_artifacts(AUTHORITY_SHA)
        with self.assertRaises(RuntimeError):
            _runtime_initial_state(manifest, 1, require_population_identity=True)

        corrupted = copy.deepcopy(manifest)
        corrupted["canonical_pre"]["mess_energy_kwh"] = (
            759.0,
            760.0,
            760.0,
            760.0,
        )
        with self.assertRaises(RuntimeError):
            _runtime_initial_state(
                corrupted, 0, require_population_identity=True
            )

    def test_runtime_accepts_exact_canonical_daily_soc_and_locations(self):
        manifest, _ = build_daily_pre_artifacts(AUTHORITY_SHA)
        state = _runtime_initial_state(
            manifest, 288, require_population_identity=True
        )
        self.assertEqual(state.issue, 288)
        self.assertEqual(tuple(state.mess_energy_kwh.values()), (760.0,) * 4)
        self.assertEqual(
            tuple(state.mess_location.values()),
            ("STA09", "IDC12", "STA07", "STA11"),
        )


if __name__ == "__main__":
    unittest.main()
