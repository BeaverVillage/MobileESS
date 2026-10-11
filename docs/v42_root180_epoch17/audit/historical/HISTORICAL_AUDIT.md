# PR160–162 historical audit

Audit source: `D:\v42_svr11_epoch16_20261011`, git HEAD `a32b4e89eadda82c11ed2e03f5c7ae087d70a908`. All historical sources and evidence were read through local Git objects or live GitHub PR metadata. No optimizer or native presolve was called by this audit. No applicable AGENTS.md was found in this checkout or its directory ancestry.

## Historical reductions

PR160 removed 190,280 rows and 2,860,885 nonzeros from its 886,017-row PR159 matrix. The resulting matrix had 695,737 rows / 316,743 columns / 5,586,970 nonzeros. Family deletions: line thermal 60,101; transformer kVA 74,802; voltage 43,584; NormalAmps 11,520; empty flow rows 273. Exact duplicates were all empty LHS rows; no nonempty proportional dominated rows were found. 140,571 other rows were independently certified through outward-safe interval/PCS support. SOC-derived aggregate P bounds were deliberately not distributed as unsafe per-site perspective bounds.

PR161 did **not** obtain those reductions from static presolve alone. `PR161_build.py` constructs C0, transports all independently replayed PR160 certificates into C1, explicitly tightens physical Q/SOC bounds and fixes source node activities, and then runs static presolve. That stage alone removed 50,427 additional rows and 19,741 columns, including 19,441 grid auxiliaries. Static categories included constant/identical proportional rows, fixed-bound equalities, fixed variable elimination, exact unit aliases and deterministic flows. Accepted coefficient/RHS substitutions had to remain exactly representable in binary64.

PR162 removed a further 71,540 rows (PCS16 53,652; connected Q 17,884; terminal location 4), tightened 48,551 helper variable bounds, and removed no columns. The local PCS polygon retains 10 of 16 PCS faces, with two P connection facets: rational Farkas implications and source-flow equality sums preserve the fractional LP projection and integer domain. The selected C3A has 582,808 rows / 306,040 columns / 9,322 binaries / 5,351,612 nonzeros.

`HISTORICAL_MODEL_CENSUS.json` and the row/column CSVs include the original full matrix, PR159 authority, C0, C1, C2 and C3A counts for every family.

## What the 180.21-second reference measures

The actual full-MILP log `PR162_MILP_C3A_NATIVE.log` reports:

- Native Gurobi 13.0.2, Intel i7-13620H, Threads=1.
- Root relaxation **180.21 seconds**, 359.99 root Work, objective 0.5687116.
- Root completion at approximately 195 seconds of total optimize elapsed time.
- Gurobi presolve 13.06 seconds; crossover 51.06 seconds.
- Actual MILP presolved size: 407,856 rows / 287,699 columns / 4,511,774 nonzeros.
- Further root relaxation presolve: 371,383 rows / 306,776 columns / 4,067,204 nonzeros.
- Native Runtime 286.135 seconds; one explored root node, zero post-root B&B nodes.
- Verified UB 0.6694159238756877; raw ObjBound 0.5687116103498335; safely adjusted LB 0.5687116003498334; gap 15.043610397376117%. No new valid incumbent appeared.

The saved read-only presolve artifact has 4,498,109 nonzeros, while the actual MILP solve log has 4,511,774. These are different measurements and must not be substituted for one another. The 180.21-second number excludes initial MILP presolve/MIP-start preparation and later root cuts. It is neither total wall time nor a claim of 0.5% gap completion.

Historical native execution source was `0a27fb90dead2b944a72c31145f5a7bdc4dbb9ac`. PR162 head is `1d922c91eb27056a5ccc79c92ef18146707099ab`; PR161 head is `4f45f04d685d5d5e689463f953695fe40d52cf98`. These historical PRs are references only.

## Current omissions and setting differences

Current production `v42_may_campaign_native90/m_model.py` calls Compact → static Presolve → current C3A. It does not perform the PR160 route/PCS grid-security support elimination before static presolve. Static Presolve detects empty/proportional/singleton and alias structure; it cannot imply the same general affine grid constraints by itself. Current `v42_ultracompact/current.py` explicitly retains all security rows and sets `security_rows_kept=True`. Therefore PR160's general grid screening is omitted, rather than absorbed.

Current production also omits PR161's explicit pre-presolve physical Q/SOC tightening and source-node activity fixing. Current C3A does apply actual freshly regenerated PCS/Q Farkas deletions, terminal implications and affine helper bounds. It is more than a C3A name, but does not contain the complete historical reduction pipeline.

The historical full native settings were Method=2, Threads=1, Crossover=2, NodeMethod=1, MIPFocus=3, DegenMoves=0, PreCrush=1, Seed=20260929, plus FeasibilityTol/OptimalityTol/IntFeasTol=1e-8. The benchmark arm had TimeLimit=285 and MIPGap=.005.

The actual Epoch16 May01 full log instead has Method=2, Threads=1, MIPFocus=1, NodefileStart=.5, FeasibilityTol=1e-9, OptimalityTol=1e-9, IntFeasTol=1e-8, NumericFocus=3, ScaleFlag=2 and MIPGap=.03. The inherited seed recovery budget calls `numerical.set_precision` before each native optimize. Consequently the stricter current FeasibilityTol/OptimalityTol and NumericFocus/ScaleFlag contracts must be preserved when restoring historical root settings. Copying historical 1e-8 tolerances would loosen current numerical authority. Root-oriented Method/Crossover/NodeMethod/MIPFocus/DegenMoves/PreCrush settings do not conflict with these contracts or the current RAM/Commit admission policy. Preserve the measured remaining 1,800-second native stage budget, current gap .03, NodefileStart=.5 and D-drive NodefileDir; the historical arm cap and .005 gap are benchmark settings, not campaign settings.

## Auxiliary substitution scope

PR162 independently considered 278,829 retained-variable projections, including all 380 SOC states. All SOC projection nonzero changes were positive. It rejected 13,224 fixed substitutions because exact new coefficients/RHS were not representable in binary64. General high-fanout response/injection substitution usually increases nonzeros; finite bound transport must be included, and cost union bounds do not establish every possible numerical cancellation. No additional historical generic auxiliary substitution was adopted.

`CURRENT_AUXILIARY_COST_AUDIT.json` examines all 109,234 actual Epoch16 injection/response defining rows without changing the matrix. No injection or line-response candidate has a negative sparse-union nonzero delta. Fifteen transformer-P candidates have a nominal negative delta, but all fifteen fail exact binary64 coefficient/RHS representability, and none retains a negative delta when both finite bound rows are explicitly transported. No additional safe generic auxiliary substitution was found or adopted. This cost audit does not claim that every possible numeric cancellation was exhaustively proven; uncertain projections remain unchanged.

Old M1 scientific inputs are May01 with a frozen prior A1 planning anchor. `OLD_GRAPH_BUNDLE_PROVENANCE.json` identifies the original electrical certificate and sensitivity outputs; the original coefficient files are under `C:\codex_mobileess_workspace\MobileESS_v41r3_scale_rebalance\frozen_artifacts\v41r4_may\e\20250501\kernel\electrical\2025-05-01`. The current B2 independent AIDC input and SVR11 electrical axes must be compared from actual data; identical four-unit/96-slot labels do not make them the same problem.
