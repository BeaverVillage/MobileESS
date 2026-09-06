"""Pinned baseline operations run only in the existing XGBoost environment."""
import argparse
import pickle
import numpy as np
import pandas as pd
from .common import *
from .data import frame,utc,normalize,authorize

def main():
    parser=argparse.ArgumentParser();parser.add_argument('action');a=parser.parse_args()
    import dayahead
    dayahead.__path__.append(str(LEGACY/'dayahead'))
    from dayahead.v35r3d.runtime import exact_model,_predict_state
    require_prereg()
    rawcache=CACHE.with_name('kestrel_preissue_raw.parquet')
    with Firewall('baseline_'+a.action,files=[CACHE,rawcache],roots=[LEGACY/'dayahead']):
        if a.action=='fit':
            # Verify exact old state reproduction on recorded out-of-fit rows, not May outputs.
            gpu=frame(J/'DEVELOPMENT_GPU_ROWS.parquet');old=frame(J/'C0_F3.parquet')
            query=gpu.merge(old,on='job_id',validate='one_to_one');state,art=pickle.loads((J/'models/C0_F3.pkl').read_bytes())
            m=exact_model();pred=_predict_state(m,state,art,query[FEATURES9+['job_id']].to_dict('records'))
            assert pred.tobytes()==query.point.to_numpy(dtype=float).tobytes(),'BASELINE_REPRODUCTION_FAILED'
            data=frame(CACHE);when=utc('2025-04-01')
            tr=data.loc[(data.end_time<when)&(data.end_time>=when-pd.Timedelta(days=120))&(data.submit_time<when)&data.runtime_seconds.notna()]
            rows=tr.to_dict('records');probe=gpu[FEATURES9+['job_id']].iloc[-1000:].to_dict('records')
            artifacts=m._build_daily_preprocessing_artifacts(rows);x=m._transform_rows(rows,artifacts);xq=m._transform_rows(probe,artifacts)
            class Time:split_epoch=int(when.timestamp())
            weights=m._time_decay_weights(rows,Time())
            print('K0 final fit',len(rows),'independent double fit',flush=True)
            s1,p1=m._fit_predict(x,tr.runtime_seconds.to_numpy(),xq,train_rows=rows,test_rows=probe,artifacts=artifacts,sample_weight=weights)
            s2,p2=m._fit_predict(x,tr.runtime_seconds.to_numpy(),xq,train_rows=rows,test_rows=probe,artifacts=artifacts,sample_weight=weights)
            assert p1.tobytes()==p2.tobytes(),'K0_NONDETERMINISTIC'
            (OUT/'models').mkdir(exist_ok=True);path=OUT/'models/K0_FINAL.pkl';path.write_bytes(pickle.dumps((s1,artifacts),protocol=5))
            write('V40K_BASELINE_REPRODUCTION.json',{'status':'PASS','existing_F3_rows':len(query),'max_difference_seconds':0.,'byte_identical':True,
              'final_fit_rows':len(rows),'end_known_before':str(when),'latest_training_end':str(tr.end_time.max()),
              'same_seed_independent_refit':True,'final_model_SHA':sha(path),'current_q_unchanged':Q,'input_SHA':sha(CACHE)})
            # Exact causal mapping validation against legacy raw/normalized authority on exposed pre-May data.
            raw=frame(rawcache);raw=raw.loc[raw.gpus_requested.gt(0)].head(5000)
            normal=normalize(raw);pair=normal.merge(data,on='job_id',suffixes=('_new','_old'),validate='one_to_one')
            checks={}
            for c in FEATURES9+['runtime_seconds','submit_time','start_time','end_time','job_state']:
                p,q=pair[c+'_new'],pair[c+'_old']
                if c in FEATURES9[:5]+['runtime_seconds']:ok=np.allclose(p.astype(float),q.astype(float),equal_nan=True,rtol=0,atol=0)
                else:ok=((p==q)|(p.isna()&q.isna())).all()
                checks[c]=bool(ok)
            assert all(checks.values()),('NORMALIZATION_NOT_EQUIVALENT',checks)
            write('V40K_FEATURE_TARGET_EQUIVALENCE.json',{'status':'PASS','paired_rows':len(pair),'exact_checks':checks,'legacy_raw_SHA':sha(rawcache),'new_source_SHA':sha(ROOT/'dayahead/v40k/data.py')})
            print('BASELINE_AND_MAPPING_PASS',flush=True)
        else:
            authorize(a.action)
            f=frame(OUT/(a.action.upper()+'_ROWS.parquet'))
            state,art=pickle.loads((OUT/'models/K0_FINAL.pkl').read_bytes());m=exact_model()
            p=_predict_state(m,state,art,f[FEATURES9+['job_id']].to_dict('records'))
            d=f[['job_id']].copy();d['K0']=p;d.to_parquet(OUT/(a.action+'_C0.parquet'),index=False)
            print('K0_PREDICTED',a.action,len(d),flush=True)
if __name__=='__main__':main()
