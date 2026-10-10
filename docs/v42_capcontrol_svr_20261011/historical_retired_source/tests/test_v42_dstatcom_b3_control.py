"""Clone entry routing and new-epoch admission fixtures; no Native/DSS execution."""
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import json

import pytest

from v42_dstatcom import b3_control as subject
from v42_pr134_b1.common import record


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value),encoding='utf8')
    return record(path)


def audit(namespace,source='a'*64,scenario='b'*64,*,engine_key=None,q=0.,tap=1.):
    controls=dict(taps=[tap]*7,capacitor_states=[1]*4,regulator_enabled=[True]*7,
        configured_MaxControlIterations=100,configured_MaxIterations=15)
    return SimpleNamespace(result=dict(namespace=namespace,source_initial_controls=controls,
        scenario_SHA=scenario,execution_source_SHA=source,hardware_and_controller_PASS=True),
        rows=[dict(controller=dict(initial_Q_state_by_device={'STA08_MESS':[q,q,q]}))],
        sessions={engine_key if engine_key is not None else namespace:object()},receipt={},
        specs=(SimpleNamespace(device_id='STA08_MESS',phases=(1,2,3)),))


@pytest.fixture
def fixture(tmp_path):
    root=tmp_path/'new_campaign';folder=root/'inputs/B1/2025-05-28'
    inputs={name:write(folder/name,{}) for name in ['NATIVE_INPUT.json','WINDOWS.json']}
    a_freeze=write(root/'dates/B1/2025-05-28/output/A_NATIVE_SOURCE_FREEZE.json',
        dict(PASS=True,arm='B1',day='2025-05-28',inputs=inputs))
    final=write(root/'dates/B1/2025-05-28/RESULT.json',dict(PASS=True,status='PASS',source_SHA='a'*64,
        identity=dict(arm='B1',day='2025-05-28'),files=[a_freeze]))
    forecast=write(root/'raw/forecast.json',dict(forecast_only=True))
    write(root/'raw/SOURCE_PROVENANCE.json',dict(daily_sources={'aemo_forecast.json':forecast}))
    write(folder/'OPERATIONS.json',dict(current_day_folder=str(root/'raw'),forecast_inputs=dict(AEMO=dict(forecast_only=True))))
    scenario=dict(scenario_SHA='b'*64);scenario_receipt=write(root/'scenario.json',scenario)
    request=dict(arm='B3',day='2025-05-28',source_SHA='a'*64,run_id='fixture',
        root=str(root),campaign_root=str(root),output=str(root/'envelope'),input_folder=str(folder))
    manifest=dict(execution_SHA='a'*64,run_id='fixture',origin_campaign_root=str(root),
        B1_results={'B1/2025-05-28':final},DSTATCOM_design={})
    stage=Path(request['output'])/'PIPELINE/M2';out=stage/'OPERATIONS'
    for name in ['PLANNING','ACTUAL','SOURCE','ACTUAL_SOURCE','FRESH']:(out/name).mkdir(parents=True)
    for name in ['PLANNING_PHYSICAL.npz','PLANNING_MESS.npz']:(out/'SOURCE'/name).write_bytes(b'new candidate fixture')
    calls=[]
    class Bridge:
        def __init__(self):
            self.context=SimpleNamespace(request=SimpleNamespace(stage='M2',authority=SimpleNamespace(day=request['day'])),
                input_folder=folder,output=stage,run_id='fixture',source_registry=SimpleNamespace(evidence_kind='SOURCE'))
        def _request(self):return dict(run_id='fixture',day=request['day'],arm='B3',input_folder=str(folder),output=str(stage))
        def _operation(self,symbol,**routing):
            calls.append(('clone',symbol,routing))
            def cloned_freeze(current,accepted,mess,output):calls.append(('freeze',));return {'original_freeze':True}
            def cloned_fresh(current,planning,actual,source,output,progress=None):calls.append(('fresh',));return {'original_fresh':True}
            return {'freeze_planning':cloned_freeze,'fresh':cloned_fresh}.get(symbol,lambda *a:('original',symbol))
    @contextmanager
    def scenario_scope(scenario,output,*,source_SHA,arm,day,namespace):
        instance=audit(namespace,source_SHA,scenario['scenario_SHA'])
        instance.receipt=write(Path(output)/'audit.json',{'namespace':namespace})
        yield instance
    @contextmanager
    def permit(*args,**kwargs):yield
    @contextmanager
    def native_zero():yield []
    def fresh(day,arm,physical,mess,forecast,output,progress=None):
        calls.append(('forecast',));write(Path(output)/'FORECAST_FRESH_RESULT.json',dict(PASS=True))
        return dict(PASS=True)
    from v42_b3_joint import operations_bridge
    from v42_dstatcom import forecast as forecast_module
    from v42_may_campaign_native90 import preflight
    patches=[patch.object(operations_bridge,'SourceOperationsBridge',Bridge),
        patch.object(subject,'verify_design',return_value=dict(scenario=scenario_receipt)),
        patch.object(subject,'scenario_scope',scenario_scope),patch.object(subject,'physical_permit',permit),
        patch.object(forecast_module,'run_fresh',fresh),patch.object(preflight,'native_zero',native_zero)]
    for p in patches:p.start()
    try:yield SimpleNamespace(root=root,folder=folder,request=request,manifest=manifest,Bridge=Bridge,out=out,calls=calls)
    finally:
        for p in reversed(patches):p.stop()


def test_wraps_original_cloned_entries_only_and_restores_class(fixture):
    f=fixture;old=f.Bridge._operation
    # Changing the original module callable cannot affect a disk-AST clone.
    from v42_may_campaign_native90 import operations
    with patch.object(operations,'freeze_planning',side_effect=AssertionError('Must call clone')):
        with subject.independent_scopes(f.request,f.manifest) as events:
            bridge=f.Bridge();r=bridge._request()
            assert bridge._operation('other')()==('original','other')
            assert bridge._operation('freeze_planning')(r,{}, {},f.out/'PLANNING')=={'original_freeze':True}
            assert bridge._operation('fresh')(r,f.out/'PLANNING',f.out/'ACTUAL',f.out/'ACTUAL_SOURCE',f.out/'FRESH')=={'original_fresh':True}
            assert events['Planning_physical_PASS'] and events['Actual_hardware_PASS']
            packet=json.loads(Path(events['independence']['path']).read_text())
            assert packet['PASS'] and packet['Actual_first_Q_all_zero']
            assert packet['Planning_and_Actual_engine_objects_distinct']
    assert f.Bridge._operation is old
    assert [item[0] for item in f.calls if item[0]!='clone']==['forecast','freeze','fresh']


def test_actual_cannot_run_without_own_new_forecast_and_exception_restores_hook(fixture):
    f=fixture;old=f.Bridge._operation
    with pytest.raises(ValueError,match='ACTUAL_AFTER_NEW_FORECAST_REQUIRED'):
        with subject.independent_scopes(f.request,f.manifest):
            b=f.Bridge();b._operation('fresh')(b._request(),None,None,None,f.out/'FRESH')
    assert f.Bridge._operation is old
    assert not any(item[0]=='fresh' for item in f.calls)


def test_different_stage_or_changed_new_input_rejected_before_forecast(fixture):
    f=fixture
    with subject.independent_scopes(f.request,f.manifest):
        b=f.Bridge();b.context.request.stage='M1'
        with pytest.raises(ValueError,match='EXACT_FINAL_SOURCE_CONTEXT_REQUIRED'):
            b._operation('freeze_planning')(b._request(),{}, {},f.out/'PLANNING')
        b.context.request.stage='M2';(f.folder/'NATIVE_INPUT.json').write_text('changed')
        with pytest.raises(ValueError,match='NEW_B1_SOURCE_MUTATED'):
            b._operation('freeze_planning')(b._request(),{}, {},f.out/'PLANNING')
    assert not any(item[0]=='forecast' for item in f.calls)


def test_old_b1_origin_and_wrong_source_completion_never_admitted(fixture):
    f=fixture;m=deepcopy(f.manifest);m['origin_campaign_root']=str(f.root.parent/'old_campaign')
    with pytest.raises(ValueError,match='OLD_B1_ORIGIN_FORBIDDEN'):
        with subject.independent_scopes(f.request,m):pass
    final=Path(f.manifest['B1_results']['B1/2025-05-28']['path']);v=json.loads(final.read_text());v['source_SHA']='c'*64
    f.manifest['B1_results']['B1/2025-05-28']=write(final,v)
    with pytest.raises(ValueError,match='NEW_SOURCE_B1_COMPLETION_REQUIRED'):
        with subject.independent_scopes(f.request,f.manifest):pass
    assert not f.calls


@pytest.mark.parametrize('defect',['nonzero_initial_q','same_engine','tap_transfer','source_drift','missing_phase_axis'])
def test_measured_independence_cannot_be_declared_from_namespaces_alone(defect):
    planning,actual=audit('DAYAHEAD'),audit('ACTUAL')
    if defect=='nonzero_initial_q':actual.rows[0]['controller']['initial_Q_state_by_device']['STA08_MESS'][0]=1.
    if defect=='same_engine':actual.sessions=planning.sessions
    if defect=='tap_transfer':actual.result['source_initial_controls']['taps'][0]=1.025
    if defect=='source_drift':actual.result['execution_source_SHA']='c'*64
    if defect=='missing_phase_axis':actual.rows[0]['controller']['initial_Q_state_by_device']['STA08_MESS']=[]
    assert not subject._independence(planning,actual,'a'*64,'b'*64,arm='B0',day='2025-05-01')['PASS']
