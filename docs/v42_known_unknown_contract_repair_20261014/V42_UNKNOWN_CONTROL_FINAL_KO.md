# V42 Known–Unknown 통합 정정 — 2026-10-14

Known은 A1/A2의 최종 UID 계획을 유지하고, Unknown만 Planning에서 생성·저장·재조회한 다중 대안 표를 사용하도록 복구했다. 검증 수준은 Native0·Fixture·실제 May01 UID 분기 감사다. 새 May01 A1/A2, C1–C3 Full96 및 Fresh AC는 **NOT_RUN**, 새로운 실제 계통 개선과 최적성은 **NOT_CERTIFIED**다.

1. PR226 `1100995086a8d202cb6b8a7308ccc6d60799bbc5`의 `experimental_actual.py:186`에서 `self.known_schedule={}`가 Known 명령을 지웠다. 이를 제거하고, 최적화 대상 밖 Known도 별도 Source Reference/Fallback으로 분리했다. Known이 Unknown selector에 들어가면 테스트가 실패한다. 계획 이전 시각의 명령을 D-day Pending에 재작성하지 않고 명시적 실패·Queue를 기록한다.

2. Source 발행 Known 1,649개 중 D-day 이전 완료 103개, 활성 Known 1,546개, Unknown 774개다. 자정 전 관측 Unknown 78개와 D-day 제출 696개를 구분했다. 개별 A-stage 1,499개와의 차이 150개는 Running nominal service 0인 106개와 외부 44개다. 활성 최적화 대상 1,498개, 활성 Known Fallback 48개다. 새 E1/E2 Known 변경 수는 NOT_RUN이다. 저장된 **이전 V5 A2 진단**은 변경 1302 UID, Time-shift 978, Preplace 1176, Migration 0, nominal model GPUh 8349.000, rho 0.641265992다. 새 계약의 결과나 PR189의 228개와 비교하지 않는다. Running의 계속 실행 경계를 역사적 재시작으로 세지 않았다.

3. B1은 Final A1 + MESS OFF, B3은 Final A2/M2 Anchor에서 Unknown 표를 생성하고 SHA를 확인해 재조회한 뒤 Actual에 전달한다. E1/E2 Known QoS는 Domain 생성 전에 적용하며 Science/Case SHA를 새로 만든다. Planning 준비가 미래 Actual 요청 목록을 읽으면 실패하도록 검증했으며, 실제 요청 변환은 최종 정책 동결 이후에 수행한다. Native 최적화 실행은 아직 없다.

4. 실제 Source는 AIDC 12개·780 GPU다. 지원 사이트를 GPU 여유 상위 K개로 자르지 않는다. 정수 Gang과 실제 Source/Rack 호환 사이트의 교집합을 모두 생성한다. May01 Unknown Gang [1, 2, 3, 4, 8, 60] 및 최대 Q50 210435.802초가 기본 선언 범위에 포함된다. 이 실제 사후 목록을 Planning 입력으로 사용하지 않았다. 제출한 표 파일은 명시적인 2 AIDC Fixture이며, 실제 May01 전체 표 컴파일은 NOT_RUN이다.

5. E1 Normal 0/15/30분, E2 Normal 0/15/30/45/60분을 생성한다. Source 확인 Standby만 기존 60/120분 범위를 사용한다. UNCONFIRMED를 관측 Standby로 승격하지 않는다. 0초 지연 Placement는 별도 Source 권한으로 검사한다. Runtime 경계는 상한과 제어 시점 경계를 평가하고 인접 Bucket의 공통 경계 Fallback을 사전 연결한다.

6. Q50 rho가 1순위이며 동등성 허용오차는 기존 1e-9다. 동점에는 Q90 CDF 위반/결손, Carry, Queue, Q50 최대 선로 노출량(loading-hours), Q90 peak, QoS 부담, 개입 최소화와 고정 Site/Frame 순서를 사용한다. 원래 A-stage P2를 변경한 것으로 표현하지 않는다. 동일 숫자를 SHA로 공유하며 후보·순위·정밀도를 삭제하지 않는다. 작은 Fixture의 모든 사이트×시간 점수를 원래 scalar 식과 독립 비교했다. Actual은 목적함수를 계산하거나 순위를 바꾸지 않는다.

7. Running 현재 점유, Known 확정 미래 예약, Unknown 확정 명령, 익명·미확정 예측을 구분했다. 관측 Running은 다음 제어 시점마다 먼저 보호한다. Known/다른 확정 Unknown 예약은 밀어내지 않는다. 실행 명령 실패 시 동일 Frozen 행의 다음 합법 대안을 원자적으로 교체하고, 모두 실패하면 Queue/STAY다. Migration의 미래 목적지 GPU Hold 시작 시에도 현재 GPU/Rack/affine 검사를 반복한다. 이미 전송을 시작한 후 목적지 Overrun 때문에 불가능하면 명시적 실행 실패로 Replay를 중단하며, 기존 Job을 밀어내거나 완료를 조작하지 않는다. R0/B를 재발급하거나 지연 의무를 환불하지 않는다. 충돌 Resource·구간·상대 UID·역할을 기록한다.

8. 기존 참여자 244개 선택 중 205개 미실행은 Known 103·Unknown 102개다. 현재 GPU·affine 검사가 가능했던 174 UID/592 사건은 미래 안전의 증명이 아니다. 동일 행 차순위 실행과 예약 보호를 Fixture에서 개선·검증했으며, 이 실제 205개 집단의 구제 수는 NOT_RUN이다. 후보 상한 잘림은 0, 승인 대안 미선택은 17개였으므로 상한 부족을 핵심 원인으로 주장하지 않는다.

9. 기존 Q50 Hard 미승인 317개는 Known 246·Unknown 71개다. 20 UID/598행 witness는 literal 상한 초과와 전압 거부를 재현했으며 불필요한 거부를 증명하지 않았다. C3는 cohort x, 시간별 총 서비스, CDF와 Carry를 유지하는 **공간 배분 대안**만 사전 평가한다. 이미 비교 중인 Reference 서비스 몫을 중복 재배분하지 않는다. 현재 실제 Job 예약과 익명 수요를 합쳐 Hard 점유로 만들지 않으며, 실제 시작 시 GPU/Rack/WAN/현재 affine 안전을 확인한다. 실제 317개 승인 증가나 시간 재배분은 아직 주장하지 않는다.

10. 과거 62개 실제 행동은 Known DELAY 6 + PREPLACE 32 = 38개, Unknown PREPLACE 24 = 24개, Migration 모두 0개다. Unknown 최종 Time-shift는 PREPLACE와 겹치는 **2개**다. 취소 명령의 지연 의무는 최종 시간 이동과 다르며, 이전 중간 분석의 15개를 최종 시간 이동 수로 사용하지 않는다. Unknown 행동률은 과거 진단으로 24/774 = 3.1008%다. 수정 후 May01 행동률은 NOT_RUN이다.

11. 과거 참여 Unknown 218개 중 조정 24개, 11.0092%다. 전체 참여 674개 중 조정은 39개이며 62/674가 아니다. 23개 비참여 Known Placement는 별도 원래 모델 권한이다. 새 Source/Case 결과에 이 비율을 이전하지 않는다.

12. 과거 조정 Unknown의 lifetime nominal GPUh는 7.568100962, 적격 Unknown nominal GPUh 3132.892889656 대비 0.241569%다. 이는 실제 이전·이월 서비스 GPUh나 전력 감소가 아니다. Known Planning/Unknown Actual 비율을 합치지 않는다. 새 측정 함수는 Known의 Source C1 사이트별 ΔP와 Unknown의 첫/후순위 실행·동일 행 Fallback·예약 실패·기한 위험을 구분해 기록한다. 실제 IT/PCC P/Q와 동일 입력 C0–C3의 상세 비교는 작은 Fixture NPZ/영수증으로 제공했다.

13. 새 실제 May01 계통 부하율 개선은 미실증이다. B0/B1/B3 새 동등 Case rho·Actual affine·Fresh AC rho·critical-line/time·Rebound는 NOT_RUN/NULL이다. 작은 Fixture에서 Known의 잘못된 B 배치를 계획된 A로 복구했고, 완료 2·Carry 1을 유지했다. 이것을 May01 성능 향상으로 표현하지 않는다. 예측 C3 배분은 실제 점유가 아니다.

14. 원본 P1·P2 코드와 GPU/Rack/WAN/서비스/전압/전류/변압기 물리 정의를 변경하지 않았다. Original signed response와 PR225 Q90−Q50 recourse를 재사용한다. 최대 1회, 최초 유효 Checkpoint, 비영 Transfer/Restart와 Shared Budget을 유지한다. Q50 overrun은 실제 완료로 처리하지 않고, 승인된 인과적 잔여 예측이 없으면 STAY한다. 새 실행 예약 역할과 정책 계약은 별도 Science SHA로 식별한다.

15. 회귀 207개와 요구 이름 27개 PASS, May01 2,320 UID 분기 감사 PASS다. B1/B3는 Solver 없는 handoff Fixture로 연결을 확인했다. 새 A/M Optimize·Fresh OpenDSS·31일 Campaign 실행 0회, Solver 원장 621.2855198158068/3,600초 및 Campaign HOLD를 보존했다. 새 E1/E2 실전 성능을 주장하려면 Source/Case/Policy Freeze와 단일 Replay 실행 권한·RAM 예산 검토가 추가로 필요하다.

Correction Science SHA: `7d50d03fa2d8b0161c8d074e0c5c695cf13931490026aec7e1a2e36ca75744b3`. 원본 Source/진단 파일·기존 FULL/Gap/Fresh·FAIL 증거는 변경하지 않았다.
