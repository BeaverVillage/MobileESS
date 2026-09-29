"""Exact inherited April2 reservation ledger, with frozen V10 conditional overrun."""
from common10 import *
from finalize10 import assert_freeze,load_provider
from distribution9 import Distribution
from metrics9 import correction
from baseline8 import module
import numpy as np,pandas as pd,math
def conditional_stress(qmod,f,caps,known,durations,truth,parameters,predict,arm):
    occ,_=qmod.occupancy(caps,known);labels=truth.set_index('job_id').runtime_seconds.to_dict();entries=[]
    for r in f.itertuples():
        if not qmod.valid(r,caps):continue
        entries.append(dict(job_id=r.id,arrival=math.ceil((r.submit_time-qmod.ISSUE).total_seconds()/900),gpu=int(r.gpus_requested),plan=float(durations[r.id]),in_day=r.submit_time>=qmod.ISSUE+pd.Timedelta(hours=6),extensions=0))
    active=[];pending=[];done=[];i=0;extensions=0;violations=0;maxex=0;conditional=[]
    def complete(uid,elapsed):return uid in labels and elapsed>=labels[uid]
    for t in range(20001):
        alive=[]
        for j in active:
            elapsed=(t-j['start_slot'])*900
            if complete(j['job_id'],elapsed):occ[t:j['reserved_until'],j['site']]-=j['gpu'];j['completed_slot']=t;done.append(j);continue
            if t>=j['reserved_until']:
                q,ls=predict(parameters[j['job_id']][None,...],elapsed)
                assert np.isfinite(q).all() and q[0,1]>=q[0,0]>=0
                conditional.append(dict(arm=arm,job_id=j['job_id'],slot=t,elapsed_seconds=elapsed,q50_remaining=q[0,0],q90_remaining=q[0,1],log_survival=ls[0],policy='STAY',extend_seconds=900))
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
    out=pd.DataFrame(done+active+pending);out.to_parquet(ROOT/f'APRIL_EXECUTION_STRESS_{arm}.parquet',index=False)
    pd.DataFrame(conditional).to_csv(ROOT/f'APRIL_QUEUE_CONDITIONAL_EXTENSIONS_{arm}.csv',index=False);z=out[out.in_day];starts=z.get('start_slot',pd.Series(index=z.index,dtype=float))
    return dict(arm=arm,N=len(z),started=int(starts.notna().sum()),start_lt_H=int(starts.lt(qmod.H).sum()),start_ge_H=int(starts.ge(qmod.H).sum()),not_started=int(starts.isna().sum()),
        overrun_extensions=extensions,capacity_violations=violations,max_excess_GPU=maxex,stop_slot=t,unresolved_active=len(active),pending_at_stop=len(pending),no_future_end_to_scheduler=True,still_running_GPU_retained=True,conditional_remaining_calls=len(conditional),calibration_state='preApril frozen; no counterfactual outcomes to predictor')
def main():
    assert_freeze();assert (ROOT/'APRIL_EVALUATION_RECEIPT.json').exists()
    qmod=module('queue8_v10',V8/'queue_replay8.py');qmod.ROOT=ROOT
    f,caps,known=qmod.inputs();pred=pd.read_parquet(ROOT/'APRIL_PREDICTIONS.parquet').set_index('job_id');source=pd.read_parquet(V8/'APRIL_JOBS.parquet')
    provider=load_provider();p10=np.load(LOCAL/'APRIL_PARAMETERS.npz')['parameters'];v10=provider.quantiles_from_parameters(p10)[:,1]
    v9model=Distribution.load(V9/'RUNTIME_PROVIDER/model');contract=read(V9/'RUNTIME_PROVIDER/runtime_contract.json');p9=np.load(V9/'.local/APRIL_PARAMETERS.npz')['parameters']
    day=qmod.ISSUE.floor('D');window=int(contract['calibration_mode'].replace('ROLLING',''));delta=correction([r['residual'] for r in contract['initial_residuals'] if day-pd.Timedelta(days=window)<=pd.Timestamp(r['end_time'])<day])
    v9=v9model.quantiles(p9,delta,quantiles=(.9,))[:,0]
    arms={a:pred[a+'_Q90'].to_dict() for a in ['B0','V8']};arms['V9']=dict(zip(source.job_id,v9));arms['V10']=dict(zip(source.job_id,v10))
    eligible=[r.id for r in f.itertuples() if qmod.valid(r,caps)];assert set(eligible)<=set(pred.index)
    ledgers={a:qmod.plan(f,caps,known,arms.get(a,{}),a) for a in ['W0','B0','V8','V9','V10']}
    base=ledgers['W0'];base=base[base.admitted&base.in_day.fillna(False)]
    saved=pd.read_parquet(qmod.EVENTS);saved['uid']=saved.uid.astype(str);pair=base.merge(saved[saved.admitted],left_on='job_id',right_on='uid',validate='one_to_one')
    assert len(pair)==saved.admitted.sum() and np.array_equal(pair.start_slot-24,pair.selected_start_slot) and np.array_equal(pair.site,pair.selected_site)
    truth=source[source.label_valid][['job_id','runtime_seconds']];summaries=[qmod.summarize(ledgers[a],truth,a,base) for a in ledgers]
    for a,n in [('W0',150),('B0',47),('V8',111),('V9',127)]:assert next(s['start_lt_H'] for s in summaries if s['arm']==a)==n
    for a,l in ledgers.items():l.to_parquet(ROOT/f'APRIL_QUEUE_{a}.parquet',index=False)
    stress=[qmod.stress(f,caps,known,arms.get(a,{}),truth,a) for a in ['W0','B0','V8']]
    def predict9(par,e):
        q,s,ls=v9model.remaining(par,e,delta);return q,ls
    stress.append(conditional_stress(qmod,f,caps,known,arms['V9'],truth,dict(zip(source.job_id,p9)),predict9,'V9'))
    stress.append(conditional_stress(qmod,f,caps,known,arms['V10'],truth,dict(zip(source.job_id,p10)),provider.remaining_from_parameters,'V10'))
    sd=pd.DataFrame(stress);sd.to_csv(ROOT/'APRIL_CAUSAL_EXECUTION_STRESS.csv',index=False);out=pd.DataFrame(summaries).merge(sd[['arm','overrun_extensions','capacity_violations','max_excess_GPU']],on='arm')
    out.to_csv(ROOT/'APRIL2_EXPOSED_QUEUE_REGRESSION.csv',index=False)
    legacy=pd.read_csv(V9/'APRIL2_EXPOSED_QUEUE_REGRESSION.csv').set_index('arm')
    for a in ['W0','B0','V8','V9']:
        for c in ['start_lt_H','overrun_extensions','capacity_violations']:assert out.set_index('arm').loc[a,c]==legacy.loc[a,c]
    write('APRIL_QUEUE_REPLAY_AUDIT.json',dict(time=now(),W0_exact=True,baseline_starts={'W0':150,'B0':47,'V8':111,'V9':127},known_background_jobs=len(known),V9_issuance_delta=delta,
        capacity_safe=bool(sd.capacity_violations.eq(0).all()),source_files=[record(p) for p in [qmod.CAP,qmod.REF,qmod.EVENTS,qmod.RAW42,V8/'queue_replay8.py']],April_selection=False,May_payload_read=False,no_V42_kernel_change=True,
        scope='Restricted background-fixed site forecast reservation counterfactual; separate causal current-slot completion-observer stress. V10 model/map frozen before April.'))
    assert_freeze();print('APRIL2_COMPLETE',out[['arm','start_lt_H','overrun_extensions','capacity_violations']].to_dict('records'),flush=True)
if __name__=='__main__':main()

