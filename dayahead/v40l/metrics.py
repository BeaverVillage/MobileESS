import numpy as np
import pandas as pd
from .protocol import GATES,IDS,SPLIT

def safety(f,k0,bound,stage):
    n=len(f)
    if not n:return {'N':0,'status':'INSUFFICIENT_SUPPORT'}
    y=f.runtime_seconds.to_numpy(float);g=f.num_gpus_req.to_numpy(float);b=np.asarray(bound,float);k0=np.asarray(k0,float)
    finite=np.isfinite(b);covered=finite&(y<=b)
    starts=f.start_time.astype('datetime64[ns, UTC]').astype('int64').to_numpy()/1e9
    missed=np.where(finite,np.maximum(y-b,0),0)
    over=np.where(finite,np.maximum(b-y,0),0)
    slots=np.where(finite,np.maximum(0,np.ceil((starts+y)/300)-np.ceil((starts+b)/300)),0)
    dates=f.submit_time.dt.strftime('%Y-%m-%d').to_numpy()
    days=pd.date_range(SPLIT[stage][0],pd.Timestamp(SPLIT[stage][1])-pd.Timedelta(days=1)).strftime('%Y-%m-%d').tolist()
    ns=np.array([(dates==d).sum() for d in days]);cs=np.array([covered[dates==d].sum() for d in days])
    gs=np.array([g[dates==d].sum() for d in days]);cg=np.array([(g*covered)[dates==d].sum() for d in days])
    rng=np.random.default_rng(GATES['bootstrap']['seed']);ix=rng.integers(0,len(days),size=(GATES['bootstrap']['resamples'],len(days)))
    den=ns[ix].sum(axis=1);gden=gs[ix].sum(axis=1)
    boot=cs[ix].sum(axis=1)[den>0]/den[den>0];gboot=cg[ix].sum(axis=1)[gden>0]/gden[gden>0]
    return {'N':n,'status':'SUPPORT_SUFFICIENT' if n>=100 else 'INSUFFICIENT_SUPPORT','coverage':float(covered.mean()),
      'GPU_weighted_coverage':float(np.sum(g*covered)/g.sum()),'active_miss_GPU_5min_slots':float(np.sum(g*slots)),
      'predicted_finished_but_actually_active_job_rate':float(np.mean(finite&(y>b))),
      'GPU_weighted_underprediction_seconds':float(np.sum(g*missed)),
      'overreserved_GPU_hours':float(np.sum(g*over)/3600),'reserved_GPU_hours':float(np.sum(g*np.where(finite,b,0))/3600),
      'mean_safe_duration_seconds':float(np.mean(b[finite])) if finite.any() else None,
      'mean_safe_inflation_seconds':float(np.mean((b-k0)[finite])) if finite.any() else None,
      'mean_safe_to_nominal_ratio':float(np.mean(b[finite])/np.mean(k0[finite])) if finite.any() and np.mean(k0[finite])>0 else None,
      'abstentions':int((~finite).sum()),'abstention_accounting':'Abstentions count uncovered in full-cohort coverage; duration efficiency metrics only served rows. Any abstention prevents eligibility.',
      'UTC_day_block_bootstrap95_coverage':np.quantile(boot,[.025,.975]).tolist(),
      'UTC_day_block_bootstrap95_GPU_coverage':np.quantile(gboot,[.025,.975]).tolist(),
      'observed_days':int((ns>0).sum()),'daily_N':dict(zip(days,ns.tolist())),
      'scope':'Nominal-workload duration replay on available complete-case cohort; no electrical/grid authority'}

def report(f,k0,p,x,stage):
    h=x.hardware.eq('H100').to_numpy();s=x.standby.eq(1).to_numpy();strong=x.exact_count.ge(100).to_numpy()
    masks={'overall':np.ones(len(f),bool),'H100':h,'H100-standby':h&s,'STRONG_SUPPORT H100-standby':h&s&strong}
    for state in ['STRONG_SUPPORT','SPARSE_SUPPORT','REGIME_MISMATCH','OUT_OF_SUPPORT']:masks[state]=x.support_class.eq(state).to_numpy()
    for b in range(5):masks['wall_bucket_'+str(b)]=x.wall_bucket.eq(b).to_numpy()
    for hh in [12,24,48]:masks[str(hh)+'h exact']=x.requested_seconds.eq(hh*3600).to_numpy()
    for name,mask in [('COMPLETED H100',h),('COMPLETED H100-standby',h&s)]:masks['retrospective '+name]=mask&f.job_state.eq('COMPLETED').to_numpy()
    metrics={name:{'Q90':safety(f.loc[m],k0[m],p[m,0],stage),'Q95':safety(f.loc[m],k0[m],p[m,1],stage)} for name,m in masks.items()}
    gates={}
    for name in ['overall','H100','STRONG_SUPPORT H100-standby']:
        a=metrics[name]['Q90'];gates[name]=a['N']>=100 and a['coverage']>=.9
    gates['GPU_weighted_overall']=metrics['overall']['Q90']['GPU_weighted_coverage']>=.9
    gates['finite_no_abstentions']=bool(np.isfinite(p).all())
    gates['monotonic_safe']=bool(np.all(p[:,0]>=k0)&np.all(p[:,1]>=p[:,0]))
    return {'metrics':metrics,'gates':gates,'eligible':bool(all(gates.values())),'required_insufficient_subgroups':[name for name in ['overall','H100','STRONG_SUPPORT H100-standby'] if metrics[name]['Q90']['N']<100]}

def choose(records):
    eligible=[cid for cid,r in records.items() if r.get('eligible')]
    if not eligible:return None,[]
    winner=min(eligible,key=lambda cid:tuple(records[cid]['metrics']['overall']['Q90'][m] for m in GATES['efficiency_order'][:-1])+(IDS.index(cid),))
    return winner,eligible
