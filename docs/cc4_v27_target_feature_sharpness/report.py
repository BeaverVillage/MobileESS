"""Post-freeze scoring only; never changes selection or fitted models."""
from core import *
from experiment import predictions,calibrate,TARGETS,FEATURES
ROLES=['DEVELOPMENT','CALIBRATION','EXPOSED_EVALUATION','OOS_EXTENSION','MAY_HISTORICAL']
def daystats(y,q,dt):
    r=y-q[...,1];e=y-q[...,0]
    return np.column_stack([np.maximum(.9*r,-.1*r).mean(1),(r<=0).mean(1),q[...,1].sum(1),y.sum(1),abs(e).mean(1),abs(y.max(1)-q[...,0].max(1)),abs(y.argmax(1)-q[...,0].argmax(1))*dt])
def paired(a,b,seed=20260928):
    out=[];names=['Q90_pinball','Q90_coverage','requirement_ratio','Q50_MAE','peak_magnitude_MAE','peak_timing_MAE_hours'];rng=np.random.default_rng(seed);n=len(a)
    def score(s):return np.stack([s[...,0],s[...,1],s[...,2]/s[...,3],s[...,4],s[...,5],s[...,6]],axis=-1)
    point=score(a.mean(0))-score(b.mean(0))
    for block in [1,7]:
        starts=rng.integers(0,n,(2000,int(np.ceil(n/block))));ix=((starts[...,None]+np.arange(block))%n).reshape(2000,-1)[:,:n]
        delta=score(a[ix].mean(1))-score(b[ix].mean(1))
        for j,name in enumerate(names):
            finite=np.isfinite(delta[:,j]).all();lo,hi=np.quantile(delta[:,j],[.025,.975]) if finite else (np.nan,np.nan)
            out.append(dict(metric=name,block_days=block,delta=point[j],CI_low=lo,CI_high=hi,draws=2000,all_draws_finite=finite,days=n))
    return out
def main():
    assert (ROOT/'STAGE2_SELECTION_FREEZE.json').exists()
    z=np.load(ROOT/'TARGETS.npz');allmetrics=[];hour=[];lead=[];strata=[];frames=[];uncertainty=[];importance=[];resolution=[]
    qs={};qcals={};bursts={};dayrows=[]
    for t in TARGETS:
        y=z[t];dt=.25 if t=='T3' else 1;n=y.shape[1];burst=np.quantile(y[TRAIN][y[TRAIN]>0],.95);bursts[t]=burst
        for f in FEATURES:
            arm=t+'_'+f;q=predictions(arm);assert np.isfinite(q[OOS]).all(),arm
            qc,avail,receipt=calibrate(arm,q);expected=read(ROOT/'FEATURE_SELECTION_FREEZE.json')['calibrations'][arm+'_M0'];assert receipt==expected
            qs[arm]=q;qcals[arm]=qc
            for variant,p in [('RAW',q),('CALIBRATED',qc)]:
                for role in ROLES:
                    ids=role_ids(role);m=metrics(y[ids],p[ids],burst,dt);m['Q90_pinball_per_TRAIN_mean']=m['Q90_pinball']/y[TRAIN].mean()
                    allmetrics.append(dict(arm=arm,target=t,features=f,model='M0',variant=variant,role=role,**m))
                    for j in range(n):hour.append(dict(arm=arm,target=t,variant=variant,role=role,slot=j,target_hour=j*dt,**metrics(y[ids,j],p[ids,j],burst,dt)))
                    for group,slots in enumerate(np.array_split(np.arange(n),4)):
                        lead.append(dict(arm=arm,target=t,variant=variant,role=role,lead_group=f'{6+6*group}..{12+6*group}',**metrics(y[ids][:,slots],p[ids][:,slots],burst,dt)))
                    yy=y[ids];pp=p[ids]
                    masks={'zero':yy==0,'positive':yy>0,'burst':yy>burst,'nonburst':yy<=burst}
                    for weekday in range(7):masks[f'weekday_{weekday}']=np.broadcast_to((pd.to_datetime(DAYS[ids]).dayofweek==weekday)[:,None],yy.shape)
                    for month in np.unique(pd.to_datetime(DAYS[ids]).strftime('%Y-%m')):masks[month]=np.broadcast_to((pd.to_datetime(DAYS[ids]).strftime('%Y-%m')==month)[:,None],yy.shape)
                    for label,mask in masks.items():
                        if mask.any():strata.append(dict(arm=arm,target=t,variant=variant,role=role,stratum=label,**metrics(yy[mask],pp[mask],burst,dt)))
                    for i in ids:dayrows.append(dict(arm=arm,target=t,variant=variant,role=role,day=DAYS[i],**metrics(y[i:i+1],p[i:i+1],burst,dt)))
            frames.append(pd.DataFrame(dict(arm=arm,target=t,day_index=np.repeat(OOS,n),target_day=np.repeat(DAYS[OOS],n),slot=np.tile(np.arange(n),len(OOS)),slot_hours=dt,target_unit='requested_GPU_arrivals' if t=='T1' else ('average_active_GPU' if t=='T3' else 'GPUh'),original_role=np.repeat(L.split.iloc[OOS].to_numpy(),n),original_eligible=np.repeat(L.eligible.iloc[OOS].to_numpy(),n),y=y[OOS].ravel(),raw_Q50=q[OOS,:,0].ravel(),raw_Q90=q[OOS,:,1].ravel(),calibrated_Q90=qc[OOS,:,1].ravel(),label_GPUh=(y[OOS]*dt).ravel() if t!='T1' else np.full(len(OOS)*n,np.nan),raw_Q90_GPUh=(q[OOS,:,1]*dt).ravel() if t!='T1' else np.full(len(OOS)*n,np.nan),calibration_available=np.repeat(avail[OOS],n))))
            names=read(ROOT/'FEATURE_GROUPS.json')[arm];total=None;count=0
            path=ROOT/'runs/M0'/(t+'_F0' if f=='F3' else arm)
            for pth in path.glob(DAYS[CAL[-1]]+'.npz'):
                data=np.load(pth);imp=data['importance'];total=imp.copy() if total is None else total+imp;count+=1
            if arm in ['T0_F0','T0_F3']:
                total=np.load(ROOT/'A0_IMPORTANCE.npz')['importance'];count=1
            if total is not None:
                for k,name in enumerate(names):importance.append(dict(arm=arm,feature=name,gain=total[0,k],split=total[1,k],refits=count,representative_day=DAYS[CAL[-1]],status='alias' if f=='F3' else 'new'))
            else:
                for name in names:importance.append(dict(arm=arm,feature=name,gain=None,split=None,refits=273,status='A0 replay importance not retained; prediction identity verified'))
        for f in FEATURES[1:]:
            for role in ROLES[2:]:
                ids=role_ids(role)
                for variant,source in [('RAW',qs),('CALIBRATED',qcals)]:
                    a=daystats(y[ids],source[t+'_'+f][ids],dt);b=daystats(y[ids],source[t+'_F0'][ids],dt)
                    for row in paired(a,b):uncertainty.append(dict(contrast=t+'_'+f+' minus '+t+'_F0',target=t,role=role,variant=variant,**row))
    # Resolution ablation uses common hourly labels; aggregated marginal Q90 is
    # a reserve proxy, not a recalculated hourly or joint daily quantile.
    for f in ['F0','F5']:
        for role in ROLES:
            ids=role_ids(role)
            for t in ['T2','T3']:
                p=qs[t+'_'+f][ids];p=p.reshape(-1,24,4,2).mean(2) if t=='T3' else p
                m=metrics(z['T2'][ids],p,bursts['T2'])
                resolution.append(dict(arm=t+'_'+f,role=role,common_resolution='hourly occupancy',Q90_semantics='mean of four marginal15min quantiles reserve proxy' if t=='T3' else 'hourly marginal quantile',**m))
            if role in ROLES[2:]:
                a=daystats(z['T2'][ids],qs['T3_'+f][ids].reshape(-1,24,4,2).mean(2),1);b=daystats(z['T2'][ids],qs['T2_'+f][ids],1)
                for row in paired(a,b):uncertainty.append(dict(contrast='T3_'+f+' hourly aggregate minus T2_'+f,target='COMMON_HOURLY',role=role,variant='RAW',**row))
    mf=pd.DataFrame(allmetrics)
    relative=[];pareto=[]
    for (t,role,var),g in mf.groupby(['target','role','variant']):
        base=g[g.features.eq('F0')].iloc[0];cols=['calibration_error','Q90_pinball','requirement_ratio']
        for _,r in g.iterrows():
            relative.append(dict(target=t,role=role,variant=var,arm=r.arm,delta_pinball=r.Q90_pinball-base.Q90_pinball,pinball_relative=r.Q90_pinball/base.Q90_pinball,delta_coverage=r.Q90_coverage-base.Q90_coverage,requirement_ratio_relative=r.requirement_ratio/base.requirement_ratio,delta_MAE=r.Q50_MAE-base.Q50_MAE))
            dominates=g[((g[cols]<=r[cols]).all(axis=1))&((g[cols]<r[cols]).any(axis=1))]
            pareto.append(dict(target=t,role=role,variant=var,arm=r.arm,dominated=len(dominates)>0,dominated_by=';'.join(dominates.arm),**{c:r[c] for c in cols}))
    csv('ARM_METRICS.csv',allmetrics);csv('HOUR_SLOT_METRICS.csv',hour);csv('LEAD_GROUP_METRICS.csv',lead);csv('STRATIFIED_METRICS.csv',strata);csv('DAY_METRICS.csv',dayrows)
    csv('FEATURE_ABLATION.csv',relative);csv('PARETO_FRONT.csv',pareto);csv('FEATURE_IMPORTANCE.csv',importance);csv('RESOLUTION_COMPARISON.csv',resolution)
    pd.concat(frames,ignore_index=True).to_parquet(ROOT/'PREDICTIONS.parquet',index=False)
    stage2=[];s2frames=[];s2=read(ROOT/'STAGE2_SELECTION_FREEZE.json')
    for arm in read(ROOT/'FEATURE_SELECTION_FREEZE.json')['candidates']:
        t=arm[:2];y=z[t];dt=.25 if t=='T3' else 1
        for model in ['M0','M1']:
            q=predictions(arm,model);assert np.isfinite(q[OOS]).all();qc,avail,r=calibrate(arm,q);assert r==s2['calibrations'][arm+'_'+model]
            for variant,p in [('RAW',q),('CALIBRATED',qc)]:
                for role in ROLES:
                    ids=role_ids(role);stage2.append(dict(arm=arm,target=t,model=model,variant=variant,role=role,**metrics(y[ids],p[ids],bursts[t],dt)))
                    if model=='M1' and role in ROLES[2:]:
                        source=qs if variant=='RAW' else qcals
                        for row in paired(daystats(y[ids],p[ids],dt),daystats(y[ids],source[arm][ids],dt)):uncertainty.append(dict(contrast=arm+' M1 minus M0',target=t,role=role,variant=variant,**row))
            n=y.shape[1];s2frames.append(pd.DataFrame(dict(arm=arm,model=model,target_day=np.repeat(DAYS[OOS],n),slot=np.tile(np.arange(n),len(OOS)),y=y[OOS].ravel(),raw_Q50=q[OOS,:,0].ravel(),raw_Q90=q[OOS,:,1].ravel(),calibrated_Q90=qc[OOS,:,1].ravel())))
    csv('STAGE2_MODEL_METRICS.csv',stage2);csv('PAIRED_UNCERTAINTY.csv',uncertainty)
    pd.concat(s2frames,ignore_index=True).to_parquet(ROOT/'STAGE2_PREDICTIONS.parquet',index=False)
    print('REPORT_METRICS_COMPLETE',flush=True)
if __name__=='__main__':main()
