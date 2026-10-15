# May01 경계 복구 및 AIDC–MESS 후속 검증

승인된 PR223 초기화와 저장 실행 증거를 복구했고, 253/886의 UID·Episode별 원인을 분해했다. 실제 Pending 최적 명령 Prefix는 복원되지 않아 Gate A/D는 NOT_CERTIFIED다. 새 May01 첫 이벤트·16슬롯·Full96·Fresh AC는 실행하지 않았다.

## PR223에서 이미 완료한 범위

324 Running /472GPU /1300 Pending, 기존151건/296GPU + PR129 20건/20GPU + PR125 153건/156GPU를 원래 loader와 원본 SHA로 검증했다. 제외44건은 재활성화하지 않았고 전체 완료 이력178건을 보존했다. 초기 사이트는 승인 모델 가정이며 Kestrel 사이트 관측값으로 바꾸지 않았다.

원본 A1→M1→A2→M2 FULL feasibility와 Full96 Actual/Fresh 영수증은 원본 V5 평가 Case에서 유효하다. 활성2320·완료1690·Carry630, GPU 위반0·Drop0, 설치11SVR·기존7 RegControl 보존을 독립 Byte/Source 검증했다. 현재 코드가 원본 실행 코드와 다르므로 현 코드로 재생한 결과라는 주장은 하지 않는다. 최종 Known 계획은 A2다.

검증된 Semantic SHA는 `5df25289619221a8ed1f7ee6d13a00e73ad5a4e38ac0cf08228e93c3fb67c573`, 초기 파일 Byte SHA는 `d8aae451858d7ab8579f087ac9811d04f83a8c10bd7e6fc1b2156e35b2db7003`다. 사용자 붙여넣기 Semantic 값은 원본과 달라 별도 입력 불일치로 기록했다. Stage/Planning/Evaluation Case 식별자 차이는 승인 변환 계보로 검증했다.

## 경계 원인과 진단 오류 수정

| A1 분류 | UID | 해석 |
|---|---:|---|
| Issue Running 연속 실행 | 103 | 133GPU, 과거 Start와 elapsed/site/Episode 일치. start=0은 잔여 서비스 좌표다. 관측 과거6h는798GPUh다. |
| Issue Pending → Dday Running | 150 | 관측 시작이 계획보다108건 먼저·42건 늦다. 사이트40건 일치·110건 차이. 기존 초기 배치를 유지한다. |
| 과거 계획인데 Dday Pending | 886 | 명목 구간714건 종료·172건 활성. 실제 실행 Prefix 증거가 없다. |
| Q50 명령 밖 Known Running | 48 | 163GPU를 실제 완료까지 유지한다. 명목 만료로 완료시키지 않는다. |
| 명령 영역의 관측 과거 완료 | 1 | Issue Running 이후 관측 완료 이력이며 새로운 START로 해석하지 않는다. literal 시작 인증은 별도다. |

원본 Producer는 Issue-relative 슬롯을 사용하고 Dday는 native24, 전력망·MESS 96슬롯은 native[24,120]이다. 00:00으로 원점을 옮기는 해석은 원본 계약이 아니다. 원본 Actual은 과거 Pending 명령을 `PRE_DDAY_START_COMMAND_NOT_REPLAYED`로 Reference Queue에 넘겼다. 이는 원본 물리 PASS의 실행 규칙이며 최적 명령 Prefix 실행 인증이 아니다.

886건 중 원래 허용 시작이 Dday 이후에도 있는 Job은 518건, 모두 과거인 Job은 368건이다. 추가 시작 예산은 모두0/PROTECTION_UNCONFIRMED이며 자동 Retiming 권한을 부여하지 않았다. A2에는 과거 Pending888건과 사이트 차이112건이 있어 A1 숫자를 최종 Actual 결과로 이전하지 않았다.

## 실제 구현 수정

Semantic SHA와 파일 SHA를 같다고 요구하던 인계 오류를 수정했다. 승인 초기화 loader를 통한 정규화와 원본 Source 재검증을 추가했다. 103개 이미 Running인 Job은 Source/Case/명령 SHA와 과거 elapsed를 재검증하는 typed continuation으로 연결한다. 남은 Pending 명령은 보존하고 gate를 통과시키지 않는다.

실제 JobRequest의 UID·Episode·site·start·elapsed·GPU·submit·Q50·compatible 계약을 검사하고 중복/재등록을 거부한다. 독립 리뷰에서 발견한 Q50/submit 검증 누락과 실제 `compatible` 필드 연결도 수정했다. 이 검증은 Native0 입력 연결이며 새 Actual 실행이 아니다.

## AIDC 검증 범위

저장 A1/A2의 Known + Unknown Q50 + Achieved CC4/Runtime Reserve 용량 관계와 CC4 CDF/서비스/Carry를 재검산했다. 둘 다 Achieved Reserve는0이며 Target Reserve나 Shortfall을 물리 점유로 바꾸지 않았다. Unknown 한번 차감·현재 GPU·signed 전체 선로 minimax·실제 Pending 충돌·WAN/QoS 권한·Running 보호·안전 Backfill은 기존 및 신규 Native0 회귀에서 검증했다. 실제 May01 정책 효과, Changed UID/GPUh, 교정 이벤트 및 Fresh 성능은 NOT_RUN이다. 두 실제 이벤트 CSV는 헤더만 포함하며 행0이다.

## MESS 후속 연구

공식 Adaptive Beam→4-MESS Joint MILP→Original FULL→Incumbent Registry를 유지했다. 원래 압축 총 고정 Pool 비용25.705→36.177초의 불리한 결과를 보존하고 기본 비활성화했다. 같은 Source/Case/Pool의 외부 SHA로 봉인한 완전 증명 패킷 재사용은 0.812986초였다. 이는 캐시 단계 측정이며 새 Native/전체 Beam 속도 개선 인증이 아니다. 새 다양한 Beam 실행과 UB 개선은 NOT_RUN이다.

원본 S1 전체 경로 Integer Oracle을40초 cap으로 한 번 실행해 실제 Native 40.174000초를 공유 원장에 추가했다. 시간 제한으로 UB 0.641265966974028, Bound 0.609063011458436, Gap 5.021778%이며 Integer 최적값은 NOT_CERTIFIED다. 원본 물리/행렬 replay와 literal Integer를 검증했고 새로운4대·24노드 Bound로 쓰지 않았다. 새 SOC/경로 Hull384개는 실제 Root 위반0으로 추가 Solver 실험을 하지 않았다. 기존 Mode Hull384 실험도 반복하지 않았다. 후속 DW 연구의 완전 Pricing 인증 전에는 Restricted Master를 Global LB로 인정하지 않는다.

원래4대·24노드의 UB0.5398310226338695 / K48 LB0.46498486997548166 / Gap13.864737209%는 원래 Case의 역사 인증값으로 보존했다.

## 현재 Gate와 다음 필요한 결정

Gate A: 승인 초기화·UID 원인·103 연속성은 확인됐지만 최적 Pending Prefix 연결은 NOT_CERTIFIED. Gate B: Native0 Fixture PASS / 실제 May01 NOT_RUN. Gate C: 원본 물리/동등성 검증 PASS, 새 Beam 성능 및 Global 최적성은 미인증. Gate D: NOT_CERTIFIED.

`RECOVERY_01/BOUNDARY_CASE_DECISION.json`에 승인 초기 상태를 고정한 별도 Dday Planning/과거 명령 처리 Case의 구체적인 범위를 남겼다. 만료된 허용 시작과 교정 권한을 먼저 명시해야 하며 새 Known 최적화는 실행하지 않았다. 없던 Prefix 생성, FCFS 최적 계획 치환, 초기 재배치, 완료 강제, Job 삭제로 숫자를0으로 만들지 않았다.

## 회귀·예산·보존

기존522개를 정확히 보존한 최종 Native0 회귀: 555 PASS / 실패0 / Skip0, 금지 Solver 시도0. 추가 33개 검증을 포함한다.

Native 252.269000→292.443000/360초, 잔여67.557000초. 과거 Call prefix와 부모 원장을 보존했고 inflight는 없다. 기존 FOLLOWUP 74개 파일 Byte SHA를 그대로 보존했다. 새 Native snapshot은 RECOVERY_01에 저장했다. Worker1/Threads1, May31·IEEE8500·Scheduler HOLD를 유지한다.
