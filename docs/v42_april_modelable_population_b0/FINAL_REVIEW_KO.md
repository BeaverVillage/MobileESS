# April current V42 modelable population 및 B0 input gate

PR122 exact head를 보존하고 physical population rule을 결과 조회 전에 freeze했다.
Raw unique 71,093, modelable 54,492,
unmodelable 16,601; modelable fraction 76.64889652%.
GPU request 누락을 숫자로 채우지 않았으며 모든 제외 event를 ledger에 보존했다.
GPUh coverage는 NOT_IDENTIFIABLE_FROM_SOURCE이다.

30일 current Runtime source fields / April CC4 date binding / April weather C1 계수는 준비했다.
이는 실행 가능한 Planning/Actual physical bundle 30개가 완성되었다는 뜻이 아니다.
Reference preflight는 28/30일 통과했다. 4/17·4/18의 pending 96-GPU job 8504781에
필요한 AIDC05의 hard RUNNING release가 causal하게 알려지지 않았다. 이 job 및
FCFS 후속 4개 row를 J_PHYSICAL에서 제거하지 않았다.
15일은 known frozen reference + current CC4 nominal occupancy가 780 GPU를 초과한다.
고정 profile로 power를 구성 가능한 날짜는 14/30이다. 개별 날짜를 골라 실행하지 않았다.

J_PHYSICAL 및 J_FLEX rule은 frozen이며, J_FLEX 실행 가능 domain의 완성은 미확인이다.
May known input metadata 1,649행에 동일 modelability rule을 read-only 적용했다.
May Actual/voltage/policy outcome을 읽거나 April numerical donor로 사용하지 않았다.

B0 실행 0일, fully executable bundle 0/30. AIDC energy, 세 voltage, physical pass,
Q95/Q99, ±0.005 coverage 및 candidate band는 미측정(null)이다. Runtime/CC4 ML은
input layer에서 ON이며, B0 실행을 했다고 주장하지 않는다. B1/B2/B3/May/M1 NOT_RUN.
FINAL_MARGIN_ACCEPTED=false. 중단 원인은 raw unmodelable row 존재가 아니라
현재 공통 fixed schedule/CC4의 capacity 및 causal release authority이다.

회귀 tests는 기존 sealed fixtures를 읽는 baseline suite를 상속한다. 이는 새 April
construction이 May scientific outcome을 donor로 사용한 것과 구분된다.

회귀 검증: 1169 tests, failures=0, errors=0.
