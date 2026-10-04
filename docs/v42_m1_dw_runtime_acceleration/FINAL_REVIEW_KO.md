# Lane C 최종 검토

1. 기준은 PR143 exact head `ce5d30fb9bcb91ab8395d1313e868d24f5fde517`이며 1,158개 retained registry를 보존했다.
2. Draft PR: [https://github.com/BeaverVillage/MobileESS/pull/144](https://github.com/BeaverVillage/MobileESS/pull/144). 최초 게시 SHA `aa03e3ff3b7b2fcba9385a8eb97dd616e2deabd6`의 원격 일치와 clean tree를 확인했다.
   브랜치 `codex/v42-m1-dw-runtime-acceleration-prep`의 Draft PR과 게시 SHA는
   DW_PUBLICATION_RECEIPT.json 및 PR의 현재 head를 확인한다. 최종 head는 후속 게시 기록
   커밋을 포함하므로 `git ls-remote origin refs/heads/codex/v42-m1-dw-runtime-acceleration-prep`가
   최종 SHA 권위다. 게시 후 사용자에게 최종 SHA를 별도로 보고한다.
3. DiscoveryController가 실제 MIPSOL에서 original local/physical audit, exact integrality,
   same-iteration true RC를 검사한다. 적법한 신규 SHA 4개에서만 terminate를 요청한다.
4. smoothed-only negative, 중복 및 기존 SHA, 물리/정수 실패는 quota에 포함하지 않는다.
   native 종료는 협력적이며 quota 이후 callback이 와도 수락은 4개로 고정된다.
5. true RC <= -1e-7, immutable dual SHA/iteration 검사를 유지했다. INTERRUPTED는
   OPTIMAL·no-negative certificate·pricing convergence로 해석하지 않는다.
6. MESS별 candidate batch를 최대 4개 Python thread로 검증하는 구조를 구현했다.
7. 56개 synthetic observation에 대해 순차/병렬의 수락·거부 SHA,
   reasons, true RC, physical residual이 정확히 동일했다. 실제 full-size validator는 실행하지 않았다.
8. Tier 1은 신규 후보 full audit, Tier 2는 매 RMP 현재 point + 신규/무효화 열,
   Tier 3은 Certification/final checkpoint 전체 retained pool audit로 구성했다.
9. scientific base/matrix, local row/variable axis, validator version, physical semantics,
   numerical tolerance SHA의 정확한 일치만 재사용한다. RC는 매 반복 다시 계산한다.
   기존 receipt에 신규 스키마 키가 없으면 재감사가 필요하다.
10. PersistentRMP는 모델 객체와 열 추가 구조만 보존한다. reset(0), LPWarmStart=0을
    적용하며 이전 VBasis/CBasis를 읽거나 import하지 않았다. warm-basis 선정은 false다.
11. 4개 toy 반복에서 행·열·nnz·행렬·RHS·senses·bounds·objective identity가 같고,
    해와 dual은 절대 허용오차 1e-8에서 일치했다.
12. Python 재구성·Gurobi build·열 update·optimize wall/native Runtime을 분리 기록했다.
    단일 toy 수치이며 production 배속 주장은 없다. early-stop toy도 속도 개선을 입증하지 않는다.
13. 기존 객체를 dispose하고 디스크 registry로 재구축한 simulated restart에서 같은 목적값,
    해·dual·행렬을 복구했다. 실제 process kill 시험은 수행하지 않았다.
14. 기존 Certification source는 byte/Git blob identity를 유지한다. 실제 기존 corrected 함수의
    exact Fraction 계산과 invalid INTERRUPTED receipt 거부를 회귀 검증했다.
15. 네 feature flag는 기본 false이며 독립적으로 helper에 전달한다. 기존 production runner는
    이 PR에서 연결하지 않았다. 환경변수만 설정하면 기존 runner가 변경되는 구조가 아니다.
16. 단일 Gurobi process, Threads=1, fixture당 TimeLimit=5 s. fixture optimize 11회,
    Lane C test optimize 11회는 모두 작은 모델이며 순차 실행됐다.
    관측 RSS 최대 104.69 MiB(호출 전후 표본), memory stress 없음. 공유 Lane A 프로세스는 측정하지 않았다.
17. Full-scale M1/Arc-LP/pricing, production RMP/OpenDSS, May 호출은 모두 0회다.
18. Lane C 31개 테스트 PASS, compileall/static diff 검사 PASS.
    FULL_PYTEST_DEFERRED_DUE_PARALLEL_HEAVY_LANE=true로 repo-wide pytest는 유보했다.
19. 변경은 별도 helper/test/evidence에 한정했다. A/B/D merge/rebase 없음. 후속 통합 시
    worker callback·snapshot transport, run batch/audit/RMP 경로의 변경 충돌을 점검해야 한다.

이번 Lane C는 PR143 scientific model과 Certification semantics를
변경하지 않고 Discovery runtime을 줄이기 위한 실행 구조만
구현했다.

Full-scale M1/Arc-LP/pricing은 실행하지 않았으며 Lane A의 heavy
계산과 자원 경쟁을 만들지 않았다.
