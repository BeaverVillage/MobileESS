import json
from v42_may12_rescue.postrun import attempt_walls,eligible_bound,native_call_counts


def test_completed_optimize_calls_with_zero_rounded_runtime_are_counted():
    assert native_call_counts([dict(native_seconds=0,Work=.01),dict(native_seconds=.003)])==dict(total=2,positive_runtime=1,zero_runtime=1)


def test_attempt_walls_include_implementation_boundary_without_recounting_native(tmp_path):
    for name,w,n in [('PRE_NATIVE_START_GATE_FAILURE1',10,0),('PRE_IMPLEMENTATION_BOUNDARY1',20,32),('PRE_PRICING_START_GATE_FAILURE6',30,35)]:
        f=tmp_path/name;f.mkdir();(f/'FINAL_DECISION.json').write_text(json.dumps(dict(new_wall_seconds=w,new_native_seconds=n)))
    (tmp_path/'LAST_NATIVE_RUN_DECISION.json').write_text(json.dumps(dict(new_wall_seconds=40,new_native_seconds=35)))
    (tmp_path/'FINAL_DECISION.json').write_text(json.dumps(dict(new_wall_seconds=999,new_native_seconds=35)))
    rows,total=attempt_walls(tmp_path)
    assert len(rows)==4 and total==100


def valid():
    return dict(PASS=True,complete_native_producer_verified=True,complete_STAY_and_migration_coverage=True,
        full_mixed_fractional_direction_coverage=True,classes=130,
        block_certificates=[dict(class_id=str(i)) for i in range(130)],
        full_domain_phase1_lower_bound='1/2',active_objective_upper='2/3',no_negative_omitted_block_certified=False)


def test_valid_bound_does_not_require_pricing_closure():
    assert eligible_bound(valid())


def test_partial_duplicate_and_contradictory_bounds_rejected():
    v=valid();v['classes']=129;assert not eligible_bound(v)
    v=valid();v['block_certificates'][-1]=v['block_certificates'][0];assert not eligible_bound(v)
    v=valid();v['full_domain_phase1_lower_bound']='3/4';assert not eligible_bound(v)
    v=valid();v['complete_STAY_and_migration_coverage']=False;assert not eligible_bound(v)
