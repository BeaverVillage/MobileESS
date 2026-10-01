# PR112 MIP start와 B3-first certificate

Exact base PR112 `c90525c330c2f8aa9971030b87cf154ecf1b284f`. 실행 전 checkpoint는 B3_EXECUTION_MARKER.json의 execution_commit에 동결되어 있다. 원 preregistration은 보존하고, 신규 결과 전에 작성한 SCOPE_CORRECTION_ADDENDUM.json으로 unconditional B1/B2/B3 rerun을 B3-first sequential gate로 수정했다.

Best validated original-M1 UB=0.591281263433, best original certified LB=0.572212503944, implied global gap=3.22498964%. Native B3가 complete 96-slot start를 `0.591281263433`의 initial incumbent로 받아들였다. 별도 full-binary acceptance/prod solve는 하지 않았다. 모든 original binaries가 integer인 accepted initial vector는 full original matrix/physical/grid 검증을 통과했다.

- B1: NOT_RUN_GATE_B2_INCONCLUSIVE; status=NOT_RUN_GATE_B2_INCONCLUSIVE; new native BestBd=None; partial optimum interval=[0.571849462550, 0.591281263433], width=0.019431800883; material=False, negative certificate=False (INCONCLUSIVE).
- B2: NOT_RUN_GATE_B3_INCONCLUSIVE; status=NOT_RUN_GATE_B3_INCONCLUSIVE; new native BestBd=None; partial optimum interval=[0.571849462550, 0.591281263433], width=0.019431800883; material=False, negative certificate=False (INCONCLUSIVE).
- B3: RUN; status=9; new native BestBd=0.5718504565144596; partial optimum interval=[0.571850456514, 0.591281263433], width=0.019430806919; material=False, negative certificate=False (INCONCLUSIVE).

분류: **CASE_E_INCONCLUSIVE**. Native start acceptance와 P1/P2 production acceptance는 별개다. M1_ACCEPTED=false, PROBLEM13_FINAL_VALIDATED=false, production/P2/downstream=false.

Feasible sets: F_original_integer ⊆ F_B3 ⊆ F_B2 ⊆ F_B1 ⊆ F_F3. 검증된 stronger feasible upper는 weaker arm으로 전달할 수 있고, weaker lower bound는 stronger arm으로 전달할 수 있다. B3 BestBd를 B1/B2 lower bound로 전달하지 않는다. S2는 original-M1 reference LB이며 partial optimum interval의 floor로 사용하지 않는다. OPTIMAL 또는 좁은 interval만으로 nonmaterial이라고 부르지 않고, partial upper-S2<=0.001 여부를 확인한다.

Effective partial lower bound에는 동일 model의 inherited PR112 bound가 포함된다. LOWER_BOUND_PROVENANCE_AUDIT.json과 dual CSV에 new raw BestBd를 별도로 표시하므로, inherited bound를 신규 solve의 bound 개선으로 오인하지 않는다.

기존 native 중복 row 이름은 MPS alias로 바뀌어도 모든 행의 순서/계수/RHS/sense가 정확히 일치한다. 첫 두 prepare assertion과 당시 산출물을 PREPARE_ATTEMPT_HISTORY.json 및 prepare_before_scope_correction/에 보존했다. 이 과정의 optimization 호출은 0이다.

Joint solver strategy는 결과 전에 한 번 사전등록했다. 4 threads에 따른 성능 우월성을 주장하지 않는다. certificate의 유효성은 feasible-set inclusion, native solver bound, 독립 feasibility/domain 검증에 근거한다. Solver builtin cuts는 최적화 과정이며 새 handmade formulation cut은 추가하지 않았다. [Gurobi parameters](https://docs.gurobi.com/projects/optimizer/en/current/reference/parameters.html), [MIP starts](https://docs.gurobi.com/projects/examples/en/current/overview/starts.html).

FINAL_REVIEW_KO.md, OPTIMUM_INTERVAL_SUMMARY.csv, PRIMAL_QUALITY_COMPARISON.csv, DUAL_BOUND_COMPARISON.csv를 함께 읽는다. SOURCE_MANIFEST.json/EXECUTION_FREEZE.json은 source를, VERIFICATION.json은 matrix/domain/gate와 preserved bytes를 검증한다. inherited 44 bounded checks를 재실행하거나 수정하지 않고 receipt/source hashes를 검증했다.

B3의 남은 optimum interval을 먼저 줄여 positive bound 또는 가까운 validated partial upper certificate를 확보해야 한다. 현재 증거로 route/mode/trajectory cut을 선택하지 않는다. 새 original-integer start는 보존하되 추가 arm·fallback·production을 자동 실행하지 않는다.
