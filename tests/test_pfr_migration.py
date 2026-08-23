from pathlib import Path
import unittest

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


if __name__ == "__main__":
    unittest.main()
