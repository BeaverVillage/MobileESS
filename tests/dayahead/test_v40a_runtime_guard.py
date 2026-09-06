import pytest
from dayahead.v40a.outcome_guard import prohibit_fresh_calls
from dayahead.v40a.runtime import runtime_profile


def test_fresh_entrypoint_blocked_in_planning_scope_and_restored():
    from dayahead.v28r2 import opendss_backend
    original = opendss_backend.run_fresh_opendss
    with prohibit_fresh_calls() as counts:
        with pytest.raises(PermissionError, match='FRESH_NOT_ALLOWED'):
            opendss_backend.run_fresh_opendss()
        assert counts['blocked_Fresh_attempts'] == 1
    assert opendss_backend.run_fresh_opendss is original


def test_runtime_counts_candidates_separately_from_optimizer_calls():
    result = {'search_info': {'trace': [{'restricted_unique_candidate_state_solves': 7,
              'restricted_cache_misses': 5, 'full_MILP_wallclock_seconds': 20}]},
              'runtime': {'M1': 30, 'A1': 2, 'MF': 3}, 'counts': {}}
    events = [{'stage': 'M1', 'wallclock_seconds': 1, 'solver_runtime_seconds': .9}] * 15
    report = runtime_profile(result, events, materialization=1, a0=2, verification=1,
                             fresh=4, restoration=0, total=43)
    assert report['TOTAL_ROUTE_CANDIDATES_EVALUATED'] == 7
    assert report['TOTAL_GUROBI_OPTIMIZE_CALLS'] == 15
    assert report['M1_route_candidate_search'] == 10
    assert report['M1_full_MILP'] == 20
    assert all(k in report for k in ['A0','A1','MF','Planning_verification','Fresh','AC_restoration','Total'])


def test_windows_descriptor_read_and_readwrite_paths_are_guarded():
    import os
    from dayahead.v40a import firewall
    firewall.activate('2025-04-01')
    try:
        for flags in (os.O_RDONLY,os.O_RDWR):
            with pytest.raises(PermissionError,match='DATA_FIREWALL'):
                firewall.check_read('actual/outcomes.parquet',None,flags)
        firewall.check_read('outputs/fresh_binding.json',None,os.O_WRONLY)
    finally:firewall.deactivate()
