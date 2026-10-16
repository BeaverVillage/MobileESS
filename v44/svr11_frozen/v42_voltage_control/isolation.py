"""Measured independence of Forecast and Actual capacitor/regulator contexts."""
from .authority import checked
from v42_pr134_b1.common import read


def measured_independence(planning, actual, source_SHA, scenario_SHA, *, arm, day):
    left, right = planning.result, actual.result
    a, b = left.get('initial_controls'), right.get('initial_controls')
    if a is None:
        a = left.get('source_initial_controls')
    if b is None:
        b = right.get('source_initial_controls')
    # The integration observer records these identifiers while retaining both
    # engine objects, so object identity cannot be recycled between scopes.
    li, ri = left.get('engine_context_identity'), right.get('engine_context_identity')
    source_initial = left.get('source_initial_controls') == right.get('source_initial_controls')
    fresh_initial = a is not None and a == b
    separate = li is not None and ri is not None and li != ri
    passed = (left.get('namespace') == 'DAYAHEAD' and right.get('namespace') == 'ACTUAL'
        and left.get('execution_source_SHA') == right.get('execution_source_SHA') == source_SHA
        and left.get('scenario_SHA') == right.get('scenario_SHA') == scenario_SHA
        and source_initial and fresh_initial and separate
        and left.get('DSTATCOM_object_count') == right.get('DSTATCOM_object_count') == 0)
    return dict(schema='V42_CAPCONTROL_SVR_PLANNING_ACTUAL_CONTROL_ISOLATION_V1',
        PASS=passed, arm=arm, day=day, source_SHA=source_SHA, scenario_SHA=scenario_SHA,
        Planning_initial_controls=a, Actual_initial_controls=b,
        original_source_initial_controls_equal=source_initial,
        complete_new_device_source_initial_states_equal=fresh_initial,
        Planning_and_Actual_engine_objects_distinct=separate,
        Planning_engine_context_identity=li, Actual_engine_context_identity=ri,
        Planning_hardware=planning.receipt, Actual_hardware=actual.receipt,
        Planning_Tap_Cap_queue_or_controller_state_transferred=False,
        Actual_future_data_used_by_Planning=False, Actual_optimizer_calls=0,
        CapControl_or_SVR_MILP_variables=0)
