# May19 Early Activation V2 최종 검토

분류: **PHASE1_TRACTABILITY_FAIL**. Stop: MATERIAL_PHI_INCREASE_INVESTIGATION.

이번900초 실험은 PR172의600초 결과를 수정하거나 연장하지 않았다. 검증된 구체적 경로만 활성화했으며, pool 후보는 모두 보존했다. 양의 Phi나 시간/크기 종료는 complete-domain infeasibility 증거가 아니다. LP closure와 integer closure, production acceptance는 별도다.

실제 heavy 실행은608.5489초에서 보수적인 조사 기준으로 종료되어900초를 소진하지 않았다. 이전 raw 해는 확장 모델에 그대로 포함되고 같은 Phi를 유지한다는 독립 replay가 PASS했다. 따라서6.73e-7 증가가 실제 최적값 증가를 증명하지 않는다. 세 번의 stagnation 조건도 충족되지 않았다.

이 발견 뒤 코드의 경미한 증가 처리만 보완했다. 이전 해의 포함 witness가 통과하면 다음 반복으로 진행하며, raw Phi를 바꾸거나 tolerance를 완화하지 않는다. 고정16/24 규칙과 세 번1% stagnation 규칙은 유지한다. 현재 코드124개 tests와 저장된 May19 witness replay는 PASS, 수정된 루프의 새로운 May19 native 검증은 미실행이다. 모든21개 실제 native 호출의 소스는ba1c9b2... archive이며, 현재 수정 코드는 기존 source permit에서 거부된다. 추가 실행에는 별도의 새 source freeze/예산이 필요하다.

1. **Exact base HEAD?** 92b8cc679e115673e0a29c71d0797013c4e08e57

2. **초기 Phi?** 0.006626776621085752

3. **Phase-I master solve 수?** 2

4. **Phi 궤적?** [0.006626776621085752, 0.006627449687993898]

5. **부분 가격 배치 수?** 1

6. **반복별 완전히 가격 계산된 클래스 수?** [('0', '17')]

7. **독립 검증 음수 구체 후보 수?** 16

8. **활성화된 후보 수?** 16

9. **STAY / migration 활성화?** STAY 16, migration 0

10. **certified Phi zero?** False

11. **Phi zero까지 시간?** None

12. **최종 original active 크기?** {'rows': 713105, 'cols': 83819, 'nnz': 13752921}

13. **최대 factor 크기 / 추정 메모리?** 16100000.0 nnz / 0.4 GB

14. **1-worker = 4-worker 정확 동등성?** True

15. **유효하게 측정된 pricing speedup?** May19 동일 배치의 serial 재실행을 하지 않았으므로 speedup 미측정; tiny fixture startup 포함 시간은 별도 receipt

16. **artificial-free 원래 active 모델 feasible?** False

17. **original P1 LP solved?** NOT_RUN_PHASE1_GATE

18. **P1 LP pricing closure?** False

19. **final150/150 closure 실행?** False

20. **영구 과학 후보 삭제?** NO

21. **physics / tolerance 변경?** NO

22. **old prescreen 복원?** NO

23. **May17 / May12 / May10 실행?** NO

24. **최종 분류?** PHASE1_TRACTABILITY_FAIL

25. **정확한 최종 HEAD?** 최종 공개 HEAD는 [FINAL_PUBLICATION_RECEIPT.json](C:/Users/kjw39/Documents/Codex/2026-10-07/v42-a-stage-early-static/FINAL_PUBLICATION_RECEIPT.json)의 exact_final_head에 기록. 실행 소스 HEAD: ba1c9b2ff63ea2b6be13ab06a601986eef82a775. 자기 commit 해시 순환참조를 피하는 외부 출판 영수증.

26. **Draft PR URL?** https://github.com/BeaverVillage/MobileESS/pull/174

실행 종료 후 새 native solve는 수행하지 않았다. 다른 날짜 및 full A1/Planning/Actual/Fresh는 실행하지 않았다. 최종 HEAD/remote/clean-tree 검증은 외부 출판 영수증이 고정하며, 각 native 실행 소스와 archive 해시는 NATIVE_RUN_SOURCES.csv에 별도로 고정한다.
