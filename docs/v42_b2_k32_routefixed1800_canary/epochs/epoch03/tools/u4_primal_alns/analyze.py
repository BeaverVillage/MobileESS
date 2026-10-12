"""No-CSR, no-solver Source18r original-coordinate operating-plan readback."""
from __future__ import annotations

import argparse
import csv
from fractions import Fraction
import json
from pathlib import Path
from time import perf_counter
import sys

import numpy as np

from . import verify as v


def original_plan(case, path, replay):
    raw = v.load_point(path)
    v.require(replay.get('PASS') is True and replay.get('case_sha') == v.CASE_SHA
              and replay.get('source_sha') == v.SOURCE_SHA
              and replay.get('point_vector_sha256') == v.vector_sha(raw)
              and replay.get('point_file_sha256') == v.file_sha(path), 'BEST_FULL_REPLAY_POINT_BINDING')
    original = case.lift(raw)
    discrete = np.flatnonzero(case.original_d['types'] != 'C')
    v.require(np.array_equal(original[discrete], np.rint(original[discrete])), 'ANALYSIS_RAW_FULL_NOT_LITERAL_INTEGER')
    values = dict(zip(map(str, case.original_d['names']), map(float, original)))
    sites, initial, arcs, battery, _ = case.graph
    rows, plans = [], {}
    for unit, origin in sorted(initial.items()):
        selected = [k for k in range(len(arcs)) if values.get(f'arc[{unit},{k}]', 0.) == 1.]
        path_ordered, loc, t = [], origin, 0
        while t < 96:
            choices = [k for k in selected if arcs[k][:2] == (loc, t)]
            v.require(len(choices) == 1, 'ORIGINAL_FULL_96_ROUTE_CHAIN')
            k = choices[0]
            path_ordered.append(k)
            loc, t = arcs[k][2:4]
        v.require(t == 96 and len(path_ordered) == len(selected), 'ORIGINAL_FULL_TERMINAL_AND_NO_EXTRA_ARC')
        moves = [dict(original_arc_index=k, route_id=arcs[k][-1].route_id,
                      source=arcs[k][0], depart=arcs[k][1], destination=arcs[k][2],
                      arrive=arcs[k][-1].arrive, connect=arcs[k][3], energy_kWh=arcs[k][-1].energy_kwh)
                 for k in path_ordered if arcs[k][-1] is not None]
        unit_rows = []
        for t in range(96):
            active = [k for k in path_ordered if arcs[k][1] <= t < arcs[k][3]]
            v.require(len(active) == 1, 'ORIGINAL_FULL_SLOT_ROUTE_UNIQUENESS')
            arc = arcs[active[0]]
            connected = arc[-1] is None
            ch = sum(values.get(f'Pch[{unit},{s},{t}]', 0.) for s in sites)
            dis = sum(values.get(f'Pdis[{unit},{s},{t}]', 0.) for s in sites)
            q = sum(values.get(f'Q[{unit},{s},{t}]', 0.) for s in sites)
            travel = sum(a['energy_kWh'] for a in moves if a['depart'] == t)
            before = values[f'SOC[{unit},{t}]']
            after = values[f'SOC[{unit},{t+1}]']
            residual = after-before-battery.dt_hours*(battery.eta_charge*ch-dis/battery.eta_discharge)+travel
            record = dict(unit=unit, slot=t, connected=connected, site=arc[0] if connected else None,
                original_arc_index=active[0], route_id=None if connected else arc[-1].route_id,
                route_depart=arc[1], route_arrive=None if connected else arc[-1].arrive, route_connect=arc[3],
                charge_mode=values[f'charge_mode[{unit},{t}]'], Pch_kW=ch, Pdis_kW=dis,
                net_P_injection_kW=dis-ch, Q_kvar=q, SOC_before_kWh=before, SOC_after_kWh=after,
                travel_debit_kWh=travel, original_energy_balance_residual_kWh=residual)
            rows.append(record)
            unit_rows.append(record)
        soc = [values[f'SOC[{unit},{t}]'] for t in range(97)]
        plans[unit] = dict(initial_location=origin, original_terminal_location=loc,
            terminal_location_semantics='Original source terminal flow; no new return-to-origin condition.',
            ordered_original_arc_indices=path_ordered, move_routes=moves, move_count=len(moves),
            travel_energy_kWh=sum(a['energy_kWh'] for a in moves), SOC97_kWh=soc,
            SOC_min_kWh=min(soc), SOC_max_kWh=max(soc), SOC_initial_kWh=soc[0], SOC_terminal_kWh=soc[-1],
            charge_mode_1_count=sum(r['charge_mode'] == 1. for r in unit_rows),
            charging_kWh=battery.dt_hours*sum(r['Pch_kW'] for r in unit_rows),
            discharging_kWh=battery.dt_hours*sum(r['Pdis_kW'] for r in unit_rows),
            Q_absolute_kvar_slot_sum=sum(abs(r['Q_kvar']) for r in unit_rows),
            Q_max_absolute_kvar=max(abs(r['Q_kvar']) for r in unit_rows),
            maximum_energy_balance_residual_kWh=max(abs(r['original_energy_balance_residual_kWh']) for r in unit_rows),
            max_raw_transit_Pch_Pdis_Q=max([0.]+[max(abs(r['Pch_kW']),abs(r['Pdis_kW']),abs(r['Q_kvar']))
                                                for r in unit_rows if not r['connected']]),
            physical_replay_PASS=replay['original_matrix_and_96_slot_physical_replay']['physical']['PASS'])
    return dict(PASS=True, point_path=str(Path(path).resolve()), point_file_sha256=v.file_sha(path),
        point_vector_sha256=v.vector_sha(raw), exact_verified_UB=replay['exact_Global_UB'],
        verified_UB=replay['Global_UB'], units=plans, move_count=sum(p['move_count'] for p in plans.values()),
        travel_energy_kWh=sum(p['travel_energy_kWh'] for p in plans.values()),
        charging_kWh=sum(p['charging_kWh'] for p in plans.values()),
        discharging_kWh=sum(p['discharging_kWh'] for p in plans.values()),
        SOC_min_kWh=min(p['SOC_min_kWh'] for p in plans.values()),
        SOC_max_kWh=max(p['SOC_max_kWh'] for p in plans.values()), Actual='ACTUAL_NOT_RUN'), rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--comparison', type=Path, default=v.DOCS/'COMPARISON.json')
    args = parser.parse_args()
    began = perf_counter()
    comparison = v.read(args.comparison)
    case = v.load_case(native=False)
    initial_path = v.DOCS/'INITIAL_U4_POINT.npz'
    initial_replay = v.read(v.DOCS/'INITIAL_U4_FULL_REPLAY.json')
    candidates = [('Original U4', initial_path, initial_replay)]
    for method in ('N1', 'N2', 'N3'):
        algo = comparison['methods'][method]
        best = Path(algo['best_point']['path'])
        replay = initial_replay
        for iteration in algo.get('iterations', []):
            for item in iteration.get('validated_candidates', []):
                if item.get('PASS') and Path(item['raw']['path']).resolve() == best.resolve():
                    replay = v.read(item['replay']['path'])
        candidates.append((method, best, replay))
    result = dict(PASS=True, source_sha=v.SOURCE_SHA, case_sha=v.CASE_SHA, candidates={},
                  Native_optimize_calls=0, CSR_matrices_loaded=0, Actual='ACTUAL_NOT_RUN')
    for label, path, replay in candidates:
        plan, rows = original_plan(case, path, replay)
        result['candidates'][label] = plan
        tag = label.replace(' ', '_')
        v.write(v.DOCS/'operating_plans'/f'{tag}_ORIGINAL_PLAN.json', plan)
        csv_path = v.DOCS/'operating_plans'/f'{tag}_SOURCE96_PLAN.csv'
        with csv_path.open('w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    v.require('gurobipy' not in sys.modules, 'NO_GUROBI_ANALYSIS_CONTRACT')
    result['analysis_wall_seconds'] = perf_counter()-began
    v.write(v.DOCS/'ORIGINAL_SOURCE_OPERATING_PLAN_COMPARISON.json', result)
    print(json.dumps(dict(PASS=True, candidates=4, Native_optimize_calls=0, CSR_matrices_loaded=0)))


if __name__ == '__main__':
    main()
