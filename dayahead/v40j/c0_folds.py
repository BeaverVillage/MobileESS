"""Existing official model trained on each causal blocked fit date."""
from io import BytesIO
import json
import pickle
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from .contracts import OUT, LEGACY, LEGACY_CACHE, SPLIT, FEATURES9
from .firewall import ReadFirewall, write

def main():
    import dayahead
    dayahead.__path__.append(str(LEGACY/'dayahead'))
    path=LEGACY_CACHE/'kestrel_preissue_normalized.parquet'
    fw=ReadFirewall('c0_folds',[path],[LEGACY/'dayahead']).install()
    try:
        assert json.loads((OUT/'V40J_CURRENT_RUNTIME_BASELINE.json').read_text())['status']=='PASS'
        from dayahead.v35r3d.runtime import exact_model
        frame=pq.read_table(BytesIO(path.read_bytes())).to_pandas()
        gpu=pq.read_table(BytesIO((OUT/'DEVELOPMENT_GPU_ROWS.parquet').read_bytes())).to_pandas()
        (OUT/'models').mkdir(exist_ok=True)
        for fold in SPLIT['folds']:
            name=fold['id']
            when=pd.Timestamp(fold['fit_before'],tz='UTC')
            mask=(frame.end_time<when)&(frame.end_time>=when-pd.Timedelta(days=120))&(frame.submit_time<when)&frame.runtime_seconds.notna()
            train=frame.loc[mask].to_dict('records')
            query=gpu.loc[(gpu.submit_time>=pd.Timestamp(fold['calibration'][0],tz='UTC'))&(gpu.submit_time<pd.Timestamp(fold['validation'][1],tz='UTC'))]
            rows=query[FEATURES9+['job_id']].to_dict('records')
            print(name,'official baseline fit rows',len(train),'query',len(rows),flush=True)
            model=exact_model()
            artifacts=model._build_daily_preprocessing_artifacts(train)
            x=model._transform_rows(train,artifacts)
            xq=model._transform_rows(rows,artifacts)
            class FitTime:
                split_epoch=int(when.timestamp())
            state,pred=model._fit_predict(x,np.array([r['runtime_seconds'] for r in train]),xq,
                train_rows=train,test_rows=rows,artifacts=artifacts,sample_weight=model._time_decay_weights(train,FitTime()))
            result=query[['job_id']].copy()
            result['point']=pred
            result.to_parquet(OUT/f'C0_{name}.parquet',index=False)
            with (OUT/'models'/f'C0_{name}.pkl').open('wb') as f: pickle.dump((state,artifacts),f,protocol=5)
            write(f'C0_{name}_FIT.json',{'train_rows':len(train),'query_rows':len(rows),'end_known_before':str(when),
                'input_features':FEATURES9,'model':'exact pinned existing HPC-ODA recipe','no_final_status_query':True})
            del train,model,state,x,xq,artifacts
    finally: fw.close()

if __name__=='__main__': main()
