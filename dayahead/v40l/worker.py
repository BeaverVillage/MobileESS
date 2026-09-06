"""Use existing isolated environments; never refit frozen K0 or K4."""
import sys
import pickle
import numpy as np
from .common import *
from .data import frame

def main():
    kind,stage=sys.argv[1:3];require_prereg();verify_k0()
    with Firewall('worker_'+kind+'_'+stage):
        f=frame(OUT/(stage.upper()+'_ROWS.parquet'))
        if kind=='K0':
            import dayahead
            dayahead.__path__.append(str(LEGACY/'dayahead'))
            from dayahead.v35r3d.runtime import exact_model,_predict_state
            if stage=='oof':
                for fold,g in f.groupby('C0_source'):
                    st,ar=pickle.loads((J/'models'/('C0_'+fold+'.pkl')).read_bytes())
                    q=_predict_state(exact_model(),st,ar,g[F9+['job_id']].to_dict('records'))
                    assert q.tobytes()==g.point.to_numpy(float).tobytes(),'OOF_PREDICTION_CHANGED'
                write('V40L_OOF_PREDICTION_REPRODUCTION.json',{'status':'PASS','rows':len(f),'max_difference_seconds':0.,'refits':0,'all_folds_byte_identical':True})
                print('OOF_REPRODUCTION',len(f),'PASS',flush=True)
                return
            state,art=pickle.loads((K/'models/K0_FINAL.pkl').read_bytes())
            p=_predict_state(exact_model(),state,art,f[F9+['job_id']].to_dict('records'))
            result=f[['job_id']].copy();result['K0']=p
            if stage=='visible_development':assert p.tobytes()==f.K0.to_numpy(float).tobytes(),'K0_PREDICTION_CHANGED'
            result.to_parquet(OUT/(stage.upper()+'_K0.parquet'),index=False)
            write('K0_VERIFY_'+stage+'.json',{'status':'PASS','rows':len(f),'model_SHA':sha(K/'models/K0_FINAL.pkl'),'CPU_only':True,'refits':0,'visible_prediction_byte_identical':True if stage=='visible_development' else None})
        elif kind=='T6':
            from dayahead.v40k.models import features
            path=K/'models/FINAL_K4_INTERVAL_HAZARD.pkl'
            receipt=load(K/'V40K_FINAL_COMMIT_RECEIPT.json')
            assert sha(path)==receipt['committed_V40K_file_SHA256'][path.relative_to(ROOT).as_posix()]
            m=pickle.loads(path.read_bytes());x=features(f)
            p=np.column_stack([m.predict(x,alpha=a) for a in [.9,.95]])
            again=np.column_stack([m.predict(x,alpha=a) for a in [.9,.95]])
            assert p.tobytes()==again.tobytes() and (p[:,1]>=p[:,0]).all()
            result=f[['job_id']].copy();result['Q90']=p[:,0];result['Q95']=p[:,1]
            result.to_parquet(OUT/(stage.upper()+'_T6.parquet'),index=False)
            write('T6_VERIFY_'+stage+'.json',{'status':'PASS','model_SHA':sha(path),'rows':len(f),'CPU_only':True,'repeat_byte_identical':True,'refits':0,'Q95_ge_Q90':True})
        else:raise ValueError(kind)
        print(kind,stage,len(f),'PASS',flush=True)
if __name__=='__main__':main()
