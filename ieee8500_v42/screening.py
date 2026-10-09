"""96-slot real AC preselection diagnostics, never production optimization.

Original background is STATIC at 1.0. V42 forecast power varies over 96 slots.
An upstream MV equivalent does not certify a physical AIDC/MESS connection.
"""
from __future__ import annotations

import argparse
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
os.environ.setdefault('OMP_NUM_THREADS', '1')
from pathlib import Path
import numpy as np

from .ac import IEEE8500AC
from .capacity import build_candidate, capacity_audit, FIXED_AIDC, CAPACITY_SCALES
from .common import DATA, REPORT, read, write, table, receipt, sha
from .geometry import read_csv

NUMERICAL_TOLERANCE = 1e-9


def engine_with_services(tag):
    e = IEEE8500AC(output_dir=REPORT / 'diagnostics' / tag / 'dss')
    for site, bus in FIXED_AIDC.items():
        e.add_pcc(site, bus, 'MV_3PH')
    # Historical fixed-v3 reproduction uses the frozen original registry,
    # never whichever current-stage table is named FINAL_STA_MAPPING.
    for r in read_csv(DATA / 'geometry/ORIGINAL_24_LOCATION_ELECTRICAL_MAPPING.csv'):
        if r['location_role']=='STA':
            e.add_pcc(r['location_id'], r['ieee8500_bus'], 'MV_3PH')
    return e


def demand(candidate, slot):
    return {s: (float(candidate['P_kw'][slot, k]), float(candidate['Q_kvar'][slot, k]))
            for k, s in enumerate(candidate['sites'])}


def axes_document(e):
    return dict(lines=e.line_axes, nodes=e.node_axes, transformers=e.transformer_axes,
                winding_axes=e.transformer_winding_axes,
                objective_mask=e.objective_line_mask.tolist(),
                regcontrols=[r['name'] for r in e.inventory['regcontrols']],
                objective_contract=e.inventory['objective_contract'],
                original_object_inventory=e.inventory['counts'])


def one_day(candidate, tag, *, full_line_report=False, expected=None):
    e = engine_with_services(tag)
    folder = REPORT / 'diagnostics' / tag
    arrays, states, slots, taps, tap_rows, caps = [], [], [], [], [], []
    write(folder / 'AC_AXES.json', axes_document(e))
    stamps = read(DATA / 'v42_inputs/PLANNING_INPUT_BUNDLE.json')['forecast_inputs']['AEMO']['timestamps_96']
    line_rows = []
    grouped = {}
    for k, axis in enumerate(e.line_axes):
        grouped.setdefault(axis['element'], []).append(k)
    previous = {r['name']: 0 for r in e.inventory['regcontrols']}
    for t in range(96):
        snap = e.solve(background_scale=1.0, pcc_demand=demand(candidate, t), reset_controls=False)
        a = e.measurement_arrays()
        # Independent scalar snapshot and bulk arrays must describe the same axes.
        if not np.allclose(a['line_amps'], [r['amps'] for r in snap['lines']], atol=1e-9, rtol=0):
            raise ValueError('SCALAR_BULK_LINE_AXIS_DRIFT')
        if not np.allclose(a['node_voltage_pu'], [r['voltage_pu'] for r in snap['buses']], atol=1e-11, rtol=0):
            raise ValueError('SCALAR_BULK_NODE_AXIS_DRIFT')
        if not a['converged'] or not a['control_actions_done'] or a['control_queue_size']:
            raise ValueError('AC_OR_CONTROL_SETTLING_FAILED')
        for site, values in demand(candidate, t).items():
            actual = snap['pcc_actual'][site]
            if max(abs(actual['p_kw'] - values[0]), abs(actual['q_kvar'] - values[1])) > 1e-6:
                raise ValueError('V42_PCC_POWER_READBACK_FAILED:' + site)
        s = dict(slot=t, timestamp=stamps[t], **snap['summary'])
        slots.append(s)
        arrays.append(a)
        states.append(snap['control_state'])
        regs = {r['name']: r for r in snap['regcontrols']}
        ordered = [regs[r['name']] for r in e.inventory['regcontrols']]
        taps.append([r['tap_number'] for r in ordered])
        caps.append([tuple(r['states']) for r in snap['capacitors']])
        for r in ordered:
            tap_rows.append(dict(scope='PRESELECTION_B0_DIAGNOSTIC', case=tag, slot=t,
                regcontrol=r['name'], tap_number=r['tap_number'], tap_pu=r['tap_pu'], enabled=r['enabled'],
                settled_net_tap_steps=abs(r['tap_number'] - previous[r['name']]),
                vmin_pu=s['vmin_pu'], vmax_pu=s['vmax_pu'], converged=True, control_actions_done=True,
                source_pu=1.05, Vreg_source_unchanged=True, internal_control_events='NOT_OBSERVED'))
            previous[r['name']] = r['tap_number']
        if full_line_report:
            for element, indices in grouped.items():
                active = [k for k in indices if e.objective_line_mask[k]]
                if not active:
                    continue
                k = max(active, key=lambda x: a['line_rho'][x])
                axis = e.line_axes[k]
                line_rows.append(dict(case=tag, slot=t, timestamp=stamps[t], line=element,
                    group=axis['group'], objective_parent_terminal=axis['terminal'], local_node=axis['node'],
                    maximum_parent_phase_current_A=float(a['line_amps'][k]), original_NormalAmps=axis['normal_amps'],
                    rho_pu=float(a['line_rho'][k]), maximum_all_terminal_conductor_rho=float(a['line_rho'][indices].max())))
        if t % 16 == 15:
            write(REPORT / 'AC_RUN_PROGRESS.json', dict(case=tag, completed_slots=t+1, total_slots=96, Native_calls=0))
            print(tag, t + 1, '/96 real AC', flush=True)
    keys = ['line_amps', 'line_rho', 'node_voltage_pu', 'transformer_amps',
            'transformer_current_rho', 'transformer_winding_kva_rho', 'transformer_winding_nameplate_kva_rho',
            'source_kw_kvar', 'loss_kw_kvar']
    matrix = {key: np.array([a[key] for a in arrays]) for key in keys}
    matrix.update(regulator_taps=np.array(taps), timestamps=np.array(stamps),
                  PCC_P_kw=candidate['P_kw'], PCC_Q_kvar=candidate['Q_kvar'])
    np.savez_compressed(folder / 'AC_96.npz', **matrix)
    write(folder / 'CONTROL_STATES.json', states)
    write(folder / 'CAPACITOR_STATES.json', caps)
    write(folder / 'AC_SLOTS.json', slots)
    if full_line_report:
        table(REPORT / 'LINE_LOADING_REPORT.csv', line_rows)
    table(folder / 'REGCONTROL_TAP_VALIDATION.csv', tap_rows)
    table(folder / 'SLOT_ELECTRICAL_SUMMARY.csv', slots)
    rho = np.array([s['rho_max'] for s in slots])
    peak = int(rho.argmax())
    result = dict(scope='UPSTREAM_MV_EQUIVALENT_PRESELECTION_DIAGNOSTIC', case=tag,
        background_scale=1.0, background_time_series='ORIGINAL_STATIC_SNAPSHOT', PV_objects=0,
        capacity_scale=candidate['scale'], installed_GPU=sum(candidate['capacities'].values()), workload_scale=1.0,
        rho_max=float(rho.max()), peak_slot=peak, binding_line=slots[peak]['binding_line'],
        vmin_pu=min(s['vmin_pu'] for s in slots), vmax_pu=max(s['vmax_pu'] for s in slots),
        lowest_voltage_node=min(slots, key=lambda s: s['vmin_pu'])['vmin_node'],
        transformer_current_rho_max=max(s['transformer_current_rho_max'] for s in slots),
        transformer_nameplate_kva_rho_max=max(s['transformer_nameplate_kva_rho_max'] for s in slots),
        voltage_violation_cells=sum(s['node_voltage_violations_095_105'] for s in slots),
        line_overload_conductor_cells=sum(s['line_conductor_overloads'] for s in slots),
        transformer_overload_conductor_cells=sum(s['transformer_conductor_overloads'] for s in slots),
        transformer_nameplate_winding_overloads=sum(s['transformer_nameplate_winding_overloads'] for s in slots),
        maximum_power_balance_residual_kW=max(abs(s['balance_residual_kw']) for s in slots),
        maximum_power_balance_residual_kvar=max(abs(s['balance_residual_kvar']) for s in slots),
        converged_slots=96, controls_settled_slots=96, canonical_source_unchanged=e.verify_source_unchanged(),
        source_pu=1.05, feeder_Vreg_V=126.5, downstream_Vreg_V=125.0,
        physical_pcc_eligibility='NOT_VERIFIED', geometric_eligibility='FAIL_FIXED_AIDC_ANCHORS',
        AC_physical_feasible=all(s['node_voltage_violations_095_105'] == 0 and s['line_conductor_overloads'] == 0
            and s['transformer_conductor_overloads'] == 0 and s['transformer_nameplate_winding_overloads'] == 0 for s in slots),
        production_selected=False, Native_calls=0, full_model_builds=0, no_actual_truth_loaded=True,
        artifacts={name: receipt(folder / name) for name in ('AC_96.npz', 'AC_AXES.json', 'CONTROL_STATES.json', 'AC_SLOTS.json')})
    if expected is not None:
        comparisons = {}
        old = np.load(expected / 'AC_96.npz', allow_pickle=False)
        for key in keys + ['regulator_taps']:
            comparisons[key] = float(np.max(np.abs(matrix[key] - old[key])))
        result['independent_fresh_planning_replay'] = dict(
            PASS=max(comparisons.values()) < 1e-9, maximum_absolute_errors=comparisons,
            role='FRESH_PLANNING_INPUT_REPLAY_NOT_DDAY_ACTUAL', Planning_taps_imported=False)
        if not result['independent_fresh_planning_replay']['PASS']:
            raise ValueError('INDEPENDENT_FRESH_AC_REPLAY_FAILED')
    write(folder / 'AC_RECEIPT.json', result)
    return result


def run_screen(scales=(1.0,)):
    candidates = [build_candidate(s) for s in scales]
    capacity_audit(candidates)
    results = []
    taps = []
    for c in candidates:
        tag = 'capacity_' + str(c['scale']).replace('.', 'p')
        result = one_day(c, tag, full_line_report=c['scale'] == 1.0)
        results.append(result)
        taps.extend(read_csv(REPORT / 'diagnostics' / tag / 'REGCONTROL_TAP_VALIDATION.csv'))
    # A new engine receives inputs only; Planning tap state is never a replay input.
    if 1.0 in scales:
        c = next(c for c in candidates if c['scale'] == 1.0)
        fresh = one_day(c, 'fresh_capacity_1p0', expected=REPORT / 'diagnostics/capacity_1p0')
        write(REPORT / 'INDEPENDENT_FRESH_REPLAY.json', fresh)
        taps.extend(read_csv(REPORT / 'diagnostics/fresh_capacity_1p0/REGCONTROL_TAP_VALIDATION.csv'))
    table(REPORT / 'REGCONTROL_TAP_VALIDATION.csv', taps)
    flat = [{k:v for k,v in r.items() if not isinstance(v, (dict,list))} for r in results]
    for scale in CAPACITY_SCALES:
        if scale not in scales:
            flat.append(dict(case='capacity_' + str(scale).replace('.', 'p'), capacity_scale=scale,
                scope='NOT_RUN_SCALE_SELECTION_HELD_PENDING_ROOT_CAUSE_REVIEW', production_selected=False,
                Native_calls=0, full_model_builds=0))
    table(REPORT / 'SCALE_SCREENING.csv', flat)
    write(REPORT / 'SCREENING_STATUS.json', dict(
        cases=results, final_production_configuration=None, final_STA_mapping=None,
        final_selection_held_pending_user_review=True, scientific_feasibility_PASS=False,
        full_B0_B1_B2_B3_comparison_executed=False, DDay_Actual_executed=False))
    print('Real 96-slot diagnostic + independent fresh replay complete; selection remains HOLD.', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--scales', nargs='+', type=float, choices=CAPACITY_SCALES, default=[1.0])
    run_screen(tuple(parser.parse_args().scales))

