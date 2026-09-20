# IEEE8500 B0 fine background-scale feasibility search

**Production recommendation: 0.574.** B0 reference AIDC ON, MESS OFF; May01 D-1 demand/PV, PV alpha 0.50 and all spatial/control/rating settings preserved.

| scale | Vmin | Vmax | max line loading | transformer current | transformer kVA | AC | Vmin >= 0.9505 |
|---:|---:|---:|---:|---:|---:|:---:|:---:|
| 0.57 | 0.952073676 | 1.041520536 | 0.975766556 | 0.281268040 | 0.285811351 | PASS | YES |
| 0.572 | 0.951546713 | 1.041779822 | 0.979596181 | 0.282223181 | 0.286748507 | PASS | YES |
| 0.574 | 0.951018221 | 1.041738296 | 0.983426062 | 0.283180621 | 0.287687281 | PASS | YES |
| 0.576 | 0.950481193 | 1.041696711 | 0.987420660 | 0.284132295 | 0.288608966 | PASS | NO |
| 0.577 | 0.950215554 | 1.041676404 | 0.989339071 | 0.284613058 | 0.289079622 | PASS | NO |
| 0.5775 | 0.950083038 | 1.041789234 | 0.990301665 | 0.284853267 | 0.289315038 | PASS | NO |
| 0.578 | 0.949949988 | 1.041655575 | 0.991261376 | 0.285094013 | 0.289550612 | FAIL | NO |
| 0.579 | 0.949683607 | 1.041634732 | 0.993181362 | 0.285575946 | 0.290022059 | FAIL | NO |
| 0.58 | 0.949416850 | 1.041798047 | 0.995102102 | 0.286058468 | 0.290493901 | FAIL | NO |

```ini
MAX_FEASIBLE_TESTED_SCALE = 0.577500000000
FIRST_INFEASIBLE_TESTED_SCALE = 0.578000000000
RECOMMENDED_PRODUCTION_SCALE = 0.574000000000
RECOMMENDED_B0_PEAK_LOADING = 0.983426061675
RECOMMENDED_VMIN_MARGIN = 0.001018220599
```

Final tested feasibility bracket: [0.5775, 0.578], width 0.0005. This is a tested bracket, not a continuous mathematical maximum. Native discrete controls can be nonmonotone. Observed FAIL-to-PASS reversals: [].

Hard limits remain Vmin >= 0.95, Vmax <= 1.05, line/current/kVA <= 1.0 pu. The 0.9505 criterion is used only to recommend production margin, not to change hard PASS/FAIL. Recommendation chooses the greatest exact peak line loading among tested candidates meeting that margin.

## Boundary refinement

- [0.576, 0.578] -> midpoint 0.577: PASS
- [0.577, 0.578] -> midpoint 0.5775: PASS

## Witnesses

| Scale | Vmin node / slot | Peak line / terminal / local phase / slot |
|---:|---|---|
| 0.57 | sx2748781a.2 / 75 | Line.tpx21459660c0 / 2 / 1 / 75 |
| 0.572 | sx2748781a.2 / 75 | Line.tpx21459660c0 / 2 / 1 / 75 |
| 0.574 | sx2748781a.2 / 75 | Line.tpx21459660c0 / 2 / 1 / 75 |
| 0.576 | sx2748781a.2 / 75 | Line.tpx21459660c0 / 2 / 1 / 75 |
| 0.577 | sx2748781a.2 / 75 | Line.tpx21459660c0 / 2 / 1 / 75 |
| 0.5775 | sx2748781a.2 / 75 | Line.tpx21459660c0 / 2 / 1 / 75 |
| 0.578 | sx2748781a.2 / 75 | Line.tpx21459660c0 / 2 / 1 / 75 |
| 0.579 | sx2748781a.2 / 75 | Line.tpx21459660c0 / 2 / 1 / 75 |
| 0.58 | sx2748781a.2 / 75 | Line.tpx21459660c0 / 2 / 1 / 75 |

Recommended critical time: 2025-05-01T18:45:00+10:00 (0-based slot start, AEST). Forecast interval-end timestamp is 15 minutes later. Local phase is the raw OpenDSS node number; a triplex node 1 is not an inferred primary A phase.

## Preserved inputs and validation

- New independent contexts: 8, each with 96 sequential exact AC snapshots. Existing .580 reference reused with hashes verified. All candidates have 96/96 convergence and settled controls.
- source=1.04 pu; Vreg=123.5 V; CAPBank3 OFF; all other native controls unchanged. Native P/Q are multiplied by the background scalar uniformly.
- B0 workload/PCC P/Q are replayed unchanged; MESS P/Q remain zero. PV spatial allocation, alpha=.50 and temporal profile are fixed.
- Topology, bus/phase distribution, host/PCC locations, line/transformer ratings, coordinates and prior authorities are unchanged. Static/spatial hashes match the existing .58 run.
- B1/B2/B3 and scheduling optimization calls: 0. Authority promotion: none.

## Heatmaps and CSV

- Every tested candidate has `scale_<value>/B0_DAILY_MAX_HEATMAP.png`, including a newly rendered map of reused .580 raw results.
- Recommended scale also has `B0_CRITICAL_TIME_HEATMAP.png`.
- All maps use YlOrRd, 0–1 pu, the original .58 whole-feeder extent and original .58 detail viewport. No reflection, rotation, translation or scaling of coordinates.
- Daily map: maximum per physical line across all 96 slots and terminals/phases. Critical map: same system-critical slot for all lines, maximum terminal/phase per line.
- Final CSV schemas exactly match the preceding actual-B0 .58 CSV. All loading values are pu. Daily 3,703 rows; critical 12,317 rows; summary 1 row. Five disabled lines have empty loading and DISABLED status; all monitored values are finite.
- Critical CSV is terminal/phase-grained. Group by element_id and take max(B0_loading_at_critical_time) for one color per physical line.

## Candidate images

- [0.57 daily max](scale_0.57/B0_DAILY_MAX_HEATMAP.png)
- [0.572 daily max](scale_0.572/B0_DAILY_MAX_HEATMAP.png)
- [0.574 daily max](scale_0.574/B0_DAILY_MAX_HEATMAP.png)
- [0.576 daily max](scale_0.576/B0_DAILY_MAX_HEATMAP.png)
- [0.577 daily max](scale_0.577/B0_DAILY_MAX_HEATMAP.png)
- [0.5775 daily max](scale_0.5775/B0_DAILY_MAX_HEATMAP.png)
- [0.578 daily max](scale_0.578/B0_DAILY_MAX_HEATMAP.png)
- [0.579 daily max](scale_0.579/B0_DAILY_MAX_HEATMAP.png)
- [0.58 daily max](scale_0.58/B0_DAILY_MAX_HEATMAP.png)
