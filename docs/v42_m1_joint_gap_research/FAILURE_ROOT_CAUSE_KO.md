# 실패 원인 및 다음 단일 연구

UB는0.6284141956452488→0.6063186498423855로 개선했지만, independently certified Global Gap 약6.3877251194%로0.5% 목표를 달성하지 못했다. 판정 UB_IMPROVED_LB_UNCHANGED, M1_ACCEPTED=false/P2=null이다. 전역 불가능성 및 실제 정수 최적값은 NOT_PROVEN이다.

R은 원본 grid 행을 삭제한 필요조건이어서 강화 자체가 아니다. count cover는 네 차량/두 시간의 정수 count를 완전히 포괄하고 저장 분수 배정을 제외하지만, direct P/Q·rho의 목표영역을 얼마나 축소하는지는 별도 문제다. Native TIME_LIMIT/dual 미가용과 원래 LP stationarity 인증 손실도 구조적 integrality gap과 구분한다. 새 certified LB 0.5675886811427069, fresh parent 대비 Δ=0.0로 실질적Δ≥0.001 강화는 NOT_PROVEN이다.

PR169 mode 재표시는 separator만 없애고 strict C3A/원본1e−8 잔차 검증은7행FAIL이다. 현재 count는 route고정이면auxiliary-only 회피가 불가능하지만, route를 재배분하면서P/Q를 유지하는 counterfactual은 NOT_RUN이다. 완료PR188의5child에서는 다른 차량 critical P/Q와10만개 이상의route좌표 재배분이 관찰됐다. 새leaf primal미저장 때문에 이번branch의cross-fleet회피를단정하지않았다.

과거 PR190 scalar D=.0130951605623203보다 private feasible support 하한합 .0342492521133151이 컸으므로 같은 방향·독립capacity합으로 모순을 반복하려하지않았다. PR182의대규모hull ROOT미완료 방향도재실행하지않았다.

UB의정수 운전 개선은 실제 역할교환과jointmode/PQ/SOC재최적화에서나왔다. 원capture는 scientifictol 3/3PASS/strict2/3PASS로분리하고 기존증거를보존했다. 같은rho의Native최종RAW전체binary0/1및physicalPASS를추가승인했으며repair0이다. 제한문제ObjBound를GlobalLB로 사용하지않았다.

다음단일우선연구는 full96슬롯 trajectory pricing과 여러 선로/시간P/Qdualvector를 결합한 희소column-generation relaxation이다. originalF포함 및 완전pricingclosure를 인증하기전 제한columns/masterbound를 GlobalLB로 사용하지않는다. 효과는 NOT_PROVEN이며 이번예산에서 추가Native실험을하지않았다.
