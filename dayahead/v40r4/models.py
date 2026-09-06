from .common import *
from scipy import optimize,stats as ss,special
from .distributions import nb_logpmf
import time,importlib.metadata

def tree_features(a):
    return np.concatenate([np.repeat(a['past'].reshape(len(a['past']),-1),48,axis=0),a['future'].reshape(-1,15)],1)
def fit_r(n,mu):
    fit=optimize.minimize_scalar(lambda lr:-nb_logpmf(n,mu,np.exp(lr)).sum(),bounds=(-7,7),method='bounded')
    assert fit.success;return float(np.exp(fit.x))
def save_params(path,p):
    np.savez_compressed(path,**p)
def load_params(path):
    f=np.load(path);return {k:(f[k].item() if f[k].ndim==0 else f[k]) for k in f.files}

def fit_classical(name,trial,a,m,reg,directory):
    import lightgbm as lgb
    started=time.monotonic();train=np.repeat(m['TRAIN'],48);y=a['target'].ravel();n=a['count'].ravel()
    s=a['sufficient'].reshape(-1,6);sumlog=s[:,1]+s[:,4];sumlog2=s[:,2]+s[:,5];positive=train&(n>0)
    kw=dict(n_estimators=400,learning_rate=[.03,.08][trial],max_depth=6,num_leaves=31,min_child_samples=30,
        reg_lambda=1.,max_bin=127,random_state=SEED,n_jobs=4,verbosity=-1,deterministic=True,force_col_wise=True)
    heads=[]
    if name in ['B2','B3','B5']:X=tree_features(a)
    if name=='B2':
        occur=lgb.LGBMClassifier(objective='binary',**kw).fit(X[train],y[train]>0);heads.append(occur)
        levels=np.array([.01,.05,.1,.25,.5,.75,.9,.95,.99]);grid=[]
        for tau in levels:
            mod=lgb.LGBMRegressor(objective='quantile',alpha=float(tau),**kw).fit(X[train&(y>0)],y[train&(y>0)])
            heads.append(mod);grid.append(mod.predict(X))
        p={'kind':'HURDLE','occ':occur.predict_proba(X)[:,1],'grid':np.maximum.accumulate(np.maximum(np.stack(grid,1),0),1),'levels':levels}
    elif name=='B3':
        power=[1.3,1.7][trial];kw['learning_rate']=.05
        mod=lgb.LGBMRegressor(objective='tweedie',tweedie_variance_power=power,**kw).fit(X[train],y[train]);heads=[mod]
        mu=np.maximum(mod.predict(X),1e-6);phi=float(np.mean((y[train]-mu[train])**2/mu[train]**power))
        p={'kind':'TWEEDIE','lam':mu**(2-power)/(phi*(2-power)),'alpha':np.full(len(mu),(2-power)/(power-1)),
           'theta':phi*(power-1)*mu**(power-1),'mean':mu,'power':power,'phi':phi}
    elif name=='B4':
        X=a['compact'];ridge=[.1,1.][trial];r=read('V40R4_COUNT_DISTRIBUTION_DIAGNOSTIC.json')['families']['NB']['dispersion_r']
        beta=np.zeros(X.shape[1]);beta[0]=np.log(n[train].mean())
        for cycle in range(3):
            def objective(b):
                eta=X[train]@b;mu=np.exp(np.clip(eta,-9,9));pen=b.copy();pen[0]=0
                value=-nb_logpmf(n[train],mu,r).sum()+.5*ridge*np.sum(pen**2)
                grad=X[train].T@(r*(mu-n[train])/(r+mu)*((eta>-9)&(eta<9)))+ridge*pen
                return value,grad
            fit=optimize.minimize(objective,beta,jac=True,method='L-BFGS-B',bounds=[(-5,5)]*len(beta),options={'maxiter':300})
            beta=fit.x;mu=np.exp(np.clip(X@beta,-9,9));r=fit_r(n[train],mu[train])
        W=n[positive];xp=X[positive]
        severity_beta=np.linalg.solve(xp.T@(W[:,None]*xp)+ridge*np.eye(X.shape[1]),xp.T@sumlog[positive])
        loc=X@severity_beta;sigma=np.sqrt(np.sum(sumlog2[train]-2*loc[train]*sumlog[train]+n[train]*loc[train]**2)/n[train].sum())
        p={'kind':'LOGNORMAL','mu':mu,'r':np.full(len(n),r),'loc':loc,'sigma':np.full(len(n),max(.1,sigma))}
        np.savez_compressed(directory/f'trial_{trial}_glm.npz',beta=beta,severity_beta=severity_beta,r=r,sigma=sigma)
    elif name=='B5':
        countmod=lgb.LGBMRegressor(objective='poisson',**kw).fit(X[train],n[train]);heads.append(countmod)
        mu=np.maximum(countmod.predict(X),1e-6);r=fit_r(n[train],mu[train])
        mod=lgb.LGBMRegressor(objective='regression',**kw).fit(X[positive],sumlog[positive]/n[positive],sample_weight=n[positive]);heads.append(mod)
        loc=mod.predict(X);sigma=np.sqrt(np.sum(sumlog2[train]-2*loc[train]*sumlog[train]+n[train]*loc[train]**2)/n[train].sum())
        p={'kind':'LOGNORMAL','mu':mu,'r':np.full(len(n),r),'loc':loc,'sigma':np.full(len(n),max(.1,sigma))}
    else:raise ValueError(name)
    for k,head in enumerate(heads):head.booster_.save_model(str(directory/f'trial_{trial}_head{k}.txt'))
    for key in ['mu','r','sigma','tail_sigma']:
        if key in p:assert np.all(np.asarray(p[key])>0)
    return p,{'family':name,'trial':trial,'device':'cpu','seed':SEED,'threads':4,'fit_time_seconds':time.monotonic()-started,
       'lightgbm_version':lgb.__version__,'numpy_version':np.__version__,'training_rows':int(train.sum()),'training_job_N':int(n[train].sum())}

def fit_neural(trial,a,m,reg,directory,tag=None):
    from .neural import CCAF,deterministic,joint_loss
    import torch
    deterministic();device='cuda:0' if torch.cuda.is_available() else 'cpu';started=time.monotonic()
    model=CCAF(reg['CCAF_initialization']).to(device);lr=reg['CCAF_training']['learning_rates'][trial]
    opt=torch.optim.Adam(model.parameters(),lr=lr,weight_decay=1e-4)
    past=torch.tensor(a['past'],device=device);future=torch.tensor(a['future'],device=device)
    count=torch.tensor(a['count'],device=device);suff=torch.tensor(a['sufficient'],device=device,dtype=torch.float32)
    train=np.flatnonzero(m['TRAIN']);dev=np.flatnonzero(m['DEVELOPMENT']);mean=float(a['count'][m['TRAIN']].mean())
    rng=np.random.default_rng(SEED);best=np.inf;beststate=None;bestepoch=0;history=[]
    for epoch in range(1,41):
        model.train();losses=[];order=rng.permutation(train)
        for first in range(0,len(order),16):
            ix=order[first:first+16];opt.zero_grad(set_to_none=True)
            loss=joint_loss(model(past[ix],future[ix]),count[ix],suff[ix],mean,float(a['tail_u']))
            assert torch.isfinite(loss);loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),1.);opt.step();losses.append(float(loss.detach()))
        model.eval()
        with torch.no_grad():
            validation=float(joint_loss(model(past[dev],future[dev]),count[dev],suff[dev],mean,float(a['tail_u'])))
        history.append({'epoch':epoch,'training_joint_NLL':float(np.mean(losses)),'development_joint_NLL':validation})
        if validation<best-1e-5:best=validation;bestepoch=epoch;beststate={k:v.detach().cpu().clone() for k,v in model.state_dict().items()}
        if epoch%10==0:print('CCAF',tag or trial,'epoch',epoch,'dev NLL',round(validation,4),flush=True)
        if epoch-bestepoch>=8:break
    model.load_state_dict(beststate);model.eval();pred={}
    with torch.no_grad():
        for first in range(0,len(past),16):
            out=model(past[first:first+16],future[first:first+16])
            for key,value in out.items():pred.setdefault(key,[]).append(value.cpu().numpy())
    pred={k:np.concatenate(v).reshape(-1).astype(float) for k,v in pred.items()};pred.update(kind='SPLICE',u=float(a['tail_u']))
    label=tag or f'trial_{trial}';torch.save(beststate,directory/f'{label}_weights.pt')
    meta={'trial':trial,'tag':label,'device':device,'seed':SEED,'threads':4,'library':'torch','version':torch.__version__,
      'CUDA':torch.version.cuda,'GPU':torch.cuda.get_device_name(0) if device.startswith('cuda') else None,
      'learning_rate':lr,'batch_size':16,'epochs':len(history),'selected_epoch':bestepoch,'fit_time_seconds':time.monotonic()-started,
      'early_stopping':'Development joint count/severity NLL, min_delta=1e-5, patience=8, max40; trial choice later uses aggregate primary',
      'deterministic_algorithms':True,'warn_only':True,'mixed_precision':False,'history':history}
    return pred,meta
