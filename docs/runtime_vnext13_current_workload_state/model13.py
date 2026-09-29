"""V9 hazard architecture plus preregistered V13 state families."""
from common13 import *
from features8 import engineer
from hazard10 import Hazard,age_matrix
import lightgbm as lgb
import time,gc

def columns(arm, static, regime, ablation=None):
    level=int(arm.split('_')[-1][1:])
    prefixes=['a_','p_','r_','c_','x_'][:(level if level<4 else 5)]
    new=[c for c in regime if any(c.startswith(p) for p in prefixes)]
    group={'A':'arrival','B':'pending','C':'running','D':'composition','E':'interaction'}.get(ablation)
    contract=read(ROOT/'CURRENT_STATE_FEATURE_CONTRACT.json')
    def keep(c):
        if group and c in contract['groups'][group]:return False
        if group in contract['interaction_dependencies'].get(c,[]):return False
        return True
    return list(static)+[c for c in new if keep(c)]

def matrix(f,pre,regime,cols):
    x=engineer(f,pre['categorical_mappings'])[pre['columns']].reset_index(drop=True)
    new=[c for c in cols if c not in pre['columns']]
    if new:x=pd.concat([x,regime.loc[f.job_id,new].reset_index(drop=True)],axis=1)
    return x[cols].astype('float32')

def fit(train,x,pre,arm,ablation=None):
    begin=time.perf_counter();edges=np.array(read(ROOT/'HAZARD_BIN_CONTRACT.json')['edges_seconds'],float)
    k=len(edges)-1;lower=train.duration_lower.to_numpy(float);exact=train.event.to_numpy(bool)
    within=exact&(lower<=edges[-1])
    counts=np.minimum(np.where(within,np.searchsorted(edges[1:],lower,side='left')+1,np.searchsorted(edges[1:],lower,side='right')),k)
    rows=np.repeat(np.arange(len(train)),counts)
    bins=np.arange(len(rows))-np.repeat(np.cumsum(counts)-counts,counts)
    xx=np.column_stack([x.to_numpy()[rows],age_matrix(edges)[bins]])
    y=(within[rows]&(bins==counts[rows]-1)).astype('int8')
    cats=[list(x.columns).index(c) for c in ['qos','partition','account']]
    learner=read(ROOT/'EXPERIMENT_PROTOCOL.json')['learner']
    model=lgb.LGBMClassifier(**learner);model.fit(xx,y,categorical_feature=cats)
    del xx;gc.collect()
    return Hazard(dict(kind='D1',arm=arm,ablation=ablation,columns=list(x.columns),edges=edges.tolist(),
        tail_exponential_rate=None,training_seconds=time.perf_counter()-begin,TRAIN_N=len(train),person_period_N=len(rows),
        fit_cutoff=pre['fit_cutoff'],provenance_mode='Kestrel_trace_proxy',preprocessing=pre,
        learner=learner,TAIL_GRID_CHANGED_FROM_V9=False),model.booster_)

def frozen_v9(i):
    folder=V9/'FOLD_MODELS'/f'fold{i}/D1';meta=read(folder/'model.json')
    meta.update(tail_exponential_rate=None,reused_frozen_V9=True)
    return Hazard(meta,lgb.Booster(model_str=(folder/'0.txt').read_text(encoding='utf-8')))
