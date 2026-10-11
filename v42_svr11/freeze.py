"""Exactly eleven banks, independent initial readback and one AC timestamp."""
from pathlib import Path
import copy,math,subprocess
from v42_pr134_b1.common import atomic,read,record,digest,now
from v42_common_campaign.authority import ROOT,source_files

def prepare(root):
    from v42_voltage_control.bindings import original_bindings
    from v42_voltage_control.siting import original_inventory,line_candidate_unit,_downstream_nodes,candidate_unit
    from v42_voltage_control.svr import install,validate_contract
    from v42_voltage_control.integration import scenario_identity,_equipment
    from v42_voltage_control.timecontrol import CommonClock
    from v42_thermal.authority import compiled
    root=Path(root).resolve();root.mkdir(parents=True,exist_ok=True)
    if (root/'HARDWARE.json').exists():raise PermissionError('SVR11_FREEZE_NEVER_OVERWRITTEN')
    authority,*_=original_bindings()
    predecessor=Path(r'D:\v42_voltage_control_development_20261011\FROZEN_SVR7_INFRASTRUCTURE_02\SCENARIO.json')
    old=read(predecessor);c=copy.deepcopy(old['svr'])
    assert [u['id'] for u in c['units']]==['STA01','STA06','STA08','BUS83','BUS79','BUS108','BUS50']
    e,ad,initial=authority.compile_verified()
    try:
        inventory=original_inventory(e,source_receipts=copy.deepcopy(c['units'][3]['source_receipts']))
        row=next(r for r in inventory['original_branches'] if r['element'].lower()=='line.l82')
        assert row['buses']==['81.1.2.3','82.1.2.3'] and row['phases']==3 and row['norm_amps']==400
        kv=4.16/math.sqrt(3);u=candidate_unit(inventory,'BUS83')
        u.update(id='BUS82',logical_site_id='FEEDER_BUS82',cut_element='Line.l82',cut_terminal=2,
            original_bus_spec='82.1.2.3',series_orientation='DOWNSTREAM_OF_EXISTING_BRANCH',
            downstream_bus='82',sensed_bus='82',upstream_new_bus='svr_bus82_series_input',
            nominal_kv_ln=kv,sensed_kv_ln=kv,phase_kva=400*kv,ctprim=400,
            ptratio=kv*1000/120,remote_ptratio=kv*1000/120,
            direct_downstream_bus_coverage=_downstream_nodes(inventory['original_branches'],'Line.l82'))
        u['engineering_assumptions']+=['SVR8 directly senses Bus82 A/B/C to address known May03 A/B overvoltage; success is not assumed.',
            'Serial interaction with retained Bus83 controller is evaluated and recorded, never assumed absent.']
        v=line_candidate_unit(inventory,'BUS48')
        v['engineering_assumptions']+=['SVR11 protects Bus48/IDC06 on a different branch from retained Bus50; past Bus48 development is not combined SVR11 safety proof.']
        assert v['phase_kva']==400*kv
        c['units'] += [u,v]
        prior9=read(Path(r'D:\v42_svr9_may_20261011\hardware\SCENARIO.json'))
        c['units']=copy.deepcopy(prior9['svr']['units'])
        for cid,element,upstream,downstream,sites in (
            ('BUS86','Line.l77','76','86',('STA03','STA10','STA11')),
            ('BUS62','Line.l61','60','62',('STA04','STA05'))):
            row=next(r for r in inventory['original_branches'] if r['element'].lower()==element.lower())
            assert row['buses']==[upstream+'.1.2.3',downstream+'.1.2.3'] and row['phases']==3 and row['norm_amps']==400
            coverage=_downstream_nodes(inventory['original_branches'],element)
            protected=[r for r in inventory['original_endpoints'] if r['logical_site_id'].upper() in sites]
            assert protected and all(r['mv_parent_bus'].split('.')[0].lower() in coverage for r in protected)
            device=candidate_unit(inventory,'BUS83')
            device.update(id=cid,logical_site_id='FEEDER_'+cid,endpoint_id='MV_BRANCH',cut_element=element,cut_terminal=2,
                original_bus_spec=row['buses'][1],series_orientation='DOWNSTREAM_OF_EXISTING_BRANCH',downstream_bus=downstream,
                sensed_bus=downstream,upstream_new_bus='svr_'+cid.lower()+'_series_input',nominal_kv_ln=kv,sensed_kv_ln=kv,
                phase_kva=row['norm_amps']*kv,ctprim=row['norm_amps'],ptratio=kv*1000/120,remote_ptratio=kv*1000/120,
                direct_downstream_bus_coverage=coverage,source_receipts=inventory['source_receipts'])
            device['engineering_assumptions']+=['User-selected series bank protecting '+','.join(sites)+
                '; original seven RegControl tap interaction is measured in every campaign slot, without a safety presumption.']
            c['units'].append(device)
        c.update(status='FROZEN',design_data='Retrospective May03-informed SVR11 design; May2025 is not independent holdout',
            independent_holdout_claim=False,whole_network_success_claim=False)
        validate_contract(c);assert c['units'][:7]==old['svr']['units'] and c['units'][:9]==prior9['svr']['units'] and len(c['units'])==11
        # Repeated saved physical failures justify one placement correction.
        # Preserve every other bank and all ratings/control parameters.
        change=read(root.parent/'EQUIPMENT_CHANGE_CONTRACT.json')
        assert change['confirmed_repeated_physical_failure'] and change['SVR_count']==11
        assert len(change['failed_dates'])>=2 and all(record(r['path'])==r for r in change['protected_evidence'])
        baseline=copy.deepcopy(c['units']);u=next(x for x in c['units'] if x['id']=='BUS82')
        assert u['cut_element']=='Line.l82' and u['cut_terminal']==2 and u['sensed_bus']=='82'
        u.update(cut_terminal=1,original_bus_spec='81.1.2.3',series_orientation='UPSTREAM_OF_EXISTING_BRANCH',
            upstream_new_bus='svr_bus82_line_input')
        u['engineering_assumptions']+=['Repeated May04/May05 Actual primary-side voltage failures: existing SVR8 is relocated before line82 with remote Bus82 A/B/C sensing; no additional device, relaxed limit or monthly safety claim.']
        placement_keys={'cut_terminal','original_bus_spec','series_orientation','upstream_new_bus','engineering_assumptions'}
        assert all(a==b if a['id']!='BUS82' else {k:v for k,v in a.items() if k not in placement_keys}==
            {k:v for k,v in b.items() if k not in placement_keys} for a,b in zip(baseline,c['units']))
        validate_contract(c)
        c['design_data']='Retrospective May04/May05 structural-primary correction; one existing bank relocated; May2025 is not independent holdout'
    finally:e.Basic.ClearAll()
    scenario=copy.deepcopy(old);scenario['svr']=c;scenario['scenario_SHA']=digest(scenario_identity(scenario))
    atomic(root/'SCENARIO.json',scenario)
    states=[];physical=[];thermal=None
    for namespace in ('DAYAHEAD','ACTUAL'):
        e,ad,initial=authority.compile_verified()
        try:
            before=_equipment(e);clock=CommonClock(namespace,'2025-05-01');clock.bind(e);bank=install(e,c)
            installed=authority.source()['inventory'](e)
            assert installed['RegControl_count']==40 and installed['CapControl_count']==0 and len(installed['capacitors'])==4
            assert all(r['enabled'] and r['initial_tap']==1 for r in installed['regulators'])
            assert installed['capacitors']==initial['capacitors']
            branches,topology=authority.source()['oriented_branches'](e)
            rows,lines=compiled(e,branches)
            identity=dict(schema='V42_TRANSFORMER_NORMALAMPS_CURRENT_V1',rows=rows,lines=lines,scenario_SHA=scenario['scenario_SHA'])
            t=dict(PASS=True,rows=rows,lines=lines,Planning=rows,Actual=rows,
                controls=installed,topology=topology,identity=identity,provenance=c['units'][3]['source_receipts'],
                transformer_current_authority_sha256=digest(identity))
            if thermal is None:thermal=t
            else:assert t==thermal
            state=dict(namespace=namespace,original_inventory=initial,installed_inventory=installed,
                empty_queue=True,initial_taps=bank.initial_state,installation=bank.installation_receipt)
            atomic(root/(namespace+'_INITIAL_STATE.json'),state);states.append(record(root/(namespace+'_INITIAL_STATE.json')))
            physical.append(dict(namespace=namespace,original_equipment=before,installed_equipment=_equipment(e)))
            if namespace=='ACTUAL':
                single=clock.settle_slot(e,0)
                measurement=bank.measure()
                assert single['PASS'] and measurement['Converged'] and measurement['ControlActionsDone']
                atomic(root/'SINGLE_TIMESTAMP_AC.json',dict(clock=single,measurement=measurement,
                    purpose='Connection and measurement implementation smoke test only; no monthly safety certification'))
        finally:e.Basic.ClearAll()
    atomic(root/'THERMAL.json',thermal);atomic(root/'PHYSICAL_PRESERVATION.json',physical)
    source=source_files();h=dict(schema='V42_SVR11_MINIMUM_IMPLEMENTATION_FREEZE_V1',PASS=True,SVR_count=11,
        source_SHA=digest(source),source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        predecessor=record(predecessor),predecessor_seven_units_preserved=True,scenario=record(root/'SCENARIO.json'),
        equipment_SHA=digest(physical),scenario_SHA=scenario['scenario_SHA'],independent_initial_states=states,
        original_RegControl_count=7,additional_RegControl_count=33,capacitors_fixed_ON=4,
        CapControl_count=0,DSTATCOM_count=0,tap_optimization_variables=0,minimum_AC=record(root/'SINGLE_TIMESTAMP_AC.json'),
        equipment_change_contract=record(root.parent/'EQUIPMENT_CHANGE_CONTRACT.json'),
        monthly_zero_violation_certification=False,pre_campaign_monthly_canary=False,independent_holdout_claim=False,UTC=now())
    atomic(root/'EXECUTION_SOURCE_MANIFEST.json',dict(execution_sources=source,execution_SHA=digest(source)))
    atomic(root/'HARDWARE.json',h)
    return h

if __name__=='__main__':
    import sys
    prepare(sys.argv[1])
