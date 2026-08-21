import unittest

from pfr.methods import (
    ComparisonMethod,
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
        self.assertEqual(self.factory.create(ComparisonMethod.B5).control_mode, "PERIODIC_MPC")
        self.assertEqual(self.factory.create(ComparisonMethod.B6).control_mode, "EVENT_TRIGGERED")
        self.assertEqual(self.factory.create(ComparisonMethod.B7).control_mode, "EVENT_TRIGGERED")

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


if __name__ == "__main__":
    unittest.main()
