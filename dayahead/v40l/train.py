import pickle
import numpy as np
from .common import *
from .protocol import EXCESS_ALPHAS,REGISTRY
from .data import history,oof_authority,Support,frame
from .models import Quantile,signed_target

def worker(kind,stage):
    py=LGB_PY if kind=='T6' else XGB_PY
    r=subprocess.run([str(py),'-B','-m','dayahead.v40l.worker',kind,stage],cwd=ROOT,capture_output=True)
    (OUT/('WORKER_'+kind+'_'+stage+'.log')).write_bytes(r.stdout+r.stderr)
    assert r.returncode==0,('WORKER_FAILED',kind,stage,(r.stdout+r.stderr)[-3000:])

def main():
    require_prereg();verify_k0()
    with Firewall('training'):
        h=history();oof,authority=oof_authority(h)
        assert authority==read('V40L_OOF_RESIDUAL_AUTHORITY.json')
        oof.to_parquet(OUT/'OOF_ROWS.parquet',index=False)
        worker('K0','oof')
        support=Support(h);xo=support.transform(oof);xh=support.transform(h)
        xo.to_parquet(OUT/'OOF_FEATURES.parquet',index=False);xh.to_parquet(OUT/'HISTORICAL_FEATURES.parquet',index=False)
        (OUT/'models').mkdir(exist_ok=True)
        (OUT/'models/SUPPORT.pkl').write_bytes(pickle.dumps(support,protocol=5))
        target=signed_target(oof.runtime_seconds,oof.point,provenance=True)
        positive=target>0
        specifications=[('T1',xo,target,[.9,.95],400,False),('T2',xh,h.runtime_seconds.to_numpy()/3600,[.5,.9,.95],400,False),
          ('T7_GATE',xo,positive.astype(int),[],300,True),('T7_EXCESS',xo.loc[positive],target[positive],EXCESS_ALPHAS,250,False)]
        records=[]
        for cid,x,y,alphas,rounds,binary in specifications:
            print('TRAIN_CPU',cid,'rows',len(y),'alphas',alphas,flush=True)
            m=Quantile(alphas,rounds,binary).fit(x,y);probe=x.iloc[:2048]
            p=m.predict(probe);m2=Quantile(alphas,rounds,binary).fit(x,y);p2=m2.predict(probe)
            assert p.tobytes()==p2.tobytes(),('NONDETERMINISTIC',cid)
            path=OUT/'models'/(cid+'.pkl');path.write_bytes(pickle.dumps(m,protocol=5))
            records.append({'candidate':cid,'rows':len(y),'alphas':alphas,'rounds':rounds,'CPU_only':True,'independent_double_fit':True,'byte_identical':True,'model_SHA':sha(path),'max_abs_prediction_difference':0.})
            write('V40L_TRAINING_DETERMINISM.json',records)
            print('FROZEN_CPU_MODEL',cid,flush=True)
        write('V40L_T1_RESIDUAL_QUANTILE_REPORT.json',{'status':'FITTED_CPU_FROZEN','objective':REGISTRY['T1'],'rows':len(oof),'positive_rows':int(positive.sum()),'nonpositive_rows':int((~positive).sum()),'full_distribution':True,'OOF_authority_SHA':sha(OUT/'V40L_OOF_RESIDUAL_AUTHORITY.json'),'model_SHA':sha(OUT/'models/T1.pkl')})
        write('V40L_T2_DIRECT_QUANTILE_REPORT.json',{'status':'FITTED_CPU_FROZEN','objective':REGISTRY['T2'],'rows':len(h),'max_training_end':str(h.end_time.max()),'model_SHA':sha(OUT/'models/T2.pkl'),'Q50_nominal_replacement':False})
        write('V40L_T7_EXCEEDANCE_REPORT.json',{'status':'FITTED_CPU_FROZEN','objective':REGISTRY['T7'],'gate_rows':len(oof),'positive_excess_rows':int(positive.sum()),'unconditional_CDF_reconstructed':True,'conditional_positive_Q90_not_called_unconditional_Q90':True})
        write('V40L_T6_HAZARD_REPORT.json',{'status':'FROZEN_V40K_SURVIVAL_CURVE_REUSED','source_model_SHA':sha(K/'models/FINAL_K4_INTERVAL_HAZARD.pkl'),'Q90_Q95_only':True,'CPU_only':True,'V40L_refits':0,'censored_rows':0,
          'formula':'S_j=product_{k<=j}(1-h_k); finite-interval CDF linear interpolation; beyond final edge t=last_edge+tail_scale*log(S_last/(1-alpha)). Clamp Q90>=K0 and Q95>=Q90.'})
        dev=frame(K/'POINT_HOLDOUT_PREDICTIONS.parquet');dev.to_parquet(OUT/'VISIBLE_DEVELOPMENT_ROWS.parquet',index=False)
        worker('K0','visible_development');worker('T6','visible_development')
        event('ML_training_complete',models=4,independent_double_fits=4,calibration_opened=False)
        print('ALL_ML_MODELS_FROZEN_CPU',flush=True)
if __name__=='__main__':main()
