"""Independent Source, ranking-only, resource and Original C1 replay gates."""
from pathlib import Path
import json
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from v42_integration.m_engine import file_record,_write
from v42_integration.unified_contract import digest
from v42_integration.actual_validation import _weather,_power_model

OUT=ROOT/'docs/v42_unified_aidc_mess_research_20261014/ISOLATED_UNKNOWN_C0_C1_20261015'
RAW=Path('D:/v42_may_joint_repair_campaign_20261013/raw/2025-05-01')


def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def main():
    target=OUT/'C0_C1_COMMON_INPUT_CERTIFICATE.json'
    if target.exists():raise FileExistsError('ISOLATED_COMMON_CERTIFICATE_MUST_NOT_OVERWRITE')
    common=read(OUT/'COMMON_RUN_INPUTS.json');done=read(OUT/'COMPARISON_COMPLETE.json')
    baseline=read(OUT/'BASELINE_SOURCE_AND_CASE_AUDIT.json')
    prepared=read(OUT/'PR223_DIAGNOSTIC_PREPARED_SOURCE.json')
    assert done['status']=='EXECUTED' and done['real_16_slot_replay'] is True
    assert common['public_Known']==1624 and common['future_Unknown']==696
    assert common['diagnostic_case_sha']==digest(prepared)
    assert common['initial_semantic_sha']==baseline['initial_semantic_sha']
    assert common['fixed_MESS_plan_sha']==baseline['fixed_MESS_plan_sha']
    snapshots=[read(OUT/c/'FROZEN_POLICY.json') for c in ('C0','C1')]
    # Policy format is the unchanged signed-policy serializer: compare every
    # field except the explicit ranking and its derived policy hash.
    def differences(a,b,path=''):
        if isinstance(a,dict) and isinstance(b,dict):
            return sum((differences(a.get(k),b.get(k),path+'/'+k) for k in set(a)|set(b)),[])
        return [] if a==b else [path]
    diff=differences(snapshots[0],snapshots[1])
    allowed={'/policy_sha','/sha','/spec/sha','/spec/policy_sha','/spec/ranking_variant','/ranking_variant'}
    assert any(p.endswith('/ranking_variant') for p in diff),diff
    assert all(p in allowed for p in diff),diff
    code=read(OUT/'ISOLATED_EXECUTED_CODE_SOURCE.json')
    assert all(file_record(r['path'])==r for r in code['files'])
    raw_sources=[file_record(RAW/n) for n in ('PLANNING_INPUT_BUNDLE.json',
        'ACTUAL_INPUT_BUNDLE.json','SOURCE_PROVENANCE.json','POWER_AUTHORITY.json','NATIVE_INPUT_TEMPLATE_B1.json')]
    plan=read(RAW/'PLANNING_INPUT_BUNDLE.json');power=read(RAW/'POWER_AUTHORITY.json')
    provenance=read(RAW/'SOURCE_PROVENANCE.json');start=baseline['evaluation_begin_seconds']
    actual_source=read(RAW/'ACTUAL_INPUT_BUNDLE.json')
    exogenous=[]
    for expected in actual_source['realized_inputs']['authority'].values():
        actual_record=file_record(expected['path'])
        assert Path(actual_record['path']).resolve()==Path(expected['path']).resolve()
        assert all(actual_record[k]==expected[k] for k in ('bytes','sha256'))
        exogenous.append(dict(declared_path=expected['path'],resolved_file=actual_record,
            declared_and_resolved_same_file=True))
    weather,weather_receipt=_weather(provenance,start,start+14400)
    model,power_sources=_power_model(power,plan['capacities'])
    assert model.authority_sha==common['Original_C1']
    replay={};events={};arrays={}
    for label in ('C0','C1'):
        base=OUT/label;actual=read(base/'ACTUAL_RESULT.json');r=actual['receipt']
        assert actual['slots']==16 and actual['diagnostic_case_sha']==common['diagnostic_case_sha']
        for key in ('capacity_violations','dropped_jobs','optimizer_calls','actual_global_reoptimization',
                    'future_duration_controller_reads','future_completion_controller_reads'):
            assert r[key]==0,(label,key,r[key])
        assert r['actual_power_recomputed'] is True and r['planning_power_copied'] is False
        with np.load(base/'ACTUAL_GPU_PQ.npz',allow_pickle=False) as packet:
            a={k:packet[k].copy() for k in packet.files}
        sites=list(map(str,a['sites']));assert sites==[f'AIDC{i:02d}' for i in range(1,13)]
        assert np.array_equal(a['slot_start_seconds'],start+np.arange(16)*900)
        assert all(a[k].shape==(16,12) and np.isfinite(a[k]).all() for k in ('GPU','compute_GPU','IT_kw','PCC_P_kw','PCC_Q_kvar'))
        caps=np.array([plan['capacities'][s] for s in sites]);assert np.max(a['GPU']-caps)<=1e-7
        # This invokes only the original frozen C1 equation on actual measured
        # occupancy and time-matched realized weather, without the event policy.
        expected=model.recompute(a['GPU'],sites,weather)
        error={k:float(np.max(np.abs(a[k]-expected[k]))) for k in ('IT_kw','PCC_P_kw','PCC_Q_kvar')}
        assert max(error.values())<=1e-8,error
        queue=read(base/'QUEUE_LEDGER.json');uids=[x['job_uid'] for x in queue]
        assert len(uids)==len(set(uids))==r['submitted_jobs']
        assert sum(not x['origin_unknown'] for x in queue)==1624
        debit=read(base/'CC4_DEPLETION_LEDGER.json');duids=[x['uid'] for x in debit]
        unknown={x['job_uid'] for x in queue if x['origin_unknown']}
        assert len(duids)==len(set(duids)) and set(duids)==unknown
        ledger=read(base/'KNOWN_REFERENCE_AND_CORRECTIVE_LEDGER.json')
        assert ledger['historical_planning_commands_sha']==common['historical_Known_commands_sha']
        assert ledger['exact_optimized_Known_execution_claim'] is False and ledger['new_D0_plan_used'] is False
        events[label]={(e['uid'],e['time_seconds']):e for e in read(base/'UNKNOWN_CANDIDATE_LEDGER.json')}
        replay[label]=dict(status='PASS',slots=16,submitted_UIDs=len(uids),initial_Known_UIDs=1624,
            actual_Unknown_submissions=len(unknown),forecast_UIDs_debited_once=len(duids),
            Original_C1_recompute_max_error=error,actual_arrays=file_record(base/'ACTUAL_GPU_PQ.npz'),
            capacity_violation=0,dropped_jobs=0,private_future_controller_reads=0,Global_MILP_calls=0)
        arrays[label]=a
    assert common['all_STA_MESS_grid_controls_preserved'] is True
    assert common['fixed_MESS_grid_controls_sha']
    equal_state=0;equal_candidates=0
    for key in events['C0'].keys()&events['C1'].keys():
        left,right=events['C0'][key],events['C1'][key]
        if left['observed_GPU_by_site']==right['observed_GPU_by_site']:
            equal_state+=1
            assert left['candidate_set_sha']==right['candidate_set_sha'],key
            equal_candidates+=1
    private_record=file_record(provenance['archive']['path'])
    assert all(private_record[k]==provenance['archive'][k] for k in ('path','bytes','sha256'))
    report=dict(schema='ISOLATED_UNKNOWN_COMMON_INPUT_AND_REPLAY_CERTIFICATE_V1',status='PASS',
        scope='FIXED_PR223_M2_REAL_FIRST16_UNKNOWN_RANKING_DIAGNOSTIC_ONLY',
        diagnostic_case_sha=common['diagnostic_case_sha'],common_inputs=common,policy_differences=diff,
        candidate_algorithm_same=True,same_state_candidate_events=equal_state,
        same_state_equal_candidate_events=equal_candidates,
        candidate_equality_applies_to_equal_observed_state=True,
        same_900_second_engine_and_Known_reference=True,same_signed_Known_corrective_algorithm=True,
        private_Runtime_source=private_record,private_Runtime_exposed_to_controller=False,
        shared_Raw_input_sources=raw_sources,shared_realized_exogenous_sources=exogenous,
        executed_source_records=code['files'],executed_source_byte_identical_after_replay=True,
        realized_weather=weather_receipt,Original_C1_sources=power_sources,
        fixed_MESS_routes_PQ_SOC=True,initial_state_changed=False,CC4_or_QoS_changed=False,
        variants=replay,Gate1='PASS',Gate2='PASS',Gate3='AFFINE_AVAILABLE_FRESH_PENDING',
        old_Full96_or_D0_optimization_performance_transferred=False,Gurobi_Native_calls=0)
    report['certificate_sha']=digest(report)
    _write(target,report)
    print(json.dumps(dict(status='PASS',policy_differences=diff,same_state_candidates=equal_candidates,
        replay=replay),indent=2))


if __name__=='__main__':main()
