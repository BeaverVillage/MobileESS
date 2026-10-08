# 완료된 M 결과의 V42 연구 handoff

단일 개발 기준은 독립 D: clone `D:\MobileESS_v42`의 `v42`다. 이번 Native 실행 시작 HEAD는 `3019dd59ee70241407dc6f9e70016de1e67d9385`이며, 최종 정확한 HEAD는 clean commit 후 루트 `V42_INTEGRATION_READY.json`에 기록한다. 원래 PR186/188과 C: 작업공간·실험·프로세스는 재현용으로 보존한다.

1. 다른 M 작업이 실제 완료했음을 확인한 뒤 **완료 commit HEAD**, scientific input SHA, 원본 authority, 결과·검증·Native ledger를 받는다. 진행 중 checkpoint나 uncommitted 작업은 읽거나 채택하지 않는다. 완료되지 않았다고 종료·재시작하거나 완료로 간주하지 않는다. 자동 대기·무한 polling을 만들지 않는다.
2. 마지막 완료 M188 `4b19e85089171729a3225529a40cb00bf31f43d5` 대비 exact Git diff와 file SHA를 D clone에서 감사한다. PR190 실패 scalar 방향의 구현은 자동 후보가 아니다. 전체 실험 branch merge/force push를 하지 않는다. 변경분 중 검증된 source/evidence만 명시적으로 선택한다.
3. May01/1499-job/C3A 사례와 May12/1782-job/P1-only 계약을 구분한다. 같은 날짜·A1 anchor·Route/Grid/AIDC/battery·objective·tolerance·integer axis의 case SHA가 같아야 LB/UB를 결합한다. May01 결과를 May12의 인증값으로 사용하지 않는다.
4. 원본 전체 정수영역 포함과 coefficient/RHS/objective/bounds/type identity, 4대/96슬롯 route/SOC/mode/PCS/grid를 독립 재검증한다. Bound는 exact certificate와 complete leaf coverage/완전 pricing closure를 포함해야 한다. 제한 neighborhood/trajectory catalog의 bound, TIME_LIMIT primal objective, 단일 child bound는 Global LB로 승격하지 않는다.
5. UB는 실제 저장 Native RAW vector의 모든 원본 정수변수 literal0/1, 전체 원본 행렬과 unchanged physical checker를 통과해야 한다. 원 capture pool의 tolerance PASS를 strict PASS로 복사하지 않는다. 이번 U2 capture와 final RAW처럼 출처가 다르면 원 checkpoint를 보존하고 새 admission addendum으로 vector/file SHA를 연결한다. rounding/clipping/repair로 숫자를 바꿔 승인하지 않는다.
6. 새 최종 결과는 독립 checker 및 optimize=0 공통/원본 replay로 검증한 후 v42에 commit한다. 실행 중 모델·callback·파라미터·예산을 수정하지 않는다. 추가 Native가 필요하면 별도 명시적 실행으로 남은 합산 예산을 먼저 검증하고 safe phase boundary에서 수행한다. 과거 ledger를 초기화하거나 비용을 소급 이전하지 않는다.
7. Scientific 목표와 delivery 상태를 분리한다. P1 Gap≤0.5%라도 P2/downstream 조건이 없으면 `M1_ACCEPTED=false`다. Production `CommittedEvidenceBackend` 및 `integration_native_optimize_allowed=false`를 자동 승격하지 않는다. 이번 연구는 명시적인 `Start-V42-M1-Research.ps1 -Execute`에서만 Native를 수행했다.
8. `v42` 원격 HEAD를 감사하고 충돌이 없을 때 검증 변경분을 push한다. PR189를 갱신하며 같은 브랜치의 중복 PR을 만들지 않는다. clean tree와 동일 remote HEAD를 확인한 뒤 readiness에 정확한 통합 HEAD·case·proof·cost·테스트를 기록한다.

기존 [통합 handoff 계약](../v42_integration_20261008/FINAL_M_HANDOFF_KO.md)과 함께 적용한다. 이번 결과의 범위·미해결 상태는 [최종 검토](FINAL_REVIEW_KO.md)에 있다.

재현 명령:

- 기본 preflight: `./Start-V42-M1-Research.ps1` — Native0, 기존 완료 best의 전체 replay.
- 신규 명시적 연구: `./Start-V42-M1-Research.ps1 -Execute -RunId <새ID>` — 새 실행 승인 후 한 번만, 동일 ledger ID 재사용 금지.
- 완료한 원 실행의 strict approval view: `python -m v42_m1_research.final_admission runtime/v42_m1_joint_gap_research/joint_gap_20261008` — Native0, 새 view를 한 번 생성. 기존 checkpoint와 ledger 변경 없음.
- 저장 view independent replay: `python -m v42_m1_research.check_joint runtime/v42_m1_joint_gap_research/joint_gap_20261008_final_strict_admission_view` — Native0, 모든 증명을 original CSR에서 재계산.

모든 명령은 D: workspace 안에서 TEMP/TMP/cache를 D:로 설정하고 PYTHONDONTWRITEBYTECODE=1 및 OMP/MKL/OPENBLAS/NUMEXPR threads1로 실행한다. 과거 입력·목적함수·물리제약·허용오차를 유지한다.

새 D: clone에서 저장 증거만 재현하려면 `artifacts/registered_original/`의 원본 bytes를 `runtime/v42_m1_joint_gap_research/joint_gap_20261008/`으로 복사하고 SHA256_MANIFEST와 FINAL_ADMISSION_VIEW의 원본 파일 SHA를 먼저 검증한다. 그 완료 ledger로 Native runner를 다시 시작하지 않는다. 위 final_admission→check_joint의 Native0 경로만 사용한다. 최종 커밋·push·clean tree 확인 후 `python -m v42_m1_research.delivery_ready`로 통합 단계 Native0와 명시적 연구 단계 Native 비용을 구분한 readiness를 생성한다.
