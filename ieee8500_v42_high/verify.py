"""Independent arithmetic and source-identity checks over saved AC evidence.

No AC solver, dispatch optimizer, producer summary routine or campaign process
is imported. Grid security is distinct from equipment/GIS/QoS qualification.
"""
from __future__ import annotations

import argparse
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import numpy as np

from .common import ROOT, REPORT, SOURCE, PARENT, PR193, BALANCED_REPORT, AEMO_REPORT, read, rows, write, table, sha

CORE = ('line_amps', 'line_rho', 'node_voltage_pu', 'transformer_amps',
        'transformer_current_rho', 'transformer_winding_nameplate_kva_rho')
ARTIFACT_PREFIXES = ('ieee8500_v42/', 'ieee8500_v42_aemo/', 'ieee8500_v42_balanced/',
    'docs/ieee8500_v42_single_case/', 'docs/ieee8500_v42_aemo_voltage_rebuild/',
    'docs/ieee8500_v42_balanced_case/', 'tests/ieee8500_v42/',
    'tests/ieee8500_v42_aemo/', 'tests/ieee8500_v42_balanced/')
JOINT_NAMESPACE = 'ieee8500_v42_joint_pcc_reselection'
REUSE_PROTOCOL = 'FULL96_EVIDENCE_SHA_REUSE_V1'


def is_joint_case(folder):
    return JOINT_NAMESPACE in Path(folder).resolve().parts


def audit_case_date(folder, receipt):
    if is_joint_case(folder):
        require(receipt.get('day') == '2025-05-01', 'JOINT_RESEARCH_MAY01_ONLY')


class VerificationError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise VerificationError(message)


def close(value, expected, tolerance=1e-10, label='NUMERIC_DRIFT'):
    error = float(np.max(np.abs(np.asarray(value) - np.asarray(expected))))
    require(np.isfinite(error) and error <= tolerance, f'{label}: {error:.12g}')
    return error


def bool_field(value):
    if isinstance(value, bool):
        return value
    require(str(value).lower() in ('true', 'false'), f'INVALID_BOOLEAN:{value}')
    return str(value).lower() == 'true'


def audit_electrical_arrays(axes, arrays):
    """Check every node and both-end conductor, independently of CSV maxima."""
    dimensions = dict(line_amps=len(axes['lines']), line_rho=len(axes['lines']),
        node_voltage_pu=len(axes['nodes']), transformer_amps=len(axes['transformers']),
        transformer_current_rho=len(axes['transformers']),
        transformer_winding_nameplate_kva_rho=len(axes['winding_axes']))
    for key in CORE:
        require(key in arrays, f'MISSING_FULL_AXIS:{key}')
        require(arrays[key].shape == (96, dimensions[key]), f'FULL_AXIS_SHAPE:{key}')
        require(np.isfinite(arrays[key]).all(), f'NONFINITE_FULL_AXIS:{key}')
        require((arrays[key] >= 0).all(), f'NEGATIVE_MAGNITUDE:{key}')
    for key in ('source_kw_kvar', 'loss_kw_kvar'):
        if key in arrays:
            require(arrays[key].shape == (96, 2) and np.isfinite(arrays[key]).all(), f'RAW_PQ_SHAPE_OR_FINITE:{key}')
    for key in ('converged', 'control_actions_done', 'control_queue_size'):
        if key in arrays:
            require(arrays[key].shape == (96,) and np.isfinite(arrays[key]).all(), f'RAW_CONTROL_SHAPE_OR_FINITE:{key}')
            if key == 'control_queue_size':
                require((arrays[key] >= 0).all() and np.equal(arrays[key], np.floor(arrays[key])).all(), 'INVALID_CONTROL_QUEUE_SIZE')
            else:
                require(np.isin(arrays[key], [False, True]).all(), f'INVALID_RAW_CONTROL_BOOLEAN:{key}')
    line_rating = np.array([r['normal_amps'] for r in axes['lines']], float)
    tx_rating = np.array([r['normal_amps'] for r in axes['transformers']], float)
    require((line_rating > 0).all() and (tx_rating > 0).all(), 'NONPOSITIVE_ORIGINAL_RATING')
    line_error = close(arrays['line_rho'], arrays['line_amps'] / line_rating, 1e-12, 'LINE_RHO_DENOMINATOR')
    tx_error = close(arrays['transformer_current_rho'], arrays['transformer_amps'] / tx_rating,
                     1e-12, 'CT_CURRENT_DENOMINATOR')
    raw_winding = arrays.get('transformer_winding_complex_kva')
    winding_error = None
    if raw_winding is not None:
        require(raw_winding.shape == (96, len(axes['winding_axes'])) and np.isfinite(raw_winding).all(),
                'WINDING_COMPLEX_POWER_SHAPE_OR_FINITE')
        nameplate = np.array([r['nameplate_kva'] for r in axes['winding_axes']], float)
        winding_error = close(arrays['transformer_winding_nameplate_kva_rho'], np.abs(raw_winding) / nameplate,
                              1e-12, 'CT_NAMEPLATE_DENOMINATOR')
    volts = arrays['node_voltage_pu']
    violations = dict(undervoltage_cells=int((volts < .95).sum()), overvoltage_cells=int((volts > 1.05).sum()),
        line_overload_cells=int((arrays['line_rho'] > 1.).sum()),
        CT_current_overload_cells=int((arrays['transformer_current_rho'] > 1.).sum()),
        CT_nameplate_overload_cells=int((arrays['transformer_winding_nameplate_kva_rho'] > 1.).sum()))
    require(len(axes['objective_mask']) == len(axes['lines']), 'OBJECTIVE_MASK_AXIS')
    mask = np.asarray(axes['objective_mask'], bool)
    require(mask.any(), 'EMPTY_CANONICAL_GLOBAL_OBJECTIVE')
    maxima = arrays['line_rho'][:, mask].max(1)
    result = dict(**violations, grid_electrical_limits_PASS=not sum(violations.values()),
        line_rho_arithmetic_error=line_error, CT_current_rho_arithmetic_error=tx_error,
        CT_nameplate_rho_arithmetic_error=winding_error,
        CT_raw_winding_power_evidence_available=raw_winding is not None,
        canonical_daily_rho=float(maxima.max()), full_both_end_rho=float(arrays['line_rho'].max()),
        Vmin=float(volts.min()), Vmax=float(volts.max()),
        every_original_and_new_node_checked=True, all_both_terminal_conductors_checked=True)
    return result, maxima


def original_parent_terminals(inventory):
    """Reconstruct source-rooted orientation from original topology and reactor."""
    adjacency = defaultdict(set)
    for record in inventory['lines'] + inventory['transformers']:
        if not record['enabled']:
            continue
        first = record['buses'][0].split('.')[0].lower()
        for other in record['buses'][1:]:
            second = other.split('.')[0].lower()
            if first != second:
                adjacency[first].add(second)
                adjacency[second].add(first)
    # This unchanged original reactor appears in Transformers.dss and is the
    # source-to-HV edge excluded from original Line/Transformer inventory.
    source_text = (SOURCE / 'Transformers.dss').read_text(encoding='utf-8-sig')
    require('new reactor.hvmv_sub_hsb' in source_text.lower(), 'ORIGINAL_SOURCE_REACTOR_MISSING')
    adjacency['sourcebus'].add('hvmv_sub_hsb')
    adjacency['hvmv_sub_hsb'].add('sourcebus')
    depth, queue = {'sourcebus': 0}, deque(['sourcebus'])
    while queue:
        bus = queue.popleft()
        for child in adjacency[bus]:
            if child not in depth:
                depth[child] = depth[bus] + 1
                queue.append(child)
    parents = {}
    for record in inventory['lines']:
        first, second = [b.split('.')[0].lower() for b in record['buses']]
        a, b = depth.get(first), depth.get(second)
        parents[record['element'].lower()] = 2 if a is not None and b is not None and b < a else 1
    return parents


def audit_axes(axes, inventory, baseline_axes):
    require(axes['lines'] == baseline_axes['lines'], 'ORIGINAL_LINE_WIRING_RATING_AXIS_CHANGED')
    require(len({r['element'] for r in axes['lines']}) == 3703, 'ORIGINAL_LINE_COUNT_CHANGED')
    require(len({r['element'] for r in axes['lines'] if r['group'] == 'Triplex'}) == 1177, 'TRIPLEX_COUNT_CHANGED')
    require(len(axes['nodes']) == len(set(axes['nodes'])), 'DUPLICATE_NODE_AXIS')
    original_nodes = set(baseline_axes['nodes'])
    require(original_nodes <= set(axes['nodes']) and len(original_nodes) == 8531, 'ORIGINAL_NODE_AXIS_LOST')
    original_txs = {r['element'].lower() for r in inventory['transformers']}
    kept_axes = [r for r in axes['transformers'] if r['element'].lower() in original_txs]
    kept_windings = [r for r in axes['winding_axes'] if r['element'].lower() in original_txs]
    require(kept_axes == baseline_axes['transformers'], 'ORIGINAL_CT_CURRENT_RATINGS_CHANGED')
    require(kept_windings == baseline_axes['winding_axes'], 'ORIGINAL_CT_NAMEPLATES_CHANGED')
    added_txs = {r['element'].lower() for r in axes['transformers']} - original_txs
    require(len(original_txs) == 1190 and 0 <= len(added_txs) <= 12, 'UNEXPECTED_TRANSFORMER_ADDITION')
    require(all(name.startswith('transformer.high_mv_sta') for name in added_txs), 'UNDECLARED_NEW_TRANSFORMER')
    new_nodes = set(axes['nodes']) - original_nodes
    require(len(new_nodes) == 3 * len(added_txs), 'NEW_480V_NODE_COUNT')
    require(all(node.startswith('high_mv_sta') and '_lv.' in node for node in new_nodes), 'UNDECLARED_NEW_NODE')
    if added_txs:
        new_windings = [r for r in axes['winding_axes'] if r['element'].lower() in added_txs]
        require(len(new_windings) == 2 * len(added_txs), 'NEW_PORT_ALL_WINDINGS_NOT_CAPTURED')
        require(all(r['nameplate_kva'] == 750 and r['normal_kva'] == 750 for r in new_windings),
                'NEW_PORT_TX_RATING_DIFFERS_FROM_750KVA_DESIGN')
    parents = original_parent_terminals(inventory)
    expected = np.array([bool(r['enabled'] and r['node'] in (1, 2, 3)
        and r['terminal'] == parents[r['element'].lower()]) for r in axes['lines']])
    require(np.array_equal(expected, np.asarray(axes['objective_mask'], bool)), 'CANONICAL_PARENT_OBJECTIVE_MASK_CHANGED')
    require(np.array_equal(expected, np.array([r['objective_included'] for r in axes['lines']])),
            'OBJECTIVE_AXIS_METADATA_MASK_DISAGREES')
    require(len({r['element'] for r in axes['lines'] if r['objective_included']}) == 3698,
            'GLOBAL_ACTIVE_LINE_OBJECTIVE_TRUNCATED')
    return dict(original_Line_count=3703, original_Triplex_count=1177, original_CT_count=1190,
        added_research_CT_count=len(added_txs), original_node_count=8531, new_480V_node_count=len(new_nodes),
        full_active_Line_objective_count=3698, independently_reconstructed_global_parent_mask_PASS=True)


def audit_slots(axes, arrays, slot_rows, receipt):
    require(len(slot_rows) == 96 and [int(r['slot']) for r in slot_rows] == list(range(96)), 'MISSING_OR_DUPLICATE_TIME_SLOT')
    mask = np.asarray(axes['objective_mask'], bool)
    for t, row in enumerate(slot_rows):
        require(row['day'] == receipt['day'] and row['source'] == receipt['source'], 'CASE_DATE_OR_SOURCE_DRIFT')
        expected_time = datetime.fromisoformat(receipt['day']).replace(tzinfo=timezone(timedelta(hours=10))) + timedelta(minutes=15*t)
        require(datetime.fromisoformat(row['interval_start']) == expected_time, 'EXACT_AEST_96_TIME_AXIS')
        binding = int(np.argmax(np.where(mask, arrays['line_rho'][t], -np.inf)))
        axis = axes['lines'][binding]
        require(row['binding_line'] == axis['element'] and int(row['binding_local_node']) == axis['node']
            and int(row['binding_parent_terminal']) == axis['terminal'] and int(row['binding_conductor']) == axis['conductor'],
            f'BINDING_LINE_OR_PHASE_DRIFT:{t}')
        quantities = dict(rho_max=float(arrays['line_rho'][t, mask].max()),
            full_both_terminal_conductor_rho_max=float(arrays['line_rho'][t].max()),
            Vmin=float(arrays['node_voltage_pu'][t].min()), Vmax=float(arrays['node_voltage_pu'][t].max()),
            transformer_current_rho_max=float(arrays['transformer_current_rho'][t].max()),
            transformer_nameplate_kva_rho_max=float(arrays['transformer_winding_nameplate_kva_rho'][t].max()),
            undervoltage_cells=int((arrays['node_voltage_pu'][t] < .95).sum()),
            overvoltage_cells=int((arrays['node_voltage_pu'][t] > 1.05).sum()),
            full_line_overload_cells=int((arrays['line_rho'][t] > 1.).sum()),
            transformer_current_overload_cells=int((arrays['transformer_current_rho'][t] > 1.).sum()),
            transformer_nameplate_overload_cells=int((arrays['transformer_winding_nameplate_kva_rho'][t] > 1.).sum()))
        for group in ('Primary', 'Triplex', 'Secondary'):
            select = mask & np.array([r['group'] == group for r in axes['lines']])
            quantities[group + '_rho_max'] = float(arrays['line_rho'][t, select].max()) if select.any() else 0.
        quantities['voltage_violation_cells'] = quantities['undervoltage_cells'] + quantities['overvoltage_cells']
        for key, value in quantities.items():
            close(float(row[key]), value, label=f'SLOT_CSV_FULL_AXIS_DRIFT:{t}:{key}')
        settled = bool_field(row['converged']) and bool_field(row['controls_settled'])
        hard = settled and sum(quantities[k] for k in ('voltage_violation_cells', 'full_line_overload_cells',
            'transformer_current_overload_cells', 'transformer_nameplate_overload_cells')) == 0
        require(bool_field(row['hard_constraints_PASS']) == hard, f'SLOT_PASS_FLAG_DRIFT:{t}')
        if 'converged' in arrays:
            require(bool(arrays['converged'][t]) == bool_field(row['converged']), 'RAW_CONVERGENCE_DRIFT')
        if 'control_actions_done' in arrays:
            require(bool(arrays['control_actions_done'][t]) == bool_field(row['controls_settled']), 'RAW_CONTROL_SETTLEMENT_DRIFT')
        if 'control_queue_size' in arrays:
            require(int(arrays['control_queue_size'][t]) == 0, 'UNSETTLED_CONTROL_QUEUE')
    return dict(all96_converged=all(bool_field(r['converged']) for r in slot_rows),
        all96_controls_settled=all(bool_field(r['controls_settled']) for r in slot_rows),
        control_queue_evidence_available='control_queue_size' in arrays,
        all_slot_CSV_vs_full_arrays_PASS=True)


def audit_control_states(folder, inventory):
    control = rows(folder / 'CONTROL_STATES_96.csv')
    require(len(control) == 96 * 31, 'ALL96_CONTROL_STATE_COUNT')
    regs = {r['name']: r for r in inventory['regcontrols']}
    caps = {r['name']: r for r in inventory['capcontrols']}
    transformer = {r['element'].lower(): r for r in inventory['transformers']}
    states = read(folder / 'CONTROL_STATES.json')
    require(len(states) == 96, 'ALL96_FULL_CONTROL_JSON_MISSING')
    for t in range(96):
        current = [r for r in control if int(r['slot']) == t]
        require(len(current) == 31, f'CONTROL_SLOT_DUPLICATES:{t}')
        require(len({(r['kind'], r['name']) for r in current}) == 31, 'DUPLICATE_CONTROL_ELEMENT')
        require(all(bool_field(r['enabled']) for r in current), 'ORIGINAL_CONTROLLER_DISABLED')
        require(sum(r['kind'] == 'RegControl' for r in current) == 12
            and sum(r['kind'] == 'CapControl' for r in current) == 9
            and sum(r['kind'] == 'Capacitor' for r in current) == 10, 'CONTROL_OBJECT_COUNTS')
        for r in current:
            if r['kind'] == 'RegControl':
                original = regs[r['name']]
                winding = transformer['transformer.' + original['transformer']]['windings'][int(original['properties']['TapWinding']) - 1]
                close(float(r['Vreg']), 123.5, label='P5_VREG_CHANGED')
                close(float(r['min_tap']), winding['mintap'], label='ORIGINAL_MIN_TAP_CHANGED')
                close(float(r['max_tap']), winding['maxtap'], label='ORIGINAL_MAX_TAP_CHANGED')
                require(winding['mintap'] <= float(r['tap_ratio']) <= winding['maxtap'], 'ORIGINAL_TAP_LIMIT_VIOLATION')
                close(float(r['delay_seconds']), float(original['properties']['Delay']), label='REG_DELAY_CHANGED')
                close(states[t]['taps'][r['name']][int(original['properties']['TapWinding']) - 1],
                      float(r['tap_ratio']), label='JSON_CSV_TAP_DRIFT')
            elif r['kind'] == 'CapControl':
                original = caps[r['name']]['properties']
                close(float(r['delay_seconds']), float(original['Delay']), label='CAP_DELAY_CHANGED')
                close(float(r['delay_off_seconds']), float(original['DelayOff']), label='CAP_DELAYOFF_CHANGED')
            else:
                cap_states = json.loads(r['states'])
                require(all(value in (0, 1) for value in cap_states), 'CAP_SWITCH_STATE_INVALID')
                require(states[t]['capacitors'][r['name']] == cap_states, 'JSON_CSV_CAP_STATE_DRIFT')
                if r['name'] == 'capbank3':
                    require(cap_states == [0], 'P5_CAPBANK3_SWITCH_CHANGED')
    return dict(all96_original_RegControl_CapControl_Capacitor_count_PASS=True,
        all12_Vreg_123p5_PASS=True, original_tap_limits_delays_PASS=True, CAPBank3_off_all96=True)


def audit_parameters(folder, inventory, axes=None, preservation_proof=None):
    snapshot_path = folder / 'PARAMETER_SNAPSHOT.json'
    if not snapshot_path.exists():
        return dict(live_source_controller_parameter_snapshot_available=False,
            live_P5_parameter_readback_complete=False, limitation='Legacy case records producer assertion and control CSV; no full live snapshot')
    snapshot = read(snapshot_path)
    live = snapshot.get('inventory', snapshot.get('live_inventory'))
    require(isinstance(live, dict), 'LIVE_PARAMETER_INVENTORY_MISSING')
    close(snapshot['source_pu'], 1.04, label='P5_SOURCE_VOLTAGE_CHANGED')
    if preservation_proof is None:
        actual_sha = {p.name: sha(p) for p in SOURCE.iterdir() if p.is_file()}
    else:
        require(preservation_proof.get('parent_commit') == PARENT
                and preservation_proof.get('original_31_DSS_source_bytes_equal') is True,
                'REUSED_SOURCE_PROOF_NOT_QUALIFIED')
        actual_sha = preservation_proof['original_DSS_SHA256']
    require(actual_sha == inventory['source_sha256'], 'ORIGINAL_DSS_SOURCE_SHA_CHANGED')
    require(snapshot['source_sha256'] == actual_sha, 'LIVE_SOURCE_SNAPSHOT_SHA_DRIFT')
    overlay = folder.parent.parent / 'overlays/P5.dss'
    require(sha(overlay) == sha(AEMO_REPORT / 'overlays/P5.dss'), 'P5_OVERLAY_BYTES_CHANGED')
    require(snapshot['P5_overlay_sha256'] == sha(overlay), 'SNAPSHOT_P5_SHA_DRIFT')
    original_lines = {r['element'].lower(): r for r in inventory['lines']}
    live_lines = {r['element'].lower(): r for r in live['lines']}
    require(set(original_lines) == set(live_lines), 'ORIGINAL_LINE_SET_CHANGED')
    for name, original in original_lines.items():
        for key in ('buses', 'ncond', 'nphase', 'nterm', 'normal_amps', 'emergency_amps', 'enabled', 'linecode', 'length', 'units'):
            require(original[key] == live_lines[name][key], f'ORIGINAL_LINE_PARAMETER_CHANGED:{name}:{key}')
    live_txs = {r['element'].lower(): r for r in live['transformers']}
    for original in inventory['transformers']:
        name = original['element'].lower()
        require(name in live_txs, 'ORIGINAL_CT_DELETED')
        current = live_txs[name]
        for key in ('buses', 'ncond', 'nphase', 'nterm', 'enabled', 'normal_hkva', 'emergency_hkva'):
            require(current[key] == original[key], f'ORIGINAL_CT_PARAMETER_CHANGED:{name}:{key}')
        require(len(current['windings']) == len(original['windings']), 'ORIGINAL_CT_WINDING_EVIDENCE_TRUNCATED')
        for before, after in zip(original['windings'], current['windings']):
            for key in ('winding', 'kv', 'kva_nameplate', 'delta', 'mintap', 'maxtap', 'numtaps', 'normal_kva'):
                require(before[key] == after[key], f'ORIGINAL_CT_WINDING_PARAMETER_CHANGED:{name}:{key}')
    original_regs = {r['name']: r for r in inventory['regcontrols']}
    current_regs = {r['name']: r for r in live['regcontrols']}
    require(set(original_regs) == set(current_regs), 'REGCONTROL_SET_CHANGED')
    for name, original in original_regs.items():
        for key, value in original['properties'].items():
            if key not in ('VReg', 'TapNum'):
                require(current_regs[name]['properties'][key] == value, f'ORIGINAL_REG_PROPERTY_CHANGED:{name}:{key}')
        close(float(current_regs[name]['properties']['VReg']), 123.5, label='LIVE_VREG_CHANGED')
    original_caps = {r['name']: r for r in inventory['capcontrols']}
    current_caps = {r['name']: r for r in live['capcontrols']}
    require(set(original_caps) == set(current_caps), 'CAPCONTROL_SET_CHANGED')
    for name, original in original_caps.items():
        require(current_caps[name]['properties'] == original['properties'], f'CAPCONTROL_PROPERTY_CHANGED:{name}')
    original_banks = {r['name']: r for r in inventory['capacitors']}
    current_banks = {r['name']: r for r in live['capacitors']}
    require(set(original_banks) == set(current_banks), 'CAPACITOR_BANK_SET_CHANGED')
    require('cmatrix' not in (SOURCE/'Capacitors.dss').read_text(encoding='utf-8-sig').lower(),
            'CAPACITOR_MATRIX_DEFINITION_REQUIRES_EXPLICIT_VERIFICATION')
    for name, original in original_banks.items():
        current = current_banks[name]
        for key in ('buses', 'kvar', 'kv'):
            require(current[key] == original[key], f'ORIGINAL_CAPACITOR_NAMEPLATE_CHANGED:{name}:{key}')
        for key, value in original['properties'].items():
            # Source banks use kvar/kV, not the alternate CMatrix definition.
            # Its getter contains nondeterministic tiny values in this engine.
            if key not in ('States', 'CMatrix'):
                require(current['properties'][key] == value, f'ORIGINAL_CAPACITOR_PROPERTY_CHANGED:{name}:{key}')
    added = [r for name, r in live_txs.items() if name not in {r['element'].lower() for r in inventory['transformers']}]
    require(all(r['element'].lower().startswith('transformer.high_mv_sta') for r in added),
            'LIVE_UNDECLARED_NEW_TRANSFORMER')
    for tx in added:
        require(tx['element'].lower().startswith('transformer.high_mv_sta') and tx['nphase'] == 3
                and tx['nterm'] == 2 and tx['ncond'] == 4 and len(tx['windings']) == 2,
                'NEW_PORT_TX_STRUCTURE')
        require(tx['normal_hkva'] == tx['emergency_hkva'] == 750, 'NEW_PORT_TX_NORMAL_OR_EMERGENCY_CHANGED')
        for w, kv, delta in zip(tx['windings'], (12.47, .48), (True, False)):
            close(w['kv'], kv, label='NEW_PORT_TX_KV_CHANGED')
            require(w['delta'] == delta and w['kva_nameplate'] == 750, 'NEW_PORT_TX_CONNECTION_OR_KVA_CHANGED')
            require(w['normal_kva'] == 750, 'NEW_PORT_TX_WINDING_NORMAL_CHANGED')
            close(w['normal_line_amps'], 750 / (np.sqrt(3) * kv), 1e-8, 'NEW_PORT_TX_CURRENT_NAMEPLATE_BASIS')
    if axes is not None:
        added_names = {r['element'].lower() for r in added}
        actual_axes = [r for r in axes['transformers'] if r['element'].lower() in added_names]
        expected_axes = []
        for tx in added:
            require(len(tx['node_order']) == tx['nterm'] * tx['ncond'], 'NEW_PORT_TX_NODE_ORDER_TRUNCATED')
            for w in tx['windings']:
                for c in range(tx['ncond']):
                    expected_axes.append(dict(element=tx['element'], winding=w['winding'], conductor=c+1,
                        node=tx['node_order'][(w['winding']-1)*tx['ncond']+c], normal_amps=w['normal_line_amps']))
        require(actual_axes == expected_axes, 'NEW_PORT_ALL_WINDING_CONDUCTOR_AXES_OR_RATINGS_CHANGED')
        axis_names = {r['element'].lower() for r in axes['transformers']} - {
            r['element'].lower() for r in inventory['transformers']}
        require(axis_names == added_names, 'NEW_PORT_LIVE_SNAPSHOT_AXIS_SET_DRIFT')
    return dict(live_source_controller_parameter_snapshot_available=True, live_P5_parameter_readback_complete=True,
        original_DSS_SHA_identity=True, all_original_line_CT_parameters_PASS=True,
        all_original_RegControl_except_P5_Vreg_parameters_PASS=True, all_original_CapControl_properties_PASS=True,
        all_original_capacitor_operating_nameplate_properties_PASS=True,
        inactive_capacitor_CMatrix_readback_excluded=True,
        source_disk_SHA_recomputed=preservation_proof is None,
        prior_original_source_proof_reused=preservation_proof is not None,
        added_750kVA_transformer_readback_count=len(added), P5_overlay_sha256=sha(overlay))


def audit_customers_power(folder, axes, arrays, receipt, slots):
    data_path = Path(receipt['AIDC_input']['path'])
    require(data_path.is_file() and sha(data_path) == receipt['AIDC_input']['sha256'], 'FROZEN_INPUT_SHA_DRIFT')
    with np.load(data_path, allow_pickle=False) as z:
        data = {k: z[k] for k in z.files}
    with np.load(folder / 'CUSTOMER_PV_PCC_96.npz', allow_pickle=False) as z:
        pq = {k: z[k] for k in z.files}
    expected_shapes = dict(customer_PQ=(96, 1177, 2), customer_legs=(96, 1177, 2, 2),
        PV_PQ=(96, 2354, 2), PCC_PQ=(96, 24, 2), balance_PQ=(96, 2), capacitor_PQ=(96, 2))
    for key, shape in expected_shapes.items():
        require(pq[key].shape == shape and np.isfinite(pq[key]).all(), f'POWER_FULL_AXIS_SHAPE_OR_FINITE:{key}')
    customers = read(BALANCED_REPORT / 'BALANCED_CUSTOMER_RECORDS.json')
    pv_records = read(BALANCED_REPORT / 'UNBALANCED_CUSTOMER_RECORDS.json')
    node_index = {n.lower(): i for i, n in enumerate(axes['nodes'])}
    fixed = np.array([r['status'] == 'fixed' for r in customers])
    base = np.array([[r['kw'], r['kvar']] for r in customers])
    factors = np.broadcast_to(float(receipt['bg']) * data['gross_factor'][:, None], (96, 1177)).copy()
    factors[:, fixed] = float(receipt['bg'])
    nominal = base[None, :, :] * factors[:, :, None]
    require(int(fixed.sum()) == 24, 'ORIGINAL_FIXED_CUSTOMER_COUNT_CHANGED')
    require(not np.ptp(nominal[:, fixed], axis=0).any(), 'FIXED_CUSTOMER_TIME_SHAPE_ADDED')
    require(all(r['model'] == 1 for r in customers), 'UNSUPPORTED_OR_CHANGED_CUSTOMER_MODEL')
    hot_volts = np.array([arrays['node_voltage_pu'][:, [node_index[r['buses'][0].split('.')[0].lower() + '.1'],
                    node_index[r['buses'][0].split('.')[0].lower() + '.2']]] for r in customers]).transpose(1, 0, 2)
    low = np.array([r['vminpu_load_characteristic'] for r in customers])[None, :, None]
    high = np.array([r['vmaxpu_load_characteristic'] for r in customers])[None, :, None]
    vfactor = np.where(hot_volts < low, (hot_volts / low)**2, np.where(hot_volts > high, (hot_volts / high)**2, 1.))
    customer_error = close(pq['customer_legs'], nominal[:, :, None, :] / 2 * vfactor[:, :, :, None],
                           1e-5, 'BALANCED_CUSTOMER_MODEL_OR_HOT_SPLIT_DRIFT')
    close(pq['customer_PQ'], pq['customer_legs'].sum(2), 1e-9, 'CUSTOMER_TOTAL_LEG_SUM')
    capacity = np.array([r['kw'] for r in pv_records]) * float(read(ROOT / 'ieee8500_v42_aemo/data/historical/SCREENING_RULE_PR62.json')['PV_ratio'])
    pv_voltage = np.column_stack([arrays['node_voltage_pu'][:, node_index[r['buses'][0].lower()]] for r in pv_records]) * .208 / np.sqrt(3) / .12
    pvfactor = np.where(pv_voltage < .88, (pv_voltage / .88)**2, np.where(pv_voltage > 1.05, (pv_voltage / 1.05)**2, 1.))
    solar_expected = data['pv_factor'][:, None] * capacity[None, :] * pvfactor
    pv_error = close(pq['PV_PQ'][:, :, 0], solar_expected, 1e-5, 'PV_CAPACITY_CHARACTERISTIC_OR_SOURCE_DRIFT')
    close(pq['PV_PQ'][:, :, 1], np.zeros((96, 2354)), 1e-5, 'PV_REACTIVE_INJECTION_DRIFT')
    expected_pcc = np.stack((data['PCC_P_kw'], data['PCC_Q_kvar']), axis=-1)
    pcc_error = close(pq['PCC_PQ'][:, :12], expected_pcc, 1e-5, 'AIDC_PCC_INPUT_READBACK_DRIFT')
    source = np.array([[float(r['source_kw']), float(r['source_kvar'])] for r in slots])
    loss = np.array([[float(r['loss_kw']), float(r['loss_kvar'])] for r in slots])
    if 'source_kw_kvar' in arrays:
        close(arrays['source_kw_kvar'], source, label='SOURCE_PQ_RAW_CSV_DRIFT')
    if 'loss_kw_kvar' in arrays:
        close(arrays['loss_kw_kvar'], loss, label='LOSS_PQ_RAW_CSV_DRIFT')
    independently_balanced = source - (pq['customer_PQ'].sum(1) + pq['PCC_PQ'].sum(1)
        - pq['PV_PQ'].sum(1) + pq['capacitor_PQ'] + loss)
    close(independently_balanced, pq['balance_PQ'], 1e-9, 'INDEPENDENT_POWER_BALANCE_DRIFT')
    balance_error = float(np.abs(independently_balanced).max())
    require(balance_error < 1e-4, 'AC_POWER_BALANCE_FAILURE')
    for t, r in enumerate(slots):
        for key, actual in [('nominal_customer_P_kw', nominal[t, :, 0].sum()),
                            ('nominal_customer_Q_kvar', nominal[t, :, 1].sum()),
                            ('actual_customer_P_kw', pq['customer_PQ'][t, :, 0].sum()),
                            ('actual_customer_Q_kvar', pq['customer_PQ'][t, :, 1].sum()),
                            ('actual_PV_kw', pq['PV_PQ'][t, :, 0].sum()),
                            ('AIDC_P_kw', pq['PCC_PQ'][t, :12, 0].sum()),
                            ('MESS_consumption_P_kw', pq['PCC_PQ'][t, 12:, 0].sum())]:
            close(float(r[key]), actual, 1e-8, f'POWER_CSV_SUM_DRIFT:{t}:{key}')
    return dict(customer_hot_leg_model_error_kw_kvar=customer_error, PV_characteristic_error_kw=pv_error,
        AIDC_PCC_readback_error_kw_kvar=pcc_error, independent_power_balance_error_kw_kvar=balance_error,
        Fixed_customers=24, Variable_customers=1153, source_input_SHA_identity=True,
        GPU_capacity_violation_cells=int((data['total_gpu'] > data['capacities'][None, :] + 1e-9).sum()),
        source_and_loss_raw_evidence_available='source_kw_kvar' in arrays and 'loss_kw_kvar' in arrays), pq


def audit_ports(folder, receipt, pq):
    ports = read(folder / 'PORT_96.json')
    require(len(ports) == 96 * 12, 'ALL96_12PORT_READBACK_COUNT')
    observed = set()
    result = []
    for r in ports:
        t, site = int(r['slot']), r['site']
        require((t, site) not in observed and 0 <= t < 96, 'PORT_READBACK_DUPLICATE_OR_TIME')
        observed.add((t, site))
        k = int(site[3:]) - 1
        close([r['P_kw'], r['Q_kvar']], pq['PCC_PQ'][t, 12 + k], 1e-9, 'PORT_PCC_READBACK_DRIFT')
        S = float(np.hypot(r['P_kw'], r['Q_kvar']))
        close(r['S_kva'], S, label='PCS_APPARENT_POWER_DRIFT')
        close(r['I_max_A'], max(r['per_conductor_A']), label='PCS_CURRENT_MAX_DRIFT')
        phase_power = np.asarray(r['per_conductor_PQ'])
        close(phase_power.sum(0), [r['P_kw'], r['Q_kvar']], 1e-9, 'PCS_ALL_PHASE_POWER_SUM')
        if 'per_conductor_voltage_V' in r:
            close(np.hypot(phase_power[:, 0], phase_power[:, 1]),
                  np.asarray(r['per_conductor_voltage_V']) * np.asarray(r['per_conductor_A']) / 1000,
                  1e-8, 'PCS_EACH_LEG_OR_PHASE_S_EQUALS_V_TIMES_I')
        layout = receipt['layout']
        mode = r.get('port_mode', 'LV_SPLIT_240' if layout == 'L0' else 'MV_DEDICATED_480V')
        require(mode in ('LV_SPLIT_240', 'MV_DEDICATED_480V'), 'UNKNOWN_STA_PORT_MODE')
        if mode == 'LV_SPLIT_240':
            limits = dict(P=5., Q=3., S=6., I=27.)
            require(phase_power.shape == (2, 2) and len(r['per_conductor_A']) == 2, 'SPLIT_PHASE_TWO_HOT_LEGS_REQUIRED')
            close(r['per_conductor_A'][0], r['per_conductor_A'][1], 1e-8, 'SPLIT_PHASE_LEG_CURRENT_IMBALANCE')
        else:
            p_limit = {'M1': 150., 'M2': 300., 'M3': 450.}.get(layout)
            require(p_limit is not None, 'UNKNOWN_MV_PORT_INTERFACE_LIMIT')
            limits = dict(P=p_limit, Q=600., S=600., I=600. / (np.sqrt(3) * .48))
            close(np.asarray(r['per_conductor_PQ'])[:3],
                  np.broadcast_to(np.array([r['P_kw'], r['Q_kvar']]) / 3, (3, 2)), 1e-5,
                  'THREE_PHASE_PCS_NOT_BALANCED_OR_BPHASE_ONLY')
        violations = int(abs(r['P_kw']) > limits['P'] + 1e-5) + int(abs(r['Q_kvar']) > limits['Q'] + 1e-5)
        violations += int(S > limits['S'] + 1e-5) + int(r['I_max_A'] > limits['I'] + 1e-5)
        result.append(dict(stage=folder.name, slot=t, site=site, layout=layout, port_mode=mode, P_kw=r['P_kw'], Q_kvar=r['Q_kvar'],
            S_kva=S, maximum_conductor_A=r['I_max_A'], port_P_limit_kw=limits['P'], port_S_limit_kVA=limits['S'],
            port_I_limit_A=limits['I'], violations=violations, port_electrical_PASS=violations == 0,
            field_GIS_protection_equipment_qualified=False))
    require(observed == {(t, f'STA{k:02d}') for t in range(96) for k in range(1, 13)}, 'PORT_SITE_SET_CHANGED')
    return dict(port_electrical_violation_cells=sum(r['violations'] for r in result),
        port_all96_electrical_PASS=all(r['port_electrical_PASS'] for r in result)), result


def audit_phasors(folder, axes, arrays, inventory):
    path = folder / 'PHASOR_FORENSICS.npz'
    if not path.exists():
        return dict(focused_phasor_evidence_available=False)
    with np.load(path, allow_pickle=False) as z:
        ph = {k: z[k] for k in z.files}
    line_indices, node_indices = ph['line_indices'], ph['node_indices']
    close(np.abs(ph['line_complex_A']), arrays['line_amps'][:, line_indices], 1e-10, 'FOCUSED_PHASOR_CURRENT_DRIFT')
    node = {axes['nodes'][i].lower(): ph['node_complex_V'][:, j] for j, i in enumerate(node_indices)}
    originals = {r['element'].lower(): r for r in inventory['lines']}
    error = 0.
    for j, i in enumerate(line_indices):
        meta = axes['lines'][i]
        bus = originals[meta['element'].lower()]['buses'][meta['terminal'] - 1].split('.')[0].lower()
        volt = np.zeros(96, complex) if meta['node'] == 0 else node[bus + '.' + str(meta['node'])]
        error = max(error, close(volt * np.conj(ph['line_complex_A'][:, j]) / 1000.,
                                 ph['line_complex_kVA'][:, j], 1e-8, 'PHASOR_S_EQUALS_V_CONJ_I'))
    return dict(focused_phasor_evidence_available=True, focused_phasor_power_identity_error_kVA=error,
        focused_phasor_axis_count=len(line_indices), focused_phasors_claim_full_complex_network=False)


def verify_case(folder, inventory=None, baseline_axes=None, preservation_proof=None):
    folder = Path(folder)
    inventory = inventory or read(PR193 / 'ORIGINAL_FEEDER_INVENTORY.json')
    baseline_axes = baseline_axes or read(BALANCED_REPORT / 'ac/BALANCED_PLANNING/AC_AXES.json')
    axes, receipt = read(folder / 'AC_AXES.json'), read(folder / 'RECEIPT.json')
    require(receipt.get('slots') == 96, 'NOT_A_FINAL_96_SLOT_CASE')
    audit_case_date(folder, receipt)
    if is_joint_case(folder):
        input_path = Path(receipt['AIDC_input']['path']).resolve()
        authoritative = ROOT/'ieee8500_v42_high/data/facility/recomputed'/f"{receipt['capacity']}_{receipt['source']}_INPUTS.npz"
        require(input_path == authoritative.resolve(), 'JOINT_MAY01_AUTHORITATIVE_INPUT_REQUIRED')
    with np.load(folder / 'AC_96.npz', allow_pickle=False) as z:
        arrays = {k: z[k] for k in z.files}
    slots = rows(folder / 'SLOTS.csv')
    axes_result = audit_axes(axes, inventory, baseline_axes)
    electrical, maxima = audit_electrical_arrays(axes, arrays)
    slot_result = audit_slots(axes, arrays, slots, receipt)
    controls = audit_control_states(folder, inventory)
    parameters = audit_parameters(folder, inventory, axes, preservation_proof)
    powers, pq = audit_customers_power(folder, axes, arrays, receipt, slots)
    ports, port_rows = audit_ports(folder, receipt, pq)
    phasors = audit_phasors(folder, axes, arrays, inventory)
    close(receipt['rho_max'], maxima.max(), label='DAILY_RECEIPT_GLOBAL_OBJECTIVE_DRIFT')
    close(receipt['Vmin'], electrical['Vmin'], label='DAILY_VMIN_DRIFT')
    close(receipt['Vmax'], electrical['Vmax'], label='DAILY_VMAX_DRIFT')
    close(receipt['all96_power_balance_error'], powers['independent_power_balance_error_kw_kvar'],
          1e-9, 'DAILY_POWER_BALANCE_RECEIPT_DRIFT')
    grid_pass = electrical['grid_electrical_limits_PASS'] and slot_result['all96_converged'] and slot_result['all96_controls_settled']
    require(receipt['grid_hard_PASS'] == grid_pass, 'DAILY_GRID_PASS_FLAG_DRIFT')
    return dict(stage=folder.name, day=receipt['day'], source=receipt['source'], capacity=receipt['capacity'],
        bg=receipt['bg'], layout=receipt['layout'], arithmetic_PASS=True, grid_hard_PASS=grid_pass,
        **axes_result, **electrical, **slot_result, **controls, **parameters, **powers, **ports, **phasors,
        field_equipment_GIS_protection_PASS=False, full_QoS_schedule_certificate=False,
        Production_PASS=False, AC_array_sha256=sha(folder / 'AC_96.npz')), port_rows


def case_evidence_identity(folder):
    """Hash every consumed case artifact; never run AC or the prior source audit."""
    folder = Path(folder).resolve()
    receipt = read(folder/'RECEIPT.json')
    require(receipt.get('slots') == 96, 'NOT_A_FINAL_96_SLOT_CASE')
    audit_case_date(folder, receipt)
    names = ('RECEIPT.json', 'AC_AXES.json', 'AC_96.npz', 'SLOTS.csv',
             'CUSTOMER_PV_PCC_96.npz', 'CONTROL_STATES_96.csv', 'CONTROL_STATES.json',
             'INITIAL_CONTROL_STATE.json', 'PORT_96.json')
    files = {str(folder/name): sha(folder/name) for name in names}
    for name in ('PARAMETER_SNAPSHOT.json', 'PHASOR_FORENSICS.npz'):
        if (folder/name).is_file():
            files[str(folder/name)] = sha(folder/name)
    overlay = folder.parent.parent/'overlays/P5.dss'
    if overlay.is_file():
        files[str(overlay)] = sha(overlay)
    for key in ('AIDC_input', 'mapping'):
        if key in receipt:
            meta = receipt[key]
            path = Path(meta['path']).resolve()
            require(path.is_file() and sha(path) == meta['sha256']
                    and path.stat().st_size == meta['bytes'], f'REUSE_INPUT_OR_MAPPING_SHA_DRIFT:{key}')
            files[str(path)] = meta['sha256']
    return dict(protocol=REUSE_PROTOCOL, verifier_sha256=sha(Path(__file__)),
                folder=str(folder), files=files)


def verify_case_cached(folder, inventory=None, baseline_axes=None, preservation_proof=None, cache_path=None):
    """Reuse only same verifier and exact consumed evidence; changed bytes block reuse."""
    folder = Path(folder).resolve()
    cache_path = Path(cache_path) if cache_path is not None else folder.parent.parent/'AC_CASE_VERIFICATION_CACHE.json'
    identity = case_evidence_identity(folder)
    cache = read(cache_path) if cache_path.exists() else dict(protocol=REUSE_PROTOCOL, cases={})
    require(cache.get('protocol') == REUSE_PROTOCOL, 'VERIFICATION_CACHE_PROTOCOL_DRIFT')
    key = str(folder)
    existing = cache['cases'].get(key)
    if existing is not None and existing['identity'] == identity:
        digest = hashlib.sha256(json.dumps(existing['payload'], sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        require(digest == existing['payload_sha256'], 'CACHED_VERIFICATION_PAYLOAD_CHANGED')
        return existing['payload']['result'], existing['payload']['ports'], True
    require(existing is None, 'COMPLETED_CASE_EVIDENCE_CHANGED_REQUIRES_EXPLICIT_NEW_TAG')
    result, ports = verify_case(folder, inventory, baseline_axes, preservation_proof)
    payload = dict(result=result, ports=ports)
    cache['cases'][key] = dict(identity=identity, payload=payload,
        payload_sha256=hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest())
    write(cache_path, cache)
    return result, ports, False


def verify_fresh(first, fresh):
    """Require exact saved arrays, input and initial/trajectory control equality."""
    first, fresh = Path(first), Path(fresh)
    files = ('AC_96.npz', 'CUSTOMER_PV_PCC_96.npz', 'PHASOR_FORENSICS.npz')
    errors = {}
    for file in files:
        if not (first / file).exists():
            continue
        require((fresh / file).exists(), 'FRESH_EVIDENCE_FILE_MISSING')
        with np.load(first / file, allow_pickle=False) as a, np.load(fresh / file, allow_pickle=False) as b:
            require(a.files == b.files, 'FRESH_ARRAY_KEYS_CHANGED')
            for key in a.files:
                require(np.array_equal(a[key], b[key]), f'FRESH_NOT_EXACT:{file}:{key}')
                errors[file + ':' + key] = 0.
    require(read(first / 'AC_AXES.json') == read(fresh / 'AC_AXES.json'), 'FRESH_AXIS_DRIFT')
    require(read(first / 'CONTROL_STATES.json') == read(fresh / 'CONTROL_STATES.json'), 'FRESH_CONTROL_STATE_DRIFT')
    require(read(first / 'INITIAL_CONTROL_STATE.json') == read(fresh / 'INITIAL_CONTROL_STATE.json'), 'FRESH_INITIAL_CONTROL_STATE_DRIFT')
    snapshot_bit_exact = None
    if (first / 'PARAMETER_SNAPSHOT.json').exists():
        require((fresh / 'PARAMETER_SNAPSHOT.json').exists(), 'FRESH_PARAMETER_SNAPSHOT_MISSING')
        first_snapshot, fresh_snapshot = read(first / 'PARAMETER_SNAPSHOT.json'), read(fresh / 'PARAMETER_SNAPSHOT.json')
        snapshot_bit_exact = first_snapshot == fresh_snapshot
        require('cmatrix' not in (SOURCE/'Capacitors.dss').read_text(encoding='utf-8-sig').lower(),
                'FRESH_CAPACITOR_MATRIX_DEFINITION_UNSUPPORTED')
        for snapshot in (first_snapshot, fresh_snapshot):
            for r in snapshot.get('inventory', snapshot.get('live_inventory', {})).get('capacitors', []):
                r['properties'].pop('CMatrix', None)
        require(first_snapshot == fresh_snapshot,
                'FRESH_LIVE_PARAMETER_SNAPSHOT_DRIFT')
    a, b = read(first / 'RECEIPT.json'), read(fresh / 'RECEIPT.json')
    require(a['AIDC_input']['sha256'] == b['AIDC_input']['sha256'], 'FRESH_INPUT_SHA_DRIFT')
    require(a['day'] == b['day'] and a['source'] == b['source'] and a['bg'] == b['bg'] and a['layout'] == b['layout'],
            'FRESH_SCENARIO_CHANGED')
    return dict(first=first.name, fresh=fresh.name, PASS=True, saved_arrays_and_control_states_bit_exact=True,
        full_serialized_parameter_snapshot_equal=snapshot_bit_exact,
        effective_live_parameter_snapshot_equal=True if snapshot_bit_exact is not None else None,
        inactive_capacitor_CMatrix_strings_excluded=snapshot_bit_exact is not None,
        capacitor_alternate_definition_reference='https://opendss.epri.com/Properties12.html',
        maximum_absolute_errors=errors, fresh_source_input_sha256=a['AIDC_input']['sha256'],
        independent_context_basis='Reviewed HighEngine creates odd.NewContext and recompiles Master.dss for each run_day',
        independent_Actual_vs_Planning_control_state_replay=False)


def preserve_sources():
    """Parent Git content through checkout filters plus strict prior SHA seals.

    On Windows core.autocrlf converts tracked text bytes during checkout. Git's
    read-only hash-object filter is authoritative for parent content; the prior
    three manifest checks below separately require exact archived file bytes.
    """
    tree = subprocess.check_output(['git', 'ls-tree', '-r', '-z', PARENT], cwd=ROOT)
    selected = []
    for item in tree.split(b'\0'):
        if not item:
            continue
        metadata, raw_name = item.split(b'\t', 1)
        _, kind, blob = metadata.decode().split()
        name = raw_name.decode('utf-8')
        if kind == 'blob' and (name.startswith(ARTIFACT_PREFIXES) or name.startswith('v42')):
            selected.append((name, blob))
    changed, present = [], []
    for name, expected_blob in selected:
        path = ROOT / name
        if not path.is_file():
            changed.append(name + ':MISSING')
            continue
        require('\n' not in name and not name.startswith('"'), 'UNSUPPORTED_GIT_CHECK_PATH')
        present.append((name, expected_blob))
    paths = ('\n'.join(name for name, _ in present) + '\n').encode('utf-8')
    hashes = subprocess.check_output(['git', 'hash-object', '--stdin-paths'], cwd=ROOT,
        input=paths).decode().splitlines()
    raw_hashes = subprocess.check_output(['git', 'hash-object', '--no-filters', '--stdin-paths'], cwd=ROOT,
        input=paths).decode().splitlines()
    require(len(hashes) == len(raw_hashes) == len(present), 'GIT_PARENT_IDENTITY_CHECK_COUNT')
    raw_equal, filtered_equal = 0, 0
    for (name, expected), actual, raw in zip(present, hashes, raw_hashes):
        raw_equal += int(raw == expected)
        filtered_equal += int(raw != expected and actual == expected)
        if expected not in (actual, raw):
            changed.append(name + ':GIT_FILTERED_CONTENT_CHANGED')
    require(not changed, 'PARENT_SOURCE_OR_REPORT_CHANGED:' + str(changed[:8]))
    manifests = []
    for prefix in ('docs/ieee8500_v42_single_case', 'docs/ieee8500_v42_aemo_voltage_rebuild', 'docs/ieee8500_v42_balanced_case'):
        path = ROOT / prefix / 'ARTIFACT_SHA256_MANIFEST.json'
        manifest = read(path)
        changed_manifest = []
        for name, value in manifest['files'].items():
            target = ROOT / name
            if not target.is_file() or sha(target) != value['sha256'] or target.stat().st_size != value['bytes']:
                changed_manifest.append(name)
        require(not changed_manifest, 'PR193_196_197_SEAL_DRIFT:' + str(changed_manifest[:8]))
        manifests.append(dict(manifest=prefix + '/ARTIFACT_SHA256_MANIFEST.json', manifest_sha256=sha(path),
                              file_count=len(manifest['files']), all_file_SHA256_bytes_equal=True))
    inventory = read(PR193 / 'ORIGINAL_FEEDER_INVENTORY.json')
    actual_source = {p.name: sha(p) for p in SOURCE.iterdir() if p.is_file()}
    require(actual_source == inventory['source_sha256'], 'ORIGINAL_DSS_BYTES_CHANGED')
    return dict(parent_commit=PARENT, Git_filtered_blob_equal_file_count=len(selected),
        Git_check_uses_configured_checkout_filters=True,
        Git_raw_blob_bytes_equal_file_count=raw_equal, Git_checkout_filter_only_equal_file_count=filtered_equal,
        prior_PR193_PR196_PR197_manifests=manifests, original_DSS_SHA256=actual_source,
        original_31_DSS_source_bytes_equal=True, all_parent_namespace_Git_content_equal=True,
        all_prior_manifest_SHA256_and_file_bytes_equal=True,
        git_write_calls=0, campaign_write_calls=0, Native_calls=0)


def run(tags=None, skip_preservation=False, report_dir=None):
    report = Path(report_dir).resolve() if report_dir is not None else REPORT
    require(report.is_relative_to(ROOT.resolve()), 'REPORT_OUTPUT_OUTSIDE_AUTHORIZED_NEW_NAMESPACE')
    report_parts = report.relative_to(ROOT.resolve()).parts
    require(len(report_parts) >= 2 and report_parts[0] == 'docs' and report_parts[1].startswith('ieee8500_v42_'),
            'REPORT_OUTPUT_OUTSIDE_AUTHORIZED_NEW_NAMESPACE')
    require(not any(report.is_relative_to(p.resolve()) for p in (PR193, AEMO_REPORT, BALANCED_REPORT)),
            'PRIOR_REPORT_WRITE_FORBIDDEN')
    inventory = read(PR193 / 'ORIGINAL_FEEDER_INVENTORY.json')
    baseline = read(BALANCED_REPORT / 'ac/BALANCED_PLANNING/AC_AXES.json')
    folders = [report / 'ac' / tag for tag in tags] if tags else sorted((report / 'ac').iterdir())
    finished = [p for p in folders if (p / 'RECEIPT.json').is_file() and (p / 'AC_96.npz').is_file()]
    completed = [p for p in finished if read(p / 'RECEIPT.json').get('slots') == 96]
    excluded = [dict(stage=p.name, reason='Diagnostic evidence is not a final96-slot AC case')
                for p in finished if p not in completed]
    require(completed, 'NO_COMPLETE_AC_CASES')
    proof_path = REPORT/'SOURCE_PRESERVATION_INDEPENDENT.json'
    proof = read(proof_path) if skip_preservation else None
    require(not skip_preservation or proof.get('original_31_DSS_source_bytes_equal') is True,
            'PRIOR_SOURCE_PROOF_REUSE_REQUIRED')
    results, port_records, fresh, reused = [], [], [], []
    for folder in completed:
        result, ports, was_reused = verify_case_cached(folder, inventory, baseline, proof)
        results.append(result)
        port_records.extend(ports)
        reused.append(dict(stage=folder.name, prior_full96_arithmetic_verification_reused=was_reused))
        if folder.name.endswith('_FRESH'):
            fresh.append(verify_fresh(folder.with_name(folder.name[:-6]), folder))
        print(folder.name, 'saved-array arithmetic PASS; grid=', result['grid_hard_PASS'],
              'new480Vnodes=', result['new_480V_node_count'], flush=True)
    preservation = proof if skip_preservation else preserve_sources()
    table(report / 'AC_INDEPENDENT_VERIFICATION.csv', results)
    table(report / 'PORT_INDEPENDENT_SECURITY_96.csv', port_records)
    if preservation and not skip_preservation:
        write(report / 'SOURCE_PRESERVATION_INDEPENDENT.json', preservation)
    strict = [r for r in results if not r['stage'].startswith(('E1_', 'E1R_'))]
    strict_complete = all(r['CT_raw_winding_power_evidence_available'] and r['live_P5_parameter_readback_complete']
                          and r['control_queue_evidence_available'] and r['source_and_loss_raw_evidence_available']
                          for r in strict) if strict else False
    receipt = dict(arithmetic_PASS=True, cases=results, fresh=fresh, source_preservation=preservation,
        report_directory=str(report), excluded_diagnostics=excluded,
        case_evidence_reuse=reused, newly_verified_case_count=sum(not x['prior_full96_arithmetic_verification_reused'] for x in reused),
        reused_case_count=sum(x['prior_full96_arithmetic_verification_reused'] for x in reused),
        source_preservation_performed=not skip_preservation, source_preservation_reused=skip_preservation,
        source_preservation_prior_proof_path=str(proof_path) if skip_preservation else None,
        source_preservation_prior_proof_SHA256=sha(proof_path) if skip_preservation else None,
        strict_final_raw_evidence_complete=strict_complete, strict_case_count=len(strict),
        strict_evidence_case_rule='Every complete96-slot case except preserved E1/E1R historical screening',
        all_records_computation_valid=True, all_case_grid_security_PASS=all(r['grid_hard_PASS'] for r in results),
        interpretation='Failed physical screening cases are preserved; arithmetic_PASS does not mean all candidates grid_PASS',
        equipment_GIS_protection_UNVERIFIED=True, full_QoS_UNVERIFIED=True, Production_PASS=False,
        Actual_results_for_selection=0, additional_AC_solves=0, Native_calls=0)
    write(report / 'INDEPENDENT_VERIFICATION.json', receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tags', nargs='*')
    parser.add_argument('--report-dir', type=Path, help='New report namespace; defaults to high-impact report')
    parser.add_argument('--skip-preservation', action='store_true', help='Partial diagnostic; final run must include preservation')
    args = parser.parse_args()
    run(args.tags, args.skip_preservation, args.report_dir)


if __name__ == '__main__':
    main()
