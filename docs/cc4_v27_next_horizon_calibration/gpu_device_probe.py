"""Identify the installed backend's default GPU; excluded from timed benchmark."""
from common import *
import lightgbm as lgb
arm='T2_F0';i=int(np.searchsorted(c.DAYS,'2024-09-15'));x=np.load(PREV/'FEATURES.npz')[arm];z=np.load(PREV/'TARGETS.npz');y=z['T2'];mature=pd.Series(pd.to_datetime(z['maturity_T2'].max(1),utc=True));tr=c.member(i,mature)
params={**c.PARAMS,'device_type':'gpu','gpu_use_dp':True,'verbosity':1}
print('Untimed device identification, same first benchmark M0 task and Q90; only verbosity differs.',flush=True)
lgb.LGBMRegressor(objective='quantile',alpha=.9,**params).fit(x[tr].reshape(-1,x.shape[-1]),np.log1p(y[tr].ravel()),sample_weight=np.repeat(c.weights(tr,i),24))
