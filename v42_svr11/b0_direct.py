"""B0 decision freeze directly to independently controlled Actual Fresh96."""
def _run_day(day,input_folder,output,*,scenario,source_SHA,progress=None,development=False,design_receipt=None):
    """New date computation; caller's frozen design/development authority is explicit."""
    from v42_voltage_control.authority import physical_permit
    require_sha(source_SHA);scenario,_,_=validate_scenario(scenario)
    require(day in tuple(f"2025-05-{d:02d}" for d in range(1,32)),"B0_NEW_MAY_DAY_REQUIRED")
    output=Path(output).resolve();require(not output.exists(),"B0_NEW_CAMPAIGN_OUTPUT_OVERWRITE_FORBIDDEN")
    output.mkdir(parents=True)
    plan=build_planning(day,input_folder,output/"PLANNING")
    options=dict(development=development,design_receipt=design_receipt)
    from v42_svr11.authority import active as svr11_epoch
    require(svr11_epoch() is not None, "B0_DIRECT_ACTUAL_SVR11_EPOCH_REQUIRED")
    from v42_svr11.initial_context import reference,independence as source_independence
    planning_audit=reference(output/"PLANNING",scenario,source_SHA,"B0",day)
    planning_ac=dict(status="NOT_EXECUTED",Planning_AC_executed=False,logical_Fresh_slots=0,
        reason="Official path proceeds from decision freeze directly to Actual")
    freeze=dict(schema=VERSION,day=day,arm="B0",Planning_frozen=True,Planning_physical_PASS=None,
        physical=plan["receipt"]["physical"],reference=plan["receipt"]["reference"],
        Planning_AC=planning_ac,Planning_hardware=planning_audit.receipt,
        Source_SHA=source_SHA,scenario_SHA=scenario["scenario_SHA"],MESS_PQ=0,
        Planning_Q_Tap_or_controller_state_is_not_Actual_input=True,old_results_reused=False)
    _write(output/"PLANNING_FREEZE.json",freeze)
    arrays,actual_sources,actual_generation=build_actual(plan,input_folder,output/"ACTUAL",output/"PLANNING_FREEZE.json")
    with physical_permit("B0",day,source_SHA,scenario,namespace="ACTUAL",**options):
        with scenario_scope(scenario,output/"ACTUAL/CAPCONTROL_SVR",source_SHA=source_SHA,arm="B0",day=day,namespace="ACTUAL") as actual_audit:
            actual_ac=fresh_environment(plan,arrays,input_folder,output/"ACTUAL/AC",namespace="ACTUAL",progress=progress)
    actual_pass=actual_ac["PASS"] and actual_audit.result["hardware_and_controller_PASS"]
    require(all(record(r["path"])==r for r in plan["sources"]+actual_sources),"B0_NEW_INPUT_SOURCE_MUTATED")
    independence=source_independence(planning_audit,actual_audit,source_SHA,scenario,"B0",day)
    planning_audit.engine.Basic.ClearAll()
    _write(output/"PLANNING_ACTUAL_CONTROL_INDEPENDENCE_AUDIT.json",independence)
    require(independence["PASS"],"B0_NEW_MEASURED_PLANNING_ACTUAL_CONTROL_INDEPENDENCE_FAILED")
    result=dict(schema=VERSION,day=day,arm="B0",PASS=bool(actual_pass),
        status="PASS" if actual_pass else "PHYSICAL_FAILED",Source_SHA=source_SHA,
        scenario_SHA=scenario["scenario_SHA"],new_Planning_and_Actual=True,previous_policy_result_reads=0,
        Planning=planning_ac,Actual=actual_ac,Planning_physical_PASS=None,Planning_AC_executed=False,Actual_physical_PASS=bool(actual_pass),
        Planning_hardware=planning_audit.receipt,Actual_hardware=actual_audit.receipt,
        planning_freeze=record(output/"PLANNING_FREEZE.json"),control_independence=record(output/"PLANNING_ACTUAL_CONTROL_INDEPENDENCE_AUDIT.json"),
        Native_Runtime=0,Native_optimizer_calls=0,CAPCONTROL_SVR_MILP_variables=0,MESS_PQ=0,Actual_plan_repair_calls=0)
    _write(output/"RESULT.json",result)
    return result


def run_day(*args,**kwargs):
    from v42_voltage_control import b0_new
    from v42_may_campaign_native90.a_routing import rebound
    return rebound(_run_day,dict(vars(b0_new)))(*args,**kwargs)
