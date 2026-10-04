# Lane B 최종 검토

1. 기준은 Draft PR #143 exact head `ce5d30fb9bcb91ab8395d1313e868d24f5fde517`이다. PR143 head를 작업 시작과 게시 직전에 조회하여 동일 SHA를 확인했다. 병렬 lane의 작업은 merge/rebase/cherry-pick하지 않았다.
2. 새 branch는 `codex/v42-m1-branch-and-price-framework-prep`, Draft PR은 [#145](https://github.com/BeaverVillage/MobileESS/pull/145)다. 검증된 구현 게시 commit은 `f49b7ce180bba4246eb2829492615ddefbf2049a`이며 뒤따르는 게시 메타데이터 commit의 최종 SHA는 PR head와 외부 게시 영수증으로 확인한다. PR은 OPEN/DRAFT이며 merge하지 않았다.
3. 신규 소스는 `v42_bap/__init__.py`, `state.py`, `adapter.py`, `solver.py`, `fixtures.py`, `lexicographic.py`, `verify.py`이며 테스트는 `tests/v42_bap/test_framework.py`다. 보고서·증거는 이 문서와 같은 디렉터리에 있다. 기존 production/scientific 소스의 변경은 0개다.
4. 재사용한 D-W 인터페이스는 기존 matrix `build`, `Block.price`, `column`, `exact_coupling`, `hash_column`, `Master.add`, `exact_rc`, `corrected_rows`, native physical validator, `global_dual`, 4-MESS `corrected`다. 정확한 참조는 `BAP_EXISTING_INTERFACE_AUDIT.md`에 기록했다.
5. Node는 ID/parent/depth, immutable branch decisions, inherited/inactive/current column IDs, certified LB, RMP objective, pricing status, incumbent association, fathom reason, creation order, node SHA와 bound/terminal certificate를 저장한다. best-bound queue의 tie는 depth, node_id 순서다.
6. 위치는 원본 time-network (site,t)에서 outgoing stay/travel arc 합이다. 이동은 원본 travel arc binary다. 모든 원본 arc/mode binary도 후보여서 fractional charge mode를 숨기지 않는다. 0.5에 가장 가까운 fractional 후보를 우선하고 family/MESS/time/site-or-arc로 결정적으로 정렬한다.
7. Node-local pricing은 전체 원본 local 모델을 복사하여 branch equality만 추가한다. domain pruning은 없다. 기존 reduced-cost convention을 그대로 호출한다. Phase I로 불완전 inherited RMP를 복구하며, restricted infeasibility를 node infeasibility로 오인하지 않는다.
8. Child는 parent pool을 branch-compatible/inactive로 분할한다. global registry의 column bytes를 삭제하지 않는다. 새 column은 원본 rows, exact integrality, 물리 semantics/SOC/PCS16/travel, branch, coupling와 reduced cost 검증 후 추가한다.
9. Global LB=min(open-node certified LB), UB=독립 검증된 original integer incumbent, gap=(UB-LB)/max(abs(UB),1e-12)다. unknown LB가 있으면 acceptance를 금지한다. 여러 open node의 0.4%/2% gap 및 0.5% threshold를 검증했다. RMP 목적값을 LB로 대입하지 않는다.
10. Node infeasible, LB dominance, independently certified integer projection, no-improving pricing+integral, explicit fixture stop의 이유를 구분한다. TIME_LIMIT/INTERRUPTED만으로 fathom하지 않는다. explicit stop은 global acceptance를 차단한다.
11. Checkpoint는 fsync+atomic replace로 registry/queue/tree/completed/incumbent/global LB/counters/base/code/node SHA 및 bound certificates를 저장한다. 복원 시 column·tree·queue·incumbent·bound를 재검증한다. D fixture는 별도 stdlib-only writer가 atomic replace 직전 exit 23으로 실제 종료돼도 기존 checkpoint가 보존되고, 복원 후 동일 tree/optimum을 얻었다. crash child solver 호출은 0이다.
12. P1이 global gap과 incumbent 검증을 통과한 뒤 P2 callback을 허용한다. 기존 `mess_groups` 순서 movement_energy→movement_count와 P1_EPS=1e-7/COMPONENT_EPS=1e-8를 재사용한다. reserve/rank/tie는 목적함수로 추가하지 않았다. production P2 호출은 0이다.
13. 필수 A~E fixtures는 모두 통과했다. 추가로 global Phase-I infeasibility와 full-local infeasibility를 검증했다.

| Fixture | Direct MILP = complete master = B&P | Tree nodes |
| --- | --- | --- |
| A: 1 MESS / 2 slots / 2 sites | 0.5 | 1 |
| B: 2 MESS / coupled capacity | 0.875 | 3 |
| C: SOC + movement | 0.6 | 1 |
| D: location branch | 0.875 | 3 |
| E: movement branch | 0.875 | 3 |

14. 모든 비교는 목적값 허용오차 1e-8 이내 일치했다. B&P의 동일한 최적 full physical projection을 direct MILP와 complete master에 각각 고정하여 공통 최적 witness의 feasibility와 목적값을 확인했다. degeneracy 때문에 서로 다른 solver의 임의 mode 선택이 같다고 주장하지 않았다.
15. 모든 toy binary 분기의 child feasible-set union=parent이고 intersection=empty임을 exhaustive enumeration으로 검증했다. 각 binary pattern의 모든 continuous polytope vertex를 열거해 lambda mixture까지 보존했다.
16. 원본 pricing rows/bounds/types가 보존되고, branch rows를 통과하는 exhaustive trajectory set이 branch-compatible set과 동일함을 확인했다. 실제 native pricing optimum도 동일 node/dual의 exhaustive minimum과 비교했다.
17. 최종 fixture batch는 160회의 순차 tiny solve, 최대 37 vars/143 rows, 최대 wall 0.001541초, optimize wall 합 0.067429초다. 모든 solve Threads=1, Lane-B 동시 solver process<=1, TimeLimit<=25초/하드 wall<=30초다. 단위 테스트를 포함한 journal은 380 calls, 최대 0.001596초다. 네 번의 개발 fixture batch는 수정 후 재검증이며 parameter sweep이나 benchmark가 아니다. 최초 두 batch는 journal 이전 실행으로 동일 hard guard를 통과했다.
18. Full-scale M1/RMP/pricing/Arc-LP/B&P/96-slot tree, production A1/A2/M1/M2, May production, Fresh OpenDSS 호출은 모두 0이다. Lane A 상태/프로세스/산출물을 변경하지 않았다.
19. Lane-B unit tests 23 passed, bounded fixtures PASS, compileall PASS, JSON syntax PASS다. Repository-wide `python -m pytest -q`는 Lane A heavy 계산과 경합 방지를 위해 유예했다. 기존 DW 테스트의 production matrix fixture도 실행하지 않았다.
20. 모든 변경이 새 isolated 경로라 A/C/D와 직접 충돌 위험은 낮다. 향후 통합은 기존 Blocks/Master 및 full original incumbent 재구성·검증과 production node-domain bound certificate validator를 공급해야 한다. 현재 guard는 large model을 거부하며 production 실행 권한/성능/과학적 acceptance를 증명하지 않는다. 기존 코드의 정확한 변경 line은 없음이다.

```text
BAP_FRAMEWORK_IMPLEMENTED=true
BAP_FULL_SCALE_RUN=false
BAP_PRODUCTION_RUN=false
BAP_BRANCH_RULE_BASELINE_IMPLEMENTED=true
BAP_NODE_LOCAL_PRICING_IMPLEMENTED=true
BAP_COLUMN_INHERITANCE_IMPLEMENTED=true
BAP_CHECKPOINT_RESTART_IMPLEMENTED=true
BAP_TOY_FIXTURES_PASS=true
BAP_DIRECT_MILP_EQUIVALENCE_PASS=true
FULL_PYTEST_DEFERRED_DUE_PARALLEL_HEAVY_LANE=true
MAY_PRODUCTION_CALLS=0
```

이번 Lane B는 Branch-and-Price full-scale 계산을 실행하지 않고,
PR143 scientific contract와 호환되는 framework와 bounded exact
fixtures만 구현했다.

Lane A의 heavy Arc-LP/D-W 계산과 자원 경합을 피하기 위해
Threads=1의 small fixture 외 heavy Gurobi solve를 실행하지 않았다.
