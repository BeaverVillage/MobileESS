# IEEE8500 May-1 final verified campaign

BG 0.552 / AIDC absolute 2.40 / MESS 2.00 (600 kW, 800 kVA, 2400 kWh per vehicle). Original paper PCC.

All four policies: DA exact, Fresh exact and original Actual PASS, including independent Actual replay.

| Policy | Planning rho | DA exact | Fresh | Actual | DA Vmin/Vmax | Actual Vmin/Vmax |
|---|---:|---:|---:|---:|---|---|
| B0 | 0.946912268 | 0.946912268 | 0.946912268 | 0.944061254 | 0.951582/1.041775 | 0.955309/1.041342 |
| B1 | 0.945892078 | 0.945894690 | 0.945894690 | 0.943463580 | 0.952107/1.041774 | 0.955468/1.041273 |
| B2 | 0.928071819 | 0.930048418 | 0.930048418 | 0.933177577 | 0.957273/1.048264 | 0.952880/1.050000 |
| B3 | 0.924155151 | 0.926287579 | 0.926287579 | 0.930493346 | 0.953866/1.045449 | 0.953058/1.044787 |

## Reductions (absolute pu; percentage points = pu x 100)

| Difference | DA exact | Actual |
|---|---:|---:|
| B0_minus_B1 | 0.001017578 | 0.000597675 |
| B0_minus_B2 | 0.016863850 | 0.010883677 |
| B0_minus_B3 | 0.020624689 | 0.013567908 |
| B2_minus_B3 | 0.003760839 | 0.002684231 |

DA and Actual naturally satisfy B0 > B1 > B2 > B3. Actual B0-B3 is 1.356791 percentage points; the earlier 5-10 percentage-point screening aspiration was not achieved.

## Runtime scope

| Policy | Recorded DA-stage seconds | Meaning | Actual controller seconds |
|---|---:|---|---:|
| B0 | None | DA runtime unavailable | 14.976621627807617 |
| B1 | 15239.785133099998 | AIDC worker; excludes Actual | 29.345178842544556 |
| B2 | 308.252372500021 | Last restoration attempt ONLY; not full B2 | 14856.938714027405 |
| B3 | 64820.0175280571 | Sum A1/M1/A2/M2 stage wall times; excludes Actual | 524.0548164844513 |

B2 calendar elapsed from saved STARTED to final DA COMPLETE: 51450.218 seconds, including interruptions, repairs and waiting. The original report's 308.252 seconds is only the last restoration attempt; do not cite it as total B2 runtime.

## Electrical and MESS details

- B0 DA critical witness: `Line.tpx21459660c0|t2|sx3101194c.1.2|node1`, slot 75 (stored index). DA transformer current/kVA: 0.282644308/0.287231582; Actual: 0.274113374/0.278562564.
- B1 DA critical witness: `Line.tpx21459660c0|t2|sx3101194c.1.2|node1`, slot 75 (stored index). DA transformer current/kVA: 0.282386961/0.287043070; Actual: 0.274359356/0.278842798.
- B2 DA critical witness: `Line.tpx21459660c0|t2|sx3101194c.1.2|node1`, slot 75 (stored index). DA transformer current/kVA: 0.727353530/0.726172774; Actual: 0.726712414/0.726262303.
  DA MESS max |P|=428.272866 kW, max |Q|=465.689420 kvar, SOC=0.444254557 to 0.828834427.
- B3 DA critical witness: `Line.tpx21459660c0|t2|sx3101194c.1.2|node1`, slot 75 (stored index). DA transformer current/kVA: 0.841302640/0.833666646; Actual: 0.844283579/0.833681857.
  DA MESS max |P|=504.787922 kW, max |Q|=426.121983 kvar, SOC=0.409528248 to 0.767431022.

B3 Actual had zero Q-intervention slots. Physical actuator P was not reoptimized. B3 completed independent A1/M1/A2/M2. Original paper MESS termination applies; no global optimality proof is claimed.

## Certifications

```ini
PAPER_PCC_CONFIG_USED = TRUE
BG_SCALE = 0.552
AIDC_ABSOLUTE_SCALE = 2.4
MESS_SCALE = 2.0
RESITING_USED = FALSE
FEEDER_MODIFIED = FALSE
AIDC_DOUBLE_SCALING = FALSE
B2_SEARCH_DOMAIN_CHANGED = FALSE
SCALE_ONLY_CHANGE = TRUE
```

Full separation closure PASS; 44 sparse certificates rehashed and checked, each covering 31,945,536 logical rows.

Original scientific outputs, failed attempts, logs and checkpoints remain preserved. FINAL_REVIEW_20260923.json records SHA-256 evidence and explicit evaluation/runtime scopes.
