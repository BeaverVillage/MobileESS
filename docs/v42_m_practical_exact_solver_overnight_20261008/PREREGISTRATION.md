# M-stage overnight practical exact solver

Scientific base: PR177 `b86486a6f58d6c39a1ea4ff2c7e984372b6087a5`; original PR162 selected C3A. The scientific P1 objective remains **minimize rho**, with bit-identical coefficients, ObjCon and variable axis. Full-domain runs add no rows or cuts. Original rows, bounds, types and A1 authority remain fixed.

The immutable clock is `IMMUTABLE_DEADLINE.json`: 2026-10-07 16:53:34.812972 UTC through 2026-10-08 00:53:34.812972 UTC (09:53:34.812972 KST). The clock includes delivery delay and all preparation, overlap, replay and publication. No stage resets it.

M0 reuses the existing worktree and PID5360 external root LP. The completed 600s canary is not repeated. Its CutPasses=0 still generated 5,272 cuts. At registration the external root had spent over 2,700s in barrier/crossover cleanup, with large infeasibility and no OPTIMAL receipt. Intermediate objective values are not bounds. Existing sources and receipts remain independently auditable.

M1 therefore needs exactly one distinct **1800s Cuts=0 / Heuristics=0** full-C3A native control. It may overlap the already-running M0 LP; wall throughput is observational, not an isolated paired speedup claim. Threads=1, Method=2, NodeMethod=1, Crossover=2, MIPFocus=3, MIPGap=.005, FeasibilityTol=OptimalityTol=IntFeasTol=1e-8, Seed=20260929, DegenMoves=0. The complete current replay-PASS point is supplied as MIP Start. Objective identity failure prohibits optimize.

Backend selection uses actual numerical certificates, node throughput and LB progression; missing external child measurements are reported as unavailable. External is favored for clean, useful certified child solves (approximately <=60s median, or better progression). Native is favored for material nonroot/tree/BestBd progression. A failed backend triggers the next registered stage rather than ending the night.

M2 external production retains deterministic best-bound OPEN, both children, exact dyadic LP/Farkas proof checks, original binary fixings only, basis inheritance, child dual simplex and SHA-bound crash-safe restart. Unresolved and in-flight nodes remain OPEN. Save every 10 nodes or five minutes at the latest. Branch ranking may use measured pseudocost; pruning may not use heuristic scores. No unproven partition or discarded child is allowed.

M3 native production: at most 10,800s in the initial uninterrupted solve, also clipped to the same deadline. The full-domain native Bound is eligible under the inherited native certificate contract only with unchanged objective/model, status OPTIMAL/TIME_LIMIT/INTERRUPTED, no callback/solver error, no severe numerical warnings and no contradiction with validated UB. At 60 minutes, if there have been fewer than 10 tree nodes and <=1e-6 bound gain, terminate cleanly and switch backend; a subsequent 60-minute window with equally negligible tree/bound progression may also trigger the switch. These are operational rules, not mathematical pruning. Native tree restart is never claimed; a subsequent run is fresh with a validated start.

M4 is conditional on gap>.005, progressing exact LB search, and UB stagnation>=3600s. At most two interventions, each<=600s, total<=5,760s. First radius64, same prior 2,100 binary axes/slots64..84. Second radius96 only if the first produces material replay-PASS UB improvement>=.001 and time remains. Only the signed Hamming row and outside-neighborhood binary fixings restrict primal runs. All continuous domains and original objective stay unchanged. A restricted bound is never global. Every incumbent event is saved; candidate UB requires independent full original C3A/route/SOC/PQ/PCS/grid/A1 replay.

M5 uses measured fractional families and child bound uplift only if external production makes that evidence available; no old hull/cut loop or speculative new formulation is registered.

M6: after gap<=.005, verify incumbent, original objective and complete global proof coverage. P2 only after inherited P1 acceptance, with repository P1_EPS=1e-7 and COMPONENT_EPS=1e-8, original movement energy then movement count contracts. No A2/M2/Planning/Actual/Fresh AC.

M7 package deterministic execution, atomic persistence, incumbent/full bound ledger, resource accounting, solver-free exactness fixtures and truthful restart semantics. Preserve the mathematical distinction between exact global LB proof and heuristic UB search.

M8: one requested primary classification, final valid bounds, all available and missing timings, comparison, replay and test receipts, Draft PR stacked on PR177, remote-matching final HEAD and clean tree. Reserve the final 15 minutes for independent audits and publication inside the deadline. Continue productive work until the deadline unless target plus P2 finishes or an unrecoverable exactness failure prevents all registered alternatives.
