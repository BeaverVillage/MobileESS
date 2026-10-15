MESS 공식 Adaptive Beam → 4-MESS Joint MILP → Original FULL → Incumbent Registry와 K48을 보존했다. 기준 490ff3ef7의 코어·Runtime/CC4·IEEE123/11 SVR/7 RegControl·물리 계약 및 기존 Native 원장 바이트를 비교했다. 기존 Git checkout CRLF 필터를 명시하고 raw blob SHA와 실제 checkout SHA를 각각 기록했으며 원본 파일은 다시 쓰지 않았다. 이번 감사는 모델 생성·solver 호출 0회다.

추가 정정11224a62를 적용한다. Scheduling/기본 최초 배치는 기존 방식이며 민감도는 Actual PENDING Pre-site만의 정책이다. May01 A1→M1→A2→M2→Actual96→Fresh AC가 모두 통과하기 전 Release Freeze로 승격하지 않는다.

Supervisor의 신규 D0 A1 P1은 1회, 50.622 Native초, Objective=Bound 0.64211779208034, Gap0, Original FULL PASS다. 신규180초 원장의 남은 129.378초는 다른 실험의 실행 권한이 아니다.

과거 PR223 M1/M2는 약 85.73/85.97 Native초, 146.05/148.47 Wall초로 반환됐다. 그 실행은 과거 Case의 warm witness 및 FULL 검증이며 새 D0 성공·소요시간의 증명이 아니다. K48 과거 180.036초와 Bound도 옛 exact Case만의 자료다. 새 D0 M1/A2/M2/K48는 미실행·예산 미승인이다. 제안은 M1 180, A2 120, M2 180, K48 180 단계별 누적 solve초와 각각 반환30+오버슈트30초이며, M1/M2 내부 4-Joint 단일 호출의 기존140초 상한을 유지하고 초기화·scoring도 단계 상한에 포함한다. P2/추가 호출은 자동 승인하지 않는다. 합계 900초는 승인 요청 상한안이다. 새 D0 Wall/성공시간 예측은 미인증이다.

May02·May10·May12의 원본 CC4 일별 행과 issue-time은 확인했다. 기존 모델 선택의 회고성·fit ingestion 미인증 한계는 남는다. 조사한 원본 트리에서 대표 날짜별 공인 D0 00:00 초기 상태를 찾지 못했다. May01 상태를 복사하지 않는다. 파일이 존재하는 날짜별 원래 Planning packet도 D0 초기 상태 승인으로 대체하지 않는다.

CAMPAIGN_BLOCKED_WITH_EXACT_REASONS: 후속 단계별 예산, 새 D0 M1/A2/M2·Actual96·Fresh AC, 대표일별 공인 초기 상태, 31일 계산 예산·Resume/Date Ledger gate가 필요하다. AIDC Canary의 실제 입장 및 계통 결과는 Agent A 자료로 별도 판정한다. 과거 UB/LB/Actual PASS는 이전하지 않는다.
