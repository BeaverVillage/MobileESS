# V41R4 May-wide B0 screen: alpha 1.30 and 1.25

**FAIL_CLOSE_NO_MAY_WIDE_ELIGIBLE_ALPHA; selected alpha_BG = NONE.**
All 31 dates from 2025-05-01 through 2025-05-31 evaluated at exactly the two new candidates. The previous validated replay function and prepared 780-GPU B0 inputs are unchanged.
62 isolated clean-engine trajectories, all 96/96 converged: 5,952 slots. Physical replay wall time: 40.9 seconds.

| alpha | May-wide | PASS / FAIL days | worst rho | worst Vmin | worst Vmax | worst transformer current | worst transformer kVA |
|---:|:---:|:---:|---:|---:|---:|---:|---:|
| 1.30 | FAIL | 22 / 9 | 0.958612227 | 0.970917083 | 1.050819836 | 1.105323253 | 0.933223241 |
| 1.25 | FAIL | 23 / 8 | 0.921101769 | 0.971701815 | 1.050354339 | 1.063301231 | 0.897854437 |

Voltage is pu; loadings are fractions of unchanged nameplate ratings. No tolerance: voltage inclusive [0.95,1.05]; all thermal loadings strictly below 1.0.

| alpha | first failing day | constraint | asset / phase | slot (0-based) | value |
|---:|:---:|---|---|---:|---:|
| 1.30 | 2025-05-19 | TRANSFORMER_CURRENT | transformer.reg1a / A | 72 | 1.043342172540 |
| 1.25 | 2025-05-19 | VOLTAGE_HIGH | 83.2 / B | 81 | 1.050354339376 |
| 1.25 | 2025-05-19 | TRANSFORMER_CURRENT | transformer.reg1a / A | 72 | 1.003645332226 |

## Distribution of 31 daily rho maxima

| alpha | min | mean | median | P75 | P90 | max |
|---:|---:|---:|---:|---:|---:|---:|
| 1.30 | 0.656387576 | 0.803361337 | 0.797301244 | 0.850161049 | 0.911791690 | 0.958612227 |
| 1.25 | 0.634016840 | 0.774548365 | 0.769834015 | 0.818256255 | 0.879915905 | 0.921101769 |

The mean is the arithmetic mean of 31 daily maxima, not the mean of all line/phase/slot samples. These statistics do not override the predeclared selection rule.

| Date | alpha 1.30 | alpha 1.25 |
|:---|---:|---:|
| 2025-05-01 | 0.793247700 | 0.764436392 |
| 2025-05-02 | 0.797301244 | 0.769834015 |
| 2025-05-03 | 0.686068197 | 0.664218885 |
| 2025-05-04 | 0.656387576 | 0.634016840 |
| 2025-05-05 | 0.699983799 | 0.673877819 |
| 2025-05-06 | 0.743674335 | 0.716853575 |
| 2025-05-07 | 0.769802339 | 0.742527416 |
| 2025-05-08 | 0.820265840 | 0.793693222 |
| 2025-05-09 | 0.811915009 | 0.783982937 |
| 2025-05-10 | 0.727132637 | 0.702105901 |
| 2025-05-11 | 0.711598923 | 0.687172730 |
| 2025-05-12 | 0.784006214 | 0.756067423 |
| 2025-05-13 | 0.800643857 | 0.773242589 |
| 2025-05-14 | 0.791396248 | 0.761983960 |
| 2025-05-15 | 0.830524214 | 0.799558934 |
| 2025-05-16 | 0.840473946 | 0.809025089 |
| 2025-05-17 | 0.757679458 | 0.731567130 |
| 2025-05-18 | 0.813192110 | 0.784269809 |
| 2025-05-19 | 0.899942263 | 0.867518715 |
| 2025-05-20 | 0.935625666 | 0.899688879 |
| 2025-05-21 | 0.956852007 | 0.920359124 |
| 2025-05-22 | 0.958612227 | 0.921101769 |
| 2025-05-23 | 0.911791690 | 0.879915905 |
| 2025-05-24 | 0.727580899 | 0.702447321 |
| 2025-05-25 | 0.723176915 | 0.696438651 |
| 2025-05-26 | 0.778339837 | 0.750143402 |
| 2025-05-27 | 0.863560652 | 0.830940058 |
| 2025-05-28 | 0.869367751 | 0.837116979 |
| 2025-05-29 | 0.859848152 | 0.827487421 |
| 2025-05-30 | 0.815802533 | 0.786929817 |
| 2025-05-31 | 0.768407221 | 0.742476604 |

## Authority and verification

If 1.30 passes all 31 Day-Ahead B0 days select 1.30; else if 1.25 passes all 31 select 1.25; else FAIL_CLOSE.

- Native/background P and Q scaled only; original spatial/phase/time shape and PF retained.
- PV, AIDC, MESS, ratings, impedances, topology, source voltage and native Day-Ahead regulator settings unchanged. MESS OFF.
- No B1/B2/B3, Actual replay, Gurobi or electrical coefficient regeneration.
- All per-day source/input records, strict counts, worst asset/phase/slot and full voltage/current/kVA/tap/capacitor trajectories are persisted.
- Re-read all 62 trajectory arrays; verified exact strict gates. 853 previous screen files and 422 protected input/source files retain their SHA-256 hashes.
- Existing screen reports and authorities are preserved in their original directories.
- Full May policy optimization remains HOLD. No unrequested alpha is evaluated.
