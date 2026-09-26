"""Audit the sparse preferred-bound failure and authorize cache-safe repair."""
from bootstrap import *
from authorize_b2_active_resume import function_sha, nested_sha


def main():
    prior=read(H/'B2_PERFORMANCE_RESUME_AUTHORITY.json')
    failure=read(H/'diagnostic_attempts/B2_PREFERRED_BOUND_FAIL_20260921/B2_FAILURE.json')
    trace=H/'diagnostic_attempts/B2_PREFERRED_BOUND_FAIL_20260921/call_00003'
    enter=read(trace/'ENTER.json')
    closure=read(trace/'FULL_SEPARATION_CLOSURE.json')
    assert 'V35_MESS_FULL_MODEL_WORSE_THAN_RESTRICTED_INCUMBENT' in failure['error']
    assert closure['status']=='PASS' and closure['all_original_electrical_rows_checked']
    assert closure['mip_gap']<=.001 and closure['incumbent']>enter['quality_bound']+1e-6
    assert enter['preferred_incumbent_loaded']
    names=('four_thread_no_cutoff_candidate','coefficients','traffic')
    checks={name:dict(expected=prior['function_ast_sha256'][name]['current'],
                      actual=function_sha(H/'mess_runtime.py',name)) for name in names}
    checks['search.current_b0_seed']=dict(
        expected=prior['function_ast_sha256']['search.current_b0_seed']['current'],
        actual=nested_sha(H/'mess_runtime.py','search','current_b0_seed'))
    assert all(v['expected']==v['actual'] for v in checks.values())
    cache=[p for p in (H/'B2/candidate_cache').rglob('*') if p.is_file()]
    assert len(cache)>=prior['cache_file_count']
    assert read(H/'FINAL_CANDIDATE_FREEZE.json')['B2_SEARCH_DOMAIN_CHANGED'] is False
    save(H/'B2_PREFERRED_BOUND_REPAIR_AUTHORITY.json',dict(
        status='PASS',failure_hypothesis='Sparse fixed-route polish objective was used as a full-grid quality bound before its omitted electrical rows were checked; the new audit will test this directly',
        prior_mess_runtime_sha256=prior['current_mess_runtime_sha256'],
        current_mess_runtime_sha256=sha(H/'mess_runtime.py'),
        original_failure=record(H/'diagnostic_attempts/B2_PREFERRED_BOUND_FAIL_20260921/B2_FAILURE.json'),
        original_closure=record(trace/'FULL_SEPARATION_CLOSURE.json'),
        bound=enter['quality_bound'],closed_full_grid_incumbent=closure['incumbent'],
        incumbent_minus_bound=closure['incumbent']-enter['quality_bound'],
        repair='Audit preferred start against all 31,945,536 original electrical rows; only full-grid-feasible preferred incumbent may provide a quality bound',
        original_acceptance_guard_unchanged=True,objective_route_domain_mipgap_unchanged=True,
        candidate_problem_unchanged=True,candidate_function_ast=checks,
        restricted_cache_entries=len(cache),restricted_cache_only=True,
        full_solution_reused=False,exact_AC_reused=False))
    print('PREFERRED_BOUND_REPAIR_AUTHORIZED',len(cache))


if __name__=='__main__':
    main()
