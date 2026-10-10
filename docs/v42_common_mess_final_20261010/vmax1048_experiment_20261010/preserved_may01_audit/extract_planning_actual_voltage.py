"""Read preserved canary coordinates; write an external audit, with Native zero."""
from pathlib import Path
from hashlib import sha256
from datetime import datetime, timezone
import csv
import json
import re

import numpy as np
import pandas as pd
from scipy import sparse

OUT = Path(__file__).resolve().parent
CASE = Path(r'D:\v42_common_mess_campaign_20261010_01\dates\B2\2025-05-01\attempts\common_u4_v1_01')
MODEL = CASE / 'output'
FRESH = MODEL / 'OPERATIONS' / 'FRESH' / 'fresh'
INPUT = Path(r'D:\MobileESS_V42\runtime\v42_may_campaign\candidate_20261009_implementation01\inputs\B2\2025-05-01')


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def record(path, expected=None):
    value = dict(path=str(path), sha256=sha256(path.read_bytes()).hexdigest(), bytes=path.stat().st_size)
    if expected is not None:
        assert value['sha256'] == expected, f'SOURCE_SHA_DRIFT:{path}'
    return value


def arrays(path):
    with np.load(path, allow_pickle=False) as data:
        return {key:data[key].copy() for key in data.files}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = read(FRESH / 'OPENDSS_OUTPUT_MANIFEST.json')
    receipt = read(MODEL / 'OPERATIONS' / 'ACTUAL' / 'ACTUAL_FIXED_REPLAY_RECEIPT.json')
    certificate = read(MODEL / 'BEST_STRICT_UB_CERTIFICATE.json')
    identity = read(MODEL / 'SCIENTIFIC_CASE_IDENTITY.json')
    native = read(INPUT / 'NATIVE_INPUT.json')
    source_receipt = read(MODEL / 'OPERATIONS' / 'ACTUAL_SOURCE' / 'ACTUAL_SOURCE_RECEIPT.json')
    raw = arrays(FRESH / 'OPENDSS_PHASE_ARRAYS.npz')
    violations = read(FRESH / 'OPENDSS_VIOLATIONS.json')['rows']
    upper = {v['upper_limit'] for v in violations if v['kind'] == 'VOLTAGE'}
    lower = {v['lower_limit'] for v in violations if v['kind'] == 'VOLTAGE'}
    assert upper == {1.05} and lower == {.95}
    low, high = .95, 1.05
    low2, high2 = .9025, 1.1025
    assert certificate['strict_raw_C3A_and_FULL_integer_and_binary_pattern_exact'] is True
    assert receipt['MESS_PQ'] == 'FROZEN_OPTIMIZED_PLANNING'
    assert receipt['MESS_Planning']['sha256'] == receipt['MESS_frozen_trajectory']['sha256']
    sources = [record(FRESH / name, row['sha256']) for name,row in manifest['files'].items()]
    sources.append(record(MODEL / 'BEST_STRICT_UB_POINT.npz', certificate['point_file_sha256']))
    sources.append(record(Path(source_receipt['source']['path']), source_receipt['source']['sha256']))
    coefficients_path = Path(native['grid_outputs']['planning_coefficients']['path'].replace('C:', 'D:', 1))
    sensitivity_path = Path(native['grid_outputs']['voltage']['path'].replace('C:', 'D:', 1))
    sources.append(record(coefficients_path, native['grid_outputs']['planning_coefficients']['sha256']))
    sources.append(record(sensitivity_path, native['grid_outputs']['voltage']['sha256']))
    coefficients, sensitivity = arrays(coefficients_path), arrays(sensitivity_path)
    planning_nodes = coefficients['node_names'].astype(str)
    actual_nodes = raw['node_names'].astype(str)
    assert np.array_equal(planning_nodes, sensitivity['node_names'].astype(str))
    assert np.array_equal(planning_nodes, actual_nodes)
    assert np.array_equal(raw['node_phases'], np.array(['ABC'[int(n.rsplit('.', 1)[1])-1] for n in actual_nodes]))
    assert raw['voltage_pu'].shape == (96, 386) and raw['convergence'].all()
    point = arrays(MODEL / 'BEST_STRICT_UB_POINT.npz')['point']
    axes = arrays(MODEL / 'CURRENT_C2_AXES.npz')
    aliases = read(MODEL / 'CURRENT_C2_ALIASES.json')
    full_d = arrays(MODEL / 'FULL_DATA.npz')
    full_A = sparse.load_npz(MODEL / 'FULL_A.npz').tocsr()
    lifted = np.zeros(identity['transport']['compact_columns'])
    lifted[axes['columns']] = point
    for definition in reversed(aliases):
        lifted[definition['column']] = definition['constant'] + sum(
            weight * lifted[int(column)] for column,weight in definition['terms'].items())
    full_point = lifted[:len(full_d['names'])].copy()
    discrete = full_point[full_d['types'] != 'C']
    assert np.array_equal(discrete, np.rint(discrete))
    assert np.isin(full_point[full_d['types'] == 'B'], [0., 1.]).all()
    source_controls = np.asarray(read(MODEL / 'FIXED_AIDC_ANCHOR.json')['controls']).copy()
    control_names = read(MODEL / 'FIXED_AIDC_ANCHOR.json')['control_names']
    assert control_names == sensitivity['control_names'].astype(str).tolist()
    columns = {str(name):i for i,name in enumerate(full_d['names'])}
    for t in range(96):
        for j,name in enumerate(control_names):
            site = name.split('[', 1)[1][:-1]
            if name.startswith('mess_p_kw['):
                source_controls[t,j] = full_point[columns[f'injection_P[{site},{t}]']]
            elif name.startswith('mess_q_kvar['):
                source_controls[t,j] = full_point[columns[f'injection_Q[{site},{t}]']]
    independent_v2 = coefficients['voltage_constant'] + np.einsum('tcn,tc->tn', coefficients['voltage_matrix'], source_controls)
    planning_v2 = np.empty((96, len(planning_nodes)))
    lower_v2 = np.empty_like(planning_v2)
    row_axes = {}
    for i,name in enumerate(full_d['row_names'].astype(str)):
        match = re.fullmatch(r'voltage_(lower|upper)\[(\d+),(\d+)\]', name)
        if not match:
            continue
        kind,t,n = match[1],int(match[2]),int(match[3])
        assert (kind,t,n) not in row_axes
        row_axes[kind,t,n] = i
        assert full_d['sense'][i] == ('>' if kind == 'lower' else '<')
        value = (full_A.getrow(i) @ full_point).item() + (low2 if kind == 'lower' else high2) - full_d['rhs'][i]
        (lower_v2 if kind == 'lower' else planning_v2)[t,n] = value
    assert len(row_axes) == 96 * 386 * 2
    lower_upper_error = float(np.max(abs(planning_v2-lower_v2)))
    coefficient_error = float(np.max(abs(planning_v2-independent_v2)))
    assert lower_upper_error < 1e-12 and coefficient_error < 1e-12
    assert np.all(planning_v2 > 0)
    planning_v = np.sqrt(planning_v2)
    actual_v = raw['voltage_pu']
    cells = np.argwhere((actual_v < low) | (actual_v > high))
    observed = {(int(t), str(actual_nodes[n]), str(raw['node_phases'][n]), float(actual_v[t,n])) for t,n in cells}
    recorded = {(r['slot'],r['asset'],r['phase'],r['value']) for r in violations if r['kind'] == 'VOLTAGE'}
    assert observed == recorded and len(cells) == 19
    exogenous = pd.read_parquet(Path(source_receipt['source']['path']))
    assert len(exogenous) == 96
    timestamps = [pd.Timestamp(t).isoformat() for t in exogenous['ts_fixed_aest_end']]
    rows = []
    for t,n in cells:
        a,p = float(actual_v[t,n]),float(planning_v[t,n])
        limit = high if a > high else low
        rows.append(dict(day='2025-05-01', arm='B2', node_phase=str(actual_nodes[n]),
            node=str(actual_nodes[n]).rsplit('.',1)[0], phase=str(raw['node_phases'][n]),
            node_axis_0based=int(n), slot_1based=int(t)+1, slot_0based=int(t),
            timestamp_interval_end_aest=timestamps[t], Actual_V_pu=a, Planning_V_pu=p,
            violated_limit_pu=limit, direction='UPPER' if a > high else 'LOWER',
            Actual_exceedance_pu=max(a-high,low-a), Actual_minus_Planning_pu=a-p,
            Planning_margin_to_violated_limit_pu=high-p if a > high else p-low,
            FULL_voltage_upper_row=row_axes['upper',int(t),int(n)],
            FULL_voltage_lower_row=row_axes['lower',int(t),int(n)]))
    csv_path = OUT / 'B2_MAY01_VOLTAGE_VIOLATIONS.csv'
    with csv_path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader();writer.writerows(rows)
    np.savez_compressed(OUT / 'B2_MAY01_PLANNING_ACTUAL_VOLTAGES.npz',
        node_names=planning_nodes, node_phases=raw['node_phases'],
        timestamps_interval_end_aest=np.asarray(timestamps), Planning_V_pu=planning_v,
        Planning_V_squared=planning_v2, Actual_V_pu=actual_v)
    sources.extend(record(MODEL / name) for name in ('SCIENTIFIC_CASE_IDENTITY.json',
        'CURRENT_C2_AXES.npz','CURRENT_C2_ALIASES.json','FULL_A.npz','FULL_DATA.npz',
        'FIXED_AIDC_ANCHOR.json','BEST_STRICT_UB_CERTIFICATE.json'))
    sources.extend((record(INPUT/'NATIVE_INPUT.json'),
        record(MODEL/'OPERATIONS'/'ACTUAL'/'ACTUAL_FIXED_REPLAY_RECEIPT.json'),
        record(MODEL/'OPERATIONS'/'ACTUAL_SOURCE'/'ACTUAL_SOURCE_RECEIPT.json')))
    for source in identity['transport_authority']['sources'].values():
        sources.append(record(Path(source['path']), source['sha256']))
    sources.extend(record(Path(r'D:\v42u4final')/relative) for relative in
        ('v42_m1_sparse/grid.py','v42_may01/prepare.py','v42_native/voltage.py'))
    report = dict(schema='V42_B2_MAY01_PRESERVED_PLANNING_ACTUAL_VOLTAGE_AUDIT_V1',
        generated_UTC=datetime.now(timezone.utc).isoformat(), scientific_case_sha=identity['case_sha'],
        source_commit=read(CASE / 'RESULT.json')['source_commit'],
        source_SHA=read(CASE / 'RESULT.json')['source_SHA'],
        Native_optimize_calls=0, OpenDSS_solve_calls=0, point_mutation_count=0,
        source_mutation_count=0, DSS_setting_changes=0, actual_band_pu=[low,high],
        Planning_band_pu=[low,high], coordinate_axis_exact_match=True,
        coordinate_proof='FULL voltage_[lower|upper][slot,node_index] labels use the native coefficient voltage_constant index; pinned planning/sensitivity node_names equal preserved Fresh node_names in exact order. Dot products use the C2-inverted original FULL strict point.',
        Planning_value_semantics='Original forecast affine squared-voltage row value, square-rooted to pu; not an AC Planning rerun.',
        timestamp_semantics='1-based slot; source-backed Actual ts_fixed_aest_end, fixed AEST UTC+10 interval end. Slot 1 is 00:15 and slot96 ends next-day00:00.',
        FULL_integer_and_binary_literal=True, original_lower_upper_v2_max_difference=lower_upper_error,
        independent_source_affine_v2_max_difference=coefficient_error,
        violation_count=len(rows), upper_violation_count=sum(r['direction']=='UPPER' for r in rows),
        lower_violation_count=sum(r['direction']=='LOWER' for r in rows),
        unique_node_phases=sorted({r['node_phase'] for r in rows}),
        worst_exceedance=max(rows,key=lambda r:r['Actual_exceedance_pu']),
        Planning_all_slots_Vmin_pu=float(planning_v.min()), Planning_all_slots_Vmax_pu=float(planning_v.max()),
        Actual_all_slots_Vmin_pu=float(actual_v.min()), Actual_all_slots_Vmax_pu=float(actual_v.max()),
        causal_scope='This coordinate comparison establishes where prediction and realized AC differ. It does not by itself isolate P, Q, exogenous forecast error, or autonomous control effects; unchanged Fresh counterfactuals provide that separate evidence.',
        csv=record(csv_path), arrays=record(OUT/'B2_MAY01_PLANNING_ACTUAL_VOLTAGES.npz'),
        sources=sources)
    (OUT / 'B2_MAY01_VOLTAGE_AUDIT.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({key:report[key] for key in ('violation_count','upper_violation_count',
        'lower_violation_count','worst_exceedance','Planning_all_slots_Vmin_pu',
        'Planning_all_slots_Vmax_pu','independent_source_affine_v2_max_difference')}, indent=2))


if __name__ == '__main__':
    main()
