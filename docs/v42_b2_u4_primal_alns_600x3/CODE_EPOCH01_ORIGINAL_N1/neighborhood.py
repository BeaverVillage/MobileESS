"""Finite signed-grid Primal neighborhoods; never constructs a solver model.

The original FULL domain is preserved by the runner, while this adapter only
declares Binary/continuous-route fixings and a center-containing Hamming ball.
Candidate scores are instantaneous heuristics, never feasibility or LB claims.
"""
from __future__ import annotations
from collections import defaultdict
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import re
import numpy as np
from v42_common_mess.neighborhood import inventory, route_witness

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT/'docs/v42_b2_u4_primal_alns_600x3'
CONTEXT = DOCS/'SIGNED_SELECTION_CONTEXT.json'
QUEUE = DOCS/'CANDIDATE_PREREGISTRATION.json'
PHYSICAL = re.compile(r'(Pch|Pdis|Q)\[(MESS\d\d),([^,]+),(\d+)\]')


def _require(ok, reason):
    if not ok:
        raise ValueError(reason)


def _read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def _sha(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(',', ':'),
        ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def _vector_sha(point):
    return hashlib.sha256(np.ascontiguousarray(point, dtype='<f8').tobytes()).hexdigest()


def candidate_queue(method):
    """Finite pre-registered candidates; cumulative caps belong to the runner."""
    _require(method in ('N1', 'N2', 'N3'), 'UNKNOWN_PRIMAL_METHOD')
    if method == 'N1':
        return [dict(candidate_id='N1_ALL96_MODES', selected_units=[], variant='all96',
            requested_cap_seconds=600, hamming_radius=384,
            policy='One complete 384-Mode problem with every original route fixed.')]
    p = _read(QUEUE)
    _require(p['Native_optimize_calls'] == 0 and p['initial_point_sha256'] ==
        'c9d63854a3ec0747a65d2c6724a5d413585f9a4f6754107fc593ba69ea4eda0d',
        'PREREGISTRATION_NOT_FROZEN_U4')
    return p[method]


def _signed_ranking(case, point, context):
    """Refresh stored exact original projections at this algorithm's own center."""
    original = case.lift(point)
    _require(len(original) == len(case.original_d['names']), 'ORIGINAL_LIFT_AXIS')
    vertices = [(F(p), F(q)) for p, q in context['PCS16_vertices_exact']]
    rho = float(point[int(np.flatnonzero(case.d['names'] == 'rho_max')[0])])
    cells = []
    moves_by_pair = defaultdict(list)
    route_choice = {}
    for arc in case.graph[2]:
        if arc[-1] is not None:
            moves_by_pair[arc[0], arc[2]].append(arc)
    for packet in context['critical_exact_rows']:
        # normalized lhs <= rhs, all helper coefficients eliminated exactly.
        coeff = {int(k): F(v) for k, v in packet['coeff'].items()}
        rhs = F(packet['rhs'])
        a_rho = coeff.get(context['original_rho_column'], F(0))
        activity = sum((v*F(float(original[j])) for j, v in coeff.items()), F(0))
        # Every projection was selected from a FULL-active row; own-center
        # refresh changes its priority and avoids borrowing another method's UB.
        unit_scale = -a_rho if a_rho < 0 else F(packet['priority_scale'])
        _require(unit_scale > 0, 'SIGNED_PRIORITY_SCALE')
        slack = max(0., float((rhs-activity)/unit_scale))
        priority = 1./(1.+slack/.01)
        grouped, current = defaultdict(lambda: [F(0), F(0), F(0)]), defaultdict(F)
        for j, weight in coeff.items():
            m = PHYSICAL.fullmatch(str(case.original_d['names'][j]))
            if m:
                family, unit, site, t = m.groups()
                grouped[(unit, site, int(t))][('Pch','Pdis','Q').index(family)] += weight/unit_scale
                current[unit] += weight/unit_scale*F(float(original[j]))
        for (unit, site, t), (ch, dis, q) in grouped.items():
            support = min([F(0)] + [dis*p+q*v if p >= 0 else ch*(-p)+q*v for p,v in vertices])
            potential = max(F(0), current[unit]-support)
            origin = case.graph[1][unit]
            # A direct actual RouteArc witness ending before the critical slot.
            # It does not certify SOC or Grid feasibility. All96 modes remain
            # free, so charging can occur before this route window at origin.
            if site == origin:
                eta, energy, route = 0, 0., None
            else:
                key = (origin, site, t)
                if key not in route_choice:
                    moves = [a for a in moves_by_pair[origin, site] if a[3] <= t]
                    route_choice[key] = min(moves, key=lambda a: (a[3]-a[1], float(a[-1].energy_kwh),
                        -a[1], a[-1].route_id)) if moves else None
                route = route_choice[key]
                if route is None:
                    continue
                eta, energy = route[3]-route[1], float(route[-1].energy_kwh)
            score = float(potential)*priority/(1.+eta/16.+energy/1080.)
            cells.append(dict(unit=unit, site=site, slot=t, source_row=packet['original_row'],
                source_name=packet['name'], family=packet['family'], rho_normalized_slack=slack,
                signed_Pch_coefficient=str(ch), signed_Pdis_coefficient=str(dis), signed_Q_coefficient=str(q),
                direct_charge_relief=ch < 0, direct_discharge_relief=dis < 0,
                preferred_Q_sign=-1 if q > 0 else 1 if q < 0 else 0,
                exact_instantaneous_PCS16_relief=str(potential), score=score,
                origin=origin, actual_route_eta_slots=eta, actual_route_energy_kwh=energy,
                actual_route_id=None if route is None else str(route[-1].route_id),
                actual_route_depart=None if route is None else int(route[1]),
                actual_route_connect=None if route is None else int(route[3]),
                full96_feasibility_claim=False))
    cells.sort(key=lambda c: (-c['score'], c['source_row'], c['unit'], c['site']))
    return cells


def make_spec(case, point, method, candidate):
    """Return JSON-only restrictions from original named Dense coordinates."""
    x = np.asarray(point)
    _require(x.shape == (354277,) and np.isfinite(x).all(), 'SOURCE_CENTER_AXIS')
    inv = inventory(case)
    binary = sorted(c['column'] for c in inv)
    _require(np.isin(x[binary], (0.,1.)).all(), 'LITERAL_INTEGER_CENTER_REQUIRED')
    selected = list(candidate.get('selected_units', []))
    _require(method == 'N1' and not selected or method in ('N2','N3') and len(set(selected)) ==
        (1 if method == 'N2' else 2) and set(selected) <= set(case.graph[1]), 'VEHICLE_SELECTION')
    rankings, windows = [], {}
    if method == 'N1':
        free = [c['column'] for c in inv if c['family'] == 'charge_mode']
        _require(len(free) == 384, 'ALL_96_MODE_COLUMNS')
        radius = 384
    else:
        context = _read(CONTEXT)
        rankings = _signed_ranking(case, x, context)
        for unit in selected:
            rows = [c for c in rankings if c['unit'] == unit]
            _require(rows, 'NO_ORIGINAL_SIGNED_ROUTE_CANDIDATE:'+unit)
            # Opening all24 sites in one finite corridor permits actual path
            # selection; it does not force a destination, dispatch or return.
            top = rows[:4]
            start = max(0, min(c['slot']-c['actual_route_eta_slots']-8 for c in top))
            stop = min(96, max(c['slot']+9 for c in top))
            if candidate.get('variant') == 'expanded':
                start = max(0, start-16)
                stop = min(96, stop+16)
            windows[unit] = [int(start), int(stop)]
        free = [c['column'] for c in inv if c['unit'] in selected and
            (c['family'] == 'charge_mode' or c['family'] == 'node_activity' and
             windows[c['unit']][0] <= c['slot'] <= windows[c['unit']][1] or
             c['family'] in ('arc','route_flow'))]
        radius = 48*len(selected)
    free = sorted(set(free))
    fixed = sorted(set(binary)-set(free))
    unselected = set(case.graph[1])-set(selected)
    route = [int(j) for j,n in enumerate(case.d['names']) if str(n).startswith('route_flow[')
        and str(n).split('[',1)[1].split(',',1)[0] in unselected]
    _require(all(case.d['types'][j] == 'C' for j in route), 'SOURCE_ROUTE_CONTINUOUS_TYPE')
    spec = dict(method=method, candidate_id=candidate['candidate_id'], selected_units=selected,
        free_binary_columns=free, fixed_binary_columns=fixed, fixed_route_columns=route,
        hamming_radius=radius, node_windows=windows,
        requested_cap_seconds=int(candidate['requested_cap_seconds']),
        center_point_vector_sha256=_vector_sha(x), case_sha=case.case_sha,
        center_always_included=True, all96_selected_vehicle_modes_free=True,
        nonroute_continuous_bounds_unchanged=True, signed_candidates=rankings[:32],
        algorithm_center_source='Own algorithm independently FULL-validated center only',
        Hamming_policy='Fixed 48 per selected vehicle; N1 releases all384Modes. No radius sweep.',
        source_route_alias_fixing_requires_independent_audit=True,
        restricted_ObjBound_is_Global_LB=False, Actual='ACTUAL_NOT_RUN')
    spec['spec_signature'] = _sha(dict(method=method, center=spec['center_point_vector_sha256'],
        free=free, fixed_route=route, radius=radius))
    if method != 'N1':
        witness = route_witness(case, x, free, radius)
        _require(not witness.get('PASS') or witness['unit'] in selected, 'WITNESS_UNSELECTED_ROUTE')
        spec['original_common_DAG_route_witness'] = witness
        spec['DAG_witness_is_SOC_PCS_Grid_feasible'] = False
    return spec
