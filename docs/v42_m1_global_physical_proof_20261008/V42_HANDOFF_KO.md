# M1 검증 결과 및 단일 v42 통합 handoff

2026-10-08 11:09 UTC 조회 시 `refs/heads/v42`가 origin에 없었다. `git fetch origin v42`는 `couldn't find remote ref v42`로 종료됐고, `git ls-remote --heads origin refs/heads/v42` 결과도 비어 있었다. 따라서 `V42_INTEGRATION_READY.json`과 최종 통합 HEAD는 아직 확인할 수 없다. 이번에는 v42에 push하지 않았으며, 통합 회귀의 결과를 PASS라고 주장하지 않는다.

## 고정된 M 결과

- 원본 시작점: PR #188 exact HEAD `4b19e85089171729a3225529a40cb00bf31f43d5`.
- 검증된 M 실험 최종 HEAD: `a1a0b25df0daf2aca9512937516c073ddde01c97`.
- M 브랜치: `codex/v42-m1-global-physical-proof-20261008`.
- 이 문서와 조회 receipt는 위 실험 commit 이후의 handoff 기록이다. 최종 원격 브랜치 HEAD는 Draft PR 본문에 별도로 고정한다.
- 모든 신규 변경은 `v42_global_proof/`와 `docs/v42_m1_global_physical_proof_20261008/`에 있다. 파일별 변경 목록은 `HANDOFF_CHANGED_FILES.txt`에 보존했다.

판정은 **INCONCLUSIVE**이며 전역 불가능성 증명은 **NOT_PROVEN**이다. 기존 Global LB `0.5687116104049206`, 검증 UB `0.6284141956452488`, Gap `9.500515051068552%`를 유지한다. **M1_ACCEPTED=false**이며 production·P2·downstream 호출은 0회다.

Method A에서 `D(3/5)=0.01309516056232032`, 엄밀한 차량 지원능력 상한 합계 `ΣU=0.04450248238934866`이므로 전역 모순은 없다. 별도의 원본 차량 물리 exact feasible witness 합계 `0.034249252113315067 > D`를 독립 검증했다. 따라서 선택된 scalar 방향은 진짜 차량별 최대 지원량을 계산해도 분리할 수 없다. 이 witness는 coupled grid feasible counterexample이 아니다.

Method B의 단일 시점·두 시점·Hall 검사는 전체 4대의 모순을 증명하지 못했다. Method C는 원본 9,322 binary를 유지한 cutoff 한 번으로, TIME_LIMIT(status 9), SolCount 0, NodeCount 1, Runtime `1180.0360000133514`초다. 전체 cutoff 정수 영역은 미정이다. 신규 native 5회의 누적 Runtime은 `1213.108999967575`초이며 3,600초 예산을 지켰다.

모델 identity, 기존 UB의 원본 FULL replay, A/B certificate, 네 차량 native 결과, exact private-physics witness를 각각 독립 checker가 검증했다. 모든 receipt는 PASS이며 `FINAL_SCIENTIFIC_VERIFICATION.json`과 `SHA256_MANIFEST.json`에 최종 검증을 보존했다. frozen C3A·B2·A1·교통·Route Table 및 실행 중 producer/solver/예산은 변경하지 않았다.

## 신규 M delta 적용 절차

후속 개발 기준은 단일 `v42`다. 통합 준비가 완료된 뒤 최신 `origin/v42`의 실제 HEAD와 `V42_INTEGRATION_READY.json`의 완료 상태·검증 범위를 먼저 확인한다. 그 HEAD에서 **별도 임시 worktree**를 만든다. 기존 M 실험 worktree에서 solver를 다시 실행하거나 다른 작업의 checkout을 바꾸지 않는다.

검증된 과학적 M delta는 아래 세 commit이며 모두 PR #188 exact HEAD 이후 신규 namespace만 추가한다. 이후 handoff 기록과 바이트 보존 commit도 같은 namespace에만 변경한다. PR #188 자체나 다른 A/M 변경을 이번 delta로 중복 적용하지 않는다.

```text
91f0351f81a52b4ea5bceb6692d96f03ee56b917
ffaedbb59239bdfdcdfa9f5a12b5cde7b2f3ffdc
a1a0b25df0daf2aca9512937516c073ddde01c97
```

Draft PR 본문의 최종 M HEAD를 고정하고, PR #188 exact HEAD 이후 그 M HEAD까지의 **전체 M commit 범위**를 임시 worktree에 순서대로 cherry-pick한다. 과학적 commit 이후의 줄바꿈 바이트 보존 변경도 포함해야 저장 artifact와 manifest의 SHA가 checkout 후 일치한다. 예를 들어 고정한 M ref를 대상으로 `git cherry-pick 4b19e85089171729a3225529a40cb00bf31f43d5..M_REF`를 사용한다. 충돌이 발생하면 통합을 중지하고 handoff를 갱신한다. 원래 과학 모델의 source hash와 기존 authority가 동일해야 한다.

저장된 M 증거의 재검사는 아래 명령으로 수행한다. 모든 checker의 native optimize 호출은 0회다. **`cutoff`와 `vehicles` producer를 재실행하지 않고 ONCE token을 삭제하지 않는다.**

```text
python -m v42_global_proof.check_source_cutoff
python -m v42_global_proof.check_grid_capacity
python -m v42_global_proof.check_temporal
python -m v42_global_proof.check_vehicles
python -m v42_global_proof.check_local_exact_witness
```

그다음 v42 readiness 문서가 지정한 A/M 통합 회귀 전체를 검사한다. M checker PASS만으로 A/M 통합 PASS를 대체하지 않는다. 충돌이 없고 **모든** 검증이 PASS일 때만 최신 원격 HEAD를 다시 확인하고 `HEAD:refs/heads/v42`로 normal fast-forward push한다. 원격이 먼저 진행돼 push가 거부되면 강제 push하지 않고 다시 handoff한다. 실패한 실험 알고리즘을 production에 자동 승격하지 않으며 0.5% 인증 전까지 `M1_ACCEPTED=false`를 유지한다.

다음 과학적 병목은 66–95 critical 구간에서 네 차량 전체의 location/mode/PQ 선택을 동시에 포괄하는 multi-time cover다. 현재 Gap을 true integrality gap으로 단정하거나 TIME_LIMIT를 불가능성으로 해석하지 않는다.
