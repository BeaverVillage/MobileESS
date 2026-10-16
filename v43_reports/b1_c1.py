"""Reconcile C1 event UID/site/time/GPU and exact source power independently."""
from collections import Counter,defaultdict
from datetime import datetime,timezone,timedelta
from pathlib import Path
from time import perf_counter
import csv
import json

import numpy as np
import psutil

from v43.common import ROOT,DOC,RUNS,read,record,atomic,now,verify_records
from v43_actual.case import BUNDLE,power_model
from v43_corrective.experiment import ACTUAL,CANARY,PREFLIGHT,PARENT
from v43_actual.vendor.policy import digest
from v43_corrective.participation import change_authority


def integrate(out,a,b,start,end,site,gpu,origin):
    for t in range(max(0,int((a-start)//900)),min(len(out),int(np.ceil((b-start)/900)))):
        overlap=max(0.,min(b,start+(t+1)*900)-max(a,start+t*900))
        out[t,site,origin]+=gpu*overlap/900


def run():
    began=perf_counter();result=read(ACTUAL/'RESULT.json');assert result['PASS']
    start_record=read(ACTUAL/'START.json')
    try:
        process=psutil.Process(start_record['pid'])
        if process.create_time()==start_record['process_created']:raise RuntimeError('DO_NOT_FINALIZE_LIVE_ACTUAL_WORKER')
    except psutil.NoSuchProcess:pass
    reconciliation=read(ACTUAL/'RECONCILIATION.json')
    assert reconciliation['inflight'] is None and reconciliation['Native_calls']==0
    verify_records(start_record['sources'])
    verify_records(read(ACTUAL.with_name(ACTUAL.name+'.CORRECTIVE_SOURCE_FREEZE.json'))['sources'])
    case=read(ACTUAL/'CASE/CASE_BINDINGS.json');verify_records(case['source_receipts'])
    target=ACTUAL/'C1';events=read(target/'ACTUAL_EVENT_LEDGERS.json')
    policy=read(ACTUAL/'CORRECTIVE_POLICY_RECEIPTS.json');p=policy['policies'][0];c=policy['controllers'][0]
    assert [x['variant'] for x in policy['policies']]==['C1']
    jobs={r['job_uid']:r for r in events['queue_ledger']};metadata=read(target/'SIMULATOR_PRIVATE_CARRYOUT.json')['controller']['metadata']
    # Simulator-only remaining runtime is deliberately not accessed.
    q={r['uid']:r for r in events['qos_ledger']}
    ledger=events['job_event_ledger'];completions={r['uid']:r['time_seconds'] for r in ledger if r['event']=='COMPLETION_OBSERVED'}
    releases={r['uid']:r['time_seconds'] for r in ledger if r['event']=='GPU_RELEASE_CONTROL'}
    basic={r['uid']:r for r in ledger if r['event']=='BASIC_SITE_DESIGNATED_PENDING'}
    running=[r for r in ledger if r['event']=='RUNNING'];participation={r['uid']:r for r in c['participation']}
    start=1746000000.;day=start+21600;end=day+86400
    with np.load(target/'ACTUAL_PHYSICAL.npz',allow_pickle=False) as z:physical={k:z[k].copy() for k in z.files}
    sites=list(map(str,physical['sites']));compute=np.zeros((120,len(sites),2));hold=compute.copy()
    source_plan=read(BUNDLE/'PLANNING_INPUT_BUNDLE.json');source_actual=read(BUNDLE/'ACTUAL_INPUT_BUNDLE.json')
    source_by={r['job_uid']:r for r in source_plan['known_population']+source_actual['post_issue_arrivals']}
    assert set(source_by)==set(jobs)==set(metadata)
    with np.load(ACTUAL/'GOLDEN_REFERENCE/REFERENCE.npz',allow_pickle=False) as z:
        commands=json.loads(str(z['Known_UID_Schedule_JSON']))
    assert digest(commands)==case['Known_commands_sha']
    occupancy_events=[]
    groups={};uidrows=[]
    for origin,name in ((0,'Known'),(1,'Unknown')):
        subset=[r for r in jobs.values() if bool(r['origin_unknown'])==bool(origin)]
        groups[name]=dict(total=len(subset),START=sum(r['admitted_time'] is not None for r in subset),
            COMPLETED=sum(r['latest_state']=='COMPLETED' for r in subset),Carryout=sum(r['carryout'] for r in subset))
        for r in subset:
            uid=r['job_uid'];a=r['admitted_time'];gpu=r['GPU_gang']
            assert gpu==source_by[uid]['GPU_gang']==metadata[uid]['gpu']
            if a is not None:
                assert r['site'] in source_by[uid]['compatible_sites']
                assert gpu<=max(source_plan['rack_compatibility'][r['site']])
                if source_by[uid]['state']!='RUNNING':
                    assert a>=metadata[uid]['submit_seconds']
                    if uid in commands:
                        assert r['site']==commands[uid]['site'] and r['plan_start_seconds']==commands[uid]['start_seconds']
                a=max(a,start);b=min(completions.get(uid,end),end)
                integrate(compute,a,b,start,end,sites.index(r['site']),gpu,origin)
                release=min(releases.get(uid,end),end)
                integrate(hold,a,release,start,end,sites.index(r['site']),gpu,origin)
                if release>a:occupancy_events.extend([(a,1,r['site'],gpu),(release,0,r['site'],-gpu)])
            receipt=participation.get(uid,{})
            uidrows.append(dict(uid=uid,group=name,basic_site=basic.get(uid,{}).get('site'),
                selected_site=r['site'],submit_seconds=metadata[uid]['submit_seconds'],START_seconds=r['admitted_time'],
                completion_seconds=completions.get(uid),state=r['latest_state'],Carryout=r['carryout'],GPU=gpu,
                compute_GPUh_Dday=(gpu*max(0.,min(completions.get(uid,end),end)-max(day,r['admitted_time']))/3600
                    if r['admitted_time'] is not None else 0.),
                R1_eligible=receipt.get('eligible'),R1_participant=receipt.get('participant'),
                policy_action=r.get('policy_action'),Source_permission_verified=False if origin else None))
    np.testing.assert_allclose(compute.sum(axis=2),physical['compute_GPU'],atol=1e-10,rtol=0)
    np.testing.assert_allclose(hold.sum(axis=2),physical['GPU'],atol=1e-10,rtol=0)
    current={s:0 for s in sites}
    for when,kind,site,delta in sorted(occupancy_events):
        current[site]+=delta;assert 0<=current[site]<=source_plan['capacities'][site]
    assert not any(current.values())
    np.savez_compressed(ACTUAL/'INDEPENDENT_UID_GPU_INTEGRALS.npz',compute_by_group=compute,hold_by_group=hold,
        sites=sites,groups=['Known','Unknown'])
    power=read(BUNDLE/'POWER_AUTHORITY.json');caps=read(BUNDLE/'PLANNING_INPUT_BUNDLE.json')['capacities']
    model,_=power_model(power,caps)
    from v43_actual.observations import load_observations
    obs=load_observations(begin=start,end=end)
    exact=model.recompute(hold.sum(axis=2),sites,[obs.at(start+t*900,observed_now=start+t*900)['weather']['values'] for t in range(120)])
    errors={k:float(np.max(np.abs(exact[k]-physical[k]))) for k in ('IT_kw','PCC_P_kw','PCC_Q_kvar')}
    assert max(errors.values())<1e-9
    for origin,name in ((0,'Known'),(1,'Unknown')):
        groups[name].update(compute_GPUh_Dday=float(compute[24:,:,origin].sum()/4),
            compute_GPUh_whole30h=float(compute[:,:,origin].sum()/4))
    uidpath=ACTUAL/'INDEPENDENT_UID_AUDIT.csv'
    with uidpath.open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(uidrows[0]));writer.writeheader();writer.writerows(uidrows)
    funnel=p['candidate_funnel'];audits=p['current_diagnostics'];selections=[];score_by=defaultdict(list)
    for r in funnel:score_by[(r['uid'],r['time_seconds'])].append(r)
    attemptlog=read(target/'SIGNED_PENDING_POLICY_AUDIT.json')['audit']
    pending_by=defaultdict(list)
    for row in attemptlog:pending_by[row['uid']].append(row)
    unknown_starts={r['uid']:r for r in running if jobs[r['uid']]['origin_unknown']}
    actually_pre={uid:r for uid,r in unknown_starts.items() if r['site']!=basic[uid]['site']}
    selected={r['uid'] for r in funnel if r.get('selected') and r['site']!=r['basic_site']}
    overrun_wait_presite=set()
    for uid,e in actually_pre.items():
        assert participation[uid]['participant'] and participation[uid]['authority']=='R1_ASSUMED'
        assert change_authority(dict(metadata[uid],state='PENDING'),e['site'],e['time_seconds']) is None
        assert not metadata[uid].get('source_pre_site_forbidden') and not metadata[uid].get('presite_explicitly_forbidden')
        selectedrow=[r for r in score_by[(uid,e['time_seconds'])] if r['site']==e['site'] and r['selected']]
        assert selectedrow and selectedrow[0]['Current_AC_PASS']
        assert basic[uid]['state']=='PENDING' and basic[uid]['GPU_started'] is False
        assert any(r['uid']==uid and r['time_seconds']==e['time_seconds'] and e['site'] in r['candidate_sites']
            and r['current_AC_reject'] is None for r in audits)
        earlier=[r for r in pending_by[uid] if r['time_seconds']<e['time_seconds'] and r['decision']['action']=='QUEUE']
        blocking=[r for r in earlier if any(x.get('observed_overrun_blocking_UIDs') for x in r['decision'].get('rejected_candidates',[]))]
        if blocking:overrun_wait_presite.add(uid)
        selections.append(dict(uid=uid,from_site=basic[uid]['site'],to_site=e['site'],START_seconds=e['time_seconds'],
            authority='R1_ASSUMED',Source_verified=False,selected_sensitivity=selectedrow[0]['sensitivity'],
            all_candidates=score_by[(uid,e['time_seconds'])],earlier_overrun_blocked_QUEUE=blocking))
    assert not any(r.get('reason')=='C0_BASIC_SITE_ONLY' for r in funnel)
    assert not events['migration_receipts']
    unknown=[r for r in jobs.values() if r['origin_unknown']]
    assert all((not participation[r['job_uid']]['participant'] and r['admitted_time'] is not None)
        <= (r['site']==basic[r['job_uid']]['site']) for r in unknown)
    evaluation=[r for r in funnel if r.get('sensitivity_evaluated') and r['time_seconds']>=day]
    alternative=[r for r in evaluation if r['site']!=r['basic_site']]
    presite=dict(R1_eligible_UIDs=sum(r['eligible'] for r in participation.values()),
        R1_participant_UIDs=sum(r['participant'] for r in participation.values()),
        basic_designated_UIDs=len(basic),sensitivity_evaluated_UIDs=len({r['uid'] for r in evaluation}),
        alternative_compatible_candidate_instances=len([r for r in funnel if r['site']!=r['basic_site']]),
        permission_pass_alternative_instances=sum(r['source_or_R1_permission_PASS'] for r in funnel if r['site']!=r['basic_site']),
        sensitivity_evaluated_alternative_instances=len(alternative),
        sensitivity_evaluated_alternative_UIDs=len({r['uid'] for r in alternative}),
        R1_participant_sensitivity_evaluated_UIDs=len({r['uid'] for r in evaluation if r['participant']}),
        selected_presite_UIDs=len(selected),actual_presite_START_UIDs=len(actually_pre),
        overrun_wait_then_presite_START_UIDs=len(overrun_wait_presite),actual_presite_transitions=selections,
        candidate_rejection_counts=dict(Counter(r['reason'] for r in funnel if not r.get('selected'))),
        new_running_migrations=0,Unknown_intentional_timeshifting=0,authority='R1_ASSUMED',Source_verified=False)
    comparisons=[]
    for row in selections:
        basic_row=next(r for r in row['all_candidates'] if r['site']==row['from_site'])
        bs=basic_row.get('sensitivity');selected_score=row['selected_sensitivity']
        comparisons.append(dict(uid=row['uid'],basic_reason=basic_row['reason'],basic_scored=bs is not None,
            predicted_peak_reduced=bool(bs and round(selected_score['grid_peak'],12)<round(bs['grid_peak'],12)),
            predicted_loading_hours_reduced=bool(bs and selected_score['loading_hours']<bs['loading_hours'])))
    presite.update(selected_when_basic_NO_CAPACITY_UIDs=sum(r['basic_reason']=='NO_CAPACITY' for r in comparisons),
        selected_with_basic_signed_score_UIDs=sum(r['basic_scored'] for r in comparisons),
        selected_predicted_peak_reduced_UIDs=sum(r['predicted_peak_reduced'] for r in comparisons),
        selected_predicted_loading_hours_reduced_UIDs=sum(r['predicted_loading_hours_reduced'] for r in comparisons))
    if not actually_pre:
        explanations=[]
        for uid,receipt in participation.items():
            if not receipt['participant']:continue
            rows=[r for r in funnel if r['uid']==uid]
            alternatives=[r for r in rows if r['site']!=r['basic_site']]
            reason=('NO_ALTERNATIVE_SIGNED_SCORE_AFTER_HARD_GUARDS' if not any(r.get('sensitivity_evaluated') for r in alternatives)
                else 'BASIC_SELECTED_BY_SIGNED_RANK_OR_ALTERNATIVE_CURRENT_AC_REJECT')
            explanations.append(dict(uid=uid,reason=reason,candidate_reason_counts=dict(Counter(r['reason'] for r in alternatives)),
                evaluated_alternative_rows=[r for r in alternatives if r.get('sensitivity_evaluated')]))
        atomic(ACTUAL/'ZERO_PRESITE_CANDIDATE_ANALYSIS.json',dict(UIDs=explanations,policy_actually_active=True,
            C0_BASIC_SITE_ONLY_count=0,summary=dict(Counter(r['reason'] for r in explanations))))
        presite['zero_presite_analysis']=record(ACTUAL/'ZERO_PRESITE_CANDIDATE_ANALYSIS.json')
    atomic(ACTUAL/'PRESITE_UID_EVIDENCE.json',presite)
    fresh=read(target/'FRESH_ORIGINAL7_AC.json');steps=fresh['physical_steps'][24:]
    assert len(steps)==96
    peak=max(steps,key=lambda r:r['maximum_phase_line_loading'])
    base=read(RUNS/'may01_B0_exact_FCFS_actual96_attempt005/FRESH_ORIGINAL7_AC.json') if (RUNS/'may01_B0_exact_FCFS_actual96_attempt005/FRESH_ORIGINAL7_AC.json').exists() else None
    # Published baselines are immutable and explicitly compared at unequal service.
    c0steps=read(PARENT/'C0/FRESH_ORIGINAL7_AC.json')['physical_steps'][24:]
    c0peak=max(r['maximum_phase_line_loading'] for r in c0steps)
    b0report=read(RUNS/'may01_B0_exact_FCFS_actual96_attempt005/INDEPENDENT_BASELINE_REPORT.json')
    b0peak=b0report['peak_line_phase_loading']
    b0fresh=list((RUNS/'may01_B0_exact_FCFS_actual96_attempt005').rglob('FRESH*AC.json'))
    if b0fresh:b0peak=max(r['maximum_phase_line_loading'] for r in read(b0fresh[0])['physical_steps'][24:])
    grid=dict(peak_loading_fraction=peak['maximum_phase_line_loading'],peak_line=peak['maximum_line_phase'],
        peak_phase=peak['maximum_line_phase_letter'],peak_issue_slot=peak['slot'],
        peak_slot_begin_AEST=datetime.fromtimestamp(start+peak['slot']*900,timezone(timedelta(hours=10))).isoformat(),
        peak_slot_end_AEST=datetime.fromtimestamp(start+(peak['slot']+1)*900,timezone(timedelta(hours=10))).isoformat(),
        voltage_min_pu=min(r['voltage_min_pu'] for r in steps),voltage_max_pu=max(r['voltage_max_pu'] for r in steps),
        converged_slots=sum(r['converged'] for r in steps),
        violations={k:sum(r['violations'][k] for r in steps) for k in peak['violations']},
        delta_vs_C0_percentage_points=100*(peak['maximum_phase_line_loading']-c0peak),
        delta_vs_B0_percentage_points=100*(peak['maximum_phase_line_loading']-b0peak),
        equal_throughput_improvement_claimed=False)
    contract=read(PREFLIGHT/'KNOWN_WINDOW_AUDIT.json');mismatch={r['uid'] for r in contract['mismatch_UIDs']}
    unstarted={u for u,r in jobs.items() if not r['origin_unknown'] and r['admitted_time'] is None}
    reasons=defaultdict(Counter);last_reason={}
    for e in ledger:
        if e['uid'] in unstarted and e.get('reason'):reasons[e['uid']][e['reason']]+=1;last_reason[e['uid']]=e['reason']
    remainder=unstarted-mismatch
    authorized={r['uid']:r['OriginalKnownWindows_allowed_seconds'] for r in contract['all_UIDs']}
    late_known=[u for u,r in jobs.items() if u in authorized and r['admitted_time'] is not None
        and events['qos_budget_ledger'][u]['state_at_issue']!='RUNNING'
        and r['admitted_time']>=start and r['admitted_time'] not in authorized[u]]
    known_unstarted=dict(total=len(unstarted),planning_window_contract_FAIL_UIDs=len(mismatch),
        mismatch_unstarted_UIDs=len(mismatch&unstarted),remaining_other_UIDs=len(remainder),
        Actual_START_outside_original_window_UIDs=late_known,
        other_last_reason_counts=dict(Counter(last_reason.get(u,'NO_EXPLICIT_EVENT') for u in remainder)),
        other_UIDs=[dict(uid=u,last_reason=last_reason.get(u),counts=dict(reasons[u])) for u in sorted(remainder)])
    atomic(ACTUAL/'KNOWN_UNSTARTED_AUDIT.json',known_unstarted)
    crosscheck=read(PREFLIGHT/'CANARY_KNOWN_WINDOW_ADAPTER_CROSSCHECK.json')
    assert crosscheck['actual_known_decision_PLAN_OUTSIDE_AUTHORIZED_WINDOW']==len(mismatch)
    actual_receipts=events['qos_budget_ledger']
    for row in contract['all_UIDs']:
        assert actual_receipts[row['uid']]['allowed_starts_seconds']==row['OriginalKnownWindows_allowed_seconds']
    qos=dict(intentional_burden_exceeds_budget_UIDs=sum(r['total_intentional_burden_seconds']>r['budget_seconds']+1e-9 for r in q.values()),
        actual_latest_start_excess_UIDs=sum(r['latest_start_excess_seconds']>0 for r in q.values()),
        actual_latest_start_excess_started_UIDs=sum(r['latest_start_excess_seconds']>0 and jobs[u]['admitted_time'] is not None for u,r in q.items()),
        completion_deadline_violations=sum((r.get('actual_completion_deadline_excess_seconds') or 0)>0 for r in q.values()),
        source_customer_QoS_certified=False,service_equivalence='NOT_CERTIFIED')
    ac=read(target/'CURRENT_AC_RECEIPTS.json');misses=[r for r in ac if not r['cache_hit']]
    timing=dict(input_preparation_wall_seconds=result['preparation_wall_seconds'],
        actual_event_wall_seconds=result['variants']['C1']['actual_event_wall_seconds'],
        fresh_AC96_wall_seconds=result['variants']['C1']['Fresh_wall_seconds'],worker_total_wall_seconds=result['wall_seconds'],
        max_control_tick_seconds=result['variants']['C1']['tick_Max_seconds'],
        measured_substages=p['timings'],Current_AC_cache_requests=len(ac),Current_AC_cache_misses=len(misses),
        Current_AC_probe_seconds=sum(r['AC_wall_seconds'] for r in misses),
        preflight_wall_seconds=read(PREFLIGHT/'RESULT.json')['wall_seconds'],canary_wall_seconds=read(CANARY/'RESULT.json')['wall_seconds'],
        Native_calls=result['Native_calls'],Native_seconds=result['Native_seconds'])
    report=dict(UTC=now(),attempt='B1_R1_FLEX30_C1',scope='MAY01_ACTUAL96_PLUS_ISSUE_PREFIX',
        physical_execution_PASS=True,independent_UID_GPU_power_PASS=True,independent_instantaneous_GPU_rack_compatibility_PASS=True,
        groups=groups,presite={k:v for k,v in presite.items() if k!='actual_presite_transitions'},
        grid=grid,known_unstarted={k:v for k,v in known_unstarted.items() if k not in ('other_UIDs','Actual_START_outside_original_window_UIDs')},
        Known_actual_START_outside_original_window_UID_count=len(late_known),QoS=qos,timing=timing,
        observed_overrun_UIDs=dict(Known=sum(not r['origin_unknown'] for r in c['overruns']),
            Unknown=sum(r['origin_unknown'] for r in c['overruns'])),
        exact_C1_power_max_abs_errors=errors,Planning_reoptimized=0,Known_commands_unchanged=c['Known_commands_unchanged'],
        legacy_driver_R1_field_stale=result.get('R1')=='NOT_EXECUTED_ASSUMED_SEPARATE',
        R1_execution_authority='CORRECTIVE_POLICY_RECEIPTS_AND_INDEPENDENT_UID_START_JOINS',
        Golden003_UB=.6718471055537026,Golden003_independent_LB=.6715871456570585,
        Known_window_contract_status='FAIL',service_equivalence='NOT_CERTIFIED',
        FORECAST_CAUSAL_AVAILABILITY='NOT_CERTIFIED',CAUSAL_PASS=False,R1='ASSUMED',R2='HOLD',
        source_initial_running_sites='44_MODEL_ASSUMED_210_FIXED',
        evidence=dict(actual=record(ACTUAL/'RESULT.json'),UID=record(uidpath),presite=record(ACTUAL/'PRESITE_UID_EVIDENCE.json'),
            known_unstarted=record(ACTUAL/'KNOWN_UNSTARTED_AUDIT.json'),preflight=record(PREFLIGHT/'RESULT.json'),
            Fresh=record(target/'FRESH_ORIGINAL7_AC.json')))
    report['timing']['independent_audit_wall_seconds']=perf_counter()-began
    report['timing']['end_to_end_since_first_canary_START_seconds']=(datetime.now(timezone.utc)-
        datetime.fromisoformat(read(CANARY/'START.json')['UTC'])).total_seconds()
    report['timing']['total_measured_experiment_wall_seconds']=sum(timing[k] for k in (
        'preflight_wall_seconds','canary_wall_seconds','worker_total_wall_seconds','independent_audit_wall_seconds'))
    atomic(ACTUAL/'INDEPENDENT_C1_REPORT.json',report)
    atomic(DOC/'V43_B1_R1_FLEX30_C1_RESULT_POINTER.json',dict(report=record(ACTUAL/'INDEPENDENT_C1_REPORT.json'),
        physical_PASS=True,service_equivalence='NOT_CERTIFIED',Known_window_contract='FAIL'))
    print(json.dumps(report,ensure_ascii=False));return report


if __name__=='__main__':run()
