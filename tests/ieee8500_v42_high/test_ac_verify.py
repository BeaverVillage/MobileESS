"""Adversarial evidence regressions: hidden nodes, second ends and nameplates."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np

from ieee8500_v42_high.common import REPORT, BALANCED_REPORT, PR193, read, rows
from ieee8500_v42_high.verify import VerificationError, audit_electrical_arrays, audit_axes, audit_slots, audit_ports, verify_case, verify_fresh, run


class SavedACVerifierTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = REPORT / 'ac/E1R_C0_BG0.750'
        cls.axes = read(cls.folder / 'AC_AXES.json')
        cls.receipt = read(cls.folder / 'RECEIPT.json')
        cls.slots = rows(cls.folder / 'SLOTS.csv')
        with np.load(cls.folder / 'AC_96.npz', allow_pickle=False) as z:
            cls.arrays = {key: z[key] for key in z.files}
        cls.inventory = read(PR193 / 'ORIGINAL_FEEDER_INVENTORY.json')
        cls.baseline = read(BALANCED_REPORT / 'ac/BALANCED_PLANNING/AC_AXES.json')

    def test_full_saved_source_case_passes_independent_arithmetic(self):
        result, ports = verify_case(self.folder, self.inventory, self.baseline)
        self.assertTrue(result['arithmetic_PASS'])
        self.assertTrue(result['grid_hard_PASS'])
        self.assertEqual(len(ports), 96 * 12)
        self.assertEqual(result['original_Triplex_count'], 1177)
        self.assertEqual(result['full_active_Line_objective_count'], 3698)
        self.assertFalse(result['Production_PASS'])

    def test_overvoltage_on_last_node_last_slot_is_not_hidden_by_maxima(self):
        changed = dict(self.arrays)
        changed['node_voltage_pu'] = self.arrays['node_voltage_pu'].copy()
        changed['node_voltage_pu'][95, -1] = np.nextafter(1.05, np.inf)
        result, _ = audit_electrical_arrays(self.axes, changed)
        self.assertEqual(result['overvoltage_cells'], 1)
        self.assertFalse(result['grid_electrical_limits_PASS'])
        with self.assertRaises(VerificationError):
            audit_slots(self.axes, changed, self.slots, self.receipt)

    def test_opposite_terminal_overload_is_checked_even_outside_objective(self):
        excluded = next(i for i, r in enumerate(self.axes['lines'])
                        if r['enabled'] and r['terminal'] == 2 and not r['objective_included'])
        changed = dict(self.arrays)
        changed['line_amps'] = self.arrays['line_amps'].copy()
        changed['line_rho'] = self.arrays['line_rho'].copy()
        changed['line_rho'][95, excluded] = 1.01
        changed['line_amps'][95, excluded] = 1.01 * self.axes['lines'][excluded]['normal_amps']
        result, _ = audit_electrical_arrays(self.axes, changed)
        self.assertEqual(result['line_overload_cells'], 1)
        self.assertFalse(result['grid_electrical_limits_PASS'])
        self.assertLess(result['canonical_daily_rho'], 1.)

    def test_replacing_global_objective_with_primary_only_is_rejected(self):
        changed = copy.deepcopy(self.axes)
        for i, row in enumerate(changed['lines']):
            if row['group'] == 'Triplex':
                changed['objective_mask'][i] = False
                row['objective_included'] = False
        with self.assertRaises(VerificationError):
            audit_axes(changed, self.inventory, self.baseline)

    def test_current_rating_enlargement_is_rejected(self):
        changed = copy.deepcopy(self.axes)
        changed['lines'][-1]['normal_amps'] *= 2.
        with self.assertRaises(VerificationError):
            audit_axes(changed, self.inventory, self.baseline)

    def test_ct_nameplate_overload_is_independent_of_current_ratio(self):
        changed = dict(self.arrays)
        changed['transformer_winding_nameplate_kva_rho'] = self.arrays['transformer_winding_nameplate_kva_rho'].copy()
        changed['transformer_winding_nameplate_kva_rho'][95, -1] = 1.001
        result, _ = audit_electrical_arrays(self.axes, changed)
        self.assertEqual(result['CT_nameplate_overload_cells'], 1)
        self.assertFalse(result['grid_electrical_limits_PASS'])
        self.assertEqual(result['CT_current_overload_cells'], 0)

    def test_false_binding_phase_or_missing_slot_is_rejected(self):
        changed = copy.deepcopy(self.slots)
        changed[-1]['binding_local_node'] = '999'
        with self.assertRaises(VerificationError):
            audit_slots(self.axes, self.arrays, changed, self.receipt)
        with self.assertRaises(VerificationError):
            audit_slots(self.axes, self.arrays, self.slots[:-1], self.receipt)

    def test_mixed_layout_lv_port_keeps_its_small_interface_limit(self):
        ports = read(self.folder / 'PORT_96.json')
        for row in ports:
            row['port_mode'] = 'LV_SPLIT_240'
        receipt = dict(self.receipt, layout='M3')
        with np.load(self.folder / 'CUSTOMER_PV_PCC_96.npz', allow_pickle=False) as z:
            pq = {key: z[key].copy() for key in z.files}
        # A mixed layout's remaining LV site cannot inherit the 450kW MV limit.
        port = ports[-1]
        t, k = int(port['slot']), int(port['site'][3:]) - 1
        port.update(P_kw=5.5, Q_kvar=0., S_kva=5.5)
        port['per_conductor_PQ'] = [[2.75, 0.], [2.75, 0.]]
        if 'per_conductor_voltage_V' in port:
            volts = np.asarray(port['per_conductor_voltage_V'])
            port['per_conductor_A'] = (2750. / volts).tolist()
            port['I_max_A'] = max(port['per_conductor_A'])
        pq['PCC_PQ'][t, 12+k] = [5.5, 0.]
        with patch('ieee8500_v42_high.verify.read', return_value=ports):
            result, checked = audit_ports(self.folder, receipt, pq)
        self.assertFalse(result['port_all96_electrical_PASS'])
        self.assertEqual(result['port_electrical_violation_cells'], 1)
        self.assertTrue(all(row['port_P_limit_kw'] == 5. for row in checked))

    def test_six_research_ports_include_all_new_nodes_and_windings(self):
        axes = copy.deepcopy(self.axes)
        for k in range(1, 7):
            name = f'Transformer.high_mv_sta{k:02d}'
            for winding, kv in ((1, 12.47), (2, .48)):
                axes['winding_axes'].append(dict(element=name, winding=winding, normal_kva=750., nameplate_kva=750.))
                for conductor, node in enumerate((1, 2, 3, 0), start=1):
                    axes['transformers'].append(dict(element=name, winding=winding, conductor=conductor,
                        node=node, normal_amps=750. / (np.sqrt(3) * kv)))
            axes['nodes'].extend(f'high_mv_sta{k:02d}_lv.{node}' for node in (1, 2, 3))
        result = audit_axes(axes, self.inventory, self.baseline)
        self.assertEqual(result['added_research_CT_count'], 6)
        self.assertEqual(result['new_480V_node_count'], 18)
        axes['winding_axes'].pop()
        with self.assertRaises(VerificationError):
            audit_axes(axes, self.inventory, self.baseline)

    def test_fresh_boolean_control_evidence_requires_exact_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            first, fresh = Path(temporary)/'FIRST', Path(temporary)/'FIRST_FRESH'
            receipt = {key: self.receipt[key] for key in ('day', 'source', 'bg', 'layout', 'AIDC_input')}
            for folder in (first, fresh):
                folder.mkdir()
                np.savez(folder/'AC_96.npz', converged=np.ones(96, dtype=bool),
                         control_actions_done=np.ones(96, dtype=bool), control_queue_size=np.zeros(96, dtype=int))
                for name, value in [('AC_AXES.json', {'nodes': []}), ('CONTROL_STATES.json', []),
                                    ('INITIAL_CONTROL_STATE.json', {}), ('RECEIPT.json', receipt)]:
                    (folder/name).write_text(json.dumps(value), encoding='utf-8')
            self.assertTrue(verify_fresh(first, fresh)['PASS'])
            altered = np.ones(96, dtype=bool)
            altered[-1] = False
            np.savez(fresh/'AC_96.npz', converged=altered,
                     control_actions_done=np.ones(96, dtype=bool), control_queue_size=np.zeros(96, dtype=int))
            with self.assertRaises(VerificationError):
                verify_fresh(first, fresh)

    def test_report_scope_allows_new_subcases_and_rejects_prior_sealed_reports(self):
        with self.assertRaisesRegex(VerificationError, 'NO_COMPLETE_AC_CASES'):
            run(tags=['MISSING'], report_dir=REPORT/'MIXED_SUBCASE')
        with self.assertRaisesRegex(VerificationError, 'PRIOR_REPORT_WRITE_FORBIDDEN'):
            run(tags=['MISSING'], report_dir=BALANCED_REPORT/'MIXED_SUBCASE')

    def test_short_probe_cannot_be_promoted_to_a_96_slot_case(self):
        with patch('ieee8500_v42_high.verify.read', return_value={'slots': 2}):
            with self.assertRaisesRegex(VerificationError, 'NOT_A_FINAL_96_SLOT_CASE'):
                verify_case(self.folder, self.inventory, self.baseline)


if __name__ == '__main__':
    unittest.main()
