# V41R4 May-wide B0 screen: alpha 1.20, 1.15 and 1.10

**FROZEN_DAYAHEAD_MAY_WIDE_ELIGIBLE; selected alpha_BG = 1.15.**
All 31 dates from 2025-05-01 through 2025-05-31 evaluated at exactly the three new candidates. The previous validated replay function and prepared 780-GPU B0 inputs are unchanged.
93 isolated clean-engine trajectories, all 96/96 converged: 8,928 slots. Physical replay wall time: 52.2 seconds.

| alpha | May-wide | PASS / FAIL days | worst rho | worst Vmin | worst Vmax | worst transformer current | worst transformer kVA |
|---:|:---:|:---:|---:|---:|---:|---:|---:|
| 1.20 | FAIL | 28 / 3 | 0.886639007 | 0.971416541 | 1.050198759 | 1.018848922 | 0.862920612 |
| 1.15 | PASS | 31 / 0 | 0.849855762 | 0.974481884 | 1.049939479 | 0.976966990 | 0.825666205 |
| 1.10 | PASS | 31 / 0 | 0.813733298 | 0.974919302 | 1.049686000 | 0.935756163 | 0.791101909 |

Voltage is pu; loadings are fractions of unchanged nameplate ratings. No tolerance: voltage inclusive [0.95,1.05]; all thermal loadings strictly below 1.0.

| alpha | first failing day | constraint | asset / phase | slot (0-based) | value |
|---:|:---:|---|---|---:|---:|
| 1.20 | 2025-05-21 | TRANSFORMER_CURRENT | transformer.reg1a / A | 31 | 1.018848921955 |
| 1.15 | NONE | NONE | — | — | — |
| 1.10 | NONE | NONE | — | — | — |

## Distribution of 31 daily rho maxima

| alpha | min | mean | median | P75 | P90 | max |
|---:|---:|---:|---:|---:|---:|---:|
| 1.20 | 0.612071872 | 0.745817782 | 0.740069919 | 0.789414306 | 0.845289577 | 0.886639007 |
| 1.15 | 0.589869516 | 0.717025201 | 0.710479697 | 0.757584381 | 0.810452497 | 0.849855762 |
| 1.10 | 0.567927497 | 0.688133319 | 0.682809423 | 0.726308188 | 0.778595615 | 0.813733298 |

The mean is the arithmetic mean of 31 daily maxima, not the mean of all line/phase/slot samples. These statistics do not override the predeclared selection rule.

| Date | alpha 1.20 | alpha 1.15 | alpha 1.10 |
|:---|---:|---:|---:|
| 2025-05-01 | 0.739100128 | 0.710479697 | 0.682356908 |
| 2025-05-02 | 0.740069919 | 0.710097886 | 0.682809423 |
| 2025-05-03 | 0.641273089 | 0.617118849 | 0.596267941 |
| 2025-05-04 | 0.612071872 | 0.589869516 | 0.567927497 |
| 2025-05-05 | 0.647933758 | 0.624169451 | 0.598650960 |
| 2025-05-06 | 0.689451769 | 0.662813542 | 0.638316874 |
| 2025-05-07 | 0.717628104 | 0.690271453 | 0.663185688 |
| 2025-05-08 | 0.763717028 | 0.734508313 | 0.704824432 |
| 2025-05-09 | 0.753675766 | 0.723159909 | 0.693155893 |
| 2025-05-10 | 0.675803862 | 0.652622034 | 0.626839172 |
| 2025-05-11 | 0.661721856 | 0.639200137 | 0.614134634 |
| 2025-05-12 | 0.728306168 | 0.702821320 | 0.675065982 |
| 2025-05-13 | 0.743519471 | 0.713918241 | 0.686294549 |
| 2025-05-14 | 0.733917429 | 0.708078610 | 0.680115668 |
| 2025-05-15 | 0.771048275 | 0.739871885 | 0.709534722 |
| 2025-05-16 | 0.780083889 | 0.748793946 | 0.717637397 |
| 2025-05-17 | 0.703166121 | 0.674875946 | 0.645494133 |
| 2025-05-18 | 0.755463321 | 0.729374412 | 0.701007917 |
| 2025-05-19 | 0.833133545 | 0.800080784 | 0.767307451 |
| 2025-05-20 | 0.865919873 | 0.830196213 | 0.794616437 |
| 2025-05-21 | 0.886639007 | 0.849855762 | 0.813733298 |
| 2025-05-22 | 0.885393330 | 0.849749921 | 0.813234986 |
| 2025-05-23 | 0.845289577 | 0.810452497 | 0.778595615 |
| 2025-05-24 | 0.675889916 | 0.651079484 | 0.626582838 |
| 2025-05-25 | 0.671415899 | 0.647973173 | 0.621818728 |
| 2025-05-26 | 0.722127516 | 0.696193119 | 0.668073905 |
| 2025-05-27 | 0.802195965 | 0.769579455 | 0.737959849 |
| 2025-05-28 | 0.807369067 | 0.775114016 | 0.742565967 |
| 2025-05-29 | 0.798744723 | 0.766374817 | 0.734978979 |
| 2025-05-30 | 0.754059631 | 0.722900029 | 0.690761015 |
| 2025-05-31 | 0.714221373 | 0.686186821 | 0.658284037 |

## Authority and verification

Select the first all-31-day Day-Ahead B0 eligible candidate in priority 1.20, 1.15, 1.10; otherwise FAIL_CLOSE.

- Native/background P and Q scaled only; original spatial/phase/time shape and PF retained.
- PV, AIDC, MESS, ratings, impedances, topology, source voltage and native Day-Ahead regulator settings unchanged. MESS OFF.
- No B1/B2/B3, Actual replay, Gurobi or electrical coefficient regeneration.
- All per-day source/input records, strict counts, worst asset/phase/slot and full voltage/current/kVA/tap/capacitor trajectories are persisted.
- Re-read all 93 trajectory arrays; verified exact strict gates. 1330 previous screen files and 422 protected input/source files retain their SHA-256 hashes.
- Existing screen reports and authorities are preserved in their original directories.
- Full May policy optimization remains HOLD. No unrequested alpha is evaluated.
