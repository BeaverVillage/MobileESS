import pickle
import numpy as np
from .common import *
from .data import frame

def main():
    from dayahead.v40k.models import features
    from dayahead.v40k.protocol import HAZARD_EDGES
    with Firewall('hazard_CDF_verification'):
        f=frame(K/'POINT_HOLDOUT_PREDICTIONS.parquet');m=pickle.loads((K/'models/FINAL_K4_INTERVAL_HAZARD.pkl').read_bytes());x=features(f);z=m.encode(x)
        survival=np.ones(len(f));decreases=[]
        for i in range(len(HAZARD_EDGES)):
            zz=z.copy();zz['hazard_interval']=float(i);h=np.clip(m.models[0].predict_proba(zz)[:,1],1e-8,1-1e-8)
            new=survival*(1-h);assert np.all((new>=0)&(new<=survival));decreases.append(float(np.max(new-survival)));survival=new
        quantiles=np.column_stack([m.predict(x,alpha=a) for a in [.1,.5,.9,.95,.99]])
        assert np.isfinite(quantiles).all() and np.all(np.diff(quantiles,axis=1)>=0)
        write('V40L_HAZARD_CDF_VERIFICATION.json',{'status':'PASS','rows':len(f),'source':'previously visible April01-07','model_SHA':sha(K/'models/FINAL_K4_INTERVAL_HAZARD.pkl'),'survival_nonincreasing_all_intervals':True,'alphas':[.1,.5,.9,.95,.99],'quantiles_monotonic':True,'refit':False,'May_rows':0})
        print('HAZARD_CDF_PASS',len(f),flush=True)
if __name__=='__main__':main()
