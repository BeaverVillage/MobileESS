"""Source-initial control isolation proof without a DayAhead AC replay."""
from pathlib import Path
from types import SimpleNamespace
from v42_pr134_b1.common import atomic,read,record

def reference(output,scenario,source,arm,day):
    from v42_regcontrol import authority
    from v42_voltage_control.timecontrol import CommonClock,queue,seconds
    from v42_voltage_control.svr import install
    from v42_voltage_control.integration import assert_control_inventory
    engine,adapter,original=authority.compile_verified()
    authority.assert_inventory(original,initial=True)
    clock=CommonClock('DAYAHEAD',day);clock.bind(engine)
    bank=install(engine,scenario['svr'])
    initial=authority.source()['inventory'](engine)
    assert_control_inventory(initial,scenario,initial=True)
    if queue(engine) or seconds(engine)!=0:raise PermissionError('SVR11_REFERENCE_NOT_SOURCE_INITIAL')
    result=dict(namespace='DAYAHEAD',execution_source_SHA=source,scenario_SHA=scenario['scenario_SHA'],
        source_initial_controls=original,initial_controls=initial,
        engine_context_identity=dict(engine_object_id=id(engine),solution_object_id=id(engine.Solution)),
        DSTATCOM_object_count=0,Planning_AC_executed=False,Planning_AC_status='NOT_EXECUTED',
        reference_compile_only=True,physical_slots=0,Native_calls=0,initial_queue=[],initial_seconds=0,
        original_RegControl_count=7,SVR_bank_count=11,Planning_tap_or_queue_transfer=False)
    path=Path(output)/'SOURCE_INITIAL_CONTROL_REFERENCE.json';atomic(path,result)
    # Retain the reference context until Actual ends; object IDs cannot recycle.
    return SimpleNamespace(result=result,receipt=record(path),engine=engine,clock=clock,bank=bank)

def independence(reference,actual,source,scenario,arm,day):
    from v42_voltage_control.isolation import measured_independence
    proof=measured_independence(reference,actual,source,scenario['scenario_SHA'],arm=arm,day=day)
    proof.update(schema='SVR11_SOURCE_INITIAL_ACTUAL_ISOLATION_V2',
        Planning_AC_executed=False,Planning_AC_status='NOT_EXECUTED',
        reference_scope='Separate source-initial context; no Forecast trajectory or tap history replay',
        reference_compile_only=True,reference_physical_slots=0,
        Actual_source_initial_clock_seconds=0,Actual_source_initial_queue=[],
        Planning_tap_queue_state_or_history_transferred=False)
    return proof
