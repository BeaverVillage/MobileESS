from common9 import *
import time,numpy as np,pandas as pd
from fit9 import matrix
from distribution9 import Distribution,QUANTILES
from train9 import ARMS
from metrics9 import *
from queue9 import replay
MODES=['NONE','STATIC14','ROLLING14','ROLLING28']
def scope(arm):return 'NONCAUSAL_RETROSPECTIVE_REFERENCE' if arm in ['B0','Bconst','V8'] else 'CAUSAL_FOLD_TRACE_PROXY'
def main():
    assert (ROOT/'TRAINING_COMPLETED.json').exists()
    folds=[];tails=[];curves=[];gpurows=[];queues=[];cal_audit=[];allq={};trainsec={};latency={}
    edges=read(ROOT/'HAZARD_BIN_CONTRACT.json')['edges_seconds'];contracts=read(ROOT/'TEMPORAL_FOLD_CONTRACT.json')['folds']
    for i in range(1,6):
        print(now(),'EVAL_FOLD',i,flush=True)
        folder=LOCAL/f'fold{i}';val=pd.read_parquet(folder/'VALID.parquet');cal=pd.read_parquet(folder/'CAL.parquet');base=pd.read_parquet(folder/'baselines.parquet')
        assert np.array_equal(base.job_id,val.job_id)
        prep=read(ROOT/f'FOLD_{i}_PREPROCESSING.json');m=val.event.to_numpy(bool);y=val.loc[m,'runtime_seconds'].to_numpy(float);g=val.loc[m,'num_gpus_req'].to_numpy(float)
        arms={}
        w=val.requested_seconds.to_numpy(float);arms['W0']=(np.tile(w[:,None],(1,5)),None,None,0)
        for a in ['B0','Bconst','V8']:
            q=np.full((len(val),5),np.nan);q[:,0]=base[a+'_Q50'];q[:,3]=base[a+'_Q90'];arms[a]=(q,None,None,0)
        for a in ARMS:
            model=Distribution.load(ROOT/'FOLD_MODELS'/f'fold{i}'/a);saved=np.load(folder/(a+'.npz'));par=saved['val_parameters']
            trainsec[a]=trainsec.get(a,0)+model.meta['training_seconds']
            t=time.perf_counter();model.parameters(matrix(val.head(1000),prep));latency.setdefault(a,[]).append((time.perf_counter()-t)*1000)
            for mode in MODES:
                if a.endswith('EXACT') and mode!='NONE':continue
                name=a+'__'+mode;d,audit=calibration(cal,val,saved['cal_quantiles'],saved['val_quantiles'],mode)
                cal_audit.extend(dict(fold=i,arm=a,**r) for r in audit)
                q=model.quantiles(par,d);arms[name]=(q,model,par,d)
        for a,(q,model,par,d) in arms.items():
            qm=q[m];s=stats(y,g,qm[:,0],qm[:,3]);s.update(fold=i,arm=a,scope=scope(a),GPU_sum=float(g.sum()))
            if model is not None and model.meta['kind']!='D3':s.update(distribution_scores(model,par,val,np.broadcast_to(d,len(val)),edges))
            folds.append(s)
            for row in tail_rows(y,g,qm):tails.append(dict(fold=i,arm=a,**row))
            for j,tau in enumerate(QUANTILES):
                if np.isfinite(qm[:,j]).all():curves.append(dict(fold=i,arm=a,nominal_quantile=tau,N=len(y),empirical_coverage=float((y<=qm[:,j]).mean())))
            for lo,hi,label in [(0,4,'GPU_1_4'),(4,16,'GPU_gt4_lt16'),(15,np.inf,'GPU_ge16'),(63,np.inf,'GPU_ge64')]:
                gm=(g>lo)&(g<=hi if hi==4 else g<hi)
                ss=stats(y[gm],g[gm],qm[gm,0],qm[gm,3]);ss['status']='INSUFFICIENT_SUPPORT' if ss['N']<100 else 'PASS' if ss['Q90_coverage']>=.85 else 'FAIL'
                gpurows.append(dict(fold=i,arm=a,stratum=label,**ss))
            queues.append(dict(fold=i,arm=a,scope=scope(a),**replay(val,q[:,3],contracts[i-1]['queue_day'])))
            allq.setdefault(a,[]).append(pd.DataFrame(dict(fold=i,job_id=val.loc[m,'job_id'].to_numpy(),submit_time=val.loc[m,'submit_time'].to_numpy(),y=y,gpu=g,q50=qm[:,0],q90=qm[:,3])))
        print(now(),'EVAL_COMPLETE',i,flush=True)
    fd=pd.DataFrame(folds);td=pd.DataFrame(tails);qd=pd.DataFrame(queues)
    for name,frame in [('FOLD_LEVEL_METRICS.csv',fd),('LONG_TAIL_METRICS.csv',td),('DISTRIBUTIONAL_CALIBRATION.csv',pd.DataFrame(curves)),('GPU_WEIGHTED_METRICS.csv',pd.DataFrame(gpurows)),('PREAPRIL_QUEUE_REPLAY.csv',qd),('CAUSAL_CALIBRATION_AUDIT.csv',pd.DataFrame(cal_audit))]:frame.to_csv(ROOT/name,index=False)
    pooled=[]
    for a,parts in allq.items():
        f=pd.concat(parts,ignore_index=True);f.to_parquet(LOCAL/(a+'_evaluation.parquet'),index=False)
        s=stats(f.y,f.gpu,f.q50,f.q90);v=fd[fd.arm.eq(a)];cv=v.Q90_coverage.to_numpy()
        s.update(arm=a,scope=scope(a),min_fold_coverage=float(cv.min()),max_fold_coverage=float(cv.max()),coverage_std=float(cv.std()),
            training_seconds_5fold=trainsec.get(a.split('__')[0]),batch1000_inference_ms_mean=float(np.mean(latency[a.split('__')[0]])) if a.split('__')[0] in latency else None,
            queue_starts_lt_H=int(qd.loc[qd.arm.eq(a),'start_lt_H'].sum()))
        for threshold in [4,8,12,24]:
            long=f[f.y>threshold*3600];s[f'gt{threshold}h_N']=len(long);s[f'gt{threshold}h_coverage']=float((long.y<=long.q90).mean()) if len(long) else None
        if 'NLL_N' in v and v.NLL_N.notna().all():
            s['coarsened_survival_NLL']=float(np.average(v.coarsened_survival_NLL,weights=v.NLL_N));s['known_status_72h_Brier']=float(np.average(v.known_status_72h_Brier,weights=v.NLL_N))
        eligible=f.submit_time>=pd.Timestamp('2025-03-14T08Z');e=f.loc[eligible];s['B0_time_eligible_N']=len(e);s['time_eligible_Q90_pinball']=stats(e.y,e.gpu,e.q50,e.q90)['Q90_pinball']
        pooled.append(s)
    table=pd.DataFrame(pooled);table.to_csv(ROOT/'MODEL_COMPARISON.csv',index=False)
    indexed=table.set_index('arm');gates=[]
    for a in table.arm:
        if not a.startswith(('D1__','D2_')) or 'EXACT' in a:continue
        s=indexed.loc[a];fold=fd[fd.arm.eq(a)];long=td[td.arm.eq(a)&td.cohort.eq('gt4h')]
        qq=qd[qd.arm.eq(a)].set_index('fold');wq=qd[qd.arm.eq('W0')].set_index('fold')
        gg=dict(OVERALL_Q90_GATE_PASS=.88<=s.Q90_coverage<=.92,
            TEMPORAL_STABILITY_GATE_PASS=s.min_fold_coverage>=.8 and s.max_fold_coverage<=.97 and s.coverage_std<=.06,
            LONG_JOB_Q90_GATE_PASS=bool(((long.N>=100)&(long.Q90_coverage>=.85)).all()),
            PINBALL_GATE_PASS=s.Q90_pinball<=1.02*indexed.loc['D3__NONE','Q90_pinball'] and s.time_eligible_Q90_pinball<=1.02*indexed.loc['B0','time_eligible_Q90_pinball'],
            RESERVATION_SHARPNESS_PASS=s.reserved_GPUh<=.8*indexed.loc['W0','reserved_GPUh'],
            PREAPRIL_QUEUE_GATE_PASS=bool((qq.start_lt_H>=wq.start_lt_H).all() and qq.capacity_violations.sum()==0 and qq.forecast_horizon_exhausted.sum()==0 and qq.causal_unresolved_at_horizon.sum()==0))
        gates.append(dict(arm=a,**gg,eligible=all(gg.values()),failed_gate_count=sum(not x for x in gg.values()),reserved_GPUh=s.reserved_GPUh,Q90_pinball=s.Q90_pinball))
    gates=pd.DataFrame(gates);gates.to_csv(ROOT/'SELECTION_GATES.csv',index=False)
    eligible=gates[gates.eligible]
    ranked=(eligible.sort_values(['reserved_GPUh','Q90_pinball']) if len(eligible) else gates.sort_values(['failed_gate_count','reserved_GPUh','Q90_pinball']))
    chosen=ranked.iloc[0].to_dict()
    selected_row=table[table.arm.eq(chosen['arm'])].copy();selected_row['selected_source_arm']=chosen['arm'];selected_row['arm']='V9_SELECTED'
    pd.concat([table,selected_row],ignore_index=True).to_csv(ROOT/'MODEL_COMPARISON.csv',index=False)
    write('PREAPRIL_SELECTION_RESULT.json',dict(time=now(),selected=chosen,eligible_candidates=len(eligible),diagnostic_only=not bool(chosen['eligible']),selection_scope='five chronological folds only; April not read',future_calibration_residual_reads=0,
        scores=record(ROOT/'MODEL_COMPARISON.csv'),gates=record(ROOT/'SELECTION_GATES.csv'),protocol=record(ROOT/'EXPERIMENT_PROTOCOL.json')))
    print('SELECTED',chosen,flush=True)
if __name__=='__main__':main()
