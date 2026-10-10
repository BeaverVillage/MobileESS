"""Original U4 windows with current-case grid ranking and a route witness."""
from collections import defaultdict
from pathlib import Path
from unittest.mock import patch
import hashlib
import json
import numpy as np

RADII = (48, 96, 144, 192, 288)
LOOKBACK = (4, 8, 16, 24)
TOP_ROUTES = (2, 3, 4, 6)


def inventory(case):
    result = []
    for j in np.flatnonzero(case.d['types'] != 'C'):
        name = str(case.d['names'][j])
        family, fields = name.split('[', 1)
        fields = fields[:-1].split(',')
        if family not in ('node_activity', 'charge_mode', 'arc', 'route_flow'):
            raise ValueError('COMMON_M_UNKNOWN_INTEGER_FAMILY:' + name)
        result.append(dict(column=int(j), family=family, unit=fields[0],
            site=fields[1] if family == 'node_activity' else None,
            slot=int(fields[-1]) if family in ('node_activity', 'charge_mode') else None))
    return result


def current_grid(case, point, path):
    """Keep PR189 exact thermal projections; voltage fallback never adds rows."""
    names = np.asarray(case.d['row_names'], dtype=str)
    rho = int(np.flatnonzero(case.d['names'] == 'rho_max')[0])
    activity = case.A @ point
    slack = np.where(case.d['sense'] == '<', case.d['rhs'] - activity,
        np.where(case.d['sense'] == '>', activity - case.d['rhs'], abs(activity - case.d['rhs'])))
    thermal = np.flatnonzero(np.char.startswith(names, 'line_thermal_face[')
        | np.char.startswith(names, 'transformer_kVA['))
    targets, provenance = [], {}
    if len(thermal):
        coefficient = np.asarray(case.A[thermal, rho].toarray()).ravel()
        ranked = thermal[np.argsort(np.maximum(slack[thermal], 0) / np.maximum(abs(coefficient), 1e-12))]
        chosen, seen = [], set()
        for i in ranked:
            key = tuple(names[i].split('[', 1)[1][:-1].split(',')[:2])
            if key not in seen:
                chosen.append(int(i)); seen.add(key)
            if len(chosen) == 12:
                break
        from v42_m1_research import projection_rows
        from v42_m1_hybrid.neighborhood import grid_candidates
        from .storage import write
        with patch.object(projection_rows, 'FIXED_ROWS', tuple(chosen)):
            packets = projection_rows.project_rows(case)
            checked = projection_rows.verify_projection_packet(case, packets)
            if checked.get('PASS') is not True:
                raise ValueError('COMMON_M_GRID_PROJECTION_NOT_VERIFIED')
            write(path, dict(case_sha=case.case_sha, exact_rows=packets,
                independent_checker=checked, original_rows=chosen,
                adaptive_row_ranking_is_UB_heuristic_not_Global_LB=True))
            # No candidate is a legitimate empty-current-thermal case. Exact
            # coefficient/recombination failures must still fail the stage.
            try:
                targets, provenance = grid_candidates(case, point, path)
            except ValueError as error:
                if str(error) != 'NO_ACTUAL_GRID_SIGNED_CANDIDATE':
                    raise
    voltage = np.flatnonzero(np.char.startswith(names, 'voltage_lower[')
        | np.char.startswith(names, 'voltage_upper['))
    vtop = voltage[np.argsort(slack[voltage])[:8]]
    observations = [dict(row=int(i), name=str(names[i]), observed_slack=float(slack[i])) for i in vtop]
    provenance['active_voltage_observations'] = observations
    provenance['all_original_grid_rows_preserved_in_native_model'] = True
    if not targets:
        # Same-day original voltage sensitivity ranks locations. This is a
        # heuristic only; FULL replay gates every resulting physical point.
        for observation in observations:
            fields = observation['name'].split('[', 1)[1][:-1].split(',')
            t, node = int(fields[0]), int(fields[1])
            coefficients = case.coefficients[t]
            controls = list(coefficients.control_names)
            for site in case.graph[0]:
                p = controls.index('mess_p_kw[' + site + ']')
                q = controls.index('mess_q_kvar[' + site + ']')
                score = (abs(float(coefficients.voltage_matrix[p, node])) * case.graph[3].p_limit
                    + abs(float(coefficients.voltage_matrix[q, node])) * case.graph[3].pcs_kva)
                for unit in sorted(case.graph[1]):
                    targets.append(dict(row=observation['row'], unit=unit, site=site, slot=t,
                        numeric_score=score, source='CURRENT_VOLTAGE_BOTTLENECK',
                        attainable_96_slot_dispatch_claimed=False))
        targets.sort(key=lambda r: (-r['numeric_score'], r['row'], r['unit'], r['site']))
        provenance['fallback_reason'] = 'NO_CURRENT_THERMAL_TARGET_USE_CURRENT_VOLTAGE'
    if not targets:
        raise ValueError('COMMON_M_NO_CURRENT_GRID_BOTTLENECK_AUTHORITY')
    return targets, provenance


def _chosen(case, point):
    original = case.lift(point)
    selected = defaultdict(set)
    for j, name in enumerate(map(str, case.original_d['names'])):
        if name.startswith('arc[') and original[j] == 1.:
            unit, k = name[4:-1].split(',')
            selected[unit].add(int(k))
    return selected


def route_witness(case, point, free, radius):
    """DAG witness of a different route admitted by this binary Hamming box.

    This proves route openness, never SOC/grid feasibility of the alternate
    route. The original coupled MILP and independent FULL replay provide that.
    """
    records = inventory(case)
    free = set(map(int, free))
    names = {str(n): j for j, n in enumerate(case.d['names'])}
    selected = _chosen(case, point)
    outgoing = defaultdict(list)
    for k, arc in enumerate(case.graph[2]):
        outgoing[arc[0], arc[1]].append(k)
    H = 96
    for unit, origin in sorted(case.graph[1].items()):
        nodes = { (r['site'], r['slot']): r for r in records
            if r['unit'] == unit and r['family'] == 'node_activity' }
        required = {r['slot']: r['site'] for r in nodes.values()
            if r['column'] not in free and point[r['column']] == 1.}
        required_times = sorted(required)
        constant = sum(point[r['column']] == 1. for r in nodes.values() if r['column'] in free)
        def node_cost(site, t):
            record = nodes.get((site, t))
            if t in required and required[t] != site:
                return None
            if record is None:
                return 0 # C2 eliminated a proved fixed source node.
            j = record['column']
            if j not in free:
                return 0 if point[j] == 1. else None
            return -1 if point[j] == 1. else 1
        states = {(origin, 0, False): (0, ())}
        for t in range(H):
            frontier = [(s, different, value) for (s, time, different), value in states.items() if time == t]
            for site, different, (cost, path) in frontier:
                node_delta = node_cost(site, t)
                if node_delta is None:
                    continue
                for k in outgoing.get((site, t), ()):
                    arc = case.graph[2][k]
                    if any(t < time < arc[3] for time in required_times):
                        continue
                    j = names.get(f'route_flow[{unit},{k}]', names.get(f'arc[{unit},{k}]'))
                    if j is not None and case.d['upper'][j] == 0:
                        continue
                    if j is not None and case.d['types'][j] != 'C' and j not in free and point[j] != 1.:
                        continue
                    key = (arc[2], arc[3], different or k not in selected[unit])
                    value = (cost + node_delta, path + (k,))
                    if key not in states or value[0] < states[key][0]:
                        states[key] = value
        terminals = sorted((cost + (node_cost(site, H) or 0), site, path)
            for (site, time, different), (cost, path) in states.items()
            if time == H and different and node_cost(site, H) is not None)
        for _, terminal, path in terminals:
            trial = point.copy()
            visited = {(case.graph[2][k][0], case.graph[2][k][1]) for k in path} | {(terminal, H)}
            chosen = set(path)
            for r in records:
                if r['unit'] != unit:
                    continue
                if r['family'] == 'node_activity':
                    trial[r['column']] = float((r['site'], r['slot']) in visited)
            for name, j in names.items():
                if name.startswith((f'route_flow[{unit},', f'arc[{unit},')):
                    trial[j] = float(int(name.split(',')[-1][:-1]) in chosen)
            allbinary = np.asarray([r['column'] for r in records], dtype=int)
            fixed = np.asarray(sorted(set(allbinary) - free), dtype=int)
            distance = int(np.count_nonzero(trial[allbinary] != point[allbinary]))
            if (distance <= radius and np.array_equal(trial[fixed], point[fixed])
                    and np.all(trial >= case.d['lower']) and np.all(trial <= case.d['upper'])):
                return dict(PASS=True, unit=unit, arc_indices=list(path), hamming_distance=distance,
                    original_DAG_flow_and_terminal_slot=96, route_changed=True,
                    SOC_PQ_grid_feasibility_claimed=False)
    return dict(PASS=False, reason='NO_DIFFERENT_ORIGINAL_ROUTE_IN_CURRENT_BINARY_BOX')


def select(case, point, method, ordinal, grid):
    records = inventory(case)
    targets, provenance = grid
    radius = RADII[min(ordinal, 2)]
    look = LOOKBACK[min(ordinal, 2)]
    top = TOP_ROUTES[min(ordinal, 2)]
    windows = defaultdict(set)
    if method == 'U4':
        charges = []
        for j, name in enumerate(map(str, case.d['names'])):
            if name.startswith('Pch[') and point[j] > 1e-6:
                _, site, t = name[4:-1].split(',')
                charges.append((float(point[j]), site, int(t)))
        charges.sort(reverse=True)
        for _, site, t0 in charges[:max(8, top * 4)]:
            for t in range(max(0, t0 - look), min(96, t0 + look + 1)):
                windows[t].add(site)
        for target in targets[:top * 4]:
            for t in range(max(0, target['slot'] - look), 96):
                windows[t].add(target['site'])
    elif method in ('U1', 'U2', 'U3'):
        from v42_m1_hybrid.neighborhood import _moves
        moves = _moves(case, point)
        moves.sort(key=lambda r: (-max((x['numeric_score'] for x in targets
            if x['site'] in (r['source'], r['destination'])), default=0.)
            - r['energy_kwh'] / case.graph[3].maximum - r['unavailable_slots'] / 96., r['route_id'], r['unit']))
        for move in moves[:top]:
            for t in range(max(0, move['depart'] - look), 96):
                windows[t].update((move['source'], move['destination']))
        for target in targets[:top * 4]:
            for t in range(max(0, target['slot'] - look), min(96, target['slot'] + look + 1)):
                windows[t].add(target['site'])
    else:
        raise ValueError('COMMON_M_REGISTERED_PRIMAL_NEIGHBORHOOD_REQUIRED')
    def columns():
        return {r['column'] for r in records if r['slot'] in windows and
            (r['family'] == 'charge_mode' or r['site'] in windows[r['slot']] or point[r['column']] == 1.)}
    free = columns()
    witness = route_witness(case, point, free, radius)
    fallback = False
    if not witness['PASS']:
        # Open the full current-day bottleneck corridor, including terminal
        # occupancy. Hamming radius stays unchanged, so this is not a sweep.
        fallback = True
        start = max(0, min(int(r['slot']) for r in targets[:top * 4]) - look)
        for t in range(start, 97):
            windows[t].update(case.graph[0])
        free = columns()
        witness = route_witness(case, point, free, radius)
        if not witness['PASS']:
            # A late bottleneck can require travel beginning before the short
            # PR189 lookback. Extend only to a same-day incoming target route,
            # using that arc's original ETA instead of a fixed calendar slot.
            target_sites = {r['site'] for r in targets[:top * 4]}
            target_slots = {r['site']: max(int(x['slot']) for x in targets[:top * 4]
                if x['site'] == r['site']) for r in targets[:top * 4]}
            departures = [arc[1] for arc in case.graph[2] if arc[-1] is not None
                and arc[2] in target_sites and arc[3] <= target_slots[arc[2]]
                and arc[3] >= max(0, target_slots[arc[2]] - LOOKBACK[-1])]
            if departures:
                start = min(start, min(departures))
                for t in range(start, 97):
                    windows[t].update(case.graph[0])
                free = columns()
                witness = route_witness(case, point, free, radius)
    allbinary = {r['column'] for r in records}
    fixed = allbinary - free
    signature = hashlib.sha256(json.dumps([method, radius, sorted(free)], separators=(',', ':')).encode()).hexdigest()
    return dict(method=method, case_sha=case.case_sha,
        description='PR189 current charge and actual grid U4 windows',
        free_binary_columns=np.asarray(sorted(free), dtype=np.int64),
        fixed_binary_columns=np.asarray(sorted(fixed), dtype=np.int64),
        original_binary_columns=len(allbinary), hamming_radius=radius,
        lookback_slots=look, route_top=top, selected_grid_provenance=provenance,
        route_openness=witness, current_bottleneck_corridor_fallback=fallback,
        no_charging_slots_fallback=method == 'U4' and not bool(locals().get('charges')),
        neighborhood_signature=signature,
        full_original_flow_route_SOC_rows_and_arcs_preserved=True,
        original_all_96_slot_continuous_bounds_preserved=True,
        bound_scope='RESTRICTED_UB_NEIGHBORHOOD_NEVER_GLOBAL_LB')
