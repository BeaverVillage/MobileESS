"""Independent ledger, causal observation, original C1 and C0/C1 audit."""
from collections import Counter
from pathlib import Path
import argparse
import json
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from v42_integration.actual_validation import _power_model
from v42_integration.m_engine import _write,file_record
from v42_integration.unified_contract import digest
from v42_integration.isolated_unknown import no_native

RC=ROOT/'docs/v42_unified_aidc_mess_research_20261014/RELEASE_RECOVERY_20261015/RC01'
RAW=Path('D:/v42_may_joint_repair_campaign_20261013/raw/2025-05-01')

def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def differences(a,b,path=''):
    if isinstance(a,dict) and isinstance(b,dict):
        return sum((differences(a.get(k),b.get(k),path+'/'+k) for k in set(a)|set(b)),[])
    return [] if a==b else [path]

def observations(row,now):
    for key in ('demand','pv','weather'):
        x=row[key]
        assert x['observed_seconds']<=x['available_seconds']<=x['decision_seconds']<=now
        assert x['source_availability_checked'] is True and x['interpolation']=='NONE_ASOF_FORWARD_HOLD'

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--actual',type=Path,default=RC/'AIDC/REPLAY02');args=parser.parse_args()
    out=args.actual;target=out/'INDEPENDENT_ACTUAL_CERTIFICATE.json'
    if target.exists():raise FileExistsError('RELEASE_ACTUAL_AUDIT_MUST_NOT_OVERWRITE')
    common=read(out/'COMMON_RUN_INPUTS.json');done=read(out/'COMPARISON_COMPLETE.json')
    assert done['status']=='COMPARISON_COMPLETE' and done['release_case_sha']==common['release_case_sha']
    assert digest({k:v for k,v in common.items() if k!='release_case_sha'})==common['release_case_sha']
    assert common['unknown_policy_difference']=='OPTIONAL_AUTHORIZED_PENDING_PRESITE_ONLY'
    assert common['old_affine_not_safety_or_ranking_authority'] is True
    source=read(out/'EXECUTED_SOURCE.json');assert all(file_record(r['path'])==r for r in source['files'])
    assert all(file_record(r['path'])==r for r in common['observed_sources'])
    audit=common['historical_PR223_source'];begin=audit['evaluation_begin_seconds'];end=begin+16*900
    assert audit['classification']['initial_Known']==1624
    original=read(audit['original_initial']['path']);assert file_record(audit['original_initial']['path'])==audit['original_initial']
    plan=read(RAW/'PLANNING_INPUT_BUNDLE.json');power=read(RAW/'POWER_AUTHORITY.json')
    provenance=read(RAW/'SOURCE_PROVENANCE.json')
    private_source=file_record(provenance['archive']['path'])
    assert all(private_source[k]==provenance['archive'][k] for k in ('path','bytes','sha256'))
    raw_sources=[file_record(RAW/name) for name in ('PLANNING_INPUT_BUNDLE.json','ACTUAL_INPUT_BUNDLE.json',
        'SOURCE_PROVENANCE.json','POWER_AUTHORITY.json','NATIVE_INPUT_TEMPLATE_B1.json')]
    model,power_sources=_power_model(power,plan['capacities']);assert model.authority_sha==common['Original_C1_SHA']
    policies=[read(out/c/'FROZEN_POLICY.json') for c in ('C0','C1')]
    diff=differences(*policies)
    assert '/spec/variant' in diff and all(k in ('/spec/variant','/policy_sha','/sha') for k in diff),diff
    variants={};initials={};arrays={};all_starts={};current_hashes={}
    with no_native() as attempts:
        for label in ('C0','C1'):
            base=out/label;actual=read(base/'ACTUAL_RESULT.json');r=actual['receipt']
            assert actual['slots']==16 and actual['release_case_sha']==common['release_case_sha']
            assert all(r[k]==0 for k in ('capacity_violations','dropped_jobs','optimizer_calls','actual_global_reoptimization',
                'future_duration_controller_reads','future_completion_controller_reads'))
            assert r['actual_power_recomputed'] and not r['planning_power_copied']
            with np.load(base/'ACTUAL_GPU_PQ.npz',allow_pickle=False) as z:a={k:z[k].copy() for k in z.files}
            sites=tuple(map(str,a['sites']));assert sites==tuple(f'AIDC{j:02d}' for j in range(1,13))
            assert np.array_equal(a['slot_start_seconds'],begin+np.arange(16)*900)
            assert all(a[k].shape==(16,12) and np.isfinite(a[k]).all() for k in ('GPU','compute_GPU','IT_kw','PCC_P_kw','PCC_Q_kvar'))
            queue=read(base/'QUEUE_LEDGER.json');byuid={x['job_uid']:x for x in queue};assert len(queue)==len(byuid)==r['submitted_jobs']
            assert all(x['migration_count']==0 for x in queue)
            unknown={uid for uid,x in byuid.items() if x['origin_unknown']};assert len(queue)-len(unknown)==1624
            assert {x['uid'] for x in original['running']+original['pending']}==set(byuid)-unknown
            for initial in original['running']:
                job=byuid[initial['uid']]
                assert (job['site'],job['GPU_gang'],job['admitted_time'])==(initial['site'],initial['gpu'],initial['observed_start_seconds'])
            initials[label]=read(base/'INITIAL_PLACEMENT_LEDGER.json')
            assert {x['uid'] for x in initials[label]}==unknown and len(initials[label])==len(unknown)
            assert all(x['allowed'] and not x['preplace_permission_required'] and not x['sensitivity_used'] and not x['GPU_registered'] for x in initials[label])
            starts=read(base/'ACTUAL_START_LEDGER.json');u_starts=[x for x in starts if x['origin_unknown']]
            assert len({x['uid'] for x in starts})==len(starts) and all(x['atomic_AC_rechecked'] for x in starts)
            debit=read(base/'CC4_DEPLETION_LEDGER.json');assert len(debit)==len(unknown) and {x['uid'] for x in debit}==unknown
            prefix=read(base/'PUBLIC_PREFIX_ORIGINAL_C1.json');assert len(prefix)==16
            for t,row in enumerate(prefix):
                assert row['slot']==t and row['start_seconds']==begin+t*900 and row['end_seconds']==begin+(t+1)*900
                observations(row['observations'],row['start_seconds'])
            weather=[row['observations']['weather']['values'] for row in prefix]
            expected=model.recompute(a['GPU'],sites,weather)
            errors={k:float(np.max(np.abs(expected[k]-a[k]))) for k in ('IT_kw','PCC_P_kw','PCC_Q_kvar')}
            assert max(errors.values())<1e-8
            # Independent integration from final public observed job ledger.
            integrated=np.zeros((16,12))
            for job in queue:
                start=job['admitted_time'];finish=job['completion_observed_time']
                if start is None:continue
                assert finish is None or finish<=end
                for t in range(16):
                    b=begin+t*900;e=b+900
                    overlap=max(0.,min(e,end if finish is None else finish)-max(b,start))
                    if overlap:integrated[t,sites.index(job['site'])]+=job['GPU_gang']*overlap/900
            gpu_error=float(np.max(np.abs(integrated-a['GPU'])));assert gpu_error<1e-8
            caps=np.array([plan['capacities'][s] for s in sites]);assert np.max(a['GPU']-caps)<1e-8
            proofs=read(base/'CURRENT_CANDIDATE_AC_LEDGER.json');keys={(x['uid'],x['time_seconds']) for x in proofs if x['PASS']}
            for x in starts:assert (x['uid'],x['time_seconds']) in keys
            started=[x['uid'] for x in original['running']]
            atomic_error=0.
            for event in starts:
                now=event['time_seconds'];instant=np.zeros(12)
                for uid in started:
                    job=byuid[uid];finish=job['completion_observed_time']
                    if finish is None or finish>now:instant[sites.index(job['site'])]+=job['GPU_gang']
                instant[sites.index(event['site'])]+=event['GPU']
                matches=[x for x in proofs if x['uid']==event['uid'] and x['time_seconds']==now and x['PASS']
                    and np.allclose(x['candidate_GPU'],instant,rtol=0,atol=1e-9)]
                assert matches,('ATOMIC_WHOLE_GANG_CURRENT_AC_PROOF_MISSING',label,event['uid'],now)
                proof=matches[-1]
                check=model.recompute(instant[None,:],sites,[proof['exogenous_receipt']['weather']['values']])
                atomic_error=max(atomic_error,float(np.max(np.abs(check['PCC_P_kw'][0]-proof['candidate_P']))),
                    float(np.max(np.abs(check['PCC_Q_kvar'][0]-proof['candidate_Q']))))
                started.append(event['uid'])
            assert atomic_error<1e-8
            current=[];past_steps={}
            for x in proofs:
                observations(x['exogenous_receipt'],x['time_seconds'])
                assert x['future_Actual_or_Tap_or_Completion_reads']==0 and x['current_candidate_added']
                assert x['baseline_PASS_is_candidate_authority'] is False
                if x['status']=='NOT_CERTIFIED':continue
                assert x['future_native_Tap_actions_executed']==0
                assert x['SVR_count']==11 and x['original_RegControl']==7
                for prior in x['physical_steps'][:-1]:
                    past_steps[(prior['native_seconds'],prior['physical_sha'],prior['SVR_sha'])]=prior
                step=x['physical_steps'][-1];current.append(step)
                assert step['native_seconds']==x['time_seconds']-begin
                assert all(z['absolute_seconds']>step['native_seconds'] for z in x['future_queue_not_executed'])
                assert step['checked_nodes']==419 and step['checked_current_rows']==832
            candidates=read(base/'PENDING_PRE_SITE_LEDGER.json');reasons=Counter();last={}
            for event in candidates:
                last[event['uid']]=event
                assert event['future_private_reads']==0 and event['presite_failed_does_not_fail_initial']
                assert event['candidates'][0]['kind']=='STAY'
                for candidate in event['candidates']:
                    if candidate['reason']:reasons[candidate['reason']]+=1
            changed=[x for x in u_starts if x['site']!=x['basic_site']]
            for x in changed:
                events=[z for z in candidates if z['uid']==x['uid'] and z['time_seconds']==x['time_seconds']]
                assert label=='C1' and len(events)==1
                chosen=next(z for z in events[0]['candidates'] if z['site']==x['site'])
                assert chosen['kind']=='PRE_SITE' and chosen['feasible']
            qos=read(base/'QOS_ACTUAL_LEDGER.json')
            assert all(x['total_intentional_burden_seconds']<=x['budget_seconds']+1e-9 for x in qos)
            assert all(x['intentional_start_delay_seconds']==0 and x['migration_interruption_seconds']==0 for x in qos)
            corrective=read(base/'KNOWN_CORRECTIVE_PREPLACEMENT.json')
            assert all(x['planning_command_modified'] is False for x in corrective)
            times=[x['wall_seconds'] for x in read(base/'CONTROL_TICK_TIMINGS.json')]
            assert len(times)==16 and max(times)<900
            last_reasons=Counter((e['candidates'][0]['reason'] or 'BASIC_STAY_LEGAL') for e in last.values() if e['chosen_site'] is None)
            variants[label]=dict(status='PASS_DIAGNOSTIC_FIRST16',Unknown_arrived_UIDs=len(unknown),
                Unknown_initial_placed_UIDs=len(initials[label]),Unknown_started_UIDs=len(u_starts),
                Unknown_started_UID_list=[x['uid'] for x in u_starts],PreSite_changed_UIDs=len(changed),PreSite_changed_UID_list=[x['uid'] for x in changed],
                changed_GPUh=actual['changed_GPUh'],Unknown_STAY_started_UIDs=len(u_starts)-len(changed),
                Unknown_unstarted_UIDs=len(unknown)-len(u_starts),PreSite_candidate_UIDs=actual['PreSite_candidate_UIDs'],
                Unknown_control_evaluated_UIDs=len(last),Unknown_not_yet_control_evaluated_UIDs=len(unknown-set(last)),
                initial_authority_rejected_UIDs=sum(not x['allowed'] for x in initials[label]),
                PreSite_source_permission_UIDs=sum(x['can_prestart_place'] is True for x in initials[label]),
                authorized_ready_alternative_UIDs=actual['authorized_ready_alternative_UIDs'],
                GPU_integral_max_error=gpu_error,Original_C1_recompute_error=errors,
                atomic_candidate_instant_GPU_and_PQ_replay_PASS=True,atomic_candidate_PQ_max_error=atomic_error,
                candidate_rejection_events=dict(reasons),unstarted_latest_evaluated_STAY_reasons=dict(last_reasons),
                current_candidate_min_voltage_pu=min(x['voltage_min_pu'] for x in current),
                current_candidate_max_voltage_pu=max(x['voltage_max_pu'] for x in current),
                current_candidate_max_phase_line_loading=max(x['maximum_phase_line_loading'] for x in current),
                current_candidate_physical_failures=sum(not x['PASS'] for x in current),
                observed_prefix_physical_fail_receipts=sum(x.get('historical_prefix_physical_PASS') is False for x in proofs),
                observed_prefix_unique_checked_substeps=len(past_steps),
                observed_prefix_substep_voltage_min=min(x['voltage_min_pu'] for x in past_steps.values()),
                observed_prefix_substep_voltage_max=max(x['voltage_max_pu'] for x in past_steps.values()),
                observed_prefix_substep_max_phase_line_loading=max(x['maximum_phase_line_loading'] for x in past_steps.values()),
                current_candidate_resource_not_certified=sum(x['status']=='NOT_CERTIFIED' for x in proofs),
                controller_P50_seconds=float(np.percentile(times,50)),controller_P95_seconds=float(np.percentile(times,95)),
                controller_max_seconds=max(times),controller_900_seconds_PASS=True,
                Known_corrective_command_UIDs=len({x['uid'] for x in corrective if x.get('command_type')=='ACTUAL_CORRECTIVE_COMMAND'}),
                QoS_intentional_budget_violations=0,
                QoS_latest_start_excess_UIDs=sum(x['latest_start_excess_seconds']>0 for x in qos),
                QoS_completion_deadline_excess_UIDs=sum((x['actual_completion_deadline_excess_seconds'] or 0)>0 for x in qos),
                capacity_violations=0,private_future_controller_reads=0,Native_calls=0)
            arrays[label]=a;all_starts[label]=starts
            current_hashes[label]={x['input_sha']:(x['physical_steps'][-1]['physical_sha'],x['physical_steps'][-1]['SVR_sha'])
                for x in proofs if x.get('physical_steps')}
    assert initials['C0']==initials['C1']
    delta={k:float(np.max(np.abs(arrays['C1'][k]-arrays['C0'][k]))) for k in ('GPU','compute_GPU','IT_kw','PCC_P_kw','PCC_Q_kvar')}
    if not any(delta.values()):
        assert all_starts['C0']==all_starts['C1']
        assert current_hashes['C0']==current_hashes['C1']
    report=dict(status='PASS',scope='RC01_DIAGNOSTIC_SHARED_BASIC_INITIAL_OPTIONAL_PENDING_PRESITE_FIRST16',
        release_case_sha=common['release_case_sha'],initial_state_sha=audit['initial_semantic_sha'],
        old_ranking_only_result_preserved=True,new_D0_full_chain=False,Full96='NOT_RUN',
        actual_executed_source_byte_identical=True,executed_source=source,policy_differences=sorted(diff),
        common_initial_placement_ledger_identical=True,variants=variants,C1_minus_C0_max_abs_arrays=delta,
        instantaneous_start_ledgers_identical=all_starts['C0']==all_starts['C1'],
        same_input_current_full_physical_and_SVR_hash_maps_identical=current_hashes['C0']==current_hashes['C1'],
        same_arrays_imply_same_offline_Fresh_inputs=not any(delta.values()),Original_C1_sources=power_sources,
        shared_raw_inputs=raw_sources,private_Runtime_source=private_source,private_Runtime_used_only_by_simulator=True,
        Native_calls=0,blocked_native_attempts=attempts)
    report['certificate_sha']=digest(report);_write(target,report)
    print(json.dumps(dict(status=report['status'],variants=variants,arrays_delta=delta),indent=2))

if __name__=='__main__':main()
