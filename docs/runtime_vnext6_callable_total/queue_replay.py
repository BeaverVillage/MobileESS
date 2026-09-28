"""Isolated April2 reservation replay. Never imports V42 controller or grid code."""
from paths import *
import math,sys
import numpy as np,pandas as pd
sys.path.insert(0,str(ROOT/'RUNTIME_PROVIDER'))
from provider import RuntimeProvider,running_proxy
ISSUE=pd.Timestamp('2025-04-01T08:00Z');END=ISSUE+pd.Timedelta(hours=30);H=120
CAP=NATIVE/'MobileESS_v41r2_780gpu_capacity_rebase/dayahead/artifacts/v41r2_780gpu_capacity_rebase/V41R2_780GPU_CAPACITY_AUTHORITY.json'
REF=WORK/'V42_RESPONSE_KERNEL_LOCAL/regeneration_002/2025-04-02/CAUSAL_REFERENCE.json'
EVENTS=WORK/'V42_RUNTIME_TEMPORAL_LOCAL/baseline_reproduction_001/2025-04-02/P2_GRID_RESPONSE_POLICY_EVENTS.parquet'
RAW42=WORK/'V42_FINAL_LOCAL/policy_raw_scanner_only.parquet'

def inputs():
    f=pd.read_parquet(RAW42,columns=['id','submit_time','gpus_requested','nodes_req','wallclock_seconds','qos','source_job_hash'],filters=[('submit_time','>',ISSUE),('submit_time','<',END)])
    f['id']=f.id.astype(str);f['tier']=f.qos.map(lambda q:0 if str(q).lower() in ['high','urgent'] else 1 if str(q).lower()=='normal' else 2 if str(q).lower()=='standby' else 3)
    f=f.sort_values(['submit_time','tier','id'],kind='stable').reset_index(drop=True)
    caps=np.array(list(read(CAP)['site_capacity'].values()),int);known=read(REF)['jobs']
    return f,caps,known
def base_occupancy(caps,known):
    occ=np.zeros((21000,len(caps)),dtype=np.int32);events={0}
    for j in known:
        if j['AIDC_site']=='UNASSIGNED':continue
        s=int(j['AIDC_site'][-2:])-1;occ[j['start_slot']:j['end_slot'],s]+=j['requested_GPU'];events.add(j['end_slot'])
    assert np.all(occ<=caps)
    return occ,events
def valid(r,caps):
    return pd.notna(r.gpus_requested) and pd.notna(r.nodes_req) and pd.notna(r.wallclock_seconds) and r.gpus_requested>0 and float(r.gpus_requested).is_integer() and r.nodes_req>0 and r.gpus_requested<=4*r.nodes_req and r.wallclock_seconds>0 and r.gpus_requested<=caps.max()
def planned(f,caps,known,q90,arm):
    occ,events=base_occupancy(caps,known);rows=[]
    for r in f.itertuples():
        arrival=math.ceil((r.submit_time-ISSUE).total_seconds()/900);in_day=arrival>=24 and r.submit_time>=ISSUE+pd.Timedelta(hours=6)
        if not valid(r,caps):
            if in_day:rows.append(dict(job_id=r.id,admitted=False,arm=arm))
            continue
        g=int(r.gpus_requested);duration=math.ceil((r.wallclock_seconds if arm=='W0' else q90)/900)
        chosen=None
        for t in sorted({arrival}|{t for t in events if arrival<t<=20000}):
            sites=np.flatnonzero((g<=caps)&np.all(occ[t:t+duration]+g<=caps,axis=0))
            if len(sites):chosen=t,int(sites[0]);break
        assert chosen is not None,'REFERENCE_HORIZON_EXHAUSTED'
        t,s=chosen;occ[t:t+duration,s]+=g;events.add(t+duration)
        assert np.all(occ[t:t+duration,s]<=caps[s])
        rows.append(dict(job_id=r.id,arm=arm,admitted=True,in_day=in_day,arrival_slot=arrival,start_slot=t,site=s,duration_slots=duration,gpu=g,
          requested_seconds=r.wallclock_seconds,planned_seconds=r.wallclock_seconds if arm=='W0' else q90,wait_seconds=t*900-(r.submit_time-ISSUE).total_seconds()))
    return pd.DataFrame(rows)
def summary(f,truth,arm,baseline=None):
    z=f[f.admitted&f.in_day.fillna(False)].copy();a=z.merge(truth,on='job_id',how='left',validate='one_to_one');m=a.runtime_seconds.notna();y=a.loc[m,'runtime_seconds'];q=a.loc[m,'planned_seconds'];g=a.loc[m,'gpu'];positive=y>0
    out=dict(arm=arm,admitted=len(z),jobs_start_lt_H=int((z.start_slot<H).sum()),jobs_start_ge_H=int((z.start_slot>=H).sum()),fraction_start_ge_H=float((z.start_slot>=H).mean()),
      reservation_GPUh=float((z.gpu*z.duration_slots/4).sum()),unrounded_reservation_GPUh=float((z.gpu*z.planned_seconds/3600).sum()),
      queue_mean_seconds=float(z.wait_seconds.mean()),queue_median_seconds=float(z.wait_seconds.median()),queue_p95_seconds=float(z.wait_seconds.quantile(.95)),
      mature_truth_N=int(m.sum()),unresolved_truth_N=int((~m).sum()),requested_actual_ratio_median=float((a.loc[m,'requested_seconds'][positive]/y[positive]).median()),Q90_actual_ratio_median=float((q[positive]/y[positive]).median()),
      runtime_overrun_fraction=float((y>q).mean()),GPU_weighted_overrun_fraction=float(np.average(y>q,weights=g)),overrun_GPUh=float((np.maximum(y-q,0)*g/3600).sum()),
      scope='RESEARCH_ONLY_ARCHIVED_REQUEST_RESOURCE_WEIGHTS; known332 reservations fixed; arriving jobs only duration intervention; no grid/optimizer')
    if baseline is not None:
        pair=z[['job_id','start_slot']].merge(baseline[['job_id','start_slot']],on='job_id',suffixes=('_ML','_W0'))
        late=pair.start_slot_W0>=H;rec=late&(pair.start_slot_ML<H);lost=(~late)&(pair.start_slot_ML>=H)
        out.update(recovered_jobs=int(rec.sum()),lost_into_post_H_jobs=int(lost.sum()),fraction_recovered_among_W0_late=float(rec.sum()/late.sum()),net_start_lt_H_change=int(rec.sum()-lost.sum()))
    return out

def execution_stress(f,caps,known,q90,truth,arm):
    """Scheduler only gets Boolean completion observations at each slot.

    Pending jobs keep submission/tier/ID order. Each control tick can start a
    pending job at the current slot if its full planned reservation fits.
    Fixed known-job reservations are exogenous. Any collision with them is
    reported, never hidden by releasing an overrun job. This is a stress replay,
    not an assertion of exact V42 temporal-controller behavior.
    """
    occ,_=base_occupancy(caps,known);entries=[]
    labels=truth.set_index('job_id').runtime_seconds.to_dict()
    for r in f.itertuples():
        if not valid(r,caps):continue
        entries.append(dict(job_id=r.id,arrival=math.ceil((r.submit_time-ISSUE).total_seconds()/900),gpu=int(r.gpus_requested),plan=r.wallclock_seconds if arm=='W0' else q90,requested_seconds=r.wallclock_seconds,
          in_day=r.submit_time>=ISSUE+pd.Timedelta(hours=6),submit_time=r.submit_time))
    # Retrospective truth stays inside this observer; planner never receives duration or future end.
    def observed_complete(uid,elapsed):return uid in labels and elapsed>=labels[uid]
    pending=[];active=[];finished=[];i=0;extensions=0;violations=0;peak=0;limit=20000
    for t in range(limit+1):
        alive=[]
        for j in active:
            elapsed=(t-j['start_slot'])*900
            if observed_complete(j['job_id'],elapsed):
                occ[t:j['reserved_until'],j['site']]-=j['gpu'];j['completed_slot']=t;finished.append(j);continue
            if t>=j['reserved_until']:
                contract=running_proxy(j['plan'],elapsed,True);assert contract['retain_GPU'] and contract['OVERRUN'] and contract['migration_recommendation']=='STAY'
                occ[t:t+1,j['site']]+=j['gpu'];j['reserved_until']=t+1;extensions+=1
            alive.append(j)
        active=alive
        excess=np.maximum(occ[t]-caps,0);violations+=int(np.any(excess));peak=max(peak,int(excess.max()))
        while i<len(entries) and entries[i]['arrival']<=t:pending.append(entries[i]);i+=1
        waiting=[]
        for j in pending:
            d=math.ceil(j['plan']/900);sites=np.flatnonzero((j['gpu']<=caps)&np.all(occ[t:t+d]+j['gpu']<=caps,axis=0))
            if not len(sites):waiting.append(j);continue
            s=int(sites[0]);occ[t:t+d,s]+=j['gpu'];j.update(start_slot=t,site=s,reserved_until=t+d)
            active.append(j)
        pending=waiting
        if i==len(entries) and not pending and not active:break
        # Never invent a May outcome: missing truth stays occupied to horizon.
    allrows=finished+active+pending
    for j in allrows:j['completed_in_simulation']='completed_slot' in j;j['arm']=arm
    out=pd.DataFrame(allrows);out.to_parquet(ROOT/f'APRIL_EXECUTION_STRESS_{arm}.parquet',index=False)
    z=out[out.in_day];starts=z.get('start_slot',pd.Series(index=z.index,dtype=float))
    return dict(arm=arm,N=len(z),started=int(starts.notna().sum()),start_lt_H=int(starts.lt(H).sum()),start_ge_H=int(starts.ge(H).sum()),not_started=int(starts.isna().sum()),
      extension_events=extensions,capacity_violation_control_slots=violations,max_excess_GPU=peak,
      unresolved_active_at_stop=len(active),pending_at_stop=len(pending),stop_slot=t,truth_missing_jobs=sum(j['job_id'] not in labels for j in entries),
      no_future_end_to_scheduler=True,future_runtime_passed_to_scheduler=False,still_running_occupancy_preserved=True,
      scope='Separate current-slot dispatch stress test; same FIFO/tier order, fixed known background; not exact temporal V42 policy, no integration.')

def main():
    freeze=read(ROOT/'PROVIDER_BUNDLE_FREEZE.json')
    for r in freeze['files']:assert sha(ROOT/r['relative'])==r['sha256']
    q90=RuntimeProvider(allow_research=True).predict_total({},'2025-04-01T08:00Z')['q90_seconds']
    f,caps,known=inputs();saved=pd.read_parquet(EVENTS);saved['uid']=saved.uid.astype(str)
    w0=planned(f,caps,known,q90,'W0');ml=planned(f,caps,known,q90,'ML_Q90')
    z=w0[w0.admitted&w0.in_day.fillna(False)];pair=z.merge(saved[saved.admitted],left_on='job_id',right_on='uid',validate='one_to_one')
    start_equal=bool(np.array_equal(pair.start_slot-24,pair.selected_start_slot));site_equal=bool(np.array_equal(pair.site,pair.selected_site))
    assert len(pair)==int(saved.admitted.sum()) and start_equal and site_equal,'W0_REFERENCE_NOT_EXACT'
    # Read truth ONLY after planned reservations have been generated and saved.
    w0.to_parquet(ROOT/'APRIL_QUEUE_W0.parquet',index=False);ml.to_parquet(ROOT/'APRIL_QUEUE_ML_Q90.parquet',index=False)
    truth=pd.read_parquet(RAW42,columns=['id','start_time','end_time'],filters=[('submit_time','>',ISSUE),('submit_time','<',END)])
    truth=truth[truth.start_time.notna()&truth.end_time.notna()&truth.end_time.lt(pd.Timestamp('2025-05-01T00:00Z'))].copy()
    truth['runtime_seconds']=(truth.end_time-truth.start_time).dt.total_seconds().clip(lower=0);truth['job_id']=truth.id.astype(str);truth=truth[['job_id','runtime_seconds']]
    rows=[summary(w0,truth,'W0_REPRODUCED'),summary(ml,truth,'ML_Q90_FROZEN',z)]
    pd.DataFrame(rows).to_csv(ROOT/'APRIL_WALLTIME_VS_ML_QUEUE_REPLAY.csv',index=False)
    late=z[z.start_slot>=H].merge(truth,on='job_id');late=late[late.runtime_seconds>0]
    write('APRIL_W0_REPRODUCTION.json',dict(PASS=True,admitted=int(saved.admitted.sum()),arrivals=len(saved),late_fraction=rows[0]['fraction_start_ge_H'],late_requested_actual_ratio_median=float((late.requested_seconds/late.runtime_seconds).median()),
      exact_start_equal=start_equal,exact_site_equal=site_equal,known_background_jobs=len(known),source_files=[record(p) for p in [RAW42,REF,EVENTS,CAP]],
      original_requests_verified=False,reported_10_22_and_93_59_used_for_selection=False,truth_opened_after_reservation_ledgers=True))
    stress=[execution_stress(f,caps,known,q90,truth,a) for a in ['W0','ML_Q90']]
    pd.DataFrame(stress).to_csv(ROOT/'APRIL_CAUSAL_EXECUTION_STRESS.csv',index=False)
    write('APRIL_QUEUE_REPLAY_AUDIT.json',dict(completed=True,W0_exact=True,model_frozen_unchanged=True,pure_numeric_site_reference=True,
      no_grid_imports=True,no_optimizer_calls=True,no_V42_changes=True,initial_known_reservations_held_fixed=True,
      not_full_known_and_unknown_intervention=True,request_version_uncertainty_applies_to_all_resource_weights_and_W0=True,
      missing_truth_never_completed_by_prediction=True,stress=stress))
    print('QUEUE',rows,flush=True)
if __name__=='__main__':main()
