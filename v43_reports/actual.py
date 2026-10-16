"""Independent UID/service/physical report; never changes an Actual result."""
from pathlib import Path
import csv
import sys

import numpy as np
import psutil

from v43.common import DOC,read,record,verify_records,atomic,now
from v43_actual.vendor.policy import digest


def report(attempt):
    attempt=Path(attempt)
    start=read(attempt/'START.json')
    if psutil.pid_exists(start['pid']):
        p=psutil.Process(start['pid'])
        if p.create_time()==start['process_created']:
            raise RuntimeError('DO_NOT_FINALIZE_LIVE_ACTUAL_WORKER')
    result=read(attempt/'RESULT.json')
    reconciliation=read(attempt/'RECONCILIATION.json')
    if reconciliation.get('inflight') is not None or reconciliation['Native_calls'] != 0:
        raise ValueError('ACTUAL_NATIVE0_RECONCILIATION_REQUIRED')
    verify_records(start['sources'])
    case=read(attempt/'CASE/CASE_BINDINGS.json')
    arm=case.get('arm','B1')
    arm_freeze=attempt.with_name(attempt.name+'.ARM_SOURCE_FREEZE.json')
    if arm_freeze.exists():verify_records(read(arm_freeze)['sources'])
    verify_records(case['source_receipts'])
    source_plan=read(case['source_receipts'][0]['path'])
    source_actual=read(case['source_receipts'][1]['path'])
    known={r['job_uid'] for r in source_plan['known_population']}
    unknown={r['job_uid'] for r in source_actual['post_issue_arrivals']}
    from datetime import datetime
    issue=datetime.fromisoformat(source_plan['issue_time']).timestamp()
    begin=issue+21600;end=begin+86400
    if known & unknown or len(known)!=case['Known'] or len(unknown)!=case['Unknown']:
        raise ValueError('FROZEN_KNOWN_UNKNOWN_ROSTER_DRIFT')
    parent=case.get('Final_AIDC_reference',case['Golden003'])
    verify_records([parent])
    selected=read(parent['path'])['selected_jobs']
    if not set(selected) <= known:
        raise ValueError('FUTURE_UNKNOWN_UID_IN_GOLDEN_PLANNING')
    import json
    with np.load(attempt/'GOLDEN_REFERENCE/REFERENCE.npz',allow_pickle=False) as archive:
        commands=json.loads(str(archive['Known_UID_Schedule_JSON']))
    if set(commands)!=set(selected) or digest(commands)!=case['Known_commands_sha']:
        raise ValueError('GOLDEN_SELECTED_COMMAND_CONTENT_CHANGED')
    summaries=[];uid_rows=[];physical={}
    for variant in ('C0','C1'):
        folder=attempt/variant
        stage=read(folder/'RESULT.json')
        event=read(folder/'ACTUAL_EVENT_LEDGERS.json')
        policy=read(folder/'SIGNED_PENDING_POLICY_AUDIT.json')
        fresh=read(folder/'FRESH_ORIGINAL7_AC.json')
        # Only public controller state is used here. Private remaining service
        # is never forwarded into a new controller or a planning adapter.
        public=read(folder/'SIMULATOR_PRIVATE_CARRYOUT.json')['controller']
        metadata=public['metadata']
        reference=public['reference']['assigned']
        actual_by={r['job_uid']:r for r in event['queue_ledger']}
        if set(actual_by) != known|unknown or set(metadata) != known|unknown:
            raise ValueError('ACTUAL_COMPLETE_SUBMITTED_UID_ROSTER_REQUIRED')
        original_by={r['job_uid']:r for r in source_plan['known_population']}
        for uid,command in commands.items():
            row=actual_by[uid]
            if original_by[uid]['state']=='RUNNING' or row['admitted_time'] is None:
                continue
            if row['site']!=command['site'] or row.get('plan_start_seconds')!=command['start_seconds']:
                raise ValueError('KNOWN_ACTUAL_ADMISSION_DEVIATES_FROM_FROZEN_COMMAND')
        for r in event['job_event_ledger']:
            uid=r['uid']
            if r['event']=='SUBMISSION_OBSERVED' and r['time_seconds'] < actual_by[uid]['submit_time']:
                raise ValueError('FUTURE_SUBMISSION_IN_ACTUAL_CONTROLLER')
        decisions={uid:[] for uid in unknown}
        for row in policy['audit']:
            if row['uid'] not in unknown:
                raise ValueError('KNOWN_ENTERED_UNKNOWN_ALLOCATOR')
            decisions[row['uid']].append(row)
        selected={uid for uid,rows in decisions.items() if any(r['decision'].get('action')=='PREPLACE' for r in rows)}
        started={uid for uid in unknown if actual_by[uid].get('policy_action')=='PREPLACE'
            and actual_by[uid]['admitted_time'] is not None}
        eligible={uid for uid in unknown if metadata[uid].get('can_prestart_place') is True
            and metadata[uid].get('source_presite_authority')}
        changed_gpuh=0.;source_permission_violations=0
        for uid in sorted(unknown):
            r=actual_by[uid];m=metadata[uid];basic=reference[uid]['reference_site']
            submitted_Dday=begin<=r['submit_time']<end
            selected_events=[a for a in decisions[uid] if a['decision'].get('action')=='PREPLACE']
            actual_start=r['admitted_time'];completion=r.get('completion_observed_time')
            release=r.get('release_control_time')
            changed=actual_start is not None and r['site'] != basic
            occupation=0. if actual_start is None else r['GPU_gang']*max(0.,
                min(end,end if release is None else release)-max(begin,actual_start))/3600
            service=0. if actual_start is None else r['GPU_gang']*max(0.,
                min(end,end if completion is None else completion)-max(begin,actual_start))/3600
            if changed:
                changed_gpuh+=occupation
                if not selected_events or uid not in eligible:source_permission_violations+=1
            reasons={a['decision'].get('status') for a in decisions[uid]}
            if not eligible.intersection({uid}):reasons.add('SOURCE_UID_DESTINATION_CONSENT_NOT_AVAILABLE')
            uid_rows.append(dict(variant=variant,uid=uid,submit_seconds=r['submit_time'],
                origin='DDAY_UNKNOWN' if submitted_Dday else 'POST_ISSUE_PREFIX_UNKNOWN',
                basic_site=basic,source_presite_eligible=uid in eligible,presite_selected=uid in selected,
                selected_events=len(selected_events),presite_actually_started=uid in started,
                actual_site=r['site'],admitted_seconds=actual_start,completion_seconds=completion,
                terminal_state=r['latest_state'],terminal_carryout=r['carryout'],
                occupation_Dday_GPUh=occupation,compute_Dday_GPUh=service,changed_from_basic=changed,
                intentional_delay_seconds=r.get('intentional_delay_seconds',0.),
                actual_wait_seconds=r.get('capacity_wait_seconds'),
                selection_or_nonexecution_reasons='|'.join(sorted(str(x) for x in reasons))))
        with np.load(folder/'ACTUAL_PHYSICAL.npz',allow_pickle=False) as z:
            physical[variant]={k:z[k].copy() for k in ('GPU','compute_GPU','IT_kw','PCC_P_kw','PCC_Q_kvar')}
            sites=list(map(str,z['sites']))
        arr=physical[variant]
        caps=np.array([source_plan['capacities'][s] for s in sites])
        if arr['GPU'].shape!=(120,12) or not np.isfinite(arr['GPU']).all() or np.any(arr['GPU']>caps+1e-8):
            raise ValueError('ACTUAL_GPU_AXES_OR_CAPACITY_DRIFT')
        power=read(case['source_receipts'][3]['path'])
        expected=power['current_IT_idle_kW_per_installed_GPU']*caps+power['current_IT_swing_kW_per_active_GPU']*arr['GPU']
        if not np.array_equal(expected,arr['IT_kw']):
            raise ValueError('ACTUAL_IT_NOT_RECOMPUTED_FROM_OCCUPATION')
        if not np.allclose(arr['PCC_Q_kvar'],arr['PCC_P_kw']*np.tan(np.arccos(power['PF_AIDC'])),rtol=0,atol=1e-12):
            raise ValueError('ACTUAL_ORIGINAL_PF_Q_COUPLING_DRIFT')
        source_by={r['job_uid']:r for r in source_plan['known_population']+source_actual['post_issue_arrivals']}
        occupancy_events=[];rack_violations=0;compatibility_violations=0
        for uid,r in actual_by.items():
            if r['GPU_gang'] != source_by[uid]['GPU_gang'] or metadata[uid]['gpu'] != source_by[uid]['GPU_gang']:
                raise ValueError('ACTUAL_SOURCE_WHOLE_GANG_CHANGED')
            if r['admitted_time'] is None:
                continue
            site=r['site']
            rack_violations += r['GPU_gang']>max(source_plan['rack_compatibility'][site])
            compatibility_violations += site not in source_by[uid]['compatible_sites']
            left=max(issue,r['admitted_time'])
            right=min(end,r['release_control_time'] if r['release_control_time'] is not None else end)
            if right>left:
                occupancy_events.extend([(left,1,site,r['GPU_gang']),(right,0,site,-r['GPU_gang'])])
        use={s:0 for s in sites};capacity_violations=0
        for at,kind,site,delta in sorted(occupancy_events):
            use[site]+=delta
            capacity_violations += use[site]<0 or use[site]>source_plan['capacities'][site]
        if any(use.values()) or capacity_violations or rack_violations or compatibility_violations:
            raise ValueError('INDEPENDENT_ACTUAL_WHOLE_GANG_GPU_RACK_COMPATIBILITY_REPLAY_FAILED')
        if event['migration_receipts']:
            raise ValueError('UNEXPECTED_MIGRATION_IN_PENDING_ONLY_CASE')
        evaluated=fresh['physical_steps'][24:]
        if len(evaluated)!=96:
            raise ValueError('INDEPENDENT_FRESH96_REQUIRED')
        violations={k:sum(r['violations'][k] for r in evaluated) for k in evaluated[0]['violations']}
        gpuh=float(arr['GPU'][24:].sum()/4);compute=float(arr['compute_GPU'][24:].sum()/4)
        urows=[r for r in uid_rows if r['variant']==variant]
        summary=dict(variant=variant,case_sha=case['case_sha'],Known_commands_sha=case['Known_commands_sha'],
            Unknown_Submitted_UID=len(unknown),Unknown_Dday_Submitted_UID=sum(r['origin']=='DDAY_UNKNOWN' for r in urows),
            Unknown_Basic_Site_Assigned=len(set(unknown)&set(reference)),Pre_site_Eligible_UID=len(eligible),
            Pre_site_Candidate_Evaluated=sum(max(0,a['decision'].get('candidate_count',0)-1-
                sum(r['reason'] in ('C0_BASIC_SITE_ONLY','SOURCE_PREPLACEMENT_AUTHORITY_MISSING',
                    'SOURCE_UID_DESTINATION_CONSENT_NOT_VERIFIED','SOURCE_DATA_WAN_READY_NOT_VERIFIED')
                    for r in a['decision'].get('rejected_candidates',[]))) for rows in decisions.values() for a in rows),
            Pre_site_Hard_Feasible=None,Pre_site_Selected_UID=len(selected),Pre_site_Actually_Started_UID=len(started),
            Pre_site_Changed_GPUh=changed_gpuh,Unknown_Queue_UID=sum(r['terminal_state']=='PENDING' for r in urows),
            Unknown_Completed_UID=sum(r['terminal_state']=='COMPLETED' for r in urows),
            Unknown_Terminal_Carryout_UID=sum(r['terminal_carryout'] for r in urows),
            Unknown_Dday_compute_GPUh=sum(r['compute_Dday_GPUh'] for r in urows),
            actual_occupation_GPUh=gpuh,actual_compute_GPUh=compute,
            actual_peak_line_phase_loading=max(r['maximum_phase_line_loading'] for r in evaluated),
            actual_daily_mean_slot_max_line_phase_loading=float(np.mean([r['maximum_phase_line_loading'] for r in evaluated])),
            Fresh_converged_slots=sum(r['converged'] for r in evaluated),Fresh_violations=violations,
            Source_permission_violations=source_permission_violations,
            GPU_runtime_violations=capacity_violations,Rack_runtime_violations=rack_violations,
            source_compatibility_violations=compatibility_violations,WAN_transfer_calls=0,
            controller_P50_seconds=stage['tick_P50_seconds'],controller_P95_seconds=stage['tick_P95_seconds'],
            controller_Max_seconds=stage['tick_Max_seconds'],controller_timing_scope='WHOLE_ISSUE_TO_END_CONTROLLER_CALLBACKS_120_PHYSICAL_SLOTS',
            Note='Hard-feasible alternative count is zero if Source eligibility is zero; otherwise requires candidate-level score evidence.')
        if not eligible:summary['Pre_site_Hard_Feasible']=0
        summaries.append(summary)
    equal={key:np.array_equal(physical['C0'][key],physical['C1'][key]) for key in physical['C0']}
    artifact=attempt/'INDEPENDENT_UNKNOWN_UID_AUDIT.csv'
    with artifact.open('x',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(uid_rows[0]));writer.writeheader();writer.writerows(uid_rows)
    report=dict(UTC=now(),schema='V43_INDEPENDENT_ACTUAL_UID_AND_PHYSICAL_REPORT_V1',arm=arm,
        result=record(attempt/'RESULT.json'),summaries=summaries,UID_audit=record(artifact),
        C0_C1_physical_bit_exact=equal,Source_pre_site_production_claim=False,
        initial_source_sites='44_MODEL_ASSUMED_210_ORIGINAL_FIXED',R1='NOT_EXECUTED',R2='HOLD',
        original_control_contract='7REG_SNAPSHOT_STATIC_NO_ADDED_SVR',
        FORECAST_CAUSAL_AVAILABILITY='NOT_CERTIFIED',CAUSAL_PASS=False,
        conditional_Gate_B_execution_PASS=result.get('Gate_B_PASS',False),
        UID_OriginalRoster_and_KnownCommands_PASS=True,GPU_IT_PF_Q_replay_PASS=True)
    atomic(attempt/'INDEPENDENT_ACTUAL_REPORT.json',report)
    destination='GATE_B_ACTUAL96_INDEPENDENT_CERTIFICATION.json' if arm=='B1' else f'V43_MAY01_{arm}_ACTUAL96_INDEPENDENT_CERTIFICATION.json'
    atomic(DOC/destination,dict(report=record(attempt/'INDEPENDENT_ACTUAL_REPORT.json'),
        conditional_Gate_B_execution_PASS=report['conditional_Gate_B_execution_PASS'],
        UID_OriginalRoster_and_KnownCommands_PASS=True,GPU_IT_PF_Q_replay_PASS=True,
        Source_initial_sites_certified=False,FORECAST_CAUSAL_AVAILABILITY='NOT_CERTIFIED',CAUSAL_PASS=False))
    return report


if __name__=='__main__':
    print(report(sys.argv[1]))
