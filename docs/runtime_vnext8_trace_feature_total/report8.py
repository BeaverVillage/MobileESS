"""Post-freeze reporting only. No model/feature/gate changes."""
from common8 import *
import pandas as pd,numpy as np,os

def md(name,txt):
    with (ROOT/name).open('x',encoding='utf-8',newline='\n') as f:f.write(txt.strip()+'\n')
def main():
    april=pd.read_csv(ROOT/'APRIL_LOCKED_RUNTIME_METRICS.csv').set_index('model');long=pd.read_csv(ROOT/'APRIL_STRATIFIED_RUNTIME_METRICS.csv');long=long[(long.dimension=='long')&long.stratum.eq('T>4h')].set_index('model')
    pre=pd.read_csv(ROOT/'MODEL_COMPARISON.csv');queue=pd.read_csv(ROOT/'APRIL_WALLTIME_VS_RUNTIME_QUEUE_REPLAY.csv').set_index('arm');ck=pd.read_csv(ROOT/'CHECKPOINT_SUBTRACTION_DIAGNOSTIC.csv');ckv=ck[(ck.arm=='V8')&ck.scope.eq('ALL')].iloc[0]
    freeze=read(ROOT/'MODEL_SELECTION_FREEZE.json');evalr=read(ROOT/'APRIL_EVALUATION_RECEIPT.json');qs=read(ROOT/'APRIL_QUEUE_REPLAY_AUDIT.json');selection=read(ROOT/'PRELIMINARY_SELECTION.json');contract=read(ROOT/'RUNTIME_PROVIDER/feature_contract.json');lat=read(ROOT/'INFERENCE_LATENCY.json')
    a=april.loc['V8'];b=april.loc['B0'];w=april.loc['W0'];l=long.loc['V8'];q=queue.loc['V8'];prepass=freeze['selected_qualified_model'];checks=evalr['gate']['checks']
    queueimproved=bool(q.start_lt_H>=queue.loc['W0','start_lt_H'] and q.admitted==queue.loc['W0','admitted'] and q.capacity_violations==0)
    validated=bool(prepass and evalr['gate']['PASS'] and queueimproved and qs['capacity_safe'])
    flags=dict(STRICT_CAUSAL_FEATURE_COUNT=0,REQUEST_VERSION_AUTHORITY_FOUND=False,RESEARCH_TRACE_FEATURE_COUNT=len(contract['selected_features']),OUTCOME_LEAKAGE_FOUND=False,TARGET_RUNTIME_AUTHORITY_PASS=True,
      TOTAL_RUNTIME_MODEL_SELECTED=bool(prepass),FROZEN_DIAGNOSTIC_CANDIDATE_SELECTED=True,Q50_MODEL_VALIDATED=bool(prepass and checks['Q50']),Q90_MODEL_VALIDATED=validated,
      OVERALL_Q90_CALIBRATION_PASS=bool(checks['calibration']),LONG_JOB_Q90_GATE_PASS=bool(checks['long']),HIGH_GPU_GATE='INSUFFICIENT_SUPPORT',
      RESERVATION_SHARPNESS_PASS=bool(checks['reservation'] and checks['sharp_pinball']),RESERVATION_REDUCTION_PASS=bool(checks['reservation']),
      APRIL_QUEUE_REPLAY_COMPLETED=True,APRIL_QUEUE_REPLAY_IMPROVED=queueimproved,CHECKPOINT_SUBTRACTION_VALIDATED=bool(evalr['checkpoint_adequate']),
      REMAINING_RUNTIME_MODEL_RESEARCH_NEEDED=True if validated and not evalr['checkpoint_adequate'] else False if validated else 'INCONCLUSIVE',
      TRACE_DESCRIPTOR_RUNTIME_MODEL_VALIDATED=validated,V42_RESEARCH_RUNTIME_PROVIDER_READY=validated,STRICT_CAUSAL_RUNTIME_PROVIDER_READY=False,
      APRIL_USED_FOR_SELECTION=False,MAY_USED_FOR_SELECTION=False,ONLINE_REFIT_REQUIRED=False,NEW_JOB_CALLABLE=read(ROOT/'NEW_JOB_CALLABLE_TEST.json')['PASS'],
      CAPACITY_SAFETY_PASS=qs['capacity_safe'],OVERRUN_CONTRACT_PASS=read(ROOT/'OVERRUN_CONTRACT_TEST.json')['PASS'],
      selected_diagnostic_candidate=selection['selected'],calibration=selection['calibration'],reason='No pre-April eligible challenger; locked April fails calibration, long-job safety, B0 accuracy/pinball and W0 queue utility. Keep diagnostic package, reject research integration.',
      production_certified=False,prior_vNext7_rewritten=False,created_at=now())
    write('FINAL_VERDICT.json',flags)
    ci=pd.read_csv(ROOT/'PAIRED_UNCERTAINTY.csv');abl=pd.read_csv(ROOT/'SELECTED_FAMILY_ABLATION.csv');screen=pd.read_csv(ROOT/'IDENTITY_SUPPORT_SCREEN.csv')
    table='|모델|Q50 MAE(s)|Q90 coverage|>4h coverage|Q90 pinball|예약/실제 GPUh|W0 대비 예약|\n|---|---:|---:|---:|---:|---:|---:|\n'
    for name in ['W0','B0','Bconst','V8']:
        r=april.loc[name];table+=f'|{name}|{r.Q50_MAE:,.1f}|{r.Q90_coverage:.2%}|{long.loc[name,"Q90_coverage"]:.2%}|{r.Q90_pinball:,.1f}|{r.reservation_to_actual_ratio:.4f}|{r.reservation_to_W0_ratio:.2%}|\n'
    questions=[
      ('어떤 Kestrel raw/archive feature를 사용했는가?','GPU/nodes/cores/memory/walltime 요청 수치, QoS·partition·account 익명 토큰, array index/존재 descriptor를 사용했다. 파생 log·비율·곱·결측 indicator를 포함해 최종 진단 후보는29개 입력 열이다. 원본9종 입력 개념에서 만든 수이며9개 모두 strict하다는 뜻은 아니다. 모델 이름은 M3_F2다.'),
      ('어떤 feature를 제외했고 왜 제외했는가?','actual start/end/runtime, 상태, queue wait, 사용량, 미래 상태·checkpoint는 금지했다. submit hour/dow도 제외했다. user/name/submitline/script/workdir는 빈도·cardinality·chronological unseen screen에 탈락했다. job_type/python/reframe은 생성시점 불명확으로 제외했다. ID는 lookup에 쓰지 않는다.'),
      ('strict causal feature=0과 research trace feature 사용은 어떻게 다른가?','PR78의 원본 제출 버전 authority와 strict 집합0은 그대로다. 사용자 지시에 따라 archive의 요청 descriptor를 연구용 proxy로 사용할 수 있지만, 원본 제출값 인증이나 production 승격으로 해석하지 않는다. provider는 Kestrel_trace_proxy와 strict FALSE를 반환하고 연구 opt-in을 요구한다.'),
      ('Runtime target은 정확히 무엇인가?','초 단위 end_time-start_time이다. 큐 대기와 요청 walltime은 라벨에 포함하지 않았다. pre-April 원자료 시간차와 기존 normalized runtime_seconds의 유효 행 오차는0초다. suspension 등을 제외한 CPU busy time이나 여러 requeue attempt의 누적 실행시간이라고 주장하지 않는다. 잘못된 시간 순서는 제외, 관측된0초 실행은 유지했다.'),
      ('가장 좋은 feature family는 무엇인가?','고정된 다기준 선택 순위에서는 account·array를 추가한 F2의 M3가 진단 후보로 남았다. 단, 모든 predictive gate를 통과한 최상위 모델은 없다. F2를 일반적으로 우수하다고 선언하지 않는다. F3와 제거 ablation도 pre-April에서만 수행했다.'),
      ('requested walltime은 얼마나 유용했는가?','선택 후보의 walltime 관련 입력/정규화를 제거한 M2 대조군은 DEV pinball4504.2→5734.7, CAL_VALID1290.7→1647.0으로 악화됐다. walltime 정규화까지 함께 바뀌므로 순수 단일 변수 효과가 아니다. 요청시간이 실제시간이라는 뜻도 아니다.'),
      ('GPU/nodes/cores/memory shape는 얼마나 기여했는가?','M3_F2에서 파생 shape를 제거하면 DEV pinball4504.2→4531.1, CAL_VALID1290.7→1359.4다. 기여는 작고 구간에 따라 다르며 인과 효과나 통계적으로 확실한 개선으로 단정하지 않는다. 기본 자원 수치는 유지하는 제거 실험이다.'),
      ('QoS/partition/account/user는 도움이 되었는가?','scheduler와 account를 제거한 결과는 SELECTED_FAMILY_ABLATION.csv 및 FEATURE_SET_ABLATION.csv에 분리했다. DEV에서 scheduler 제거 시 coverage84.91%→54.98%로 악화됐다. account가 F2의 유일한 통과 identity다. user는 CAL_VALID unknown86.42%로 배제돼 기여를 주장할 수 없다.'),
      ('workflow/script identity는 unseen 문제 때문에 쓸 수 있었는가?','최종 후보에는 넣지 않았다. 빈도20 이상 TRAIN mapping 기준 CAL_VALID unknown은 script99.86%, workdir99.61%, name96.44%, submitline96.18%다. 기존 공개 토큰 반복만으로 안정적인 새 작업 workflow identity를 보장하지 않는다. 역식별은 하지 않았다.'),
      ('raw vs log-runtime target 중 무엇이 나았는가?','F2에서 M1 raw DEV pinball4834.1, M2 log5125.1로 raw가 낫지만 CAL_VALID는2574.8/2355.7로 log가 낫다. 어느 한 변환이 일관되게 우월하지 않았다. Q50과 장기 coverage도 별도로 비교했다.'),
      ('walltime-relative target은 효과가 있었는가?','M3는 log((T+1)/(walltime+1))를 학습하고 exp(pred)×(walltime+1)-1로 복원한다. DEV/CAL_VALID pinball4504.2/1290.7과 예약 감소가 선택 순위에 도움이 됐지만, 최종 April undercoverage가 커서 유효성 검증에는 실패했다.'),
      ('long-tail mixture는 효과가 있었는가?','M4는 P(T>4h) classifier와 short/long 각각6개 조건부 log-quantile로 CDF mixture를 구성했다. 구간이 분리되어 있어 일반 이분법 대신 동일한 mixture inverse를 직접 계산했다. F2 DEV pinball5248.9, 장기 coverage79.30%로 목표를 충족하지 못했다. M5는 상위 두 가족 오차 상관0.961이 사전 조건0.95 미만을 만족하지 않아 제외했다.'),
      ('최종 Q50/Q90 성능은?',f'April mature49,712행에서 Q50 MAE {a.Q50_MAE:,.1f}초, Q90 pinball {a.Q90_pinball:,.1f}다. B0의 MAE {b.Q50_MAE:,.1f}초와 pinball {b.Q90_pinball:,.1f}보다 악화됐다. 이는 frozen 진단 후보의 결과이며 통과 모델 성능이라고 쓰지 않는다.'),
      ('전체 Q90 coverage는?',f'{a.Q90_coverage:.2%}로 사전88–92% 기준을 실패했다. DEV84.91%, CAL_VALID99.24%에서도 구간 간 안정성이 부족했다.'),
      ('>4h Q90 coverage는?',f'April9,628행에서{l.Q90_coverage:.2%}로 사전85% 최소 기준에 크게 못 미친다. B0는{long.loc["B0","Q90_coverage"]:.2%}, Bconst는{long.loc["Bconst","Q90_coverage"]:.2%}다.'),
      ('GPU-weighted long-job 성능은?',f'장기 작업의 GPU 가중 coverage는{l.GPU_Q90_coverage:.2%}, underprediction은{l.GPU_underprediction_rate:.2%}다. 자원 가중치를 적용해도 장기 보호 실패다.'),
      ('reservation/actual GPUh ratio는?',f'900초 올림을 적용한 V8={a.reservation_to_actual_ratio:.4f}, W0={w.reservation_to_actual_ratio:.4f}, B0={b.reservation_to_actual_ratio:.4f}다. 연속시간 비율과 별도 저장했으며 vNext6의 unrounded 수치를 그대로 비교하지 않았다.'),
      ('W0보다 얼마나 reservation을 줄였는가?',f'{(1-a.reservation_to_W0_ratio):.2%} 감소했다. Q90/장기/queue gate를 실패했으므로 안전하거나 실용적인 개선으로 인정하지 않는다.'),
      ('B0보다 실제로 개선됐는가?','종합적으로 아니다. pre-April pinball/예약에서 일부 개선이 있었지만 DEV Q50은 악화되고 장기 underprediction도 나빠졌다. 잠금 April에서도 MAE·pinball·coverage가 악화됐다. 예약 감소 하나로 승격하지 않았다.'),
      ('개선 차이 uncertainty는?','제출 UTC일 단위 paired1000회 bootstrap을 사용했다. DEV pinball 차이(V8−B0)−268.6초의95% CI는[−1811.3,1475.6]으로0을 포함한다. DEV MAE 차이+3365.0초 CI[930.6,6065.1]은 악화다. CAL_VALID는3일뿐이므로 interval을 강한 일반화 증거로 볼 수 없다. 4개 요구 지표의 전체 CI는 PAIRED_UNCERTAINTY.csv에 있다.'),
      ('April2 start<H는 W0/B0/V8 각각 몇 개인가?',f'동일 v6 기준의 예약 ledger에서{int(queue.loc["W0","start_lt_H"])}/{int(queue.loc["B0","start_lt_H"])}/{int(q.start_lt_H)}건이다. 세 arm 모두2340건 admitted. W0의 site/start를 원래 reference와 정확히 재현했다.'),
      ('vNext6의150→0 악화는 해소됐는가?','0건 collapse 자체는111건으로 완화됐지만 W0의150건보다39건 적다. 따라서 운영 개선 gate는 FALSE다. 별도 현재-slot dispatch stress는 모든 arm841건으로, 예약 ledger와 다른 정책이며 그 수치로 실패를 감추지 않는다.'),
      ('checkpoint total-minus-elapsed는 충분한가?',f'아니다. mature 작업의 모든30분 checkpoint299,805개에서 remaining MAE{ckv.remaining_MAE_seconds:,.1f}초, overrun checkpoint{ckv.overrun_checkpoint_fraction:.2%}다. 15분/30분/1h/2h/4h 분류와 장기 실행집단도 보고했고 vNext6 Bconst와 비교했다.'),
      ('별도 remaining/survival model이 필요한가?','INCONCLUSIVE다. 먼저 total-runtime 모델이 충분히 좋아져야 한다는 조건을 통과하지 못했다. subtraction 실패만으로 survival 필요를 TRUE로 선언하거나 이번 작업에서 추가 학습하지 않았다.'),
      ('overrun semantics는 안전한가?','계약 unit 검증은 PASS다. RUNNING이고 elapsed≥plan이면 GPU를 유지하고900초씩 연장, 강제 종료하지 않으며 STAY를 반환한다. 별도 causal stress에서 capacity violation0, extension은 W0/B0/V8=209/1014/1995다. 이는 배경332개 예약을 고정한 제한된 재생이며 전체 V42 운영 안전 인증은 아니다.'),
      ('CPU/GPU 어느 backend가 적합한가?',f'이 workload에서는 CPU4 threads가4.43초로 CPU single11.78초, OpenCL GPU6.67초보다 빨랐다. 비교 예측 오차0이었다. CPU 단일 추론 P99={lat["batches"]["1"]["p99_ms"]:.2f}ms. OpenCL 기본 장치로 실행했으며 장치명 runtime 로그를 남기지 않아 RTX4060 귀속은 아래 장치 감사 한계에 따라 정적 추정으로 표시한다.'),
      ('새 job inference가 재학습 없이 가능한가?','가능하다. CPU provider의 predict_total(job_record,event_time=None)가 Q50/Q90·버전·Kestrel_trace_proxy를 반환한다. 새 job ID 치환 불변성, unknown category0, 금지된 outcome key 거부, 직렬화 예측 오차0을 확인했다. callable이라는 사실은 성능 승격을 뜻하지 않는다.'),
      ('April/May tuning은 있었는가?','없다. target·membership·피처/맵·모델·보정·gates·provider bytes를3개 freeze로 고정한 뒤 April raw 파티션을1회 열었다. 후속 코드는 평가·문서·무학습 장치 감사뿐이다. May 파티션은 열지 않았고 April 행의 cutoff 이후 end는 라벨 산술 전에 가렸다.'),
      ('V42 research provider로 사용할 수 있는가?','검증된 V42 research provider로 채택할 수 없다. TRACE_DESCRIPTOR_RUNTIME_MODEL_VALIDATED=FALSE 및 V42_RESEARCH_RUNTIME_PROVIDER_READY=FALSE다. 재현 가능한 진단 패키지만 보존했고 V42 코드/논문/기존 모델을 수정하지 않았다.'),
      ('논문 provenance limitation은 무엇인가?','익명 요청 descriptor를 이용한 trace 연구라고 밝혀야 한다. 공개 trace가 모든 값의 immutable initial submission version임을 확인할 request-version 이력을 제공하지 않는다는 제한이 필수다. 검증되지 않은 연구 후보의 결과를 production-certified scheduler 입력 모델이라고 쓰면 안 된다.')]
    text='# Runtime-vNext8 최종 검토\n\n**결과는 부정적이다. 작업별 연구 예측기와 호출 패키지는 만들었지만 통과 모델은 없다. 기존 strict authority FALSE를 유지하고 V42 연구 통합도 승인하지 않는다.**\n\n'+table+'\n'
    for i,(title,answer) in enumerate(questions,1):text+=f'## {i}. {title}\n\n{answer}\n\n'
    text+='## 범위와 해석\n\nTRAIN222,182, DEV11,486, CAL_FIT5,438, CAL_VALID14,623행은 vNext6 mature membership와 해시까지 일치한다. DEV/CAL_FIT/CAL_VALID unresolved495/498/13건은 라벨로 쓰지 않았다. April51,499행 중1,787건은 unresolved로 제외했다. 성공 COMPLETED 작업만의 모델이 아니며 종료된 실패·취소 작업도 실행시간 라벨에 포함될 수 있다. 종료 cutoff에 의한 maturity selection과 archive request-version 불확실성을 유지한다.\n\n'
    text+='MODEL_SELECTION_FREEZE의 selected_qualified_model은 FALSE다. 필수 잠금 평가를 마치기 위해 사전 순위의 한 **진단 후보**만 직렬화했다. FAILED 후보를 성능 통과로 선택했다는 뜻이 아니다. TOTAL_RUNTIME_MODEL_SELECTED도 qualified 의미로 FALSE다.\n\n'
    text+='장기 gate는 actual>4h를 **평가 층화**에만 쓴다. inference에는 실행/종료/라벨이 들어가지 않는다. M4 TRAIN의 장기 label은 classifier의 정상 학습 타깃이며 새 job의 actual 장기 여부를 입력으로 주지 않는다. CAL_FIT residual로 DEV에 보정값을 적용한 행은 소급적 진단이고 사전 DEV gate는 raw prediction이다.\n\n'
    text+='F3 pruning은 pre-April DEV 두 시간구간에서 양의 group permutation 중요도를 요구했다. 추가 selected-family ablation은 후속 진단이며 재선택에 쓰지 않았다. M5는 고정된 complementarity 조건에 탈락했다. 대규모 search, 별도 remaining·survival·neural 모델은 없다.\n\n'
    text+='## 최종 flags\n\n```json\n'+json.dumps(flags,indent=2,ensure_ascii=False)+'\n```\n\n'
    text+='세부 근거는 MODEL_COMPARISON.csv, SELECTED_FAMILY_ABLATION.csv, CALIBRATION_COMPARISON.csv, PAIRED_UNCERTAINTY.csv, APRIL_LOCKED_RUNTIME_METRICS.csv, APRIL_WALLTIME_VS_RUNTIME_QUEUE_REPLAY.csv와 SOURCE_MANIFEST.json에 보존했다. 원본 gate·provider bytes의 사후 불변성은 VERIFICATION.json으로 검증한다.\n'
    md('FINAL_REVIEW_KO.md',text)
    md('PAPER_FACING_INTERPRETATION.md','''
# 논문용 문구 초안 — 본문은 수정하지 않음

“Runtime prediction was trained using anonymized job request descriptors contained in the Kestrel workload trace.”

“The public trace does not provide sufficient request-version provenance to verify that every archived descriptor exactly corresponds to the immutable initial submission value.”

The frozen Runtime-vNext8 trace-descriptor challenger reduced rounded reservations but failed calibration, long-job coverage, and queue utility criteria in the locked April evaluation. It was therefore not adopted as the V42 research runtime provider. These results describe a retrospective trace experiment and do not certify original scheduler inputs or production readiness.

baseline·challenger의 전체 결과와 부정적 gate를 함께 보고한다. 장기 undercoverage를 예약 절감이라는 장점만으로 대체하지 않는다. checkpoint subtraction 실패는 total-runtime 성능이 불충분한 상태의 관측이므로 별도 survival model의 필요성을 확정하지 않는다.
''')
    # Supplemental documentation of already-frozen transforms, not a new feature decision.
    maps={'num_gpus_req':'gpus_requested','num_nodes_req':'nodes_req','num_cores_req':'processors_req','requested_memory_mib':'memory_req','requested_seconds':'wallclock_req','account':'account_hash','qos':'qos','partition':'partition','array_index':'array_pos'}
    expr={'log_gpu':'log1p(num_gpus_req)','log_nodes':'log1p(num_nodes_req)','log_cores':'log1p(num_cores_req)','log_memory':'log1p(requested_memory_mib)','log_walltime':'log1p(requested_seconds)','gpu_per_node':'num_gpus_req / num_nodes_req','cores_per_node':'num_cores_req / num_nodes_req','cores_per_gpu':'num_cores_req / num_gpus_req','memory_per_gpu':'requested_memory_mib / num_gpus_req','memory_per_node':'requested_memory_mib / num_nodes_req','requested_gpu_time':'num_gpus_req * requested_seconds','log_requested_gpu_time':'log1p(num_gpus_req * requested_seconds)','is_array_descriptor':'array_pos valid/nonmissing indicator (not certified original membership)','log_array_index':'log1p(array_pos) if nonnegative integer','gpu_nodes_inconsistent':'gpus_requested > 4*nodes_req'}
    rows=[]
    for col in contract['selected_features']:
        formula=expr.get(col,'numeric parsing or TRAIN-only category map0UNKNOWN')
        if col.endswith('_missing_or_invalid'):formula='is missing/nonfinite/nonpositive (counts also noninteger); array index allows zero'
        rows.append(dict(feature=col,raw_source=maps.get(col,'derived from '+formula),exact_transform=formula,implementation='features8.py::engineer',no_outcome_input=True,original_version_verified=False))
    pd.DataFrame(rows).to_csv(ROOT/'SELECTED_FEATURE_TRANSFORM_LINEAGE.csv',index=False)
    md('COMPUTE_DEVICE_ATTRIBUTION.md','''
# 계산 장치 귀속 한계

CPU single/4-thread 및 `device_type=gpu, gpu_use_dp=True`로 동일 TRAIN·M3_F2 두 quantile을 재학습해 pre-April DEV 예측 동등성을 확인했다. 원래 선택된 CPU model bytes를 유지했다. 벤치마크 이름은 RTX4060_OpenCL_GPU지만 explicit platform/device index를 고정하지 않았다. verbosity=-1로 runtime device-name 로그도 없다.

사후 **무학습** OpenCL 열거 결과 platform0=device0 NVIDIA GeForce RTX4060 Laptop, platform1=device0 Intel UHD다. LightGBM4.6 GPUTreeLearner::InitGPU는 index=-1이면 Boost.Compute default_device를 사용한다. 기본 GPU 순서상 NVIDIA 사용을 추정할 수 있으나, 빌드된 Boost 버전과 당시 device-name 로그까지 확보한 직접 관측은 아니다. 6.67초는 OpenCL GPU 경로 실측, 정확한 RTX4060 귀속은 이 한계를 명시한다. CPU4-thread 선택은 CPU 측정과 동등성만으로도 유지된다. freeze 이후 이 문제를 이유로 다시 fit하거나 모델을 교체하지 않았다.

공식 코드: https://github.com/microsoft/LightGBM/blob/v4.6.0/src/treelearner/gpu_tree_learner.cpp#L652 ; https://github.com/boostorg/compute/blob/boost-1.84.0/include/boost/compute/system.hpp . `OPENCL_DEVICE_AUDIT.json`이 실제 열거 결과다.
''')
    prior_sources=read(V7/'SOURCE_MANIFEST.json')
    write('SOURCE_MANIFEST.json',dict(created_at=now(),base_commit=BASE,raw=record(RAW),vNext7_manifest=record(V7/'DELIVERY_MANIFEST.json'),vNext6_manifest=record(V6/'DELIVERY_MANIFEST.json'),
      target_sources=read(ROOT/'RUNTIME_TARGET_AUTHORITY_AUDIT.json')['evidence'],baseline=read(ROOT/'BASELINE_REPRODUCTION.json'),queue_sources=qs['source_files'],
      splits=record(ROOT/'DATA_SPLIT_AND_MATURITY.json'),source_code=[record(p) for p in sorted(ROOT.glob('*.py'))],freeze_files=[record(ROOT/p) for p in ['MODEL_SELECTION_FREEZE.json','FEATURE_CONTRACT_FREEZE.json','PROVIDER_BUNDLE_FREEZE.json']],
      official_sources=['https://data.nlr.gov/submissions/302','https://github.com/NatLabRockies/hpc-oda-commons/tree/218d75f56b783ebfd698100f9406cfb46fa04c01','https://lightgbm.readthedocs.io/en/v4.6.0/Parameters.html','https://lightgbm.readthedocs.io/en/v4.6.0/GPU-Tutorial.html','https://github.com/microsoft/LightGBM/blob/v4.6.0/src/treelearner/gpu_tree_learner.cpp','https://github.com/boostorg/compute/blob/boost-1.84.0/include/boost/compute/system.hpp'],
      source_access_date='2026-09-28',model_input_limits='No April before freeze; only locked April after freeze; no May partition or mature May outcome',
      dependency_compatibility='tqdm4.67.1 installed into ignored .local/dependencies; NumPy2 pickle module names aliased to NumPy1.26 implementation for B0 deserialization only, exact predictions0 error; XGBoost pickle warning retained in logs; no B0 refit'))
    md('README.md','''
# Runtime-vNext8 연구 결과

`FINAL_REVIEW_KO.md`와 `FINAL_VERDICT.json`을 먼저 읽는다. 검증된 운영/연구 승격 모델은 없다. RUNTIME_PROVIDER는 frozen 진단 후보이며 기본 로더는 연구 opt-in을 요구한다.

재현은 Python3.11, numpy1.26.4, pandas2.2.3, LightGBM4.6.0, pyarrow18.1.0 기준이다. baseline import용 tqdm4.67.1이 필요하다. SOURCE_MANIFEST의 정확한 원자료/이전 frozen 경로를 준비하고 **빈 독립 output 디렉터리**에서 register8→prepare8→baseline8→train8→benchmark_selected8→freeze_provider8 순서로 실행한다. 이전 결과를 덮어쓰지 않는다. `common8.py`의 경로를 새 환경에 맞춘다. 이미 동결된 결과에서 새 fit을 실행하지 않는다.

세 freeze 후 evaluate_april8는 raw April을1회만 읽는다. 이후 queue_replay8, report8, verify8, delivery8을 실행한다. 기존 산출물 검증에는 verify8만 사용한다. May는 필요 없다. provider folder를 Python module path에 두고 `RuntimeProvider(bundle_path,allow_research=True).predict_total(job_record,event_time=None)`를 호출한다. 입력은 feature_contract와 preprocessing의 normalized request keys를 따른다. 학습·baseline 코드 없이 CPU inference가 가능하다.

feature_count29는 engineered/indicator/encoded 열의 수다. total-runtime subtraction은 조건부 survival quantile이 아니다. 원본 요청 authority FALSE, 직렬화 PASS, predictive validation FAIL을 구분한다.
''')
    print('REPORT_COMPLETE',flags,flush=True)
if __name__=='__main__':main()
