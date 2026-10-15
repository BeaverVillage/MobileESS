"""Minimax switch/lateness, duplicates and pool-versus-route UB attribution."""
from copy import deepcopy
import pytest

from v42_integration.mess_minimax_lookahead import candidate_metrics,duplicate_groups,offline_outcome_scope


def fixture():
    rows=[dict(current_loading=v,slot=t,metadata=dict(asset=a,phase="A")) for v,t,a in [(1.,0,"L1"),(.95,8,"L2"),(.8,90,"L3")]]
    c=dict(unit="M",path_signature="a",MOVE_count=1,original_moves=[dict(depart=5,connect=10,destination="B")],
        signed_critical_impact=[-.02,.1,.4],charge_rebound_risk=[0.,.1,0.],Minimax_heuristic_score=1.2,
        lookahead=dict(terminal_recovery_shortfall=0.,charge_rebound=[0.,.1,.3]))
    return c,rows


def test_global_critical_switch_and_prearrival_peak_use_existing_signed_PQ_rebound():
    c,rows=fixture();r=candidate_metrics(c,rows)
    assert r["predicted_new_critical"]==dict(asset="L3",phase="A",slot=90)
    assert r["critical_asset_phase_slot_switch"] is True
    assert r["reconstructed_existing_signed_PQ_plus_rebound_peak"]==pytest.approx(1.2)
    assert r["existing_path_charge_rebound_max"]==.3
    assert r["near_critical_rows_before_destination_connect"]==1
    assert r["early_near_critical_peak_after_heuristic"]==pytest.approx(.98)
    assert r["predeparture_origin_PQ_redispatch_and_joint_vehicles_can_still_help"] is True
    assert r["lateness_is_not_a_hard_infeasibility_or_bound_proof"] is True


def test_misaligned_source_critical_vector_is_rejected():
    c,rows=fixture();c["signed_critical_impact"]=[0.]
    with pytest.raises(ValueError,match="CRITICAL_VECTOR_AXIS_REQUIRED"):candidate_metrics(c,rows)


def test_same_departure_destination_does_not_make_distinct_routes_equivalent():
    c,rows=fixture();a=candidate_metrics(c,rows);b=deepcopy(a);b["path_signature"]="b"
    r=duplicate_groups([a,a,b])
    assert r["unique_exact_unit_paths"]==2 and r["repeated_exact_path_occurrences"]==1
    assert r["distinct_unit_paths_per_coarse_group"][0]["unique_paths"]==2
    assert r["no_candidate_pruned_from_offline_duplicates"] is True


def test_joint_pool_UB_cannot_label_every_alternative_or_prove_score_improvement():
    r=offline_outcome_scope([dict(actual_joint_UB=.54),dict(actual_joint_UB=.54)])
    assert r["distinct_joint_FULL_UBs"]==1 and r["correlation"] is None
    assert r["score_to_FULL_UB_predictive_improvement"]=="NOT_CERTIFIED" and r["new_UB"] is None


def test_pinned_STAY_and_verified_selected_repetitions_are_separate_from_exploration_duplicates():
    c,rows=fixture();stay=candidate_metrics(c,rows);stay["MOVE_count"]=0
    move=deepcopy(stay);move["MOVE_count"]=1;move["path_signature"]="moving";move["actual_DIRECT_selected_lambda"]=1.
    r=duplicate_groups([stay,stay,move,move])
    assert r["protected_repeat_occurrences"]==2 and r["exploratory_repeat_occurrences"]==0
