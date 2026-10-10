"""Explicit permissions and preservation guards; no optimizer or campaign."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json

import pytest

from v42_voltage_control import integration as subject, authority
from v42_b3_joint.contracts import digest


@pytest.fixture
def expected():
    root=Path(__file__).resolve().parents[1]
    audit=json.loads((root/'docs/v42_autonomous_grid_controls_april_b0/REGCONTROL_CAPCONTROL_SOURCE_AUDIT.json').read_text(encoding='utf8'))
    return audit['actual_static_compile']


def scenario(case='REF'):
    return dict(case=case,time_mode='STATIC' if case=='REF' else 'TIME',
        capcontrol=None if case in ('REF','REFa','B') else dict(devices=[dict(capacitor=n) for n in
            (['c83'] if case=='A1' else ['c83','c88a','c90b','c92c'])]),svr=None)


def test_original_static_contract_is_exact_and_settings_not_mutated(expected):
    before=deepcopy(expected)
    assert subject.assert_control_inventory(expected,scenario(),initial=True,expected=expected)
    assert before==expected


def test_cap_states_permitted_only_for_explicit_controlled_subset(expected):
    inventory=deepcopy(expected);inventory['control_mode']=2;inventory['CapControl_count']=1
    inventory['capacitors'][0]['states']=[0]
    assert subject.assert_control_inventory(inventory,scenario('A1'),expected=expected)
    with pytest.raises(ValueError,match='FIXED_ON'):
        subject.assert_control_inventory(inventory,scenario('A1'),initial=True,expected=expected)
    inventory['capacitors'][1]['states']=[0]
    with pytest.raises(ValueError,match='FIXED_ON'):
        subject.assert_control_inventory(inventory,scenario('A1'),expected=expected)


@pytest.mark.parametrize('property,value',[('VReg','119'),('Band','3'),('R','0'),('X','0'),('Delay','1'),('TapDelay','1'),('CTPrim','701'),('PTRatio','21')])
def test_original_element_properties_cannot_be_changed_in_new_epoch(expected,property,value):
    inventory=deepcopy(expected);inventory['control_mode']=2
    inventory['regulators'][0]['resolved_properties'][property]=value
    with pytest.raises(ValueError,match='PARAMETER_DRIFT'):
        subject.assert_control_inventory(inventory,scenario('REFa'),expected=expected)


def test_fixed_on_and_physical_cap_rating_guards_are_separate(expected):
    inventory=deepcopy(expected);inventory['control_mode']=2;inventory['CapControl_count']=4
    inventory['capacitors'][0]['states']=[0]
    assert subject.assert_control_inventory(inventory,scenario('A2'),expected=expected)
    inventory['capacitors'][0]['num_steps']=12
    with pytest.raises(ValueError,match='PHYSICAL_RATING'):
        subject.assert_control_inventory(inventory,scenario('A2'),expected=expected)


def test_extra_regulator_and_nonautomatic_original_are_rejected(expected):
    inventory=deepcopy(expected)
    inventory['regulators'].append(dict(inventory['regulators'][0],name='undeclared'))
    with pytest.raises(ValueError,match='UNDECLARED'):
        subject.assert_control_inventory(inventory,scenario(),expected=expected)
    inventory=deepcopy(expected);inventory['regulators'][0]['enabled']=False
    with pytest.raises(ValueError,match='SEVEN_AUTO'):
        subject.assert_control_inventory(inventory,scenario(),expected=expected)


def test_scenario_schema_requires_frozen_hash_and_distinct_ref_semantics(tmp_path):
    p=tmp_path/'connections.json';p.write_text('{}')
    identity=dict(schema=subject.SCHEMA,**scenario(),connection_manifest=subject.record(p))
    value=dict(identity,scenario_SHA=digest(identity))
    assert subject.validate_scenario(value)[0]==value
    value['time_mode']='TIME';value['scenario_SHA']=digest(subject.scenario_identity(value))
    with pytest.raises(ValueError,match='REF_STATIC'):
        subject.validate_scenario(value)
    value=dict(identity,scenario_SHA=digest(identity));p.write_text('{"changed":true}')
    with pytest.raises(ValueError,match='MANIFEST_RECEIPT_DRIFT'):
        subject.validate_scenario(value)


def test_source_bound_namespace_permission_cannot_be_replaced_by_hash_string(tmp_path):
    p=tmp_path/'connections.json';p.write_text('{}')
    identity=dict(schema=subject.SCHEMA,**scenario(),connection_manifest=subject.record(p))
    value=dict(identity,scenario_SHA=digest(identity));sources={'example.py':'1'*64};source=digest(sources)
    with patch.object(authority,'source_files',return_value=sources):
        with pytest.raises(PermissionError,match='SOURCE_BOUND_NAMESPACE'):
            authority.authorize_actual('B2','2025-05-01',source,value['scenario_SHA'])
        with authority.physical_permit('B2','2025-05-01',source,value,development=True,namespace='DAYAHEAD'):
            assert authority.authorize_physical('B2','2025-05-01',source,value['scenario_SHA'],'DAYAHEAD')
            with pytest.raises(PermissionError,match='SOURCE_BOUND_NAMESPACE'):
                authority.authorize_actual('B2','2025-05-01',source,value['scenario_SHA'])
        with pytest.raises(PermissionError,match='FROZEN_DESIGN'):
            with authority.physical_permit('B2','2025-05-01',source,value): pass


def test_execution_source_change_inside_permit_fails_even_without_native(tmp_path):
    p=tmp_path/'connections.json';p.write_text('{}')
    identity=dict(schema=subject.SCHEMA,**scenario(),connection_manifest=subject.record(p))
    value=dict(identity,scenario_SHA=digest(identity));sources={'example.py':'1'*64}
    with patch.object(authority,'source_files',side_effect=[sources,{'example.py':'2'*64}]):
        with pytest.raises(PermissionError,match='EXECUTION_SOURCE_MUTATED'):
            with authority.physical_permit('B2','2025-05-01',digest(sources),value,development=True): pass


def test_full_archive_copy_and_original_receipts_rechecked_never_overwritten(tmp_path):
    root=tmp_path/'root';root.mkdir();(root/'v42_example').mkdir();(root/'tests').mkdir()
    source=root/'v42_example/source.py';source.write_bytes(b'x = 1\r\n')
    (root/'tests/test_x.py').write_bytes(b'assert True\n')
    sources={'v42_example/source.py':subject.record(source)['sha256']}
    output=tmp_path/'archive'
    with patch.object(authority,'ROOT',root),patch.object(authority,'source_files',return_value=sources):
        receipt=authority.archive_source(output,source_SHA=digest(sources))
        assert authority.archive_source(output,source_SHA=digest(sources))==receipt
        assert (output/'code/v42_example/source.py').read_bytes()==source.read_bytes()
        assert (output/'code/tests/test_x.py').is_file()
        (output/'code/v42_example/source.py').write_bytes(b'x = 2\n')
        with pytest.raises(PermissionError,match='RECEIPT_DRIFT'):
            authority.archive_source(output,source_SHA=digest(sources))


def test_new_scientific_package_does_not_import_retired_implementation():
    import ast
    root=Path(subject.__file__).parent
    for p in root.glob('*.py'):
        tree=ast.parse(p.read_text(encoding='utf8'))
        for node in ast.walk(tree):
            names=[alias.name for alias in node.names] if isinstance(node,ast.Import) else [node.module or ''] if isinstance(node,ast.ImportFrom) else []
            assert not any(name.startswith('v42_dstatcom') for name in names),(p,names)


def test_only_direct_original_backend_compile_hook_is_admitted_not_auxiliary_ancestor():
    from types import SimpleNamespace
    namespace={}
    exec('def backend(trajectory):\n    compile_clean_engine()\n    auxiliary_thermal_compile()\n',namespace)
    body=namespace['backend'].__code__;seen=[]
    def compile_hook():
        seen.append(subject._physical_frame(body,'ACTUAL',direct_calls=('compile_clean_engine',)))
    def auxiliary():
        compile_hook()
    namespace.update(compile_clean_engine=compile_hook,auxiliary_thermal_compile=auxiliary)
    tr=SimpleNamespace(namespace='ACTUAL',day='2025-05-01',case='B0')
    namespace['backend'](tr)
    assert seen[0]['arm']=='B0'
    assert seen[1] is None


def test_wrong_design_producer_pass_or_measurement_proxy_cannot_qualify_model():
    item=dict(PASS=True,evidence_kind='physical_model_regeneration',source_SHA='1'*64,scenario_SHA='2'*64,
              model_regenerated=True,topology_measurement_proxy_only=False,original_model_reused=False)
    authority._evidence_identity('physical_model_regeneration',item,'1'*64,'2'*64)
    for key,value in [('source_SHA','3'*64),('scenario_SHA','3'*64),('evidence_kind','regression')]:
        with pytest.raises(PermissionError,match='SOURCE_SCENARIO_MATCHED'):
            authority._evidence_identity('physical_model_regeneration',dict(item,**{key:value}),'1'*64,'2'*64)
    with pytest.raises(PermissionError,match='NOT_MODEL_REGENERATION'):
        authority._evidence_identity('physical_model_regeneration',dict(item,topology_measurement_proxy_only=True),'1'*64,'2'*64)


def test_gate_label_requires_actual_arm_day_and_current_source_scenario():
    gate=dict(PASS=True,arm='B1',day='2025-05-28',source_SHA='1'*64,scenario_SHA='2'*64)
    authority._gate_identity('B1',gate,'1'*64,'2'*64)
    for key,value in [('arm','B2'),('day','2025-05-01'),('source_SHA','3'*64),('scenario_SHA','3'*64)]:
        with pytest.raises(PermissionError,match='EXACT_ARM_DAY_SOURCE_SCENARIO'):
            authority._gate_identity('B1',dict(gate,**{key:value}),'1'*64,'2'*64)


def test_native_normalamps_and_original_nameplate_current_are_independent_strict_guards():
    from types import SimpleNamespace
    winding=[1]
    engine=SimpleNamespace(
        Circuit=SimpleNamespace(AllNodeNames=lambda:['a.1','a.2','a.3','b.1','b.2','b.3'],
            AllBusMagPu=lambda:[1.]*6,SetActiveElement=lambda name:None,Losses=lambda:[0.,0.]),
        Lines=SimpleNamespace(AllNames=lambda:['none']),
        Transformers=SimpleNamespace(AllNames=lambda:['tx'],Name=lambda name:None,
            Wdg=lambda w:winding.__setitem__(0,w),kV=lambda:1. if winding[0]==1 else .5,kVA=lambda:100.),
        Properties=SimpleNamespace(Value=lambda name:'120'),
        CktElement=SimpleNamespace(NumConductors=lambda:4,NumTerminals=lambda:2,NumPhases=lambda:3,
            NodeOrder=lambda:[1,2,3,0,1,2,3,0],
            CurrentsMagAng=lambda:[100.,0.,100.,0.,100.,0.,0.,0.,200.,0.,200.,0.,200.,0.,0.,0.],
            Powers=lambda:[0.]*16))
    measured=subject.measure_full_network(engine,{'a.1','a.2','a.3','b.1','b.2','b.3'},{'transformer.tx':{}})
    assert measured['transformer_current_violation_cells']==0
    assert measured['transformer_kva_violation_cells']==0
    assert measured['transformer_nameplate_current_violation_cells']==6
    assert measured['original_transformer_nameplate_current_violation_cells']==6
    assert measured['PASS'] is False
    for row in measured['currents']:
        kv=1. if row['terminal']==1 else .5
        assert row['nameplate_current_A']==100./(3.**.5*kv)
        assert row['nameplate_current_loading_pu']==row['current_A']/row['nameplate_current_A']
        assert row['loading_pu']==100./120.


def test_nameplate_current_units_cancel_kilo_for_service_and_singlephase_series_banks():
    import math
    assert 750./(math.sqrt(3.)*.48)==pytest.approx(902.1097956087903)
    assert 960.710847931536/2.40177711982884==pytest.approx(400.)


def test_both_source_measurement_formulas_use_same_narrow_backend_proxy_and_restore(tmp_path):
    from types import SimpleNamespace
    from unittest.mock import Mock
    engine=object(); calls=[]
    def current(engine,branch): return ('NormalAmps',branch)
    def legacy(engine,branch): return ('Nameplate',branch)
    def compile_original(): return (engine,None,None)
    def voltage_original(engine,nodes): return nodes
    def assert_original(inventory,*,initial=False): return True
    source=dict(branch_measurement=current,legacy_branch_measurement=legacy,
                audit=dict(static_source_graph=dict(files=[]),code_read=[]))
    original=SimpleNamespace(compile_verified=compile_original,assert_inventory=assert_original,source=lambda:source)
    namespace={}
    exec(compile('def run_fresh_opendss(trajectory,engine,branch):\n    return _branch_measurement(engine,branch)\n',__file__,'exec'),namespace)
    backend=SimpleNamespace(run_fresh_opendss=namespace['run_fresh_opendss'],_voltage_vector=voltage_original)
    mapping=SimpleNamespace(apply_trajectory_slot=voltage_original)
    audit=SimpleNamespace(scenario=dict(scenario_SHA='2'*64),sessions={id(engine):dict(engine=engine)},sources=[],
        persist=Mock())
    def measure(engine,branch,function):
        calls.append(function)
        return function(engine,'declared-terminal-proxy')
    audit.measure_original_branch=measure
    thermal=dict(PASS=True,transformer_current_authority_sha256='3'*64,Planning=[],Actual=[])
    trajectory=SimpleNamespace(namespace='ACTUAL',day='2025-05-01',case='B0')
    from v42_thermal.authority import current_authority
    with patch.object(subject,'PhysicalScenario',return_value=audit),patch.object(subject,'_bindings',return_value=(original,backend,mapping)),\
         patch.object(authority,'authorize_physical',return_value=True),patch('v42_thermal.authority.current_authority',return_value=thermal):
        with subject.scenario_scope({},tmp_path,source_SHA='1'*64,arm='B0',day='2025-05-01'):
            for name,label in [('branch_measurement','NormalAmps'),('legacy_branch_measurement','Nameplate')]:
                namespace['_branch_measurement']=source[name]
                assert backend.run_fresh_opendss(trajectory,engine,'original')==(label,'declared-terminal-proxy')
                assert source[name](engine,'auxiliary')==(label,'auxiliary')
        assert source['branch_measurement'] is current and source['legacy_branch_measurement'] is legacy
    assert calls==[current,legacy]
    audit.persist.assert_called_once_with(error=None,bodies_unchanged=True)
