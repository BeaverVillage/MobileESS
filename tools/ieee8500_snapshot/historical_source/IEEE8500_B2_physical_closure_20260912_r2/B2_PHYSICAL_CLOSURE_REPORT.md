# IEEE8500 B2 frozen physical closure

**PASS — original beam/final selection preserved. B3 has not started.**

The original selected decision remains `B2-S4-b55b48c9f33cb380`. Its primary exact-AC failure remains frozen; post-selection P/Q closure does not replace that primary record. Completed authoritative B1 was neither changed nor rerun.

| Stage | Status | Evidence |
|---|---|---|
| Primary Fresh | FAIL | Vmax = 1.0585440631902354 pu |
| Local fixed-discrete restoration | INFEASIBLE | Gurobi status 3 is the sole fallback trigger |
| Full physical P/Q fallback | True | Original V41R4 minimum-effort / affine-deviation seeds and 16-step refinements |
| Independent clean 96-slot AC | PASS | All voltage, phase-line, transformer phase-current/winding-kVA, convergence and settling gates |

| Metric | Primary failure | Accepted closure |
|---|---:|---:|
| Vmin_pu | 0.958741940169 | 0.961459237106 |
| Vmax_pu | 1.058544063190 | 1.049999733147 |
| max_phase_line_loading_pu | 0.836248388964 | 0.835581035286 |
| max_transformer_phase_current_pu | 0.916828924469 | 0.829635776208 |
| max_transformer_winding_kva_pu | 0.931601321266 | 0.844828194368 |

All 384 vehicle-slot rows retain every field except P/Q and resulting battery energy/SoC. The AIDC schedule, vehicle, route, destination, service location, departure, connected/transit state and all other mobility fields are fixed.

Unchanged discrete SHA256: `77e952a57b6860e9e1bc97fe6be684451c10adc65c00363973c0dd4632db5ec4`.

The pruned candidate `B2-S4-e0d2bbcf68b5d690` (Vmax 1.0499207243101567 pu) remains `DIAGNOSTIC_AC_FEASIBLE_EXISTENCE_WITNESS` only. No restoration/fallback seed, target, or selection anchor reads it. The rejected selection-order proposal is preserved under `IEEE8500_runtime_repair_20260912/DEVELOPMENT_ONLY_REJECTED_SELECTION_ORDER`.

Electrical adapter preparation history: the first version stopped before the local solver on an additional tight-held-baseline check. Its failure and code remain preserved. The executing version retains the exactly reproduced chronological AC intercept and uses tight held-state derivatives, matching the frozen numerical preflight convention. The 3.0231086168841514e-05 pu diagnostic shift is recorded; original margin, chronological anchor tolerance, trust region and exact-acceptance limits remain unchanged.

Authority settings remain source 1.0400 pu, Vreg 123.5 V, alpha 0.50, CAPBank3 OFF. Topology, ratings, AIDC/MESS/PCC scales, 24-location mapping and all hard limits are unchanged.

Original local loop, local P/Q solver and fallback search bytecode identity passed the structural audit. Source, completed B1, frozen primary failure, diagnostic evidence and quarantined development bytes were checked against the preservation manifest after acceptance.

This is post-selection physical feasibility closure. No global AC optimum or improved beam/final-selection procedure is claimed.
