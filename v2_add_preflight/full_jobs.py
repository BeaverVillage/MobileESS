"""Exact r043 baseline controller; same-policy replays and whole-work checks."""
import copy,types,json
from pathlib import Path
import numpy as np
from .full_common import *

def prepare(day,tag,selected=None):
    from .prestart_aidc import prepare_case
    # Namespace routing only: preserve all a4dabafb evidence and original source.
    fn=types.FunctionType(prepare_case.__code__,dict(prepare_case.__globals__,RUN=RUN,put=put),argdefs=prepare_case.__defaults__)
    args=fn(day,selected or {},tag)
    from v43_corrective.reference import CorrectedReferenceScheduler
    args['reference']=CorrectedReferenceScheduler.from_dict(args['reference'].to_dict())
    # Dated source bug: observed Running jobs excluded from Planning can have
    # positive remaining service but no Planning WINDOW. Continue those exact
    # initial episodes through the existing external-Running contract (zero
    # flexibility), rather than inventing a finite optimization window or
    # dropping their physical GPU/service. Source originally selected only n=0.
    native=read(day['files']['native']['path']);qos=args['qos_window_provider'];by={r['job_uid']:r for r in native['known_population']}
    extra=[]
    for request,site,start in args['running']:
        r=by[request.uid]
        if request.uid not in qos.windows and not r['planning_eligible']:
            assert not request.metadata['Can_Checkpoint_Migrate']
            assert request.uid not in args['known_schedule']
            extra.append(request.uid)
    added=sorted(set(extra)-set(qos.external_running));parent=dict(case_sha=qos.case_sha,provider_sha=qos.provider_sha)
    qos.external_running=frozenset(set(qos.external_running)|set(extra))
    if added:
        qos.provider_sha=digest(dict(parent_provider=parent['provider_sha'],positive_service_external_Running=added,
            contract='EXTERNAL_OBSERVED_RUNNING_CONTINUATION_ONLY_ZERO_FLEXIBILITY'))
        qos.case_sha=digest(dict(parent_case=parent['case_sha'],provider_sha=qos.provider_sha))
    put('AIDC_'+tag+'_EXTERNAL_RUNNING_CONTINUATION.json',dict(UIDs=added,count=len(added),all_external_running=len(qos.external_running),
        parent=parent,adapter_case_sha=qos.case_sha,adapter_provider_sha=qos.provider_sha,
        source_selection='non-Planning observed initial Running with no WINDOW; positive remaining service retained',
        existing_provider_contract='EXTERNAL_OBSERVED_RUNNING_CONTINUATION_ONLY',new_Planning_windows=0,new_flexibility_seconds=0,
        site_or_service_changed=False,source_window_module=record(ROOT/'v43_actual/windows.py')))
    return args

def baseline(args,day):
    from v43_actual.vendor.actual import run_actual
    from v43_baseline.worker import BaselineController
    racks=read(day['files']['planning_input']['path'])['rack_compatibility']
    def factory(*a,**kw):return BaselineController(*a,rack_limits=racks,**kw)
    return run_actual(**dict(args,arm='B0'),controller_class=factory)

def save(tag,x):
    p=RUN/'jobs'/tag;p.mkdir(parents=True,exist_ok=True)
    np.savez_compressed(p/'PHYSICAL.npz',GPU=x['occupancy_GPU'],compute_GPU=x['compute_occupancy_GPU'])
    (p/'EVENTS.json').write_text(json.dumps({k:v for k,v in x.items() if k not in ('occupancy_GPU','compute_occupancy_GPU','physical')}),encoding='utf-8')
    return dict(arrays=record(p/'PHYSICAL.npz'),events=record(p/'EVENTS.json'))

def conservation(x,args):
    """Independent interval integration and per-UID work/carryout, no policy reads.

    This validator deliberately rejects migration traces until transfer phase
    intervals have their own independent reconstruction. It cannot certify a
    future FULL migration result by accepting a zero-migration baseline.
    """
    carry=x['carryout'];state=carry['controller'];remaining=carry['simulator_only_remaining_compute_seconds']
    # The environment has the original Source service; use its public simulator
    # method outside any policy to certify work, including unstarted carryout.
    requests={r.uid:r for r in [*args['requests'],*(v[0] for v in args['running'])]}
    running={r.uid:(site,start) for r,site,start in args['running']}
    events=x['job_event_ledger'];observed={r['uid']:r for r in events if r['event']=='RUNNING'}
    completed={r['uid']:r['time_seconds'] for r in events if r['event']=='COMPLETION_OBSERVED'}
    released={r['uid']:r['time_seconds'] for r in events if r['event']=='GPU_RELEASE_CONTROL'}
    result=[];gpu=np.zeros((120,len(x['sites'])));compute=np.zeros_like(gpu);begin=args['begin'];end=args['end']
    def integrate(a,b,site,g,target):
        for t in range(120):
            target[t,x['sites'].index(site)]+=g*max(0.,min(b,begin+900*(t+1))-max(a,begin+900*t))/900
    jobs=state['episode_jobs']
    for uid,r in requests.items():
        total=(args['environment'].running_completion(uid)-begin if uid in running else args['environment'].started(uid,0.))
        if uid in running:site,a=running[uid];a=begin
        elif uid in observed:site=observed[uid]['site'];a=observed[uid]['time_seconds']
        else:site=None;a=end
        worked=max(0.,min(end,completed.get(uid,end))-a)
        rem=remaining.get(uid,total)
        if site is not None:
            integrate(a,completed.get(uid,end),site,r.gpu,compute)
            integrate(a,released.get(uid,end),site,r.gpu,gpu)
        elapsed=float(getattr(r,'metadata',{}).get('elapsed_compute_seconds',0)) if uid in running else 0.
        accumulated=state['metadata'][uid]['accumulated_compute_seconds']-elapsed
        result.append(dict(uid=uid,GPU=r.gpu,required_remaining_at_issue_seconds=total,worked_seconds=worked,
            simulator_remaining_seconds=rem,work_residual_seconds=worked+rem-total,
            accumulated_compute_residual_seconds=accumulated-worked,started=site is not None,
            completed=uid in completed,carryout=jobs[uid]['latest_observed_state']!='COMPLETED',
            compatible=site is None or site in r.compatible))
    err=float(np.max(abs(compute-x['compute_occupancy_GPU'])));oe=float(np.max(abs(gpu-x['occupancy_GPU'])))
    qos=[r for r in x['qos_ledger'] if r['total_intentional_burden_seconds']>r['budget_seconds']+1e-6]
    maximum=max(abs(r['work_residual_seconds']) for r in result)
    acerr=max(abs(r['accumulated_compute_residual_seconds']) for r in result)
    capacity=np.array([args['capacities'][s] for s in x['sites']])
    cert=dict(PASS=not x['migration_receipts'] and maximum<1e-5 and acerr<1e-5 and err<1e-8 and oe<1e-8
        and not qos and all(r['compatible'] for r in result) and bool(np.all(gpu<=capacity+1e-8)),
        jobs=len(result),completed=sum(r['completed'] for r in result),carryout=sum(r['carryout'] for r in result),
        compute_GPUh=float(compute.sum()*.25),occupation_GPUh=float(gpu.sum()*.25),
        remaining_service_GPUh=sum(r['GPU']*r['simulator_remaining_seconds']/3600 for r in result),
        required_service_GPUh=sum(r['GPU']*r['required_remaining_at_issue_seconds']/3600 for r in result),
        work_residual_max_seconds=maximum,accumulated_residual_max_seconds=acerr,
        reconstructed_compute_GPU_max_error=err,reconstructed_occupation_GPU_max_error=oe,
        strict_intentional_QoS_excess=len(qos),migration_receipts=len(x['migration_receipts']),
        no_private_service_controller_reads=True,Source_customer_permission_claim=False,
        certification_scope='No-migration exact private-service accounting; FULL finite-WINDOWS joint resources certified separately; does not certify unexecuted migration/WAN')
    return cert,result

def study():
    from collections import Counter
    from dataclasses import asdict
    from .prestart_acceptance import source_domain,certify
    from v42_job_capability import Option,validate,resources_used,resource_limit
    from collections import defaultdict
    init();resources();day=day_input('2025-05-01');args=prepare(day,'ACCOUNTING')
    base=read(RUN/'jobs/BASE/EVENTS.json');arrays=np.load(RUN/'jobs/BASE/PHYSICAL.npz')
    base.update(occupancy_GPU=arrays['GPU'],compute_occupancy_GPU=arrays['compute_GPU'])
    cert,rows=conservation(base,args);put('B0_INDEPENDENT_FULL_WORK.json',cert);table('B0_INDEPENDENT_PER_JOB_WORK.csv',rows)
    native=read(day['files']['native']['path']);windows=read(day['files']['windows']['path'])
    jobs,bounds,seconds,r,raw=source_domain(native,windows)
    reference={u:asdict(Option(j.reference_start,j.reference_site,((j.reference_site,j.reference_start,j.reference_start+j.service_slots),))) for u,j in jobs.items()}
    put('ORIGINAL_FULL_REFERENCE_ACCEPTANCE.json',certify(reference,native,windows,identity={},expected_identity={}))
    usage=defaultdict(float)
    for uid,j in jobs.items():
        for key,value in resources_used(j,Option(**reference[uid])).items():usage[key]+=value
    selected=None;tested=[];census=[]
    for uid,j in sorted(jobs.items()):
        row=dict(uid=uid,state=j.state,GPU=j.gpu,reference_start=j.reference_start,preplace_options=0,shift_options=0)
        row['shift_options']=sum(s!=j.reference_start for s in bounds[uid].allowed_starts)
        if j.state=='PENDING':
            for site in sorted(set(j.initial_sites)-{j.reference_site}):
                o=Option(j.reference_start,site,((site,j.reference_start,j.reference_start+j.service_slots),))
                try:validate(j,o,bounds[uid],r)
                except ValueError:continue
                row['preplace_options']+=1
                if selected is None:
                    old=resources_used(j,Option(**reference[uid]));new=resources_used(j,o)
                    bad=[dict(key=key,use=usage[key]-old.get(key,0)+new.get(key,0),limit=resource_limit(key,r))
                        for key in set(old)|set(new) if usage[key]-old.get(key,0)+new.get(key,0)>resource_limit(key,r)+1e-5]
                    tested.append(dict(uid=uid,site=site,PASS=not bad,violations=bad[:3]))
                    if not bad:
                        selected={uid:asdict(o)};selected_full=dict(reference);selected_full[uid]=asdict(o)
        census.append(row)
    table('AIDC_ORIGINAL_FULL_DOMAIN_CENSUS.csv',census);put('AIDC_ORIGINAL_FULL_FORCED_OPTION_CHECKS.json',tested)
    if selected is None:
        put('AIDC_SAME_POLICY_STUDY.json',dict(status='NO_JOINT_REFERENCE_PRESITE_WITNESS',census=census,global_inflexibility_proven=False));return
    put('AIDC_ORIGINAL_FULL_SELECTED_ACCEPTANCE.json',certify(selected_full,native,windows,identity={},expected_identity={}))
    # Both arms use the identical unmodified flexible controller. This pair is
    # separate from exact B0 FCFS; it must never be reported as B1-minus-B0.
    from v43_actual.vendor.actual import run_actual
    trial_args=prepare(day,'SAME_POLICY_PRESITE',selected)
    pairbase=run_actual(**dict(copy.deepcopy(args),arm='B1'))
    trial=run_actual(**dict(copy.deepcopy(trial_args),arm='B1'))
    fresh=run_actual(**dict(copy.deepcopy(trial_args),arm='B1'))
    reports={};artifacts={}
    for tag,x,a in [('SAME_POLICY_BASE',pairbase,args),('SAME_POLICY_PRESITE',trial,trial_args),('SAME_POLICY_FRESH',fresh,trial_args)]:
        c,rs=conservation(x,a);reports[tag]=c;table(tag+'_WORK.csv',rs);artifacts[tag]=save(tag,x)
    identical=np.array_equal(trial['occupancy_GPU'],fresh['occupancy_GPU']) and trial['job_event_ledger']==fresh['job_event_ledger']
    from .aidc_candidate import actual_c1
    bp,bq,bit=actual_c1(pairbase['occupancy_GPU'],pairbase['sites'],day);p,q,it=actual_c1(trial['occupancy_GPU'],trial['sites'],day)
    pth=RUN/'jobs/SAME_POLICY_POWER.npz';np.savez_compressed(pth,P=p,Q=q,base_P=bp,base_Q=bq,delta_P=p-bp,delta_Q=q-bq)
    table('AIDC_SAME_POLICY_POWER.csv',[dict(slot=t,evaluation_slot=t-24,reduction_kw=float(np.maximum(bp[t]-p[t],0).sum()),rebound_kw=float(np.maximum(p[t]-bp[t],0).sum()),signed_net_kw=float((p[t]-bp[t]).sum())) for t in range(120)])
    put('AIDC_SAME_POLICY_STUDY.json',dict(status='FINITE_SOURCE_FULL_PRESITE_REPLAY_NOT_A1_OR_B3',selected=selected,
        same_jobs_same_input_same_controller=True,baseline='Original B1 reference fallback; separately labelled, not original B0 FCFS',
        source_controller=record(ROOT/'v43_actual/vendor/actual.py'),Fresh_identical=identical,independent_work=reports,
        power=record(pth),artifacts=artifacts,nonzero_power=float(np.max(abs(p-bp))),
        daily_compute_GPUh_difference=reports['SAME_POLICY_PRESITE']['compute_GPUh']-reports['SAME_POLICY_BASE']['compute_GPUh'],
        research_Known_window_relaxation_used=False,strict_QoS_required=True,Source_customer_QoS_certified=False,
        GPU_scaling_run=False,grid120_AC_certified=False,full_optimizer_acceptance=False,Native_calls=0))
    print('FULL JOB STUDY',cert['PASS'],selected,identical,float(np.max(abs(p-bp))),flush=True)

def main():
    init();resources();day=day_input('2025-05-01');args=prepare(day,'EXACT_BASE')
    base=baseline(copy.deepcopy(args),day);fresh=baseline(copy.deepcopy(args),day)
    assert np.array_equal(base['occupancy_GPU'],fresh['occupancy_GPU'])
    assert base['job_event_ledger']==fresh['job_event_ledger']
    from .aidc_candidate import actual_c1
    p,q,it=actual_c1(base['occupancy_GPU'],base['sites'],day)
    old=np.load(DOC/'input/IEEE123_FROZEN_ELECTRICAL_INPUTS.npz')
    gp=np.load(Path('D:/smartds_gso_substation2_v44_r043_runtime/jobs/ACTUAL_PHYSICAL.npz'))
    err=float(np.max(abs(p-old['ACTUAL_AIDC_P_kw'])));ge=float(np.max(abs(base['occupancy_GPU']-gp['GPU'])))
    records=[save('BASE',base),save('BASE_FRESH',fresh)]
    folder=RUN/'jobs/BASE';np.savez_compressed(folder/'C1.npz',P=p,Q=q,IT=it,sites=np.array(base['sites']))
    put('B0_FCFS_EXACT_REPLAY.json',dict(PASS=err<1e-7 and ge<1e-9,baseline_P_max_error_kw=err,baseline_GPU_max_error=ge,
        independent_event_Fresh_identical=True,receipt=base['receipt'],records=records,
        source_controller=record(ROOT/'v43_baseline/worker.py'),source_admission=record(ROOT/'v42_capacity/actual.py'),
        corrected_reference=record(ROOT/'v43_corrective/reference.py'),same_jobs_same_input=True,Native_calls=0))
    put('WHOLE_WORK_ACCOUNTING_READBACK.json',dict(carryout_keys=list(base['carryout']['controller']),
        ledger_keys=list(base['carryout']['controller'].get('ledger',{})),simulator_remaining_count=len(base['carryout']['simulator_only_remaining_compute_seconds'])))
    print('EXACT FCFS',err,ge,flush=True)
if __name__=='__main__':
    import sys
    study() if len(sys.argv)>1 and sys.argv[1]=='study' else main()
