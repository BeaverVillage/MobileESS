import numpy as np
from .protocol import POINT_GATE

def point(y,p):
    y,p=np.asarray(y,float),np.asarray(p,float);d=y-p
    if not len(y):return {'N':0}
    return {'N':len(y),'pinball_Q50':float(np.mean(abs(d))*.5),'MAE':float(np.mean(abs(d))),
      'underprediction':float(np.mean(d>0)),'median_calibration_error':float(abs(np.mean(d>0)-.5)),
      'mean_signed_error_diagnostic':float(np.mean(d)),'median_signed_error':float(np.median(d))}
def subgroups(f):
    h=f.partition.str.contains('h100',case=False,na=False);s=f.qos.eq('standby')
    masks={'overall':np.ones(len(f),bool),'H100':h,'standby':s,'H100-standby':h&s,'COMPLETED H100-standby':h&s&f.job_state.eq('COMPLETED')}
    for state in sorted(f.job_state.dropna().unique()):masks['status/'+str(state)]=f.job_state.eq(state)
    b=np.searchsorted(POINT_GATE['wall_buckets'],f.requested_seconds)
    for i in sorted(set(b)):masks['wall_bucket/'+str(i)]=b==i
    return masks
def report(f,p):return {k:point(f.runtime_seconds[m],np.asarray(p)[m]) for k,m in subgroups(f).items()}
def point_gate(base,new,deterministic):
    b=base['overall'];n=new['overall'];sg='COMPLETED H100-standby';bs=base[sg];ns=new[sg]
    catastrophic=[k for k,v in new.items() if k!='overall' and v['N']>=100 and v['MAE']>base[k]['MAE']*1.25]
    gates={'pinball':n['pinball_Q50']<b['pinball_Q50'],'MAE':n['MAE']<b['MAE'],
      'median_calibration':n['median_calibration_error']<b['median_calibration_error'],
      'completed_H100_standby_median':ns['N']>=100 and ns['median_calibration_error']<bs['median_calibration_error'],
      'no_catastrophic_subgroup_regression':not catastrophic,'determinism':bool(deterministic)}
    return {'gates':gates,'catastrophic_subgroups':catastrophic,'eligible':all(gates.values())}
def safety(f,p):
    y=f.runtime_seconds.to_numpy(float);p=np.asarray(p,float);g=f.num_gpus_req.to_numpy(float)
    starts=f.start_time.astype('datetime64[ns, UTC]').astype('int64').to_numpy()/1e9
    miss=np.maximum(y-p,0);over=np.maximum(p-y,0)
    slots=np.maximum(0,np.ceil((starts+y)/300)-np.ceil((starts+p)/300))
    return {'N':len(f),'coverage':float(np.mean(y<=p)),
      'GPU_weighted_coverage':float(np.sum(g*(y<=p))/g.sum()),
      'GPU_weighted_underprediction_seconds':float(np.sum(g*miss)),
      'overreserved_GPU_hours':float(np.sum(g*over)/3600),'reserved_GPU_hours':float(np.sum(g*p)/3600),
      'active_miss_GPU_5min_slots':float(np.sum(g*slots)),
      'predicted_finished_but_actually_active_GPU_slots':float(np.sum(g*slots)),
      'scope':'workload-layer duration replay; no independent grid-critical line authority','grid_critical_improvement':None}
