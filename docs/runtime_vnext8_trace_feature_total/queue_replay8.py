"""Same v6 April2 arrival/site reference; per-job B0/V8 duration intervention."""
from common8 import *
from evaluate_april8 import assert_freeze
from baseline8 import module
from provider_source import running_proxy
import numpy as np,pandas as pd,math,sys
ISSUE=pd.Timestamp('2025-04-01T08Z');END=ISSUE+pd.Timedelta(hours=30);H=120
CAP=NATIVE/'MobileESS_v41r2_780gpu_capacity_rebase/dayahead/artifacts/v41r2_780gpu_capacity_rebase/V41R2_780GPU_CAPACITY_AUTHORITY.json'
REF=WORK/'V42_RESPONSE_KERNEL_LOCAL/regeneration_002/2025-04-02/CAUSAL_REFERENCE.json'
EVENTS=WORK/'V42_RUNTIME_TEMPORAL_LOCAL/baseline_reproduction_001/2025-04-02/P2_GRID_RESPONSE_POLICY_EVENTS.parquet'
RAW42=WORK/'V42_FINAL_LOCAL/policy_raw_scanner_only.parquet'

def inputs():
    f=pd.read_parquet(RAW42,columns=['id','submit_time','gpus_requested','nodes_req','wallclock_seconds','qos','source_job_hash'],filters=[('submit_time','>',ISSUE),('submit_time','<',END)])
    f['id']=f.id.astype(str);f['tier']=f.qos.map(lambda q:0 if str(q).lower() in ['high','urgent'] else 1 if str(q).lower()=='normal' else 2 if str(q).lower()=='standby' else 3)
    return f.sort_values(['submit_time','tier','id'],kind='stable').reset_index(drop=True),np.array(list(read(CAP)['site_capacity'].values()),int),read(REF)['jobs']
def occupancy(caps,known):
    occ=np.zeros((21000,len(caps)),dtype=np.int32);events={0}
    for j in known:
        if j['AIDC_site']=='UNASSIGNED':continue
        site=int(j['AIDC_site'][-2:])-1;occ[j['start_slot']:j['end_slot'],site]+=j['requested_GPU'];events.add(j['end_slot'])
    assert (occ<=caps).all();return occ,events
def valid(r,caps):return pd.notna(r.gpus_requested) and pd.notna(r.nodes_req) and pd.notna(r.wallclock_seconds) and r.gpus_requested>0 and float(r.gpus_requested).is_integer() and r.nodes_req>0 and r.gpus_requested<=4*r.nodes_req and r.wallclock_seconds>0 and r.gpus_requested<=caps.max()
def plan(f,caps,known,durations,arm):
    occ,events=occupancy(caps,known);rows=[]
    for r in f.itertuples():
        arrival=math.ceil((r.submit_time-ISSUE).total_seconds()/900);in_day=arrival>=24 and r.submit_time>=ISSUE+pd.Timedelta(hours=6)
        if not valid(r,caps):
            if in_day:rows.append(dict(job_id=r.id,arm=arm,admitted=False,in_day=True))
            continue
        seconds=float(r.wallclock_seconds if arm=='W0' else durations[r.id]);assert math.isfinite(seconds) and seconds>=0
        gpu=int(r.gpus_requested);slots=max(1,math.ceil(seconds/900));chosen=None
        for t in sorted({arrival}|{x for x in events if arrival<x<=20000}):
            if t+slots>len(occ):continue
            sites=np.flatnonzero((gpu<=caps)&np.all(occ[t:t+slots]+gpu<=caps,axis=0))
            if len(sites):chosen=t,int(sites[0]);break
        assert chosen is not None,'HORIZON_EXHAUSTED'
        t,site=chosen;occ[t:t+slots,site]+=gpu;events.add(t+slots);assert np.all(occ[t:t+slots,site]<=caps[site])
        rows.append(dict(job_id=r.id,arm=arm,admitted=True,in_day=in_day,arrival_slot=arrival,start_slot=t,site=site,duration_slots=slots,gpu=gpu,
          planned_seconds=seconds,requested_seconds=r.wallclock_seconds,wait_seconds=t*900-(r.submit_time-ISSUE).total_seconds(),minimum_control_slot_applied=seconds==0))
    return pd.DataFrame(rows)
def summarize(ledger,truth,arm,base):
    z=ledger[ledger.admitted&ledger.in_day.fillna(False)];a=z.merge(truth,on='job_id',how='left',validate='one_to_one');m=a.runtime_seconds.notna();y=a.loc[m,'runtime_seconds'];gpu=a.loc[m,'gpu'];pair=z[['job_id','start_slot']].merge(base[['job_id','start_slot']],on='job_id',suffixes=('_new','_W0'))
    return dict(arm=arm,admitted=len(z),start_lt_H=int(z.start_slot.lt(H).sum()),start_ge_H=int(z.start_slot.ge(H).sum()),
      recovered_in_day_starts=int((pair.start_slot_new.lt(H)&pair.start_slot_W0.ge(H)).sum()),lost_in_day_starts=int((pair.start_slot_new.ge(H)&pair.start_slot_W0.lt(H)).sum()),
      average_queue_wait_seconds=float(z.wait_seconds.mean()),P50_queue_wait_seconds=float(z.wait_seconds.median()),P95_queue_wait_seconds=float(z.wait_seconds.quantile(.95)),
      reserved_GPUh=float((z.gpu*z.duration_slots*.25).sum()),realized_GPUh=float((y*gpu/3600).sum()),mature_truth_N=int(m.sum()),unresolved_truth_N=int((~m).sum()),
      forecast_capacity_violations=0,minimum_control_slot_N=int(z.minimum_control_slot_applied.sum()),horizon_slot=H,scope='v6 exact background332; arriving duration-only counterfactual; forecast ledger, separate causal execution stress below')
def stress(f,caps,known,durations,truth,arm):
    occ,_=occupancy(caps,known);entries=[];labels=truth.set_index('job_id').runtime_seconds.to_dict()
    for r in f.itertuples():
        if not valid(r,caps):continue
        entries.append(dict(job_id=r.id,arrival=math.ceil((r.submit_time-ISSUE).total_seconds()/900),gpu=int(r.gpus_requested),plan=float(r.wallclock_seconds if arm=='W0' else durations[r.id]),
          in_day=r.submit_time>=ISSUE+pd.Timedelta(hours=6),submit_time=r.submit_time,extensions=0))
    def complete(uid,elapsed):return uid in labels and elapsed>=labels[uid]
    pending=[];active=[];done=[];i=0;extensions=0;violations=0;maxex=0
    for t in range(20001):
        alive=[]
        for j in active:
            elapsed=(t-j['start_slot'])*900
            if complete(j['job_id'],elapsed):occ[t:j['reserved_until'],j['site']]-=j['gpu'];j['completed_slot']=t;done.append(j);continue
            if t>=j['reserved_until']:
                r=running_proxy(j['plan'],elapsed,True);assert r['OVERRUN'] and r['retain_GPU'] and r['migration_recommendation']=='STAY' and not r['terminate_job']
                occ[t:t+1,j['site']]+=j['gpu'];j['reserved_until']=t+1;extensions+=1;j['extensions']+=1
            alive.append(j)
        active=alive;ex=np.maximum(occ[t]-caps,0);violations+=int(np.any(ex));maxex=max(maxex,int(ex.max()))
        while i<len(entries) and entries[i]['arrival']<=t:pending.append(entries[i]);i+=1
        waiting=[]
        for j in pending:
            d=max(1,math.ceil(j['plan']/900))
            if t+d>len(occ):waiting.append(j);continue
            sites=np.flatnonzero((j['gpu']<=caps)&np.all(occ[t:t+d]+j['gpu']<=caps,axis=0))
            if not len(sites):waiting.append(j);continue
            site=int(sites[0]);occ[t:t+d,site]+=j['gpu'];j.update(start_slot=t,site=site,reserved_until=t+d);active.append(j)
        pending=waiting
        if i==len(entries) and not pending and not active:break
    out=pd.DataFrame(done+active+pending);out['arm']=arm;out.to_parquet(ROOT/f'APRIL_EXECUTION_STRESS_{arm}.parquet',index=False);z=out[out.in_day];starts=z.get('start_slot',pd.Series(index=z.index,dtype=float))
    return dict(arm=arm,N=len(z),started=int(starts.notna().sum()),start_lt_H=int(starts.lt(H).sum()),start_ge_H=int(starts.ge(H).sum()),not_started=int(starts.isna().sum()),overrun_extensions=extensions,
      capacity_violations=violations,max_excess_GPU=maxex,stop_slot=t,unresolved_active=len(active),pending_at_stop=len(pending),truth_missing_jobs=sum(e['job_id'] not in labels for e in entries),
      no_future_end_to_scheduler=True,still_running_GPU_retained=True,minimum_live_reservation_interval=900,scope='Separate causal current-slot dispatch stress, fixed known background. Not exact integrated V42 optimization.')
def main():
    assert_freeze();f,caps,known=inputs();pred=pd.read_parquet(ROOT/'APRIL_PREDICTIONS.parquet').set_index('job_id')
    eligible=[r.id for r in f.itertuples() if valid(r,caps)];assert set(eligible)<=set(pred.index),'Missing inference features; do not guess durations'
    arms={a:pred[a+'_Q90'].to_dict() for a in ['B0','V8']};ledgers={a:plan(f,caps,known,arms.get(a,{}),a) for a in ['W0','B0','V8']}
    saved=pd.read_parquet(EVENTS);saved['uid']=saved.uid.astype(str);w0=ledgers['W0'];base=w0[w0.admitted&w0.in_day.fillna(False)];pair=base.merge(saved[saved.admitted],left_on='job_id',right_on='uid',validate='one_to_one')
    assert len(pair)==saved.admitted.sum() and np.array_equal(pair.start_slot-24,pair.selected_start_slot) and np.array_equal(pair.site,pair.selected_site),'W0_REFERENCE_NOT_EXACT'
    for a,l in ledgers.items():l.to_parquet(ROOT/f'APRIL_QUEUE_{a}.parquet',index=False)
    # Truth enters only AFTER planned ledgers exist; dispatch observer is isolated above.
    truth=pd.read_parquet(ROOT/'APRIL_JOBS.parquet');truth=truth[truth.label_valid][['job_id','runtime_seconds']]
    summaries=[summarize(ledgers[a],truth,a,base) for a in ['W0','B0','V8']]
    results=[stress(f,caps,known,arms.get(a,{}),truth,a) for a in ['W0','B0','V8']]
    stressdf=pd.DataFrame(results);stressdf.to_csv(ROOT/'APRIL_CAUSAL_EXECUTION_STRESS.csv',index=False)
    merged=pd.DataFrame(summaries).merge(stressdf[['arm','overrun_extensions','capacity_violations','max_excess_GPU']],on='arm');merged.to_csv(ROOT/'APRIL_WALLTIME_VS_RUNTIME_QUEUE_REPLAY.csv',index=False)
    write('APRIL_QUEUE_REPLAY_AUDIT.json',dict(time=now(),W0_exact=True,reference_admitted=int(saved.admitted.sum()),known_background_jobs=len(known),summary=summaries,causal_stress=results,
      capacity_safe=all(r['capacity_violations']==0 for r in results),no_V42_grid_or_optimizer_changes=True,May_payload_read=False,source_files=[record(x) for x in [CAP,REF,EVENTS,RAW42]],
      original_request_provenance_unverified=True,truth_not_exposed_to_planner=True,missing_truth_never_completed_by_prediction=True,
      scope='Same frozen v6 issue Apr1T08Z and H=120 (Apr2T14Z); in-day arrival begins issue+6h. Exact reference start offsets -24. Restricted background-fixed counterfactual, not whole-system production simulation.'))
    assert_freeze();print('QUEUE_COMPLETE',merged[['arm','admitted','start_lt_H','start_ge_H','overrun_extensions','capacity_violations']].to_dict('records'),flush=True)
if __name__=='__main__':main()
