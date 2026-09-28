from paths import *
import sys,hashlib
import numpy as np,pandas as pd
from metrics import stats
from datetime import datetime,timezone

def main():
    selection=read(ROOT/'MODEL_SELECTION_FREEZE.json');apr=read(ROOT/'APRIL_EVALUATION_RECEIPT.json');lat=read(ROOT/'INFERENCE_LATENCY.json');rq=read(ROOT/'REQUEST_VERSION_AUTHORITY_AUDIT.json')
    m=pd.read_csv(ROOT/'APRIL_LOCKED_RUNTIME_METRICS.csv').set_index('model');s=m.loc['STRICT_SELECTED'];w=m.loc['W0'];b=m.loc['B0_RESEARCH']
    cv=pd.read_csv(ROOT/'MODEL_COMPARISON.csv');cv=cv[(cv.role=='CAL_VALID')&(cv.model=='SELECTED_CALIBRATED')].iloc[0]
    q=pd.read_csv(ROOT/'APRIL_WALLTIME_VS_ML_QUEUE_REPLAY.csv');cp=apr['checkpoint_metrics'];queue=read(ROOT/'APRIL_W0_REPRODUCTION.json')
    ag=pd.read_csv(ROOT/'APRIL_STRATIFIED_METRICS.csv');ag=ag[ag.model=='STRICT_SELECTED'];long=ag[(ag.dimension=='long_actual')&(ag.stratum=='>4h')].iloc[0];high=ag[(ag.dimension=='high_GPU')&(ag.stratum=='16+')].iloc[0]
    # Exact requested boundary supplement; old tables remain byte-for-byte preserved.
    exact=[];sys.path.insert(0,str(ROOT/'RUNTIME_PROVIDER'));from provider import RuntimeProvider
    provider=RuntimeProvider(allow_research=True)
    for period in ['PREAPRIL','APRIL']:
        f=pd.read_parquet(ROOT/f'{period}_JOBS.parquet');f=f[f.label_valid]
        if period=='PREAPRIL':f=f[f.role.isin(['DEV','CAL_FIT','CAL_VALID'])]
        else:f['role']='APRIL'
        for role,g in f.groupby('role'):
            if period=='PREAPRIL':g=g[g.end_time.lt(pd.Timestamp(read(ROOT/'EXPERIMENT_PROTOCOL.json')[role]['mature_before']))]
            p=provider.predict_array(len(g));v=g.requested_seconds
            groups=np.select([v<900,v<1800,v<3600,v<7200,v<=14400],['<15m','15-30m','30-60m','1-2h','2-4h'],default='>4h')
            for name in ['<15m','15-30m','30-60m','1-2h','2-4h','>4h']:
                ix=groups==name
                if ix.any():exact.append(dict(role=role,model='FROZEN_SELECTED',requested_bucket=name,**stats(g[ix],p[ix,0],p[ix,1])))
    pd.DataFrame(exact).to_csv(ROOT/'EXACT_REQUESTED_BUCKET_METRICS.csv',index=False)
    flags=dict(TOTAL_RUNTIME_MODEL_SELECTED=True,TOTAL_RUNTIME_Q90_GATE_PASS=False,HIGH_GPU_RUNTIME_GATE_PASS=False,LONG_JOB_RUNTIME_GATE_PASS=False,
      REQUESTED_WALLTIME_DIRECT_SCHEDULING_REJECTED=True,PRE_APRIL_CAUSAL_TRAINING=True,APRIL_USED_FOR_SELECTION=False,MAY_USED_FOR_SELECTION=False,
      SERIALIZED_MODEL_PRESENT=True,SERIALIZED_PREPROCESSING_PRESENT=True,NEW_JOB_CALLABLE=True,ONLINE_REFIT_REQUIRED=False,
      CHECKPOINT_SUBTRACTION_BASELINE_VALIDATED=False,SEPARATE_REMAINING_RUNTIME_MODEL_NEEDED='INCONCLUSIVE',OVERRUN_CONTRACT_VALIDATED=True,
      SELECTED_TRAIN_BACKEND='CPU_SINGLE',CPU_INFERENCE_READY=lat['CPU_INFERENCE_READY'],APRIL_WALLTIME_BASELINE_REPRODUCED=True,APRIL_ML_QUEUE_REPLAY_COMPLETED=True,
      RUNTIME_PROVIDER_READY_FOR_V42=False,OPTIMIZER_INTEGRATION_PERFORMED=False,
      REQUEST_VERSION_AUTHORITY_FOUND=False,SUBMISSION_TIME_FEATURES_STRICTLY_VERIFIED=True,MUTABLE_REQUEST_FEATURE_COUNT=7,UNVERIFIED_REQUEST_FEATURE_COUNT=9,
      IMMUTABLE_FEATURE_ONLY_MODEL_TRAINABLE=True,STRICT_CAUSAL_RUNTIME_PROVIDER_READY=False)
    write('FINAL_VERDICT.json',dict(status='COMPLETED_NEGATIVE_RESULT_NO_PRODUCTION_PROMOTION',flags=flags,
      selected_scope='Persisted strict featureless M2 research candidate; selected is not promoted.',
      feature_flag_scope='Only constant_bias=1 is verified by construction. Zero job-specific immutable predictors were source-backed. Not certification of submitted request versions.',
      high_GPU_gate_scope='DEV N89 and CAL_VALID N6 < preregistered100: insufficient support. April N298 is descriptive and cannot repair prefreeze gate.',
      preApril_scope='Event-time mature labels end<cutoff; logical retrospective freeze; artifact physically created September2026. End is not a certified ingestion receipt.',
      flags_not_implying_ready=['SERIALIZED_MODEL_PRESENT','NEW_JOB_CALLABLE','SUBMISSION_TIME_FEATURES_STRICTLY_VERIFIED'],
      failed_reasons=['No source-backed informative submission-time feature subset','DEV pinball worse than B0','Long runtime undercoverage','Insufficient high-GPU validation support','Independent CAL_VALID overcoverage/reservation inflation','April walltime-scale reservation and zero recovered D-day jobs','Checkpoint subtraction diagnostic fails'],
      source_authority_remedy='Original submission attempt record, per-field revisions/effective timestamps and ingestion receipts; deterministic user-category hash mapping if used. No proxy promotion.',
      model_changed_after_April=False,May_used=False,V42_CC4_MESS_IEEE_OpenDSS_unchanged=True))
    source_notes='''# 요청 버전·수집 방식 감사

공식 NLR 데이터 카드와 [dataset302](https://data.nlr.gov/submissions/302)는 주기적 sacct 수집→PostgreSQL load_slurm→DB trigger/batch 갱신 경로를 설명한다. 내부 SQL 함수는 공개되지 않았고 원 Slurm JSONB 및 job_step은 배포에서 빠졌다. 공개 아카이브의 버전 번호는 작업 요청의 버전 이력이 아니다. 로컬 scheduler authority 디렉터리의 slurmctld 자료는 parser 코드와 합성 테스트이며, Kestrel 제출 원본 로그가 아니다. 조사 범위 안에서 원본 authority는 발견되지 않았다는 결론이며, 비공개 로그의 부재를 주장하지 않는다.

| 정규화 피처 | 제출 시 의미 존재 | 이후 수정 가능성 | 아카이브 최초/최종 | 원본 이력 | 새 모델 사용 |
|---|---|---|---|---|---|
| requested_seconds | walltime 요청 | 문서상 가능 | 미확인 | 없음 | 제외 |
| num_gpus_req | GPU 요청 | GRES 변경 경로 존재 | 미확인 | 없음 | 제외 |
| num_nodes_req | node 요청 | 문서상 가능 | 미확인 | 없음 | 제외 |
| num_cores_req | CPU 요청 | 문서상 가능 | 미확인 | 없음 | 제외 |
| requested_memory_mib | memory 요청 | 이 조사에서 불변성 증명 못함 | 미확인 | 없음 | 제외 |
| qos | QoS | 문서상 가능 | 미확인 | 없음 | 제외 |
| partition | partition | 문서상 가능 | 미확인 | 없음 | 제외 |
| account | allocation account | 문서상 가능 | 미확인 | 없음 | 제외 |
| user | submitting user hash | 수정 관측 없음; 해시 변환·원본 매핑 권한 미확인 | 미확인 | 없음 | 제외 |

[SchedMD scontrol](https://slurm.schedmd.com/scontrol.html)의 수정 명령은 scheduler 기능의 근거이며 이 7개 필드가 실제 Kestrel 각 행에서 변경됐다는 증거는 아니다. [sacct](https://slurm.schedmd.com/sacct.html)는 재큐잉 시 Submit이 재설정될 수 있다고 명시한다. 따라서 hour/weekday도 초기 제출 시각이라는 증거 없이 쓰지 않는다. 종료시각은 인과적 피처가 아니라 사용자 지정 end<cutoff 라벨 성숙 조건에만 쓴다. 수집 지연은 확인되지 않았다.

최종 피처는 자체 생성 constant_bias=1 하나, 작업별 피처는 0개다. 해당 값의 가용성만 TRUE다. GPU 기반 표본 선택·가중치·strata와 W0/B0/대기열은 과거 archive descriptor를 쓰는 연구 평가이며 최초 요청값으로 인증하지 않는다. 이 조건에서 총 실행시간의 무조건부 분포를 학습할 수는 있으나 개별 작업을 구별할 근거가 없다.
'''
    (ROOT/'REQUEST_VERSION_AUTHORITY_AUDIT_KO.md').write_text(source_notes,encoding='utf-8')
    qa=[
      ('walltime을 scheduling duration으로 쓰면 무엇이 문제인가?',f"실행시간과 다른 최대 요청값이다. April 예약/실제 GPUh는 {w.reservation_to_actual_GPUh:.3f}배, April2 늦은 코호트 요청/실제 중앙값은 {queue['late_requested_actual_ratio_median']:.3f}배였다. 이것만으로 ML 대체의 타당성이 증명되지는 않는다."),
      ('기존 기준 모델을 재현했는가?','예. 2025-03-14 08Z의 PENDING 총 실행시간 Q50/Q90와 저장 전처리를 로드하여 275행을 오차 0으로 재현했다. 원본 요청 버전 미검증으로 연구 comparator만 허용한다.'),
      ('어떤 총 실행시간 모델을 선택했는가?','M2 log1p LightGBM 상수 입력 기준선을 연구 후보로 선택했다. M1과 pinball 차이는 0.000152초 수준의 수치적 차이이며 실질적인 우월성 주장은 없다. M3는 walltime 역변환이 미검증 요청값을 요구하므로 제외했다. 운영 모델은 선택·승격하지 못했다.'),
      ('Q50/Q90의 의미는?',f"한 패키지의 무조건부 총 실행시간 분위수다. 최종 Q50={selection['calibrated_quantiles'][0]:.3f}초, Q90={selection['calibrated_quantiles'][1]:.0f}초(약 {selection['calibrated_quantiles'][1]/3600:.2f}시간). Q90 전역 보정값 {selection['calibration_delta_seconds']:.3f}초. 작업별 조건부 Q90라는 주장을 하지 않는다."),
      ('Q90이 보정됐는가?',f"아니오. DEV 원시 coverage 91.41%지만 독립 CAL_VALID {cv.Q90_coverage:.2%}, April {s.Q90_coverage:.2%}로 88–92% 게이트를 벗어났다. CAL_FIT 90.03%는 같은 표본의 보정 결과이므로 검증 통과로 쓰지 않는다."),
      ('high-GPU 보정은?',f"승인 불가. DEV 89건, CAL_VALID 6건으로 최소 100건 미달. April ≥16GPU {int(high.N)}건의 coverage {high.Q90_coverage:.2%}도 잠금 후 기술통계이며 사전 실패를 고칠 수 없다."),
      ('4시간 초과 작업 보정은?',f"실패. DEV 원시 61.74%, CAL_VALID 63.46%, April {long.Q90_coverage:.2%}; April GPU 가중 coverage {long.GPU_coverage:.2%}."),
      ('예약 과잉은 얼마나 남았는가?',f"April 예약/실제 GPUh {s.reservation_to_actual_GPUh:.3f}배. 총 초 단위 예측/실제 비율 {s.total_prediction_actual_ratio:.3f}배. 0초 50건은 개별 비율에서 제외하고 총량에서는 유지했다."),
      ('walltime보다 얼마나 작아졌는가?',f"April 전체 예약 GPUh 감소는 {(1-s.reservation_to_W0_GPUh):.2%}뿐으로 요구한 20% 이상 감소에 미달. April2 신규 코호트의 슬롯 예약은 {(1-q.iloc[1].reservation_GPUh/q.iloc[0].reservation_GPUh):.2%} 감소했지만 당일 시작은 악화됐다."),
      ('실행시간을 얼마나 자주 과소예측하는가?',f"April 작업 기준 {s.underprediction_rate:.2%}. 빈도는 낮아도 긴 overrun의 손실이 크므로 이를 단독 성공 지표로 보지 않는다."),
      ('GPU 가중 overrun은?',f"April GPU 요청수 가중 작업 비율 {s.GPU_weighted_overrun_job_fraction:.2%}, 초과 실행 {s.overrun_GPUh:,.1f} GPUh. checkpoint 가중 비율은 별도 분모로 {cp['GPU_weighted_overrun_checkpoint_fraction']:.2%}."),
      ('30분 체크포인트에서 단순 차감이 충분한가?',f"아니오. {cp['N']:,}개 checkpoint의 remaining MAE {cp['remaining_MAE_seconds']/3600:.2f}시간, >15/>30/>60분 분류 정확도 {cp['accuracy_gt_900s']:.2%}/{cp['accuracy_gt_1800s']:.2%}/{cp['accuracy_gt_3600s']:.2%}. 사전 게이트 실패."),
      ('OVERRUN에 얼마나 들어가는가?',f"작업 단위 {s.overrun_job_fraction:.2%}, 관측 체크포인트 단위 {cp['overrun_checkpoint_fraction']:.2%}. 체크포인트는 30분 이상 생존 작업 중심의 다른 모집단이다. OVERRUN 시 GPU 유지·STAY·매 제어 간격 예약 연장 테스트는 통과했다."),
      ('별도 remaining 모델이 필요한가?','INCONCLUSIVE. 실패한 무피처 TOTAL 모델의 차감 실패가 별도 시스템의 필수성을 입증하지 않는다. 먼저 원본 요청 권한과 유용한 TOTAL 예측 문제를 해결해야 한다.'),
      ('survival/AFT 개발을 피했는가?','예. 별도 remaining, survival, AFT, 신경망 모델을 학습하지 않았다.'),
      ('완전히 새 작업에 호출 가능한가?','예, 연구 모드에서. 별도 폴더·새 프로세스·빈 요청 피처·새 ID로 예측했다. 과거 행의 ID를 제거해도 같고 예측 lookup 캐시는 없다. 모든 작업이 같은 예측을 받는 것이 이 엄격 기준선의 한계다.'),
      ('온라인 재학습이 필요한가?','아니오. 모델 선택/보정 동결 후 TRAIN 동일 표본으로 Q50/Q90 각각 한 번 최종 fit하고 저장했다. 로더와 predict에는 학습 경로가 없다. Q50/Q90 두 booster는 한 Runtime 패키지다.'),
      ('CPU/GPU 어느 쪽이 빨랐는가?','동일 5만 행·4개 fit 작업에서 CPU 단일 0.351초, CPU4 2.147초, GPU 4.382초. 예측·지표 차이 0. CPU_SINGLE 선택. 상수 입력에는 유효 분할이 없어 프로세스 시작 비용이 지배적이며 일반적인 full-feature 모델 결과로 일반화하지 않는다.'),
      ('CPU 추론 지연은?',f"1,000회 API 호출 P50 {lat['single']['p50_ms']:.4f}ms, P95 {lat['single']['p95_ms']:.4f}ms, P99 {lat['single']['p99_ms']:.4f}ms, 최대 {lat['single']['max_ms']:.4f}ms. 배치10/100/1000 처리량은 INFERENCE_LATENCY.json 참조. GPU 불필요."),
      ('April start≥H가 얼마나 바뀌었는가?',f"정확 재현 W0 2,190/2,340 ({q.iloc[0].fraction_start_ge_H:.2%}) → 동결 Q90 2,340/2,340 (100%). 회복 0건, 당일 시작 150건 상실. 평균 대기시간은 {q.iloc[0].queue_mean_seconds/3600:.2f}→{q.iloc[1].queue_mean_seconds/3600:.2f}시간으로 줄어도 H 안의 시작은 악화된다. 기존 332건 배경 예약은 고정한 신규 도착 작업 개입이다."),
      ('V42로 넘길 준비가 됐는가?','아니오. callable/persisted 기술적 부분은 해결했지만 authorized/validated 모델이라는 핵심은 미해결이다. 기본 로더는 PermissionError로 차단하며 연구 모드만 명시적으로 허용한다. V42·CC4·MESS·IEEE/OpenDSS 및 optimizer를 수정하거나 실행하지 않았다.')]
    lines=['# Runtime-vNext6 최종 검토','', '**결론: 작업은 완료했지만 운영 승격은 거절한다. 원본 요청 버전 authority가 없으며, 이를 제외한 무피처 총 실행시간 기준선은 성능·대기열 게이트를 통과하지 못했다.**','',
      '요청한 엄격 피처 원칙을 적용했다. 불변 작업별 피처가 0개이므로 callable 연구 패키지를 성공적인 production predictor로 포장하지 않는다. 새 원본 로그가 확보되기 전에는 full-feature comparator를 운영으로 승격할 수 없다.','',
      '## 동결·표본·권한','',
      '- 논리적 학습 cutoff: 2025-03-14 08Z, 논리적 번들 as-of: 2025-03-31 08Z. 실제 파일 생성은 2026년 9월의 소급 실험이다.',
      '- TRAIN 222,182건(0초 111건), DEV 11,486 성숙/495 미성숙, CAL_FIT 5,438/498, CAL_VALID 14,623/13. September2024 이후 공개 partition 중 지정 end-window에 해당하는 표본이다.',
      '- April 51,499건 중 pre-May 성숙·유효 라벨 49,712건, 미해결/부적격 1,787건. May partition과 May 완료 라벨은 사용하지 않았다. 완료는 end/start가 있는 종료 기록이며 성공 상태 COMPLETED만을 의미하지 않는다.',
      '- 피처: constant_bias=1만 사용. 9개 요청 피처와 재큐잉에 민감한 submit hour/weekday 제외. 원본 요청 미검증 GPU는 연구 표본·가중치·strata에만 사용한다.',
      '- `SUBMISSION_TIME_FEATURES_STRICTLY_VERIFIED=TRUE`는 상수 입력만의 성질이다. `REQUEST_VERSION_AUTHORITY_FOUND=FALSE`, `STRICT_CAUSAL_RUNTIME_PROVIDER_READY=FALSE`다.',
      '- 선택·보정 동결 → 동일 TRAIN 최종 refit → standalone 호출/무학습/무캐시 검증 → 번들 hash 동결 → April 개방 순서를 보존했다. 모델은 April 이후 변경하지 않았다.','',
      '## 필수 질문 21개','']
    for i,(question,answer) in enumerate(qa,1):lines += [f'### {i}. {question}','',answer,'']
    lines+=['## 해석과 한계','',
      '`Q90(T|x)-elapsed`는 제출 시점 고정 잔여 proxy이며 `Q90(T-elapsed | T>elapsed,x)`와 다르다. 본 상수 모델은 x에 작업 정보를 갖지 않는다. 30분 checkpoint 결과도 May1 전에 종료된 작업의 생존 checkpoint에 한정되며, 긴 우측 검열 작업의 성능을 보증하지 않는다.','',
      '요청 walltime cap을 primary에 적용하지 않았다. 사후 연구 진단은 WALLTIME_CAP_DIAGNOSTIC.csv에 보존했다. 초기 strata의 최상위 requested bin은 >=4h이며 사용자 지정 >4h 경계를 정확히 따르는 보완표는 EXACT_REQUESTED_BUCKET_METRICS.csv에 있다. 실제 실행 >4h 게이트는 처음부터 엄격한 >4h다.','',
      '기본 reservation replay는 미래 실행 라벨을 읽기 전에 저장했다. 별도의 실행 스트레스 재생은 매 15분 완료 여부만 scheduler에 전달한다. OVERRUN에는 GPU를 유지했으며 W0/ML 각각 209/3,597회 연장, 두 경우 용량 위반 0이었다. 이 현재-slot dispatch 진단은 정확한 V42 controller 재생이 아니며, 예약 재생의 start≥H 비교와 섞지 않는다. 실제-duration 반사실 가정도 새로운 시스템에서 관측된 사실이 아니다.','',
      '기존 연구 파일 해시를 보존했다. 중간 Windows 한글 경로 로딩 오류는 Python 문자열 로딩으로 동결 전에 수정했고 실패 로그를 남겼다. 모델·데이터 결과를 수정하거나 실패 게이트를 낮추지 않았다.','',
      '## 산출물','',
      '- `RUNTIME_PROVIDER/`: Q50/Q90, 전처리·계약·해시·예제. 연구용 호출은 `RuntimeProvider(allow_research=True)`.',
      '- `REQUEST_VERSION_AUTHORITY_AUDIT_KO.md`: 필드별 원본성·수정·수집 근거.',
      '- `MODEL_SELECTION_FREEZE.json`, `PROVIDER_BUNDLE_FREEZE.json`: 선택과 모델 bytes 동결.',
      '- `MODEL_COMPARISON.csv`, `STRATIFIED_METRICS.csv`, `GPU_WEIGHTED_METRICS.csv`, `PAIRED_UNCERTAINTY.csv`: pre-April 비교.',
      '- `APRIL_LOCKED_RUNTIME_METRICS.csv`, `APRIL_WALLTIME_VS_ML_QUEUE_REPLAY.csv`, `CHECKPOINT_SUBTRACTION_DIAGNOSTIC.csv`: 잠금 평가.',
      '- `FINAL_VERDICT.json`, `DELIVERY_MANIFEST.json`: 최종 flag와 배달 검증.','']
    (ROOT/'FINAL_REVIEW_KO.md').write_text('\n'.join(lines),encoding='utf-8')
    print('FINAL_NEGATIVE_REVIEW_WRITTEN',flush=True)
if __name__=='__main__':main()
