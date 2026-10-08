"""UB-only candidate selection from exact original signed grid coefficients.

Projection packets only rank choices. They never modify scientific grid rows,
certify an attainable dispatch, or supply a global lower bound.
"""
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import numpy as np
from v42_m1_research.ub import binary_inventory, select_neighborhood
from v42_m1_research.projection_rows import verify_projection_packet


def _family(name):
    return str(name).split('[', 1)[0]


def _pcs_vertices(case):
    """Instantaneous candidate score corners from the original 16 source rows."""
    ids = [i for i, n in enumerate(case.original_d['row_names']) if _family(n) == 'PCS16'][:16]
    if len(ids) != 16:
        raise ValueError('ORIGINAL_PCS16_SCORE_AUTHORITY_MISSING')
    planes = []
    for i in ids:
        a, b = case.original_A.indptr[i:i+2]
        terms = [(str(case.original_d['names'][j]), F(float(w))) for j, w in
                 zip(case.original_A.indices[a:b], case.original_A.data[a:b])]
        p = sum((w for n, w in terms if n.startswith('Pdis[')), F(0))
        q = sum((w for n, w in terms if n.startswith('Q[')), F(0))
        constant = F(float(case.original_d['rhs'][i]))-sum((w for n, w in terms if n.startswith('arc[')), F(0))
        planes.append((p, q, constant))
    limit = F(float(case.graph[3].p_limit))
    planes += [(F(1), F(0), limit), (F(-1), F(0), limit)]
    vertices = set()
    for i, (a, b, c) in enumerate(planes):
        for p, q, r in planes[:i]:
            determinant = a*q-b*p
            if not determinant:
                continue
            x, y = (c*q-b*r)/determinant, (a*r-c*p)/determinant
            if all(s*x+t*y <= u for s, t, u in planes):
                vertices.add((x, y))
    if not vertices:
        raise ValueError('ORIGINAL_PCS16_SCORE_CORNERS_EMPTY')
    return sorted(vertices), ids


def signed_support_score(coefficients, current_unit_contribution, vertices):
    """Signed instantaneous proxy, with exclusive modes and both Q directions."""
    ch, dis, q = map(F, coefficients)
    lower = min((dis*p+q*v if p >= 0 else ch*(-p)+q*v for p, v in vertices), default=F(0))
    lower = min(F(0), lower)
    potential = max(F(0), F(current_unit_contribution)-lower)
    return potential, lower


def grid_candidates(case, point, projection_path):
    raw = Path(projection_path).read_bytes()
    document = json.loads(raw)
    packets = document['exact_rows']
    checked = verify_projection_packet(case, packets)
    if not checked['PASS']:
        raise ValueError('EXACT_SOURCE_GRID_PROJECTION_NOT_VERIFIED')
    vertices, pcs_rows = _pcs_vertices(case)
    rho = int(np.flatnonzero(case.d['names'] == 'rho_max')[0])
    candidates, row_diagnostics = [], []
    for packet in packets:
        expression = packet['direct_rho_lower_requirement']
        if expression is None:
            continue
        weights = {int(j): F(w) for j, w in expression['exact_physical_coefficients'].items()}
        constant = F(expression['exact_constant'])
        required = constant+sum((w*F(float(point[j])) for j, w in weights.items()), F(0))
        slack = max(0., float(point[rho])-float(required))
        priority = 1./(1.+slack/.01)
        cells, current = {}, {}
        for j, w in weights.items():
            name = str(case.d['names'][j]); family, fields = name.split('[', 1)
            u, s, t = fields[:-1].split(','); key = (u, s, int(t))
            cell = cells.setdefault(key, [F(0), F(0), F(0)])
            cell[('Pch', 'Pdis', 'Q').index(family)] = w
            current[u] = current.get(u, F(0))+w*F(float(point[j]))
        row_diagnostics.append(dict(source_row=packet['source_row'],
            same_dispatch_rho_requirement=float(required), same_dispatch_requirement_exact=str(required),
            incumbent_rho=float(point[rho]), rho_slack=slack, active_priority=priority,
            exact_native_binding_rows=len(packet['exact_native_equality_multipliers']),
            is_global_LB=False))
        for (u, s, t), coefficients in cells.items():
            potential, minimum = signed_support_score(coefficients, current[u], vertices)
            candidates.append(dict(row=int(packet['source_row']), unit=u, site=s, slot=t,
                signed_Pch_coefficient=str(coefficients[0]), signed_Pdis_coefficient=str(coefficients[1]),
                signed_Q_coefficient=str(coefficients[2]), current_unit_contribution_exact=str(current[u]),
                instantaneous_candidate_minimum_exact=str(minimum), potential_exact=str(potential),
                active_priority=priority, numeric_score=float(potential)*priority,
                signed_direction={'direct_charge_coefficient_favors_charge': coefficients[0] < 0,
                                  'direct_discharge_coefficient_favors_discharge': coefficients[1] < 0,
                                  'preferred_Q_sign': -1 if coefficients[2] > 0 else 1 if coefficients[2] < 0 else 0},
                attainable_96_slot_dispatch_claimed=False))
    candidates.sort(key=lambda r: (-r['numeric_score'], r['row'], r['unit'], r['site'], r['slot']))
    selected, seen = [], set()
    # Keep the best actual signed site for each row/unit, rather than many
    # repeated site alternatives at one high-score time.
    active_rows = {r['source_row'] for r in row_diagnostics if r['rho_slack'] <= .01}
    for candidate in candidates:
        key = (candidate['row'], candidate['unit'])
        if candidate['row'] in active_rows and key not in seen:
            selected.append(candidate); seen.add(key)
    if not selected:
        raise ValueError('NO_ACTUAL_GRID_SIGNED_CANDIDATE')
    provenance = dict(projection_packet_path=str(projection_path),
        projection_packet_SHA256=hashlib.sha256(raw).hexdigest(),
        exact_source_recombination_checker=checked, original_PCS16_score_rows=pcs_rows,
        instantaneous_PCS_vertices_exact=[[str(a), str(b)] for a, b in vertices],
        source_rows=row_diagnostics, selected_grid_targets=selected,
        score_formula='max(0,current unit signed grid contribution - minimum signed original PCS16 support)/(1+rho_slack/0.01)',
        physical_or_objective_coefficients_changed=False,
        score_is_candidate_priority_only_not_cut_or_LB=True,
        whole_96_slot_route_SOC_feasibility_verified_only_after_solver=True)
    return selected, provenance


def _moves(case, point):
    original = case.lift(point)
    values = dict(zip(map(str, case.original_d['names']), map(float, original)))
    result = []
    for u in sorted(case.graph[1]):
        for k, arc in enumerate(case.graph[2]):
            if arc[-1] is not None and values.get(f'arc[{u},{k}]', 0.) == 1.:
                r = arc[-1]
                result.append(dict(unit=u, arc=int(k), route_id=r.route_id, source=arc[0],
                    destination=arc[2], depart=arc[1], arrive=r.arrive, connect=arc[3],
                    energy_kwh=r.energy_kwh, unavailable_slots=arc[3]-arc[1]))
    return result


def select(case, point, method, projection_path):
    inventory = binary_inventory(case.d)
    baseline = select_neighborhood(case, point, 'U2')
    seed_free = set(map(int, baseline['free_binary_columns']))
    selected, provenance = grid_candidates(case, point, projection_path)
    if method == 'A':
        free = seed_free
        route_targets = []
        name = 'unchanged previous U2 fleet-role site union selection'
    elif method == 'B':
        free = set()
        target_windows = {}
        for r in selected:
            start, stop = max(0, r['slot']-6), min(96, r['slot']+7)
            for t in range(start, stop):
                target_windows.setdefault((r['unit'], t), set()).add(r['site'])
        # Release the current connected state as well as the proposed state;
        # otherwise a fixed old location would block the new route.
        for r in inventory:
            key = (r['unit'], r['slot'])
            if key in target_windows and (r['family'] == 'charge_mode' or
                    r['site'] in target_windows[key] or point[r['column']] == 1.):
                free.add(r['column'])
        route_targets = []
        name = 'signed source-grid row/site/time support neighborhood'
    elif method == 'C':
        scored = []
        for route in _moves(case, point):
            related = [r for r in selected if r['site'] in (route['source'], route['destination'])
                       and route['depart']-6 <= r['slot'] <= 95]
            signed_score = max((r['numeric_score'] for r in related), default=0.)
            energy = route['energy_kwh']/case.graph[3].maximum
            connection = route['unavailable_slots']/96.
            scored.append(dict(**route, signed_grid_opportunity=signed_score,
                normalized_travel_energy=energy, normalized_connection_loss=connection,
                numeric_score=signed_score+energy+connection,
                score_formula='signed grid opportunity + travel_kWh/battery.maximum + unavailable_slots/96',
                role_substitution_units=sorted(case.graph[1]),
                route_removal_is_optional_not_forced=True))
        scored.sort(key=lambda r: (-r['numeric_score'], r['route_id'], r['unit']))
        route_targets = scored[:3]
        windows = {}
        for route in route_targets:
            for t in range(max(0, route['depart']-6), 96):
                windows.setdefault(t, set()).update((route['source'], route['destination']))
        # Four units jointly substitute for those roles; all actual native arcs
        # remain present and original flow equations choose legal travel.
        free = set()
        for r in inventory:
            t = r['slot']
            if t in windows and (r['family'] == 'charge_mode' or r['site'] in windows[t]
                                  or point[r['column']] == 1.):
                free.add(r['column'])
        name = 'four-fleet selective route removal and role redeployment corridors'
    else:
        raise ValueError('ONLY_REGISTERED_HYBRID_METHODS_A_B_C')
    all_binary = set(r['column'] for r in inventory)
    if not free:
        raise ValueError('EMPTY_HYBRID_NEIGHBORHOOD')
    return dict(method=method, description=name, case_sha=case.case_sha,
        free_binary_columns=np.asarray(sorted(free), dtype=np.int64),
        fixed_binary_columns=np.asarray(sorted(all_binary-free), dtype=np.int64),
        original_binary_columns=9322, hamming_radius=96,
        selected_grid_provenance=provenance, selected_route_targets=route_targets,
        source_seed_restricted_feasible=True, forced_route_removal=False,
        full_original_flow_route_SOC_rows_and_arcs_preserved=True,
        original_all_96_slot_continuous_bounds_preserved=True,
        bound_scope='RESTRICTED_UB_NEIGHBORHOOD_NEVER_GLOBAL_LB')
