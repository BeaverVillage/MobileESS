"""Independent Forecast and Actual controller scopes for Original Operations.

The original accepted materializer, decision freeze, Actual body and Fresh
backend are executed. A Forecast-only physical check precedes the decision
freeze. Actual receives a fresh Source Initial State and a new controller.
"""
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from v42_pr134_b1.common import atomic, read, record
from .authority import checked, physical_permit, verify_design
from .integration import scenario_scope


@contextmanager
def independent_scopes(request, manifest):
    from v42_may_campaign_native90 import operations as original
    from .forecast import run_fresh
    design = verify_design(manifest['CAPCONTROL_SVR_design'],request['source_SHA'])
    scenario = read(checked(design['scenario']))
    freeze_body,fresh_body = original.freeze_planning,original.fresh
    events = dict(Planning=None,Actual=None,independence=None,Planning_physical_PASS=False,Actual_hardware_PASS=False)
    options = dict(design_receipt=manifest['CAPCONTROL_SVR_design'])

    def planning(current_request, accepted, mess, output):
        if current_request != request:
            raise PermissionError('CAPCONTROL_SVR_PLANNING_EXACT_SOURCE_REQUEST_REQUIRED')
        output = Path(output)
        source_folder = output.parent/'SOURCE'
        input_folder = Path(request['input_folder'])
        ops = read(input_folder/'OPERATIONS.json')
        provenance = read(Path(ops['current_day_folder'])/'SOURCE_PROVENANCE.json')
        forecast_receipt = provenance['daily_sources']['aemo_forecast.json']
        if read(checked(forecast_receipt)) != ops['forecast_inputs']['AEMO']:
            raise PermissionError('CAPCONTROL_SVR_PLANNING_FORECAST_AUTHORITY_DRIFT')
        with physical_permit(request['arm'],request['day'],request['source_SHA'],scenario,namespace='DAYAHEAD',**options):
            with scenario_scope(scenario,output/'CAPCONTROL_SVR',source_SHA=request['source_SHA'],
                    arm=request['arm'],day=request['day'],namespace='DAYAHEAD') as audit:
                physical = run_fresh(request['day'],request['arm'],record(source_folder/'PLANNING_PHYSICAL.npz'),
                    record(source_folder/'PLANNING_MESS.npz'),forecast_receipt,output/'FORECAST_FRESH')
        events['Planning'] = audit
        events['Planning_physical_PASS'] = physical['PASS'] and audit.result['hardware_and_controller_PASS']
        result = freeze_body(current_request,accepted,mess,output)
        atomic(output/'CAPCONTROL_SVR_PLANNING_CANDIDATE_AC.json',dict(
            schema='V42_CAPCONTROL_SVR_INDEPENDENT_PLANNING_CANDIDATE_AC_V1',PASS=events['Planning_physical_PASS'],
            day=request['day'],arm=request['arm'],source_SHA=request['source_SHA'],scenario_SHA=scenario['scenario_SHA'],
            forecast_Fresh=record(output/'FORECAST_FRESH/FORECAST_FRESH_RESULT.json'),hardware=audit.receipt,
            Original_MILP_surrogate_voltage_limits=[.95,1.05],CAPCONTROL_SVR_MILP_variables=0,
            Actual_private_sources_opened_before_Planning=False,Planning_frozen_after_Forecast_AC=True,
            physical_failure_preserved=True,Original_freeze=result))
        return result

    def actual(current_request, planning_folder, actual_folder, source_folder, output, progress=None):
        if current_request != request or events['Planning'] is None:
            raise PermissionError('CAPCONTROL_SVR_ACTUAL_AFTER_INDEPENDENT_FORECAST_REQUIRED')
        with physical_permit(request['arm'],request['day'],request['source_SHA'],scenario,namespace='ACTUAL',**options):
            with scenario_scope(scenario,Path(output)/'CAPCONTROL_SVR',source_SHA=request['source_SHA'],
                    arm=request['arm'],day=request['day'],namespace='ACTUAL') as audit:
                result = fresh_body(current_request,planning_folder,actual_folder,source_folder,output,progress)
        events['Actual'] = audit
        events['Actual_hardware_PASS'] = audit.result['hardware_and_controller_PASS']
        from .isolation import measured_independence
        packet = measured_independence(events['Planning'],audit,request['source_SHA'],
            scenario['scenario_SHA'],arm=request['arm'],day=request['day'])
        independent = packet['PASS']
        path=Path(output)/'PLANNING_ACTUAL_CONTROL_INDEPENDENCE_AUDIT.json'
        atomic(path,packet);events['independence']=record(path)
        if not independent:
            raise PermissionError('CAPCONTROL_SVR_MEASURED_PLANNING_ACTUAL_STATE_INDEPENDENCE_FAILED')
        return result

    with patch.object(original,'freeze_planning',planning),patch.object(original,'fresh',actual):
        yield events
