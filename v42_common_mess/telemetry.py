"""Keep solver global bounds distinct from independent exact certificates."""
from fractions import Fraction
import math
import re
from pathlib import Path


FIELDS = (
    'Solver_ObjVal', 'Solver_ObjBound', 'Solver_MIPGap', 'Solver_MIPGap_percent',
    'solver_global_LB', 'solver_global_gap', 'solver_global_gap_percent',
    'solver_global_gap_valid', 'solver_global_gap_target_met',
    'solver_bound_provenance', 'solver_bound_rejection_reason',
    'Root_LP_seconds', 'Root_LP_status', 'B_and_B_Node_count',
    'Full_MILP_Native_Runtime', 'Solver_MemUsed_GB', 'Solver_MaxMemUsed_GB',
    'full_MILP_telemetry', 'full_MILP_bound_identity', 'full_MILP_native_log',
    'Presolve_seconds', 'Barrier_seconds', 'Crossover_seconds', 'Presolved_Rows',
    'Presolved_Columns', 'Presolved_NNZ', 'Root_completion_native_elapsed_seconds',
    'Post_root_native_seconds', 'model_build_wall_seconds', 'memory_after_native',
)


def finite(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def verified_gap(upper, lower):
    """Report a solver-based gap only against an independently verified UB."""
    lower = finite(lower)
    if upper is None or lower is None:
        return None
    upper, lower = Fraction(upper), Fraction(lower)
    if lower > upper:
        return None
    if upper == 0:
        return 0. if lower == 0 else None
    return float((upper - lower) / abs(upper))


def admit_solver_bound(identity, transport, *, unrestricted, bound, status,
                       native_error_code=None, runtime_known=True):
    """A neighborhood bound cannot pass this full-domain admission gate."""
    checks = identity.get('unrestricted_checks', {})
    exact = identity.get('unrestricted_original_C3A_MILP') is True and all(
        checks.get(key) is True for key in (
            'all_original_bounds_exact', 'all_original_integer_types_exact',
            'all_original_rows_and_no_additional_cuts',
            'no_neighborhood_or_hamming_constraint', 'original_minimization'))
    exact = exact and all(transport.get(key) is True for key in (
        'PASS', 'original_P1_bit_exact', 'integer_and_full_LP_domains_identical'))
    # 12 is GRB.NUMERIC; 10014 is GRB.ERROR_NUMERIC. A numerically failed
    # solve keeps its raw attributes but cannot supply the admitted global LB.
    if not unrestricted or not exact:
        return None, 'RESTRICTED_OR_UNPROVEN_DOMAIN'
    if not runtime_known:
        return None, 'UNMEASURED_NATIVE_RUNTIME'
    if status not in (2, 7, 8, 9, 10, 11, 13, 15, 16, 17) or native_error_code == 10014:
        return None, 'INVALID_OR_NUMERIC_SOLVER_STATUS'
    bound = finite(bound)
    return (bound, None) if bound is not None else (None, 'NO_FINITE_SOLVER_BOUND')


def root_lp(logfile):
    path = Path(logfile)
    if not path.exists():
        return dict(Root_LP_seconds=None, Root_LP_status='NATIVE_LOG_UNAVAILABLE')
    log = path.read_text(encoding='utf-8', errors='replace')
    phases = {}
    patterns = {
        'Presolve_seconds': r'Presolve time:\s*([0-9.eE+-]+)s',
        'Crossover_seconds': r'Crossover time:\s*([0-9.eE+-]+) seconds',
        'Barrier_seconds': r'Barrier solved model in \d+ iterations and\s*([0-9.eE+-]+) seconds',
    }
    for key, pattern in patterns.items():
        found = re.findall(pattern, log)
        phases[key] = float(found[-1]) if found else None
    dimensions = re.findall(r'Presolved:\s*(\d+) rows,\s*(\d+) columns,\s*(\d+) nonzeros', log)
    for key, value in zip(('Presolved_Rows', 'Presolved_Columns', 'Presolved_NNZ'),
                          dimensions[-1] if dimensions else (None, None, None)):
        phases[key] = int(value) if value is not None else None
    # Log timestamps are elapsed native time and have only printed precision.
    # Crossover is included in Root relaxation; do not add it a second time.
    timed_root = re.search(r'Root relaxation:[^\r\n]*\(([^\r\n]+)\)', log)
    phases['Root_completion_native_elapsed_seconds'] = None
    if timed_root:
        elapsed = re.search(r'([0-9.eE+-]+)\s*s', timed_root[1])
        if elapsed:
            phases['Root_completion_native_elapsed_seconds'] = float(elapsed[1])
    # This is the native Root relaxation time, excluding presolve and later
    # root cuts; callback elapsed time would include those different costs.
    match = re.search(r'Root relaxation:([^\r\n]*?),\s*([0-9.eE+-]+) seconds', log)
    if match:
        status = 'NATIVE_LOG_ROOT_INTERRUPTED' if 'interrupted' in match[1].lower() else 'NATIVE_LOG_REPORTED'
        # Root completion may be followed by a separately printed elapsed
        # timestamp. Keep absent timestamps unknown instead of deriving them
        # by adding overlapping presolve, barrier and crossover timings.
        return dict(phases, Root_LP_seconds=float(match[2]), Root_LP_status=status)
    status = 'PRESOLVE_SOLVED_NO_ROOT_LP' if 'All rows and columns removed' in log else 'NOT_REPORTED_OR_ROOT_INCOMPLETE'
    return dict(phases, Root_LP_seconds=None, Root_LP_status=status)


def summarize_full(history, exact_ub):
    """Raw attributes use the last full run; global LB uses the best valid run."""
    rows = [row for row in history if row.get('method') == 'FULL_MILP']
    last = rows[-1] if rows else {}
    result = {key: last.get(key) for key in FIELDS}
    valid = [row for row in rows if row.get('solver_global_gap_valid') is True
             and finite(row.get('solver_global_LB')) is not None]
    best = max(valid, key=lambda row: row['solver_global_LB']) if valid else {}
    lower = best.get('solver_global_LB')
    gap = verified_gap(exact_ub, lower)
    result.update(solver_global_LB=lower, solver_global_gap=gap,
        solver_global_gap_percent=None if gap is None else 100 * gap,
        solver_global_gap_valid=gap is not None,
        solver_global_gap_target_met=gap is not None and gap <= .03,
        solver_bound_provenance=best.get('solver_bound_provenance'),
        full_MILP_telemetry=best.get('telemetry_receipt', last.get('telemetry_receipt')),
        full_MILP_bound_identity=best.get('original_model_identity'),
        full_MILP_native_log=last.get('native_log'),
        Full_MILP_Native_Runtime=sum(row.get('Native_Runtime') or 0. for row in rows) if rows else None)
    root_times = [row['Root_LP_seconds'] for row in rows if finite(row.get('Root_LP_seconds')) is not None]
    result['Root_LP_seconds'] = sum(root_times) if root_times else None
    nodes = [row['B_and_B_Node_count'] for row in rows if finite(row.get('B_and_B_Node_count')) is not None]
    result['B_and_B_Node_count'] = sum(nodes) if nodes else None
    return result


def select_fields(result):
    return {key: result.get(key) for key in FIELDS}
