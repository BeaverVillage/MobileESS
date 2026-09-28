"""Limited strict candidates, frozen selection, then one identical-membership final refit."""
from paths import *
import os
for k in ['OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS']:os.environ[k]='1'
import numpy as np,pandas as pd,lightgbm as lgb
from benchmark import fit_task
from metrics import compare,gate,uncertainty,stats
from datetime import datetime,timezone

def main():
    assert not (ROOT/'MODEL_SELECTION_FREEZE.json').exists()
    protocol=read(ROOT/'EXPERIMENT_PROTOCOL.json');backend=read(ROOT/'TRAIN_BACKEND_SELECTION.json')
    f=pd.read_parquet(ROOT/'PREAPRIL_JOBS.parquet');tr=f[f.role.eq('TRAIN')]
    assert tr.end_time.lt(pd.Timestamp(protocol['TRAIN']['end_before'])).all()
    y=tr.runtime_seconds.to_numpy();models={};raw={}
    for family in ['M1','M2']:
        result=[fit_task((family,t,y,'cpu',protocol['lgbm'])) for t in [.5,.9]]
        models[family]=result;raw[family]=np.maximum.accumulate(np.maximum([r['prediction'] for r in result],0))
        d=ROOT/'DEVELOPMENT_MODELS'/family;d.mkdir(parents=True)
        for r in result:(d/f'Q{int(r["tau"]*100)}.txt').write_text(r['model'],encoding='utf-8')
    b=pd.read_parquet(ROOT/'PREAPRIL_B0_PREDICTIONS.parquet');data={};pred={}
    for role in ['DEV','CAL_FIT','CAL_VALID']:
        g=f[f.role.eq(role)&f.label_valid&f.end_time.lt(pd.Timestamp(protocol[role]['mature_before']))].merge(b,on='job_id',validate='one_to_one')
        data[role]=g
        pred[role]={'W0':np.column_stack([g.requested_seconds]*2),'B0_RESEARCH':g[['B0_Q50','B0_Q90']].to_numpy(),**{k:np.tile(v,(len(g),1)) for k,v in raw.items()}}
    scores={k:stats(data['DEV'],pred['DEV'][k][:,0],pred['DEV'][k][:,1])['Q90_pinball'] for k in raw}
    selected='M1' if scores['M1']<=scores['M2']+1e-6 else 'M2'
    cf=data['CAL_FIT'];res=cf.runtime_seconds.to_numpy()-raw[selected][1];rank=int(np.ceil(.9*(len(res)+1)));delta=float(np.sort(res)[rank-1])
    calibrated=np.maximum.accumulate(np.maximum([raw[selected][0],raw[selected][1]+delta],0))
    rows=[];groups=[];cis=[];gates={}
    for role,g in data.items():
        pred[role]['SELECTED_CALIBRATED']=np.tile(calibrated,(len(g),1))
        r,s=compare(g,pred[role],role);rows+=r;groups+=s
        for ref in ['W0','B0_RESEARCH']:cis+=uncertainty(g,pred[role]['SELECTED_CALIBRATED'],pred[role][ref],role,'SELECTED - '+ref)
        use=pred[role][selected] if role=='DEV' else pred[role]['SELECTED_CALIBRATED']
        gates[role]=gate(g,use,[pred[role]['W0'],pred[role]['B0_RESEARCH']])
    pd.DataFrame(rows).to_csv(ROOT/'MODEL_COMPARISON.csv',index=False);pd.DataFrame(groups).to_csv(ROOT/'STRATIFIED_METRICS.csv',index=False)
    pd.DataFrame(rows)[['role','model','N','GPU_coverage','GPU_underprediction_rate','reservation_GPUh','actual_GPUh','reservation_to_actual_GPUh','overrun_GPUh','excess_reservation_GPUh']].to_csv(ROOT/'GPU_WEIGHTED_METRICS.csv',index=False)
    pd.DataFrame(cis).to_csv(ROOT/'PAIRED_UNCERTAINTY.csv',index=False)
    freeze=dict(time=datetime.now(timezone.utc).isoformat(),selected_family=selected,selected_scope='STRICT_FEATURELESS_RESEARCH_CANDIDATE',
      production_promoted=False,optimizer_use_allowed=False,raw_quantiles=raw[selected].tolist(),calibrated_quantiles=calibrated.tolist(),calibration_delta_seconds=delta,
      quantile=.9,calibration_rank=rank,calibration_N=len(res),DEV_raw_scores=scores,gates=gates,development_calibration_gate_pass=gates['DEV']['PASS'] and gates['CAL_VALID']['PASS'],
      backend=backend['selected'],membership=read(ROOT/'DATA_SPLIT_AND_MATURITY.json')['roles'],feature_contract=record(ROOT/'FEATURE_CONTRACT.json'),protocol=record(ROOT/'EXPERIMENT_PROTOCOL.json'),
      sources=[record(ROOT/p) for p in ['develop.py','benchmark.py','metrics.py','prepare_strict.py']],april_opened=False,may_used=False,
      final_refit_plan='Same TRAIN membership, uniform weights, same params, CPU; require identical predictions. Two quantile boosters = one package.',
      training_source_scope='September2024 through March2025 archive partitions; TRAIN also end-window Sept15..Mar14; no claim earlier-submit long jobs exhaustively included.')
    write('MODEL_SELECTION_FREEZE.json',freeze)
    bundle=ROOT/'RUNTIME_PROVIDER';bundle.mkdir()
    refit=[]
    for tau in [.5,.9]:
        r=fit_task((selected,tau,y,'cpu',protocol['lgbm']));refit.append(r)
        assert abs(r['prediction']-raw[selected][int(tau>.5)])<1e-9
        (bundle/f'Q{int(tau*100)}.txt').write_text(r['model'],encoding='utf-8')
    write('FINAL_REFIT_RECEIPT.json',dict(fit_count=2,one_fit_each_quantile=True,training_N=len(y),no_DEV_CAL_absorption=True,max_prediction_difference=0.,after_selection_freeze=record(ROOT/'MODEL_SELECTION_FREEZE.json'),fits=[{k:v for k,v in r.items() if k!='model'} for r in refit]))
    write('RUNTIME_PROVIDER/preprocessing.json',dict(feature_order=['constant_bias'],types=['float64'],constant=1.,job_feature_count=0,categorical_mappings={},missing_rules='No job feature consumed; event_time must be timezone-aware ISO timestamp.'))
    write('RUNTIME_PROVIDER/feature_contract.json',read(ROOT/'FEATURE_CONTRACT.json'))
    write('RUNTIME_PROVIDER/runtime_contract.json',dict(model_version='runtime-vnext6-strict-constant-v1',unit='seconds',target=protocol['target'],family=selected,
      inverse_transform='expm1' if selected=='M2' else 'identity',Q90_signed_calibration_delta_seconds=delta,quantiles=[.5,.9],planned='Q90',walltime_cap=False,
      Q90_semantics='Unconditional frozen total execution runtime quantile, global residual adjustment. No claim of conditional calibration for a particular job.',
      remaining='max(Q90-elapsed,0) fixed submit-time residual, NOT Q90(T-elapsed | T>elapsed,x)',
      overrun='While still running and elapsed>=planned: STAY, retain GPU, extend current reservation one interval; never inspect future end.',
      optimizer_use_allowed=False,production_promoted=False,strict_feature_availability=True,informative_job_features=0))
    write('RUNTIME_PROVIDER/source_manifest.json',dict(raw=read(ROOT/'DATA_SPLIT_AND_MATURITY.json')['source'],request_authority=record(ROOT/'REQUEST_VERSION_AUTHORITY_AUDIT.json'),
      selection_freeze=record(ROOT/'MODEL_SELECTION_FREEZE.json'),code=[record(ROOT/p) for p in ['develop.py','benchmark.py','metrics.py']],baseline_reproduction=record(ROOT/'B0_FROZEN_BASELINE_REPRODUCTION.json')))
    write('RUNTIME_PROVIDER/model_manifest.json',dict(training_cutoff=protocol['TRAIN']['end_before'],logical_freeze_cutoff=protocol['logical_freeze_cutoff'],membership=freeze['membership'],hyperparameters=protocol['lgbm'],
      seed=4005,backend=backend['selected'],software=backend['versions'],target=protocol['target'],unit='seconds',
      files=[dict(relative=p.name,sha256=sha(p),bytes=p.stat().st_size) for p in bundle.iterdir() if p.is_file()]))
    print('SELECTED',selected,'QUANTILES',calibrated,'DEV_GATE',gates['DEV']['PASS'],'CAL_GATE',gates['CAL_VALID']['PASS'],flush=True)
if __name__=='__main__':main()
