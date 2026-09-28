"""Pre-April common empty-background aggregate-capacity research replays."""
import math,numpy as np,pandas as pd
def replay(f,pred,day):
    day=pd.Timestamp(day,tz='UTC');end=day+pd.Timedelta(days=1)
    z=f.loc[f.submit_time.ge(day)&f.submit_time.lt(end)].copy()
    z['pred']=np.asarray(pred)[f.submit_time.ge(day)&f.submit_time.lt(end)]
    ok=(z.num_gpus_req>0)&(z.num_nodes_req>0)&(z.num_gpus_req<=4*z.num_nodes_req)&(z.num_gpus_req<=780)&(z.requested_seconds>0)&z.num_gpus_req.eq(np.floor(z.num_gpus_req))&z.num_nodes_req.eq(np.floor(z.num_nodes_req))
    z=z[ok];z['tier']=z.qos.map({'high':0,'normal':1,'standby':2}).fillna(3);z=z.sort_values(['submit_time','tier','job_id'],kind='stable')
    occ=np.zeros(1921);events={0};ledger=[];exhausted=0
    entries=[]
    for r in z.itertuples():
        arrival=math.ceil((r.submit_time-day).total_seconds()/900);slots=max(1,math.ceil(r.pred/900));gpu=int(r.num_gpus_req);chosen=None
        for t in sorted({arrival}|{e for e in events if e>=arrival}):
            if t+slots>1920:continue
            if np.all(occ[t:t+slots]+gpu<=780):chosen=t;break
        if chosen is None:exhausted+=1
        else:occ[chosen:chosen+slots]+=gpu;events.add(chosen+slots)
        ledger.append((chosen if chosen is not None else np.nan,arrival,r.pred,gpu,float(r.runtime_seconds) if r.event else np.nan))
        entries.append(dict(arrival=arrival,gpu=gpu,slots=slots,plan=r.pred,truth=float(r.runtime_seconds) if r.event else np.inf))
    a=np.array(ledger) if ledger else np.empty((0,5));wait=(a[:,0]-a[:,1])*900
    active=[];pending=[];i=0;done=[];extensions=0;violations=0
    for t in range(1920):
        # Truth is isolated in completion observer. Dispatcher sees only still-running.
        alive=[]
        for j in active:
            elapsed=(t-j['start'])*900
            if elapsed>=j['truth']:done.append(j);continue
            if elapsed>=j['slots']*900:j['slots']+=1;extensions+=1
            alive.append(j)
        active=alive
        while i<len(entries) and entries[i]['arrival']<=t:pending.append(entries[i].copy());i+=1
        used=sum(j['gpu'] for j in active);waiting=[]
        for j in pending:
            if used+j['gpu']<=780:
                j['start']=t;active.append(j);used+=j['gpu']
            else:waiting.append(j)
        pending=waiting;violations+=int(used>780)
        if i==len(entries) and not pending and not active:break
    started=done+active
    return dict(N=len(z),start_lt_H=int(np.sum(a[:,0]<96)),start_ge_H=int(np.sum(a[:,0]>=96)),forecast_horizon_exhausted=exhausted,
        reserved_GPUh=float(np.sum(np.maximum(1,np.ceil(a[:,2]/900))*a[:,3]*.25)),realized_GPUh=float(np.nansum(a[:,4]*a[:,3]/3600)),
        missing_truth_N=int(np.isnan(a[:,4]).sum()),minimum_control_slot_N=int(np.sum(a[:,2]==0)),mean_queue_wait_seconds=float(np.nanmean(wait)) if len(wait) and np.isfinite(wait).any() else None,
        P50_queue_wait_seconds=float(np.nanmedian(wait)) if len(wait) and np.isfinite(wait).any() else None,
        P95_queue_wait_seconds=float(np.nanquantile(wait,.95)) if len(wait) and np.isfinite(wait).any() else None,
        causal_start_lt_H=sum(j['start']<96 for j in started),causal_start_ge_H=sum(j['start']>=96 for j in started),
        capacity_violations=violations,overrun_extensions=extensions,causal_unresolved_at_horizon=len(active)+len(pending),
        causal_mean_queue_wait_seconds=float(np.mean([(j['start']-j['arrival'])*900 for j in started])) if started else None,
        queue_scope='Empty background,780 aggregate GPUs, same-day arrivals; separate forecast reservation and causal current-slot stress')
