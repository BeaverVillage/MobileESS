"""Retrospective partial diagnostics; never an input to a controller."""
from collections import Counter
import math
import numpy as np
from .trajectory_tracking import service_integral
from .action_metrics import unknown_actual_metrics


def separated_occupancy(result,begin,end):
    c=result['carryout']['controller'];sites=tuple(result['sites'])
    groups={k:np.zeros((96,len(sites))) for k in ('Known','Unknown')}
    compute={k:np.zeros((96,len(sites))) for k in groups}
    migrations={r['job_id']:r for r in result['migration_receipts']}
    for uid,j in c['episode_jobs'].items():
        if j['start_time'] is None:continue
        group='Unknown' if c['metadata'][uid]['origin_unknown'] else 'Known'
        stop=end if j['release_control_time'] is None else min(end,j['release_control_time'])
        done=end if j['completion_observed_time'] is None else min(end,j['completion_observed_time'])
        site=j['initial_site'];start=max(begin,j['start_time']);gpu=j['gpu']
        migration=migrations.get(uid)
        if not migration:
            occupied=[dict(resource='gpu:'+site,begin=start,end=stop,quantity=gpu)]
            service=[dict(resource='gpu:'+site,begin=start,end=done,quantity=gpu)]
        else:
            cp=migration['physical_checkpoint_seconds'];times=migration['times']
            occupied=[dict(resource='gpu:'+site,begin=start,end=min(stop,cp),quantity=gpu)]
            occupied += [dict(s,end=min(s['end'],end)) for s in migration['segments']
                         if s['resource'].startswith('gpu:') and s['begin']<end]
            occupied += [dict(resource='gpu:'+migration['destination'],begin=times['restart_end'],end=stop,quantity=gpu)]
            service=[dict(resource='gpu:'+site,begin=start,end=min(done,cp),quantity=gpu),
                dict(resource='gpu:'+migration['destination'],begin=times['restart_end'],end=done,quantity=gpu)]
        occupied=[s for s in occupied if s['end']>s['begin']]
        service=[s for s in service if s['end']>s['begin']]
        groups[group]+=service_integral(sites,occupied,begin)
        compute[group]+=service_integral(sites,service,begin)
    slots=int((end-begin)/900)
    groups={k:v[:slots] for k,v in groups.items()};compute={k:v[:slots] for k,v in compute.items()}
    np.testing.assert_allclose(groups['Known']+groups['Unknown'],result['occupancy_GPU'],rtol=0,atol=1e-8)
    np.testing.assert_allclose(compute['Known']+compute['Unknown'],result['compute_occupancy_GPU'],rtol=0,atol=1e-8)
    return groups,compute


def grid_diagnostic(packet,p):
    per=[];all_line=[];bad=[]
    for t in range(len(p)):
        planned=np.array([packet.aidc_plan['AIDC_P_by_site'][s][t] for s in packet.sites])
        gpu_delta=(p[t]-planned)/packet.p_slope[t]
        rho,violations=packet._at_slot(t,gpu_delta);per.append(rho);bad.extend(violations)
        c=packet.coefficients[t];control=packet.controls[t].copy()
        for j,s in enumerate(packet.sites):control[packet.control_names.index('aidc_load_kw['+s+']')]=p[t,j]
        branch_p=c.flow_p_constant+c.flow_p_matrix@control
        branch_q=c.flow_q_constant+c.flow_q_matrix@control
        faces=(branch_p[:,None]*packet.cos+branch_q[:,None]*packet.sin)/packet.ap[t][:,None]
        faces+=((packet.correction[t]@(control-c.anchor))+packet.bias[t])[:,None]
        all_line.append(np.maximum(0,np.max(faces[packet.line_indices],axis=1)))
    all_line=np.asarray(all_line)
    t,j=np.unravel_index(np.argmax(all_line),all_line.shape)
    branch=packet.branch_names[packet.line_indices[j]]
    return dict(affine_rho=max(per),critical_line_phase=branch,critical_slot=int(t),
        critical_epoch_seconds=packet.begin_seconds+t*900,per_slot_rho=per,
        changing_critical_loading_hours=float(sum(per)*.25),
        fixed_critical_line_loading_hours=float(all_line[:,j].sum()*.25),
        hard_violations=bad,violation_counts=dict(Counter(v['reason'] for v in bad)),
        PCC_input='EXECUTED_OCCUPANCY_EXACT_C1_PQ;ORIGINAL_SIGNED_16FACE_RESPONSE',
        Fresh_AC=False,partial_slots=len(p))


def summarize(result,reference,packet):
    canary=result['tracking_canary'];begin,end=canary['begin'],canary['end']
    occupied,compute=separated_occupancy(result,begin,end);slots=len(result['occupancy_GPU'])
    target=reference.arrays;actual=result['physical'];c=result['carryout']['controller']
    unknown=unknown_actual_metrics(result);known={u for u,m in c['metadata'].items() if not m['origin_unknown']}
    unknown_uids={u for u,m in c['metadata'].items() if m['origin_unknown']}
    qos=result['qos_ledger'];times=canary['decision_seconds']
    errors=dict(GPU_L1_GPUh=float(np.abs(result['occupancy_GPU']-target['G_Total_Plan'][:slots]).sum()/4),
        Known_GPU_L1_GPUh=float(np.abs(occupied['Known']-target['G_Known_Plan'][:slots]).sum()/4),
        Unknown_GPU_L1_GPUh=float(np.abs(occupied['Unknown']-target['G_Unknown_Q50_Plan'][:slots]).sum()/4),
        PCC_P_L1_kWh=float(np.abs(actual['PCC_P_kw']-target['PCC_P_Plan'][:slots]).sum()/4),
        PCC_Q_L1_kvarh=float(np.abs(actual['PCC_Q_kvar']-target['PCC_Q_Plan'][:slots]).sum()/4))
    future=target['G_Unknown_Q50_Plan'][:slots].sum(axis=1)/4
    available=[]
    for t in range(slots):
        until=begin+(t+1)*900
        # Only UIDs observed within this completed replay; prefix restriction
        # models arrival availability, never exposes them to the controller.
        available.append(sum(m['gpu']*max(0,m['t50_seconds']-c['requests'][u]['metadata'].get('elapsed_compute_seconds',0))/3600
            for u,m in c['metadata'].items() if u in unknown_uids and c['requests'][u]['submit']<until))
    bound=np.maximum(0,np.cumsum(future)-np.asarray(available))
    residual=np.maximum(0,target['G_Total_Plan'][:slots]-occupied['Known'])
    errors.update(negative_residual_clamped_GPUh=float(np.maximum(0,occupied['Known']-target['G_Total_Plan'][:slots]).sum()/4),
        residual_target_GPUh=float(residual.sum()/4),
        unarrived_nominal_cumulative_shortfall_GPUh=bound.tolist(),
        arrival_bound_scope='NOMINAL_VOLUME_ONLY;Q50_OVERRUN_CAN_SUPPLY_EXTRA;NOT_A_FUTURE_ARRIVAL_LOOKUP')
    states=Counter(m['state'] for m in c['metadata'].values())
    metrics=dict(label=canary['label'],lineage=canary['lineage'],new_A1_status=canary['new_A1_status'],
        Known_observed_UIDs=len(known),Unknown_observed_UIDs=len(unknown_uids),
        Known_optimized_observed_UIDs=len(known & set(reference.commands)),
        Known_command_SHA_unchanged=c['tracking_state']['Known_schedule_sha']==reference.identity['Known_commands_SHA'],
        Known_command_execution_failures=sum(e['event']=='KNOWN_COMMAND_EXECUTION_FAILED' for e in result['job_event_ledger']),
        Known_plan_start_deviations=sum(r.get('plan_actual_start_deviation_seconds',0)!=0 for r in result['queue_ledger'] if r['job_uid'] in known),
        unknown=unknown,errors=errors,grid=grid_diagnostic(packet,actual['PCC_P_kw']),
        Known_actual_compute_GPUh=float(compute['Known'].sum()/4),
        Unknown_actual_compute_GPUh=float(compute['Unknown'].sum()/4),
        Known_occupation_GPUh=float(occupied['Known'].sum()/4),Unknown_occupation_GPUh=float(occupied['Unknown'].sum()/4),
        known_unknown_overlap_UIDs=len(known & unknown_uids),states=dict(states),
        carry_unfinished_UIDs=sum(r['unfinished'] for r in qos),
        carry_nominal_remaining_GPUh=sum(m['gpu']*max(0,m['t50_seconds']-m.get('accumulated_compute_seconds',0))/3600
            for m in c['metadata'].values() if m['state']!='COMPLETED'),
        QoS_intentional_budget_excess_UIDs=sum(r['total_intentional_burden_seconds']>r['budget_seconds']+1e-9 for r in qos),
        intentional_delay_seconds=sum(r['intentional_start_delay_seconds'] for r in qos),
        unavoidable_queue_seconds=sum(r.get('unavoidable_queue_seconds',0) for r in result['queue_ledger']),
        latest_start_excess_UIDs=sum(r['latest_start_excess_seconds']>0 for r in qos),
        observed_completion_deadline_excess_UIDs=sum((r.get('actual_completion_deadline_excess_seconds') or 0)>0 for r in qos),
        decision_mean_seconds=None if not times else float(np.mean(times)),
        decision_P50_seconds=None if not times else float(np.median(times)),
        decision_P95_seconds=None if not times else float(np.percentile(times,95)),
        decision_max_seconds=None if not times else float(max(times)),decision_calls=len(times),
        candidate_evaluations=sum(a['decision']['candidate_count'] for a in canary['policy_audit']),
        controller_global_optimizer_calls=0,replay_wall_seconds=canary['wall_seconds'],
        Full96_Actual_PASS=False,Fresh_AC_rho=None,actual_power_from_occupancy=True,
        CDF_risk_scope='ORIGINAL_NOMINAL_CDF_FROZEN;OBSERVED_QUEUE_START_DEADLINE_EXCESSES_SEPARATE_NO_PROBABILITY_GUARANTEE')
    return metrics,occupied,compute
