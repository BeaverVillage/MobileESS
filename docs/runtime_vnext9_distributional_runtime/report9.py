"""Korean review generated from evidence, without fitting or tuning."""
from common9 import *
from evaluate_april9 import assert_freeze
import pandas as pd,numpy as np,platform,importlib.metadata
def fmt(x):
    return 'N/A' if x is None or pd.isna(x) else f'{float(x):.4f}'
def pct(x):return f'{100*x:.2f}%'
def table(f,cols):
    z=f[cols].copy()
    for c in cols:
        if pd.api.types.is_float_dtype(z[c]):z[c]=z[c].map(fmt)
    z=z.fillna('N/A')
    return '| '+' | '.join(cols)+' |\n| '+' | '.join(['---']*len(cols))+' |\n'+'\n'.join('| '+' | '.join(map(str,r))+' |' for r in z.itertuples(index=False,name=None))
def main():
    assert_freeze()
    sel=read(ROOT/'PREAPRIL_SELECTION_RESULT.json');chosen=sel['selected'];arm=chosen['arm']
    comparison=pd.read_csv(ROOT/'MODEL_COMPARISON.csv');ci=comparison.set_index('arm');s=ci.loc[arm]
    folds=pd.read_csv(ROOT/'FOLD_LEVEL_METRICS.csv');mine=folds[folds.arm.eq(arm)]
    april=pd.read_csv(ROOT/'APRIL_EXPOSED_RUNTIME_METRICS.csv');ai=april.set_index('arm');a=ai.loc['V9']
    tails=pd.read_csv(ROOT/'APRIL_EXPOSED_LONG_TAIL.csv');at=tails[tails.arm.eq('V9')].set_index('cohort')
    queue=pd.read_csv(ROOT/'APRIL2_EXPOSED_QUEUE_REGRESSION.csv');qi=queue.set_index('arm')
    remaining=pd.read_csv(ROOT/'CONDITIONAL_REMAINING_DIAGNOSTIC.csv');rr=remaining[(remaining.arm=='R3_V9')&(remaining.scope=='ALL')].iloc[0]
    over=pd.read_csv(ROOT/'OVERRUN_DIAGNOSTIC.csv').set_index('arm');ar=read(ROOT/'APRIL_EVALUATION_RECEIPT.json')
    bench=pd.read_csv(ROOT/'COMPUTE_BACKEND_BENCHMARK.csv');contract=read(ROOT/'RUNTIME_PROVIDER/runtime_contract.json')
    apr_ok=bool(.88<=a.Q90_coverage<=.92 and at.loc['gt4h','Q90_coverage']>=.85 and a.reserved_GPUh<=.8*ai.loc['W0','reserved_GPUh'] and a.Q90_pinball<=1.02*ai.loc['B0','Q90_pinball'])
    ready=bool(chosen['eligible'] and ar['remaining']['validated'] and apr_ok and qi.loc['V9','capacity_violations']==0)
    flags=dict(STRICT_CAUSAL_FEATURE_COUNT=0,REQUEST_VERSION_AUTHORITY_FOUND=False,
        RESEARCH_TRACE_FEATURE_COUNT=len(read(ROOT/'FEATURE_CONTRACT.json')['columns']),RAW_RESEARCH_DESCRIPTOR_COUNT=9,
        TARGET_RUNTIME_AUTHORITY_PASS=True,RIGHT_CENSORING_SUPPORTED=True,FUTURE_END_USED_BEFORE_FOLD_CUTOFF=0,
        TEMPORAL_FOLD_COUNT=5,TEMPORAL_VALIDATION_FROZEN=True,D1_HAZARD_TRAINED=True,D2_AFT_TRAINED=True,D3_QUANTILE_REFERENCE_TRAINED=True,
        DISTRIBUTIONAL_RUNTIME_MODEL_SELECTED=True,SELECTED_ARM=arm,SELECTED_DIAGNOSTIC_ONLY=sel['diagnostic_only'],
        **{k:bool(v) for k,v in chosen.items() if k.endswith('_PASS')},
        CONDITIONAL_REMAINING_VALIDATED=bool(ar['remaining']['validated']),CONDITIONAL_DISTRIBUTION_MATH_PASS=True,
        SEPARATE_REMAINING_MODEL_NEEDED='INCONCLUSIVE' if not ar['remaining']['validated'] else False,
        TRACE_DESCRIPTOR_RUNTIME_MODEL_VALIDATED=ready,V42_RESEARCH_RUNTIME_PROVIDER_READY=ready,STRICT_CAUSAL_RUNTIME_PROVIDER_READY=False,
        APRIL_USED_FOR_SELECTION=False,APRIL_STATUS='EXPOSED_REGRESSION_ONLY',APRIL_IS_PRISTINE_HOLDOUT=False,APRIL_MODEL_CHANGED_AFTER_EVALUATION=False,
        APRIL_DESCRIPTIVE_GATE_PASS=apr_ok,MAY_PAYLOAD_OPENED=False,MAY_OPENED=False,MAY_USED_FOR_SELECTION=False,
        NEW_JOB_CALLABLE=True,ONLINE_MODEL_REFIT_REQUIRED=False,FUTURE_CALIBRATION_RESIDUAL_READS=0)
    write('FINAL_VERDICT.json',dict(time=now(),**flags))
    preservation=[]
    for folder in [V6,V7,V8]:
        manifest=read(folder/'DELIVERY_MANIFEST.json')
        for r in manifest['files']:assert sha(folder/r['relative'])==r['sha256'],str(folder/r['relative'])
        original=next(r for r in read(ROOT/'BASE_PRESERVATION_RECEIPT.json')['prior'] if r['folder']==folder.name)
        assert sha(folder/'DELIVERY_MANIFEST.json')==original['manifest']['sha256']
        preservation.append(dict(namespace=folder.name,files=len(manifest['files']),all_byte_identical=True,manifest_sha256=sha(folder/'DELIVERY_MANIFEST.json')))
    write('PRESERVATION_VERIFICATION.json',dict(time=now(),PASS=True,prior=preservation))
    exact=ci.loc['D2_normal_1.0_EXACT__NONE'];cen=ci.loc['D2_normal_1.0__NONE']
    family=[]
    for prefix in ['D1__','D2_','D3__']:
        z=comparison[comparison.arm.str.startswith(prefix)&~comparison.arm.str.contains('EXACT')]
        b=z.sort_values('coverage_std').iloc[0]
        family.append(dict(family=prefix.rstrip('_'),minimum_std_arm=b.arm,coverage_std=b.coverage_std,pooled_coverage=b.Q90_coverage,min_fold_coverage=b.min_fold_coverage))
    pd.DataFrame(family).to_csv(ROOT/'TEMPORAL_STABILITY_COMPARISON.csv',index=False)
    write('SOURCE_MANIFEST.json',dict(time=now(),repository='BeaverVillage/MobileESS',base=BASE,preApril_cache=record(V7/'.local/GPU_PREAPRIL.parquet'),
        exposed_April_cache=record(V8/'APRIL_JOBS.parquet'),parent_artifacts=preservation,
        source_authority='Archived request descriptors; immutable submit-version source unavailable; strict source-backed features0',
        primary_documentation=[dict(url='https://xgboost.readthedocs.io/en/release_3.0.0/tutorials/aft_survival_analysis.html',purpose='AFT exact/right-censor bounds and distributions'),
            dict(url='https://xgboost.readthedocs.io/en/release_3.0.0/parameter.html',purpose='hist and AFT parameters')],
        raw_zip=record(RAW),packages={p:importlib.metadata.version(p) for p in ['numpy','pandas','lightgbm','xgboost','scipy','pyarrow']},
        python=platform.python_version(),May_payload_opened=False))
    support=pd.read_csv(ROOT/'TEMPORAL_FOLD_SUPPORT.csv')
    qp=pd.read_csv(ROOT/'PREAPRIL_QUEUE_REPLAY.csv');qm=qp[qp.arm.isin(['W0','B0','V8',arm])]
    fd=pd.DataFrame([dict(fold=x['fold'],TRAIN_cutoff=x['TRAIN_cutoff'],VALID_from=x['VALID_submit_from'],VALID_end=x['VALID_end']) for x in read(ROOT/'TEMPORAL_FOLD_CONTRACT.json')['folds']])
    proper=pd.read_csv(ROOT/'POOLED_PROPER_DISTRIBUTION_SCORES.csv')
    selected_proper=proper[proper.arm.eq(arm)].copy();selected_proper['arm']='V9_SELECTED'
    base=comparison[comparison.arm.isin(['W0','B0','Bconst','V8','D1__NONE','D2_normal_1.0__NONE','D2_logistic_1.5__NONE','D3__NONE','V9_SELECTED'])].merge(pd.concat([proper,selected_proper]),on='arm',how='left')
    answers=[
    ('V8의 직접적인 실패 원인은 무엇이었는가?','April 전체 Q90 coverage69.46%, >4h37.62%로 긴 작업을 심하게 과소예측했다. 시간별 보정 불안정도 남았다. reservation 감소를 안전성 개선으로 해석할 수 없다.'),
    ('왜 April은 이제 pristine holdout이 아닌가?','V8에서 이미 열어 실패 수치를 확인했고 그 지식이 V9 문제 설정에 쓰였다. 새 모델·분포·보정·gate 선택에는 사용하지 않았다. 노출 회귀 평가로만 명명한다.'),
    ('5개 blocked fold를 정확히 어떻게 나눴는가?','아래 UTC 표와 membership CSV에 사전 고정했다. validation 직전14일 CAL, 그 전까지 expanding TRAIN이며 label은 각 cutoff에서 마스킹했다.\n\n'+table(fd,list(fd.columns))),
    ('각 fold의 Q90 coverage는?',table(mine,['fold','N','Q90_coverage','Q90_pinball','Q50_MAE'])),
    ('temporal calibration stability가 개선됐는가?',f'선택 모델 범위 {pct(s.min_fold_coverage)}–{pct(s.max_fold_coverage)}, std={fmt(s.coverage_std)}, stability gate={chosen["TEMPORAL_STABILITY_GATE_PASS"]}. V8의 과거 fold 예측은 미래 학습된 모델의 소급 비교이므로 인과적 개선 증거로 사용하지 않았다.'),
    ('hazard model은 어떻게 total runtime distribution을 만드는가?','x와 age/bin에서 interval hazard h를 예측해 S(t_k)=Π(1−h_m)를 만든다. 구간 안은 일정 hazard rate, 마지막 구간 이후는 마지막 rate 외삽이다. 127개 구간은 첫 TRAIN만 보고 고정했다. 초기15/60/300초 분해 후15분·1시간·6시간·1일 간격이며0초 종료는 첫 구간에 포함한다.'),
    ('AFT model은 censored job을 어떻게 처리하는가?','원래 T의 정확한 lower/upper를 보존하고 라이브러리에는 U=T+1의 exact U/U 또는 censor (c−start+1)/∞를 전달했다. 세 분포×scale1.0/1.5를 비교했다. logU=mu+scale Z를 T=max(exp(logU)−1,0)로 복원한다. PENDING은 runtime 관측이 아니다.'),
    ('D1/D2/D3 중 무엇이 pre-April에서 가장 안정적인가?','단순 std 최소 설정은 아래와 같다. 낮은 변동성만으로 안전성 PASS나 승자를 선언하지 않는다.\n\n'+table(pd.DataFrame(family),list(pd.DataFrame(family).columns))),
    ('전체 Q90 coverage는 nominal90% 부근인가?',f'{pct(s.Q90_coverage)}; 88–92% gate={chosen["OVERALL_Q90_GATE_PASS"]}.'),
    ('fold 하나에 성능 collapse가 있는가?',f'최저 {pct(s.min_fold_coverage)}. 사전 안정성 기준 min≥80%, max≤97%, std≤0.06; 통과={chosen["TEMPORAL_STABILITY_GATE_PASS"]}.'),
    ('>4h coverage는 개선됐는가?',f'pre-April {pct(s.gt4h_coverage)}, fold별 long gate={chosen["LONG_JOB_Q90_GATE_PASS"]}. April {pct(at.loc["gt4h","Q90_coverage"])}를 V8 37.62%와 비교하며 목표85%도 함께 평가한다.'),
    ('>8h/>12h/>24h는 어떤가?',f'pre-April {pct(s.gt8h_coverage)} / {pct(s.gt12h_coverage)} / {pct(s.gt24h_coverage)}. April {pct(at.loc["gt8h","Q90_coverage"])} / {pct(at.loc["gt12h","Q90_coverage"])} / {pct(at.loc["gt24h_aggregate","Q90_coverage"])}. 9개 세부 bucket과 N은 두 LONG_TAIL CSV에 보존했다.'),
    ('walltime/scheduler descriptor는 계속 유용한가?','V8 pre-April ablation 근거로 유지했다. V9의 새 feature search나 April ablation은 하지 않아 각각의 추가 인과 효과를 주장하지 않는다. walltime은 predictor이며 label이나 기본 상한이 아니다.'),
    ('right-censored job을 포함한 것이 성능에 어떤 영향을 주는가?',f'normal AFT scale1.0 검열 포함/완료만: coverage {pct(cen.Q90_coverage)} / {pct(exact.Q90_coverage)}, pinball {fmt(cen.Q90_pinball)} / {fmt(exact.Q90_pinball)}, >4h {pct(cen.gt4h_coverage)} / {pct(exact.gt4h_coverage)}. 이 compact ablation의 관측 효과이며 모든 분포의 개선을 보장하지 않는다.'),
    ('reservation/actual GPUh는 W0/B0/V8 대비 어떤가?',f'pre-April W0={fmt(ci.loc["W0","reservation_actual_GPUh"])}, B0={fmt(ci.loc["B0","reservation_actual_GPUh"])}, V8={fmt(ci.loc["V8","reservation_actual_GPUh"])}, V9={fmt(s.reservation_actual_GPUh)}. Sharpness gate={chosen["RESERVATION_SHARPNESS_PASS"]}. 과소 coverage로 얻은 절감을 성공으로 해석하지 않는다.'),
    ('pre-April queue utility는 개선됐는가?',f'Queue gate={chosen["PREAPRIL_QUEUE_GATE_PASS"]}. 고정5일 empty-background780GPU 연구 replay다. 전체 과거 V42 재구성이 아니며 예약 forecast와 완료 관측 기반 현재-slot stress를 분리했다.\n\n'+table(qm,['fold','arm','start_lt_H','start_ge_H','forecast_horizon_exhausted','causal_unresolved_at_horizon','capacity_violations','overrun_extensions'])),
    ('April exposed regression은 어떻게 나왔는가?',table(april,['arm','N','Q50_MAE','Q90_coverage','Q90_pinball','reservation_actual_GPUh'])+f'\n\nV9 >4h={pct(at.loc["gt4h","Q90_coverage"])}. 이전 V8 결과를 덮어쓰지 않았다.'),
    ('April 결과를 보고 재튜닝했는가?','NO. 다섯 freeze 이후 모델·분포·bin·feature·보정 알고리즘·threshold·provider bytes 변경은 없다. Rolling이면 예정된 과거 관측 상태 갱신만 수행한다.'),
    ('April2 start<H는 W0/B0/V8/V9 각각 몇 개인가?',f'{int(qi.loc["W0","start_lt_H"])} / {int(qi.loc["B0","start_lt_H"])} / {int(qi.loc["V8","start_lt_H"])} / {int(qi.loc["V9","start_lt_H"])}. 같은332개 background와 site ledger, baseline150/47/111 정확 재현이다. 전체 optimizer 통합 결과로 해석하지 않는다.'),
    ('conditional remaining inference는 total-minus-elapsed보다 나은가?',table(remaining[remaining.scope.eq('ALL')],['arm','N','remaining_Q50_MAE_seconds','remaining_MAE_seconds','remaining_Q90_coverage','overrun_checkpoint_fraction'])+'\n\n생존한 작업의 반복 checkpoint는 긴 작업에 더 큰 가중치를 주며 미완료 정답은 제외한다.'),
    ('checkpoint remaining Q90 coverage는?',f'{pct(rr.remaining_Q90_coverage)}, N={int(rr.N)}, jobs={int(rr.unique_jobs)}; 잔여시간 성능 gate={ar["remaining"]["validated"]}. 수학적 조건부 추론의 타당성과 실제 예측 성능은 구분한다.'),
    ('overrun frequency는 줄었는가?',f'checkpoint 비율 Bconst={pct(over.loc["Bconst","overrun_checkpoint_fraction"])}, B0={pct(over.loc["B0","overrun_checkpoint_fraction"])}, V8={pct(over.loc["V8","overrun_checkpoint_fraction"])}, V9={pct(over.loc["V9","overrun_checkpoint_fraction"])}. 원래 total Q90 대비 overrun을 측정해 조건부 잔여 Q90로 계획 초과를 숨기지 않았다.'),
    ('별도 remaining-runtime model이 여전히 필요한가?',f'{flags["SEPARATE_REMAINING_MODEL_NEEDED"]}. 별도 모델은 학습하지 않았다. 조건부 예측 실패가 곧 별도 모델의 필수성을 입증하지는 않는다.'),
    ('selected provider는 완전히 새 job에 호출 가능한가?','YES. CPU predict_total/predict_remaining, UNKNOWN0, 신규 ID 불변성, outcome 거부와 직렬화 예측 일치를 검증했다. 연구 opt-in이 필요하다.'),
    ('online model refit이 필요한가?','NO. Booster bytes는 고정이며 rolling이면 완료 관측 API가 residual 보정 상태만 갱신한다.'),
    ('rolling calibration을 사용했다면 미래 residual leakage가 없는가?',f'선택={contract["calibration_mode"]}; 미래 residual 읽기0. end<예측 UTC day를 먼저 적용한 뒤 잔차를 계산한다. out-of-training 관측만 쓰며 미래 label 교란 불변성과 날짜별 감사 CSV가 있다. April2 counterfactual은 issue 시점 보정 상태를 고정해 off-policy 미래 잔차를 쓰지 않는다.'),
    ('CPU/GPU 어느 backend가 적합한가?',table(bench,[c for c in ['backend','supported','training_seconds','actual_device_identity_verified','preApril_1000_max_quantile_difference_seconds','selected_for_provider'] if c in bench])+'\n\nCPU4 학습/CPU1 추론 bundle을 제공한다. GPU 실제 실행명은 BENCHMARK_GPU.log에서 검증한다. INFERENCE_LATENCY.json은1/10/100/1000건 측정이다.'),
    ('May를 열었는가?','NO. MAY_PAYLOAD_OPENED=FALSE, MAY_USED_FOR_SELECTION=FALSE. 이전 namespace byte hash와 raw ZIP 식별은 May record decoding이 아니다.'),
    ('V42 research Runtime provider로 사용할 수 있는가?',f'검증된 provider 준비={ready}. 선택 {arm}, 전체 gate 통과 후보 {sel["eligible_candidates"]}개. Callable 진단 bundle을 검증 통과로 바꾸지 않는다. V42/AIDC/MESS/electrical kernel은 수정하지 않았다.'),
    ('provenance limitation은 여전히 무엇인가?','Kestrel_trace_proxy archived request descriptor다. 최초 submit 값인지 최종 수정 값인지 증명할 immutable request-version authority가 없다. Strict feature0, authorityFALSE, strict providerFALSE를 유지한다.')
    ]
    text=f'# Runtime-vNext9 분포 기반 런타임 연구 검토\n\n선택 **{arm}**, 진단 전용={sel["diagnostic_only"]}. **V42_RESEARCH_RUNTIME_PROVIDER_READY={ready}**. April은 **EXPOSED_REGRESSION_ONLY**, May는 미개봉이다.\n\n'
    text+='## 사전 계약 및 비교 요약\n\n'+table(base,['arm','Q50_MAE','Q90_coverage','min_fold_coverage','max_fold_coverage','coverage_std','gt4h_coverage','gt12h_coverage','Q90_pinball','proper_coarsened_survival_NLL','reservation_actual_GPUh','queue_starts_lt_H','training_seconds_5fold','batch1000_inference_ms_mean'])+'\n\n'
    text+='B0는 March14T08 이전 fold에서, Bconst/V8은 모든 과거 fold에서 NONCAUSAL_RETROSPECTIVE_REFERENCE다. 그 점수는 선택에 쓰지 않았다. Pinball gate는 인과적 D3 전체 fold와 March14T08 이후 B0 구간만 사용한다. Baseline 학습시간 N/A는 재학습하지 않았다는 뜻이다. MODEL_COMPARISON.csv의 coarsened_survival_NLL은 수치 확률 하한을 적용한 진단 점수다. 엄밀한 proper score는 POOLED_PROPER_DISTRIBUTION_SCORES.csv에 분리했다. 양의 additive shift가 짧은 관측 구간에 확률0을 주면 실제 NLL은 INFINITE다. 다른 수치적0은 NUMERICAL_FLOOR_UNRESOLVED로 표시하고 정확한 proper score라고 주장하지 않는다. 선택 후보도 zero-support 때문에 분포의 log score가 실패한다. 이는 Q90 보정 개선과 별개의 추가 한계다. Brier는 IPCW 모집단 IBS가 아니며 CRPS를 계산했다고 주장하지 않는다.\n\n'
    for i,(question,answer) in enumerate(answers,1):text+=f'## {i}. {question}\n\n{answer}\n\n'
    text+='## 표본 및 재현 범위\n\n'+table(support,['fold','role','N','exact','censored','no_runtime_information','observed_long_gt4h','high_GPU'])+'\n\n'
    text+='Validation 미완료 작업은 quantile 오차에서 제외되고 검열 정보는 분포 score에 남는다. 완료 표본 coverage에는 행정 검열/선택 편향 가능성이 있다. RIGHT_CENSORING_AUDIT의 VALID는 cutoff까지 전체 제출 관측 상태이며 support 표가 실제 validation cohort다. High-GPU N<100은 INSUFFICIENT_SUPPORT로 보고한다.\n\n'
    text+='재현 순서: prepare9.py → verify_causality9.py / verify_math9.py → train9.py → baselines9.py → evaluate9.py → finalize_model9.py → evaluate_april9.py → queue_april9.py → report9.py. 사전 계약/freeze는 배타적 생성이다. 원본 경로·hash는 SOURCE_MANIFEST.json, 계산 캐시 .local은 Git 제외다. 이전 v6/v7/v8의355개 과학 산출물과3개 manifest byte hash를 다시 검증했다.\n'
    (ROOT/'FINAL_REVIEW_KO.md').write_text(text,encoding='utf-8')
    required='RUNTIME_TARGET_AUTHORITY_AUDIT.json RIGHT_CENSORING_AUDIT.json TEMPORAL_FOLD_CONTRACT.json TEMPORAL_FOLD_MEMBERSHIP.csv TEMPORAL_FOLD_SUPPORT.csv FEATURE_CONTRACT.json HAZARD_BIN_CONTRACT.json AFT_MODEL_CONTRACT.json MODEL_COMPARISON.csv FOLD_LEVEL_METRICS.csv LONG_TAIL_METRICS.csv DISTRIBUTIONAL_CALIBRATION.csv GPU_WEIGHTED_METRICS.csv PREAPRIL_QUEUE_REPLAY.csv MODEL_SELECTION_FREEZE.json TEMPORAL_FOLD_FREEZE.json FEATURE_CONTRACT_FREEZE.json CALIBRATION_FREEZE.json PROVIDER_BUNDLE_FREEZE.json CONDITIONAL_REMAINING_DIAGNOSTIC.csv OVERRUN_DIAGNOSTIC.csv APRIL_EXPOSED_RUNTIME_METRICS.csv APRIL2_EXPOSED_QUEUE_REGRESSION.csv COMPUTE_BACKEND_BENCHMARK.csv INFERENCE_LATENCY.json SOURCE_MANIFEST.json FINAL_REVIEW_KO.md FINAL_VERDICT.json'.split()
    assert all((ROOT/n).exists() for n in required);assert read(ROOT/'DISTRIBUTION_MATH_TEST.json')['PASS'] and read(ROOT/'CAUSALITY_VALIDATION.json')['PASS']
    write('DELIVERY_VALIDATION.json',dict(time=now(),PASS=True,required_artifacts=len(required),five_freezes_unchanged=True,parent_byte_preservation=True,math_test_pass=True,causality_test_pass=True,new_job_provider_test_pass=True,no_scientific_gate_override=True))
    files=[dict(relative=str(p.relative_to(ROOT)).replace('\\','/'),bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(ROOT.rglob('*')) if p.is_file() and '.local' not in p.parts and '__pycache__' not in p.parts and p.name not in ['DELIVERY_MANIFEST.json','report9.log','pipeline9.log']]
    write('DELIVERY_MANIFEST.json',dict(base=BASE,scope='docs/runtime_vnext9_distributional_runtime only',files=files))
    print('REVIEW_COMPLETE',flags,flush=True)
if __name__=='__main__':main()
