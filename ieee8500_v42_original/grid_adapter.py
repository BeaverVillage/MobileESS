"""Data-only contract for IEEE8500 -> the original native/F3 grid API.

No DSS compile, coefficient generation, matrix allocation, or optimization occurs
here. Coverage must come from the new case's frozen inventory, including inactive
source elements. The old 87-axis screening responses cannot satisfy this schema.
The thermal authority scope and original A/M builders still need integration;
accepting metadata here is not a physical or mathematical feasibility certificate.
"""
from dataclasses import dataclass
from hashlib import sha256
import json
import math

from .hold import require_execution_approval


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _sha(value):
    _require(isinstance(value, str) and len(value) == 64 and
             all(c in '0123456789abcdef' for c in value), 'SHA256_REQUIRED')


@dataclass(frozen=True)
class GridInventory:
    node_names: tuple
    branch_names: tuple
    original_line_ids: tuple
    inactive_line_ids: tuple
    original_transformer_ids: tuple
    inactive_transformer_ids: tuple
    sta_transformer_ids: tuple
    pcs_current_axis: tuple
    source_sha: str
    mapping_sha: str
    current_authority_sha: str

    def validate(self):
        for key in ('source_sha', 'mapping_sha', 'current_authority_sha'):
            _sha(getattr(self, key))
        for key in ('node_names', 'branch_names', 'original_line_ids',
                    'inactive_line_ids', 'original_transformer_ids',
                    'inactive_transformer_ids', 'sta_transformer_ids', 'pcs_current_axis'):
            values = getattr(self, key)
            _require(isinstance(values, tuple) and len(values) == len(set(values)) and
                     all(isinstance(x, str) and x == x.lower() and x for x in values),
                     'UNIQUE_LOWERCASE_AXIS_REQUIRED:' + key)
        _require(bool(self.node_names), 'ALL_NODE_AXIS_REQUIRED')
        _require(len(self.original_line_ids) == 3703, 'ORIGINAL_3703_LINE_INVENTORY_REQUIRED')
        _require(len(self.original_transformer_ids) == 1190, 'ORIGINAL_1190_TRANSFORMERS_REQUIRED')
        _require(len(self.sta_transformer_ids) == 12, 'TWELVE_NEW_STA_TRANSFORMERS_REQUIRED')
        _require(len(self.pcs_current_axis) == 36, 'TWELVE_THREE_PHASE_PCS_CURRENT_AXES_REQUIRED')
        branches = {name.split('::', 1)[0] for name in self.branch_names}
        for kind, source, inactive in (
            ('line.', self.original_line_ids, self.inactive_line_ids),
            ('transformer.', self.original_transformer_ids, self.inactive_transformer_ids),
        ):
            source, inactive = set(source), set(inactive)
            _require(all(name.startswith(kind) for name in source), 'SOURCE_ELEMENT_CLASS_DRIFT')
            _require(inactive <= source and not (inactive & branches), 'INACTIVE_ELEMENT_AXIS_DRIFT')
            _require(source - inactive <= branches, 'ALL_ACTIVE_SOURCE_ELEMENTS_REQUIRED:' + kind)
        _require(not (set(self.sta_transformer_ids) & set(self.original_transformer_ids)),
                 'NEW_STA_TRANSFORMERS_MUST_BE_SEPARATE')
        _require(set(self.sta_transformer_ids) <= branches, 'STA_TRANSFORMER_CURRENT_AXES_REQUIRED')
        _require(set(self.pcs_current_axis) <= set(self.branch_names) and
                 all(name.startswith('transformer.pcs_') for name in self.pcs_current_axis),
                 'PCS_CURRENT_ROWS_MUST_NOT_ENTER_LINE_RHO_OBJECTIVE')

    @property
    def identity_sha(self):
        return sha256(json.dumps(vars(self), sort_keys=True,
                                 separators=(',', ':')).encode()).hexdigest()


class GridAdapter:
    """Supply unchanged coefficient objects, with explicit complete-case axes.

    The native builder uses demand-positive AIDC kW and injection-positive MESS
    kW/kvar, voltage squared pu, current/unchanged NormalAmps, and kW/kvar flow
    faces. The coefficient producer must perform that conversion and bind actual
    IEEE8500 input/anchor/tap/control identities; this class does not infer it.
    """
    def __init__(self, inventory, control_names, case_metadata):
        inventory.validate()
        self.inventory = inventory
        self.control_names = tuple(control_names)
        self.metadata = dict(case_metadata)
        _require(len(self.control_names) == 60 and len(set(self.control_names)) == 60,
                 'TWELVE_AIDC_AND_24_SERVICE_PQ_CONTROLS_REQUIRED')
        expected = ([f'aidc_load_kw[IDC{i:02d}]' for i in range(1, 13)] +
                    [f'{family}[{role}{i:02d}]' for family in ('mess_p_kw', 'mess_q_kvar')
                     for role in ('IDC', 'STA') for i in range(1, 13)])
        _require(set(self.control_names) == set(expected), 'ORIGINAL_CONTROL_NAMES_REQUIRED')
        _require(self.metadata.get('day') == '2025-05-01' and self.metadata.get('slots') == 96
                 and self.metadata.get('grid') == 'IEEE8500_BALANCED'
                 and self.metadata.get('inventory_sha') == inventory.identity_sha,
                 'IEEE8500_MAY01_FROZEN_CASE_REQUIRED')
        for key in ('inputs_sha', 'anchor_sha', 'policy_sha'):
            _sha(self.metadata.get(key))

    def validate_coefficient_metadata(self, coefficient, slot):
        """Small metadata checks only; do not scan or copy dense responses."""
        c = coefficient
        _require(c.slot == slot and tuple(c.control_names) == self.control_names,
                 'SLOT_CONTROL_AXIS_DRIFT')
        _require(tuple(c.node_names) == self.inventory.node_names and
                 tuple(c.branch_names) == self.inventory.branch_names,
                 'FULL_GRID_AXIS_REQUIRED')
        n, b, k = len(c.node_names), len(c.branch_names), len(self.control_names)
        for field, shape in (
            ('voltage_constant', (n,)), ('voltage_matrix', (k, n)),
            ('current_constant', (b,)), ('current_matrix', (k, b)),
            ('flow_p_constant', (b,)), ('flow_q_constant', (b,)),
            ('flow_p_matrix', (b, k)), ('flow_q_matrix', (b, k)),
            ('branch_limits', (b,)), ('current_denominators_A', (b,)),
            ('anchor', (k,)),
        ):
            _require(tuple(getattr(c, field).shape) == shape, 'COEFFICIENT_SHAPE:' + field)
        _require(len(c.transformer_ratings) == b, 'SOURCE_KVA_AXIS_REQUIRED')
        for name, rating in zip(c.branch_names, c.transformer_ratings):
            if name.startswith('transformer.'):
                _require(isinstance(rating, (int, float)) and math.isfinite(rating) and rating > 0,
                         'ALL_TRANSFORMER_AND_PCS_KVA_LIMITS_REQUIRED')
        _sha(c.coefficient_sha256)
        _require(c.transformer_current_authority_sha256 == self.inventory.current_authority_sha,
                 'IEEE8500_CURRENT_AUTHORITY_REQUIRED')
        _require(getattr(c, 'ieee8500_case_metadata', None) == self.metadata,
                 'COEFFICIENT_INPUT_POLICY_ANCHOR_BINDING_REQUIRED')

    def supply(self, coefficients):
        # Supplying actual 96-slot coefficients is part of execution, not Mock QA.
        require_execution_approval('IEEE8500_COEFFICIENT_SUPPLY')
        _require(len(coefficients) == 96, 'FULL_96_SLOT_RESPONSE_REQUIRED')
        for slot, coefficient in enumerate(coefficients):
            self.validate_coefficient_metadata(coefficient, slot)
        return coefficients
