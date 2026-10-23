"""Read-only policy re-audit and enlarged, source-strict witness search."""
from collections import Counter
from pathlib import Path
import io,json,zipfile
import numpy as np
from .audit import ROOT,DOC,read,sha
from .correction import OUT,RUN,put,csvout,priority
from .aidc_candidate import actual_c1

def main():
    priority()
    day=read(ROOT/'docs/v44/SEVEN_DAY_INPUT_MANIFEST.json')['days'][0]
    native=read(day['files']['native']['path']);windows=read(day['files']['windows']['path'])
    jobs={r['job_uid']:r for r in native['known_population']};win={r['job_id']:r for r in windows}
    archived=read(Path('D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/campaign004/ARCHIVED_RESULTS_20250501_14.json'))['days'][0]
    z=zipfile.ZipFile(archived['archive']);prefix='2025-05-01/B1/attempt002/ACTUAL/C1/'
    legacy=json.loads(z.read(prefix+'ACTUAL_EVENT_LEDGERS.json'))
    reference=read(DOC/'source/aidc_pilot/PLANNING_REFERENCE.json')
    issue=day['axis']['issue_seconds'];start={r['uid']:r for r in legacy['job_event_ledger'] if r['event']=='RUNNING'}
    finish={r['uid']:r for r in legacy['job_event_ledger'] if r['event']=='COMPLETION_OBSERVED'}
    qos={r['uid']:r for r in legacy['qos_ledger']};budgets=legacy['qos_budget_ledger']
    assumptions={r['uid']:r for r in legacy['job_event_ledger'] if r['event']=='KNOWN_RESEARCH_WINDOW_ASSUMPTION'}
    def detail(uid):
        j=jobs.get(uid,{});w=win.get(uid,{});q=qos.get(uid,{});b=budgets[uid]
        actual=start.get(uid,{}).get('time_seconds');plan=reference['selected_jobs'].get(uid,{}).get('start')
        return dict(job_uid=uid,origin_unknown=b['origin_unknown'],known_unknown='Unknown' if b['origin_unknown'] else 'Known',
            original_allowed_starts=json.dumps(w.get('allowed_starts',[])),planning_start_slot=plan,
            actual_start_seconds=actual,actual_start_issue_slot=None if actual is None else (actual-issue)/900,
            native_source_can_timeshift=j.get('can_timeshift'),effective_WINDOWS_can_timeshift=w.get('can_timeshift'),
            native_delay_budget_seconds=None if j.get('delay_budget_slots') is None else j['delay_budget_slots']*900,
            original_window_delay_budget_seconds=b['budget_seconds'],completion_deadline_seconds=b['hard_contract'].get('completion_deadline_seconds'),
            original_latest_start_seconds=b['latest_start_seconds'],
            source_hard_latest_start_seconds=b['hard_contract'].get('hard_latest_start_seconds'),
            completion_observed_seconds=finish.get(uid,{}).get('time_seconds'),
            actual_delay_seconds=q.get('intentional_start_delay_seconds'),intentional_burden_seconds=q.get('total_intentional_burden_seconds'),
            strict_budget_pass=q.get('total_intentional_burden_seconds',0)<=b['budget_seconds']+1e-6,
            research_policy_id=assumptions.get(uid,{}).get('policy_id'),
            source_customer_QoS_certified=False,
            planning_domain_source='v42_pr134_b1/native.py: allowed_starts=tuple(windows[uid][allowed_starts]); v44/planning.py:golden',
            actual_policy_source='v43_corrective/known_window.py:policy_assumption,_known_decision,_measure; v43_corrective/controller.py:admission_core; v44/actual_policy.py:controller_class')
    mismatch=[]
    for uid,r in reference['selected_jobs'].items():
        if r['start'] in win[uid]['allowed_starts']:continue
        row=detail(uid);row.update(classification='V44_POLICY_OR_PHYSICAL_VIOLATION',
            scope='PLANNING_ORIGINAL_FULL_DOMAIN',planning_original_domain_pass=False,
            actual_known_relaxed_window_permitted=uid in assumptions,
            reason='Cached Accepted Planning command is outside original FULL finite start domain; Actual relaxed policy is a separate execution assumption, not Planning domain authorization')
        mismatch.append(row)
    excess=[]
    for uid,q in qos.items():
        if q['total_intentional_burden_seconds']<=q['budget_seconds']+1e-6:continue
        row=detail(uid);relaxed=uid in assumptions and budgets[uid]['origin_unknown'] is False
        row.update(classification='V44_RESEARCH_POLICY_COMPLIANT_BUT_SOURCE_QOS_NOT_CERTIFIED' if relaxed else 'V44_POLICY_OR_PHYSICAL_VIOLATION',
            scope='ACTUAL_QOS_MEASUREMENT',actual_known_relaxed_window_permitted=relaxed,
            strict_source_qos_pass=False,physical_FULL_recertified=False,
            reason='Known window/latest/deadline and resulting start burden are measured post hoc by opt-in policy; no Source authorization inferred' if relaxed else 'No matching Known relaxed-policy event; original budget gate applies')
        excess.append(row)
    assert len(mismatch)==414 and len(excess)==192
    csvout('AIDC_WINDOW_POLICY_414_REAUDIT.csv',mismatch);csvout('AIDC_QOS_BUDGET_192_REAUDIT.csv',excess)
    # Broader strict time-shift search: every gang size, every original start,
    # any number per site, chronological UID tie-break, preserved prefix.
    basefolder=Path('D:/smartds_gso_substation2_v44_r043_runtime/jobs')
    base=np.load(basefolder/'ACTUAL_PHYSICAL.npz');led=read(basefolder/'EVENT_LEDGERS.json')
    sites=list(map(str,base['sites']));original=base['GPU'];gpu=original.copy()
    starts={r['uid']:r for r in led['job_event_ledger'] if r['event']=='RUNNING'}
    releases={r['uid']:r for r in led['job_event_ledger'] if r['event']=='GPU_RELEASE_CONTROL'}
    completions={r['uid']:r for r in led['job_event_ledger'] if r['event']=='COMPLETION_OBSERVED'}
    qby={r['uid']:r for r in led['qos_ledger']};bounds=led['qos_budget_ledger']
    counters=Counter();chosen=[];perjob=[];candidate_count=0;capacity=np.array([native['capacities'][s] for s in sites])
    for uid,event in sorted(starts.items(),key=lambda v:(v[1]['time_seconds'],v[0])):
        if uid not in jobs:continue
        j=jobs[uid];w=win.get(uid);b=bounds[uid];reason=None;feasible=[]
        begin=int(round((event['time_seconds']-issue)/900))
        if begin<24:reason='SOURCE_PREFIX_ALREADY_STARTED_NO_RETROACTIVE_SHIFT'
        elif w is None or not w['can_timeshift']:reason='NO_EFFECTIVE_WINDOW_TIMESHIFT_AUTHORITY'
        elif uid not in releases or uid not in completions:reason='NO_COMPLETE_REBOUND_WITHIN_HORIZON'
        else:
            end=int(round((releases[uid]['time_seconds']-issue)/900));s=sites.index(event['site']);g=j['GPU_gang']
            for new in w['allowed_starts']:
                delay=new-begin
                if delay<=0 or end+delay>120:continue
                newseconds=issue+new*900
                if newseconds>b['latest_start_seconds']+1e-6:continue
                if qby[uid]['total_intentional_burden_seconds']+delay*900>b['budget_seconds']+1e-6:continue
                deadline=b['hard_contract'].get('completion_deadline_seconds')
                if deadline is not None and completions[uid]['time_seconds']+delay*900>deadline:continue
                trial=gpu.copy();trial[begin:end,s]-=g;trial[new:end+delay,s]+=g
                if trial.min()<-1e-8 or np.any(trial>capacity+1e-8):continue
                feasible.append((new,delay,trial))
            candidate_count+=len(feasible)
            if feasible:
                new,delay,gpu=feasible[0]
                chosen.append(dict(uid=uid,site=event['site'],GPU_gang=g,start=begin,end=end,new_start=new,
                    delay=delay,service_preserved=True,capacity_PASS=True,WAN_bytes=0,migration=False))
                reason='SOURCE_WINDOW_BUDGET_DEADLINE_CAPACITY_WITNESS'
            else:reason='NO_ORIGINAL_ALLOWED_START_WITH_BUDGET_DEADLINE_COMPLETE_REBOUND_CAPACITY'
        counters[reason]+=1;perjob.append(dict(uid=uid,GPU_gang=j['GPU_gang'],start_slot=begin,
            original_allowed_start_count=len(w['allowed_starts']) if w else 0,feasible_choices=len(feasible),reason=reason))
    csvout('AIDC_EXPANDED_TIMESHIFT_JOB_AUDIT.csv',perjob)
    p,q,_=actual_c1(gpu,sites,day);bp,bq,_=actual_c1(original,sites,day)
    assert np.max(abs(bp-base['PCC_P_kw']))<1e-7
    np.savez_compressed(OUT/'AIDC_EXPANDED_STRICT_WITNESS.npz',GPU=gpu,P=p,Q=q,delta_P=p-bp,delta_Q=q-bq)
    # Source capability is an envelope, not a migration receipt or feasible schedule.
    running=[r for r in native['known_population'] if r['state']=='RUNNING']
    pending=[r for r in native['known_population'] if r['state']=='PENDING']
    migration_code=ROOT/'v43_actual/vendor/policy.py'
    put('AIDC_REAL_FEASIBILITY.json',dict(status='ACTUAL_AIDC_NONZERO_NOT_VERIFIED' if not chosen else 'STRICT_OFFLINE_WITNESS_PENDING_CAUSAL_FULL_REPLAY',
        planning_mismatch_count=len(mismatch),planning_mismatch_classifications=dict(Counter(r['classification'] for r in mismatch)),
        actual_budget_count=len(excess),actual_budget_classifications=dict(Counter(r['classification'] for r in excess)),
        customer_Source_QoS_certified=False,policy_authorizes_Source_QoS=False,
        expanded_search='all Known gang sizes/all original allowed starts/no one-per-site cap/same site/complete rebound/prefix fixed; no A1/A2 changes',
        expanded_search_reason_counts=dict(counters),finite_feasible_choices=candidate_count,selected_jobs=chosen,
        GPUh_change=float((gpu-original).sum()*.25),GPUh_moved=float(sum(j['GPU_gang']*(j['end']-j['start'])*.25 for j in chosen)),
        maximum_reduction_kw=float(np.max(np.sum(bp-p,axis=1))),maximum_rebound_kw=float(np.max(np.sum(p-bp,axis=1))),
        peak74_reduction_kw=float(np.sum(bp[98]-p[98])),actual_C1_reproduction_max_kw=float(np.max(abs(bp-base['PCC_P_kw']))),
        pending_Known_count=len(pending),pending_gang_counts=dict(Counter(str(r['GPU_gang']) for r in pending)),
        running_Known_count=len(running),running_multiGPU_count=sum(r['GPU_gang']>1 for r in running),
        effective_WINDOW_timeshift_jobs=sum(r['can_timeshift'] for r in windows),
        source_native_timeshift_flag_true=sum(r.get('can_timeshift') is True for r in native['known_population']),
        preplace_capability_flag_jobs=sum(r.get('can_prestart_place') is True for r in native['known_population']),
        checkpoint_capability_flag_jobs=sum(r.get('can_checkpoint_migrate') is True for r in native['known_population']),
        migration_envelope_status='NOT_A_FEASIBLE_WITNESS: requires original capability packet, observed execution-anchored checkpoint, WAN/rack/data residency, source/dest simultaneous occupancy and shared delay budget',
        migration_guard_source=str(migration_code.relative_to(ROOT)),migration_guard_sha256=sha(migration_code.read_bytes()),
        preplace_witness_status='NOT_VERIFIED_ORIGINAL_CONTROLLER_AND_COMPATIBILITY_FULL_REPLAY_REQUIRED',
        migration_witness_status='NOT_VERIFIED_ORIGINAL_CONTROLLER_AND_CAPABILITY_WAN_FULL_REPLAY_REQUIRED',
        migration_feasible_kw=None,migration_feasible_GPUh=None,preplace_feasible_kw=None,
        migration_and_preplace_numeric_status='NOT_VERIFIED_NO_FULL_CAUSAL_WITNESS; blank is not zero',
        no_new_schedule_with_unknown_future_runtime_claim=True,not_global_flexibility_upper_bound=True,
        unknown_count=sum(b['origin_unknown'] for b in bounds.values()),unknown_positive_budget_count=sum(b['origin_unknown'] and b['budget_seconds']>0 for b in bounds.values()),
        strict_Source_authorization_limit='Original effective finite WINDOWS and PR189 ORIGINAL_MODEL_RESEARCH_AUTHORITY are not customer SLA consent; neither alone establishes Source QoS certification'))
    print('AIDC REAUDIT',len(mismatch),len(excess),'expanded shifts',len(chosen),dict(counters),flush=True)

if __name__=='__main__':main()
