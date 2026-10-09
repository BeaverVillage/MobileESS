"""Metadata-only placeholders: no matrices, power flow, or solver objects."""
from dataclasses import replace
from types import SimpleNamespace
import unittest

from ieee8500_v42_original.grid_adapter import GridAdapter, GridInventory
from ieee8500_v42_original.hold import ExecutionHold


class ShapeOnly:
    def __init__(self, *shape):
        self.shape = shape


def fixture():
    # Arbitrary fixture labels and placeholder shapes; never research coefficients.
    lines = tuple(f'line.mock{i}' for i in range(3703))
    tx = tuple(f'transformer.mock{i}' for i in range(1190))
    sta = tuple(f'transformer.sta{i}' for i in range(12))
    pcs = tuple(f'transformer.pcs_sta{i}::{phase}' for i in range(12) for phase in 'abc')
    branches = tuple(name + '::a' for name in (*lines, *tx, *sta)) + pcs
    inventory = GridInventory(('mock.1',), branches, lines, (), tx, (), sta, pcs,
                              'a' * 64, 'b' * 64, 'c' * 64)
    names = tuple([f'aidc_load_kw[IDC{i:02d}]' for i in range(1, 13)] +
                  [f'{family}[{role}{i:02d}]' for family in ('mess_p_kw', 'mess_q_kvar')
                   for role in ('IDC', 'STA') for i in range(1, 13)])
    metadata = dict(day='2025-05-01', slots=96, grid='IEEE8500_BALANCED',
                    inventory_sha=inventory.identity_sha, inputs_sha='d' * 64,
                    anchor_sha='e' * 64, policy_sha='f' * 64)
    adapter = GridAdapter(inventory, names, metadata)
    b = len(branches)
    coefficient = SimpleNamespace(slot=0, control_names=names, node_names=inventory.node_names,
        branch_names=branches, voltage_constant=ShapeOnly(1), voltage_matrix=ShapeOnly(60, 1),
        current_constant=ShapeOnly(b), current_matrix=ShapeOnly(60, b),
        flow_p_constant=ShapeOnly(b), flow_q_constant=ShapeOnly(b),
        flow_p_matrix=ShapeOnly(b, 60), flow_q_matrix=ShapeOnly(b, 60),
        branch_limits=ShapeOnly(b), current_denominators_A=ShapeOnly(b), anchor=ShapeOnly(60),
        transformer_ratings=tuple(1. if name.startswith('transformer.') else None for name in branches),
        coefficient_sha256='0' * 64,
        transformer_current_authority_sha256=inventory.current_authority_sha,
        ieee8500_case_metadata=metadata)
    return adapter, coefficient


class GridMetadataTests(unittest.TestCase):
    def test_complete_fixture_shapes(self):
        adapter, coefficient = fixture()
        adapter.validate_coefficient_metadata(coefficient, 0)

    def test_partial_screening_is_rejected(self):
        adapter, coefficient = fixture()
        coefficient.branch_names = coefficient.branch_names[:87]
        with self.assertRaisesRegex(ValueError, 'FULL_GRID_AXIS'):
            adapter.validate_coefficient_metadata(coefficient, 0)

    def test_wrong_grid_authority_and_date_are_rejected(self):
        adapter, coefficient = fixture()
        coefficient.transformer_current_authority_sha256 = '1' * 64
        with self.assertRaisesRegex(ValueError, 'CURRENT_AUTHORITY'):
            adapter.validate_coefficient_metadata(coefficient, 0)
        metadata = dict(adapter.metadata, day='2025-05-02')
        with self.assertRaisesRegex(ValueError, 'MAY01'):
            GridAdapter(adapter.inventory, adapter.control_names, metadata)

    def test_missing_original_line_is_rejected(self):
        adapter, _ = fixture()
        incomplete = replace(adapter.inventory, branch_names=adapter.inventory.branch_names[1:])
        with self.assertRaisesRegex(ValueError, 'ALL_ACTIVE_SOURCE_ELEMENTS'):
            incomplete.validate()

    def test_supply_is_blocked_before_accessing_coefficients(self):
        adapter, _ = fixture()
        with self.assertRaises(ExecutionHold):
            adapter.supply(None)

    def test_missing_transformer_kva_limit_is_rejected(self):
        adapter, coefficient = fixture()
        coefficient.transformer_ratings = (None,) * len(coefficient.branch_names)
        with self.assertRaisesRegex(ValueError, 'PCS_KVA_LIMITS'):
            adapter.validate_coefficient_metadata(coefficient, 0)


if __name__ == '__main__':
    unittest.main()
