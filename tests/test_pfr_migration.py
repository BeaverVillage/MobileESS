from pathlib import Path
import tempfile
import unittest

from pfr.canary import run_idc_migration_canary
from pfr.migration import load_migration_authority


class MigrationAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.path = (
            Path(__file__).parents[1]
            / "pfr/contracts/IDC_MIGRATION_AUTHORITY_V1.json"
        )
        self.authority = load_migration_authority(self.path)

    def test_contract_has_connected_bijective_12_idc_topology(self):
        self.assertEqual(len(self.authority.idc_to_wan_node), 12)
        self.assertEqual(len(set(self.authority.idc_to_wan_node.values())), 12)
        for source in self.authority.idc_to_wan_node:
            for destination in self.authority.idc_to_wan_node:
                if source != destination:
                    self.assertTrue(self.authority.route(source, destination))

    def test_checkpoint_payload_and_transfer_capacity_are_exact(self):
        self.assertEqual(
            self.authority.checkpoint_payload_bytes(4), 320_000_000_000
        )
        self.assertEqual(
            self.authority.transfer_capacity_bytes_per_step("IDC01", "IDC02"),
            372_000_000_000,
        )
        self.assertEqual(
            self.authority.transfer_steps(80_000_000_000, "IDC01", "IDC02"),
            1,
        )

    def test_authorized_checkpoint_occupancy_sensitivity_is_explicit(self):
        expected = {0.25: 20_000_000_000, 0.5: 40_000_000_000, 1.0: 80_000_000_000}
        fingerprints = set()
        for factor, payload in expected.items():
            authority = load_migration_authority(
                self.path,
                checkpoint_payload_occupancy_factor=factor,
            )
            self.assertEqual(authority.checkpoint_payload_bytes(1), payload)
            self.assertEqual(authority.checkpoint_payload_occupancy_factor, factor)
            self.assertEqual(authority.contract_fingerprint, self.authority.contract_fingerprint)
            fingerprints.add(authority.fingerprint)
        self.assertEqual(len(fingerprints), 3)

    def test_runtime_canary_proves_work_conservation_and_b8_fairness(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = run_idc_migration_canary(
                self.authority, Path(temporary)
            )
        self.assertEqual(result["status"], "PASS")
        self.assertGreater(result["wan_bytes_transferred"], 0)
        self.assertTrue(result["remaining_compute_work_conserved"])
        self.assertTrue(result["running_at_different_idc_after_restart"])
        self.assertTrue(result["b8_precheckpoint_migration_blocked"])


if __name__ == "__main__":
    unittest.main()
