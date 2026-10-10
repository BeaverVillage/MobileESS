# Pre-registered bounded May01 integration pilot

Run only after the frozen-source fixture gate passes. Existing Case and best UB
are admitted by the original checker. Start with the prior 12-column Master and
first-round true dual; use prior current-case columns as discovery candidates.
No previous pricing numerical bound is transferred to a changed objective.

Native budget is the preserved first-CG ledger (136.16500186920166 seconds) plus
at most 300 measured seconds; overall ceiling remains 600 seconds. One sequential
worker, Threads=1, maximum three Discovery/Master/certification rounds. Each vehicle
requests 6 seconds integer discovery and up to 8/3/3 seconds node LP certification;
the Master requests 15 seconds. Maximum three-round request is 285 seconds.
Require 98 seconds remaining before beginning a round, record any native overshoot,
and never repeat failed settings or automatically start a fourth round.

Same-case cached and native columns require full local replay, literal binary
integrality, current true negative exact RC, axis identity, nonduplicate SHA and
original coupling products. Admit at most one per vehicle. Record near-equal grid
projections without pruning. Smoothed prices have discovery-only authority.

Every new Master is read back bit-exact under the prior power-of-two scaling.
Recover true dual and replay lifted original LP primal numerically. Require strict
dual signs and a complete conservative exact pricing cover for all four vehicles.
Current-objective/current-bounds saved dual recertification and all rejected native
Pi are audited. Exact global accounting includes NONUNIT and objective constant.

Stops: no eligible true negative RC; source, original-coordinate or certificate
failure; budget reserve; full bound closure; or maximum pricing diagnostic gap
>0.001 together with no >0.001 improvement of the last exact DW candidate.
Candidate progress below the frozen published LB is not certified global gain.
An independently exact-certified full-DW upper witness below
0.97 * 0.5406756909532602 would classify a formulation ceiling; otherwise report
ceiling NOT_PROVEN. No numerical RMP objective is promoted to a global lower bound.

Outputs stay in `runtime/v42_trajectory_hull/integrated_cg01`; old evidence is
read-only. Draft PR contains source, gate and bounded scientific summary only.
No production, campaign, Supervisor, scheduled task or B3 runs.
