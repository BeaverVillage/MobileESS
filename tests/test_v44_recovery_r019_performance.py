import inspect
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from v44_recovery_r019.current_ac_performance import ordinal_reader,require_policy,_actual_request


def properties(engine,name):
    if not engine.Circuit.SetActiveElement(name):raise ValueError('MISSING')
    return {p:str(engine.Properties.Value(p)) for p in engine.CktElement.AllPropertyNames()}


def fake(values):
    class P:
        def __init__(self):self.calls=[]
        def Value(self,*args):
            assert len(args)==1
            key=args[0];self.calls.append(key)
            if isinstance(key,int):key=list(values)[key-1]
            return values[key]
    return SimpleNamespace(Circuit=SimpleNamespace(SetActiveElement=lambda x:True),
        Properties=P(),CktElement=SimpleNamespace(AllPropertyNames=lambda:list(values)))


@pytest.mark.parametrize('values',[{'A':'1','B':'2'},{'TapNum':'-7','Reset':'No','Vreg':'120'},
    {'winding':'2','Tap':'1.00625','NormAmps':'400','Enabled':'Yes'}])
def test_every_live_value_exact_without_name_lookup(values):
    old=fake(values);new=fake(values);f=ordinal_reader(properties,1)
    assert properties(old,'X')==f(new,'X')==values
    assert old.Properties.calls==list(values)
    assert new.Properties.calls==list(range(1,len(values)+1))
    values[next(iter(values))]='CHANGED'
    assert f(new,'X')==properties(old,'X')==values
    assert len(new.Properties.calls)==2*len(values)


def test_schema_order_is_taken_from_live_element_every_call():
    values={'A':'1','B':'2'};e=fake(values);f=ordinal_reader(properties,1)
    assert f(e,'X')==values
    values.clear();values.update(B='3',C='4')
    assert f(e,'X')==values


def test_shape_drift_denied():
    with pytest.raises(ValueError,match='SOURCE_SHAPE'):ordinal_reader(properties,2)


def test_inspect_generated_source_for_later_adapters():
    assert 'enumerate' in inspect.getsource(ordinal_reader(properties,1))


def test_unleased_production_denied():
    with pytest.raises(RuntimeError,match='LIVE_CASE_LEASE'):require_policy(SimpleNamespace(arm='B1'))


@pytest.mark.parametrize('day,arm,attempt,allowed',[
 ('2025-05-01','B1','attempt002',False),('2025-05-02','B1','attempt001',True),
 ('2025-05-01','B3','attempt002',True),('2025-05-02','B0','attempt001',True)])
def test_only_authorized_subsequent_cases(day,arm,attempt,allowed):
    request=dict(day=day,arm=arm,stage='ACTUAL',source_sha='case-sha',case_root=f'D:/{day}/{arm}/{attempt}',execution_permit=dict(path='permit'))
    overlay=dict(policy='V44_AUTONOMOUS_RECOVERY_R019',
        Current_AC_performance='EXACT_PREFIX_HISTORY_AUDIT_REUSE_WITH_LIVE_BOUNDARIES_AND_IMMUTABLE_PHYSICS',
        Historical_audit_guard='FIRST_AND_FINAL_FULL_LIVE_CONTROLS_RATINGS_AND_EXACT_NATIVE_STAMP')
    with patch('v44.execution.assert_current',return_value=dict(request={k:v for k,v in request.items() if k!='stage'})),patch('v44.common.read',return_value=dict(autonomous_recovery_overlay=overlay)),patch('v44_recovery_r019.current_ac_performance._actual_request') as stage:
        stage.get.return_value=request
        if day=='2025-05-01' and arm=='B1':
            with pytest.raises(PermissionError,match='PROTECTED'):require_policy(SimpleNamespace(arm=arm))
        else:assert require_policy(SimpleNamespace(arm=arm)) is allowed


def test_case_lease_alone_cannot_enable_performance_outside_actual():
    request=dict(day='2025-05-02',arm='B1',case_root='case')
    with patch('v44.execution.assert_current',return_value=dict(request=request)):
        with pytest.raises(PermissionError,match='EXACT_ACTUAL_STAGE'):require_policy(SimpleNamespace(arm='B1'))


def test_actual_wrapper_binds_stage_request_and_restores_after_exception():
    from v44_recovery_r019.current_ac_performance import install
    from v44 import worker
    request=dict(stage='ACTUAL')
    def original(r,*args):
        assert _actual_request.get() is request
        raise ValueError('SENTINEL')
    with patch.object(worker,'actual',original):
        with install():
            with pytest.raises(ValueError,match='SENTINEL'):worker.actual(request,None,None)
        assert worker.actual is original
    assert _actual_request.get() is None


def test_independent_fresh_uses_separate_pure_live_scope():
    from v44_recovery_r019.current_ac_performance import install
    from v44.svr12 import SVR12CurrentAC
    sentinel=object()
    with patch.object(SVR12CurrentAC,'_probe',return_value=sentinel) as original,patch('v44_recovery_r019.current_ac_performance.require_policy',return_value=True),patch('v44_recovery_r019.current_ac_performance.live_read_scope') as scope,patch('v44_recovery_r019.fresh_performance.live_fresh_scope') as fresh_scope:
        with install():
            assert SVR12CurrentAC._probe(SimpleNamespace(_independent_fresh=True),[]) is sentinel
        scope.assert_not_called();fresh_scope.assert_called_once();original.assert_called_once()


@pytest.mark.parametrize('fail',[False,True])
def test_direct_live_getters_free_owned_strings_even_on_error(fail):
    from v44_recovery_r019.current_ac_performance import live_properties
    values={'TapNum':'1','Reset':'No'};freed=[];selected=[];reads=[]
    def get(obj,i):reads.append(i);return list(values.values())[i-1]
    lib=SimpleNamespace(CktElement_Get_Pointer=lambda:1,Obj_GetAsString=get,
        DSS_Dispose_String=freed.append,DSSProperty_Set_Index=selected.append)
    def check():
        if fail:raise ValueError('NATIVE_ERROR')
    e=SimpleNamespace(CktElement=SimpleNamespace(AllPropertyNames=lambda:list(values)),
        Properties=SimpleNamespace(_lib=lib,_api_util=SimpleNamespace(ffi=SimpleNamespace(NULL=0)),
            _get_string=lambda raw:raw,_check_for_error=check))
    if fail:
        with pytest.raises(ValueError,match='NATIVE_ERROR'):live_properties(e)
        assert freed==['1']
    else:
        assert live_properties(e)==values and reads==[1,2] and freed==['1','No'] and selected==[1]


def test_direct_reader_has_identical_full_property_coverage():
    from v44_recovery_r019.current_ac_performance import direct_reader
    e=fake({'Tap':'1.0','Enabled':'Yes'})
    assert direct_reader(properties,1)(e,'X')==properties(e,'X')


def test_expected_reference_mutation_is_limited_to_its_copied_bus_list():
    from v44_recovery_r019.current_ac_performance import expected_reference
    old=dict(buses=['a','b'],properties={'NormAmps':'100'},windings=[dict(kV=4.16)])
    new=expected_reference(old);assert new==old
    new['buses'][0]='series_bus'
    assert old['buses']==['a','b'] and new['properties']==old['properties']


def test_ratings_source_diff_only_removes_redundant_expected_json_roundtrip():
    from v44.svr11_vendor import install
    install()
    from v42_voltage_control.integration import PhysicalScenario
    from v44_recovery_r019.current_ac_performance import ratings_reader
    import ast,textwrap
    source=inspect.getsource(ratings_reader(PhysicalScenario._ratings)).replace('reference=_r019_expected_reference(original)','reference=json.loads(canonical(original))')
    assert ast.dump(ast.parse(source))==ast.dump(ast.parse(textwrap.dedent(inspect.getsource(PhysicalScenario._ratings))))


def test_audit_encoder_preserves_exact_json_bytes_and_type_changes():
    from v44_recovery_r019.current_ac_performance import ExactAuditEncoding
    import json,math
    canonical=lambda x:json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
    cache=ExactAuditEncoding();rows=[dict(x=1,z='한글'),dict(x=-0.0,q=[True,False,None])]
    assert cache.canonical_list(rows,canonical)==canonical(rows)
    assert cache.canonical_list(rows,canonical)==canonical(rows) and cache.hits==2
    for value in [1.,0.,2,{'nested':3},[1,2]]:
        rows[0]['x']=value
        assert cache.canonical_list(rows,canonical)==canonical(rows)
    with pytest.raises(ValueError):cache.canonical_list([{'nan':math.nan}],canonical)


def test_audit_encoder_memory_is_bounded_and_changed_queue_is_not_reused():
    from v44_recovery_r019.current_ac_performance import ExactAuditEncoding
    import json
    cache=ExactAuditEncoding(max_bytes=80)
    for i in range(100):
        rows=[{'queue':[i],'tap':i/100}]
        assert cache.canonical_list(rows,json.dumps)=='['+json.dumps(rows[0])+']'
        assert cache.bytes<=80
    assert cache.misses==100


def test_persist_source_only_replaces_two_equivalent_json_encoding_calls():
    from v44.svr11_vendor import install
    install()
    from v42_voltage_control.integration import PhysicalScenario
    from v44_recovery_r019.current_ac_performance import audit_writer,ExactAuditEncoding
    import ast,textwrap
    source=inspect.getsource(audit_writer(PhysicalScenario.persist,ExactAuditEncoding()))
    source=source.replace('_r019_encode(self.rows)','canonical(self.rows)').replace('_r019_encode(self.events)','canonical(self.events)')
    assert ast.dump(ast.parse(source))==ast.dump(ast.parse(textwrap.dedent(inspect.getsource(PhysicalScenario.persist))))


def test_state_source_only_projects_the_live_fields_it_actually_consumes():
    from v44.svr11_ac import SVR11CurrentAC
    from v44_recovery_r019.current_ac_performance import state_reader
    import ast,textwrap
    old=inspect.getsource(SVR11CurrentAC._state)
    new=inspect.getsource(state_reader(SVR11CurrentAC._state)).replace('inv=_r019_state_inventory(e)',"inv=authority.source()['inventory'](e)")
    assert ast.dump(ast.parse(new))==ast.dump(ast.parse(textwrap.dedent(old)))


def test_redundant_svr_measurement_reuse_is_only_immediate_same_native_state():
    from v44_recovery_r019.current_ac_performance import bank_reader
    from copy import deepcopy
    state=dict(time=900,tap=1.,queue=[]);inputs={'load':[1.,2.]};voltage=[1.,0.];calls=[]
    engine=SimpleNamespace(Circuit=SimpleNamespace(AllBusVolts=lambda:voltage))
    bank=SimpleNamespace(engine=engine);audit=SimpleNamespace(rows=[])
    oracle=SimpleNamespace(_bank=bank,_scenario_audit=audit,_state=lambda e:deepcopy(state))
    def original(b):calls.append(1);return {'live':len(calls),'hardware_PASS':True}
    read=bank_reader(original,oracle)
    with patch('v42_voltage_control.integration._physical_inputs',return_value=inputs):
        a=read(bank);audit.rows.append({});b=read(bank)
        assert a==b and len(calls)==1 and oracle._r019_duplicate_bank_reuses==1
        state['tap']=1.00625
        assert read(bank)['live']==2
        inputs['load'][0]=3.
        assert read(bank)['live']==3
        voltage[0]=1.01
        assert read(bank)['live']==4
        state['time']=1800;audit.rows.append({})
        assert read(bank)['live']==5


def test_global_trajectory_sha_change_still_encodes_identical_historical_fields_exactly():
    from v44_recovery_r019.current_ac_performance import ExactAuditEncoding
    import json
    canonical=lambda x:json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
    cache=ExactAuditEncoding();rows=[dict(frozen_trajectory_SHA='old',physical={'nodes':[1.,0.95]},queue=[])]
    assert cache.canonical_list(rows,canonical)==canonical(rows)
    rows[0]['frozen_trajectory_SHA']='new'
    assert cache.canonical_list(rows,canonical)==canonical(rows) and cache.hits>=2
