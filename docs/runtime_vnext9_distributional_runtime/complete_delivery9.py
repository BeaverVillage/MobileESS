"""Final evidence completeness and byte-preservation checks, without model changes."""
from common9 import *
from evaluate_april9 import assert_freeze
import pandas as pd,numpy as np
v8path()
import metrics8
def main():
    assert_freeze()
    f=pd.read_parquet(V8/'APRIL_JOBS.parquet');pred=pd.read_parquet(ROOT/'APRIL_PREDICTIONS.parquet');m=f.label_valid.to_numpy();g=f[m]
    predictions={a:pred.loc[m,[a+'_Q50',a+'_Q90']].to_numpy() for a in ['B0','Bconst','V8','V9']}
    predictions['W0']=np.tile(g.requested_seconds.to_numpy()[:,None],(1,2))
    rows,strata=metrics8.compare(g,predictions,'APRIL_EXPOSED_REGRESSION')
    full=pd.DataFrame(rows);full.to_csv(ROOT/'APRIL_PREVIOUS_SCHEMA_REPRODUCTION.csv',index=False)
    pd.DataFrame(strata).to_csv(ROOT/'APRIL_PREVIOUS_SCHEMA_STRATA.csv',index=False)
    old=pd.read_csv(V8/'APRIL_LOCKED_RUNTIME_METRICS.csv').set_index('model');new=full.set_index('model');errors=[]
    for arm in ['W0','B0','Bconst','V8']:
        for col in old.select_dtypes(include='number').columns:
            error=abs(float(old.loc[arm,col])-float(new.loc[arm,col]));assert error<1e-7,(arm,col,error);errors.append(error)
    mainframe=pd.read_csv(ROOT/'APRIL_EXPOSED_RUNTIME_METRICS.csv')
    extra=[c for c in full.columns if c not in mainframe.columns and c not in ['model','role']]
    mainframe=mainframe.merge(full[['model']+extra],left_on='arm',right_on='model',validate='one_to_one').drop(columns='model')
    mainframe.to_csv(ROOT/'APRIL_EXPOSED_RUNTIME_METRICS.csv',index=False)
    pd.DataFrame(metrics8.uncertainty(g,predictions['V9'],predictions['B0'],'APRIL_EXPOSED_REGRESSION')).to_csv(ROOT/'APRIL_PAIRED_UNCERTAINTY.csv',index=False)
    proper=pd.read_csv(ROOT/'POOLED_PROPER_DISTRIBUTION_SCORES.csv');selected=read(ROOT/'PREAPRIL_SELECTION_RESULT.json')['selected']['arm']
    alias=proper[proper.arm.eq(selected)].copy();alias['arm']='V9_SELECTED'
    pd.read_csv(ROOT/'MODEL_COMPARISON.csv').merge(pd.concat([proper,alias]),on='arm',how='left').to_csv(ROOT/'MODEL_COMPARISON_WITH_PROPER_SCORES.csv',index=False)
    report=ROOT/'FINAL_REVIEW_KO.md';text=report.read_text(encoding='utf-8').replace('| nan |','| N/A |')
    text=text.replace('## 사전 계약 및 비교 요약\n','## 사전 계약 및 비교 요약\n\n오차·pinball·학습시간 단위는 초, inference latency는 밀리초다. Proper score를 병합한 전체 CSV는 MODEL_COMPARISON_WITH_PROPER_SCORES.csv다.\n')
    text=text.replace('CPU4 학습/CPU1 추론 bundle을 제공한다. GPU 실제 실행명은 BENCHMARK_GPU.log에서 검증한다. INFERENCE_LATENCY.json은1/10/100/1000건 측정이다.',
        'GPU가 학습23.67초로 CPU4의45.68초, CPU1의143.05초보다 빨랐다. 실제 RTX4060 Laptop 실행을 로그로 확인했다. 다만 pre-April1000건 분위수 최대 차이는347.18초였고 CPU1/4끼리는0이었다. 동결 CPU4 학습/CPU1 추론 bundle을 유지한다. 이후 연구 학습 가속에는 GPU가 유리하지만 이 CPU 모델과 같은 예측값을 보장하지 않는다. CPU 추론 median은1/10/100/1000건에서21.72/33.54/163.60/1410.45ms다.')
    text=text.replace('High-GPU N<100은 INSUFFICIENT_SUPPORT로 보고한다.','High-GPU N<100은 INSUFFICIENT_SUPPORT로 보고한다. April V9의 GPU≥16은 N298, coverage79.19%로 FAIL이고 GPU≥64는 N53으로 INSUFFICIENT_SUPPORT다.')
    text=text.replace('→ evaluate9.py → finalize_model9.py','→ evaluate9.py → audit_proper_score9.py → finalize_model9.py')
    text=text.replace('→ queue_april9.py → report9.py.','→ queue_april9.py → verify_provider_external9.py → report9.py → complete_delivery9.py. 실패한 checkpoint datetime 연산만 resume_april_diagnostics9.py로 재개했으며 예측값 변화0과 provider byte 불변을 확인했다.')
    report.write_text(text,encoding='utf-8')
    for folder in [V6,V7,V8]:
        for r in read(folder/'DELIVERY_MANIFEST.json')['files']:assert sha(folder/r['relative'])==r['sha256']
    assert_freeze();verdict=read(ROOT/'FINAL_VERDICT.json');assert verdict['V42_RESEARCH_RUNTIME_PROVIDER_READY'] is False and verdict['STRICT_CAUSAL_RUNTIME_PROVIDER_READY'] is False and verdict['MAY_PAYLOAD_OPENED'] is False
    validation=read(ROOT/'DELIVERY_VALIDATION.json');validation.update(final_time=now(),previous_April_schema_comparisons=len(errors),previous_April_schema_max_error=max(errors),standalone_provider_PASS=read(ROOT/'STANDALONE_PROVIDER_VALIDATION.json')['PASS'],all_freezes_unchanged=True,model_selection_unchanged=True)
    (ROOT/'DELIVERY_VALIDATION.json').write_text(json.dumps(validation,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    files=[dict(relative=str(p.relative_to(ROOT)).replace('\\','/'),bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(ROOT.rglob('*')) if p.is_file() and '.local' not in p.parts and '__pycache__' not in p.parts and p.name not in ['DELIVERY_MANIFEST.json','report9.log','pipeline9.log']]
    manifest=dict(base=BASE,scope='docs/runtime_vnext9_distributional_runtime only',files=files)
    (ROOT/'DELIVERY_MANIFEST.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    for r in files:assert sha(ROOT/r['relative'])==r['sha256']
    print('DELIVERY_VERIFIED',len(files),'files; baseline metric comparisons',len(errors),'max error',max(errors),flush=True)
if __name__=='__main__':main()
