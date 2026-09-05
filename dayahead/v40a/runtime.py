"""Keep route candidates, solver invocations and elapsed stage time distinct."""
from __future__ import annotations


def runtime_profile(result, events, *, materialization, a0, verification,
                    fresh, restoration, total, current_execution=None, rsp_base=0.0):
    trace = result['search_info']['trace']
    summed = lambda key: sum(row.get(key, 0) for row in trace)
    full_wall = summed('full_MILP_wallclock_seconds')
    profile = {
        'RSP_base_materialization': rsp_base, 'D1_context_materialization': materialization, 'A0': a0,
        **result['runtime'], 'M1_route_candidate_search': max(0, result['runtime']['M1'] - full_wall),
        'M1_full_MILP': full_wall,
        'M1_cheap_screen': summed('cheap_screen_wallclock_seconds'),
        'M1_restricted_candidate_wallclock': summed('restricted_wallclock_seconds'),
        'Planning_verification': verification, 'Fresh': fresh, 'AC_restoration': restoration,
        'Total': total, 'TOTAL_RUNTIME_SECONDS': total, **result['counts'],
        'AIDC_OPTIMIZATION_PASSES': 2,
        'TOTAL_GUROBI_OPTIMIZE_CALLS': len(events),
        'TOTAL_ROUTE_CANDIDATES_EVALUATED': summed('restricted_unique_candidate_state_solves'),
        'ROUTE_CANDIDATE_COUNT_UNIT': 'CANDIDATE_STATE_PAIRS_SELECTED_BY_INHERITED_BEAM_INCLUDING_CACHE_HITS',
        'ROUTE_CANDIDATE_CACHE_MISSES': summed('restricted_cache_misses'),
        'ROUTE_CANDIDATE_CACHE_HITS': summed('restricted_cache_hits'),
        'INTERNAL_FULL_MILP_CHILD_SOLVES': summed('full_MILP_actual_solver_calls'),
        'INTERNAL_FULL_MILP_CHILD_CACHE_HITS': summed('full_MILP_cache_hits'),
        'M1_beam_trace': trace,
        'solver_wallclock_by_stage': {}, 'solver_runtime_by_stage': {},
        'solver_events': events,
        'stage_overlap_note': 'Planning verification and RSP base loading are also included in their enclosing stage wallclock; do not sum overlapping fields.',
    }
    for event in events:
        stage = event['stage']
        for field, key in [('solver_wallclock_by_stage', 'wallclock_seconds'),
                           ('solver_runtime_by_stage', 'solver_runtime_seconds')]:
            profile[field][stage] = profile[field].get(stage, 0) + event.get(key, 0)
    if current_execution is not None:
        profile['current_resume_execution_seconds'] = current_execution
        profile['Total_scope'] = 'PAIRED_PIPELINE_WITH_ONCE_MEASURED_M1_PREFIX_PLUS_CURRENT_FEEDBACK_AND_VERIFICATION'
    return profile


def comparison(result, materialization, a0):
    old = materialization + a0 + result['runtime']['M1']
    new = old + result['runtime']['A1'] + result['runtime']['MF']
    j_old, j_new = result['objectives']['J_M1'], result['objectives']['J_FINAL']
    return {
        'comparison_design': 'PAIRED_SHARED_A0_M1_PREFIX; no duplicate expensive search',
        'J_old': j_old, 'J_new': j_new,
        'relative_J_improvement': (j_old - j_new) / j_old if j_old else None,
        'runtime_old': old, 'runtime_new': new, 'runtime_ratio': new / old,
        'A1_overhead_seconds': result['runtime']['A1'],
        'MF_overhead_seconds': result['runtime']['MF'],
        'total_feedback_overhead_seconds': new - old,
        'OLD_full_route_search_calls': 1, 'NEW_full_route_search_calls': 1,
        'runtime_scope': 'PLANNING_DECISION_PIPELINE; Fresh and post-freeze AC restoration reported separately',
    }
