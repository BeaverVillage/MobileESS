# V42 R1 Pre-site 연구 검증과 캠페인 준비

R1 공유 입력 연구 환경에서 Unknown 기본 배치 이후의 합법적인 PENDING Pre-site가 실제 작동했다. May01 첫 16슬롯의 고정 PR223 M2 비교에서 C1은 31개 UID를 변경했고 Changed GPUh는 81.062222였다. C0/C1 원본 정착 Fresh AC는 모두 PASS했다. 최대 선로·상 부하율은 양군 모두 0.6159699835로, 이번 비교의 최대 부하율 개선량은 0이다. 이 결과는 현재 D0 A1–M1–A2–M2 및 Full96의 완료를 뜻하지 않는다.

공식 물리 Gate는 원본 11-SVR의 900초 × 96슬롯 정착 AC다. Substep 진단과 Source-strict/R1/R2, 16슬롯/Full96, 고정 M2/현재 D0의 결과를 구분한다. 최종 Release Freeze와 May31 PASS는 선언하지 않는다. [평가 범위와 승인 조건](RELEASE_SCOPE_KO.md), [정책 후보](RELEASE_POLICY_CANDIDATE.json)를 함께 적용한다.

## 문헌과 연구 계약

[Wang et al., IEEE TSG 2016](https://doi.org/10.1109/TSG.2015.2501808)은 지리적으로 분산된 DC의 Workload 배분과 서비스·지연 제약을, [Hogade et al., IEEE TSUSC 2022](https://doi.org/10.1109/TSUSC.2021.3086087)는 에너지·네트워크 비용 및 입력 크기 민감도를, [Basmadjian et al., IEEE TSG 2018](https://doi.org/10.1109/TSG.2016.2632526)은 GreenSDA/GreenSLA의 유연성·QoS 계약을 모델 근거로 제공한다. 이 논문들로 실제 Kestrel 고객 승인이나 데이터 복제를 입증하지 않는다. 원문의 위치·DOI·발행 정보와 적용 한계는 [문헌 검토](LITERATURE/RESEARCH_MODEL_JUSTIFICATION_KO.md), [사실 레코드](LITERATURE/LITERATURE_FACTS.json), [BibTeX](LITERATURE/REFERENCES.bib)에 있다.

R1은 기존 FLEX30 적격 PENDING 작업만 Source-Compatible 사이트와 공유 입력 접근 집합의 교집합에서 평가한다. 공유 입력이 사전 준비되어 실행 직전 사이트 간 전송을 요구하지 않는 것은 명시적 **ASSUMED 연구 환경**이다. Kestrel의 `data_ready`나 고객 동의 필드를 생성하지 않는다. 원본의 명시적 이동·접근 금지, 보호·비배치 조건과 기존 QoS/Release/Deadline은 우선한다. R1에 관측되지 않은 WAN 완료 기록을 요구하지 않는다.

R2는 별도 전송 인지 Case다. TSUSC 원문 Table 2의 100/233/500/600/650 MB 입력 예시를 절대 작업당 Payload 시나리오로 사용한다. Kestrel UID를 그 benchmark 작업유형과 대응시키지 않았다. MB=10⁶ bytes, 기존 V42 WAN Path/Capacity, 대역폭 비율 0.25/1, 준비 0/900초를 구분한다. 데이터 크기와 대역폭으로 전송시간 하한을 계산하고 900초 격자로 올림하며, 원래 QoS가 추가 지연을 허용하지 않으면 이동을 거절하고 STAY를 유지한다. 기존 80 GB/GPU proxy는 별도 역사 시나리오로 보존했다.

## 실제 R1 첫 16슬롯

| 지표 | C0 | C1 |
|---|---:|---:|
| 실제 Unknown 도착 / 기본 사이트 지정 | 217 / 217 | 217 / 217 |
| 실제 Unknown 시작 UID | 25 | 43 |
| 실제 Known 시작 UID | 640 | 625 |
| 실제 Pre-site 변경 UID | 0 | 31 |
| Changed GPUh | 0 | 81.062222 |
| 기본 사이트 STAY 시작 UID | 25 | 12 |
| Unknown Queue UID | 192 | 174 |
| 전체 실제 Compute GPUh | 2949.154167 | 2984.966389 |
| Controller 최대 Tick, 초 | 59.374507 | 165.843126 |
| Controller P95, 초 | 30.068541 | 84.427757 |
| Actual Wall Time, 초 | 206.721860 | 500.631833 |
| 원본 정착 Fresh AC | PASS | PASS |
| 정착 전압 최소–최대, pu | 0.968310075–1.043686280 | 0.967979276–1.044457318 |
| 최대 선로·상 부하율 | 0.6159699835 | 0.6159699835 |
| 정착 전압·선로전류·변압기 전류/kVA 위반 | 0 | 0 |
| GPU 용량 위반 / Dropped Job / Actual Global MILP | 0 / 0 / 0 | 0 / 0 / 0 |
| 원래 예산 초과 의도적 QoS burden UID | 0 | 0 |
| 원장 latest-start excess UID / 최대 초 | 637 / 36000 | 628 / 36000 |
| Native/P2 호출 | 0 / 0 | 0 / 0 |

두 군의 초기 상태, 원본 Job 이벤트, Known 계획, 기본 사이트 지정 원장, CC4/Runtime, 원본 C1 전력 모델과 24개 MESS 서비스 사이트 P/Q 계획은 같다. 데이터 환경도 같고 C0는 Pre-site 행동만 비활성화한다. 실제 처리량과 후속 GPU/PQ 상태는 실행 결과로 달라질 수 있다. 서로 다른 상태의 점별 부하를 순수한 사이트 이동 효과로 해석하지 않는다.

Unknown 시작 증가와 함께 Known 실제 시작은 640개에서 625개로 감소했다. 이는 같은 Known 명령 아래 달라진 현재 자원 경합의 관측 결과이며 Known 처리량 개선을 주장하지 않는다. 의도적 추가 지연·이동 중단 burden의 예산 초과는 0이고 관측된 Hard Completion Deadline 초과도 0이지만, 원장에는 기존 backlog/reference의 latest-start 초과가 남는다. Raw의 이 지표와 미확인 고객 SLA를 혼동해 전체 QoS 위반 0 또는 SLA 충족을 선언하지 않는다. 미래 Known의 잠재적 GPU 예약을 사전 veto로 사용하지 않는 기존 사용자 정책도 유지했다.

31건 모두 당시 STAY가 불가능한 상태에서 합법적인 대체 사이트 중 최소 인증 score를 선택한 경우다. 실행 가능한 STAY보다 더 좋은 score 때문에 변경한 UID는 이번 실행에서 0개다. 따라서 이번 결과는 공간 유연성이 일부 Queue를 실행으로 연결했다는 관측이며, 최대 선로부하율 개선이나 일반적인 최적성을 입증하지 않는다. 최대 부하율 개선량을 조작하지 않았다.

Changed GPUh는 변경된 UID의 Start부터 관측된 실제 완료 또는 16슬롯 종료까지의 GPU 점유를 적분한 값이다. C0 대비 추가 GPUh와 다른 지표다. 실제 Start와 완료 이벤트로 31개 UID와 81.062222 GPUh를 독립 재계산한 [감사](INDEPENDENT_RESEARCH_AUDIT/R1_RAW_SELECTION_AUDIT.json)에 UID·기본/선택 사이트·GPUh·선택 score를 기록했다. 완료 이벤트는 실행 후 감사에서만 읽었으며 Controller에 미래 정보로 전달하지 않았다.

217개 중 FLEX30 61개는 연구 계약 적격 대상 수다. 실제 평가 시각까지 도달한 적격 UID, GPU/Rack 통과 UID, 데이터/QoS 통과 UID, AC 통과 UID 및 실제 변경 UID와 같지 않다. Compatibility → GPU/Rack → 데이터 계약 → QoS → AC → 민감도의 실제 Funnel은 별도 원장으로 제시한다. 앞선 실행 어댑터의 호출 순서와 논리 Funnel을 구분하고, 미실행 검사를 PASS로 채우지 않는다.

원시 결과는 [R1 실행](ACTUAL_RESEARCH02/R1_SHARED_READY/), [원본 Fresh 요약](ACTUAL_RESEARCH02/R1_SHARED_READY/OFFLINE_FRESH_16_STATUS.json)에 있다. 최초 3슬롯의 C1 1건·1.0 GPUh는 이 16슬롯의 부분 범위로 별도 보존하며 전체에 더하지 않는다.

## R2와 Source-strict

Source-strict의 기존 첫 16슬롯은 217개 기본 배치, 25개 STAY 실행, Pre-site 0건이다. 원본에 대체 사이트의 데이터 준비·이동 권한 근거가 없어서 Pre-site를 닫았으며, 어댑터의 기본 `False`를 고객의 명시적 거부로 해석하지 않는다. 기존 최초 배치 연구 권한은 유지한다. R1의 승인을 실제 Source 권한으로 덮어쓰지 않았다.

문헌 기반 R2 사전 검사는 20/20 별도 조건을 구성했고, 61개 적격 UID의 671개 목적지 전제에서 기존 추가 QoS 지연 0초가 전송 준비를 거절했다. 이 값은 GPU/Rack/AC까지 통과한 실제 이동 가능 수가 아니다. 실제 대표 233 MB·0.25 대역폭·준비 0초 C0/C1 결과와 첫 16슬롯 Fresh는 [문헌 R2 실행](ACTUAL_LITERATURE01/)에 기록한다. **R2_FINAL_METRICS_TO_BE_INSERTED_AFTER_RUN**

기존 proxy R2 실행은 C0까지 완료했지만 C1 후반에 Available RAM 8 GiB/Commit 75% 안전 Gate가 발동했다. 해당 시도는 부분 실행으로 보존하며 C1 완료/PASS로 집계하지 않는다. 이후 문헌 R2는 범위와 군별로 별도 프로세스를 순차 실행하여 이전 원장과 객체의 메모리 누적을 피한다. Worker는 동시에 1개다. 실패 Raw·자원 원장·완료한 R1 결과는 삭제하지 않았다.

## 전압 원인과 공식 평가 복구

E0는 초기 RUNNING만, E1은 Known 실행 추가, E2는 기존 Unknown 기본 시작 추가, E3는 당시 Pre-site 정책 추가로 구분했다. E0에서도 substep 위반이 있었고, Pre-site 0건인 E2/E3는 145개 물리 step와 전체 SVR 상태 SHA가 정확히 같았다. E2의 32개 위반 step, 100개 버스·상 셀, 0.920348532–1.083657372 pu는 May01 이후 양의 물리 경과 시간에 발생했다. 내부 반복이나 전날 Prefix로 재분류하지 않았다.

Tap 초기화, 이중 replay, Control Queue/Delay/TapDelay, 입력 P/Q와 시간축을 검사했으며 진단을 없애기 위한 원본 제어 변경은 하지 않았다. 관측 결과는 정상적인 제어 지연을 포함하는 상태에서 입력 변화와 전압이 상호작용한다는 범위다. MESS Q 변화의 동시성만으로 단일 원인을 단정하지 않았다. [원인 진단](../RC02/VOLTAGE/)의 Raw와 위반 위치·시간·P/Q·Tap·Queue를 보존한다.

사용자 정정에 따라 공식 Gate를 원본 `settle_slot → measure_full_network`로 복구했다. 16슬롯 연구 Case는 해당 범위에서 새 trace로 다시 Fresh를 실행했고, 현재 D0 Full96는 별도로 재검증해야 한다. ASOF 진단 실패만으로 May01/May31을 차단하지 않는다. 정착 PASS는 슬롯 내부 연속시간 전압 안전성 인증이 아니며 이 한계는 계속 남는다. 전압 범위, NormalAmps, 변압기 전류/kVA, 원본 11-SVR·7 AUTO·제어 이력 및 MESS P/Q를 완화하거나 수리하지 않았다.

과거 Forecast Affine를 현재 Actual 안전 판정에 사용하던 연결도 분리했다. 현재 관측 가능한 Demand/PV/Weather와 원본 C1 P/Q로 후보별 인과적 AC를 계산하고, 공개 Q50 예측은 순위용 조건부 결과로 표시한다. 원래 Affine의 국소 유효 범위를 확장했다고 주장하지 않는다.

## Planning·31일 입력·Production 준비

성공한 A1 P1 해는 재실행하지 않았다. Objective/Native Bound 0.64211779208034, 사용 Native 50.622초, 원본 844129행 FULL 최대 잔차 약 3.82×10⁻¹²를 보존하고 원본 export와 직접 대조했다. 별도 P1-only Stage Acceptance가 성공점을 직접 전달하므로 가짜 P2 출력이 필요하지 않다. P2 호출은 0회다. Native Gap 0%를 미가격 전체 Migration 도메인의 전역 최적성으로 주장하지 않는다.

현재 M1 원본 factory도 Native0으로 한 번 구성했고, 원본 1130336×344967/16432980 nnz와 선택 행렬의 transport 동등성을 확인했다. 전체 준비 창 1513.660초이며, Native 최적화 완료가 아니다. 2,131,289,534-byte 실행 준비 packet은 로컬에 보존하고 재사용 시 SHA와 현재 Case/도메인/원본 factory 발급 정보를 재검증한다. 이 대형 로컬 packet은 Source 권한 또는 새 M1 해가 아니다. 같은 모델을 다시 만들지 않았다.

31/31 날짜의 독립 D0 초기 상태, 날짜별 CC4/Raw 기반 공개 Planning 입력, 공개 Actual 명령 변환을 준비했다. May01은 324 RUNNING/472 GPU/1300 PENDING을 정확히 재현했고 다른 날에는 복사하지 않았다. 미래 Completion/Unknown 개별 UID를 Planning에 넣거나 전날 Actual Carry를 가져오지 않았다. [초기 상태 표](../RC02/INITIAL_STATES/), [날짜 Case](../RC02/DATE_CASES/COMPILE01/), [공개 Actual 변환](DATE_ACTUAL_HANDOFF/PUBLIC01/)에 누락과 Source/Initial/CC4 SHA를 기록했다. 또한 [31일 R1 계약](CAMPAIGN_R1_CONTRACTS/MAY31_R1_CONTRACT_PREPARATION.json)을 각각의 날짜 Raw/WAN/Planning identity에 묶었다. UID roster나 실제 이동 결정을 포함하지 않는다.

Production은 Original A1/A2, 기존 Beam–Joint/FULL, Actual Event Controller, 원본 Fresh를 직접 연결한다. Dummy와 임의 executor 주입은 생산 경로에서 거절한다. 실제 FULL/Source/Case/parent/result/Raw SHA가 없는 Stage는 다음 Stage로 넘기지 않는다. 개인 Runtime/Completion Truth는 공개 Gate를 검증한 뒤 원본 Environment 안에서만 사용한다. 날짜 AC의 May01 literal은 별도 날짜 어댑터에서 Clock 날짜 식만 바꾸어 연결하고 원본 Source는 보존했다. 초기 PENDING의 첫 사이트 지정과 관측된 실제 자원 대기 재시도는 좁은 원장 증거로 구분하며 새로운 이동·지연 권한을 부여하지 않는다.

Native Budget Adapter는 새 승인 ID/단일 원장 경로/날짜·Stage cap/Source·Case·parent/native matrix binding, Worker1/Threads1, RAM/Commit, P2 금지, durable in-flight/charge/중단·재시작과 읽기 전용 역사 원장을 검사한다. Planning-only 완료 뒤 그 원장을 읽기 전용으로 고정하여 FULL checkpoint를 검증하고, 후속 실행은 별도 승인/원장을 사용한다. 정상 A2 이후와 날짜 완료·실패·resume 실패 때 대형 Case와 context를 해제한다. 테스트된 연결을 실제 새 D0 생산 실행 성공으로 표현하지 않는다.

## 남은 작업과 승인 조건

| 항목 | 현재 상태 | 최소 후속 조치 |
|---|---|---|
| 현재 D0 M1 → A2 → M2 | NOT_RUN, 별도 Native 승인 없음 | 570초 제안 승인 후 원본 P1-only 실행과 매 단계 FULL 수용 |
| 현재 Case K48 Global LB | NOT_CERTIFIED | 새 FULL M2의 현재 도메인 포함성·투영 packet 검증 및 기존 K48 executor 연결. 별도 Native 승인 |
| 현재 D0 May01 16슬롯/Full96 | NOT_RUN | 새 최종 A2/M2에 대해 Actual, 현재 GPU/QoS 및 원본 정착 Fresh 재검증 |
| May02/10/12 및 31일 실행 | NOT_RUN | 현재 D0 May01 Full96 Raw Gate와 동결 Source, 대표 날짜 확인, 별도 캠페인 Native 승인 |
| 최종 Release Freeze | 미발급 | 실제 현재 D0 통합 검증 및 필수 Gate 충족 후 발급 |

첫 Native 제안은 M1 180 + A2 120 + M2 180 + 반환 30 + overshoot 60 = **570초**다. 승인 전 실행하지 않았다. 완료한 Planning 원장을 보존한 후 K48은 Native cap 180 + 새 반환 30 + 새 overshoot 60 = **270초**의 별도 제안이다. 두 승인 상한의 합은 840초이며 실제 소비·Wall Time 예측이 아니다. 기존 750초 단일 원장 제안은 미승인 역사 자료로 보존하고 현재 두 원장 경로에 적용하지 않는다. 실제 K48 도메인 packet과 계산 준비가 끝나기 전에는 최적성 인증을 주장하지 않는다.

검토 가능한 [570초 승인 후보](../RC02/PRODUCTION/APPROVAL_CANDIDATE_V5/UNAPPROVED_PLANNING_570_APPROVAL.json), [정확한 May01 실행안](../RC02/PRODUCTION/APPROVAL_CANDIDATE_V5/UNAPPROVED_MAY01_PLAN.json), [Source·Case 결합 증거](../RC02/PRODUCTION/APPROVAL_CANDIDATE_V5/EXACT_REVIEW_BINDING.json)를 준비했다. `approved=false`이며 새 원장은 생성하지 않았다. 승인 후보는 `approved_plan_sha`로 해당 실행안 전체에 직접 묶인다. Planning-only 준비 검사의 남은 blocker는 새 명시적 Native 승인 하나다. K48/Actual/Fresh가 없는 이 경로는 최종 M2를 먼저 만들기 위한 것으로, 통합 캠페인 물리 Gate를 생략한 PASS 선언이 아니다.

기존 Native 원장은 318.681/360초, A1 전용 원장은 사용 50.622초 그대로다. 그 잔여분을 후속 권한으로 전용하지 않았다. Actual/AC/모델 구성 Wall Time은 Native와 구분해 기록한다. 현 단계의 릴리스 상태는 **연구 검증 및 실행 준비를 담은 Candidate**이며, 새 D0 Full96와 May31은 예산·현재 Case 검증 대기다.

## 보존·회귀·전달

원본 Source13, Source11, Source/Raw, 기존 A1 성공점, MESS 코어, 역사 진단과 테스트를 보존했다. RC01은 커밋 6a12d503a의 Source 23개 및 전달 artifact 180개의 Git blob/현재 bytes와 27개 gzip 원본 복원을 다시 확인했다. 새로운 대형 Raw는 원본을 삭제하지 않고 64 MiB 이하 원문 조각별 gzip으로 전달하며 전체 복원 크기·SHA256을 검증한다.

**FINAL_REGRESSION_AND_SOURCE_FREEZE_TO_BE_INSERTED_AFTER_VERIFICATION**

모든 변경은 기존 `codex/v42-trajectory-tracking-may01-20261014` 및 Draft PR230에만 전달한다. 새 브랜치/Worktree/PR, 새 Heavy Native 실행 또는 외부 worker 종료를 하지 않았다.
