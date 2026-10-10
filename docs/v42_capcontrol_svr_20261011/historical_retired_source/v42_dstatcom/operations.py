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
    design = verify_design(manifest['DSTATCOM_design'],request['source_SHA'])
    scenario = read(checked(design['scenario']))
    freeze_body,fresh_body = original.freeze_planning,original.fresh
    events = dict(Planning=None,Actual=None,independence=None,Planning_physical_PASS=False,Actual_hardware_PASS=False)
    options = dict(design_receipt=manifest['DSTATCOM_design'])

    def planning(current_request, accepted, mess, output):
        if current_request != request:
            raise PermissionError('DSTATCOM_PLANNING_EXACT_SOURCE_REQUEST_REQUIRED')
        output = Path(output)
        source_folder = output.parent/'SOURCE'
        input_folder = Path(request['input_folder'])
        ops = read(input_folder/'OPERATIONS.json')
        provenance = read(Path(ops['current_day_folder'])/'SOURCE_PROVENANCE.json')
        forecast_receipt = provenance['daily_sources']['aemo_forecast.json']
        if read(checked(forecast_receipt)) != ops['forecast_inputs']['AEMO']:
            raise PermissionError('DSTATCOM_PLANNING_FORECAST_AUTHORITY_DRIFT')
        with physical_permit(request['arm'],request['day'],request['source_SHA'],scenario,namespace='DAYAHEAD',**options):
            with scenario_scope(scenario,output/'DSTATCOM',source_SHA=request['source_SHA'],
                    arm=request['arm'],day=request['day'],namespace='DAYAHEAD') as audit:
                physical = run_fresh(request['day'],request['arm'],record(source_folder/'PLANNING_PHYSICAL.npz'),
                    record(source_folder/'PLANNING_MESS.npz'),forecast_receipt,output/'FORECAST_FRESH')
        events['Planning'] = audit
        events['Planning_physical_PASS'] = physical['PASS'] and audit.result['hardware_and_controller_PASS']
        result = freeze_body(current_request,accepted,mess,output)
        atomic(output/'DSTATCOM_PLANNING_CANDIDATE_AC.json',dict(
            schema='V42_DSTATCOM_INDEPENDENT_PLANNING_CANDIDATE_AC_V1',PASS=events['Planning_physical_PASS'],
            day=request['day'],arm=request['arm'],source_SHA=request['source_SHA'],scenario_SHA=scenario['scenario_SHA'],
            forecast_Fresh=record(output/'FORECAST_FRESH/FORECAST_FRESH_RESULT.json'),hardware=audit.receipt,
            Original_MILP_surrogate_voltage_limits=[.95,1.05],DSTATCOM_MILP_variables=0,
            Actual_private_sources_opened_before_Planning=False,Planning_frozen_after_Forecast_AC=True,
            physical_failure_preserved=True,Original_freeze=result))
        return result

    def actual(current_request, planning_folder, actual_folder, source_folder, output, progress=None):
        if current_request != request or events['Planning'] is None:
            raise PermissionError('DSTATCOM_ACTUAL_AFTER_INDEPENDENT_FORECAST_REQUIRED')
        with physical_permit(request['arm'],request['day'],request['source_SHA'],scenario,namespace='ACTUAL',**options):
            with scenario_scope(scenario,Path(output)/'DSTATCOM',source_SHA=request['source_SHA'],
                    arm=request['arm'],day=request['day'],namespace='ACTUAL') as audit:
                result = fresh_body(current_request,planning_folder,actual_folder,source_folder,output,progress)
        events['Actual'] = audit
        events['Actual_hardware_PASS'] = audit.result['hardware_and_controller_PASS']
        left,right = events['Planning'].result,audit.result
        # Measurements from the two compiles and first controller records,
        # rather than namespace declarations alone, establish independence.
        left_initial,right_initial = left['source_initial_controls'],right['source_initial_controls']
        q0 = all(q == 0 for item in audit.rows[0]['controller']['initial_Q_state_by_device'].values() for q in item)
        independent = (left['namespace']=='DAYAHEAD' and right['namespace']=='ACTUAL'
            and left_initial==right_initial and right_initial['taps']==[1.]*7
            and right_initial['capacitor_states']==[1,1,1,1] and q0
            and left['scenario_SHA']==right['scenario_SHA']==scenario['scenario_SHA']
            and left['execution_source_SHA']==right['execution_source_SHA']==request['source_SHA'])
        packet = dict(schema='V42_PLANNING_ACTUAL_CONTROL_INDEPENDENCE_V2',PASS=independent,
            day=request['day'],arm=request['arm'],source_SHA=request['source_SHA'],scenario_SHA=scenario['scenario_SHA'],
            Planning_hardware=events['Planning'].receipt,Actual_hardware=audit.receipt,
            Planning_source_initial_controls=left_initial,Actual_source_initial_controls=right_initial,
            Actual_first_Q_all_zero=q0,Planning_Q_Tap_or_controller_state_transferred=False,
            Actual_future_data_used_by_Planning=False,Actual_optimizer_calls=0)
        path=Path(output)/'PLANNING_ACTUAL_CONTROL_INDEPENDENCE_AUDIT.json'
        atomic(path,packet);events['independence']=record(path)
        if not independent:
            raise PermissionError('DSTATCOM_MEASURED_PLANNING_ACTUAL_STATE_INDEPENDENCE_FAILED')
        return result

    with patch.object(original,'freeze_planning',planning),patch.object(original,'fresh',actual):
        yield events
