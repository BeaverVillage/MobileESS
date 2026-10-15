# PR223 고정 M2 조건의 May01 16슬롯 Unknown C0/C1 독립 검증

00:00–04:00(FIXED AEST UTC+10, 900초×16) 실제 Replay와 새 Fresh AC 평가를 완료했다. Unknown 217 UID가 도착했고, 제어 시각에 도달한 197 UID 중 실행은 양군 0건이다. 목적지 차이 0건, Changed GPUh 0.0, C1의 실제 성능 개선은 **NOT_DEMONSTRATED**다. 합법 후보가 없어 실제 데이터에서 Ranking 선택 효과를 식별하지 못했다.

Gate1/2는 PASS다. Gate3는 결과 계산·동일 물리 Authority·위반 공개를 완료했다는 판정이며, 전기적 무위반 여부는 Fresh의 별도 판정 **C0 PASS / C1 PASS**를 따른다. Frozen affine 전압 검사와 Fresh 사이의 최대 0.354931 pu 차이 때문에 **온라인 전기적 입장 판정의 realized 정확성은 NOT_CERTIFIED**다. 초기 상태를 재배치하거나 제약을 완화하지 않았다. C_REF의 과거 성공 수치를 C0/C1에 이전하지 않았다.

| 실측 지표 | C0 | C1 | C1−C0 |
|---|---:|---:|---:|
| 도착 Unknown UID | 217 | 217 | 0 |
| Start Eligibility UID | 197 | 197 | 0 |
| 실행 Unknown UID | 0 | 0 | 0 |
| 초기 Running 외 추가 Known 시작 UID | 46 | 46 | 0 |
| 완료 UID / Carry UID | 43 / 1798 | 43 / 1798 | 0 / 0 |
| 전체 창 내 Compute GPUh | 1874.313055556 | 1874.313055556 | 0.000000000 |
| 창 내 완료 Job의 창 내 Compute GPUh | 57.313055556 | 57.313055556 | 0 |
| PCC P 에너지 kWh | 1590.737360481 | 1590.737360481 | 0 |
| PCC Q 에너지 kvarh | 522.850085904 | 522.850085904 | 0 |
| Fresh 최대 선로·상 부하율 | 59.028540% | 59.028540% | 0.000000000 pu |
| Fresh 16슬롯별 최대 부하율의 시간평균 | 50.899539% | 50.899539% | 0 |
| Fresh 전압 최저/최고 pu | 0.963607026 / 1.045940776 | 0.963607026 / 1.045940776 | 0 / 0 |
| 전체 Controller Tick P50/P95/Max | 6.514748/8.287196/8.708086초 | 3.038872/3.441089/3.498337초 | 실행시간 차이는 성능 인과 효과로 해석하지 않음 |

## 최종 20개 질문에 대한 답

1. **초기 상태:** 원본 byte SHA `d8aae451858d7ab8579f087ac9811d04f83a8c10bd7e6fc1b2156e35b2db7003`, semantic SHA `5df25289619221a8ed1f7ee6d13a00e73ad5a4e38ac0cf08228e93c3fb67c573`를 확인했다. 324 Running/472 GPU/1,300 Pending, 12 AIDC/780 GPU, 원래 사이트·Elapsed를 보존했다. 이전 완료 44 UID를 활성 집합으로 복귀시키지 않았다. 이 배치는 승인된 모델 초기 상태이며 Kestrel에서 관측한 실제 사이트라는 주장은 하지 않는다.

2. **Known 실행 구분:** byte 고정 PR223 원본 `_known_decision`/`_reference_decision`의 Reference Queue/Fallback을 사용했다. 과거 6시간 최적 명령의 정확한 실행이나 새 D0 명령을 사용했다고 주장하지 않는다. Planning 원본과 Actual 교정 원장은 분리했다.

3. **동일 최초 입력:** PASS. 초기 공개 Known 1,624 UID(기존 계보 Unknown 78 재분류 포함), May01 미래 Unknown 696 UID, 전체 활성 모집단 2,320 UID다. 이 구간 실제 도착은 217 UID이며 나머지 479 UID는 아직 제출 시각이 오지 않았다. CC4/Runtime/실제 사건·완료 Source/C1/GPU·Rack·WAN/QoS/Known 규칙/24사이트 M2/계통·날씨·수요·PV·900초 시계가 같다. 상세 SHA는 `C0_C1_COMMON_INPUT_CERTIFICATE.json`에 있다.

4. **후보와 Ranking:** 동일 public 상태의 1537개 후보 평가에서 후보 SHA가 일치했다. 양군은 같은 후보 함수와 현재 hard guard를 쓰며, C0는 Reference/사이트 순서, C1은 공개 Q50 서비스가 겹치는 모든 관련 슬롯·선로·상의 signed 최대 부하율을 최소화한다. 미래 예측은 동결 forecast와 공개 nominal remaining의 soft projection이며 미래 Known 예약 veto를 추가하지 않았다. Q50 초과·96슬롯 밖 tail은 보장하지 않는다. 여러 슬롯 반례 테스트는 C0 A/C1 B 선택을 확인했지만 실제 Source의 합법 후보는 0이다.

5. **Unknown 도착:** 각 군 217 UID. 최초 UID 8714697 제출은 00:16:06, 최초 합법 제어는 00:30이다. 강제 00:00 Unknown은 없다. 197 UID가 04시 이전 제어 tick에 도달했고 마지막 슬롯의 20 UID는 다음 tick이 평가 구간 밖이다.

6. **실행 Job:** Unknown 0 UID. 초기 Running 324 외 Known 46 UID가 시작했다. 전체 370 UID가 실행 이력이 있으며 43 완료/327 Running/1254 Known Pending/217 Unknown Pending이다. 전체 창 내 Compute 1874.313055556 GPUh와 완료 Job의 창 내 Compute 57.313055556 GPUh를 구분한다.

7. **C1 목적지 변경:** C0 대비 0 UID다. Queue의 `None` 목적지를 가상 배치로 세지 않았다.

8. **Changed GPUh:** 0.0 GPUh. 실제 시작/완료 구간 기준이며 계획 GPUh를 복사하지 않았다.

9. **Known 실제 충돌과 교정:** 99 UID에서 660회 현재 GPU 충돌 검사·교정 시도가 기록됐다. 합법 준비 근거 부족 등으로 교정 명령 0건/교정 후 실제 시작 0건이다. 전송·준비 시간과 추가 계통 영향은 실행 0건이므로 N/A/0이며, 모든 UID·시각·원사이트·후보 거부는 `KNOWN_CORRECTIVE_EVENTS.csv`에 있다. Reference latest-start 초과는 전체 690 UID, 최대 36000초다. 이는 기존 대기와 Reference 비교 위험이며 Source에서 확인된 고객 SLA 위반 판정으로 바꾸지 않는다. Running 강제 중단은 없다.

10. **Queue 원인:** Unknown 거부 UID 수는 `{"CURRENT_GPU_CAPACITY": 197, "CURRENT_OBSERVED_ORIGINAL_PLANNING_VOLTAGE": 185, "SOURCE_PREPLACEMENT_AUTHORITY_MISSING": 197}`다. 같은 UID가 여러 후보·시각에서 거부되므로 합산하지 않는다. Raw 호환 사이트와 권한·현재 GPU·전기를 모두 통과한 합법 사이트를 구분한다. 원사이트의 frozen affine 전압 검사와 대체 사이트의 Source/데이터/WAN 권한 부족, 일부 용량 부족이 함께 작용했다. Known 교정 거부 후보 횟수는 `{"CURRENT_GPU_CAPACITY": 473, "SOURCE_DATA_PREPARATION_AUTHORITY_MISSING": 6787}`다. Known Pending 1254와 Unknown Queue 217는 삭제하지 않고 Carry했다.

11. **물리 제약:** GPU 위반/Job 삭제/Global MILP 모두 0이며 Actual GPU로 Original C1을 독립 재계산해 P/Q 배열 일치를 확인했다. Frozen affine에서는 15개 슬롯별 위반 종류 기록이 있어 전체 affine 무위반을 주장하지 않는다. 실제 Fresh 위반은 전압 0, 선로 전류 0, 변압기 전류 0, 변압기 kVA 0 cell이며 C1도 동일하다. Fresh를 사용해 이미 거부된 Job을 소급 입장시키지 않았다.

12. **미래 정보 차단:** Simulator의 private Environment만 실제 Runtime/Completion을 읽는다. Controller future duration/completion read는 양군 0이고, Source 필드 주입 차단 테스트가 있다. 현재 관측 날씨만 current C1 callback에 전달하고 미래 ranking은 동결 forecast를 쓴다. Forecast는 실제 도착 Unknown UID당 한 번, 초기 Known에는 0회 차감했다.

13. **16슬롯 최대 부하율:** Fresh C0 59.028540%, C1 59.028540%다. 별도 frozen affine 값은 양군 62.594062%다. 서로 다른 상태의 평가를 같은 실측값으로 표시하지 않는다.

14. **Critical Line/Phase/Slot:** Fresh는 양군 `line.l52`, phase 1, terminal 1, 0-based slot 0, `2025-05-01T00:00:00+10:00`–`2025-05-01T00:15:00+10:00`다. Affine는 `line.l52`/phase `A`/slot 0다.

15. **실제 개선:** 입증되지 않았다. Δ사이트/Compute GPUh/PCC P/Q/선로 부하율은 0이다. 모든 Unknown이 공통 후보 guard에서 거절되어 Ranking 경쟁이 발생하지 않았다. Fixture에서 작동한 점을 실제 성능 개선으로 이전하지 않는다.

16. **11-SVR Fresh AC:** 양군 새 16슬롯 평가 PASS/PASS. 원본 7 RegControl, 11 SVR, LDC, 자동 TIME 시계와 모든 전기적 경계를 유지했다. Fresh wall은 C0 3.365421초/C1 1.848494초로 Gurobi Native와 별도다. Affine는 Actual AIDC P/Q와 고정 M2를 넣었지만 배경·LDC secant는 원래 forecast 상태다. Certificate는 local/unsaturated 유효범위이며 Actual 입력을 읽지 않았다. 최악 지점은 slot12 `idc_idc11_pcc.1`: affine 0.645841133 pu/Fresh 1.000771905 pu, 최대 정렬 전압 차이 0.354930772 pu다. 최대 control−anchor 차이는 392.314112이며 단위는 각 control의 kW/kvar다. 실제 forecast−realized 수요·PV 차이와 슬롯별 SVR/clock SHA를 `AFFINE_FRESH_AUTHORITY_AND_DIFFERENCE_AUDIT.json`에 남겼다. 비선형 오차·배경 차이·tap 동작의 개별 인과 기여는 분리 인증하지 않았다. 이 큰 차이는 미해결 검증 문제이며 현재 입장 판정이 realized 물리에 정확하다고 인증하지 않는다.

17. **D0 A1 결함 판정:** 아직 판단 불가다. 동일 Source/Case/Matrix/Domain/Objective가 재생성됐다. 정적 box 필요조건에서 직접 모순은 없었지만 feasibility 증명은 아니다. 25초 요청/26.238초 실측 Pilot는 presolve 12.97초 후 Root barrier 도중 TIME_LIMIT/SolCount0이므로 INFEASIBLE이나 단순 시간 부족 확정으로 해석하지 않는다.

18. **다음 Native 예산:** 모델 변경 없는 P1 120초와 반환 30초를 위한 최소 총 한도 468.681초, overshoot buffer를 고려한 권고 총 한도 480초(현행보다 +120초)다. 정수해 성공 보장이 아니며 P2/M1/A2/M2 예산은 별도다. 현재 Native `318.681/360`, 잔여 41.319초/반환 여유 30초를 보존했고 추가 실행은 HOLD다.

19. **MESS 보존:** Adaptive Beam→4-MESS Joint MILP→Original FULL→Incumbent Registry와 K48 코어를 변경하지 않았다. 고정 PR223 M2의 경로·P/Q·SOC와 96개 실행 명령을 확인했으며, IDC의 MESS P/Q가 0이어도 비영 STA 주입을 포함한 24사이트 전체를 유지했다. S1 5.0218%와 별도 4×24 Case 13.8647%를 혼합하지 않았다.

20. **Full96 잔여 조건:** 이 진단의 Full96는 NOT_RUN이다. 합법 Source·데이터·WAN 준비 근거와 실제 대체 후보가 생기는지, affine forecast guard와 realized AC 차이를 원본 Authority 안에서 어떻게 다룰지 먼저 검토해야 한다. 96슬롯 전체 사건·Carry·QoS·GPU/PQ와 새 Fresh96 평가가 필요하다. 새 D0 공동 최적화는 추가 예산 승인 후 P1 수용→P2→M1/A2/M2의 같은 Case 최종 결과가 별도로 있어야 한다. May31/IEEE8500는 실행하지 않았다.

## 보존·검증·전달

기존 445개 연구 산출물과 D0 Source13개를 byte 동일하게 재확인했다. 기존 Source/Raw/624개 테스트의 기대값은 변경하지 않았다. 최종 회귀 **640 PASS(624 기존+16 신규)**, failures/skips/신규 Native 호출 0이다. 외부 Worker PID35740은 같은 명령으로 실행 중이며 종료·신호를 보내지 않았다.

초기 준비 오류 두 건과 계측 전 Replay, 현재 슬롯만 평가하던 Replay를 별도 폴더에 Source bytes와 함께 보존했다. 최종 증거는 현재 C0/C1 폴더와 `ISOLATED_EXECUTED_CODE_SOURCE.json`을 따른다. 큰 새 Raw 원장은 원본을 로컬에 그대로 두고 deterministic gzip으로 전달하며 `LOSSLESS_EVIDENCE_DELIVERY.json`의 원본/압축 SHA로 byte 복원을 검증한다. 과거 Raw를 재작성하지 않았다.

필수 비교 CSV 중 `C0_C1_GRID_LOADING_COMPARISON.csv`는 frozen affine 평가이고, 새 실제 AC 값은 `C0_C1_FRESH_GRID_LOADING_COMPARISON.csv`다. `INDEPENDENT_MEASURED_COMPARISON.json`은 단위·UID/후보 수·QoS 위험·C1−C0를 구분한 통합 수치다. QoS Source의 미확인 속성이나 Queue 지연을 SLA 보장으로 바꾸지 않았다.
