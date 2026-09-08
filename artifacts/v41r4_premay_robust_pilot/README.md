# V41R4 physical-support pilot snapshot (draft)

This PR records completed pre-May calibration, the authorized PV physical-support correction, and existing May-04 B0/coefficient evidence. It is not a completed robust B1 implementation or an integrated runnable release.

S1 remains the complete 2025-01-29 residual bundle; S2 remains the complete 2025-03-12 bundle. Materialized PV is projected onto zero and the inherited installed capacity (698.000002861023 kW). No upper-bound clipping occurred. The archived selection authority is retained. The amended contract applies identically to every May evaluation day without policy or Actual-result tuning.

| Scenario | Negative/projected slots | Minimum raw PV kW | Clipped kWh | PV before/after kWh | Clipped/positive energy |
| --- | ---: | ---: | ---: | ---: | ---: |
| S1 | 2 | -2.532172 | 1.266086 | 1797.666435 / 1798.932521 | 0.070380% |
| S2 | 6 | -19.292372 | 19.014598 | 1692.967126 / 1711.981724 | 1.110678% |

Existing results: 119 historical days calibrated without historical optimizer, OpenDSS, or ML calls; physical-support audit PASS; May-04 S0/S1/S2 B0 preflight PASS (96 slots each); S0 coefficients reused, S1/S2 coefficient generation PASS. No new scientific runs were performed to prepare this PR.

`ranking.py` and `robust_model.py` are untested development drafts. Robust B1 P1_ROB -> P2 -> P3 -> P4 -> P5, post-decision Fresh S0/S1/S2, and May-04 Actual development replay remain unexecuted. Full May remains HOLD.

These files are copied without source changes from the local pilot artifact directory. Scripts and provenance retain the original absolute filesystem paths and require the local V41R3 runtime, frozen inputs, generated arrays, and raw sources. The PR base is the existing V41R2 audit branch; unpublished local V41R3 dependencies are not included. Do not treat this snapshot as reproducible from this checkout alone. Binary simulation/coefficient arrays remain local; compact certificates are copied under `evidence/` with their original bytes.

The PR does not modify alpha_BG, the 780-GPU allocation, W/GPU, ML, the temporal/spatial candidate domain, MESS 300/400 authority, or objective priorities.
