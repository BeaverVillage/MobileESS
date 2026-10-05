1. Baseline retained: 새 15개, 1,604 → 1,619개 (MESS01–04: 4/4/4/3).

2. Challenger retained: 새 21개, 1,604 → 1,625개 (6/8/4/3).

3. Harvested MIPSOL candidates/MESS: Baseline 8/7/6/5, Challenger 8/13/6/5. 모두 negative proposal 관측; admission은 별도 audit.

4. 검증된 distinct negative columns/MESS: Baseline 6/6/4/3, Challenger 6/10/4/3. 독립 physics PASS candidates: 각각 7/7/5/4, 7/11/5/4.

5. Captured trajectory duplicate / exact projection duplicate / strict dominance 제거: 두 방식 모두 0/0/0. Challenger postsolve 재관측 duplicate는 6/10/4/3으로 신규 column 수에서 제외했다. Batch cap으로 제외한 distinct valid candidates는 Baseline 4개, Challenger 2개이며 duplicate로 계산하지 않았다.

6. Baseline pricing: native 합계 63.759466s, batch wall 22.425645s; retained/native pricing minute 14.115551.

7. Challenger pricing: native 합계 52.044584s, batch wall 18.409992s; retained/native pricing minute 24.210012. MESS02는 K=8 quota 종료, MESS01/03/04는 OTHER_NATIVE_RESERVATION guard로 조기 종료됐다.

8. Baseline RMP: 69.354135s, OPTIMAL, original matrix/primal audit PASS.

9. Challenger RMP: 35.974112s, OPTIMAL, original matrix/primal audit PASS.

10. Baseline audited upper: 0.5741861223241257 → 0.574115768594322; 감소 0.00007035372980368493.

11. Challenger audited upper: 0.5741861223241257 → 0.5741155437914072; 감소 0.00007057853271852377.

12. Baseline audited upper improvement/wall-sec: 4.377775424151859e-7 (total wall 160.706576s).

13. Challenger audited upper improvement/wall-sec: 6.164804630897311e-7 (total wall 114.486244s). 조기 종료된 pricing을 포함한 관측값이므로 공정한 성능 우위나 채택 근거로 사용하지 않았다.

14. Sampled peak tree RSS / min available RAM / max commit: Baseline 10.993GiB / 8.772GiB / 45.493%; Challenger 10.932GiB / 9.113GiB / 44.586%. 정확한 연속 peak가 아닌 sampling 결과다. Guard가 foreign PID/call context를 저장하지 않아 실제 다른 Lane optimize나 원인을 단정하지 않는다.

15. Scientific equivalence PASS; lightweight exact fixtures 10/10 PASS (0.46s); 전체 admitted 36개 invalid=0. Original 12,919 tracked files와 terminal 2,033 hash bindings 보존, 동일 checkpoint/duals/seed/domain/settings. Certification 코드는 원래 controller로 위임되며 변경되지 않았다. 전체 inherited pytest 재실행은 수행하지 않았으며 신규 검증 범위는 fixtures와 독립 matrix/semantic audit다.

16. MICROBENCHMARK_INCONCLUSIVE; MULTICOLUMN_SELECTED=false. 관측 효율은 개선됐지만 3개 pricing의 guard 조기 종료로 acceptance 비교의 독립성이 부족하다. 최신 process 지시는 두 benchmark 종료 후 도착했고, 이후 마무리를 process 존재 때문에 대기시키지 않았다. Historical guard receipts는 보존했고 재실행하지 않았다.

17. Draft PR [#153](https://github.com/BeaverVillage/MobileESS/pull/153); publication evidence commit/remote SHA `b6fe074e570211b945dfb83e6937f548dbd3eefd` 일치, evidence tree와 PR152 tree clean. 후속 report/manifest commit의 최종 remote SHA/clean은 최종 응답에서 확인한다. 전체 tracked child diff check PASS; raw native logs byte 보존; SHA256_MANIFEST 제공.

18. AUTHORITATIVE_ROOT_CONTINUATION_NOT_RUN; authoritative continuation calls=0, Certification calls=0, historical budget consumption=0. 각 leg 정확히 1 Discovery + 1 RMP, 총 8 pricing + 2 RMP; native receipt charge 221.1339035/600s (Baseline 133.1144430, Challenger 88.0194605). 자동 연장/second round/replay=0. PR152 authoritative interval [0.5687115725336208, 0.5741861223241257], threshold 0.5737116104747505, CG convergence=false, materiality INCONCLUSIVE 유지.

19. BRANCH_AND_PRICE_NOT_RUN; Branch-and-Price calls=0, May production=0/0/0, 다른 Lane kill/terminate/edit=0. Microbenchmark 결과를 authority에 합치지 않고 이 작업의 계산을 종료했다.

PR152의 1,604-column checkpoint는 immutable baseline으로 보존했으며, 동일 checkpoint의 read-only copies에서 기존 방식과 multi-column 방식을 각각 정확히 1 Discovery round + 1 RMP로 비교했다.

이번 실험은 최대 600초의 development microbenchmark이며, 결과를 authoritative D-W root certificate에 합치지 않았다.

선택 기준은 raw column 수가 아니라 audited upper-bound improvement per wall-clock second였다.
