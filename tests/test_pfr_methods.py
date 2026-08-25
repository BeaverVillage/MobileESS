import unittest

from pfr.methods import (
    ComparisonMethod,
    FACTORIAL_ELECTRICAL_STRESS_CELLS,
    ElectricalStressMethod,
    ExperimentAuthority,
    K9H7ResultIdentityV2,
    MethodContractError,
    MethodFactory,
)


HASHES = [format(index, "064x") for index in range(1, 8)]


class MethodFactoryTests(unittest.TestCase):
    def setUp(self):
        self.authority = ExperimentAuthority(*HASHES)
        self.factory = MethodFactory(self.authority)

    def test_registry_has_exactly_b0_through_b7(self):
        configs = self.factory.all()
        self.assertEqual([item.comparison_method_id.value for item in configs], [f"B{i}" for i in range(8)])

    def test_b8_is_a_separate_five_minute_periodic_baseline(self):
        main = self.factory.all()
        supplementary = self.factory.supplementary()
        self.assertNotIn(ComparisonMethod.B8, [item.comparison_method_id for item in main])
        self.assertEqual(len(supplementary), 1)
        b8 = supplementary[0]
        b7 = self.factory.create(ComparisonMethod.B7)
        self.assertEqual(b8.comparison_method_id, ComparisonMethod.B8)
        self.assertEqual(b8.control_mode, "PERIODIC_MPC")
        self.assertEqual(b8.periodic_replan_steps, 1)
        self.assertEqual(b8.risk_interface, "CALIBRATED")
        self.assertEqual(b8.energy_flexibility, b7.energy_flexibility)
        self.assertEqual(b8.temporal_workload_shift, b7.temporal_workload_shift)
        self.assertEqual(b8.spatial_workload_migration, b7.spatial_workload_migration)

    def test_all_methods_share_one_experiment_authority_and_ac_safety(self):
        configs = self.factory.all()
        self.assertEqual(len({item.authority_fingerprint for item in configs}), 1)
        self.assertTrue(all(item.ac_safety_filter for item in configs))

    def test_b0_has_no_flexibility(self):
        b0 = self.factory.create(ComparisonMethod.B0)
        self.assertEqual(b0.energy_flexibility, "NONE")
        self.assertFalse(b0.temporal_workload_shift)
        self.assertFalse(b0.spatial_workload_migration)

    def test_b1_is_mess_only(self):
        b1 = self.factory.create(ComparisonMethod.B1)
        self.assertEqual(b1.energy_flexibility, "MESS")
        self.assertFalse(b1.ai_training_aware)

    def test_b2_and_b3_isolate_temporal_and_spatial_compute(self):
        b2 = self.factory.create(ComparisonMethod.B2)
        b3 = self.factory.create(ComparisonMethod.B3)
        self.assertEqual((b2.temporal_workload_shift, b2.spatial_workload_migration), (True, False))
        self.assertEqual((b3.temporal_workload_shift, b3.spatial_workload_migration), (False, True))

    def test_b5_is_periodic_and_b6_b7_are_event_triggered(self):
        self.assertTrue(all(
            self.factory.create(method).control_mode == "PERIODIC_MPC"
            for method in (
                ComparisonMethod.B1,
                ComparisonMethod.B2,
                ComparisonMethod.B3,
                ComparisonMethod.B4,
                ComparisonMethod.B5,
            )
        ))
        self.assertEqual(self.factory.create(ComparisonMethod.B5).control_mode, "PERIODIC_MPC")
        self.assertEqual(self.factory.create(ComparisonMethod.B6).control_mode, "EVENT_TRIGGERED")
        self.assertEqual(self.factory.create(ComparisonMethod.B7).control_mode, "EVENT_TRIGGERED")
        self.assertEqual(self.factory.create(ComparisonMethod.B8).control_mode, "PERIODIC_MPC")

    def test_fast_recourse_toggle_matches_frozen_table(self):
        self.assertFalse(self.factory.create(ComparisonMethod.B0).slow_fast_control)
        self.assertTrue(all(
            self.factory.create(method).slow_fast_control
            for method in tuple(ComparisonMethod)[1:]
        ))

    def test_b6_raw_and_b7_calibrated_are_explicit(self):
        self.assertEqual(self.factory.create(ComparisonMethod.B6).risk_interface, "RAW_UNCALIBRATED")
        self.assertEqual(self.factory.create(ComparisonMethod.B7).risk_interface, "CALIBRATED")

    def test_result_identity_is_v2_and_hash_addressed(self):
        b7 = self.factory.create(ComparisonMethod.B7)
        identity = K9H7ResultIdentityV2.for_method(
            b7, controller_id="pfr-controller-v1", representative_week_id="W02_2025-01-13"
        )
        self.assertEqual(identity.schema_version, "K9H7_RESULT_V2")
        self.assertEqual(len(identity.result_uid), 64)

    def test_v1_identity_is_rejected(self):
        identity = K9H7ResultIdentityV2(
            "V13_AI_ICPS", "B0", "c", None, "W02", self.authority.fingerprint,
            schema_version="K9H7_RESULT_V1",
        )
        with self.assertRaises(MethodContractError):
            identity.validate()

    def test_electrical_stress_registry_is_b00_through_b09(self):
        configs = self.factory.electrical_stress_campaign()
        self.assertEqual(
            [item.comparison_method_id.value for item in configs],
            [f"B{index:02d}" for index in range(10)],
        )
        self.assertEqual(
            self.factory.create_electrical_stress(
                ElectricalStressMethod.B04
            ).label,
            "Full compute only",
        )

    def test_factorial_cells_share_controller_and_only_toggle_capabilities(self):
        cells = {
            cell: self.factory.create_electrical_stress(method)
            for cell, method in FACTORIAL_ELECTRICAL_STRESS_CELLS.items()
        }
        common = {
            (
                config.control_mode,
                config.periodic_replan_steps,
                config.risk_interface,
                config.joint_uncertainty,
                config.ac_safety_filter,
            )
            for config in cells.values()
        }
        self.assertEqual(len(common), 1)
        self.assertEqual(
            {
                cell: (
                    config.energy_flexibility != "NONE",
                    config.temporal_workload_shift
                    and config.spatial_workload_migration,
                )
                for cell, config in cells.items()
            },
            {
                "RC0": (False, False),
                "RCE": (True, False),
                "RCC": (False, True),
                "RCEC": (True, True),
            },
        )
        self.assertEqual(
            cells["RCC"].h54_capability_mask,
            {
                "mess_dispatch": False,
                "mess_mobility": False,
                "temporal_compute": True,
                "spatial_compute": True,
            },
        )


if __name__ == "__main__":
    unittest.main()
