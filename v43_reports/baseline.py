"""Independent event integrals, Source constraints and exact C1 power audit."""
from pathlib import Path
from datetime import datetime
import numpy as np
import psutil

from v43.common import DOC,read,record,verify_records,atomic,now


def report(attempt):
    attempt=Path(attempt);start=read(attempt/'START.json')
    if psutil.pid_exists(start['pid']) and psutil.Process(start['pid']).create_time()==start['process_created']:
        raise RuntimeError('BASELINE_REPORT_REQUIRES_OFFICIAL_WORKER_EXIT')
    verify_records(start['sources']);result=read(attempt/'RESULT.json');rec=read(attempt/'RECONCILIATION.json')
    if rec['Native_calls'] or rec['inflight'] is not None:raise ValueError('NATIVE0_RECONCILIATION_REQUIRED')
    if start['control_variant'] is not None or start['execution_mode']!='GRID_BLIND_EVENT_FCFS':
        raise ValueError('NO_C0_OR_C1_IN_BASELINE')
    case=read(attempt/'CASE/CASE_BINDINGS.json');verify_records(case['source_receipts'])
    plan=read(case['source_receipts'][0]['path']);source_actual=read(case['source_receipts'][1]['path'])
    source={r['job_uid']:r for r in plan['known_population']+source_actual['post_issue_arrivals']}
    known={r['job_uid'] for r in plan['known_population']};unknown=set(source)-known
    event=read(attempt/'ACTUAL_EVENT_LEDGERS.json');rows={r['job_uid']:r for r in event['queue_ledger']}
    if set(source)!=set(rows):raise ValueError('BASELINE_KNOWN_UNKNOWN_UID_ROSTER_DRIFT')
    public=read(attempt/'SIMULATOR_PRIVATE_CARRYOUT.json')['controller'];assigned=public['reference']['assigned']
    issue=datetime.fromisoformat(plan['issue_time']).timestamp();end=issue+120*900
    with np.load(attempt/'ACTUAL_PHYSICAL.npz',allow_pickle=False) as z:
        arrays={k:z[k].copy() for k in z.files}
    sites=list(map(str,arrays['sites']));occupancy=np.zeros((120,len(sites)));compute=np.zeros_like(occupancy)
    boundaries=[];qos_breaches=[]
    def integrate(target,site,left,right,gpu):
        left=max(issue,left);right=min(end,right)
        for t in range(max(0,int((left-issue)//900)),min(120,int(np.ceil((right-issue)/900)))):
            duration=max(0.,min(right,issue+(t+1)*900)-max(left,issue+t*900))
            target[t,sites.index(site)]+=gpu*duration/900
    for uid,r in rows.items():
        if r['GPU_gang']!=source[uid]['GPU_gang']:raise ValueError('SOURCE_GPU_GANG_CHANGED')
        if r.get('intentional_delay_seconds',0) or r['migration_count'] or r.get('policy_action') not in (None,'START'):
            raise ValueError('FLEXIBILITY_ACTION_IN_BASELINE')
        begin=r['admitted_time']
        if begin is None:continue
        site=r['site'];gpu=r['GPU_gang']
        if (site not in source[uid]['compatible_sites'] or source[uid].get('source_site') is not None
                and site!=source[uid]['source_site']):
            raise ValueError('BASELINE_SOURCE_SITE_OR_COMPATIBILITY_CHANGED')
        if gpu>max(plan['rack_compatibility'][site]):raise ValueError('SOURCE_RACK_GANG_VIOLATION')
        if begin<r['submit_time']:raise ValueError('FUTURE_SUBMISSION_USED')
        release=r['release_control_time'] if r['release_control_time'] is not None else end
        completion=r['completion_observed_time'] if r['completion_observed_time'] is not None else end
        integrate(occupancy,site,begin,release,gpu);integrate(compute,site,begin,completion,gpu)
        if min(end,release)>max(issue,begin):
            boundaries += [(max(issue,begin),1,site,gpu),(min(end,release),0,site,-gpu)]
    use={s:0 for s in sites}
    for at,kind,site,delta in sorted(boundaries):
        use[site]+=delta
        if not 0<=use[site]<=plan['capacities'][site]:raise ValueError('INDEPENDENT_INSTANTANEOUS_GPU_CAPACITY_VIOLATION')
    if any(use.values()):raise ValueError('INDEPENDENT_GPU_INTEGRAL_NOT_CLOSED')
    # Different summation orders may differ by roundoff; compare the complete
    # independently integrated trajectories, not just their daily totals.
    errors={k:float(abs(a-arrays[k]).max()) for k,a in [('GPU',occupancy),('compute_GPU',compute)]}
    if max(errors.values())>1e-10:raise ValueError('PUBLIC_UID_EVENT_TO_GPU_INTEGRAL_MISMATCH')
    from v43_actual.case import power_model
    from v43_actual.observations import load_observations
    weather=load_observations(begin=issue,end=end)
    model,_=power_model(read(case['source_receipts'][3]['path']),plan['capacities'])
    exact=model.recompute(arrays['GPU'],sites,[weather.at(issue+t*900,observed_now=issue+t*900)['weather']['values'] for t in range(120)])
    power_exact={k:np.array_equal(exact[k],arrays[k]) for k in ('IT_kw','PCC_P_kw','PCC_Q_kvar')}
    if not all(power_exact.values()):raise ValueError('EXACT_ORIGINAL_C1_POWER_RECOMPUTATION_FAILED')
    if event['migration_receipts'] or event['rule_consumption_receipt']:raise ValueError('BASELINE_CONTAINS_POLICY_OR_MIGRATION_RECEIPTS')
    fresh=read(attempt/'FRESH_ORIGINAL7_AC.json')['physical_steps'][24:]
    if len(fresh)!=96 or not all(r['PASS'] for r in fresh):raise ValueError('FRESH_ACTUAL96_FAILED')
    groups={}
    for label,uids in [('Known',known),('Unknown',unknown)]:
        selected=[r for u,r in rows.items() if u in uids]
        groups[label]=dict(UIDs=len(selected),started=sum(r['admitted_time'] is not None for r in selected),
            completed=sum(r['latest_state']=='COMPLETED' for r in selected),carryout=sum(r['carryout'] for r in selected))
    payload=dict(UTC=now(),PASS=True,arm=start['arm'],control_variant=None,
        scope='INDEPENDENT_BASELINE_UID_GPU_RESOURCE_C1_POWER_AND_FRESH96_NOT_SLA_OR_CAUSAL_CERTIFICATE',
        result=record(attempt/'RESULT.json'),case=record(attempt/'CASE/CASE_BINDINGS.json'),groups=groups,
        independent_UID_GPU_integral_max_abs_errors=errors,exact_C1_power_arrays_bit_exact=power_exact,
        instantaneous_GPU_capacity_PASS=True,Source_rack_and_compatibility_PASS=True,
        Pre_site=0,Time_shift=0,Migration=0,C0_policy_calls=0,C1_policy_calls=0,
        candidate_Current_AC_calls=0,candidate_past_replays=0,
        QoS_deadline_PASS='NOT_CERTIFIED_BY_THIS_RESOURCE_AUDIT',
        Actual_daily_occupation_GPUh=float(arrays['GPU'][24:].sum()/4),
        Actual_daily_compute_GPUh=float(arrays['compute_GPU'][24:].sum()/4),
        Fresh96_PASS=True,peak_line_phase_loading=max(r['maximum_phase_line_loading'] for r in fresh),
        Source_initial_sites_certified=False,initial_source_assumptions='44_MODEL_ASSUMED_210_RETAINED',
        FORECAST_CAUSAL_AVAILABILITY='NOT_CERTIFIED',CAUSAL_PASS=False,
        Native_calls=0,Native_seconds=0.,inflight=None)
    out=attempt/'INDEPENDENT_BASELINE_REPORT.json'
    if out.exists():raise ValueError('INDEPENDENT_BASELINE_REPORT_ALREADY_SEALED')
    atomic(out,payload);atomic(DOC/f'V43_MAY01_{start["arm"]}_BASELINE_CERTIFICATION.json',dict(report=record(out),PASS=True))
    return payload


if __name__=='__main__':
    import sys
    report(sys.argv[1])
