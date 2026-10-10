"""Independent physical contexts around B3's original AST-cloned operations.

Only the two OriginalOperationsBridge operation entry points are wrapped. The
original SourceRegistry admission, source cloning, freeze/Actual arithmetic,
four planning stages and every other operation remain the source authority.
"""
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from v42_b3_joint.contracts import require, require_sha
from v42_pr134_b1.common import atomic, read, record
from .authority import checked, physical_permit, verify_design
from .integration import scenario_scope


def _new_b1_input(request, manifest):
    root = Path(request['campaign_root']).resolve()
    require(root == Path(request['root']).resolve(), 'DSTATCOM_B3_CURRENT_CAMPAIGN_ROOT_REQUIRED')
    origin = Path(manifest['origin_campaign_root']).resolve()
    require(origin == root or origin.is_relative_to(root), 'DSTATCOM_B3_OLD_B1_ORIGIN_FORBIDDEN')
    final_receipt = manifest['B1_results']['B1/'+request['day']]
    final_path = Path(checked(final_receipt)).resolve()
    require(final_path.is_relative_to(origin), 'DSTATCOM_B3_NEW_B1_RESULT_ROOT_REQUIRED')
    final = read(final_path)
    require(final.get('PASS') is True and final.get('status') == 'PASS'
        and final.get('source_SHA') == request['source_SHA']
        and final['identity']['arm'] == 'B1' and final['identity']['day'] == request['day'],
        'DSTATCOM_B3_NEW_SOURCE_B1_COMPLETION_REQUIRED')
    freezes = [r for r in final['files'] if Path(r['path']).name == 'A_NATIVE_SOURCE_FREEZE.json']
    require(len(freezes) == 1, 'DSTATCOM_B3_NEW_B1_SOURCE_FREEZE_REQUIRED')
    freeze_path = Path(checked(freezes[0])).resolve()
    require(freeze_path.is_relative_to(origin), 'DSTATCOM_B3_NEW_B1_FREEZE_ROOT_REQUIRED')
    freeze = read(freeze_path)
    require(freeze.get('PASS') is True and freeze.get('day') == request['day'] and freeze.get('arm') == 'B1',
            'DSTATCOM_B3_NEW_B1_FREEZE_IDENTITY_REQUIRED')
    inputs = freeze['inputs']
    folder = Path(checked(inputs['NATIVE_INPUT.json'])).resolve().parent
    require(folder.is_relative_to(root) and Path(checked(inputs['WINDOWS.json'])).resolve() == folder/'WINDOWS.json',
            'DSTATCOM_B3_NEW_B1_INPUT_SOURCE_ROOT_REQUIRED')
    if request.get('input_folder'):
        require(Path(request['input_folder']).resolve() == folder, 'DSTATCOM_B3_OUTER_INPUT_FOLDER_DRIFT')
    return folder, [final_receipt,freezes[0],inputs['NATIVE_INPUT.json'],inputs['WINDOWS.json']]


def _independence(planning, actual, source_SHA, scenario_SHA, *, arm, day):
    left, right = planning.result, actual.result
    li, ri = left['source_initial_controls'], right['source_initial_controls']
    q = actual.rows[0]['controller']['initial_Q_state_by_device'] if actual.rows else {}
    devices = {spec.device_id:len(spec.phases) for spec in actual.specs}
    q0 = bool(devices) and set(q)==set(devices) and all(
        len(q[key])==phases and all(value==0 for value in q[key]) for key,phases in devices.items())
    distinct = bool(planning.sessions) and bool(actual.sessions) and set(planning.sessions).isdisjoint(actual.sessions)
    passed = (left['namespace']=='DAYAHEAD' and right['namespace']=='ACTUAL' and li==ri
        and ri['taps']==[1.]*7 and ri['capacitor_states']==[1,1,1,1]
        and li['regulator_enabled']==ri['regulator_enabled']==[True]*7
        and li['configured_MaxControlIterations']==ri['configured_MaxControlIterations']==100
        and li['configured_MaxIterations']==ri['configured_MaxIterations']==15
        and q0 and distinct and left['scenario_SHA']==right['scenario_SHA']==scenario_SHA
        and left['execution_source_SHA']==right['execution_source_SHA']==source_SHA)
    return dict(schema='V42_PLANNING_ACTUAL_CONTROL_INDEPENDENCE_V2',PASS=bool(passed),
        arm=arm,day=day,source_SHA=source_SHA,scenario_SHA=scenario_SHA,
        Planning_hardware=planning.receipt,Actual_hardware=actual.receipt,
        Planning_source_initial_controls=li,Actual_source_initial_controls=ri,
        Actual_first_Q_all_zero=q0,Planning_and_Actual_engine_objects_distinct=distinct,
        Actual_first_Q_device_axis_complete=set(q)==set(devices),Actual_first_Q_device_count=len(q),
        Planning_Q_Tap_or_controller_state_transferred=False,Actual_future_data_used_by_Planning=False,
        Actual_optimizer_calls=0)


@contextmanager
def independent_scopes(request, manifest):
    """Require new same-epoch B1 and wrap only B3 final freeze and Actual Fresh."""
    from v42_b3_joint.operations_bridge import SourceOperationsBridge
    from v42_autonomous_b3.admission import scientific_run_id
    from v42_may_campaign_native90.preflight import native_zero
    from .forecast import run_fresh
    require(request['arm']=='B3', 'DSTATCOM_B3_POLICY_REQUIRED')
    require_sha(request['source_SHA'])
    require(manifest['execution_SHA']==request['source_SHA'] and manifest['run_id']==request['run_id'],
            'DSTATCOM_B3_OUTER_MANIFEST_SOURCE_IDENTITY_DRIFT')
    design = verify_design(manifest['DSTATCOM_design'], request['source_SHA'])
    scenario = read(checked(design['scenario']))
    folder, protected = _new_b1_input(request, manifest)
    stage_root = Path(request['output']).resolve()/'PIPELINE/M2'
    run_id = scientific_run_id(request)
    operation = SourceOperationsBridge._operation
    events = dict(Planning=None,Actual=None,independence=None,Planning_physical_PASS=False,Actual_hardware_PASS=False)
    options = dict(design_receipt=manifest['DSTATCOM_design'])

    def admit(bridge, current_request):
        context = bridge.context
        require(context.request.stage=='M2' and context.request.authority.day==request['day']
            and Path(context.input_folder).resolve()==folder and Path(context.output).resolve()==stage_root
            and context.run_id==run_id and current_request==bridge._request()
            and context.source_registry.evidence_kind=='SOURCE',
            'DSTATCOM_B3_EXACT_FINAL_SOURCE_CONTEXT_REQUIRED')
        require(all(record(r['path'])==r for r in protected), 'DSTATCOM_B3_NEW_B1_SOURCE_MUTATED')

    def routed(bridge, symbol, **routing):
        # SourceRegistry still compiles and admits the original disk AST first.
        original = operation(bridge, symbol, **routing)
        if symbol == 'freeze_planning':
            def planning(current_request, accepted, mess, output):
                admit(bridge, current_request)
                require(events['Planning'] is None, 'DSTATCOM_B3_FORECAST_REEXECUTION_FORBIDDEN')
                output = Path(output)
                require(output.resolve()==stage_root/'OPERATIONS/PLANNING','DSTATCOM_B3_FREEZE_OUTPUT_DRIFT')
                ops = read(folder/'OPERATIONS.json')
                provenance = read(Path(ops['current_day_folder'])/'SOURCE_PROVENANCE.json')
                forecast = provenance['daily_sources']['aemo_forecast.json']
                require(read(checked(forecast))==ops['forecast_inputs']['AEMO'],'DSTATCOM_B3_FORECAST_AUTHORITY_DRIFT')
                with physical_permit('B3',request['day'],request['source_SHA'],scenario,namespace='DAYAHEAD',**options):
                    with scenario_scope(scenario,output/'DSTATCOM',source_SHA=request['source_SHA'],arm='B3',day=request['day'],namespace='DAYAHEAD') as audit:
                        with native_zero() as attempts:
                            physical=run_fresh(request['day'],'B3',record(output.parent/'SOURCE/PLANNING_PHYSICAL.npz'),
                                record(output.parent/'SOURCE/PLANNING_MESS.npz'),forecast,output/'FORECAST_FRESH')
                        require(not attempts,'DSTATCOM_B3_FORECAST_OPTIMIZER_FORBIDDEN')
                events['Planning']=audit
                events['Planning_physical_PASS']=physical['PASS'] and audit.result['hardware_and_controller_PASS']
                result=original(current_request,accepted,mess,output)
                atomic(output/'DSTATCOM_PLANNING_CANDIDATE_AC.json',dict(schema='V42_DSTATCOM_B3_FORECAST_CANDIDATE_AC_V1',
                    PASS=events['Planning_physical_PASS'],day=request['day'],arm='B3',source_SHA=request['source_SHA'],
                    scenario_SHA=scenario['scenario_SHA'],forecast_Fresh=record(output/'FORECAST_FRESH/FORECAST_FRESH_RESULT.json'),
                    hardware=audit.receipt,Planning_frozen_after_Forecast_AC=True,Actual_private_sources_opened_before_Planning=False,
                    Original_MILP_surrogate_voltage_limits=[.95,1.05],DSTATCOM_MILP_variables=0,Original_freeze=result))
                return result
            return planning
        if symbol == 'fresh':
            def actual(current_request, planning_folder, actual_folder, source_folder, output, progress=None):
                admit(bridge,current_request)
                require(events['Planning'] is not None and events['Actual'] is None,'DSTATCOM_B3_ACTUAL_AFTER_NEW_FORECAST_REQUIRED')
                output=Path(output)
                require(output.resolve()==stage_root/'OPERATIONS/FRESH','DSTATCOM_B3_FRESH_OUTPUT_DRIFT')
                with physical_permit('B3',request['day'],request['source_SHA'],scenario,namespace='ACTUAL',**options):
                    with scenario_scope(scenario,output/'DSTATCOM',source_SHA=request['source_SHA'],arm='B3',day=request['day'],namespace='ACTUAL') as audit:
                        with native_zero() as attempts:
                            result=original(current_request,planning_folder,actual_folder,source_folder,output,progress)
                        require(not attempts,'DSTATCOM_B3_ACTUAL_OPTIMIZER_FORBIDDEN')
                events['Actual']=audit;events['Actual_hardware_PASS']=audit.result['hardware_and_controller_PASS']
                packet=_independence(events['Planning'],audit,request['source_SHA'],scenario['scenario_SHA'],arm='B3',day=request['day'])
                path=output/'PLANNING_ACTUAL_CONTROL_INDEPENDENCE_AUDIT.json';atomic(path,packet);events['independence']=record(path)
                require(packet['PASS'],'DSTATCOM_B3_MEASURED_CONTROL_INDEPENDENCE_FAILED')
                return result
            return actual
        return original

    with patch.object(SourceOperationsBridge,'_operation',routed):
        yield events
    require(SourceOperationsBridge._operation is operation,'DSTATCOM_B3_OPERATION_HOOK_RESTORATION_FAILED')
