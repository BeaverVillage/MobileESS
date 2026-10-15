"""Independent same-input current AC crosscheck after measured Actual.

Rebuild candidate instantaneous GPU from public start/completion ledgers and
past interval P/Q from public occupancy, then use original grid/clock helpers.
Past replay retains every native solve and due-event check. Past physical
proofs are separately retained in the full candidate ledger. This crosscheck
measures and saves all current nodes/currents rather than an affine estimate.
"""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import json
import sys
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from v42_integration.actual_validation import read,_power_model,_validated_hardware_context,mess_service_bindings
from v42_integration.m_engine import _write,file_record
from v42_integration.unified_contract import digest
from v42_integration.isolated_unknown import no_native

OUT=ROOT/'docs/v42_unified_aidc_mess_research_20261014/RELEASE_RECOVERY_20261015/RC01/AIDC/REPLAY02'
RAW=Path('D:/v42_may_joint_repair_campaign_20261013/raw/2025-05-01')
OLD=Path('D:/v42_integration_validation_20261013/DDAY_V5_B3_FINAL_ATTEMPT01/B3')

def main():
    target=OUT/'CURRENT_SAME_INPUT_AC_CROSSCHECK.json'
    if target.exists():raise FileExistsError('CURRENT_AC_CROSSCHECK_MUST_NOT_OVERWRITE')
    gate=read(OUT/'INDEPENDENT_ACTUAL_CERTIFICATE.json');assert gate['status']=='PASS'
    common=read(OUT/'COMMON_RUN_INPUTS.json');base=OUT/'C0'
    starts=read(base/'ACTUAL_START_LEDGER.json');unknown=[x for x in starts if x['origin_unknown']]
    assert unknown
    chosen=[starts[0],unknown[0],unknown[-1]]
    queue={x['job_uid']:x for x in read(base/'QUEUE_LEDGER.json')}
    source_initial=read(common['historical_PR223_source']['original_initial']['path'])
    prefix=read(base/'PUBLIC_PREFIX_ORIGINAL_C1.json');proofs=read(base/'CURRENT_CANDIDATE_AC_LEDGER.json')
    model,_=_power_model(read(RAW/'POWER_AUTHORITY.json'),read(RAW/'PLANNING_INPUT_BUNDLE.json')['capacities'])
    sites=tuple(f'AIDC{j:02d}' for j in range(1,13));begin=prefix[0]['start_seconds']
    freeze=read(OLD/'PLANNING_FREEZE.json')['source_freeze']
    manifest=read('D:/v42_may_joint_repair_campaign_20261013/CAMPAIGN_MANIFEST.json')
    mess=read(OLD/'M2/COMMON_M_PR222/FULL_MESS_PHYSICAL_ANCHOR.json');assert mess['plan_sha']==common['MESS_plan_sha']
    from v42_regcontrol import authority
    from v42_regcontrol.runner import background
    from v42_voltage_control.timecontrol import CommonClock,queue as native_queue,seconds
    from v42_voltage_control.integration import _equipment,measure_full_network,assert_control_inventory
    from v42_voltage_control.svr import install
    from dayahead.v28r2.opendss_mapping import _set_load,_set_generator,mess_injection_mapping
    results=[]
    with no_native() as attempts,_validated_hardware_context(freeze,manifest) as scenario:
        source=authority.source()
        for event in chosen:
            now=event['time_seconds'];t=int((now-begin)/900);instant=np.zeros(12)
            preceding=starts[:starts.index(event)+1]
            uids=[r['uid'] for r in source_initial['running']]+[r['uid'] for r in preceding]
            for uid in uids:
                job=queue[uid]
                if job['completion_observed_time'] is None or job['completion_observed_time']>now:
                    instant[sites.index(job['site'])]+=job['GPU_gang']
            candidates=[r for r in proofs if r['uid']==event['uid'] and r['time_seconds']==now and r['PASS']
                and np.allclose(r['candidate_GPU'],instant,rtol=0,atol=1e-9)]
            assert candidates;expected=candidates[-1];obs=expected['exogenous_receipt']
            physical_power=model.recompute(instant[None,:],sites,[obs['weather']['values']])
            current=dict(slot=t,P=physical_power['PCC_P_kw'][0],Q=physical_power['PCC_Q_kvar'][0],observations=obs)
            rows=[*prefix[:t],current]
            stamps=[datetime.fromtimestamp(begin+(j+1)*900,timezone(timedelta(hours=10))).isoformat() for j in range(96)]
            bg=background(stamps,[rows[j if j<len(rows) else -1]['observations']['demand']['values']['demand_mw'] for j in range(96)],
                [rows[j if j<len(rows) else -1]['observations']['pv']['values']['pv_mw'] for j in range(96)])
            engine,adapter,_=authority.compile_verified()
            try:
                equipment=_equipment(engine);nodes={n.lower() for n in engine.Circuit.AllNodeNames() if n.rsplit('.',1)[-1] in {'1','2','3'}}
                native=source['NativeAllocation'].from_adapter(adapter);native.validate_native_engine(engine)
                svrs=install(engine,scenario['svr']);clock=CommonClock('ACTUAL','2025-05-01');clock.bind(engine)
                aliases,_=mess_service_bindings(source,mess['P_by_site'])
                def apply(row):
                    slot=row['slot'];native.apply(engine,bg,slot)
                    for item in adapter['pv_generators']:
                        loc=(str(item['bus']).lower(),'ABC'[int(item['phase'])-1])
                        _set_generator(engine,item['generator_name'],bg.pv_generation_kw_96[slot].get(loc,0),0)
                    for j in range(12):_set_load(engine,f'IDC_IDC{j+1:02d}',row['P'][j],row['Q'][j])
                    for site,names in aliases.items():
                        inj=mess_injection_mapping(mess['P_by_site'][site][slot],mess['Q_by_site'][site][slot])
                        _set_generator(engine,names['generator'],inj['generator_p_kw'],inj['generator_q_kvar'])
                        _set_load(engine,names['load'],inj['charging_load_p_kw'],inj['charging_load_q_kvar'])
                for past in prefix[:t]:apply(past);clock.settle_slot(engine,past['slot'],capture_events=False)
                apply(current);assert seconds(engine)==t*900;engine.Solution.SolveSnap()
                assert engine.Solution.Converged() and engine.Solution.ControlActionsDone()
                assert all(r['absolute_seconds']>t*900 for r in native_queue(engine))
                assert_control_inventory(source['inventory'](engine),scenario)
                physical=measure_full_network(engine,nodes,equipment);hardware=svrs.measure()
                assert physical['PASS'] and hardware['hardware_PASS'] and hardware['added_nodes_voltage_PASS']
                reference=expected['physical_steps'][-1]
                assert digest(physical)==reference['physical_sha'] and digest(hardware)==reference['SVR_sha']
                results.append(dict(uid=event['uid'],time_seconds=now,input_sha=expected['input_sha'],instant_GPU=instant.tolist(),
                    candidate_P=current['P'].tolist(),candidate_Q=current['Q'].tolist(),physical=physical,SVR=hardware,
                    native_seconds=seconds(engine),future_pending_queue=native_queue(engine),
                    same_full_physical_SHA_and_SVR_SHA=True,independently_reconstructed_occupancy=True))
            finally:engine.Basic.ClearAll()
    result=dict(status='PASS_SAME_CURRENT_INPUT_ORIGINAL_AC',scope='FIRST_KNOWN_FIRST_AND_LAST_UNKNOWN_START_C0',
        real_selected_current_candidates=len(results),independent_raw_current_nodes_and_currents_saved=True,
        prior_prefix_solves_or_due_action_checks_skipped=False,past_full_physical_proofs='CURRENT_CANDIDATE_AC_LEDGER.json',
        future_Tap_actions_executed=0,Native_calls=0,blocked_native_attempts=attempts,
        source=file_record(__file__),results=results)
    _write(target,result);print(json.dumps({k:v for k,v in result.items() if k!='results'},indent=2))

if __name__=='__main__':main()
