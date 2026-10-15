"""Read-only ordered funnel and settled certificates for completed RC03 cases.

The executing attempt's check order is preserved. GPU/Rack is independently
reconstructed at each exact public serial prefix. A later stage with no raw
evaluation remains NOT_EVALUATED; assumptions never become Source facts.
"""
from collections import Counter,defaultdict
import argparse
import csv
import gc
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from v42_integration.actual_validation import read,record
from v42_integration.policy import digest
from v42_integration.rc02_voltage_audit import write_new
from v42_integration.release_ac_contract import validate_settled_fresh

RAW=Path('D:/v42_may_joint_repair_campaign_20261013/raw/2025-05-01')
STAGES=('Compatibility','GPU_Rack','Data','QoS','AC','Sensitivity')
HARD={'SOURCE_RELEASE_WINDOW','SOURCE_REPRESENTATION_WINDOW','SOURCE_LATEST_START_WINDOW',
      'SOURCE_COMPLETION_DEADLINE','SOURCE_PUBLIC_Q50_COMPLETION_DEADLINE',
      'ORIGINAL_QOS_HAS_NO_PREPARATION_DELAY_AUTHORITY','UNCHANGED_ORIGINAL_QOS_RECEIPT_REQUIRED'}


def observed_GPU(queue,uid,now,sites):
    current=queue[uid];key=(current['submit_time'],uid);use=dict.fromkeys(sites,0)
    for other,r in queue.items():
        start=r['admitted_time'];done=r['completion_observed_time']
        if other==uid or start is None or start>now or done is not None and done<=now:continue
        if start==now and (r['submit_time'],other)>=key:continue
        use[r['site']]+=r['GPU_gang']
    return use


def raw_stages(row):
    if row['kind']=='STAY':data='NOT_REQUIRED';qos='FAIL' if row.get('reason') in HARD else 'PASS'
    else:
        p=row.get('research_data_contract')
        if p is None:data=qos='NOT_EVALUATED'
        elif p.get('eligible') is not True:data='FAIL';qos='NOT_EVALUATED'
        elif p.get('reason') in HARD:data='PASS_ASSUMED';qos='FAIL'
        elif p.get('ready_at_seconds') is None or p.get('status')=='REJECTED':data='FAIL';qos='NOT_EVALUATED'
        else:data='PASS_ASSUMED';qos='PASS'
        if row.get('reason') in HARD:qos='FAIL'
    ac='NOT_EVALUATED' if row.get('candidate_AC_input_sha') is None else 'PASS' if row['physical']['PASS'] else 'FAIL'
    score=row.get('sensitivity_score')
    sensitivity='NOT_EVALUATED' if score is None else 'PASS' if score.get('status')=='PASS' else 'NOT_CERTIFIED'
    return dict(Data=data,QoS=qos,AC=ac,Sensitivity=sensitivity)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--case',required=True,type=Path)
    parser.add_argument('--name',default='FUNNEL_AUDIT01');args=parser.parse_args();case=args.case
    out=case/args.name
    if out.exists():raise FileExistsError('RC03_FUNNEL_AND_CERTIFICATE_MUST_NOT_OVERWRITE')
    complete=read(case/'COMPARISON_COMPLETE.json');assert complete['status']=='COMPARISON_COMPLETE'
    common=read(case/'COMMON_RUN_INPUTS.json');executed=read(case/'EXECUTED_SOURCE.json')
    for r in executed['files']:
        if record(r['path'])!=r:raise ValueError('RC03_EXECUTED_SOURCE_BYTES_DRIFT')
    native=read(RAW/'NATIVE_INPUT_TEMPLATE_B1.json');actual=read(RAW/'ACTUAL_INPUT_BUNDLE.json')
    source={str(r['job_uid']):r for r in actual['post_issue_arrivals']};capacities=native['capacities']
    racks={s:max(r['compatibility_GPU_limit'] for r in native['racks'] if r['aidc_id']==s) for s in capacities}
    out.mkdir();result=dict(scope='READ_ONLY_RECONSTRUCTED_SERIAL_PUBLIC_GPU_AND_RAW_LOGICAL_FUNNEL',
        release_case_sha=common['release_case_sha'],research_science_sha=common['research_science_sha'],
        original_execution_order_unchanged=True,ordered_funnel='Compatibility→GPU/Rack→data→QoS→AC→sensitivity',
        no_not_evaluated_filled_as_PASS=True,posthoc_GPU_is_not_new_execution=True,
        research_data_provenance='ASSUMED_NOT_CUSTOMER_PERMISSION_NOT_MEASURED_WAN',variants={},certificates={},
        Native_calls=0,Actual_calls=0,AC_calls=0,full96_claim=False,new_D0_full_chain=False)
    sources=[record(__file__),record(case/'COMMON_RUN_INPUTS.json'),record(case/'COMPARISON_COMPLETE.json'),
        record(RAW/'NATIVE_INPUT_TEMPLATE_B1.json'),record(RAW/'ACTUAL_INPUT_BUNDLE.json')]
    for label in ('C0','C1'):
        folder=case/label;events=read(folder/'PENDING_PRE_SITE_LEDGER.json')
        queue={r['job_uid']:r for r in read(folder/'QUEUE_LEDGER.json')}
        metrics=read(folder/'ACTUAL_RESULT.json');counts=Counter();uids=defaultdict(set);checks=0
        memo={};fields=['uid','time_seconds','site','kind','source_submit_seconds','gpu','observed_GPU_at_site',
            'capacity','rack_limit',*STAGES,'raw_Data','raw_QoS','raw_AC','raw_Sensitivity',
            'raw_reason','candidate_AC_input_sha','chosen_site','serial_prefix_sha']
        with (out/(label+'_CANDIDATE_FUNNEL.csv')).open('w',encoding='utf-8',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
            for event in events:
                uid=event['uid'];now=event['time_seconds'];q=queue[uid];r=source[uid]
                key=(uid,now)
                if key not in memo:memo[key]=observed_GPU(queue,uid,now,capacities)
                use=memo[key];gpu=q['GPU_gang']
                if q['submit_time']>now:raise ValueError('FUNNEL_REQUEST_WAS_NOT_YET_OBSERVED')
                for candidate in event['candidates']:
                    site=candidate['site'];gpu_ok=use[site]+gpu<=capacities[site] and gpu<=racks[site]
                    status=dict(Compatibility='PASS' if site in r['compatible_sites'] else 'FAIL',
                        GPU_Rack='PASS' if gpu_ok else 'FAIL',**raw_stages(candidate))
                    if candidate.get('reason')=='CURRENT_GPU_CAPACITY' and use[site]+gpu<=capacities[site]:
                        raise ValueError('FUNNEL_EXACT_SERIAL_GPU_DISAGREES_WITH_RAW_CAPACITY_REJECTION')
                    if candidate.get('candidate_AC_input_sha') and not gpu_ok:
                        raise ValueError('FUNNEL_RAW_AC_PASSED_GPU_BUT_RECONSTRUCTED_GPU_FAILED')
                    checks+=1;raw=dict(status);path=True
                    for stage in STAGES:
                        if not path:status[stage]='NOT_EVALUATED'
                        if status[stage] not in ('PASS','PASS_ASSUMED','NOT_REQUIRED'):path=False
                        prefix='PRE_SITE:' if candidate['kind']=='PRE_SITE' else 'STAY:'
                        counts[prefix+stage+':'+status[stage]]+=1
                        if status[stage] in ('PASS','PASS_ASSUMED','NOT_REQUIRED'):uids[prefix+stage].add(uid)
                    writer.writerow(dict(uid=uid,time_seconds=now,site=site,kind=candidate['kind'],
                        source_submit_seconds=q['submit_time'],gpu=gpu,observed_GPU_at_site=use[site],capacity=capacities[site],
                        rack_limit=racks[site],**status,**{'raw_'+k:raw[k] for k in ('Data','QoS','AC','Sensitivity')},
                        raw_reason=candidate.get('reason'),candidate_AC_input_sha=candidate.get('candidate_AC_input_sha'),
                        chosen_site=event['chosen_site'],serial_prefix_sha=digest(dict(uid=uid,now=now,observed_GPU=use))))
        result['variants'][label]=dict(Unknown_submitted_UIDs=metrics['Unknown_submitted_UIDs'],
            Unknown_initial_placed_UIDs=metrics['Unknown_initial_placed_UIDs'],
            evaluated_pending_UIDs=len({r['uid'] for r in events}),candidate_event_count=checks,
            ordered_candidate_counts=dict(counts),ordered_unique_UIDs={k:len(v) for k,v in uids.items()},
            Unknown_started_UIDs=metrics['Unknown_started_UIDs'],PreSite_changed_UIDs=metrics['PreSite_changed_UIDs'],
            changed_GPUh=metrics['changed_GPUh'],common_contract_eligibility_is_not_C0_action_off_evaluation_count=True,
            exact_serial_GPU_checked_against_all_raw_AC_and_capacity_branches=True)
        fresh_path=folder/'OFFLINE_FRESH_16/FRESH_PHYSICAL_RESULT.json'
        rows_path=folder/'OFFLINE_FRESH_16/FRESH_PHYSICAL_SLOTS.json'
        receipt=read(fresh_path);rows=read(rows_path)
        trace=receipt['actual_power_trace']
        if record(trace['path'])!=trace:raise ValueError('RC03_FRESH_TRACE_BYTES_DRIFT')
        certificate=validate_settled_fresh(receipt,rows,day='2025-05-01',case_sha=common['release_case_sha'],
            initial_state_sha=common['historical_PR223_source']['initial_semantic_sha'],
            mess_plan_sha=common['MESS_plan_sha'],trace_record=trace,slots=16)
        result['certificates'][label]=certificate
        result['variants'][label]['QoS']=dict(intentional_burden_violation_UIDs=sum(
            r['total_intentional_burden_seconds']>r['budget_seconds']+1e-7 for r in read(folder/'QOS_ACTUAL_LEDGER.json')),
            latest_start_excess_includes_unavoidable_backlog_wait_not_new_permission=True)
        sources.extend(record(p) for p in (folder/'PENDING_PRE_SITE_LEDGER.json',folder/'QUEUE_LEDGER.json',
            folder/'ACTUAL_RESULT.json',folder/'QOS_ACTUAL_LEDGER.json',fresh_path,rows_path))
        del events,queue,rows;gc.collect()
    result.update(status='PASS_READ_ONLY_FUNNEL_AND_OFFICIAL_SETTLED16' if all(
        r['status']=='PASS' for r in result['certificates'].values()) else 'PHYSICAL_FAIL',sources=sources)
    result['report_sha']=digest(result);write_new(out/'FUNNEL_AND_OFFICIAL_SETTLED16.json',result)
    print(json.dumps({k:v for k,v in result.items() if k not in ('sources',)},indent=2))


if __name__=='__main__':main()
