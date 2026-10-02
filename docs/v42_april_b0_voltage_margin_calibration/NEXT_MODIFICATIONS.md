# 다음 작업

1. B0/C0 forecast 이름과 operational B0 baseline을 구분하여 정확한 B0 정책을 저장소 근거로 확정한다. MESS/AIDC 결정, known/unknown 처리, D-Day causal replay, forecast/Actual mapping과 schedule SHA provenance를 동결한다. 임의 fixed CC4 또는 anonymous LP schedule을 만들지 않는다.
2. B0 gate PASS 이후 target April 연도와 전체 paired forecast/realized coverage를 source SHA, timezone, resolution, missing/duplicate, causal availability로 감사한다. 실제 historical source가 있더라도 authority 없이 자동 승격하지 않는다. 전체 사용 가능일과 사전 제외 규칙을 실행 전에 동결한다.
3. resource snapshot 후 authorized S0 plan을 freeze하고 offline DA-AC와 동일 SHA의 D-Day Fresh AC를 실행한다. DA-AC fail은 plan 수정이나 operational gate를 유발하지 않는다. Actual P/Q·route·schedule repair와 재최적화는 금지한다.
4. 정확한 node-phase-time alignment, residual identity, directional residual, 모든 네 quantile의 pointwise/day-worst 통계, daily min/max/violations/worst identities, line/transformer 및 RMSE component dominance를 생성한다. S1/S2는 선택 sensitivity이며 S2 infeasible을 physical infeasible로 표현하지 않는다.
5. April 후보를 동결한 뒤 별도 May holdout validation을 수행한다. 이번 PR에서 May 실행·결과 기반 tuning·margin acceptance를 하지 않는다. B0 authority FAIL을 B1/Proposed로 대체하지 않는다.

현재 verdict는 BLOCKED_B0_ACTUAL_AUTHORITY다. Generic validators, 통계 unit fixture, header-only CSV는 과학 실험 결과가 아니다. 다른 architecture/Benders branch를 수정하지 않았다.
