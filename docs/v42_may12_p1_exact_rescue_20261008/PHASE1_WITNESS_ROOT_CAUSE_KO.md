# May12 witness 오류의 원인과 복구

실제 source HEAD는 1b891dbe5b1dd454d89b657efec7cba469c0cf94였다. 기존 실행은 Phase-I에서 멈추지 않았다. Full-row Phi가 0.0362344419 → 0.0164196204 → 0.0046485901 → 0으로 감소했고, 세 round에서 STAY96개와 migration96개를 활성화했다. P1 restricted LP 0.669016629와 full130 pricing도 끝났으며 92개의 정확히 검증된 음수 블록을 추가하는 단계에서 Python 검증기 오류가 났다.

`v42_a_stage_canary.phase.activate`가 원래 P1 점에 artificial을 0으로 붙인 뒤, 새 후보로 row coefficient scale이 달라진 elastic master와 artificial weight 동일성을 비교했다. 40개의 global row에서 80개의 artificial weight가 바뀌었고 signs는 동일했다. 실제 prior Phi는 0이고 원본 primal은 feasible이었다. Solver가 infeasible이라고 판정한 사건이 아니다.

실제 저장 모델과 pricing 방향을 재구성하여 같은 ValueError를 재현했다. 먼저 실제 May12 regression test가 기존 코드에서 실패하는 것을 저장하고, 이후 P1 activation을 artificial-free original inclusion 검증으로 수정했다. 양수 Phi의 원래 frozen weight/sign 검사는 유지했다. Original coefficient/RHS/bound/objective/tolerance는 변경하지 않았다. 기존 perspective concrete columns도 rebuild에 보존했다.

모든 신규 작업은 독립 D: tree에서 진행됐다. Native source는 별도 freeze에 기록된다. 원본 May12/May10 증거와 실행 source/cache/input은 바꾸지 않았다. Exact dyadic replay는 전체 새 original rows에 대해 수행했으며 fixture 통과와 실제 대규모 모델 검증을 별도로 기록했다.

성능 개선은 완료된 285회의 native solve와 192 concrete columns/92 pricing directions를 재사용하고, graph union의 ledger를 매 열마다 전체 재계산하던 것을 batch당 한 번으로 줄인 것이다. 실제 130-class ledger와 source matrix 동치성을 확인했다. 새로운 initial build나 23회의 Phase-I를 다시 실행하지 않았다. Basis는 column/row axes가 바뀌므로 호환성 증거 없이 재사용하지 않았다.

추가 개선은 exact sum의 0항 제거, 완료된 full pricing의 Pi/행렬/RAW/hash/유리수 하한 재검증 후 재사용, 활성화된 다음 모델의 immutable checkpoint 재사용이다. 별도 shadow 검증에서 추가 concrete STAY 39,993개를 정확한 음수 가격과 full native A/B/bounds/cardinality 동치성으로 검증했다. 실제 추가 batch 활성화는 하지 않았다. S1 전체 pricing은 잠시76/130에서 다른 native 작업으로 중단됐으나, 사용자의 M 단계 종료 후 재개 지시에 따라 저장된 master/activation/pricing을 재사용해 130/130을 완료했다. 음수 블록이 없어 추가 활성화가 필요하지 않았다.
