# Exact dense response audit — saved Source17 baseline

All counts come from the fresh saved FULL and C3A CSR/domain files for May 01. Source17 was not modified. No Native optimize/presolve, model rebuild, optimization bound, point, or MIP start was used. Dense values below are structural predictions awaiting integrated Source18 readback.

The supported change shares 14,890 exact repeated voltage expressions. Each selected group has one retained lower and upper inequality on the same stored full-coordinate vector. Replacing those two rows with one equality and one bounded continuous helper saves 14,890 rows and 698,341 NNZ while adding 14,890 columns. Prediction: **715,596 rows / 354,277 columns / 9,322 binary / 7,911,369 NNZ**. Original columns, objective and bounds remain unchanged. The mathematical extension is Y=a·x; projection discards Y. Both fractional LP and integer domains have the same projection.

Expression widths are 8–48 (mean 47.9). The sum of row-degree-square proxy savings is 32,765,107. This proxy is not measured Gurobi fill, factorization cost or root time. Native presolve can change this representation; its actual readback is required before a performance claim.

## All row families

| Row family | FULL rows | FULL NNZ | FULL degree min–max | C3A rows | C3A NNZ | C3A degree min–max |
|---|---:|---:|---:|---:|---:|---:|
| NormalAmps | 14,688 | 676,974 | 2–48 | 2 | 96 | 48–48 |
| PCS16 | 143,072 | 518,636 | 2–4 | 89,420 | 321,912 | 2–4 |
| connected_Pch | 8,942 | 17,884 | 2–2 | 8,942 | 17,884 | 2–2 |
| connected_Pdis | 8,942 | 17,884 | 2–2 | 8,942 | 17,884 | 2–2 |
| connected_Qmax | 8,942 | 17,884 | 2–2 | 0 | 0 | — |
| connected_Qmin | 8,942 | 17,884 | 2–2 | 0 | 0 | — |
| energy_balance | 384 | 217,638 | 27–602 | 384 | 217,630 | 26–602 |
| flow | 9,216 | 415,760 | 0–52 | 8,942 | 415,760 | 23–52 |
| initial_SOC | 4 | 4 | 1–1 | 0 | 0 | — |
| injection_P_binding | 2,304 | 20,188 | 1–9 | 2,263 | 20,147 | 3–9 |
| injection_Q_binding | 2,304 | 11,246 | 1–5 | 2,237 | 11,153 | 3–5 |
| line_thermal_face | 403,968 | 1,510,656 | 1–4 | 333,689 | 1,251,736 | 3–4 |
| no_simultaneous_charge | 8,942 | 17,884 | 2–2 | 8,942 | 17,884 | 2–2 |
| no_simultaneous_discharge | 8,942 | 17,884 | 2–2 | 8,942 | 17,884 | 2–2 |
| node_activity_link | 0 | 0 | — | 8,746 | 216,386 | 3–25 |
| response_line_P_binding | 25,152 | 1,232,138 | 46–49 | 25,152 | 1,210,659 | 9–49 |
| response_line_Q_binding | 25,152 | 1,232,344 | 48–49 | 25,152 | 1,210,862 | 9–49 |
| response_line_correction_binding | 25,152 | 1,229,260 | 47–49 | 25,152 | 1,207,844 | 9–49 |
| response_transformer_P_binding | 14,688 | 412,956 | 3–49 | 7,583 | 74,595 | 3–49 |
| response_transformer_Q_binding | 14,688 | 713,836 | 47–49 | 7,583 | 366,215 | 44–49 |
| terminal_SOC | 4 | 4 | 1–1 | 0 | 0 | — |
| terminal_location | 4 | 96 | 24–24 | 0 | 0 | — |
| transformer_kVA | 235,008 | 411,264 | 1–2 | 120,756 | 211,380 | 1–2 |
| voltage_lower | 80,448 | 3,861,338 | 47–48 | 17,033 | 815,477 | 8–48 |
| voltage_upper | 80,448 | 3,861,338 | 47–48 | 20,624 | 986,322 | 8–48 |

## All column families, fanout and used/dead auxiliaries

| Column family | FULL columns | FULL NNZ | FULL max fanout | C3A columns | C3A NNZ | C3A max fanout | C3A used/dead auxiliaries |
|---|---:|---:|---:|---:|---:|---:|---:|
| Pch | 8,942 | 160,956 | 18 | 8,942 | 107,304 | 12 | 0/0 |
| Pdis | 8,942 | 160,956 | 18 | 8,942 | 107,304 | 12 | 0/0 |
| Q | 8,942 | 152,014 | 17 | 8,942 | 124,637 | 1,113 | 0/0 |
| SOC | 388 | 776 | 2 | 380 | 760 | 2 | 0/0 |
| arc | 207,928 | 793,682 | 22 | 0 | 0 | 0 | 0/0 |
| charge_mode | 384 | 17,884 | 48 | 384 | 17,884 | 48 | 0/0 |
| injection_P | 2,304 | 6,555,957 | 2,858 | 2,263 | 2,890,005 | 1,316 | 2263/0 |
| injection_Q | 2,304 | 6,564,003 | 2,858 | 2,237 | 2,869,642 | 1,316 | 2237/0 |
| node_activity | 0 | 0 | 0 | 8,938 | 11,338 | 14 | 0/0 |
| response_line_P | 25,152 | 377,280 | 14 | 25,152 | 316,335 | 14 | 25152/0 |
| response_line_Q | 25,152 | 377,280 | 14 | 25,152 | 318,327 | 14 | 25152/0 |
| response_line_correction | 25,152 | 427,584 | 16 | 25,152 | 358,841 | 16 | 25152/0 |
| response_transformer_P | 14,688 | 220,320 | 14 | 7,583 | 113,241 | 14 | 7583/0 |
| response_transformer_Q | 14,688 | 220,320 | 14 | 7,583 | 113,305 | 14 | 7583/0 |
| rho_max | 1 | 403,968 | 403,968 | 1 | 333,689 | 333,689 | 0/0 |
| route_flow | 0 | 0 | 0 | 207,736 | 927,098 | 15 | 0/0 |

Fanout excludes the auxiliary’s own definition. Physical columns have no such definition to exclude. The CSVs enumerate every variable with its degree, fanout, defining NNZ, bounds and objective. JSON gives complete degree histograms and the family of each consumer. There are **0** safely dead unbounded zero-objective definition-only auxiliaries, before and after C3A. All 95,122 surviving affine auxiliaries are used.

C3A injection P/Q columns carry 5,759,647 NNZ and have maximum fanout 1,316 each. Line P/Q/correction binding rows retain 3,629,365 NNZ. Merely shortening the column list does not remove these couplings. Physical Q columns can already have degree 1,113 after exact static injection aliases.

## Exact expression sharing and substitution

FULL has one repeated identical affine-expression group:82 constant-zero injection definitions. Static reduction already removes that repetition. C3A has **0** repeated identical affine definitions on full stored column coordinates. Time-normalized signatures have fewer directions (90,729 versus 95,122 actual directions) but different slot coordinates; they cannot be merged as physical variables. Coefficient vector caching across construction slots is distinct from model expression sharing.

| Auxiliary family | C3A variables | Definition NNZ | Sum of one-variable substitution NNZ delta upper estimates | Negative cost candidates |
|---|---:|---:|---:|---:|
| injection_P | 2,263 | 20,147 | 19,958,327 | 0 |
| injection_Q | 2,237 | 11,153 | 8,551,970 | 0 |
| response_line_P | 25,152 | 1,210,659 | 12,287,073 | 0 |
| response_line_Q | 25,152 | 1,210,862 | 12,380,319 | 0 |
| response_line_correction | 25,152 | 1,207,844 | 14,229,555 | 0 |
| response_transformer_P | 7,583 | 74,595 | 736,407 | 18 |
| response_transformer_Q | 7,583 | 366,215 | 4,527,791 | 22 |

These costs evaluate each variable separately against the saved model, subtracting actual consumer/dependency support intersections. They are not a prediction of a combined simultaneous substitution. Response-to-grid consumers have disjoint physical/injection supports, so replacing reused line responses generally duplicates their dense expressions across many faces. Forty transformer response variables have a negative one-variable NNZ candidate cost, but **all 40** fail exact binary 64 coefficient/RHS representability. Their finite C3A bounds also need separate transport proof. No selective substitution is adopted.

## Rejected unit line basis

For Z=P+correction, exact substitution is oldP=Z−oldCorrection and the retained correction coefficient becomes actualStored(aCorrection)−actualStored(aP). Across all 25,152 line pairs, **0** thermal coefficients cancel and **0** pairs have every transformed coefficient exactly representable in binary 64. All 291,183 retained thermal P consumers have nonrepresentable exact differences. The P-binding row would additionally gain a correction entry for every pair, increasing NNZ by 25,152 even before any box transport. Every C3A pair has finite derived bounds; those cannot simply be discarded or copied to Z. The FULL model has unbounded pairs but still fails stored coefficient representability. No fresh trigonometric recomputation, small-sine approximation, near-zero cutoff or changed polygon is used.

## Stage authority and remaining unknowns

ALL_STAGE_DENSE_BASELINE_METRICS.json/.md contains Raw → PhysicalPrescreen → Compact → Security → Static → C3A → Dense counts, every row/column family count and NNZ, binary family counts and four-MESS domain counts. ALL_STAGE_PER_MESS_96_SLOT_METADATA.csv has all 2,688 stage/unit/slot records with terminal 96 stored separately in JSON. Raw is an analytic scalar incidence census of the accepted RouteArc time graph before existing constructor-forward screening; it is not an instantiated saved matrix. PhysicalPrescreen is saved FULL after that existing screen. Additional backward/SOC exclusions are 0. Raw Route Table records rejected by the inherited RouteArc time contract are not counted as physical model arcs.

Existing native logs report presolved aggregate 624,655 rows /339,287 cols /8,719,504 NNZ (66.00 s presolve), followed by root-relaxation 555,509 rows /396,854 cols /7,936,819 NNZ. No actual native presolved matrix/name map was exported. **Per-family native presolved counts are unknown**; aggregate log values are not used to infer family counts.

The stable Source18 sharing path passed independent source review, all 26 tests and 10 additional rejection attacks. SOURCE18_INDEPENDENT_DENSE_RESPONSE_REVIEW.json binds producer/verifier/test SHAs and exact Fraction projection checks including a 3/8 value on an original binary coordinate. This verifies LP fractional-domain preservation, not root performance. Current incremental physical prescreen gain is 0. Latest user steering nevertheless authorizes one fresh Root600 after all fresh physical/exact proofs and actual model compression PASS. Root controls a single live-case construction followed by fresh U4 and Full600; no additional Native call is performed by this audit.
