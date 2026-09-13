# May06 IEEE8500 independent screening

**NO_FEASIBLE_B0_ON_USER_GRID** — 지정한 세 background alpha 모두 B0 exact AC hard limits를 위반했습니다.

- 날짜:2025-05-06; scope:Day-Ahead exact OpenDSS AC,96 chronological slots/case.
- source1.0400pu, all Vreg123.5V, CAPBank3 OFF. Native topology/ratings/PCC/controlled capacitor settings unchanged.
- AIDC scale1.00; MESS OFF for B0. Authorized later MESS fleet remains4×300kW/400kVA.
- PV interpretation adopted before screening: May06 forecast and B0 exogenous penetration ratio, with PV capacity fixed at inherited alpha0.50. Only native load P/Q varied with alpha. PV proportional-to-alpha was not tested.
- Comparison scope was provisionally Day-Ahead exact AC while the optional user scope question remained unanswered. No B1/B2/B3 ranking or scale selection was performed.
- This is outcome-conditioned exploratory screening; no general policy-superiority claim is made.

| αBG | AIDC scale | B0 max line(pu) | Vmin | Vmax | transformer current(pu) | winding kVA(pu) | feasible | runtime(s) |
|---:|---:|---:|---:|---:|---:|---:|---|---:|
| 0.60 |1.00| 1.028096850 | 0.950011171 | 1.041368592 | 0.268888672 | 0.271779494 |FAIL| 5.430 |
| 0.65 |1.00| 1.117175003 | 0.947794160 | 1.041288349 | 0.289803642 | 0.294369931 |FAIL| 5.581 |
| 0.70 |1.00| 1.202843592 | 0.934933338 | 1.041364486 | 0.314114098 | 0.317169053 |FAIL| 5.536 |

All288 slots converged and controls settled. Feasibility failed because of line overload; alpha0.65 and0.70 additionally had undervoltage. Runtime is per-case setup through96 solves and static checks, before output-array compression; preparation/source-hash validation excluded.

## Stop gate

No feasible alpha was selected. AIDC scales1.25/1.50, B1, B2, B3 and new Actual replays were not executed. Their values and adjacent differences are NA in BACKGROUND_SCREEN_TABLE.csv. No additional alpha, source, Vreg, capacitor or rating tuning was attempted.

## Critical witnesses

- alpha0.60: line witness `Line.tpx21459660c0|t2|sx3101194c.1.2|node1`, zero-based slot73; line violating slots=6, voltage violating slots=0.
- alpha0.65: line witness `Line.tpx21459660c0|t2|sx3101194c.1.2|node1`, zero-based slot72; line violating slots=14, voltage violating slots=4.
- alpha0.70: line witness `Line.tpx21459660c0|t2|sx3101194c.1.2|node1`, zero-based slot73; line violating slots=20, voltage violating slots=12.

## Preservation

All72 prebound model/input/helper files passed SHA256, size and mtime rechecks. Each case additionally verified unchanged static native/PCC definitions after restoring scheduled native loads. Existing May21 results and active B2 Actual/export processes were not modified, stopped or reused as May06 outcomes.
The PRE_EXECUTION_FREEZE.json and B0_STAGE_OUTPUT_SHA256.json remain unchanged. Raw voltage/current/kVA arrays, control states and per-slot extrema are retained under background_screen/.
