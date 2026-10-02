"""Actual native execution, threshold classification and conditional gates."""
import gzip
import numpy as np
from v42_threshold.common import *
from v42_threshold.closure import energy_predecessors,route_predecessors

def test_actual_exact_decision_run_and_no_min_rho_rerun():
    r=read(OUT/'B3_THRESHOLD_SOLVER.json');raw=gzip.decompress((OUT/'B3_THRESHOLD_SOLVER.raw.gz').read_bytes()).decode()
    assert r['kind']=='DIRECT' and r['optimize_calls']==1 and r['fixed_route_bounds']==0
    assert r['zero_objective_bound_not_B3_rho_LB'] and not r['callback_errors']
    assert 'Model has 0 linear objective coefficients' in raw
    assert r['settings']==settings('DIRECT')

def test_actual_classification_obeys_independent_point_and_proof():
    c=read(OUT/'B3_THRESHOLD_CERTIFICATE.json');d=read(OUT/'B3_THRESHOLD_SOLVER.json')
    if c['negative_certificate']:
        v=read(OUT/'B3_THRESHOLD_POINT_VALIDATION.json')
        assert v['threshold_certificate_PASS'] and v['rho']<=T-THRESHOLD_MARGIN
        assert v['grid']['independently_recomputed_P1']<=T-THRESHOLD_MARGIN
    if c['positive_certificate']:assert d['solver_status']==3 and d['fixed_route_bounds']==0
    if c['classification']=='B3_INCONCLUSIVE':assert not c['certificate_valid']
    assert c['negative_certificate']+c['positive_certificate']<=1

def test_candidate_infeasibility_is_not_full_threshold_proof():
    for k in ['W1','W2']:
        if (OUT/(k+'_SOLVER.json')).exists():
            r=read(OUT/(k+'_SOLVER.json'))
            assert not r['proven_infeasible'] and r['candidate_infeasibility_not_full_B3_certificate']
            assert r['fixed_route_bounds']==85592

def test_zero_B1_B2_production_downstream_expansion_calls():
    f=read(OUT/'FINAL_FLAGS.json')
    assert f['B1_OPTIMIZE_CALLS']==f['B2_OPTIMIZE_CALLS']==f['EXPANDED_WINDOW_OPTIMIZE_CALLS']==f['DECOMPOSITION_OPTIMIZE_CALLS']==0
    assert not any(f[k] for k in ['PRODUCTION_M1_RUN','P2_RUN','A2_RUN','M2_RUN','ACTUAL_RUN','FRESH_AC_RUN','IEEE8500_RUN','MAY_CAMPAIGN_RUN','SENSITIVITY_CAMPAIGN_RUN','EXCLUDED_PROBLEMS_NEW_WORK','M1_ACCEPTED','PROBLEM13_FINAL_VALIDATED','B0_WORK_TOUCHED','B1_COMPARISON_WORK_TOUCHED'])
    assert {p.stem for p in LOCAL.glob('*_STARTED.json')}<={'W1_STARTED','W2_STARTED','DIRECT_STARTED'}

def test_conditional_dependency_closure_not_another_window_search():
    c=read(OUT/'B3_THRESHOLD_CERTIFICATE.json');d=read(OUT/'CAUSAL_BACKWARD_CLOSURE.json')
    if c['classification']=='B3_INCONCLUSIVE':
        assert d['earliest_causal_predecessor_slot']==0 and not d['expanded_window_run'] and d['optimization_calls']==0
        assert d['dependency_graph_not_materiality_certificate'] and d['no_claim_window0_necessary_or_sufficient']
    else:assert d['execution']=='NOT_RUN_CERTIFICATE_OBTAINED' and d['earliest_causal_predecessor_slot'] is None

def test_physical_SOC_dependency_chain_to_initial_boundary():
    assert energy_predecessors(58)==list(range(58)) and energy_predecessors(66)==list(range(66))
    assert energy_predecessors(0)==[]

def test_route_predecessor_graph_includes_initial_state_without_pruning():
    graph=[('A',0,'A',1,None),('A',1,'A',2,None)]
    d=route_predecessors(graph,'A',2)
    assert d['earliest_slot']==0 and d['initial_node_is_ancestor'] and d['ancestor_arcs']==2

def test_actual_native_feasibility_seed_not_false_inherited_start_claim():
    r=read(OUT/'B3_THRESHOLD_SOLVER.json')
    assert r['inherited_start_violates_threshold'] and r['inherited_start_not_passed_as_feasible']
    assert r['inherited_original_complete_start_rho']==ORIGINAL_UB>T

def test_interrupted_root_log_marker_is_not_completed_root():
    a=read(OUT/'ROOT_COMPLETION_AUDIT.json');f=read(OUT/'FINAL_FLAGS.json')
    direct=next(r for r in a['runs'] if r['kind']=='DIRECT')
    if direct['root_interrupted'] or direct['root_time_limited']:assert not f['DIRECT_ROOT_COMPLETED']
    assert f['DIRECT_ROOT_COMPLETED']==direct['independently_completed_feasible_root']

def test_partial_upper_and_original_bound_do_not_use_zero_objective():
    f=read(OUT/'FINAL_FLAGS.json');c=read(OUT/'B3_THRESHOLD_CERTIFICATE.json')
    assert f['ORIGINAL_M1_UB']<=ORIGINAL_UB and f['ORIGINAL_M1_LB']>=S2
    assert f['ORIGINAL_M1_LB']==(T if c['positive_certificate'] else S2)
    assert c['partial_valid_LB']!=0 and f['ORIGINAL_M1_LB']!=0
    assert abs(f['ORIGINAL_M1_IMPLIED_GAP']-(f['ORIGINAL_M1_UB']-f['ORIGINAL_M1_LB'])/f['ORIGINAL_M1_UB'])<1e-15

def test_original_UB_promotion_requires_full_original_validation_beyond_integrality_screen():
    a=read(OUT/'ORIGINAL_M1_PROMOTION_AUDIT.json')
    assert a['original_UB_requires_all_original_integrality_and_full_original_physical_grid_validation']
    for p in a['points']:
        if p['promotable_original_UB']:
            assert p['all_original_binary_integrality_screen'] and p['independent_full_original_validation']['valid_new_UB']

def test_preregistration_and_execution_checkpoint_frozen():
    f=read(OUT/'EXECUTION_FREEZE.json');m=read(OUT/'DIRECT_EXECUTION_MARKER.json')
    assert f['before_any_new_optimization'] and m['execution_freeze_sha256']==sha(OUT/'EXECUTION_FREEZE.json')
    assert m['preregistration_sha256']==sha(OUT/'PREREGISTRATION.json')==f['preregistration_sha256']
    from v42_voltage.preservation import assert_snapshot
    assert assert_snapshot(f['source_files'])
