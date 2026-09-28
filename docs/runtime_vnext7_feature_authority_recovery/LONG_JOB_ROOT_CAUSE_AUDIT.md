# pre-April 장기 작업 기술 감사

피처 권위 분류·계약 해시를 먼저 동결했다. 본 문서는 사용자 §10의 **라벨이 성숙한 아카이브 기술 통계**이며 인과적 피처 유용성·모델 선택 결과가 아니다. strict feature가 0개이므로 §9의 Spearman/MI, 범주별 예측 분산, walltime/runtime 양방향 비율은 수행하지 않았다. workflow runtime CV도 같은 권위 게이트로 보류하고 CSV에 결측 사유를 썼다. 그 대신 라벨과 무관한 토큰 반복·미관측률을 모두 보고한다.

|구간|mature GPU 행|>4h|장기 비율|≥16 GPU|≥16 GPU 중 >4h|
|---|---:|---:|---:|---:|---:|
|TRAIN|222,182|47,229|21.26%|3,607|442|
|DEV|12,002|2,643|22.02%|93|14|
|CAL_FIT|5,622|1,130|20.10%|10|2|
|CAL_VALID|18,640|464|2.49%|17|4|
|CAL|24,262|1,594|6.57%|27|6|
|ALL_MATURE|621,004|61,415|9.89%|30,437|677|


모집단은 아카이브에서 요청 GPU>0으로 기록된 모든 행이다. 기존 vNext6 학습용 필터나 April 평가 코호트와 동일하지 않다. 실제 실행 시간을 0초 이상으로 허용하고 terminal state로 성공 작업만 선별하지 않았다. 요청 GPU와 Submit 자체가 버전 미확정이므로 이 집단 역시 **소급적 descriptor 코호트**다. 전체 GPU 621,583행 중 621,004행이 label_valid다. end/start의 2025-04-01 이후 시각은 라벨 산술 전에 제거했다. April/May 2025 파티션 payload는 열지 않았다.

TRAIN은 end∈[2024-09-15 08:00Z,2025-03-14 08:00Z). DEV는 submit∈[03-15,03-23), end<03-23. CAL_FIT은 submit∈[03-23,03-27),end<03-27. CAL_VALID는 submit∈[03-27,03-31),end<03-31 08:00Z. CAL은 마지막 두 구간 합집합이다. ALL_MATURE는 전체 pre-April 성숙 라벨이며 TRAIN과 겹친다. cutoff 직전 제출 후 아직 끝나지 않은 장기 작업은 빠지므로 구간별 장기 비율의 차이는 workload shift와 maturity-selection을 구분할 수 없다.

TRAIN에서 단기/장기 작업의 기록 walltime 중앙값은 **6시간/36시간**, cores는 **4/8**, GPU는 **1/1**, nodes는 **1/1**이다. 범위 접미사가 없는 메모리 수치 중앙값은 **81,920/10,240 MiB**이며 범위를 확정하지 못해 total 또는 per-node로 해석하지 않는다. 개별 QoS/partition/account/user 빈도와 모든 수치 분위수는 `LONG_JOB_FEATURE_DIAGNOSTIC.csv`에 보존했다. 이 차이는 기록된 요청값의 연관성이다. 가장 강한 **제출 당시** 정보가 무엇인지는 확인할 수 없다.

TRAIN의 동일한 아카이브 요청 9개 값 조합은 3,372종이다. 단기와 장기가 함께 있는 조합은 551종, 해당 행은 150,595(67.78%)이고 장기 작업의 98.40%가 이 혼합 조합에 속한다. 표본 10개 이상 조합의 runtime CV 중앙값은 0.959, 양수 최소값 기준 max/min 중앙값은 약329다. ALL_MATURE에서도 장기 작업의 98.41%가 혼합 조합에 속한다. 넓은 내부 분산은 관측되지만 **분포의 통계적 heavy-tail 형태를 검정한 것은 아니며**, 원본 요청 동일성이나 불충분한 피처의 인과적 기여를 증명하지 않는다. script/업무 종류가 섞였을 수 있다.

장기 작업은 TRAIN47,229·DEV2,643·CAL1,594건으로 전체 수가 극소수인 문제는 아니다. 그러나 CAL_VALID 장기 비율은2.49%이고 TRAIN21.26%와 다르다. DEV/CAL의 ≥16 GPU 표본은93/27건, 그중 장기는14/6건뿐이다. 이 작은 수로 GPU·workflow별 보장 성능을 인증할 수 없다. `HIGH_GPU_SUPPORT_SUFFICIENT=FALSE`는 수치에 기반한 보수적 기술 판단이며 조정된 성능 임계값이 아니다.

TRAIN의 name/submitline/script/workdir 토큰별 중앙 표본은 모두1이다. script token의 DEV 미관측률은77.49%, CAL96.82%; name은57.22%/89.64%; workdir은88.59%/93.14%다. 단순 문자열 반복은 안정적 workflow identity나 온라인 재현성을 증명하지 않는다. `COHORT_CATEGORY_SUPPORT.csv.gz`는 모든 관측 category×role별 n/long_n/high_gpu_n/seen_in_train을 저장한다. 누락·미존재 범주는 별도 G 및 미지원 판정이며 의미를 생성하지 않았다.

원인 후보 A–F 판정:

- A: 아카이브에 정보가 전혀 없다는 결론은 부당하다. **검증된 작업별 피처가 0개**라는 제약은 확실하다.
- B: 원본 request/version 연결이 미확정이라는 provenance 문제가 있다. 실제 모든 값이 변경되거나 원본이 소실됐다는 비율은 추정 불가다.
- C: 전체 장기 표본은 많지만 highGPU 및 세부 category의 장기 validation은 희소하다.
- D: 동일 아카이브 요청 조합 안의 폭넓은 runtime 분산을 관측했다. 원본 클래스의 heavy-tail 인과 진단은 미확정이다.
- E: 구간별 분포·토큰 support가 다르다. 실제 workload 변화와 종료 cutoff에 따른 선택효과를 분리하지 못한다.
- F: provenance 제한, 내부 이질성, 희소 검증 표본, 분포 차이의 복합 위험이다. 이번 관측만으로 vNext6 실패의 기여율이나 주된 인과 원인을 추정하지 않는다.

`LONG_JOB_FEATURE_SEPARABILITY=INCONCLUSIVE`. 이번에는 예측기·분류기를 학습하지 않았으며 April 성능으로 후보를 고르지 않았다.
