"""Validate the packaged May01 B0 evidence without power flow or optimization."""
from pathlib import Path
from collections import Counter
from decimal import Decimal
from datetime import datetime, timedelta
import csv
import hashlib
import json
import numpy as np

PACKAGE = Path(__file__).resolve().parents[1] / 'science/ieee8500_b0_may01_fine_scale'

def read(p):
    return json.loads(p.read_text(encoding='utf-8'))

def csvrows(p):
    with p.open(encoding='utf-8', newline='') as f:
        return list(csv.DictReader(f))

def check(condition, message):
    if not condition:
        raise ValueError(message)

def validate(root=PACKAGE):
    manifest = read(root / 'PACKAGE_MANIFEST.json')
    for r in manifest['files']:
        p = root / r['path']
        check(p.resolve().is_relative_to(root.resolve()), 'Manifest path escapes package')
        check(p.stat().st_size == r['bytes'], f'Size mismatch: {r["path"]}')
        check(hashlib.sha256(p.read_bytes()).hexdigest() == r['sha256'], f'SHA256 mismatch: {r["path"]}')
    rows = read(root / 'SCREEN_TABLE.json')
    result = read(root / 'SEARCH_RESULT.json')
    check([r['scale'] for r in rows] == [.57,.572,.574,.576,.577,.5775,.578,.579,.58], 'Unexpected candidates')
    keys = {'Vmin':'Vmin_pu','Vmax':'Vmax_pu','max_line_loading':'max_phase_line_loading_pu','transformer_current':'max_transformer_phase_current_pu','transformer_kVA':'max_transformer_winding_kva_pu'}
    reference = csvrows(root / 'scale_0.58/B0_96_SLOT_EXTREMA.csv')
    signatures = read(root / 'scale_0.58/STATIC_SPATIAL_CONSERVATION_AUDIT.json')['signatures']
    for r in rows:
        p = root / f'scale_{r["scale"]}'
        slots = csvrows(p / 'B0_96_SLOT_EXTREMA.csv')
        states = read(p / 'B0_CONTROL_STATES_96.json')
        check(len(slots) == len(states) == 96, 'Incomplete candidate')
        check(read(p / 'STATIC_SPATIAL_CONSERVATION_AUDIT.json')['signatures'] == signatures, 'Static/spatial drift')
        for key, field in keys.items():
            metric = (min if key == 'Vmin' else max)(float(x[field]) for x in slots)
            check(metric == r[key], f'{r["scale"]}: {key} does not match slot extrema')
        for t, (x, old, state) in enumerate(zip(slots, reference, states)):
            check(int(x['slot']) == t and x['converged'] == x['control_actions_complete'] == 'True', 'Unconverged/unsettled slot')
            check(state['slot'] == t and state['source_pu'] == 1.04, 'Wrong control timeline/source')
            check(all(reg['Vreg'] == 123.5 for reg in state['regulators']), 'Vreg changed')
            for k in ['PV_scheduled_kw','AIDC_P_scheduled_kw','AIDC_Q_scheduled_kvar','MESS_P_scheduled_kw','MESS_Q_scheduled_kvar']:
                check(float(x[k]) == float(old[k]), f'Changed injection: {k}')
            check(float(x['MESS_P_scheduled_kw']) == float(x['MESS_Q_scheduled_kvar']) == 0, 'MESS active')
            for k in ['native_P_scheduled_kw','native_Q_scheduled_kvar']:
                check(abs(float(x[k])/r['scale'] - float(old[k])/.58) < 1e-10, 'Nonuniform load scaling')
        ok = r['Vmin'] >= .95 and r['Vmax'] <= 1.05 and max(r['max_line_loading'],r['transformer_current'],r['transformer_kVA']) <= 1
        check(r['status'] == ('PASS' if ok else 'FAIL'), 'Wrong hard-limit status')
    good = [r for r in rows if r['status'] == 'PASS']
    bad = [r for r in rows if r['status'] == 'FAIL']
    check(result['MAX_FEASIBLE_TESTED_SCALE'] == max(r['scale'] for r in good), 'Wrong maximum tested feasible')
    check(result['FIRST_INFEASIBLE_TESTED_SCALE'] == min(r['scale'] for r in bad), 'Wrong first infeasible')
    check(Decimal(str(result['boundary_upper']))-Decimal(str(result['boundary_lower'])) == Decimal('.0005'), 'Wrong boundary resolution')
    selected = max((r for r in good if r['Vmin'] >= .9505), key=lambda r:(r['max_line_loading'],r['scale']))
    check(selected == result['selected'] and selected['scale'] == .574, 'Wrong robustness recommendation')
    check(result['RECOMMENDED_VMIN_MARGIN'] == selected['Vmin']-.95 and result['B1_B2_B3_runs'] == 0, 'Wrong margin or scope')
    daily = csvrows(root / 'csv/B0_0.574_DAILY_MAX_HEATMAP.csv')
    critical = csvrows(root / 'csv/B0_0.574_CRITICAL_TIME_HEATMAP.csv')
    summary = csvrows(root / 'csv/B0_0.574_HEATMAP_SUMMARY.csv')
    basecols = 'element_type element_id from_bus to_bus x_from y_from x_to y_to'.split()
    check(list(daily[0]) == basecols + 'data_status B0_element_max_loading max_terminal max_phase max_slot max_time_AEST'.split(), 'Wrong daily schema')
    check(list(critical[0]) == basecols + 'terminal phase data_status B0_loading_at_critical_time critical_slot critical_time_AEST'.split(), 'Wrong critical schema')
    check(list(summary[0]) == 'background_scale critical_slot critical_time_AEST critical_line critical_terminal critical_phase rho_max Vmin Vmax transformer_current_max transformer_kVA_max AC_status AIDC MESS'.split(), 'Wrong summary schema')
    check((len(daily),len(critical),len(summary)) == (3703,12317,1), 'Wrong export row counts')
    check(Counter(r['data_status'] for r in daily) == {'OK':3698,'DISABLED':5}, 'Wrong daily status coverage')
    check(Counter(r['data_status'] for r in critical) == {'OK':12312,'DISABLED':5}, 'Wrong critical status coverage')
    check(len({r['element_id'] for r in daily}) == 3703, 'Duplicate/missing physical lines')
    check(len({(r['element_id'],r['terminal'],r['phase']) for r in critical}) == 12317, 'Duplicate terminal/local-node rows')
    coords = read(root / 'inputs/GEOMETRY.json')['coordinates']
    with np.load(root / 'scale_0.574/B0_ALL_PHASE_ARRAYS.npz', allow_pickle=False) as z:
        a = z['line_current_loading_pu']; byline = {}; axes = {}
        check(a.shape == (96,12312) and np.isfinite(a).all(), 'Invalid raw line arrays')
        for j, text in enumerate(z['line_phase_axes']):
            name,term,bus,node = str(text).lower().split('|')
            byline.setdefault(name,[]).append(j); axes[name,term[1:],node[4:]] = j
        slot,j = np.unravel_index(a.argmax(),a.shape)
        check(slot == 75 and a[slot,j] == selected['max_line_loading'], 'Wrong system critical point')
        n,t,b,ph = str(z['line_phase_axes'][j]).lower().split('|')
        check((summary[0]['critical_line'],summary[0]['critical_terminal'],summary[0]['critical_phase']) == (n,t[1:],ph[4:]), 'Wrong critical summary witness')
        check(summary[0]['background_scale'] == '0.574' and summary[0]['AC_status'] == 'PASS' and summary[0]['AIDC'] == 'B0_REFERENCE_ON' and summary[0]['MESS'] == 'OFF', 'Wrong recommended policy')
        for records in [daily,critical]:
            for r in records:
                check([float(r['x_from']),float(r['y_from'])] == coords[r['from_bus']], 'From-coordinate altered')
                check([float(r['x_to']),float(r['y_to'])] == coords[r['to_bus']], 'To-coordinate altered')
        for r in daily:
            if r['data_status'] == 'DISABLED':
                check(r['B0_element_max_loading'] == '', 'Disabled line zero-filled'); continue
            value = float(r['B0_element_max_loading'])
            check(value == a[:,byline[r['element_id']]].max(), 'Incorrect daily maximum')
            check(value == a[int(r['max_slot']),axes[r['element_id'],r['max_terminal'],r['max_phase']]], 'Incorrect daily witness')
            expected_time = datetime.fromisoformat('2025-05-01T00:00:00+10:00') + timedelta(minutes=15*int(r['max_slot']))
            check(r['max_time_AEST'] == expected_time.isoformat(), 'Wrong daily witness time')
        for r in critical:
            check(r['critical_slot'] == '75' and r['critical_time_AEST'] == '2025-05-01T18:45:00+10:00', 'Wrong critical time')
            if r['data_status'] == 'DISABLED':
                check(r['B0_loading_at_critical_time'] == '', 'Disabled line zero-filled'); continue
            check(float(r['B0_loading_at_critical_time']) == a[slot,axes[r['element_id'],r['terminal'],r['phase']]], 'Incorrect critical loading')
        raw = {'rho_max':a.max(),'Vmin':z['voltage_pu'].min(),'Vmax':z['voltage_pu'].max(),'transformer_current_max':z['transformer_current_loading_pu'].max(),'transformer_kVA_max':z['transformer_winding_kva_loading_pu'].max()}
        for k,value in raw.items():
            check(float(summary[0][k]) == value, f'Incorrect recommended summary: {k}')
    print(f'PASS: {len(manifest["files"])} hashes; 9 candidates; 864 recorded slots; full recommended raw/CSV checks; 0 new scientific solves.')
    print('Other eight candidates: slot-summary/control validation; full raw arrays remain external with recorded hashes.')

if __name__ == '__main__':
    validate()
