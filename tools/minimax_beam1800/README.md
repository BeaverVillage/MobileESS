# Source18r B2 May01 minimax cold-start canary

This adapter is based on PR218 `dd283b631e5b88c2f26ca81fde34b2c2cc180a45`.
It reuses the original Source18r builder and FULL validator without changing
their source, numeric tolerances, coefficients, bounds or objective.

Executed sequence: cold initialization, real moving routes, conditional LP
pilot, route-fixed C3A+Dense MILP, separate Original FULL replay, then repeat.
All Native Runtime is accumulated in one 1800-second ledger. Native starts
are absent. The historical N1 point is not a new performance point or start.

The eight-route LP gate is preregistered. Any LP bound used to prune must pass
the exact finite-box weak-duality certificate and its offline reproduction.
It is a conditional route bound, never a new Original Global LB. Mode
relaxation and omitted Grid rows broaden feasibility. The retained source
physical rows are extracted independently; Grid helper elimination is checked
against the original FULL CSR. Binary64 projection errors are bounded over
the original variable box and the RHS is rounded outward.

Beam scores and SOC/rebound estimates are heuristics. Exact physical pruning
is limited to source arc bounds and optimistic SOC necessary conditions.
Beam64, maximum three MOVE arcs per vehicle, ranking and pairing exclusions
do not certify exhaustive route search. Joint cooperative candidates use
cross products and a maximum row loading vector, rather than zipped ranks or
summed independent gains. All384 charge modes stay free in route MILP.

The original incumbent-independent physics remain in every route MILP.
Optional `rho <= current_UB - 1e-5` restricts the improvement target only;
infeasibility there is not physical route infeasibility. Every fourth
post-pilot route uses an unrestricted objective domain.

The experiment is one shot. `prepare` requires no run latch; `run` creates
`RUN_STARTED.json` and refuses another run or a budget reset. Scientific
Source and protected worktree paths are the original Windows research
environment, not portable synthetic replacements.

```powershell
python -X utf8 -m tools.minimax_beam1800.prior_audit
python -X utf8 -c "from tools.minimax_beam1800.conditional_lp import prepare_template; prepare_template()"
python -X utf8 -m tools.minimax_beam1800.controller prepare
python -X utf8 -m tools.minimax_beam1800.controller run
python -X utf8 -m tools.minimax_beam1800.post
python -X utf8 -m tools.minimax_beam1800.review
```

These instructions document the completed run; do not rerun it into the same
latched directory. Results and immutable Native evidence are under
`docs/v42_b2_minimax_beam1800/`. Postprocessing and independent review optimize
nothing. This is a Certified Matheuristic / Bound-Guided Anytime MILP, not an
exact global route solver. Planning FULL verification is not fresh OpenDSS AC
and does not authorize the Actual interface or another date/campaign.
