# 완료된 최종 M 연구의 V42 수용 계약

수용 기준은 마지막 완료 M HEAD `4b19e85089171729a3225529a40cb00bf31f43d5`이다. 진행 중인 연구의 작업파일, 임시 결과, 부분 certificate, 아직 완료되지 않은 branch HEAD를 통합에 사용하지 않는다. 통합 작업은 M 프로세스에 신호를 보내거나 다른 채팅을 재시작하지 않는다. 완료 결과를 기다리는 polling·자동 실행도 없다.

M 담당자가 연구를 완료하면 D:에 `V42_COMPLETED_M_HANDOFF_V1` manifest를 제공한다. 필수 필드는 `state=COMPLETE`, `baseline_completed_head`, 정확한 40자리 `completed_head`, `verified_changes`, `verification_evidence`, `preserved_scientific_hashes`이다. `verified_changes` 각 항목에는 Git 상대경로, 완료 커밋의 blob SHA256, `independent_verification_PASS=true`, `scope=RESEARCH_ONLY` 또는 `PROVEN_EXACT_FORMULATION`을 넣는다. verification evidence는 완료 커밋 안의 PASS JSON과 그 SHA256이어야 한다. 물리 소스, scientific objective/CSR/RHS/axes/types/bounds와 frozen input의 기존 해시를 명시하고 보존한다.

`M_HANDOFF_TEMPLATE.json`은 아직 완료되지 않은 상태의 양식이다. 공통 물리 두 파일과 원본 C3A matrix/data/start 다섯 필수 SHA256이 들어 있다. 이 필수 identity를 누락한 manifest는 checker가 거부한다. 새 formulation과 증거는 새 파일로 추가하며, 원본 authority 파일을 덮어쓰지 않는다.

1. 독립 D Clone에서 완료 커밋만 fetch한다. 예: `git fetch origin <완료된 40자리 HEAD>`. 원래 A/M 저장소나 진행 중인 worktree의 상태는 바꾸지 않는다.
2. `.\Start-V42.ps1 handoff-check -Handoff D:\completed_M_handoff.json`을 실행한다. ancestry, exact committed delta, 명시한 파일의 blob SHA256, 증거 PASS, scientific identity를 읽기 전용으로 검사한다. 이 명령은 파일을 import하거나 solver를 승격하지 않는다.
3. 검사된 변경 파일만 별도 검토한다. 전체 branch merge는 사용하지 않는다. 공통 소스 변경은 A 기준과 충돌 여부 및 물리·목적함수·허용오차 동치를 별도 재증명한다. 승인되지 않은 branch priority, Benders, 다른 solver, 과거 실패 실험 설정은 기본값에 적용하지 않는다.
4. 기존 v42 입력·증거를 보존한 채, 검토된 exact blob만 v42에서 적용한다. 새로운 연구 증거는 별도 하위 디렉터리에 저장한다. 기존 Native 시간·Work·실패 시도·Wall 기록을 수정하지 않는다.
5. `replay`, `build-only`, zero-Native 공통 테스트와 독립 P1-only interface 검증을 다시 수행한다. P1-only May12의 1,782 job/47 grid array authority에 M 결과가 실제로 결합됐는지 확인한다. May01의 1,499 job용 C3A point/LB/UB를 새 May12 결과로 전용하지 않는다.
6. 연구 결과가 nonmaterial 또는 gap 미달이면 코드·증거만 수용하고 `M1_ACCEPTED=false`를 유지한다. M1 인증에는 원본 integer/route/PQ/SOC/grid 검증, 올바른 전체 영역 LB 및 feasible UB, Global Gap≤0.5%, 필요한 M P2 인증이 모두 필요하다. 진짜 infeasibility 역시 independently checked mathematical certificate가 필요하며 TIME_LIMIT로 추론하지 않는다.
7. A2/M2와 운영 단계는 해당 정확한 입력의 M1이 인증된 뒤 실행한다. 모든 새 Native 비용을 단계별 5,400초 ledger에 누적하고 실제 모델 생성·검증 Wall을 분리한다. 전체 May B1 캠페인은 별도의 명시적 실행 지시가 있을 때만 실행한다.
8. 검증된 v42 integration commit을 만들고 clean 상태에서 `python -m v42_unified.delivery`를 실행하여 정확한 새 HEAD의 readiness receipt를 다시 생성한다.

현재 `V42_INTEGRATION_READY.json`은 통합 기반의 준비 완료를 뜻한다. M 과학 연구 완료, Global Gap 충족, 새로운 M1/A2/M2/Actual/Fresh AC 완료를 뜻하지 않는다.
