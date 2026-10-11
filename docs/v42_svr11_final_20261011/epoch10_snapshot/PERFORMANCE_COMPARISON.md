# SVR11 campaign performance comparison

IN_PROGRESS: 49/124 dates terminal.

Scientific Source SHA: `a113106e7bbfeb2ca3a0760e9dfb1ff479e0afa2d81a6bdcc71a250b23982f72`

Policy own PASS cohorts and paired same-date populations are separate. B0 has no MILP objective.

| Policy | Own PASS | Current FAIL | Actual peak line loading mean | Actual losses kWh mean |

|---|---:|---:|---:|---:|

| B0 | 31 | 0 | 0.7346894579860525 | 1597.3511744384796 |

| B2 | 17 | 1 | 0.6008141332681624 | 1508.2701634289217 |

| B1 | 0 | 0 | None | None |

| B3 | 0 | 0 | None | None |



Pairwise deltas use only dates where both policies PASS. A lower failure rate and a smaller mean on a different PASS population are not an unbiased policy comparison.



- B0 / B2: 17 common PASS dates; exact dates and numerical deltas in PERFORMANCE_COMPARISON.json.

- B0 / B1: 0 common PASS dates; exact dates and numerical deltas in PERFORMANCE_COMPARISON.json.

- B0 / B3: 0 common PASS dates; exact dates and numerical deltas in PERFORMANCE_COMPARISON.json.

- B2 / B1: 0 common PASS dates; exact dates and numerical deltas in PERFORMANCE_COMPARISON.json.

- B2 / B3: 0 common PASS dates; exact dates and numerical deltas in PERFORMANCE_COMPARISON.json.

- B1 / B3: 0 common PASS dates; exact dates and numerical deltas in PERFORMANCE_COMPARISON.json.



All failed attempts and measured/unknown Native Runtime remain linked, even when the final date attempt PASSes. May2025 is retrospective and is not an independent holdout.



All eleven banks and original seven RegControls operate jointly in each independent chronological Planning/Actual context. Per-phase tap ranges/change counts and full slot evidence are retained for joint response assessment. Series BUS82/BUS83 and upstream RegControl interaction remain possible; voltage PASS alone does not prove absence of interference. No comparative siting or isolated-control AC experiment was performed.
