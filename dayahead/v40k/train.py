import pickle
import numpy as np
from .common import *
from .data import frame,train_mask,block_mask,residual_oof,utc
from .models import Central,features,stacking_fit
from .protocol import SPLIT,IDS,STACK

def fit_one(cid,train,oof,when):
    f=oof.loc[train_mask(oof,when)] if cid.startswith('K1_') else train
    x=features(f);kw={'early':((f.runtime_seconds<=300)|f.job_state.eq('FAILED')).to_numpy(),
      'times':f.submit_time,'end_times':f.end_time,'fit_before':when}
    if cid.startswith('K1_'):kw.update(c0=f.point.to_numpy(),c0_fit_times=f.C0_fit_before,submit_times=f.submit_time)
    return Central(cid).fit(x,f.runtime_seconds,**kw)

def main():
    require_prereg()
    with Firewall('central_training'):
        assert (OUT/'V40K_POINT_SWING_ROOT_CAUSE.json').exists()
        f=frame(J/'DEVELOPMENT_GPU_ROWS.parquet');oof=residual_oof(f)
        oof.to_parquet(OUT/'RESIDUAL_OOF_ROWS.parquet',index=False)
        write('V40K_RESIDUAL_CROSSFIT_PROVENANCE.json',{'rows':len(oof),'row_ids_unique':True,'self_fit_overlap':0,
          'sources':{k:int(v) for k,v in oof.C0_source.value_counts().items()},'max_training_time_before_each_query':True,
          'further_filter':'end_time strictly before each correction fit timestamp','rows_SHA':sha(OUT/'RESIDUAL_OOF_ROWS.parquet')})
        (OUT/'models').mkdir(exist_ok=True)
        records=read('V40K_TRAINING_DETERMINISM.json') if (OUT/'V40K_TRAINING_DETERMINISM.json').exists() else []
        inner=[];unavailable={}
        stages=SPLIT['inner_folds']+[{'id':'FINAL','fit_before':SPLIT['final_point_fit_before']}]
        for stage in stages:
            sid=stage['id'];when=stage['fit_before'];train=f.loc[train_mask(f,when)]
            if sid!='FINAL':
                val=f.loc[block_mask(f,stage['validation'],SPLIT['development_label_deadline'])].copy()
                bp=frame(J/'C0_F3.parquet');val=val.merge(bp,on='job_id',validate='one_to_one');base=val.point.to_numpy()
            else:
                val=f.loc[train_mask(f,when)].tail(1024).copy();base=np.zeros(len(val))
            x=features(val);preds={'K0':base}
            for cid in IDS[1:-1]:
                model_path=OUT/'models'/f'{sid}_{cid}.pkl'
                previous=[r for r in records if r['stage']==sid and r['candidate']==cid and r['status']=='PASS']
                if previous and model_path.exists() and sha(model_path)==previous[-1]['model_SHA']:
                    m=pickle.loads(model_path.read_bytes())
                    assert all(model.get_params().get('device_type','cpu')=='cpu' for model in m.models)
                    preds[cid]=m.predict(x,c0=base)
                    print('RESUME_VERIFIED_CPU_MODEL',sid,cid,flush=True)
                    continue
                print('TRAIN',sid,cid,'rows',len(train),flush=True)
                try:
                    m=fit_one(cid,train,oof,when);p=m.predict(x,c0=base)
                    m2=fit_one(cid,train,oof,when);p2=m2.predict(x,c0=base)
                except ValueError as e:
                    if str(e)!='CDF_COMPONENT_SUPPORT_UNAVAILABLE':raise
                    unavailable[cid]=str(e);records.append({'stage':sid,'candidate':cid,'status':'NOT_EVALUATED_COMPONENT_SUPPORT_UNAVAILABLE'});continue
                assert p.tobytes()==p2.tobytes(),'NONDETERMINISTIC:'+sid+cid
                if cid=='K4_INTERVAL_HAZARD':assert (m.predict(x,alpha=.9)>=p).all()
                model_path.write_bytes(pickle.dumps(m,protocol=5))
                preds[cid]=p
                records.append({'stage':sid,'candidate':cid,'status':'PASS','train_rows':m.training_rows,
                  'max_training_end':str(train.end_time.max()),'fit_before':when,'same_seed_independent_refit':True,
                  'prediction_bytes_identical':True,'model_SHA':sha(model_path),
                  'CDF_population':getattr(m,'CDF_population',None),'hazard_expanded_rows':getattr(m,'expanded_rows',None)})
                write('V40K_TRAINING_DETERMINISM.json',records)
            if sid!='FINAL':
                v=val[['job_id','runtime_seconds','submit_time']].copy()
                for cid,p in preds.items():v[cid]=p
                v['fold']=sid;inner.append(v)
        import pandas as pd
        inn=pd.concat(inner,ignore_index=True);assert not inn.job_id.duplicated().any()
        columns=[c for c in STACK if c not in unavailable]
        weights=stacking_fit(inn[columns],inn.runtime_seconds);again=stacking_fit(inn[columns],inn.runtime_seconds)
        assert weights.tobytes()==again.tobytes(),'STACK_NONDETERMINISTIC'
        write('V40K_STACKING_WEIGHTS.json',{'base_ids':columns,'weights':weights.tolist(),'sum':float(weights.sum()),'nonnegative':bool((weights>=0).all()),'fit_rows':len(inn),'fit_scope':'I1/I2 only','independent_repeat_identical':True},immutable=True)
        inn['K5_STACKING']=inn[columns].to_numpy()@weights;inn.to_parquet(OUT/'INNER_OOF_PREDICTIONS.parquet',index=False)
        write('V40K_PREHOLDOUT_MODEL_LOCK.json',{'created_at':now(),'preregistration_commit':require_prereg(),
          'models_SHA':{p.name:sha(p) for p in (OUT/'models').glob('*.pkl')},'weights_SHA':sha(OUT/'V40K_STACKING_WEIGHTS.json'),
          'source_SHA':{p.name:sha(p) for p in (ROOT/'dayahead/v40k').glob('*.py')},'unavailable':unavailable,
          'point_holdout_opened':False,'safe_fit_opened':False,'shadow_opened':False},immutable=True)
        print('ALL_CENTRAL_MODELS_LOCKED',flush=True)
if __name__=='__main__':main()
