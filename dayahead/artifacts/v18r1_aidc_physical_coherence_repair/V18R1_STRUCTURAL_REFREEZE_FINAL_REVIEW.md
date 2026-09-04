# V18R1 AIDC Physical-Coherence Repair and Day-Ahead Causal Re-freeze

RESULT CLASSIFICATION: `B. V18R1_PASS_CAPACITY_TIMELINE_PARTIAL`

## READY

- `STRUCTURAL_REFREEZE_READY = true`
- `NEW_LOCKED_SCIENCE_RUN_READY = false`
- `KNOWN_QUEUE_EXTENSION_STATUS = UNAVAILABLE`

## 핵심 결론

V18의 **589.411 GPU**는 직접 관측된 allocation이 아니라 `gpus_requested`를 retrospective execution interval에 투영한 15분 평균이다. 원시 archive에는 AllocTRES/GRES allocation field가 없다. 528 초과 902 slot은 공식 132-node 정적 경계를 확장 이후까지 적용한 capacity-timeline mismatch가 주된 설명이며, 그 자체는 physical over-allocation 증거가 아니다.

Raw nodelist 감사에서는 source-infeasible event interval **37개**와 관련 job **76개**가 확인됐다. 어느 행이 오류인지 임의 선택하지 않고 전체 관련 job을 global conflict set으로 격리했다. 격리 후 exact-uniform nodelist execution은 node당 4 GPU 이내이며 ambiguous multi-node flow도 모두 feasible하다. clipping과 q99.5/u85 용량 승격은 0회다.

Kestrel-native repaired flexible GPU-hour share는 **36.779839%**다. 이는 facility 전력 비율이 아니다.

Main D-1 scope는 `FORECAST_NEW_FLEXIBLE_WORKLOAD_ONLY`이며 기존 running/queued와 기타 IT는 `REFERENCE_LOCKED_IT_RESIDUAL`에 남긴다. 미래 realized start/end main-feature read는 0회다. Retrospective queue oracle은 `NON_CAUSAL_RETROSPECTIVE_DIAGNOSTIC`일 뿐 모델/optimizer 권위가 아니다.

Training-only conditional tier mixture로 총 forecast GPU-hour를 FULL_1/2/4/8/16/PARTIAL에 분해했고 mass identity를 보존했다. Hybrid power를 적용한 7개 observed April diagnostic day의 facility flexible energy share는 **0.465931%**다. 이는 source-backed hybrid 전력과 engineering tier overlay의 결과이며 문헌 20-25% 보정 결과가 아니다.

시설 분해는 `P_IT_REF = REFERENCE_LOCKED_IT_RESIDUAL + P_FLEX_REF`를 모든 site/slot에서 만족하며, 최소 residual은 **13.001190 kW**, 최대 보존오차는 **2.842e-14 kW**다. PUE 1.30은 IT 합산 뒤 정확히 한 번 적용한다.

B0-B3, OpenDSS, 새 grid science result는 실행하지 않았다. 새 untouched locked test가 없으므로 structural re-freeze가 통과해도 새 science run은 승인되지 않는다.
