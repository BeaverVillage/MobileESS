"""Read public starts/queue/episodes; no replay or private service access."""
from pathlib import Path
import gzip,hashlib,json,collections,shutil

ROOT=Path(__file__).parents[2]
FOLDER=ROOT/'audit/control/FINAL_FLEX_COMPARISON/E1_FLEX30_GRID_SENSITIVITY_AWARE'
OUTPUT=Path(__file__).parent/'MAIN_PUBLIC_START_QUEUE_COUNT_RECONCILIATION.json'

def main():
    path=FOLDER/'CONDITIONAL_ACTUAL_RESULT.json.gz'
    with gzip.open(path,'rt',encoding='utf8') as stream:d=json.load(stream)
    receipt=json.loads((FOLDER/'EXECUTION_RECEIPT.json').read_text(encoding='utf8'))
    begin,end=receipt['begin_seconds'],receipt['end_seconds'];c=d['carryout']['controller']
    rows={r['job_uid']:r for r in d['queue_ledger']};episodes=c['episode_jobs']
    running=[e for e in d['job_event_ledger'] if e['event']=='RUNNING'];starts={e['uid']:e for e in running}
    initial={uid for uid,r in rows.items() if r.get('admitted_time') is not None and uid not in starts and r['admitted_time']<=begin}
    pending={uid for uid,r in rows.items() if r.get('admitted_time') is None}
    episode_pending={uid for uid,r in episodes.items() if r['start_time'] is None}
    heap_pending={p[1] for p in c['pending']}
    unknown_pending={uid for uid in pending if c['metadata'][uid].get('origin_unknown') is True}
    known_pending=pending-unknown_pending
    risks=d.get('experimental_pending_contract_risk',[]);risk_UIDs={r['uid'] for r in risks}
    references=c.get('experimental_runtime_state',{}).get('references',{})
    missing_risk_UIDs=pending-risk_UIDs
    mismatches=[]
    for uid,row in rows.items():
        if row.get('admitted_time')!=episodes[uid]['start_time']:
            mismatches.append(dict(uid=uid,queue_admitted_time=row.get('admitted_time'),episode_start=episodes[uid]['start_time']))
        if uid in starts and starts[uid]['time_seconds']!=row['admitted_time']:
            mismatches.append(dict(uid=uid,event_start=starts[uid]['time_seconds'],queue_admitted_time=row['admitted_time']))
    day_wait=sum(max(0.,min(end if r.get('admitted_time') is None else r['admitted_time'],end)-max(begin,r['submit_time']))
        for uid,r in rows.items() if uid not in initial)
    def public(uid):
        r=rows[uid];j=episodes[uid];m=c['metadata'][uid]
        return dict(uid=uid,submit_time=r['submit_time'],queue_admitted_time=r.get('admitted_time'),
            episode_start_time=j['start_time'],episode_state=j['latest_observed_state'],metadata_state=m.get('state'),
            origin_unknown=m.get('origin_unknown'),gpu=j['gpu'],nominal_q50_seconds=j['q50_seconds'],
            initial_site=j.get('initial_site'),final_site=j.get('current_site'),RUNNING_event=starts.get(uid),
            experimental_physical_R0=references.get(uid),
            qos_budget_seconds=c['qos_budget_ledger'][uid]['budget_seconds'])
    out=dict(schema='PUBLIC_PHYSICAL_START_QUEUE_RECONCILIATION_V2',source_sha=receipt['source_freeze_sha'],
        case_sha=receipt['case_sha'],result_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        begin_seconds=begin,end_seconds=end,active_jobs=len(rows),initial_running=len(initial),
        RUNNING_event_occurrences=len(running),RUNNING_event_unique_UIDs=len(starts),
        never_admitted_queue_rows=len(pending),never_started_episode_rows=len(episode_pending),
        pending_heap_unique_UIDs=len(heap_pending),pending_unknown=len(unknown_pending),pending_known=len(known_pending),
        pending_first_reference_risk_ledger_rows=len(risks),pending_first_reference_risk_unique_UIDs=len(risk_UIDs),
        risk_ledger_is_subset_of_physical_never_started_PASS=risk_UIDs.issubset(pending),
        physically_never_started_excluded_from_first_reference_risk_count=len(missing_risk_UIDs),
        all_risk_excluded_pending_have_no_physical_R0=all(uid not in references for uid in missing_risk_UIDs),
        physically_never_started_without_risk_rows=[public(uid) for uid in sorted(missing_risk_UIDs)],
        count_scope='330_TOTAL_PHYSICAL_NEVER_STARTED_VS318_FIRST_REFERENCE_RISK_SUBSET;RISK_LEDGER_IS_NOT_TOTAL_QUEUE',
        episode_state_counts=dict(collections.Counter(j['latest_observed_state'] for j in episodes.values())),
        metadata_state_counts=dict(collections.Counter(m.get('state') for m in c['metadata'].values())),
        queue_episode_event_time_mismatches=mismatches,
        public_day_wait_seconds=day_wait,wait_uses_actual_admitted_and_episode_start_not_reserved_plan_or_raw_future_start=True,
        partition_PASS=set(rows)==initial|set(starts)|pending and not(initial&set(starts) or initial&pending or set(starts)&pending),
        episode_queue_heap_pending_UIDs_equal=pending==episode_pending==heap_pending,
        supplied_318_is_current_public_never_started_count=len(pending)==318,
        discrepant_heap_or_episode_rows=[public(uid) for uid in sorted(pending^heap_pending|pending^episode_pending)],
        known_never_started_rows=[public(uid) for uid in sorted(known_pending)],
        first_pending_rows=[public(uid) for uid in sorted(pending)[:15]],
        Native_Optimize_calls=0,Actual_replays=0,Fresh_AC_calls=0,private_realized_duration_or_completion_read=False)
    out['PASS']=out['partition_PASS'] and out['episode_queue_heap_pending_UIDs_equal'] and not mismatches and len(running)==len(starts)
    prior=OUTPUT.with_name(OUTPUT.stem+'_V1.json')
    if OUTPUT.is_file() and not prior.is_file():shutil.copyfile(OUTPUT,prior)
    OUTPUT.write_text(json.dumps(out,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
    shutil.copyfile(OUTPUT,OUTPUT.with_name(OUTPUT.stem+'_V2.json'))
    print(json.dumps({k:v for k,v in out.items() if not isinstance(v,(dict,list))},ensure_ascii=False))

if __name__=='__main__':main()
