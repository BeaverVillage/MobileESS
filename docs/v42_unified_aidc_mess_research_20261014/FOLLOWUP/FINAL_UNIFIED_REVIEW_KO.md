PR #230의 기존 브랜치에서 요청된 복구·개발과 제한된 검증을 수행했다. 522개 Native0 테스트 PASS(기존451 보존, skip0)이며 새 Native 사용량은 같은 누적 원장에 기록했다. 최종 실제 통합 Gate는 NOT_CERTIFIED다.

가장 먼저 막히는 AIDC 조건은 원본 Planning과 당시 저장된 Dday 상태의 불일치다. 동일 원본 파일과 원본1,499명령을 연결해 Running253건의 사이트/시작 불일치와 과거Pending886건을 확인했다. 파일 누락이 아니며 임의 Retiming·진단 FCFS로 교체하지 않았다. 정규화된 관측 상태 Receipt의 파일 SHA와 실제 Driver 초기 상태를 연결하는 Gate를 추가했으나 기존 semantic SHA를 파일 SHA로 바꿔 인증하지 않는다.

MESS는 공식 Adaptive Beam → 4-MESS Joint MILP → Original FULL → Incumbent Registry를 보존했다. 압축의 수학적 동등성은 PASS지만 비용은 증가했고, S1 Mode Cut은 실제 LP 목적 개선에 실패했다. 별도 소형 LP/Oracle 연구를 운영 Full MILP로 대체하지 않았다.

|번호|질문|상태|답변|
|---|---|---|---|
|1|Known과 CC4 GPU 공동 최적화|PASS|과거 동일 FULL A1의 96×12 용량·서비스를 재검증했다. 최신 연구 A1 인증은 없다.|
|2|Q50 Nominal과 Achieved Reserve|PASS|Nominal은 미래 예상 점유다. 확보 Reserve는 실제 용량 여유이며 과거 CC4/Runtime 확보량은 모두 0, 부족분은 75,649/17,330 GPU-slot이다.|
|3|Planning/Actual GPU 이중 계산|PASS|Bridge·Fixture에서 Forecast/Observed/Running/Committed를 분리하고 UID당 Forecast 1회 차감 및 서비스·Carry 보존을 검증했다. 실제 통합 인증은 없다.|
|4|미래 Known 예약 때문에 Unknown 사전 거부|PASS|새 활성 CurrentEvent 경로에서 제거했다. FCFS 비교 기준시각도 Source hard release로 취급하지 않는다. 과거 진단 코드는 재현용으로 보존했다.|
|5|현재 GPU·Signed Sensitivity 배치|PASS|모든 선로/상과 Original C1을 평가한다. 원본 12 AIDC/780 GPU/11 SVR 계수 Fixture에서 12후보 중10 허용, P/Q 오차1.83e-15·도함수 오차9.36e-17이다. 실제 May 성능은 미검증이다.|
|6|실제 Known 충돌 시 PENDING Pre-placement|PASS|명명 Fixture에서 실제 충돌 때만 수행했다. 미래 추측과 Running 이동은 수행하지 않는다.|
|7|GPU/WAN/데이터/QoS 만족|PASS|권한·Rack·bytes/s WAN·전송/준비시간·공유 QoS를 검사하고 준비 후 현재 GPU/계통을 다시 검사한다. 증거 부족은 Queue한다. 실제 May 인증은 없다.|
|8|Planning/Actual 명령 구분|PASS|PLANNING_COMMAND를 보존하고 ACTUAL_CORRECTIVE_COMMAND를 별도 저장한다. 같은 입력의 교정 후 Known 실행 SHA 동일을 강제하지 않는다.|
|9|Runtime Overrun Running 보호|PASS|Q50 만료로 해제하지 않는다. 실제 관측 완료까지 물리 점유를 유지하며 잔여 Runtime 미검증은 None으로 표시한다.|
|10|Runtime Short Backfill|PASS|실제 완료 즉시 GPU를 해제한다. 다음 합법적15분 실행 이벤트에 후보 사이트별 미래 확정 예약을 검사하며 안전성 증명 없으면 대기한다.|
|11|QoS60분 연구 가정|PASS|참여 Batch 연구 계약과 고객 SLA를 구분했다. 본 Actual의 의도적 Time-shifting·Checkpoint Migration은 활성화하지 않았다.|
|12|May01 Unknown 실행·Changed GPUh|NOT_RUN|새 제어의 실제 May01은 실행하지 않았다. 합성 Fixture의 Changed GPUh0.5를 May 결과로 사용하지 않았다. 과거2시간 진단의 Unknown 시작/변경은0이었다.|
|13|C0/C1/C2 최대 선로부하율|NOT_RUN|새 May01 값은 모두 미측정이다. 합성 Fixture만0.90/0.65/0.65이고, 과거C0/C1 진단0.5201161496609195는 별도 역사다.|
|14|기존11-SVR Fresh AC|NOT_RUN|현재 Actual trace가 없으므로 새 Fresh AC를 실행하지 않았다. 과거Fresh16 PASS를 이전하지 않았다.|
|15|원래4대·24노드 정확 압축|PASS|동일 PR221 Pool137,635변수/416binary를 유지하며715,600→685,819행,7,008,176→6,961,847NNZ. Integer/LP 동등성 및 원본 FULL replay를 검증했다.|
|16|전체 Beam 반복시간 개선|NOT_CERTIFIED|같은 Pool 측정 비용25.7048→36.1767초로 증가했다. 압축 Native20.229초·증명/캐시9.243초, 원본 Native19.089초. 전체 새 Beam 반복 Wall은 미측정이며 기본 채택하지 않는다.|
|17|더 좋은 FULL UB 발견|NOT_RUN|새 Beam 실제 탐색은 미실행이다. 고정 Pool 양쪽 FULL UB0.5398310226338695로 개선0이다.|
|18|다른 차량·충전소 충분 탐색|NOT_CERTIFIED|4차량·STAY/이동·목적지/시각 다양성의 같은 예산 Admission Fixture는 PASS다. 실제 원본24노드 탐색 범위와 UB 효과는 미검증이다.|
|19|S1 Root Gap 원인|DIAGNOSTIC_ONLY|실제 LP0.6090630116, 분수Arc4,307·Mode192·다중 위치187 차량슬롯·동시 충방전192 차량슬롯이다. 정수 feasible UB0.64126596697은 최적값이 아니다. Mode만 바꿔 같은 목적을 유지하는 LP witness가 있다.|
|20|K48보다 높은 인증 Global LB|NOT_CERTIFIED|유효한384 Mode Cut으로 S1 LP 변화6.7e-11에 그쳤다. 원본4×24 K48 LB0.46498486997548166을 넘어선 새 인증은 없다.|
|21|Restricted Bound/Global LB 구분|PASS|Pool ObjBound0.539831/0.289400과 S1 LP는 원본Global LB로 쓰지 않는다. 원본 같은 Case의 gap13.864737209%를 보존했다.|
|22|동일 Case A1–M1–A2–M2 실제 통합|NOT_CERTIFIED|원래4단계와 최종A2→Actual Hook은 유지했다. 과거 원본 경계의Running253·과거Pending886 불일치 및 최신 SAME_CASE_A1_NOT_CERTIFIED로 실행 인증이 막힌다.|
|23|동결 가능한 기능|PASS|현재 이벤트 배치·Pending 교정·물리 점유/Forecast Bridge·Source 경계/명령/실제 Driver Join·동일 Pool 삭제 증명/오염 거부를 코드·Fixture 범위로 동결한다. 성능 개선을 동결하지 않는다.|
|24|연구 실패/미검증|NOT_CERTIFIED|압축 전체 비용 개선 실패, Mode Hull LP 개선 실패. 새 Beam UB·강화Global LB·S1정수최적값·60분Actual·Migration·May Fresh AC·실제 통합은 미검증이다.|
|25|다음 May01/May31 실행 근거|NOT_CERTIFIED|May31/IEEE8500/자동 Scheduler는 HOLD다. 기존6시간 Prefix의 정당한 실행과 정상화된 동일 Source Dday 상태를 먼저 인증해야 May01 Canary를 진행할 수 있다.|

공유 Native는 252.269000/360초 사용했고 107.731000초가 남았다. Worker1·Thread1, 부모 원장 SHA와 기존 사용량, PR221 별도 세션을 보존했다. 추가 날짜 캠페인·IEEE8500·자동 재시작·Running 강제 종료·Actual 전역 MILP는 실행하지 않았다.
