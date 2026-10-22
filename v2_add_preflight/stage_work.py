"""Independent event-interval work/GPU/WAN replay, including migration.

Private realized service is read only by the post-execution validator. The
public interval constructor is also used by current-AC history IO and never
receives an environment, a future completion or private remaining service.
"""
from collections import defaultdict
import math
import numpy as np
from .stage_common import *


def intervals(uid,*,begin,end,initial,events,migrations):
    observed=[e for e in events if e['uid']==uid and e['time_seconds']<=end]
    starts=[e for e in observed if e['event']=='RUNNING']
    if initial is not None:site,a=initial;a=begin
    elif starts:assert len(starts)==1;site,a=starts[0]['site'],starts[0]['time_seconds']
    else:return [],[]
    compute=[];hold=[]
    for m in sorted((m for m in migrations if m['job_id']==uid),key=lambda m:m['physical_checkpoint_seconds']):
        cp=float(m['physical_checkpoint_seconds']);restart=float(m['times']['restart_end'])
        if cp>end:raise ValueError('FUTURE_MIGRATION_IN_PUBLIC_HISTORY')
        assert cp>=a and m['source']==site and restart>=cp
        checkpoints=[e for e in observed if e['event']=='CHECKPOINT' and e['physical_checkpoint_seconds']==cp]
        assert len(checkpoints)==1
        compute.append((a,cp,site));hold.append((a,cp,site))
        for s in m['segments']:
            if s['resource'].startswith('gpu:'):
                hold.append((max(cp,s['begin']),min(end,restart,s['end']),s['resource'][4:]))
        if restart>end:return compute,hold
        resumes=[e for e in observed if e['event']=='DESTINATION_RUNNING' and e['time_seconds']==restart and e['destination']==m['destination']]
        assert len(resumes)==1
        site,a=m['destination'],restart
    completed=[e for e in observed if e['event']=='COMPLETION_OBSERVED']
    assert len(completed)<=1
    stop=completed[0]['time_seconds'] if completed else end
    release=completed[0]['release_control_seconds'] if completed else end
    assert stop>=a and release>=stop
    compute.append((a,min(end,stop),site));hold.append((a,min(end,release),site))
    return compute,hold


def integrate(target,rows,gpu,sites,begin):
    for a,b,site in rows:
        if b<=a:continue
        assert site in sites
        for t in range(max(0,int((a-begin)//900)),min(len(target),int(math.ceil((b-begin)/900)))):
            target[t,sites.index(site)]+=gpu*max(0.,min(b,begin+900*(t+1))-max(a,begin+900*t))/900.


def validate(actual,args,*,allow_known_research=False):
    begin,end=args['begin'],args['end'];sites=actual['sites'];n=int((end-begin)/900)
    assert n*900==end-begin
    compute=np.zeros((n,len(sites)));occupation=np.zeros_like(compute)
    state=actual['carryout']['controller'];remaining=actual['carryout']['simulator_only_remaining_compute_seconds']
    requests={r.uid:r for r in [*args['requests'],*(a[0] for a in args['running'])]}
    initial={r.uid:(site,begin) for r,site,start in args['running']};rows=[];wan=defaultdict(list);active=[]
    for uid,r in requests.items():
        c,h=intervals(uid,begin=begin,end=end,initial=initial.get(uid),events=actual['job_event_ledger'],migrations=actual['migration_receipts'])
        assert all(site in r.compatible for a,b,site in c+h)
        integrate(compute,c,r.gpu,sites,begin);integrate(occupation,h,r.gpu,sites,begin)
        worked=math.fsum(max(0.,b-a) for a,b,s in c)
        required=(args['environment'].running_completion(uid)-begin if uid in initial else args['environment'].started(uid,0.))
        rem=remaining.get(uid,required)
        elapsed=float(r.metadata.get('elapsed_compute_seconds',0)) if uid in initial else 0.
        accumulated=state['metadata'][uid]['accumulated_compute_seconds']-elapsed
        rows.append(dict(uid=uid,GPU=r.gpu,required_remaining_at_issue_seconds=required,
            worked_seconds=worked,remaining_seconds=rem,work_residual_seconds=worked+rem-required,
            accumulated_residual_seconds=accumulated-worked,
            carryout=state['episode_jobs'][uid]['latest_observed_state']!='COMPLETED'))
    for m in actual['migration_receipts']:
        uid=m['job_id'];cap=state['metadata'][uid]['migration_capability'];r=requests[uid]
        assert m['capability_source_sha']==cap['source_sha'] and cap['checkpoint_authorized']
        assert m['destination'] in cap['allowed_destinations'] and m['destination'] in r.compatible
        assert m['accumulated_compute_seconds']>=1800 and abs(m['accumulated_compute_seconds']%1800)<1e-7
        assert m['control_checkpoint_seconds']==math.ceil(m['physical_checkpoint_seconds']/900)*900
        w=[s for s in m['segments'] if s['resource'].startswith('wan:')]
        expected={'wan:'+cap['wan_path']}|{'wan:LINK::'+link for link in cap.get('route_links',[])}
        assert len(w)==len(expected) and {s['resource'] for s in w}==expected
        for s in w:
            assert s['quantity']==cap['bandwidth_bytes_per_second'] and s['begin']==m['times']['transfer_start'] and s['end']==m['times']['transfer_end']
            assert s['quantity']*(s['end']-s['begin'])>=cap['payload_bytes']
            wan[s['resource'][4:]].append((s['begin'],s['end'],s['quantity']))
        aa=[s for s in m['segments'] if s['resource']=='active:WAN'];assert len(aa)==1
        assert aa[0]['quantity']==1 and aa[0]['begin']==w[0]['begin'] and aa[0]['end']==w[0]['end']
        active.append((aa[0]['begin'],aa[0]['end'],1.))
    def maximum(segments):
        times=sorted(set(a for a,b,q in segments)|set(b for a,b,q in segments))
        return max([0.]+[math.fsum(q for a,b,q in segments if a<=t<b) for t in times])
    wan_max={path:maximum(ss) for path,ss in wan.items()}
    assert all(v<=args['wan_capacities'][path]+1e-8 for path,v in wan_max.items())
    assert maximum(active)<=1
    error=float(np.max(abs(compute-actual['compute_occupancy_GPU'])))
    occupation_error=float(np.max(abs(occupation-actual['occupancy_GPU'])))
    work=max(abs(r['work_residual_seconds']) for r in rows);accum=max(abs(r['accumulated_residual_seconds']) for r in rows)
    caps=np.array([args['capacities'][s] for s in sites]);capacity=bool(np.all(occupation<=caps+1e-8))
    excess=[r for r in actual['qos_ledger'] if r['total_intentional_burden_seconds']>r['budget_seconds']+1e-6]
    unknown_excess=[r for r in excess if state['metadata'][r['uid']]['origin_unknown']]
    strict=not excess
    late_start=[r for r in actual['qos_ledger'] if r['latest_start_excess_seconds']>1e-6]
    late_completion=[r for r in actual['qos_ledger'] if (r['actual_completion_deadline_excess_seconds'] or 0)>1e-6]
    return dict(PASS=work<1e-5 and accum<1e-5 and error<1e-8 and occupation_error<1e-8 and capacity and (strict or allow_known_research and not unknown_excess),
        jobs=len(rows),migrations=len(actual['migration_receipts']),work_residual_max_seconds=work,
        accumulated_compute_residual_max_seconds=accum,reconstructed_compute_GPU_max_error=error,
        reconstructed_occupation_GPU_max_error=occupation_error,capacity_PASS=capacity,
        compute_GPUh=float(compute.sum()*.25),occupation_GPUh=float(occupation.sum()*.25),
        required_service_GPUh=sum(r['GPU']*r['required_remaining_at_issue_seconds']/3600 for r in rows),
        remaining_service_GPUh=sum(r['GPU']*r['remaining_seconds']/3600 for r in rows),
        Source_QoS_PASS=strict,Source_QoS_excess=excess,Known_research_policy_enabled=allow_known_research,
        Source_QoS_scope='Original intentional burden budget; source window/controller constraints are retained separately',
        Source_customer_SLA_certified=False,
        actual_start_window_excess=late_start,actual_completion_deadline_excess=late_completion,
        actual_window_and_completed_deadline_compliance_PASS=not late_start and not late_completion,
        exogenous_wait_and_realized_runtime_not_erased_or_reclassified_as_intentional_QoS=True,
        WAN_maxima=wan_max,maximum_active_transfers=maximum(active),private_service_read_by_controller=False),rows


def certify_baseline():
    from .full_jobs import prepare
    from .full_common import RUN as LEGACY
    with measured('ACTUAL_INDEPENDENT_WORK_REPLAY.json') as (report,start):
        args=prepare(day_inputs(),'STAGE_INDEPENDENT_WORK')
        actual=read(LEGACY/'jobs/BASE/EVENTS.json')
        with np.load(LEGACY/'jobs/BASE/PHYSICAL.npz') as z:
            actual.update(occupancy_GPU=z['GPU'],compute_occupancy_GPU=z['compute_GPU'])
        cert,rows=validate(actual,args);assert cert['PASS']
        report.update(PASS=True,baseline=cert,actual_migration_fixture_PASS=False,
            scope='Independent full baseline replay; nonzero migration event fixture still required')


if __name__=='__main__':certify_baseline()
