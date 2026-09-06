# 최종 다음 revision 결정

RUNTIME_NEXT_REVISION = HYBRID_PREDICTOR_CALIBRATION_ROBUST
REACTIVE_NEXT_REVISION = RETAIN_FIXED_PF

근거: COMPLETED point underprediction64.13%, mean+7,064s; subgroup q90/current q5.346배;12h conditional regime mismatch; metadata-linked multiple runtime regimes와 heavy positive-residual tail. Point redesign + condition-aware upper bound + robust reserve/envelope를 연구 대상으로 결합한다.

Missing authority: final encoder/tree state와 leaf별 인과 attribution,12h matched-family validation, correlation-aware coverage 검증. Raw status mix와 support count만으로 FAILED effect를 증명하지 않았다. COMPLETED/FAILED를 feature로 사용하지 않는다.

Reactive baseline은 fixed PF0.95 유지. 이것이 물리적으로 충분히 정확하다는 판정은 아니다. TIME_VARYING_EXOGENOUS_PF_REQUIRES_DATA; CONTROLLABLE_Q_REQUIRES_EQUIPMENT_AUTHORITY. 독립 facility P/Q와 UPS/STATCOM P-Q capability/control interval 전에는 자유 Q 변수 금지.

이 결정은 다음 연구 방향이며 model/q/PF/도메인/정책 변경이나 실행 승인이 아니다. May Actual fitting/calibration/tuning NO. May-01은 더 이상 untouched blind evaluation으로 주장하지 않는다.

31_DAY_ELECTRICAL_REGENERATION=HOLD; B2_B3=NO; FULL_MAY=NO; MODEL_RETRAINING=NO. Final forensic commit 이후에도 자동 재개하지 않는다.
