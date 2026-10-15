"""Separate actual as-of substeps from retrospective settled Fresh samples."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import json
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from v42_integration.actual_validation import read,_validated_hardware_context,mess_service_bindings
from v42_integration.m_engine import _write,file_record
from v42_integration.unified_contract import digest
from v42_integration.isolated_unknown import no_native

OUT=ROOT/'docs/v42_unified_aidc_mess_research_20261014/RELEASE_RECOVERY_20261015/RC01/AIDC/REPLAY02'
OLD=Path('D:/v42_integration_validation_20261013/DDAY_V5_B3_FINAL_ATTEMPT01/B3')

def main():
    target=OUT/'ASOF_SUBSTEP_PHYSICAL_DIAGNOSIS.json'
    if target.exists():raise FileExistsError('ASOF_SUBSTEP_DIAGNOSIS_MUST_NOT_OVERWRITE')
    certificate=read(OUT/'INDEPENDENT_ACTUAL_CERTIFICATE.json')
    assert certificate['instantaneous_start_ledgers_identical'] and certificate['same_input_current_full_physical_and_SVR_hash_maps_identical']
    prefix=read(OUT/'C0/PUBLIC_PREFIX_ORIGINAL_C1.json');begin=prefix[0]['start_seconds']
    common=read(OUT/'COMMON_RUN_INPUTS.json')
    freeze=read(OLD/'PLANNING_FREEZE.json')['source_freeze']
    manifest=read('D:/v42_may_joint_repair_campaign_20261013/CAMPAIGN_MANIFEST.json')
    mess=read(OLD/'M2/COMMON_M_PR222/FULL_MESS_PHYSICAL_ANCHOR.json')
    assert mess['plan_sha']==common['MESS_plan_sha']
    from v42_regcontrol import authority
    from v42_regcontrol.runner import background
    from v42_voltage_control.timecontrol import CommonClock,seconds
    from v42_voltage_control.integration import _equipment,measure_full_network,assert_control_inventory
    from v42_voltage_control.svr import install
    stamps=[datetime.fromtimestamp(begin+(j+1)*900,timezone(timedelta(hours=10))).isoformat() for j in range(96)]
    demand=[prefix[min(j,15)]['observations']['demand']['values']['demand_mw'] for j in range(96)]
    pv=[prefix[min(j,15)]['observations']['pv']['values']['pv_mw'] for j in range(96)]
    rows=[];settled=[]
    with no_native() as attempts,_validated_hardware_context(freeze,manifest) as scenario:
        source=authority.source();bg=background(stamps,demand,pv)
        from dayahead.v28r2.opendss_mapping import _set_load,_set_generator,mess_injection_mapping
        engine,adapter,_=authority.compile_verified()
        try:
            equipment=_equipment(engine);nodes={n.lower() for n in engine.Circuit.AllNodeNames() if n.rsplit('.',1)[-1] in {'1','2','3'}}
            native=source['NativeAllocation'].from_adapter(adapter);native.validate_native_engine(engine)
            svrs=install(engine,scenario['svr']);clock=CommonClock('ACTUAL','2025-05-01');clock.bind(engine)
            aliases,_=mess_service_bindings(source,mess['P_by_site'])
            for point in prefix:
                slot=point['slot'];native.apply(engine,bg,slot)
                for item in adapter['pv_generators']:
                    loc=(str(item['bus']).lower(),'ABC'[int(item['phase'])-1])
                    _set_generator(engine,item['generator_name'],bg.pv_generation_kw_96[slot].get(loc,0),0)
                for j in range(12):_set_load(engine,f'IDC_IDC{j+1:02d}',point['P'][j],point['Q'][j])
                for site,names in aliases.items():
                    inj=mess_injection_mapping(mess['P_by_site'][site][slot],mess['Q_by_site'][site][slot])
                    _set_generator(engine,names['generator'],inj['generator_p_kw'],inj['generator_q_kvar'])
                    _set_load(engine,names['load'],inj['charging_load_p_kw'],inj['charging_load_q_kvar'])
                def observe(event):
                    physical=measure_full_network(engine,nodes,equipment);hardware=svrs.measure()
                    assert_control_inventory(source['inventory'](engine),scenario)
                    low=min(physical['nodes'],key=lambda r:r['voltage_pu']);high=max(physical['nodes'],key=lambda r:r['voltage_pu'])
                    rows.append(dict(slot=slot,native_seconds=seconds(engine),event=event,
                        physical=physical,SVR=hardware,physical_sha=digest(physical),SVR_sha=digest(hardware),
                        lowest_node=low,highest_node=high,
                        PASS=bool(physical['PASS'] and hardware['hardware_PASS'] and hardware['added_nodes_voltage_PASS'])))
                clock.settle_slot(engine,slot,observer=observe)
                settled.append(dict(slot=slot,native_seconds=rows[-1]['native_seconds'],PASS=rows[-1]['PASS'],
                    voltage_min_pu=rows[-1]['physical']['voltage_min_pu'],voltage_max_pu=rows[-1]['physical']['voltage_max_pu']))
        finally:engine.Basic.ClearAll()
    _write(OUT/'ASOF_PREFIX_ALL_SUBSTEP_RAW.json',rows)
    bad=[r for r in rows if not r['PASS']]
    def compact(r):return {k:r[k] for k in ('slot','native_seconds','lowest_node','highest_node','physical_sha','SVR_sha','PASS')}|dict(
        kind=r['event']['kind'],voltage_min_pu=r['physical']['voltage_min_pu'],voltage_max_pu=r['physical']['voltage_max_pu'],
        voltage_violation_cells=r['physical']['voltage_violation_cells'],
        violations={k:v for k,v in r['physical'].items() if 'violation_cells' in k})
    first=None
    if bad:
        r=bad[0];i=rows.index(r)
        first=dict(step=compact(r),event=r['event'],SVR=r['SVR'],
            actual_PQ_and_observations=prefix[r['slot']],previous_slot_inputs=None if r['slot']==0 else prefix[r['slot']-1],
            previous_native_step=None if not i else compact(rows[i-1]))
    result=dict(status='PHYSICAL_FAIL_ASOF_SUBSTEPS' if bad else 'PASS_ASOF_SUBSTEPS',scope='C0_C1_EQUAL_ACTUAL_ASOF_AVERAGE_PQ_FIRST16_ALL_NATIVE_SUBSTEPS',
        same_actual_occupancy_as_driver=True,controller_future_observations_used=False,
        limits_unchanged=True,original_11SVR_7RegControl=True,physical_substeps=len(rows),violating_substeps=len(bad),
        min_voltage_pu=min(r['physical']['voltage_min_pu'] for r in rows),max_voltage_pu=max(r['physical']['voltage_max_pu'] for r in rows),
        first_violation=first,violating_step_summary=[compact(r) for r in bad],last_solve_per_slot=settled,
        settled_last_solve_all_PASS=all(r['PASS'] for r in settled),
        raw=file_record(OUT/'ASOF_PREFIX_ALL_SUBSTEP_RAW.json'),Native_calls=0,blocked_native_attempts=attempts,
        source=file_record(__file__),cannot_replace_asof_substep_failure_with_retrospective_settled_Fresh_PASS=True)
    _write(target,result)
    print(json.dumps({k:v for k,v in result.items() if k not in ('first_violation','violating_step_summary','last_solve_per_slot')},indent=2))

if __name__=='__main__':main()
