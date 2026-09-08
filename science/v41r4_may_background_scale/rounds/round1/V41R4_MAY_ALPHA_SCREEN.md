# V41R4 May-wide B0 background scale screen

**FAIL-CLOSE — no selected alpha_BG.** All 31 May dates were evaluated at exactly 1.35 / 1.40 / 1.45 / 1.50.
All 124 trajectories converged 96/96 (11,904 slots). Four isolated processes completed physical replay in 42.1 seconds. No coefficient generation, optimization, or additional alpha tests.

| alpha | May-wide | PASS / FAIL days | Worst day* | max rho | min V | max V | max transformer current | max transformer kVA |
|---:|:---:|:---:|:---:|---:|---:|---:|---:|---:|
| 1.35 | FAIL | 20 / 11 | 2025-05-22 | 0.993736392 | 0.967442662 | 1.050748452 | 1.150197616 | 0.970937433 |
| 1.40 | FAIL | 17 / 14 | 2025-05-21 | 1.029932114 | 0.968194016 | 1.051235896 | 1.193551749 | 1.006558330 |
| 1.45 | FAIL | 11 / 20 | 2025-05-21 | 1.067059050 | 0.967122145 | 1.051291752 | 1.235962340 | 1.042230293 |
| 1.50 | FAIL | 9 / 22 | 2025-05-22 | 1.101418251 | 0.965285188 | 1.056235160 | 1.282807254 | 1.080919645 |

*Worst day uses maximum normalized constraint utilization. Each metric above is its own campaign extremum; exact metric-specific dates and assets are in JSON. Voltages are pu; current and kVA are fractions of unchanged ratings.

## First failing day and limiting constraint

| alpha | First failing day | Constraint | Asset / phase | Slot (0-based) | Value |
|---:|:---:|---|---|---:|---:|
| 1.35 | 2025-05-08 | VOLTAGE_HIGH | 83.2 / B | 78 | 1.050025153617 |
| 1.40 | 2025-05-08 | TRANSFORMER_CURRENT | transformer.reg1a / A | 72 | 1.026353732091 |
| 1.45 | 2025-05-01 | VOLTAGE_HIGH | 83.2 / B | 81 | 1.050053940375 |
| 1.45 | 2025-05-01 | TRANSFORMER_CURRENT | transformer.reg1a / A | 72 | 1.019252007130 |
| 1.50 | 2025-05-01 | TRANSFORMER_CURRENT | transformer.reg1a / A | 72 | 1.054658577976 |

Voltage limits are inclusive [0.95, 1.05]. Line current, transformer phase current, and transformer total kVA must each be strictly below 1.0. No tolerance is applied.

## May-02 explicit direct OpenDSS recheck

| alpha | PASS | reg1a-A max current | reg1a-A max kVA | Bus83-B min V | Bus83-B max V | max line rho | system Vmin | system Vmax |
|---:|:---:|---:|---:|---:|---:|---:|---:|---:|
| 1.35 | YES | 0.950650453 | 0.800355776 | 1.033682527 | 1.049013634 | 0.827191182 | 0.976824143 | 1.049484601 |
| 1.40 | YES | 0.985366943 | 0.828700190 | 1.035809012 | 1.048929603 | 0.857680526 | 0.974205627 | 1.049261111 |
| 1.45 | NO | 1.019858013 | 0.857021041 | 1.036215179 | 1.049064865 | 0.887937326 | 0.971295297 | 1.049121828 |
| 1.50 | NO | 1.057043688 | 0.887860696 | 1.036383029 | 1.048867164 | 0.915300870 | 0.971109943 | 1.049010773 |

kVA is direct terminal total kVA divided by the frozen winding rating. These measurements do not use historical planning polygon kVA or linear scaling assumptions. The full 96-slot Bus83-B traces are in JSON and NPZ.

## Descriptive May stress distribution

| alpha | rho min | median | P75 | P90 | max | days ≥.70 | ≥.75 | ≥.80 | ≥.85 | ≥.90 | ≥.95 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1.35 | 0.679162263 | 0.827191182 | 0.881872974 | 0.946489762 | 0.993736392 | 30 | 25 | 20 | 10 | 6 | 3 |
| 1.40 | 0.702135934 | 0.857680526 | 0.913320526 | 0.981509690 | 1.029932114 | 31 | 29 | 23 | 17 | 9 | 5 |
| 1.45 | 0.725165724 | 0.887937326 | 0.945720748 | 1.013999323 | 1.067059050 | 31 | 30 | 26 | 21 | 13 | 8 |
| 1.50 | 0.745812664 | 0.915300870 | 0.976416981 | 1.049000973 | 1.101418251 | 31 | 30 | 29 | 24 | 18 | 10 |

These distributions did not override the predeclared largest-feasible-alpha rule.

## Selected-alpha diagnostics and downstream state

- SELECTED alpha_BG = NONE.
- Selected-alpha May-02 and May distribution = N/A.
- Selected-alpha Actual B0 = NOT EXECUTED; PASS/FAIL day counts and extrema = N/A.
- No alpha qualified. No Actual input or Actual result was used for selection.
- AIDC 780 unchanged = YES; AIDC power unchanged = YES; ML unchanged = YES.
- B1/B2/B3 used for alpha selection = NO; robust B1 executed = NO.
- Electrical coefficient regeneration = 0; May-04 scenario rebuild = HOLD.
- FULL MAY policy optimization = HOLD.
- Previous alpha=1.60 = DEVELOPMENT_HISTORICAL_ONLY; its original evidence is preserved.

## Verification and artifacts

- Recomputed 31 B0 GPU/IT/PCC arrays: bit exact with authoritative stored inputs. H4 physical cap remains 3120 GPUh.
- 422 protected source/input files retained their SHA-256 hashes; feeder asset hashes and every-slot regulator/capacitor settings were unchanged.
- Re-read all 124 NPZs; independently recalculated eligibility, counts, extrema, and quantiles. Verified strict threshold boundary behavior.
- May-04 alpha=1.40 and 1.50: bit exact with independently stored historical native-DA trajectories for every saved array.
- Every run saves regulator taps, capacitor states, full voltage/current/kVA arrays, losses, root P/Q and strict summaries under `replays/DAYAHEAD/`.
- All day × alpha results, source SHAs, metric-specific worst dates and descriptive distributions are in `V41R4_MAY_ALPHA_SCREEN.json`.
- The frozen negative selection is in `V41R4_MAY_WIDE_BACKGROUND_SCALE_AUTHORITY.json`.

## Daily maximum line loading and its May mean

Each daily value is the maximum measured line-phase loading over all lines/phases and the 96 quarter-hour slots. The mean below is the arithmetic mean of the 31 daily maxima, not the mean of all line/slot loading samples.

| alpha | Mean daily rho max | Median | Minimum | Maximum |
|---:|---:|---:|---:|---:|
| 1.35 | 0.832706604 | 0.827191182 | 0.679162263 | 0.993736392 |
| 1.40 | 0.861933861 | 0.857680526 | 0.702135934 | 1.029932114 |
| 1.45 | 0.891397185 | 0.887937326 | 0.725165724 | 1.067059050 |
| 1.50 | 0.920394685 | 0.915300870 | 0.745812664 | 1.101418251 |

| Date | alpha 1.35 | alpha 1.40 | alpha 1.45 | alpha 1.50 |
|:---|---:|---:|---:|---:|
| 2025-05-01 | 0.821718734 | 0.850173640 | 0.879348224 | 0.904760350 |
| 2025-05-02 | 0.827191182 | 0.857680526 | 0.887937326 | 0.915300870 |
| 2025-05-03 | 0.710804739 | 0.732074959 | 0.755666452 | 0.779400265 |
| 2025-05-04 | 0.679162263 | 0.702135934 | 0.725165724 | 0.745812664 |
| 2025-05-05 | 0.727932550 | 0.750739633 | 0.777565584 | 0.805944947 |
| 2025-05-06 | 0.767681331 | 0.795313398 | 0.822326940 | 0.850152522 |
| 2025-05-07 | 0.797777802 | 0.825466581 | 0.849722609 | 0.877960327 |
| 2025-05-08 | 0.849698700 | 0.880054477 | 0.909940489 | 0.936943341 |
| 2025-05-09 | 0.842357478 | 0.873401257 | 0.901423191 | 0.932052467 |
| 2025-05-10 | 0.749832255 | 0.775147260 | 0.800673473 | 0.826257986 |
| 2025-05-11 | 0.733587511 | 0.758105997 | 0.783069711 | 0.808004204 |
| 2025-05-12 | 0.812688614 | 0.840816327 | 0.866346120 | 0.894455022 |
| 2025-05-13 | 0.830493794 | 0.860465218 | 0.891335319 | 0.918509139 |
| 2025-05-14 | 0.819001801 | 0.847936909 | 0.877571917 | 0.905155546 |
| 2025-05-15 | 0.861619094 | 0.893545400 | 0.921923762 | 0.953235670 |
| 2025-05-16 | 0.872038368 | 0.901567273 | 0.933271902 | 0.965057406 |
| 2025-05-17 | 0.786472765 | 0.815485815 | 0.846306815 | 0.872836398 |
| 2025-05-18 | 0.843986164 | 0.870249587 | 0.899852395 | 0.929535442 |
| 2025-05-19 | 0.934522344 | 0.969222899 | 1.001853687 | 1.036638517 |
| 2025-05-20 | 0.971712040 | 1.005688422 | 1.041948046 | 1.078544585 |
| 2025-05-21 | 0.993736392 | 1.027938573 | 1.064768196 | 1.098638633 |
| 2025-05-22 | 0.992175472 | 1.029932114 | 1.067059050 | 1.101418251 |
| 2025-05-23 | 0.946489762 | 0.981509690 | 1.013999323 | 1.049000973 |
| 2025-05-24 | 0.750388095 | 0.776083349 | 0.801778202 | 0.827649225 |
| 2025-05-25 | 0.746179621 | 0.771673305 | 0.797524209 | 0.823437692 |
| 2025-05-26 | 0.807418215 | 0.835821730 | 0.861799518 | 0.890233306 |
| 2025-05-27 | 0.895730161 | 0.928692851 | 0.960786885 | 0.990662223 |
| 2025-05-28 | 0.902604760 | 0.931633825 | 0.964122270 | 0.997712616 |
| 2025-05-29 | 0.891707581 | 0.925073779 | 0.958169593 | 0.987776556 |
| 2025-05-30 | 0.848598202 | 0.880445846 | 0.913538057 | 0.946362431 |
| 2025-05-31 | 0.798596944 | 0.825873107 | 0.856517748 | 0.882785656 |

All four candidates remain May-wide FAIL. These descriptive statistics do not change eligibility or the frozen selection rule.
