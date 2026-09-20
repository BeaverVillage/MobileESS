"""Verify the committed CSV package without numpy, solvers, or local raw data."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify(folder):
    manifest = json.loads((folder/'MANIFEST.json').read_text(encoding='utf-8'))
    require(manifest['date'] == '2025-05-01' and manifest['mess_count'] == 6, 'Wrong case')
    require(manifest['scientific_execution_count'] == 0, 'Scientific execution detected')
    tables = {}
    require(len(manifest['outputs']) == 13, 'Expected 13 CSV files')
    for name, metadata in manifest['outputs'].items():
        path = folder/name
        require(hashlib.sha256(path.read_bytes()).hexdigest() == metadata['sha256'], 'Hash mismatch: '+name)
        with path.open(encoding='utf-8-sig', newline='') as f:
            tables[name] = list(csv.DictReader(f))
        require(len(tables[name]) == metadata['rows'], 'Row count: '+name)
        require(all(None not in r and all(v not in (None, '', 'nan', 'NaN', 'Infinity', '-Infinity') for v in r.values()) for r in tables[name]), 'Malformed/missing field: '+name)
        require(all(n in manifest['sources'] for n in metadata['sources']), 'Unknown source: '+name)
    summary = tables['POLICY_RESULT_SUMMARY.csv']
    require([r['policy'] for r in summary] == ['B0', 'B1', 'B2', 'B3'], 'Policy identity/order')
    order = {}
    for scope in ('planning', 'dayahead_ac', 'realized_ac'):
        values = [float(r[scope+'_rho_max']) for r in summary]
        order[scope] = all(a > b for a, b in zip(values, values[1:]))
        for r, value in zip(summary, values):
            require(int(r[scope+'_rank']) == 1+sum(v < value for v in values), 'Invalid rank: '+scope)
            require(math.isclose(float(r[scope+'_reduction_vs_B0_pct']), 100*(values[0]-value)/values[0], abs_tol=1e-10), 'Invalid reduction: '+scope)
    require(order == {'planning': True, 'dayahead_ac': False, 'realized_ac': True}, 'Wrong historical scope ordering')
    for file, scope in [('MAY01_MAX_LOADING_TIMESERIES.csv','realized_ac'), ('MAY01_DAYAHEAD_MAX_LOADING_TIMESERIES.csv','dayahead_ac')]:
        rows = tables[file]
        require(len(rows) == 96 and len({r['time'] for r in rows}) == 96, 'Time horizon: '+file)
        require([int(r['interval_index']) for r in rows] == list(range(96)), 'Missing/duplicate slots')
        require(all(r['time'].startswith('2025-05-01T') for r in rows), 'Wrong time-series date')
        for policy, result in zip(('B0','B1','B2','B3'), summary):
            require(math.isclose(max(float(r[policy+'_rho_max']) for r in rows), float(result[scope+'_rho_max']), abs_tol=1e-12), 'Time-series maximum mismatch')
    heat = tables['HEATMAP_B0_B3_SAME_TIME.csv']
    hm = tables['HEATMAP_SAME_TIME_SUMMARY.csv'][0]
    critical = max(tables['MAY01_MAX_LOADING_TIMESERIES.csv'], key=lambda r: float(r['B0_rho_max']))
    require(hm['critical_time_B0'] == critical['time'] == '2025-05-01T18:15:00', 'Wrong critical time')
    require({r['time'] for r in heat} == {critical['time']}, 'Mixed heatmap timestamps')
    require({r['validation_scope'] for r in heat} == {'REALIZED_OPERATION_AC'}, 'Mixed heatmap scope')
    require(len(heat) == 16094 and len({r['element_id'] for r in heat}) == 4929, 'Missing heatmap elements')
    require(len({(r['element_id'],r['terminal'],r['phase']) for r in heat}) == len(heat), 'Duplicate heatmap channels')
    disabled = [r for r in heat if r['data_status'] == 'DISABLED_ELEMENT_NO_RECORDED_CURRENT']
    require(len(disabled) == 5 and all(r['B0_loading'] == r['B3_loading'] == 'NA' for r in disabled), 'Disabled line data fabricated')
    require(all(r[k] != 'NA' for r in heat for k in ('x_from','y_from','x_to','y_to')), 'Missing coordinates')
    for policy, field in [('B0','B0_rho_max_at_time'), ('B3','B3_rho_max_at_same_time')]:
        peak = max(float(r[policy+'_loading']) for r in heat if r['element_type']=='LINE' and r['data_status']=='RECORDED')
        require(math.isclose(peak,float(hm[field]),abs_tol=1e-12), 'Heatmap summary mismatch')
        require(math.isclose(peak,float(critical[policy+'_rho_max']),abs_tol=1e-12), 'Heatmap/time-series mismatch')
    floor = tables['B3_OPERATING_ENERGY_EXCEPTION.csv']
    require(len(floor)==9 and [int(r['slot']) for r in floor]==list(range(32,41)), 'Energy exception coverage')
    require(all(r['mess_id']=='MESS06' and r['operating_floor_feasible']=='false' and r['ac_feasible']=='true' for r in floor), 'Energy exception hidden')
    for row in floor:
        require(math.isclose(440-float(row['energy_min_kWh']),float(row['shortfall_kWh']),abs_tol=1e-12), 'Energy shortfall arithmetic')
    runtime = {r['policy']:r for r in tables['RUNTIME_TERMINATION.csv']}
    require(all(runtime[p]['runtime_s']=='NA' for p in ('B0','B2','B3')), 'Invented end-to-end runtime')
    require(all(r['optimality_proven']=='false' and r['mip_gap']==r['best_bound']=='NA' for r in runtime.values()), 'Unsupported optimum/bound/gap')
    require(all(runtime[p]['time_limit_s']=='14400' for p in ('B1','B3')), 'Wrong component time limit')
    require(len(tables['AC_FEASIBILITY.csv'])==8 and all(r['overall_ac_feasible']=='true' for r in tables['AC_FEASIBILITY.csv']), 'AC result mismatch')
    require(len(tables['PAPER_KEY_RESULTS.csv'])<=30, 'Too many paper key rows')
    require(len(tables['B2_MESS_OPTIMIZATION_RUNTIME.csv'])==6, 'Wrong MESS fleet')
    return {'status':'PASS','csv_count':13,'date':manifest['date'],'mess_count':6,'scope_ordering':order,'scientific_execution_count':0}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    print(json.dumps(verify(parser.parse_args().folder)))
