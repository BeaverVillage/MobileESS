# Corrected F&O compute control

The authoritative universe, full original model, seed builder, all physical tolerances and P1-P5 locks are unchanged. Unopened options are NOT_VISITED_WITHIN_COMPUTE_BUDGET; raw coverage is an audit metric, never a convergence prerequisite.

| Priority | Normal exploration target | One overlap pass target | Nominal cumulative-budget share |
|---|---:|---:|---:|
| P1 | 420 s | 150 s | 900 s |
| P2 | 180 s | 90 s | 480 s |
| P3 | 45 s | up to 30 s | 180 s |
| P4 | 45 s | up to 30 s | 120 s |
| P5 | 30 s | none | 120 s |

A sweep is a deterministic round through the five named families. Its target is split into five wall-clock family slices; each slice may solve multiple complete-job neighborhoods. Short atomic solve/independent-validation/checkpoint work may finish a slice slightly later. The shared hard cap takes precedence. Each subproblem uses four Gurobi threads and at most sixty solver seconds. Candidate domains are never shortened to fit a time slice.

The soft cumulative ceilings distribute the budget remaining after model/seed preparation; saved time rolls to later stages. All A0/M1/A1/MF work shares one PolicyBudget. Fresh and Actual are outside it. P1 stops after one stagnant normal plus one overlapping diversification sweep. Only an accepted, independently validated improvement of the current objective resets its sweep. Lower-priority improvements and changes at the existing tolerance boundary do not reset it. P2-P4 use the same principle with shorter targets. P5 remains an optimization stage with one short sweep.

P2 mean nonnegative H4 shortfall, P3 nonnegative migration count, and P4 nonnegative GPU-weighted occupancy symmetric difference have rigorous zero lower bounds. Independently validated exact zero permits immediate conditional stage optimality. This does not certify P1/P2 or the joint lexicographic solution. No matching nontrivial global P1/LP bound was available for this acceptance; the old monolithic bound belongs to a different MPS and is not transferred. Neighborhood bounds remain local.

Reports retain per-stage family coverage, complete raw-option visit ranges, sweep history, current-objective improvements, objective vectors, runtime, explicit termination reasons, conditional floor certificates, and unused shared budget. The old fa/03 evidence is immutable. Release requires identical uncompressed full MPS and authoritative candidate SHA, unchanged scientific sources, core/control/operations regressions, and new May-04 B1 Fresh/Actual receipt checks A-O.

Full-model MIP-start processing gets a minimum five-second solver slice in production. Soft family slices never truncate that minimum. If the stage ceiling cannot fund the atomic solve and measured validation/startup reserve, the stage ends with its verified incumbent. Exploration targets scale to the component budget remaining after earlier components and model preparation; M1 therefore cannot leave A1 searching toward an unavailable full-day exploration target.

After the preserved early02 Windows reader-lock failure, compute-report writes retry the original canonical writer with identical bytes and atomic replacement. A persistently locked nonauthoritative live UI snapshot may be skipped; required scientific/checkpoint receipts still fail closed. Live-status computation and I/O are charged immediately, and family slices use cumulative sweep deadlines so atomic overruns do not accumulate five times.
