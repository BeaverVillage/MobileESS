# V42 연구용 유연성 계약과 조건부 제어 — 한국어 최종 보고서

최종 Source c4b59fb3…에서 E1/E2 × FLEX20/30/40 × FIXED/GREEDY/GRID의 독립 Full96 조건부 이벤트 replay 18개를 완료했다. E0는 기존 strict 경로의 물리 실행 1회를 9개 비교 셀로 명시적으로 재사용했다. 따라서 비교 표 27셀은 27회의 독립 실행이 아니다.

주 사례 E1/FLEX30/GRID에서 DELAY 6건과 PREPLACE 56건이 실제 시뮬레이션에 연결됐다. 최종 causal R0보다 늦은 물리 시작은 8개 작업·8,100초이며, 이 중 PREPLACE는 2개다. 주 사례는 같은 C의 FIXED보다 완료 294개·Compute 88.042222 GPUh가 늘었고 GREEDY보다 선택 후보 Q50 최대 점수가 작았다. 그러나 FIXED의 Q50 점수는 GRID보다 더 작았으며, E0 대비 완료는 275개 줄고 이월·대기는 증가했다. 행동 연결을 모든 계통·서비스 성능의 개선으로 표현하지 않는다.

18개에서 GPU 용량 위반·작업 삭제·비공개 미래 제어 읽기·실행 의도 예산 위반은 0이었다. 실현 서비스량은 보존됐지만 미시작 계약 초과 위험과 CDF 하한 부족이 남았다. 새 A/M Optimize와 Fresh AC는 NOT_RUN이고, Actual 최대 선로부하율과 실제 전기적 위반 수는 NULL이다. 31일 캠페인 및 B2/B3 M HOLD는 유지한다.

## 1. 기존 제어표가 지나치게 보수적이었던 직접 원인은 무엇인가?

V5 May01의 5,816개 제어 사건은 예측 GPU 지원 범위와 실제 관측값의 차이 때문에 5,763회, 일말 지원 경계 때문에 53회 거부됐다. 소스 분기와 전 사건 원장상 select/select_migration에 도달하지 않았다. 타이밍 카운터 0과 이 분기 재구성 근거를 구분한다. 독립적으로 엄격 TRAIN 요청 Provenance 표본이 0이었고, May01 원시 활성 작업 2,320개 모두 QoS·보호·Batch 권한이 미확인이므로 E0 추가 예산은 0이었다.

오프라인 4,392개 후보는 익명 기준 서비스 지원 부족 3,111개, 자원 envelope 거부 972개, 실제 점수 평가 309개로 나뉜다. 309개 중 Q50 Hard 통과는 112개였으나 A2의 Q90 추가 수요 목표를 고정 물리 점유처럼 모두 더하는 검사에서는 승인 0개였다. 원본 A-stage 모델이 실패한 것이 아니라 제어표에서 수요 목표·실현 점유·행동 권한을 과도하게 결합한 것이었다.

최종 C 주 사례는 동적 bounded 선택 진입 128,414건으로 연결됐다. 남은 거부는 원본 현재 affine 전압 guard 1,109,293 occurrences와 실제 자원 부족 181,139 occurrences가 주도한다. 이는 반복 후보의 거부 이유 수이지 고유 Job 수나 신규 Fresh AC 위반 수가 아니다. 예측 불일치의 일괄 veto를 제거해도 현재 물리 guard는 유지한다.

## 2. 수정된 구현 오류는 무엇인가?

PR224는 zero-delay Pre-placement까지 Batch 지연 권한으로 막던 조건과 이미 지난 슬롯의 자원 초과로 현재 후보를 거부하던 조건을 수정했다. source_site가 없어도 명시적인 PREPLACE 행동에는 명시적 placement 권한을 요구하도록 보강했다. 완료된 최소 구현 수정이며 C 연구 계약과 구분한다.

별도 PR225(D)는 원본 A2 Q50의 서비스 x·site GPU·carry를 재사용하고 Q90−Q50 추가분만 TRAIN CDF 아래 물리 recourse로 처리한다. 원본 A-stage P1 목적과 서비스 타이밍 모델을 변경하지 않았다.

C는 새 연구 QoS 계약, 관측 상태별 실제 예약 검사, 분리된 능력(TimeShift/Preplace/Checkpoint Migration), 고정 최초 R0와 불변 예산을 새 모듈로 구현했다. 늦게 나타난 block으로 이미 만료된 창을 소급 갱신하지 않으며, 제때 관측한 연속 물리 block 증거는 보존한다. 스냅샷은 R0/증거/소비량을 기록하고 E1/E2 이어 실행은 상태 변경 전 명시적으로 거부한다.

성능 공학 변경은 캐시 키의 완전한 수치·자원 입력을 사용하고 원본 예약 fit을 그대로 호출한다. 변경 전후 동일 입력 2슬롯의 canonical 행동 및 GPU/Compute/IT/PCC P/Q SHA는 동일했다. Source4a의 30/96슬롯 성능 탐색 중단과 Sourceaac의 2슬롯 검증은 최종 Full96 결과에서 제외하고 원본을 보존했다.

## 3. Q90을 Queue/Carry-over로 처리한 결과는 무엇인가?

원본 시간별 Q50 총합은 5,503.441472 GPUh이다. 동결 A2 nominal은 3,225.157483 GPUh를 서비스하고 2,278.283989 GPUh를 carry로 보존한다. 시간별 Q90 합 24,408.063227 GPUh는 24개 한계 분위수의 합이며 하루 총수요의 Q90은 아니다. 추가분 Q90−Q50은 18,904.621755 GPUh다.

검증된 공통 D 기준 recourse는 추가분 3,848.076403 GPUh를 서비스하고 15,056.545352 GPUh를 carry로 보존했다. Nominal carry를 포함한 미완료량은 17,334.829341 GPUh다. 질량 오차 약 3.64e−12 GPUh, CDF 상한 위반 0이며, CDF 하한 부족은 1,057개 관측·791.699451 GPUh로 남는다. 이를 정상 완료나 Job별 QoS 증명으로 표시하지 않는다.

C 18개는 선택 Q90 후보의 질량·물리 Hard 검사를 통과했다. 사례별 선택 후보의 최대 미완료량은 17,334.829341~17,335.329341 GPUh였다. 주 사례의 최대는 17,334.938138 GPUh이며 선택 Q90 기록 9,427건 모두 LOWER_BOUND_UNMET 위험이다. Q90은 실제 익명 GPU 점유가 아니라 같은 full-day aggregate counterfactual이며 Actual 제출 차감·개별 Job 실행과 별도다.

A2의 약 18,904 GPUh reserve 목표와 achieved reserve 0을 혼동하지 않는다. 원본 P1/FULL은 shortfall을 허용하므로 목표는 capacity-backed reserve 증명이 아니다. Kernel은 예측 reference이고 고정 실제 서비스 시각이 아니며, 원본 Q10/Q90 CDF 누적 하한·상한과 cohort mass/carry를 재사용한다. Q90을 clipping하거나 버리거나 미래 UID로 생성하지 않는다.

## 4. E0/E1/E2의 실제 유연 Job 수는 얼마인가?

활성 2,320개는 Known 1,546개 + 관측 Unknown 774개(prefix 78개·당일 제출 696개)다. Known 최초 issue 영수증 1,649개에는 과거 완료 103개가 별도로 남는다. 아래는 계약 참여·양수 예산 수이며 실행 성공 수가 아니다.

| 정책 | FLEX | 활성 Known | 활성 Unknown | 양수 예산 합계 | 활성 Job 참여율 | 전체 Nominal GPUh 중 참여율 | 전체 발행 양수 영수증 |
|---|---|---:|---:|---:|---:|---:|---:|
| E0 | 20/30/40 | 0 | 0 | 0 | 0% | 0% | 0 |
| E1/E2 | 20 | 317 | 140 | 457 | 19.6983% | 18.0935% | 482 |
| E1/E2 | 30 | 456 | 218 | 674 | 29.0517% | 25.1688% | 708 |
| E1/E2 | 40 | 597 | 293 | 890 | 38.3621% | 32.4932% | 938 |

Nominal GPUh는 source GPU gang × 총 Q50 시간이며 실제 잔여 서비스·Actual Compute가 아니다. UID/관측 episode(없으면 UID fallback)와 사전 동결 Seed의 SHA256 임계값으로 참여를 결정한다. FLEX20⊆30⊆40이고 정확한 사후 quota나 계통 성능 기반 재선택은 없다. Known은 최초 issue, Unknown은 공개 submit 시점에 같은 산식을 사용하며 Planning Unknown 영수증 발행은 0이다.

## 5. Normal/Standby 연구 계약의 적용 범위는 무엇인가?

| 정책 | Normal Batch | Source 확인 Standby Batch | High/Urgent/Protected·명시적 nonbatch |
|---|---:|---:|---:|
| E0 | 기존 확인 Source 권한만 | 기존 확인 Source 권한만 | 기존 보호 유지 |
| E1 | 추가 최대 30분 | 추가 최대 60분 | 추가 지연 0 |
| E2 | 추가 최대 60분 | 추가 최대 120분 | 추가 지연 0 |

May01 활성 원시 QoS는 모두 UNCONFIRMED이고 protected/batch는 미확인이다. 연구 모델은 ASSUMED_NORMAL_BATCH를 원시 필드와 별도로 두고 선택 집단에만 양수 예산을 부여한다. 따라서 이번 May 비교의 실제 계약 상한은 E1 1,800초·E2 3,600초다. Standby 60/120분은 확인된 Standby 입력 및 독립 fixture에서 검증한 범위이며 원래 Planning의 Standby 라벨을 관측 요청으로 승격하지 않는다.

30/60/120분은 승인된 연구 상한이지 Kestrel 고객 SLA가 아니다. E2의 7,200초는 새 계약·새 Case의 명시적 상한이며 기존 strict issuer를 수정하지 않는다. 확인된 보호·High/Urgent·명시적 nonbatch는 가정으로 덮어쓰지 않는다. 원시 정보 미확인은 관측된 비보호 상태를 뜻하지 않는다.

## 6. Pre-placement와 Migration은 몇 개 후보에서 가능해졌는가?

Phase A의 참여 집단에서 초기 대기 placement/당시 Running checkpoint 자격은 FLEX20 425/32개, FLEX30 630/44개, FLEX40 831/59개였다. 이후 상태 전환 시 같은 불변 계약으로 자격을 검사하므로 초기 자격 수가 하루 전체 Migration 후보 수는 아니다. 원본 모델의 독립적인 zero-delay placement 권한 1,245개도 보존한다.

아래 후보는 반복 이벤트의 발생 수다. 생성, 점수 평가, Q50 Hard 통과, 알고리즘 승인, 선택 성공을 구분한다. FIXED는 Hard 통과 후보 중 reference action만 허용하므로 Hard 통과 수와 승인 수가 다를 수 있다. 조회된 고유 UID는 모든 18개에서 2,312개다.

| 사례 | 생성 후보 | 점수 평가 | Q50 Hard 통과 | 알고리즘 승인 | 선택 성공 이벤트 |
|---|---:|---:|---:|---:|---:|
| E1/F20/FIXED | 1361260 | 114359 | 15137 | 9936 | 9936 |
| E1/F20/GREEDY | 1203884 | 91346 | 10625 | 10625 | 9154 |
| E1/F20/GRID | 1175592 | 83054 | 9635 | 9635 | 8912 |
| E1/F30/FIXED | 1645826 | 150241 | 17367 | 10180 | 10180 |
| E1/F30/GREEDY | 1418088 | 116543 | 11354 | 11354 | 9604 |
| E1/F30/GRID | 1387984 | 104111 | 10420 | 10420 | 9427 |
| E1/F40/FIXED | 1921333 | 186384 | 20168 | 10445 | 10445 |
| E1/F40/GREEDY | 1601292 | 133734 | 11434 | 11434 | 9684 |
| E1/F40/GRID | 1570154 | 124582 | 11228 | 11228 | 9803 |
| E2/F20/FIXED | 1845833 | 186436 | 17299 | 9936 | 9936 |
| E2/F20/GREEDY | 1629513 | 157124 | 11670 | 11670 | 9354 |
| E2/F20/GRID | 1569982 | 135446 | 10628 | 10628 | 9472 |
| E2/F30/FIXED | 2369007 | 257029 | 20550 | 10180 | 10180 |
| E2/F30/GREEDY | 2058362 | 214179 | 12976 | 12976 | 9929 |
| E2/F30/GRID | 1958874 | 177232 | 10814 | 10814 | 9294 |
| E2/F40/FIXED | 2876869 | 327473 | 24690 | 10445 | 10445 |
| E2/F40/GREEDY | 2444164 | 265006 | 13612 | 13612 | 9971 |
| E2/F40/GRID | 2313930 | 220534 | 12020 | 12020 | 9746 |

주 사례 PREPLACE는 생성 1,246,652 → 평가 88,454 → Q50 Hard 승인 903 → 선택 181 → 실제 실행 56건이다. MIGRATE는 생성 2,630 → 평가 1,612 → Q50 Hard 승인·선택·실행 0건이다. 점수 평가만으로 행동 승인을 주장하지 않는다. EXPLICIT_NONZERO_PHYSICAL_PACKET_REQUIRED 15,144건은 참여/행동 권한과 packet 조건을 공유하는 reason이므로 전부 packet 누락으로 해석하지 않는다.

원본 GPU 780·whole-gang·rack/site 호환성·WAN route/link/global 동시성·checkpoint 1,800초·최대 1회 Migration·source/destination hold·양수 payload/transfer/restart·서비스 보존을 유지한다. 관측하지 않은 checkpoint 지원과 hold protocol은 명시적 실험 가정이다.

## 7. 실제 May01에서 선택·실행된 유연 행동은 몇 개인가?

표는 실제 May01 공개 이벤트를 사용한 counterfactual 시뮬레이션의 물리 실행이다. 실제 고객 데이터센터에서 이동을 수행했다는 뜻이 아니다. START/DELAY/PREPLACE는 최종 명령 라벨이며 사이트·시각을 함께 바꾼 경우 PREPLACE가 DELAY보다 우선한다. 마지막 열은 라벨과 별도로 실제 시작−최종 causal R0가 양수인 작업 수다.

| 사례 | START | DELAY | PREPLACE | MIGRATE | 완료 | 이월 | Compute GPUh | 최종 R0 이후 시작 작업 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| E1/F20/FIXED | 1334 | 0 | 0 | 0 | 1121 | 1199 | 14560.744722 | 0 |
| E1/F20/GREEDY | 1628 | 0 | 40 | 0 | 1397 | 923 | 14605.531667 | 0 |
| E1/F20/GRID | 1574 | 0 | 55 | 0 | 1414 | 906 | 14608.342222 | 0 |
| E1/F30/FIXED | 1334 | 0 | 0 | 0 | 1121 | 1199 | 14560.744722 | 0 |
| E1/F30/GREEDY | 1634 | 0 | 37 | 1 | 1415 | 905 | 14642.915278 | 2 |
| E1/F30/GRID | 1604 | 6 | 56 | 0 | 1415 | 905 | 14648.786944 | 8 |
| E1/F40/FIXED | 1334 | 0 | 0 | 0 | 1121 | 1199 | 14560.744722 | 0 |
| E1/F40/GREEDY | 1635 | 0 | 43 | 0 | 1432 | 888 | 14648.250833 | 0 |
| E1/F40/GRID | 1623 | 2 | 66 | 0 | 1446 | 874 | 14655.466667 | 5 |
| E2/F20/FIXED | 1334 | 0 | 0 | 0 | 1121 | 1199 | 14560.744722 | 0 |
| E2/F20/GREEDY | 1665 | 8 | 41 | 0 | 1447 | 873 | 14627.294722 | 8 |
| E2/F20/GRID | 1617 | 0 | 68 | 0 | 1419 | 901 | 14659.957778 | 1 |
| E2/F30/FIXED | 1334 | 0 | 0 | 0 | 1121 | 1199 | 14560.744722 | 0 |
| E2/F30/GREEDY | 1637 | 10 | 39 | 1 | 1414 | 906 | 14652.685833 | 11 |
| E2/F30/GRID | 1568 | 9 | 66 | 0 | 1391 | 929 | 14629.476389 | 9 |
| E2/F40/FIXED | 1334 | 0 | 0 | 0 | 1121 | 1199 | 14560.744722 | 0 |
| E2/F40/GREEDY | 1651 | 12 | 41 | 1 | 1430 | 890 | 14639.357500 | 14 |
| E2/F40/GRID | 1645 | 3 | 61 | 0 | 1477 | 843 | 14624.555278 | 4 |

주 사례의 실제 새 시작 1,666 = START 1,604 + DELAY 6 + PREPLACE 56이다. 물리 시작−최종 R0가 양수인 작업은 8개, 그중 PREPLACE 2개, 합계 8,100초였다. 누적 양수 차감 의무를 가진 시작 작업 170개·PREPLACE 15개·298,800초는 이전 취소/재기준 명령의 의무를 포함하므로 이 물리 지연 수와 다르다. 전체 차감 의무 360,000초 = 시작 작업 298,800 + 미시작 61,200초다.

Migration은 E1/FLEX30/GREEDY, E2/FLEX30/GREEDY, E2/FLEX40/GREEDY에서 각각 1건 실행됐다. 이는 같은 원시 UID 8729886의 서로 독립적인 정책 실행 3건이며 서로 다른 원시 Job 3개라고 계산하지 않는다. 각 실행은 80 GB engineering payload와 1,800초 중단을 포함한다. 독립 첫 Migration 감사는 checkpoint→transfer→restart→compute 재개의 단계, source/destination 중복 compute 없음, Q50 overrun 후 실제 서비스 지속, CC4 차감 1회를 확인했다. Source의 restart 300초와 연구의 보수적 900초를 구분하며 WAN/checkpoint I/O energy는 NULL(미모델링)이지 0이 아니다.

전체 상세 사건 2,359,317행은 별도 EVENT_DETAIL과 SHA로 보존했고 필수 Funnel은 18개 사례 집계로 정확히 재조정했다. 이 행 수를 고유 Job 수나 실제 실행된 행동 수로 사용하지 않는다.

## 8. QoS 및 물리적 제약을 위반하지 않았는가?

18개 모두 GPU 용량 위반·작업 삭제·비공개 미래 제어 읽기·실행된 의도 예산 초과는 0이었다. 원본 예약/whole-gang/rack/WAN guard를 사용했고 실현 Compute + 실제 terminal remaining 질량 오차 최대는 3.46e−11 GPUh였다. 제출된 당일 Unknown 696개는 각각 CC4를 1회만 차감했으며 prefix 78개는 당일 제출 차감과 중복되지 않는다. 161개 focused 테스트와 독립 실행 SHA/배열/서비스 감사를 보존한다.

주 사례의 324개 초기 Running + 1,666개 새 물리 시작 + 330개 미시작 = 2,320개다. 전체 미시작 330개 중 first-R0 위험 원장에 들어간 것은 318개이며 그 안의 양수 계약 overdue는 55개다. 나머지 12개는 최초 R0가 없다: 9개는 NO_PHYSICAL_CAUSAL_REFERENCE, 3개는 마지막 제어 후 제출로 조회 0이다. 이 중 양수 B 4개도 R0가 없어 overdue 판정은 NULL이다. 318을 전체 미시작 수라고 표현한 초기 설명은 amended V2에서 정정했으며 원래 V1 bytes는 보존한다.

실제 시작은 고정 연구 창 안에 있었고 주 사례의 창 누락/창 밖 늦은 시작은 0이었다. 창 만료 후 Queue를 유지한 사건 4,307건·287개 UID, 양수 미시작 overdue 55개를 숨기지 않는다. 전 사례의 양수 overdue는 20~89개다. 실행 예산을 넘지 않았다는 사실은 전체 연구 계약·관측 SLA가 모두 충족됐다는 뜻이 아니다.

주 사례 R0 갱신 86,626건(현재 grid-required 83,702·관측 자원 2,924)은 due/관측 clock·deadline·물리 증거·불변 예산·미환불 검사를 통과했다. 일반 Queue 대기, 의도 차감 부담, grid/resource-required 대기는 별도다. Source-confirmed 보호/High/Urgent/nonbatch는 0개여서 May 보호집단 실증은 공집합이다. 보호 보존은 fixture·정책 검사 근거이며 미확인 원시 정보를 관측 SLA로 바꾸지 않는다.

현재 Original affine 전압 거부 및 DD00 affine 최소 약 0.949120185는 동결 선형 모델의 guard 진단이다. 신규 Fresh AC 위반이나 PR223 기존 Fresh AC PASS의 재결함으로 승격하지 않는다. 선택 후보 Q50/Q90 전기적 검사는 같은 Original signed coefficients/정격을 사용하지만 실제 Actual 전압·전류·변압기 위반 수와 최대 선로부하율은 NULL이며 새 Fresh AC 인증은 없다.

## 9. 기존 Greedy/FIXED 대비 계통 성능이 개선됐는가?

균일한 개선은 아니다. 아래 Q50 값은 각 실행에서 선택한 후보 프로파일의 최대 signed affine 점수다. 실제 합성된 Actual 궤적의 AC 최대값이 아니며 FIXED가 적은 작업을 시작하면 점수가 더 낮을 수 있다. GRID의 후보 순위는 Q50 전체 남은 구간 peak 우선, 동률일 때 Q90 queue/carry/grid 위험, 이어 적은 이동·지연이다. 원본 A-stage P2 목적함수가 아니다.

| 정책/FLEX | FIXED Q50 점수 | GREEDY Q50 점수 | GRID Q50 점수 | GRID−FIXED 완료 | GRID−FIXED Compute GPUh | GRID D-day 대기초 |
|---|---:|---:|---:|---:|---:|---:|
| E1/FLEX20 | 0.641265991603 | 0.641691744110 | 0.642764079970 | 293 | 47.597500 | 96527392 |
| E1/FLEX30 | 0.641265991603 | 0.642763952704 | 0.641691744064 | 294 | 88.042222 | 95378092 |
| E1/FLEX40 | 0.641265991603 | 0.642014568258 | 0.642764079970 | 325 | 94.721944 | 95162992 |
| E2/FLEX20 | 0.641265991603 | 0.642435822521 | 0.642763952704 | 298 | 99.213056 | 95975692 |
| E2/FLEX30 | 0.641265991603 | 0.642763952704 | 0.642022138572 | 270 | 68.731667 | 95786692 |
| E2/FLEX40 | 0.641265991603 | 0.642763952704 | 0.642764079970 | 356 | 63.810556 | 95046892 |

주 사례 GRID는 동일 FLEX30 GREEDY보다 선택 Q50 최대가 0.642763952704→0.641691744064로 작고 완료 1,415개는 같으며 Compute는 약 5.871667 GPUh 많다. 동일 FIXED는 Q50 0.641265991603으로 더 낮지만 완료는 1,121개·Compute 14,560.744722 GPUh였다. GRID는 FIXED보다 완료 294개 늘고 이월 294개 줄었으며 D-day 대기는 107,004,292→95,378,092초로 줄었다. 낮은 점수·높은 처리량을 동시에 모든 알고리즘에 대해 보장하지 않는다.

E1/FLEX30/GRID와 E2/FLEX30/GRID는 1,415→1,391개 완료, 905→929개 이월, Q50 0.641691744064→0.642022138572였다. 큰 상한이 항상 개선으로 이어지지 않는다. E2 GRID의 완료는 FLEX20/30/40에서 1,419/1,391/1,477개로 참여율 효과도 비단조적이다. E1/FLEX20 및 FLEX40에서는 GREEDY가 GRID보다 선택 Q50 최대가 작아 GRID의 전반 우월성을 주장할 수 없다.

E0는 완료 1,690개·이월 630개·Compute 17,210.680000 GPUh·D-day 대기 54,968,092초였다. 주 사례는 완료 275개 감소·이월 275개 증가·Compute 2,561.893056 GPUh 감소·D-day 대기 40,410,000초 증가가 있다. E0의 legacy forecast guard와 Known commands, 새 C의 conditional selector/current-grid 경로가 다르므로 이를 순수 계약 상한 효과만으로 귀속하지 않는다. 알고리즘 효과는 동일 C 내부의 FIXED/GREEDY/GRID 비교로 분리한다.

D-day 대기는 공개 submit/start/dayEnd의 max/min으로 계산하고 초기 Running 324개를 제외한다. 과거 issue 이전을 포함한 주 사례 총 대기 373,039,315초와 D-day 대기 95,378,092초를 혼동하지 않으며 의도 지연으로 등치하지 않는다.

## 10. 그 결과는 Fixture인가, Offline Replay인가, 실제 Full96 검증인가?

Phase A는 실제 source와 original Native local domain을 읽은 Native0 감사이고, 작은 fixture는 보호·placement·예산·물리 Migration·만료 경계를 검증한다. 최종 18개는 실제 May01 공개 이벤트를 사용해 00:00~24:00의 96슬롯을 실행한 fixed A2/M2 counterfactual Actual replay다. 실행 행동·점유·Compute·IT·PCC P/Q는 재계산했고 Planning power를 복사하지 않았다.

새 E1/E2 Known 도메인을 Optimize한 A1/M1/A2/M2 증명은 아니다. 과거 A/M FULL·UB·LB·Gap을 새로운 문제로 이전하지 않는다. 온라인 global MILP 0, 새 Native Optimize 0, Fresh AC NOT_RUN이며 Actual 최대 선로부하율·AC 개선은 NULL이다. B2/B3 M와 31일 캠페인은 HOLD이고 공유 Solver 원장을 초기화하지 않았다.

주 사례 프로그램 구성 16.357711초는 첫 process의 lazy source 준비를 포함하며 solver compilation이 아니다. event engine 928.320644초, 구성/감사/직렬화를 포함한 writer wall 1,011.555768초를 구분한다. 주 사례 선택 median 약 0.6162 ms·P95 약 14.2186 ms다. 18개 engine wall은 822.099216~2,973.972161초이며 동시 CPU worker 측정이므로 고립된 solver 성능과 비교하지 않는다.

Source4a 성능 탐색은 30/96슬롯에서 중단돼 최종 결과가 없다. Sourceaac는 동일 입력 2슬롯 cache 동등성 검증으로 engine 39.235→10.894초(약 3.60배), 준비를 포함한 wall 57.502→29.021초였다. 동작/배열 SHA는 동일하며 이 측정은 Full96 속도 개선의 증거가 아니다. 두 epoch는 audit/performance에 그대로 보존했고 최종 Sourcec4b와 분리했다.

## 11. 새 연구 정책으로 변경된 Source/Case SHA는 무엇인가?

| 근거 | 정확한 식별자 |
|---|---|
| PR223 보존 head | 8f0ea6e8f97147bb425530e8d787ca89f4a05053 |
| PR224 최소 구현 수정 head | c6f1a0f41164b7da4afe406dd692abd583a29d1e |
| 공유 D PR225 head | 97da5c097f0eefc30a057c51378676c6402138c8 |
| D Source | fe2d882b3db6c43422436e4ea0f5dbd7f7bd1462298389031e18384293d3f0f5 |
| 최종 C Source | c4b59fb3898da7f3bed6b3b6818890165c74f7f1f90e4cd2470fa3abd5c56c0a |
| E1/FLEX30/GRID Case | 1918c86e27831476f67916512e9ba3d068f4c0258517dc429383e1c16331fa52 |
| E1/FLEX30/GRID Policy | a7b7095782d0272572a43d9fe368e7c7d72b6918ba346890e8f3d64ec3fd3266 |
| E1/FLEX30/GRID result gzip SHA | 94df773347a51dc3ca5de18d91b5e206ddc6e2cecdd7bd6cd395d1b8a5ead53f |
| 사전 등록 canonical 내용 SHA | 4ac5f4bdb57665a400eb17c3af98525380157607c34c185bed899b20e3ca3e98 |
| PREREGISTRATION.json 파일 byte SHA | f2c0acbb067bb038a8fa9ac8480696fe4858d5fedc340e84634127cf61bc80c9 |
| 실행 code 무손실 archive byte SHA | 0f58a5967266a2c78d7de199f65a88b0ed8eecfb4d1896a0bb47eb4fde36d0f9 |

Seed는 V42_EXPERIMENTAL_FLEXIBLE_QOS_CONTROL_V1::PARTICIPATION_PREREGISTERED_20261014_01이다. 최종 18개 Case/Policy/result/physics bindings는 CASE_MANIFEST와 각 EXECUTION_RECEIPT 및 independent validation에 각각 고정·검증됐다. Phase A preview Case와 최종 replay Case를 동일시하지 않는다. C는 명시적 연구 가정 변경이며 PR224의 버그 수정과 별도 계보다.

사전 등록 canonical 내용 hash는 preregistration_sha 필드만 제외한 sorted compact UTF-8 JSON의 hash이며, 파일 byte hash는 self-hash 필드와 줄바꿈을 포함한다. 두 값은 독립 재계산으로 확인됐고 Seed·상한·참여 규칙 변경을 뜻하지 않는다. 실행 Source SHA는 실행 시 파일 bytes에 묶인다. archive의 1,799개 파일은 실행 manifest와 모두 byte 동일하고 변경 source/test 9개도 Git index와 byte 동일하다. 이전 계보의 641개 파일은 checkout CRLF와 Git LF 차이가 있어 전체 index의 raw byte 동일성을 주장하지 않는다. 재현에는 audit/EXECUTED_SOURCE_BYTES.tar.gz의 무손실 code archive를 사용하고 Git commit의 버전 계보와 구분한다. 외부 모델·입력 자료는 각각의 source receipt와 SHA로 별도 결합한다. EOL·문서 포맷 차이를 수치 정책 변경으로 간주하거나 Git checkout만으로 실행 byte 동일성을 자동 주장하지 않는다.

중단 Source4a13796f69a39dc8b7e5c6159747a402561ec5661f0edda9cbfadef35d7a6bff 및 당시 주 Caseee2e65c5…는 superseded performance probe다. Sourceaac397455fc3344efb61016ef4fcede668437fa490852c46fab74d4df9d04c0a는 partial engineering validation이다. 과거 실행 영수증은 소급 교체하지 않는다. 최종 C Git commit/PR 식별자는 부모 제출 영수증에서 별도로 기록하며 기존 SHA를 재사용하지 않는다.

## 12. 논문에서 관측 데이터와 연구용 가정을 어떻게 구분해야 하는가?

관측 데이터는 Kestrel 공개 submit/start/상태·GPU gang이다. 동결 runtime Q50와 CC4 시간별 분위수는 source-verified 모델 예측이지 실제 완료시간·관측 SLA가 아니다. TRAIN CDF, source 전력/열/WAN 모델, 날씨를 각각 별도 근거로 기록한다. 실제 잔여 service/completion은 private Environment에만 두며 제어 입력·참여 선택·Planning Unknown UID 생성에 사용하지 않는다.

연구 가정은 IEEE123와 12개 합성 AIDC, 승인된 초기 site/queue 모델, ASSUMED_NORMAL_BATCH, 해시 참여, 추가 30/60/120분 계약, checkpointable/hold protocol, source engineering 80 GB/GPU payload와 보수적 restart 900초다. 실제 Kestrel 고객 지리·계약·이동 가능성·관측 유연성 비율로 표현하지 않는다. 실제 Migration 수는 counterfactual 시뮬레이션에 실행된 수이고 80 GB는 관측 checkpoint payload가 아니다.

Q90 익명 GPUh recourse는 cohort CDF 아래 집계 위험 근사이며 미래 개별 UID·whole-gang 스케줄·Job별 QoS의 정확한 증명이 아니다. CDF 부족, 미완료량, Queue, 미시작 overdue와 미모델링 WAN/I/O energy를 공개한다. 집계 recourse를 실제 Q90 점유나 Actual에서 이미 서비스한 forecast backlog로 표현하지 않는다.

원시 QoS와 모델 QoS, 계약 참여와 실제 행동, persistent 차감 의무와 최종 R0 물리 지연, 후보 예측 점수와 Actual AC, 실제 이벤트 replay와 새 A/M 최적화, 최소 구현 수정과 연구 가정 변경을 별도 열·원장으로 제시한다. 본 결과는 행동 연결과 처리량/계통 점수의 교환 관계를 보여 주며 일률적 개선이나 전체 SLA/AC 안전성을 주장하지 않는다.

## 최종 근거 파일

- audit/qos/QOS_PHASE_A_ARTIFACT_MANIFEST.json
- audit/qos/E0_E1_E2_POLICY_MANIFEST.json 및 KNOWN_UNKNOWN_POLICY_EQUIVALENCE.json
- audit/SOURCE_FREEZE_C.json 및 PREREGISTRATION.json
- audit/control/FINAL_FLEX_COMPARISON/CASE_MANIFEST.json 및 COMPARISON_DETAIL.json
- audit/control/FINAL_E0_STRICT_BASELINE_FULL96/E0_EXECUTION_RECEIPT.json, CONDITIONAL_ACTUAL_RESULT.json.gz, RETROSPECTIVE_SERVICE_MASS.json
- 각 사례 EXECUTION_RECEIPT.json, CONDITIONAL_ACTUAL_RESULT.json.gz, ACTUAL_PHYSICAL_ARRAYS.npz
- audit/POLICY_E0_E1_E2_COMPARISON.csv 및 POLICY_GRID_GREEDY_FIXED_ABLATION.json
- audit/CONTROL_POLICY_CANDIDATE_FUNNEL.csv, EVENT_DETAIL, RECONCILIATION.json
- audit/independent_review/C_COMPLETED_CASE_VALIDATION.json
- audit/independent_review/PREREGISTRATION_HASH_SCOPE_AUDIT.json
- audit/EXECUTED_SOURCE_BYTES.tar.gz, GIT_STAGED_SOURCE_BYTE_VERIFICATION.json, independent_review/C_EXECUTED_SOURCE_ARCHIVE_REVIEW.json
- audit/control/FIRST_E1_FLEX30_GRID_CONTROL_INDEPENDENT_AUDIT_AMENDED_V2.json (V1 preserved)
- audit/control/FIRST_REAL_MIGRATION_INDEPENDENT_AUDIT.json
- audit/independent_review/IMMUTABLE_QOS_R0_REVIEW.json 및 current-grid chain 전후 증거
- audit/performance/EPOCH03_PRECACHE와 EPOCH04_EXACT_CACHE_PREFIX
- 공유 D의 original CC4/24→96 service binding/CDF recourse 및 source-only final evidence

최종 집계·패키징 단계에서는 추가 실행 없이 기존 18개 완료 영수증을 읽어 보고서를 완성했다. 생산 소스·원시 입력·과거 결과·원래 실행 원장은 수정하지 않았으며 이 집계 단계에서 추가 replay·Native·AC를 수행하지 않았다.
