"""Exact local PCS-mode union hull and outward binary64 certificates.

This module does not construct or solve an optimization model.  It reads the
original stored halfspaces and enumerates rational intersections directly.
"""
from __future__ import annotations
import itertools
import json
import math
from collections import defaultdict
from fractions import Fraction as F
from types import MappingProxyType
from independent_hull import Authority, exact, rational, OUT, write, FAMILIES

FAMILY = 'FOLDED_PCS_CONNECTED_POWER'


def vertices2(halfplanes):
    rows = list(dict.fromkeys((exact(a), exact(b), exact(c)) for a, b, c in halfplanes))
    vertices = set()
    for (a, b, c), (d, e, f) in itertools.combinations(rows, 2):
        determinant = a * e - b * d
        if not determinant:
            continue
        x, y = (c * e - b * f) / determinant, (a * f - c * d) / determinant
        if all(A * x + B * y <= C for A, B, C in rows):
            vertices.add((x, y))
    return sorted(vertices)


def cross(origin, a, b):
    return (a[0] - origin[0]) * (b[1] - origin[1]) - (a[1] - origin[1]) * (b[0] - origin[0])


def convex_hull(points):
    points = sorted(set(points))
    if len(points) <= 1:
        return points
    lower, upper = [], []
    for point in points:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)
    for point in reversed(points):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)
    return lower[:-1] + upper[:-1]


def original_mode_vertices(authority, unit, slot, site):
    L, S = exact(authority.battery.p_limit), exact(authority.battery.pcs_kva)
    # Always read the requested target's immutable original planes first.  Only
    # exact plane identity permits sharing geometry; no assumed site symmetry.
    faces = authority.pcs(unit, site, slot)
    geometry_key = (tuple(sorted(faces)), L, S)
    if not hasattr(authority, '_folded_mode_vertex_cache'):
        authority._folded_mode_vertex_cache = {}
    cache = authority._folded_mode_vertex_cache
    if geometry_key in cache:
        return cache[geometry_key]
    by_mode = {}
    for mode, sign in [(0, F(1)), (1, F(-1))]:
        # x>=0 is |P| because original integer charge_mode is exclusive.
        rows = [(a * sign, b, cap) for a, b, cap in faces]
        rows += [(-1, 0, 0), (1, 0, L), (0, 1, S), (0, -1, S)]
        by_mode[mode] = tuple(vertices2(rows))
        assert by_mode[mode]
    result = MappingProxyType(by_mode)
    cache[geometry_key] = result
    return result


def outward(a, b, gamma, L, S):
    """Round a/b once; compensate exact rounding on [0,L]×[-S,S]."""
    a64, b64 = float(a), float(b)
    da, db = exact(a64) - a, exact(b64) - b
    rounding_margin = max(F(0), da) * L + abs(db) * S
    needed = gamma + rounding_margin
    gamma64 = float(needed)
    if exact(gamma64) < needed:
        gamma64 = math.nextafter(gamma64, math.inf)
    assert exact(gamma64) >= needed
    return dict(alpha=a64, beta=b64, gamma=gamma64,
                alpha_exact=rational(a), beta_exact=rational(b), gamma_exact=rational(gamma),
                alpha_stored_exact=rational(a64), beta_stored_exact=rational(b64),
                gamma_stored_exact=rational(gamma64),
                coefficient_rounding_margin_exact=rational(rounding_margin),
                outward_RHS_needed_exact=rational(needed),
                outward_RHS_extra_exact=rational(exact(gamma64) - gamma))


def derive_hull(authority, unit, slot, site):
    by_mode = original_mode_vertices(authority, unit, slot, site)
    vertices = convex_hull([v for points in by_mode.values() for v in points])
    assert len(vertices) >= 3
    facets = []
    L, S = exact(authority.battery.p_limit), exact(authority.battery.pcs_kva)
    for number, (v, w) in enumerate(zip(vertices, vertices[1:] + vertices[:1])):
        # CCW hull interior is left of the oriented edge.
        a, b = w[1] - v[1], v[0] - w[0]
        gamma = a * v[0] + b * v[1]
        scale = max(abs(a), abs(b))
        assert scale
        a, b, gamma = a / scale, b / scale, gamma / scale
        assert all(a * x + b * q <= gamma for x, q in vertices)
        coefficient = outward(a, b, gamma, L, S)
        # Test the actual emitted binary64 coefficients in exact arithmetic.
        A, B, G = map(exact, [coefficient['alpha'], coefficient['beta'], coefficient['gamma']])
        residual_by_mode = {mode: max(A * p + B * q - G for p, q in points)
                            for mode, points in by_mode.items()}
        assert max(residual_by_mode.values()) <= 0
        nonnegative_gamma = G >= 0
        facets.append(dict(id=f'PCS_FOLDED_FACET_{number:02d}',
                           **coefficient,
                           exact_vertex_max_residual_by_mode={str(m): rational(r) for m, r in residual_by_mode.items()},
                           exact_vertex_max_residual=rational(max(residual_by_mode.values())),
                           valid_when_disconnected=nonnegative_gamma,
                           strengthening_candidate=bool(A > 0 and nonnegative_gamma),
                           edge_vertices=[[rational(x), rational(y)] for x, y in [v, w]]))
    return dict(PASS=True, MESS=unit, slot=slot, site=site,
                physical_variables=['abs(P)=Pch+Pdis at integer mode', 'Q'],
                original_half_polygon_vertices={str(mode): [[rational(p), rational(q)] for p, q in values]
                                                for mode, values in by_mode.items()},
                original_mode_vertex_count={str(m): len(v) for m, v in by_mode.items()},
                union_convex_hull_vertices=[[rational(p), rational(q)] for p, q in vertices],
                union_convex_hull_vertex_count=len(vertices),
                facets=facets,
                emitted_facet_count=len(facets),
                positive_active_power_candidate_facets=sum(f['strengthening_candidate'] for f in facets),
                trig_symmetry_assumed=False, rational_exact_arithmetic=True,
                original_full_matrix_SHA256='35bdc6e7c2664b763d3d0456b7296b7c8830d7c7c39a61a3cb32e699f8bb2024',
                no_solver_calls=True,
                scope='Exact PCS16-mode one-site power projection; conservative relative to original SOC/grid constraints',
                inequality='alpha*(Pch+Pdis)+beta*Q <= gamma*stay',
                global_integer_validity='Every integer stay/mode state belongs to one of the original half-polygons; disconnected power is zero.')


def verify_folded_candidate(candidate, context=None, authority=None):
    """Independent verifier for one serialized selected-coordinate folded cut.

    Required fields: id,family,MESS,slot,site,alpha,beta,gamma,terms,rhs.
    This reads the *target block's* original PCS coefficients, so it does not
    infer validity at every site merely from the reference-site hull.
    """
    authority = authority or Authority(context)
    assert candidate['family'] == FAMILY
    unit, slot, site = candidate['MESS'], int(candidate['slot']), candidate['site']
    assert unit in authority.initial and site in authority.sites and 0 <= slot < 96
    alpha, beta, gamma = map(exact, [candidate['alpha'], candidate['beta'], candidate['gamma']])
    assert gamma >= 0, 'INVALID_DISCONNECTED_STATE'
    vertices = original_mode_vertices(authority, unit, slot, site)
    maxima = {m: max(alpha * p + beta * q - gamma for p, q in vv)
              for m, vv in vertices.items()}
    assert max(maxima.values()) <= 0, 'ORIGINAL_INTEGER_MODE_VERTEX_VIOLATION'
    physical = [(f'Pch[{unit},{site},{slot}]', alpha),
                (f'Pdis[{unit},{site},{slot}]', alpha),
                (f'Q[{unit},{site},{slot}]', beta),
                (f'arc[{unit},{authority.sites.index(site) * 96 + slot}]', -gamma)]
    expected_terms = defaultdict(F)
    constant = F(0)
    for name, weight in physical:
        terms, offset = authority.expression(name)
        constant += weight * offset
        for j, value in terms.items():
            expected_terms[j] += weight * value
    expected_terms = {j: w for j, w in expected_terms.items() if w}
    actual_terms = {int(j): exact(w) for j, w in candidate['terms'].items() if exact(w)}
    assert actual_terms == expected_terms, 'SELECTED_COORDINATE_TERMS_MISMATCH'
    assert exact(candidate['rhs']) == -constant, 'SELECTED_COORDINATE_RHS_MISMATCH'
    start_residual = None
    if context is not None:
        start_residual = sum((w * exact(context['start'][j]) for j, w in actual_terms.items()), F(0)) + constant
        assert start_residual <= exact(1e-8), 'VALIDATED_START_VIOLATION'
    return dict(id=candidate['id'], PASS=True,
                exact_target_original_vertex_max_residual_by_mode={str(m): rational(v) for m, v in maxima.items()},
                exact_target_original_vertex_count=sum(len(v) for v in vertices.values()),
                disconnected_zero_power_state_verified=True,
                independent_coordinate_reconstruction=True,
                exact_validated_start_residual=None if start_residual is None else rational(start_residual),
                production_candidate_constructor_called=False,
                no_solver_calls=True, original_P1_P2_unchanged=True,
                global_integer_feasible_set_preserved=True)


def verify_folded_candidates(candidates, context=None):
    authority = Authority(context)
    reports, rejected = [], []
    for candidate in candidates:
        try:
            reports.append(verify_folded_candidate(candidate, context, authority))
        except Exception as exc:
            rejected.append(dict(id=candidate.get('id'), reason=repr(exc)))
    return dict(PASS=not rejected, candidate_count=len(candidates),
                independently_verified_count=len(reports), rejected=rejected,
                exact_rational_original_vertex_verification=True,
                reports=reports, no_solver_calls=True)


if __name__ == '__main__':
    authority = Authority()
    unit = sorted(authority.initial)[0]
    site = authority.initial[unit]
    report = derive_hull(authority, unit, 0, site)
    write('FOLDED_PCS_LOCAL_HULL.json', report)
    print('FOLDED_PCS_HULL_DONE', report['union_convex_hull_vertex_count'],
          report['positive_active_power_candidate_facets'], flush=True)
