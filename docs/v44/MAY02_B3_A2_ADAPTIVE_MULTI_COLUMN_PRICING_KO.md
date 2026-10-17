# May02 B3 A2 Adaptive Multi-Column Pricing r024a

기록 UTC: 2026-10-17T16:20:55.498575+00:00; Case: D:\MobileESS_V44\runtime\v43_planning_svr12_actual_v1\campaign004\2025-05-02\B3\attempt007; PR: https://github.com/BeaverVillage/MobileESS/pull/233

사용자 지시로 r022 attempt005를 Native 비실행 경계에서 중단했다. 667호출/567.3849945068359초와 Raw/Trace/로그/원장은 보존했고 중단 분류는 USER_REQUESTED_ALGORITHM_REVISION_STOP이다. 마지막 행 검사 완료 Phi는0.0011475893025559441이었다. 기존13 PASS와 완료된 May02 B1 A1 및 B3 M1은 SHA 검증하고 재최적화하지 않는다.

r024의 최초 attempt006은 Native0/0호출 모델 준비 중 프로파일 wrapper 메타데이터 연결 오류를 발견해 중단했다. 봉인 r024는 보존하고 Profile.wrap의 __wrapped__ 메타데이터만 보완한 운영 수정본 r024a로 attempt007을 시작했다. 탐색/선택/물리 인증 로직은 r024와 동일하며 해당 실제 wrapper 경로 회귀를 추가했다.

r023의 정확한 sparse 재조립/행 생성/활성행 대응/Full Phi/prior inclusion/물리옵션 및 원래 raw primal/dual 인증을 상속한다. 과학 원본은 그대로이며 별도 봉인 r024a 어댑터에서 Phase I 탐색과 선택만 바꿨다. P1 본문은 원본과 동일하다. 허용치 Full Phi1e-8, 원본 잔차1e-6, 독립 Gap0.5%, M2 및 Actual/Fresh 정책은 유지한다.

기존 상위 전체16+이동가능16 클래스 휴리스틱에 최소8개 미탐색/오래 미탐색 클래스를 순환 추가한다. 행 검사 완료 Full Phi의 실제 감소율이 연속2회15% 미만이면 탐색을 확대하고3회이면 전체 Eligible 탐색을 수행한다. 전체 탐색 뒤 한 라운드 쉬고 필요 시 다시 넓히며, 감소가 좋아도5회 주기의 전체 탐색으로 굶는 클래스를 방지한다. 모든 LP마다 전체 탐색하지 않는다. 실제 eligible 클래스 ID, 현재/누적 coverage와 각 클래스 oracle/physical recovery 영수증을 남긴다. 전체 Class 탐색은 모든 물리 옵션/혼합 LP의 Pricing Closure와 다르다.

모든 생성 후보는 원래 Native Query, 원본 물리 membership/local primal/exact coupling/현재 원시 dual의 정확한 음의 RC 검증을 통과한다. 추정 영향도와 음의 가격 강도를 함께 쓰고 클래스/사이트/시간대/종류 다양성을 보상하며 GPU시간 중복을 감점하는 다중열 배치를 선택한다. STAY/Migration이 모두 있으면 양쪽 후보를 포함하되 어느 동작도 실제 해에 강제하지 않는다. 배치는 휴리스틱이며 feasible/optimal 인증이 아니다. 원본 전체 모델에서 재최적화하고 신규 전압 위반 및 동일 원본 행/동결 가중치의 Full Phi 변화를 확인한다.

각 행 검사 완료 후 R024A_ACTUAL_FULL_PHI_FEEDBACK.json에 이전/현재 Full Phi, 실제 감소율, 이전 배치/RC, 전압 행·slot/node/phase·원본 선형 단위 부족량·현재 AIDC resource 값·고정 M1 P/Q·LP Native 시간을 남긴다. A-stage slot24는 M-stage slot0에 대응한다. 전압 민감도와 GPU/Deadline/STAY/Migration 여유는 R024A_VIOLATION_GUIDANCE.json에 탐색 순위용으로만 저장한다. 선형 행 부족량을 AC pu로 바꾸어 보고하지 않는다. Dual 변화는 진단만 하며 안정화 dual은 추가하지 않았다.

기존의3회 미소 감소 뒤 새 batch를 재최적화하기도 전에 종료하던 분기는 확대 배치를 실제로 평가하는 진단으로 바꿨다. 모든 호출은 동일5400초 예산 안에 남는다. 후보가 없다고 불가능을 주장하지 않고 NOT_CERTIFIED로 분류한다. 고정 M1의 LP 불가능성은 전체 원본 LP/정확한 완전 Pricing/엄밀한 양의 Phase I 하한 없이는 인증하지 않는다.

| 측정 | 중단 r022 attempt005 | 새 r024a |
|---|---:|---:|
| 전체 A2 Native 초 | 567.3849945068359 | 0.0 |
| 전체 A2 Wall 초 | 5719.335952599999 | 1.3800017768517137e-05 |
| 최대 Master 행 | 129350 | None |
| 최대 변수 | 118245 | None |
| 최대 측정 RSS bytes | 12667404288 | None |
| 누적 Pricing Class | 기존 초기37LP 시점35/138; 종료 시점은 원본기록 | 0 |

새 Native0 시작 admission: True; A1/M1 새 Native0회; M1 plan SHA: 0d1bec449f5110dfd76c82265bc98fefa4fb0e8a691445a6f11f660d303eaf10. Full Phase I: False; P1: False; A2: RUNNING; Gap: 미인증; M2: 미실행; Actual/Fresh: 미완료.

B1 A1/A2와 B3 A1/A2 공통 scope이며 실제 캠페인은 B1 A1 및 B3 A2에서 사용한다. 이후 미실행 Case에도 현재 A2 PASS 조건 없이 적용한다. A2 인증 후 기존 K48_M2→M2→Actual→독립 Fresh96으로 이어진다. 시간별 Codex 점검과 케이스 오류 격리·다음 날짜 진행 정책을 유지한다.

검증·배정 영수증: OPS/R024A_CHANGE_AND_VALIDATION.json, R024A_SEALED.json, RECOVERY_R024A_EXECUTION_PERMIT.json, R024A_CURRENT_A2_STOPPED.json, R024A_FRESH_A2_RESTARTED.json, 새 Attempt/PARENT_VERIFICATION/R024A_PARENT_COMPATIBILITY.json. 미완료 인증과 미측정 전체 A2 개선은 주장하지 않는다.
