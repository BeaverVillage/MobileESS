from common10 import *
from hazard10 import Hazard
from calibration10 import *
from calibration_state10 import *
from metrics10 import *
from queue9 import replay
import pandas as pd,numpy as np
def remaining_rows(model,par,f,totalq,states,mode,conditioned,bounds,continuation):
    m=f.event.to_numpy();g=f.loc[m].reset_index(drop=True);pp=par[m];y=g.runtime_seconds.to_numpy(float);gpu=g.num_gpus_req.to_numpy(float)
    counts=np.maximum(np.ceil(y/1800).astype(int)-1,0);ix=np.repeat(np.arange(len(g)),counts)
    elapsed=(np.arange(len(ix))-np.repeat(np.cumsum(counts)-counts,counts)+1)*1800;actual=y[ix]-elapsed
    times=pd.DatetimeIndex(g.start_time.iloc[ix])+pd.to_timedelta(elapsed,unit='s');days=times.floor('D')
    risks=np.exp(model.logsf(pp,14400,continuation));groups=np.digitize(risks,bounds,right=True)
    pred=np.zeros((len(ix),2));logs=np.zeros(len(ix));rawlogs=np.zeros(len(ix))
    for start in range(0,len(ix),4000):
        sl=slice(start,start+4000);rawlogs[sl]=model.logsf(pp[ix[sl]],elapsed[sl],continuation)
    for day in sorted(days.unique()):
        state=states['STATIC'] if mode=='STATIC' else states[str(day)]
        for group in range(len(bounds)+1):
            positions=np.flatnonzero((days==day)&(groups[ix]==group))
            if not len(positions):continue
            mapping=group_map(state,group) if conditioned else ProbabilityMap(state['pooled'])
            for start in range(0,len(positions),4000):
                pos=positions[start:start+4000];ls=mapping.logsf(rawlogs[pos]);logs[pos]=ls
                for j,tau in enumerate([.5,.9]):
                    target=mapping.inverse_logsf(ls+np.log1p(-tau))
                    pred[pos,j]=np.maximum(model.inverse_logsf(pp[ix[pos]],target,continuation)-elapsed[pos],0)
    planned=totalq[m,3][ix];over=elapsed>=planned;rows=[]
    for scope,mask in [('ALL',np.ones(len(ix),bool)),('ELAPSED_GT4H',elapsed>14400),('ELAPSED_GT12H',elapsed>43200),('TOTAL_GT4H',y[ix]>14400)]:
        yy=actual[mask];q=pred[mask];s=stats(yy,gpu[ix][mask],q[:,0],q[:,1]);s.update(scope=scope,unique_jobs=int(np.unique(ix[mask]).size),overrun_checkpoint_fraction=float(over[mask].mean()),GPU_sum=float(gpu[ix][mask].sum()))
        for t in [900,1800,3600,7200,14400]:
            truth=yy>t;p=q[:,1]>t
            s.update({f'accuracy_gt_{t}s':float((truth==p).mean()),f'TP_gt_{t}s':int((truth&p).sum()),f'FP_gt_{t}s':int((~truth&p).sum()),f'FN_gt_{t}s':int((truth&~p).sum())})
        rows.append(s)
    return rows
def main():
    selected=read(ROOT/'RAW_GRID_SELECTION.json');grid=selected['grid'];cont=selected['continuation']
    candidates=[('T1','NONE','STATIC',False)]+[(f'{kind}_{family}_{mode}',family,mode,kind=='T3') for kind in ['T2','T3'] for family in ['ISOTONIC','LOGISTIC'] for mode in ['STATIC','ROLLING14','ROLLING28']]
    foldrows=[];tailrows=[];queues=[];curves=[];gpus=[];remaining=[];risk_support=[];risk_cal=[];cal_audit=[];parts={}
    contracts=read(ROOT/'TEMPORAL_FOLD_CONTRACT.json')['folds'];old=pd.read_csv(V9/'MODEL_COMPARISON.csv').set_index('arm')
    for i in range(1,6):
        print(now(),'CALIBRATION_FOLD',i,flush=True)
        val=fold_data(i,'VALID');cal=fold_data(i,'CAL');pool=pd.concat([cal,val],ignore_index=True);ncal=len(cal)
        model=Hazard.load(ROOT/'FOLD_MODELS'/f'fold{i}'/grid);saved=np.load(LOCAL/f'fold{i}'/(grid+'.npz'));par=saved['val_parameters'];pc=saved['cal_parameters'];allpar=np.concatenate([pc,par])
        risks=np.exp(model.logsf(allpar,14400,cont));bounds=read(ROOT/f'RISK_BOUNDARIES/fold{i}_{grid}.json')['bounds'];groups=np.digitize(risks[ncal:],bounds,right=True)
        bins=probability_bins(raw_landmarks(model,allpar,cont));scoredata=score_inputs(model,par,val,cont)
        m=val.event.to_numpy(bool);y=val.loc[m,'runtime_seconds'].to_numpy();gpu=val.loc[m,'num_gpus_req'].to_numpy()
        start=pd.Timestamp(contracts[i-1]['VALID_submit_from']);end=pd.Timestamp(contracts[i-1]['VALID_end'])
        days=pd.date_range(start.floor('D'),end.ceil('D')-pd.Timedelta(days=1),tz='UTC');jobday=val.submit_time.dt.floor('D')
        states_cache={}
        for family in ['ISOTONIC','LOGISTIC']:
            for mode in ['STATIC','ROLLING14','ROLLING28']:
                states={}
                for day in ([start] if mode=='STATIC' else days):
                    if mode=='STATIC':state=fit_state(cal,bins[:ncal],risks[:ncal],day,mode,family,True,bounds)
                    else:state=fit_state(pool,bins,risks,day,mode,family,True,bounds)
                    key='STATIC' if mode=='STATIC' else str(day);states[key]=state
                    risk_support.extend(dict(fold=i,family=family,mode=mode,day=str(day),**s) for s in state['support'])
                    cal_audit.append(dict(fold=i,**{k:v for k,v in state.items() if k not in ['groups','pooled','bounds','support']}))
                    for group,mapstate in state['groups'].items():risk_cal.append(dict(fold=i,family=family,mode=mode,day=str(day),group=group,map_family=mapstate['family'],knot_N=len(mapstate.get('s',[])),a=mapstate.get('a'),b=mapstate.get('b')))
                states_cache[(family,mode)]=states
                write(f'CALIBRATION_STATES/fold{i}_{family}_{mode}.json',dict(states=states,grid=grid,continuation=cont,bounds=bounds))
        identity=dict(pooled={'family':'NONE'},groups={str(g):{'family':'NONE'} for g in range(len(bounds)+1)})
        for arm,family,mode,conditioned in candidates:
            states={'STATIC':identity} if family=='NONE' else states_cache[(family,mode)]
            q=np.zeros((len(val),5));assign=[]
            for day in sorted(jobday.unique()):
                state=states['STATIC'] if mode=='STATIC' else states[str(day)]
                for group in range(len(bounds)+1):
                    mask=jobday.eq(day).to_numpy()&(groups==group)
                    if not mask.any():continue
                    mapping=group_map(state,group) if conditioned else ProbabilityMap(state['pooled'])
                    q[mask]=maps_quantiles(model,par[mask],mapping,cont);assign.append((mask,mapping))
            score=distribution_metrics(scoredata,assign);ss=stats(y,gpu,q[m,0],q[m,3])
            foldrows.append(dict(fold=i,arm=arm,censored_N=int(val.censored.sum()),**ss,**score))
            tailrows.extend(dict(fold=i,arm=arm,**r) for r in tail_rows(y,gpu,q[m]))
            for j,tau in enumerate([.5,.7,.8,.9,.95]):curves.append(dict(fold=i,arm=arm,nominal=tau,N=len(y),empirical_coverage=float((y<=q[m,j]).mean())))
            for threshold in [16,64]:
                gm=gpu>=threshold;s=stats(y[gm],gpu[gm],q[m,0][gm],q[m,3][gm]);s['status']='INSUFFICIENT_SUPPORT' if s['N']<100 else 'PASS' if s['Q90_coverage']>=.85 else 'FAIL';gpus.append(dict(fold=i,arm=arm,GPU_min=threshold,**s))
            queues.append(dict(fold=i,arm=arm,**replay(val,q[:,3],contracts[i-1]['queue_day'])))
            parts.setdefault(arm,[]).append(pd.DataFrame(dict(y=y,gpu=gpu,q50=q[m,0],q90=q[m,3])))
            np.savez_compressed(LOCAL/f'fold{i}'/(arm+'_calibrated.npz'),quantiles=q)
            print(now(),'REMAINING',i,arm,flush=True)
            rem=remaining_rows(model,par,val,q,states,mode,conditioned,bounds,cont)
            remaining.extend(dict(phase='PREAPRIL',fold=i,arm=arm,**r) for r in rem)
        print(now(),'CALIBRATED_FOLD_DONE',i,flush=True)
    fd=pd.DataFrame(foldrows);td=pd.DataFrame(tailrows);qd=pd.DataFrame(queues);rem=pd.DataFrame(remaining)
    for name,frame in [('FOLD_LEVEL_METRICS.csv',fd),('LONG_TAIL_METRICS.csv',td),('DISTRIBUTIONAL_METRICS.csv',pd.DataFrame(curves)),('GPU_WEIGHTED_METRICS.csv',pd.DataFrame(gpus)),('PREAPRIL_QUEUE_REPLAY.csv',qd),('PREAPRIL_REMAINING_FOLD.csv',rem),('RISK_GROUP_SUPPORT.csv',pd.DataFrame(risk_support)),('RISK_GROUP_CALIBRATION.csv',pd.DataFrame(risk_cal)),('CALIBRATION_CAUSALITY_AUDIT.csv',pd.DataFrame(cal_audit))]:frame.to_csv(ROOT/name,index=False)
    rpool=[]
    for (arm,scope),g in rem.groupby(['arm','scope']):
        row=dict(phase='PREAPRIL',arm=arm,scope=scope,N=int(g.N.sum()))
        for col in ['Q50_MAE','Q90_MAE','Q90_coverage','Q90_pinball','overrun_checkpoint_fraction']+[f'accuracy_gt_{t}s' for t in [900,1800,3600,7200,14400]]:row[col]=float(np.average(g[col],weights=g.N))
        for col in [c for c in g if c.startswith(('TP_gt','FP_gt','FN_gt'))]:row[col]=int(g[col].sum())
        rpool.append(row)
    rp=pd.DataFrame(rpool);rp.to_csv(ROOT/'PREAPRIL_REMAINING_POOLED.csv',index=False)
    baselinequeue=pd.read_csv(V9/'PREAPRIL_QUEUE_REPLAY.csv');wq=baselinequeue[baselinequeue.arm.eq('W0')];summaries=[];checks=[]
    for arm,p in parts.items():
        s=pooled(arm,p,fd,float(old.loc['W0','reserved_GPUh']));summaries.append(s)
        r=rp[(rp.arm==arm)&(rp.scope=='ALL')].iloc[0].to_dict()
        gg=gates(s,fd[fd.arm.eq(arm)],td[td.arm.eq(arm)],qd[qd.arm.eq(arm)],wq,r)
        checks.append(dict(arm=arm,**gg,Q90_pinball=s['Q90_pinball'],reservation_actual_GPUh=s['reservation_actual_GPUh'],Q50_MAE=s['Q50_MAE'],coverage_std=s['coverage_std']))
    pd.DataFrame(summaries).to_csv(ROOT/'CALIBRATION_COMPARISON.csv',index=False);gate=pd.DataFrame(checks);gate.to_csv(ROOT/'SELECTION_GATES.csv',index=False)
    eligible=gate[gate.eligible];rank=eligible if len(eligible) else gate
    ordering=([] if len(eligible) else ['failed_gates'])+['Q90_pinball','reservation_actual_GPUh','Q50_MAE','coverage_std'];chosen=rank.sort_values(ordering).iloc[0].to_dict()
    definition=next(c for c in candidates if c[0]==chosen['arm'])
    write('PREAPRIL_SELECTION_RESULT.json',dict(time=now(),selected=chosen,grid=grid,continuation=cont,family=definition[1],mode=definition[2],risk_conditioned=definition[3],
        eligible_candidates=len(eligible),diagnostic_only=not chosen['eligible'],April_read=False))
    write('MONOTONICITY_AUDIT.json',dict(time=now(),PASS=bool(fd.monotonicity_pass.all()),formal_reason='Positive hazard rates, continuous monotone map with endpoint0/1 and .01 identity component, logistic slope constrained positive; whole distribution uses same map',sampled_all_calibration_states=True))
    write('ZERO_SUPPORT_AUDIT.json',dict(time=now(),ZERO_SUPPORT_OBSERVED_INTERVAL_COUNT=int(fd.zero_support_count.sum()),all_proper_scores_finite=bool(fd.proper_score_finite.all()),score='Exact one-second observed-interval probability or right-censor survival; no NLL clipping',phase='PREAPRIL'))
    risk=[]
    for i in range(1,6):
        for s in read(ROOT/f'RISK_BOUNDARIES/fold{i}_{grid}.json')['support']:risk.append(dict(fold=i,scope='TRAIN',**s))
    pd.DataFrame(risk).to_csv(ROOT/'TAIL_RISK_AUDIT.csv',index=False)
    print('CALIBRATION_SELECTED',chosen,flush=True)
if __name__=='__main__':main()
