"""All-May Actual-only replay admission, separate from new Planning/E2E."""
from contextlib import ExitStack
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json

import pytest

from v42_b3_joint.contracts import digest
from v42_voltage_control import authority,integration


def saved(tmp_path,name,value):
    p=tmp_path/name;p.write_text(json.dumps(value));return integration.record(p)


@pytest.fixture
def frozen(tmp_path):
    expected=json.loads((Path(integration.__file__).parents[1]/'docs/v42_autonomous_grid_controls_april_b0/REGCONTROL_CAPCONTROL_SOURCE_AUDIT.json').read_text())['actual_static_compile']
    sources={'example.py':'1'*64};source=digest(sources)
    units=[dict(id=name,phases=[1,2,3]) for name in ('STA01','STA06','STA08','BUS83')]
    contract=dict(status='FROZEN',units=units)
    scenario=dict(case='B',time_mode='TIME',capcontrol=None,svr=contract,connection_manifest=saved(tmp_path,'connection.json',{}),scenario_SHA='2'*64)
    inventory=deepcopy(expected);inventory['RegControl_count']=19;inventory['control_mode']=2
    inventory['regulators'] += [dict(deepcopy(expected['regulators'][0]),name='svr_'+u['id'].lower()+'_p'+str(p)) for u in units for p in (1,2,3)]
    state=dict(source_SHA=source,scenario_SHA=scenario['scenario_SHA'],original_initial_inventory=expected,installed_inventory=inventory,
        native_clock={'Hour':0,'Seconds':0.,'control_mode':2,'maxcontroliter':100,'maxiter':15,'queue':[],'queue_size':0,'solution_mode':0},
        new_SVR_initial_winding_taps={'svr_'+u['id'].lower()+'_p'+str(p):[1.,1.] for u in units for p in (1,2,3)},
        retired_inventory={'retired_objects_count':0})
    ident=digest(state);namespaces=[]
    for namespace in ('DAYAHEAD','ACTUAL'):
        namespaces.append(dict(namespace=namespace,initial_state_SHA=ident,
            initial_state_receipt=saved(tmp_path,namespace+'.json',dict(initial_state=state,initial_state_SHA=ident))))
    value=dict(schema='V42_SVR4_HARDWARE_FREEZE_RECEIPT_V1',status='FROZEN_HARDWARE_ONLY_NOT_E2E_QUALIFIED',PASS=True,
        execution_SourceSHA_before=source,execution_SourceSHA_after=source,SourceCode_before_after_equal=True,
        original_RegControl_count=7,CapControl_count=0,Cap4_fixed_ON_total_nameplate_kvar=750,existing_original_band_pu=[.95,1.05],
        additional_RegControl_count=12,additional_single_phase_transformer_count=12,
        new_model_regenerated=False,optimized_Planning_Actual_E2E_qualified=False,all31May_qualified=False,
        scenario=saved(tmp_path,'scenario.json',scenario),scenario_SHA=scenario['scenario_SHA'],controller_contract=saved(tmp_path,'contract.json',contract),
        selected_units_canonical_SHA_before=digest(units),selected_units_canonical_SHA_after=digest(units),
        independent_namespaces=namespaces,source_initial_state_SHA=ident,external_original_source_receipts=[saved(tmp_path,'original_source.json',{})],
        source_archive_receipt=saved(tmp_path,'archive.json',dict(source_SHA=source,execution_sources=sources)))
    for k in ('hardware_and_control_law_changes_from_selected_development_units','original_equipment_rating_changes',
        'original_RegControl_settings_changes','original_RegControl_tap_setters','original_Capacitor_state_setters',
        'Native_optimizer_calls','runtime_physical_solve_count','replay_logical_slots'):value[k]=0
    return value,scenario,sources,source


def test_frozen_hardware_literal_state_and_changed_layout_fail_closed(tmp_path,frozen):
    value,scenario,sources,source=frozen
    with patch.object(authority,'source_files',return_value=sources),patch.object(integration,'validate_scenario',side_effect=lambda v:(v,None,v['svr'])):
        assert authority.verify_frozen_infrastructure(saved(tmp_path,'freeze.json',value),source)[1]==scenario
        changed=deepcopy(value);changed['selected_units_canonical_SHA_after']='3'*64
        with pytest.raises(PermissionError,match='UNIT_LAYOUT_DRIFT'):
            authority.verify_frozen_infrastructure(saved(tmp_path,'changed.json',changed),source)
        changed=deepcopy(value);changed['execution_SourceSHA_after']='3'*64
        with pytest.raises(PermissionError,match='HARDWARE_REPLAY_ONLY'):
            authority.verify_frozen_infrastructure(saved(tmp_path,'changed_source.json',changed),source)
        changed=deepcopy(value);changed['optimized_Planning_Actual_E2E_qualified']=True
        with pytest.raises(PermissionError,match='HARDWARE_REPLAY_ONLY'):
            authority.verify_frozen_infrastructure(saved(tmp_path,'wrong_claim.json',changed),source)


@pytest.mark.parametrize('day',['2025-05-02','2025-05-23','2025-05-31'])
def test_all_may_existing_plan_permit_is_actual_only_and_native_guarded(tmp_path,frozen,day):
    value,scenario,sources,source=frozen;infra=saved(tmp_path,'freeze.json',value);binding={'binding_SHA':'4'*64}
    with patch.object(authority,'source_files',return_value=sources),patch.object(authority,'verify_preserved_plan',return_value=binding), \
            patch.object(integration,'validate_scenario',side_effect=lambda v:(v,None,v['svr'])):
        with authority.frozen_plan_permit('B2',day,source,scenario,infrastructure_receipt=infra,preserved_plan=binding):
            current=authority.authorize_actual('B2',day,source,scenario['scenario_SHA'])
            assert current['scope']=='EXISTING_FROZEN_PLAN_NATIVE_ZERO_REPLAY'
            assert current['new_Planning_E2E_qualified'] is False
            import gurobipy as gp
            assert gp.Model.optimize.__name__=='denied' and gp.Model.presolve.__name__=='denied'
            with pytest.raises(PermissionError,match='SOURCE_BOUND_NAMESPACE'):
                authority.authorize_physical('B2',day,source,scenario['scenario_SHA'],'DAYAHEAD')
        with pytest.raises(PermissionError,match='ACTUAL_ONLY_MAY31'):
            with authority.frozen_plan_permit('B2',day,source,scenario,infrastructure_receipt=infra,preserved_plan=binding,namespace='DAYAHEAD'):pass


def test_preserved_plan_digest_rejects_changed_day_or_receipt(tmp_path):
    source=saved(tmp_path,'source.json',{})
    binding=authority.preserved_plan_binding('B2','2025-05-02',{},[source])
    with pytest.raises(PermissionError,match='EXACT_EXISTING_FROZEN_PLAN'):
        authority.verify_preserved_plan(dict(binding,day='2025-05-03'),'B2','2025-05-02')
    with pytest.raises(PermissionError,match='EXACT_EXISTING_FROZEN_PLAN'):
        authority.verify_preserved_plan(dict(binding,receipts={'changed':source}),'B2','2025-05-02')


def original_operations_binding(tmp_path,arm='B2',day='2025-05-02',*,log_mutation=None,exo_day=None):
    """Use the preserved producer's actual slots/exogenous-only log schema."""
    import numpy as np
    import pandas as pd
    p=np.arange(96*12,dtype=float).reshape(96,12)/10
    q=-p/4
    mp=np.arange(96*4,dtype=float).reshape(96,4)/20
    mq=mp/5
    locations=np.tile(np.array(['STA01','IDC03','STA08','IDC12']),(96,1))
    fixed=tmp_path/'fixed.npz';mess=tmp_path/'mess.npz';exo=tmp_path/'actual.parquet'
    np.savez(fixed,PCC_P_kw=p,PCC_Q_kvar=q)
    np.savez(mess,P_kw=mp,Q_kvar=mq,locations=locations)
    pd.DataFrame({'ts_fixed_aest_end':pd.date_range(pd.Timestamp(exo_day or day,tz='Etc/GMT-10')
        +pd.Timedelta(minutes=15),periods=96,freq='15min')}).to_parquet(exo)
    rows=[dict(slot=k,PCC_P_kw=p[k].tolist(),PCC_Q_kvar=q[k].tolist(),MESS_P_kw=mp[k].tolist(),
        MESS_Q_kvar=mq[k].tolist(),MESS_locations=locations[k].tolist(),allocation={}) for k in range(96)]
    inputs=dict(slots=rows,Actual_exogenous=integration.record(exo))
    if log_mutation:log_mutation(inputs)
    receipts=dict(REQUEST=saved(tmp_path,'request.json',dict(arm=arm,day=day)),
        PLANNING_FREEZE=saved(tmp_path,'freeze.json',dict(identity=dict(arm=arm,day=day))),
        ACTUAL_FIXED=integration.record(fixed),ACTUAL_MESS=integration.record(mess),
        ORIGINAL_RAW_AC=saved(tmp_path,'raw.json',{}),PHYSICAL_INPUT_LOG=saved(tmp_path,'physical.json',inputs),
        ORIGINAL_CONTROL_LOG=saved(tmp_path,'controls.json',{}),NATIVE_INPUT=saved(tmp_path,'native.json',{}),
        OPERATIONS_INPUT=saved(tmp_path,'operations.json',{}),Actual_exogenous=integration.record(exo))
    return authority.preserved_plan_binding(arm,day,receipts,[saved(tmp_path,'original_source.json',{})])


@pytest.mark.parametrize('arm',['B1','B2'])
def test_original_log_without_envelope_day_binds_exact_96_actual_inputs(tmp_path,arm):
    binding=original_operations_binding(tmp_path,arm=arm)
    assert authority.read(authority.checked(binding['receipts']['PHYSICAL_INPUT_LOG'])).keys()=={'slots','Actual_exogenous'}
    assert authority.verify_preserved_plan(binding,arm,'2025-05-02')==binding


@pytest.mark.parametrize('key,value',[('PCC_P_kw',999.),('MESS_Q_kvar',999.),('MESS_locations','OTHER_SITE')])
def test_literal_physical_log_cannot_change_frozen_power_or_location(tmp_path,key,value):
    def mutate(inputs):inputs['slots'][10][key][0]=value
    binding=original_operations_binding(tmp_path,log_mutation=mutate)
    with pytest.raises(PermissionError,match='FROZEN_PQ_LOCATION_DRIFT:'+key):
        authority.verify_preserved_plan(binding,'B2','2025-05-02')


def test_actual_timestamp_axis_cannot_substitute_other_day(tmp_path):
    binding=original_operations_binding(tmp_path,exo_day='2025-05-03')
    with pytest.raises(PermissionError,match='ACTUAL_EXOGENOUS_DAY_AXIS_DRIFT'):
        authority.verify_preserved_plan(binding,'B2','2025-05-02')


def test_declared_receipt_path_normalizes_only_same_file_and_exact_bytes(tmp_path):
    receipt=saved(tmp_path,'original.json',{'immutable':True})
    (tmp_path/'subfolder').mkdir()
    alias=dict(receipt,path=str(tmp_path/'subfolder/../original.json'))
    assert authority.checked(alias)==Path(receipt['path'])
    with pytest.raises(PermissionError,match='RECEIPT_DRIFT'):
        authority.checked(dict(alias,sha256='f'*64))


def test_nested_original_exogenous_path_alias_requires_same_checked_file(tmp_path):
    (tmp_path/'alias').mkdir()
    def alias(inputs):
        inputs['Actual_exogenous']['path']=str(tmp_path/'alias/../actual.parquet')
    binding=original_operations_binding(tmp_path,arm='B1',log_mutation=alias)
    assert authority.verify_preserved_plan(binding,'B1','2025-05-02')==binding


@pytest.mark.parametrize('key,value',[('sha256','f'*64),('bytes',0),('extra_field',True)])
def test_nested_original_exogenous_alias_cannot_change_hash_size_or_keys(tmp_path,key,value):
    def change(inputs):inputs['Actual_exogenous'][key]=value
    binding=original_operations_binding(tmp_path,arm='B1',log_mutation=change)
    with pytest.raises(PermissionError,match='RECEIPT_DRIFT|EXOGENOUS_BINDING_DRIFT'):
        authority.verify_preserved_plan(binding,'B1','2025-05-02')


def test_nested_exogenous_identical_copy_is_not_original_file_alias(tmp_path):
    def copied(inputs):
        actual=Path(inputs['Actual_exogenous']['path']);other=tmp_path/'copy.parquet'
        other.write_bytes(actual.read_bytes())
        inputs['Actual_exogenous']=integration.record(other)
    binding=original_operations_binding(tmp_path,arm='B1',log_mutation=copied)
    with pytest.raises(PermissionError,match='EXOGENOUS_BINDING_DRIFT'):
        authority.verify_preserved_plan(binding,'B1','2025-05-02')


def version_two_freeze(tmp_path,frozen,variant):
    old,scenario,sources,source=frozen
    value=deepcopy(old);scenario=deepcopy(scenario)
    value.update(schema='V42_SVR_HARDWARE_FREEZE_RECEIPT_V2',infrastructure_variant=variant,
        original_SVR4_predecessor_receipt=saved(tmp_path,'predecessor.json',old),
        preserved_SVR4_units_canonical_SHA=digest(scenario['svr']['units']))
    added=[]
    if variant=='SVR7':
        for name,element,bus in [('BUS79','Line.l79','79'),('BUS108','Line.l105','108'),('BUS48','Line.l47','48')]:
            added.append(dict(id=name,phases=[1,2,3],cut_element=element,cut_terminal=2,
                downstream_bus=bus,original_bus_spec=bus+'.1.2.3'))
    scenario['svr']['units']+=added
    value['additional_unit_ids']=[u['id'] for u in added]
    value['scenario']=saved(tmp_path,'v2scenario.json',scenario)
    value['controller_contract']=saved(tmp_path,'v2contract.json',scenario['svr'])
    value['selected_units_canonical_SHA_before']=value['selected_units_canonical_SHA_after']=digest(scenario['svr']['units'])
    value['additional_RegControl_count']=value['additional_single_phase_transformer_count']=3*len(scenario['svr']['units'])
    state=authority.read(authority.checked(old['independent_namespaces'][0]['initial_state_receipt']))['initial_state']
    example=deepcopy(state['installed_inventory']['regulators'][0])
    for unit in added:
        for p in unit['phases']:
            name='svr_'+unit['id'].lower()+'_p'+str(p)
            state['installed_inventory']['regulators'].append(dict(example,name=name))
            state['new_SVR_initial_winding_taps'][name]=[1.,1.]
    state['installed_inventory']['RegControl_count']=7+value['additional_RegControl_count']
    value['source_initial_state_SHA']=digest(state)
    value['independent_namespaces']=[dict(namespace=n,initial_state_SHA=digest(state),
        initial_state_receipt=saved(tmp_path,'v2'+n+'.json',dict(initial_state=state,initial_state_SHA=digest(state))))
        for n in ('DAYAHEAD','ACTUAL')]
    return value,scenario,sources,source


@pytest.mark.parametrize('variant',['SVR4','SVR7'])
def test_versioned_freeze_preserves_four_units_and_exact_dynamic_native_inventory(tmp_path,frozen,variant):
    value,scenario,sources,source=version_two_freeze(tmp_path,frozen,variant)
    with patch.object(authority,'source_files',return_value=sources),patch.object(integration,'validate_scenario',side_effect=lambda v:(v,None,v['svr'])):
        assert authority.verify_frozen_infrastructure(saved(tmp_path,'v2freeze.json',value),source)[1]==scenario
        bad=deepcopy(value);bad['additional_RegControl_count']+=1
        with pytest.raises(PermissionError,match='PHASE_EQUIPMENT_COUNT_DRIFT'):
            authority.verify_frozen_infrastructure(saved(tmp_path,'badcount.json',bad),source)
        badscenario=deepcopy(scenario);badscenario['svr']['units'][0]['phase_kva']=999.
        bad=deepcopy(value);bad['scenario']=saved(tmp_path,'badscenario.json',badscenario)
        bad['controller_contract']=saved(tmp_path,'badcontract.json',badscenario['svr'])
        bad['selected_units_canonical_SHA_before']=bad['selected_units_canonical_SHA_after']=digest(badscenario['svr']['units'])
        with pytest.raises(PermissionError,match='ORIGINAL_FOUR_PHYSICAL_UNIT_DRIFT'):
            authority.verify_frozen_infrastructure(saved(tmp_path,'badphysical.json',bad),source)


def test_ref_time_frozen_comparison_has_no_added_devices_or_planning_rights(tmp_path,frozen):
    value,scenario,sources,source=frozen;infra=saved(tmp_path,'freeze.json',value);binding={'binding_SHA':'4'*64}
    ref=dict(scenario,case='REFa',svr=None)
    with patch.object(authority,'source_files',return_value=sources),patch.object(authority,'verify_preserved_plan',return_value=binding), \
            patch.object(integration,'validate_scenario',side_effect=lambda v:(v,None,v['svr'])):
        with authority.frozen_plan_permit('B2','2025-05-02',source,ref,infrastructure_receipt=infra,preserved_plan=binding) as identity:
            assert identity['namespace']=='ACTUAL'
            assert identity['new_Planning_E2E_qualified'] is False
        ref['connection_manifest']=saved(tmp_path,'otherconnection.json',{})
        with pytest.raises(PermissionError,match='REF_CONNECTION_SOURCE_DRIFT'):
            with authority.frozen_plan_permit('B2','2025-05-02',source,ref,infrastructure_receipt=infra,preserved_plan=binding):pass
