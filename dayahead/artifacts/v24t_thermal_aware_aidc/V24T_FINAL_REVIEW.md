# V24T final review

RESULT CLASSIFICATION: `V24T_QUASISTATIC_THERMAL_MODEL_PASS_DYNAMIC_FAIL`

## READY FLAGS

- `NLR_POWER_AUTHORITY_READY = true`
- `NLR_WEATHER_AUTHORITY_READY = true`
- `MELBOURNE_ACTUAL_WEATHER_READY = true`
- `GFS_D1_FORECAST_READY = true`
- `FULL_GFS_CASE_STUDY_COVERAGE_READY = true`
- `THERMAL_POWER_BOUNDARY_READY = true`
- `QUASISTATIC_MODEL_READY = true`
- `DYNAMIC_THERMAL_MODEL_READY = false`
- `DYNAMIC_PUE_READY = true`
- `MARGINAL_PUE_READY = true`
- `COOLING_REBOUND_DIAGNOSTIC_READY = true`
- `MELBOURNE_THERMAL_EQUIVALENT_READY = true`
- `THERMAL_SCALE_REFREEZE_READY = false`
- `NEW_GRID_SCIENCE_RUN_READY = false`
- `FINAL_GRID_SCIENCE_AUTHORIZED = false`

## Data authorities

- Raw inventory: 111 files, 25397018808 bytes; source modifications 0.
- NLR aligned native 1-minute rows: 3778759.
- Power boundary: `BOUNDARY_B_NONOVERLAPPING_COMPONENT_SUM`; double count 0.
- NOAA Melbourne: station 94866099999 at -37.673333, 144.843333.
- GFS: 06Z f008–f032, 175/175 rows, full GRIB downloads 0.

## Thermal models (mean blocked CV)

| Model | Cooling WAPE | Facility WAPE | PUE MAE | Peak error kW | Lag error min |
|---|---:|---:|---:|---:|---:|
| C1 | 0.379337 | 0.019843 | 0.022103 | -43.278 | 53.2 |
| C2 | 0.379488 | 0.019992 | 0.022421 | -49.759 | 59.6 |
| LOAD_ONLY | 0.390944 | 0.020589 | 0.023096 | -51.027 | 56.3 |

C2 rho=0.997918835; tau=480.000 min (8.000 h); status `REJECTED`. Primary sensitivity: `C1_QUASISTATIC_ONLY`.

## Dynamic PUE and scale

Primary actual-weather PUE P05/P50/P95: 1.239835/1.301418/1.357451; IT-weighted mean 1.300000000000.
mPUE P05/P50/P95/peak: 1.361063/1.436823/1.501202/1.515325.
C0 frozen peak: 0.528808791957965 MW. Thermal-aware actual-weather peak: 0.543308821706109 MW. Difference: 0.014500029748144 MW. No force fit.

## Limitations

- NLR thermal response is transferred to Melbourne; it is not measured Melbourne cooling.
- Cooling-technology response is assumed transferable after dimensionless normalization.
- No site-specific Melbourne cooling plant model is available.
- Actual Melbourne metered PUE is unavailable.

## Final Q1–Q12

- Q1: YES — exact non-overlapping component boundary with rounded-PUE conservation PASS.
- Q2: YES — IT/load-only relation is useful, though blocked-fold error is material.
- Q3: YES — C1 relative WAPE lift over load-only is 0.029689.
- Q4: NO — C2 failed the pre-registered improvement gates.
- Q5: 480.000 minutes (8.000 hours); diagnostic because C2 was rejected.
- Q6: P05=1.239835, P50=1.301418, P95=1.357451, range=1.216603–1.371787.
- Q7: P05=1.361063, P50=1.436823, P95=1.501202, peak=1.515325.
- Q8: NO for primary C1: post-IT-peak rebound is zero; the natural cooling peak median is coincident with the IT peak (0 minutes) and PCC peak lag is 0 minutes. Rejected C2 synthetic step response is retained as a diagnostic.
- Q9: Diagnostic Tdb MAE=1.748 degC and Twb MAE=1.004 degC; not used for thermal fitting.
- Q10: Actual-weather dynamic peak differs by 0.014500030 MW from frozen C0.
- Q11: NO.
- Q12: NO.

Grid science may not start from this task. `FINAL_GRID_SCIENCE_AUTHORIZED = false`.
