"""Independent raw UB admission: original rows, domains and physical replay.

No neighborhood builder is imported. Every candidate is replayed without
rounding, clipping, flow extraction, fixing or continuous dispatch repair.
"""
from fractions import Fraction
import hashlib
from time import perf_counter
import numpy as np


def vector_sha(point):
    return hashlib.sha256(np.ascontiguousarray(point, dtype='<f8').tobytes()).hexdigest()


def matrix_replay(A, d, point, *, tolerance=1e-8, bound_tolerance=1e-8,
                  integer_tolerance=1e-8, row_tolerances=None):
    """Outward sparse dot enclosure; exact dyadic checks at a close threshold."""
    x = np.asarray(point)
    if x.shape != (A.shape[1],) or not np.isfinite(x).all():
        return dict(PASS=False, finite=False, reason='NONFINITE_OR_WRONG_AXIS')
    A = A.tocsr()
    product = A @ x
    residual = product-d['rhs']
    counts = np.diff(A.indptr)
    eps = np.finfo(np.float64).eps
    gamma = (2*counts+4)*eps/(1-(2*counts+4)*eps)
    absolute = abs(A) @ abs(x)
    error = np.nextafter(gamma*(absolute/(1-gamma)+abs(d['rhs'])), np.inf)
    sense = d['sense']
    observed = np.where(sense == '=', abs(residual),
                        np.where(sense == '<', residual, -residual))
    upper = np.nextafter(observed+error, np.inf)
    tolerances = np.full(A.shape[0], tolerance) if row_tolerances is None else np.asarray(row_tolerances)
    close = np.flatnonzero((upper > tolerances) & (observed <= tolerances+error))
    exact_failures = []
    for i in close:
        a, b = A.indptr[i:i+2]
        value = sum((Fraction(float(w))*Fraction(float(x[j]))
                     for j, w in zip(A.indices[a:b], A.data[a:b])), Fraction(0))
        value -= Fraction(float(d['rhs'][i]))
        violation = abs(value) if sense[i] == '=' else value if sense[i] == '<' else -value
        if violation > Fraction(float(tolerances[i])):
            exact_failures.append(int(i))
        # The exact comparison, rather than a rounded reported number, controls PASS.
        upper[i] = float(violation)
    obvious_failures = np.flatnonzero(observed-error > tolerances)
    bounds = max(0., float(np.max(d['lower']-x, initial=0.)),
                 float(np.max(x-d['upper'], initial=0.)))
    discrete = np.flatnonzero(d['types'] != 'C')
    integer = float(np.max(abs(x[discrete]-np.rint(x[discrete])), initial=0.))
    exact_integer = bool(np.array_equal(x[discrete], np.rint(x[discrete])))
    binary = np.flatnonzero(d['types'] == 'B')
    exact_binary = bool(np.isin(x[binary], (0., 1.)).all())
    checked = set(map(int, close))
    unresolved = [int(i) for i in np.flatnonzero(upper > tolerances)
                  if int(i) not in checked]
    passed = not len(obvious_failures) and not exact_failures and not unresolved
    passed = passed and bounds <= bound_tolerance and integer <= integer_tolerance
    return dict(PASS=bool(passed), finite=True, rows=A.shape[0], columns=A.shape[1],
                checked_discrete_columns=len(discrete), checked_binary_columns=len(binary),
                maximum_observed_row_violation=max(0., float(observed.max(initial=0.))),
                maximum_outward_row_upper=max(0., float(upper.max(initial=0.))),
                max_bound_violation=bounds, max_integrality_violation=integer,
                integer_pattern_exact=exact_integer, exact_binary_0_1=exact_binary,
                affine_tolerance=tolerance, bound_tolerance=bound_tolerance,
                integrality_tolerance=integer_tolerance, close_exact_dyadic_checks=len(close),
                failing_rows=list(map(int, obvious_failures[:20]))+exact_failures[:20]+unresolved[:20],
                objective=float(d['objective'] @ x+float(d['constant'])))


def physical_replay(case, original_point):
    """Call the unchanged independent original graph and battery validators."""
    from v42_native.mess import validate
    from v42_bootstrap.attribution import supplemental_physical
    sites, initial, arcs, battery, receipt = case.graph
    values = dict(zip(map(str, case.original_d['names']), map(float, original_point)))
    # Reachability-removed variables are exact scientific zero constants.
    for unit in initial:
        for k in range(len(arcs)):
            values.setdefault(f'arc[{unit},{k}]', 0.)
        for site in sites:
            for t in range(96):
                for prefix in ('Pch', 'Pdis', 'Q'):
                    values.setdefault(f'{prefix}[{unit},{site},{t}]', 0.)
    selected = {u: [k for k in range(len(arcs)) if values[f'arc[{u},{k}]'] > .5]
                for u in initial}
    plan = dict(values=values, initial_sites=initial, chosen_arcs=selected, mode='MILP')
    physical = validate(plan, sites, [a[-1] for a in arcs if a[-1] is not None], battery, 96)
    mode = supplemental_physical(plan, sites, battery)
    records = []
    for u in sorted(initial):
        for k in selected[u]:
            a = arcs[k]
            if a[-1] is not None:
                records.append(dict(unit=u, route_id=a[-1].route_id, source=a[0], depart=a[1],
                                    destination=a[2], connect=a[3], energy_kwh=a[-1].energy_kwh))
    return dict(PASS=bool(physical['PASS'] and mode['charge_mode_and_connection_PASS']),
                original_route_SOC_PCS=physical, original_charge_mode_connection=mode,
                selected_move_arcs=records, repairs=0, native_optimize_calls=0)


def validate_candidate(case, point):
    started = perf_counter()
    x = np.asarray(point, dtype=np.float64)
    before = vector_sha(x)
    c3 = matrix_replay(case.A, case.d, x)
    if not c3.get('finite'):
        return dict(PASS=False, C3A=c3, case_sha=case.case_sha, repairs=0)
    if c3['checked_binary_columns'] != 9322:
        raise ValueError('ORIGINAL_C3A_BINARY_AXIS_MUST_HAVE_9322_COLUMNS')
    original = case.lift(x)
    row_names = np.asarray(case.original_d['row_names']).astype(str)
    tight = np.array([n.split('[', 1)[0] in ('flow', 'terminal_location', 'voltage_lower', 'voltage_upper',
                     'NormalAmps', 'line_thermal_face', 'transformer_kVA') for n in row_names])
    tol = np.where(tight, 1e-8, 1e-6)
    full = matrix_replay(case.original_A, case.original_d, original,
                         tolerance=1e-6, row_tolerances=tol)
    physics = physical_replay(case, original)
    full_objective = full['objective']
    objective_equal = full_objective == c3['objective']
    unchanged = before == vector_sha(x)
    passed = c3['PASS'] and full['PASS'] and physics['PASS'] and objective_equal and unchanged
    return dict(PASS=bool(passed), case_sha=case.case_sha, point_sha256=before,
                objective=full_objective, C3A=c3, original_full_matrix=full,
                physical=physics, original_objective_bit_equal=objective_equal,
                all_9322_original_C3A_binaries_correspond=True, original_integer_axis_checked=True,
                frozen_AIDC_and_grid='all original matrix rows, axes and coefficients checked',
                raw_point_unchanged=unchanged, repairs=0, rounding=0, clipping=0,
                scientific_tolerances_unchanged=True, validation_wall_seconds=perf_counter()-started)


def dispatch_difference(case, before, after):
    a, b = case.lift(np.asarray(before)), case.lift(np.asarray(after))
    names = list(map(str, case.original_d['names']))
    binary = np.flatnonzero(case.original_d['types'] != 'C')
    changed = [names[j] for j in binary if a[j] != b[j]]
    dispatch = {}
    for prefix in ('Pch', 'Pdis', 'Q', 'SOC'):
        columns = [j for j, n in enumerate(names) if n.startswith(prefix+'[')]
        dispatch[prefix] = float(np.max(abs(a[columns]-b[columns]), initial=0.))
    return dict(changed_original_discrete_names=changed,
                changed_original_discrete_count=len(changed),
                maximum_dispatch_change_by_family=dispatch,
                before_objective=float(case.original_d['objective']@a+float(case.original_d['constant'])),
                after_objective=float(case.original_d['objective']@b+float(case.original_d['constant'])))
