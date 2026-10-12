"""Meaningful Native0 restriction regressions on the actual Source18r axes."""
import json
from pathlib import Path
import numpy as np

from . import verify as v


def main():
    case = v.load_native_case()
    center = case.point
    binary = np.flatnonzero(case.d['types'] != 'C')
    free = np.flatnonzero(np.char.startswith(case.d['names'], 'charge_mode['))
    route = np.flatnonzero(np.char.startswith(case.d['names'], 'route_flow['))
    fixed = np.setdiff1d(binary, free)
    spec = dict(method='N1', selected_units=[], free_binary_columns=free.tolist(),
                fixed_binary_columns=fixed.tolist(), fixed_route_columns=route.tolist(), hamming_radius=384)
    lower, upper = case.d['lower'].copy(), case.d['upper'].copy()
    ids = np.r_[fixed, route]
    lower[ids] = center[ids]
    upper[ids] = center[ids]
    tests = {}
    receipt = v.audit_neighborhood(case, center, spec, lower, upper, v.DOCS/'N1_INITIAL_INDEPENDENT_NATIVE0.json')
    tests['real_N1_96_modes_full_aliases_center_included'] = receipt['PASS']

    def rejects(label, fn, expected):
        try:
            fn()
        except ValueError as exc:
            tests[label] = dict(PASS=expected in str(exc), error=str(exc))
        else:
            tests[label] = dict(PASS=False, error='INVALID_RESTRICTION_ACCEPTED')

    wrong = lower.copy()
    j = int(fixed[0])
    wrong[j] = 1.-center[j]
    rejects('wrong_fixed_center_rejected', lambda: v.audit_neighborhood(case, center, spec, wrong, upper),
            'UNDECLARED_BOUND_RESTRICTION_OR_CENTER_DRIFT')
    q = int(np.flatnonzero(np.char.startswith(case.d['names'], 'Pch['))[0])
    restricted = upper.copy()
    restricted[q] = case.d['upper'][q]-1.
    rejects('undeclared_continuous_Pch_limit_rejected', lambda: v.audit_neighborhood(case, center, spec, lower, restricted),
            'UNDECLARED_BOUND_RESTRICTION_OR_CENTER_DRIFT')
    missing = dict(spec, fixed_route_columns=route[:-1].tolist())
    l2, u2 = case.d['lower'].copy(), case.d['upper'].copy()
    i2 = np.r_[fixed, route[:-1]]
    l2[i2], u2[i2] = center[i2], center[i2]
    rejects('missing_continuous_route_alias_fix_rejected', lambda: v.audit_neighborhood(case, center, missing, l2, u2),
            'UNSELECTED_CONTINUOUS_ROUTE_FIX_INCOMPLETE')
    coeff = np.where(center[free] == 1., -1., 1.)
    rhs = 384.-np.count_nonzero(center[free])
    tests['actual_384_mode_hamming_recipe'] = v.audit_hamming(center, free, 384, coeff, rhs)['PASS']
    rejects('wrong_hamming_RHS_rejected', lambda: v.audit_hamming(center, free, 384, coeff, rhs+1.),
            'HAMMING_COEFFICIENT_OR_RHS_DRIFT')
    rejects('wrong_hamming_sign_rejected', lambda: v.audit_hamming(center, free, 384, -coeff, rhs),
            'HAMMING_COEFFICIENT_OR_RHS_DRIFT')
    fractional = center.copy()
    fractional[int(binary[0])] = np.nextafter(center[int(binary[0])], .5)
    rejects('fractional_raw_Dense_B_not_rounded', lambda: v.audit_hamming(fractional, binary[:1], 1, np.ones(1), 1),
            'HAMMING_LITERAL_CENTER_REQUIRED')
    historical_raw = v.load_point(v.SOURCE/'FRESH_U4/RAW_00.npz')
    original = case.lift(historical_raw)
    full_name = {str(name): j for j, name in enumerate(case.original_d['names'])}
    counts = {}
    for unit in sorted(case.graph[1]):
        with np.load(v.ROOT/'docs/v42_physical_global_lb_pilot'/('UNIT_'+unit+'_DATA.npz'), allow_pickle=False) as z:
            names = z['names'].copy()
        with np.load(v.ROOT/'docs/v42_physical_global_lb_pilot'/('UNIT_'+unit+'_START.npz'), allow_pickle=False) as z:
            saved = z['x'].copy() if 'x' in z.files else z['point'].copy()
        projected = original[[full_name[str(name)] for name in names]]
        v.require(np.array_equal(saved, projected), 'INDEPENDENT_LITERAL_UNIT_SOURCE_ALIAS_PROJECTION_DRIFT:'+unit)
        counts[unit] = len(saved)
    tests['all_four_original_literal_unit_START_points_exactly_match_actual_frozen_RAW00_inverse_aliases'] = dict(
        PASS=True, columns=counts, historical_RAW00_vector_sha256=v.vector_sha(historical_raw),
        current_FULL_verified_initial_vector_sha256=v.vector_sha(center),
        historical_RAW00_and_FINAL_point_coordinates_identical=bool(np.array_equal(historical_raw, center)),
        coordinate_difference_count=int(np.count_nonzero(historical_raw != center)),
        maximum_coordinate_difference=float(abs(historical_raw-center).max()))
    passed = all(x if isinstance(x, bool) else x['PASS'] for x in tests.values())
    result = dict(PASS=passed, source_sha=v.SOURCE_SHA, case_sha=v.CASE_SHA, tests=tests,
                  Native_optimize_calls=0, Gurobi_imported='gurobipy' in __import__('sys').modules)
    v.write(v.DOCS/'INDEPENDENT_REGRESSION_TESTS.json', result)
    print(json.dumps(dict(PASS=passed, tests=len(tests), Native_optimize_calls=0)))
    return 0 if passed else 2


if __name__ == '__main__':
    raise SystemExit(main())
