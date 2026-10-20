# Ckt24 / frozen V44 r043 / May01 / MESS target 8

This is an **incomplete, gated preflight study**, not a completed port or scalability certificate. Read [FINAL_REVIEW_KO.md](FINAL_REVIEW_KO.md) and [PRE_SOLVER_GATES.json](PRE_SOLVER_GATES.json) first. No Ckt24 A1/M1/A2/M2, complete AIDC B0, Actual or Fresh day run is claimed.

The only study-owned paths are `D:/ckt24_v44_r043_may01` and `D:/ckt24_v44_r043_may01_runtime`. Never invoke the inherited V44 dispatchers: their historical absolute paths target the production campaign. This package imports no production dispatcher, acquires no production lock, modifies no campaign permits and updates no scheduler.

Reproduce in the pinned Windows Python environment with dss-python 0.15.7 (C-API 0.14.5, based on OpenDSS SVN 3723), NumPy, pandas, Matplotlib and Gurobi for offline mapping only. Gurobi is not used here to solve any AIDC–MESS stage. Exact engine details are in the network audit. This study does not certify parity with a different native OpenDSS executable or engine revision.

1. Copy `ckt24_study/original_ckt24/` unchanged to the independent runtime's `original_ckt24/`. Copy `ORIGINAL_DSS_SHA256_MANIFEST.json` to runtime `ORIGINAL_DOWNLOAD_MANIFEST.json`. These are the unmodified public EPRI files at SVN r4176.
2. `python -X utf8 -m ckt24_study.preflight` inventories the complete original network and runs the 96-slot background-only diagnostic. Master demo execution is deliberately excluded, following the original master's instructions. Independent AC numerical tolerance is strengthened to 1e-10; MILP tolerances remain untouched.
3. `python -X utf8 -m ckt24_study.traffic` verifies r043 May01 routes/forecasts, reads original SUMO junction XY and copies exact traffic authority bytes. Original Windows/WSL data paths must be available; missing files fail instead of generating replacement traffic.
4. `python -X utf8 -m ckt24_study.screening scenarios` writes the predeclared 1.0/0.75/0.5 background-only scenarios, including a controls-off original-demo reference. These are not final AIDC B0 cases. No final scenario has been selected.
5. `python -X utf8 -m ckt24_study.screening sensitivity` rebuilds an independent original circuit for each P/Q perturbation at all 380 coordinate-bearing MV three-phase buses. The shared fresh reference is identical for all candidates. Final file count is checked before mapping. This is instantaneous virtual-port response only.
6. `python -X utf8 -m ckt24_study.spatial` attempts a 24-site original-axis order witness (45 seconds, one Gurobi thread), then AIDC12 if necessary. Time limit is not a proof of infeasibility. A witness is provisional; it does not certify geographic CRS, electrical branch diversity or physical PCC infrastructure.
7. `python -X utf8 -m ckt24_study.locality` records source-oriented connectivity and local nameplate ratios. A nameplate ratio is not a feasible SOC/route/PQ schedule certificate.
8. `python -X utf8 -m ckt24_study.plots` writes measured SVG/PNG figures. Missing electrical coordinates stay missing. Figures requiring nonexistent final optimization results are explicitly withheld.
9. Commit the study code, then `python -X utf8 -m ckt24_study.report` seals that code revision, records unresolved gates and writes NOT_RUN rows. The reporter cannot dispatch a case.
10. `python -X utf8 -m pytest tests/test_ckt24_preflight.py -q` checks admission rejection and direction inversion detection. These small tests do not validate an eight-vehicle solver.

`python -X utf8 -m ckt24_study.power_envelope` preserves the original C1/GPU installed-power envelope without claiming a feasible job schedule. `python -X utf8 -m ckt24_study.diagnostics null` calibrates an empirical numerical floor with zero-power ports; `... diagnostics multiport` evaluates small eight-port AC probes at a provisional drawing witness, without freezing vehicle initial positions or certifying PCC capacity/SOC/routes.

Raw voltage/current/transformer CSVs remain in the independent runtime, outside Git, with SHA-256 receipts. The network inventory, original DSS files, compact summaries and Top20 survey are preserved in this PR. The requested `B0_MV_LV_BOTTLENECKS.csv` filename contains original-background diagnostics; it must not be cited as the AIDC-inclusive B0 result. Blank UB/LB/Gap values mean **not measured**, never zero.

The traffic and electrical networks are synthetically paired. Original EPRI drawing XY is not a claim of GIS co-location with Melbourne traffic. No coordinates are rotated, reflected, swapped or synthesized to earn a spatial PASS.

Source: [EPRI examples](https://opendss.epri.com/ExamplesDocsandTestCases.html), [original Ckt24 at immutable SVN r4176](https://svn.code.sf.net/p/electricdss/code/!svn/rvr/4176/trunk/Version8/Distrib/Examples/ADiakoptics/ckt24/). Original attribution and comments are preserved byte for byte. Algorithm authority: `affc7226a519adbe072d7debbc3ae25ea71c3487` in BeaverVillage/MobileESS.
