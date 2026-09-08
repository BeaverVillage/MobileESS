from .common import *
from scipy import stats as ss,optimize
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
import lightgbm as lgb,xgboost as xgb,pickle,time

LEVELS=np.array([.01,.05,.1,.25,.5,.75,.9,.95,.99])
def lgb_kwargs(trial=0):return dict(n_estimators=300,learning_rate=[.03,.08][trial],max_depth=4,num_leaves=15,min_child_samples=30,
    reg_lambda=1.,max_bin=127,random_state=SEED,n_jobs=4,verbosity=-1,deterministic=True,force_col_wise=True)
def fit_r(n,mu):
    fit=optimize.minimize_scalar(lambda lr:-ss.nbinom.logpmf(n,np.exp(lr),np.exp(lr)/(np.exp(lr)+mu)).sum(),bounds=(-7,7),method='bounded')
    assert fit.success;return float(np.exp(fit.x))
def seasonal(v,mask):
    q=np.zeros((len(v),2));mean=np.zeros(len(v))
    for k in range(len(v)):
        a=v[k,mask[k]]
        if len(a):q[k]=np.quantile(a,[.5,.9]);mean[k]=a.mean()
    return q,mean
def hurdle_predict(heads,X,cap=None):
    occ=heads[0].predict_proba(X)[:,1];grid=np.maximum.accumulate(np.maximum(np.column_stack([h.predict(X) for h in heads[1:]]),0),axis=1)
    if cap is not None:grid=np.minimum(grid,cap)
    q=[];knots=np.r_[0.,LEVELS,1.];vals=np.column_stack([np.zeros(len(X)),grid,grid[:,-1]])
    for tau in [.5,.9]:
        u=np.clip((tau-(1-occ))/np.maximum(occ,1e-12),0,1);hi=np.searchsorted(knots,u,side='right').clip(1,len(knots)-1);lo=hi-1
        q.append(vals[np.arange(len(X)),lo]+(u-knots[lo])/(knots[hi]-knots[lo])*(vals[np.arange(len(X)),hi]-vals[np.arange(len(X)),lo]))
    return np.column_stack(q)
def tweedie_predict(mu,phi,power,M=10000):
    q=np.zeros((len(mu),2));cq=np.zeros_like(q);mean=np.zeros(len(mu));t0=time.monotonic()
    for day in range(len(mu)//96):
        ix=slice(day*96,(day+1)*96);mm=mu[ix];lam=mm**(2-power)/(phi*(2-power));alpha=(2-power)/(power-1);theta=phi*(power-1)*mm**(power-1)
        rng=np.random.default_rng(SEED+7919*day);n=rng.poisson(lam[:,None],size=(96,M));s=rng.gamma(n*alpha,theta[:,None]);assert np.isfinite(s).all() and (s>=0).all()
        q[ix]=np.quantile(s,[.5,.9],axis=1).T;cq[ix]=np.quantile(np.cumsum(s,axis=0),[.5,.9],axis=1).T;mean[ix]=s.mean(1)
    return q,cq,mean,time.monotonic()-t0
def fit_forecaster(name,trial,X,y,train,u,directory,tag=None):
    directory.mkdir(parents=True,exist_ok=True);stem=tag or f'trial_{trial}';t0=time.monotonic();heads=[];kw=lgb_kwargs(trial)
    fitmask=train if name=='B2' else train&(y<=u) if name=='PB1' else train
    if name in ['B2','PB1']:
        heads=[lgb.LGBMClassifier(objective='binary',**kw).fit(X[fitmask],y[fitmask]>0)]
        for level in LEVELS:heads.append(lgb.LGBMRegressor(objective='quantile',alpha=float(level),**kw).fit(X[fitmask&(y>0)],y[fitmask&(y>0)]))
    elif name=='B3':
        power=[1.3,1.7][trial];kw['learning_rate']=.05;heads=[lgb.LGBMRegressor(objective='tweedie',tweedie_variance_power=power,**kw).fit(X[fitmask],y[fitmask])]
    else:raise ValueError(name)
    fit_time=time.monotonic()-t0
    for k,head in enumerate(heads):head.booster_.save_model(str(directory/f'{stem}_head{k}.txt'))
    t0=time.monotonic()
    if name=='B3':
        mu=np.maximum(heads[0].predict(X),1e-6);phi=np.mean((y[train]-mu[train])**2/mu[train]**power)
        q,cq,mean,simulation=tweedie_predict(mu,float(phi),power)
        np.savez_compressed(directory/f'{stem}_distribution.npz',mu=mu,phi=phi,power=power,cumulative_q=cq,MC_mean=mean)
    else:q=hurdle_predict(heads,X,u if name=='PB1' else None);simulation=0.
    np.save(directory/f'{stem}_q.npy',q)
    return q,{'candidate':name,'trial':trial,'tag':stem,'device':'cpu','seed':SEED,'threads':4,'fit_rows':int(fitmask.sum()),'fit_positive_rows':int((fitmask&(y>0)).sum()),
      'fit_time_seconds':fit_time,'prediction_time_seconds':time.monotonic()-t0,'scenario_time_seconds':simulation,'body_training_excludes_bursts':name=='PB1',
      'objective':'binary +9 conditional quantile heads' if name!='B3' else 'Tweedie','rounds':300,'early_stopping':'None; fixed 300 rounds','deterministic':True}
def count_predict(model,r,X,high):
    mu=np.maximum(model.predict(X),1e-6);prob=ss.nbinom.sf(np.floor(high),r,r/(r+mu));p90=ss.nbinom.ppf(.9,r,r/(r+mu))
    return np.column_stack([mu,p90,prob])
def fit_count(X,n,train,high,directory,tag='full'):
    t0=time.monotonic();kw=lgb_kwargs(0);kw['learning_rate']=.05
    model=lgb.LGBMRegressor(objective='poisson',**kw).fit(X[train],n[train]);r=fit_r(n[train],np.maximum(model.predict(X[train]),1e-6));fit_time=time.monotonic()-t0
    model.booster_.save_model(str(directory/f'{tag}_count.txt'));t0=time.monotonic();p=count_predict(model,r,X,high)
    return p,{'candidate':'N1','tag':tag,'dispersion_r':r,'fit_rows':int(train.sum()),'fit_time_seconds':fit_time,'prediction_time_seconds':time.monotonic()-t0,'device':'cpu','seed':SEED,'threads':4}
def fit_classifier(name,trial,X,y,train,directory,tag=None):
    t0=time.monotonic();stem=tag or f'trial_{trial}'
    if name=='C0':model=float(y[train].mean())
    elif name=='C1':model=make_pipeline(StandardScaler(),LogisticRegression(C=[.1,1.][trial],max_iter=1000,solver='lbfgs',random_state=SEED,n_jobs=1)).fit(X[train],y[train])
    elif name=='C2':model=lgb.LGBMClassifier(objective='binary',**lgb_kwargs(trial)).fit(X[train],y[train])
    elif name=='C3':model=xgb.XGBClassifier(n_estimators=300,learning_rate=[.03,.08][trial],max_depth=4,min_child_weight=5,reg_lambda=1.,subsample=1.,colsample_bytree=1.,
        objective='binary:logistic',eval_metric='logloss',tree_method='hist',device='cpu',random_state=SEED,n_jobs=4).fit(X[train],y[train])
    else:raise ValueError(name)
    fit_time=time.monotonic()-t0;t0=time.monotonic();p=np.full(len(X),model) if name=='C0' else model.predict_proba(X)[:,1]
    prediction_time=time.monotonic()-t0;directory.mkdir(parents=True,exist_ok=True)
    with (directory/f'{stem}_model.pkl').open('wb') as f:pickle.dump(model,f,protocol=5)
    np.save(directory/f'{stem}_prob.npy',p)
    assert np.isfinite(p).all() and (p>=0).all() and (p<=1).all()
    return p,{'candidate':name,'trial':trial,'tag':stem,'fit_time_seconds':fit_time,'prediction_time_seconds':prediction_time,'fit_rows':int(train.sum()),
      'device':'cpu','seed':SEED,'threads':1 if name=='C1' else 4,'class_weight':'None','probability_calibration':'None; natural-frequency loss','early_stopping':'None; fixed registered iteration/round cap'}

def envelope_fit(y,count_probability,slot,train,cal,u):
    cut=float(np.quantile(count_probability[train],.75));cls=(count_probability>=cut).astype(int);tod=slot//24;burst=cal&(y>u);z=y[burst]
    assert len(z)>0
    r0=float(np.quantile(z,.9));r1=float(np.quantile(z,.95));tables={}
    for group in ['tod_count','count','tod']:
        key=tod*2+cls if group=='tod_count' else cls if group=='count' else tod
        tables[group]={str(int(k)):{'N':int((burst&(key==k)).sum()),'Q90':float(np.quantile(y[burst&(key==k)],.9))} for k in np.unique(key[burst])}
    estimates=[];paths=[]
    for t,c in zip(tod,cls):
        value=r0;path='global'
        for group,key in [('tod_count',str(int(t*2+c))),('count',str(int(c))),('tod',str(int(t)))]:
            v=tables[group].get(key)
            if v and v['N']>=30:value=v['Q90'];path=f'{group}:{key}';break
        estimates.append(value);paths.append(path)
    report={'R0':{'policy':'GLOBAL_BURST_Q90','value_GPUh':r0,'CAL_burst_N':len(z),'quantile':.9,'CAL_sorted_burst_values':np.sort(z)},
      'R1':{'policy':'GLOBAL_BURST_Q95','value_GPUh':r1,'CAL_burst_N':len(z),'quantile':.95},
      'R2':{'policy':'CONDITIONAL_BURST_Q90','count_risk_cut_TRAIN_Q75':cut,'groups':tables,'minimum_group_N':30,'time_blocks':'Four fixed 6-hour blocks','hierarchy':['tod_count','count','tod','global'],
        'fallback_counts_all_rows':pd.Series(paths).value_counts().to_dict(),'global':r0,'CAL_burst_N':len(z)}}
    return {'R0':np.full(len(y),r0),'R1':np.full(len(y),r1),'R2':np.array(estimates)},report,np.array(paths,dtype='U30')
