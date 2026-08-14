# Method and reviewer-defense contract

## Method name and novelty boundary

The working method name is **Event-Triggered Mobility Replanning with
Five-Minute AC-Aware Dispatch**. “Event-triggered MPC” by itself is not claimed
as novel. The intended contribution is the combination of:

1. an offline, globally certified coupled mobility/workload/energy/grid
   reference formulation;
2. measured evidence that mobility-trajectory integrality, rather than the AC
   power-flow gate, dominates runtime;
3. event-triggered slow mobility/work replanning with periodic maximum refresh;
4. uninterrupted five-minute AC-aware P/Q/SOC dispatch; and
5. Fresh nonlinear OpenDSS verification of every committed h0 action.

This positioning is consistent with prior event-triggered microgrid/EV MPC and
hierarchical MESS scheduling work; the manuscript must distinguish the
combination above from event triggering alone.

## Measured computational diagnosis

The interrupted R25R issue-149 snapshot is preserved as
`r26/R26_RUNTIME_DIAGNOSIS_ISSUE149.json`. Exact root QCP/pricing closed in
132.06 seconds, while the restricted integer master later reached 6,074.45
seconds and 1,064,725 nodes without a global 3% certificate. At that snapshot,
the displayed restricted-native gap was 1.773%, but the conservative exact-root
global gap was 3.183%. This is diagnostic—not a completed issue result—but it
directly supports treating discrete mobility/work regeneration frequency as the
first runtime intervention while retaining AC physics.

## Trigger hierarchy

- Tier 1 — hard feasibility: active-plan infeasibility, transit conflict,
  predicted hard SOC violation, dispatch infeasibility, or hard workload risk.
  This tier bypasses dwell.
- Tier 2 — security margin: SOC reserve, voltage, thermal, or rack-support
  margin approaches a configured boundary.
- Tier 3 — prediction deviation: traffic/ETA, workload, load, or renewable
  forecast deviates materially from the plan-generation snapshot.
- Tier 4 — economic: the retained plan's predicted cost deterioration crosses
  a configured threshold.
- Periodic maximum refresh: forces reconsideration even if no event fires.

Every threshold, unit, hysteresis release value, dwell, and maximum refresh is
configuration data. No threshold is justified by intuition alone.

## Recursive-feasibility claim boundary

The implementation supports the following conditional proposition, not an
unqualified stability theorem:

> If the active plan is feasible at the current PRE state, connects to the
> configured terminal safe set, and realized deviation stays inside the tested
> robust margin, then its verified one-step shift supplies an admissible
> candidate at the next boundary.

The mechanism supporting that statement is an immutable state-chain plan,
exact first-step equality, causal tail extension, continued use of a valid old
plan while replanning, a prevalidated safe-fallback interface, and fail-closed
behavior when neither an active plan nor fallback is safe. The eventual paper
must state and test the terminal set and robust-margin assumptions; the current
code does not claim a general Lyapunov proof.

## Required empirical comparisons

Use identical causal inputs for:

- R25T exact five-minute reference on the predeclared monthly 54-issue oracle
  windows;
- fixed 15-, 30-, and 60-minute mobility refresh;
- event-triggered with maximum refresh of 15, 30, and 60 minutes.

The threshold sensitivity grid includes ETA deviation of 5/10/15 minutes,
maximum refresh of 15/30/60 minutes, and 0.5/1.0/1.5 multipliers around the
predeclared SOC reserve threshold. Report economic degradation
`(J_online - J_exact) / abs(J_exact)`, route solves and fraction of 288 daily
five-minute opportunities, travel energy, minimum SOC and rack-support margins,
AC violations, runtime median/p95/p99/max, and deadline misses. No policy winner
is declared until every required cell has validated results.

## Monthly evaluation sampling

The primary annual score uses one contiguous seven-day block per calendar
month, for 84 scored days and 24,192 five-minute issues. The block is selected
before policy results using a deterministic minimum normalized-feature-distance
rule relative to the full month's empirical centroid. Candidate blocks require
complete input data and 48 hours of prior causal history. The burn-in is run but
excluded from reported metrics. Months receive equal weight so longer months do
not dominate the annual score.

Operational policies run each complete seven-day block. R25T is retained as an
exact global-3% oracle on one predeclared 54-issue window inside the same block;
its objective is compared only against the matching online window and is never
imputed over the rest of the week. Extreme/stress cases are disclosed
separately and do not silently change the primary sample.

The principal plot is economic degradation versus route replans per day, with
fixed-period and event-triggered policies shown together. This directly tests
whether events improve the cost/computation frontier rather than merely using a
longer fixed period.

## Real-time and physical claims

A five-minute online claim requires zero deadline misses and strict maximum
fast-loop runtime below 300 seconds; average runtime is insufficient. The
approximation is limited to how often discrete mobility/work decisions are
regenerated. AC-aware dispatch continues every five minutes, and every h0 action
must pass a Fresh nonlinear OpenDSS AC power flow before state commit.

## Literature anchors

- Wu et al., “Event-triggered model predictive control for dynamic energy
  management of electric vehicles in microgrids,” *Journal of Cleaner
  Production* 368 (2022), DOI 10.1016/j.jclepro.2022.133175.
- Valverde et al., “Event-based state-space model predictive control of a
  renewable hydrogen-based microgrid for office power demand profiles,”
  *Journal of Power Sources* 450 (2020), DOI 10.1016/j.jpowsour.2019.227670.
- Ananduta and Ocampo-Martinez, “Event-triggered partitioning for
  non-centralized predictive-control-based economic dispatch of interconnected
  microgrids,” *Automatica* 132 (2021), DOI
  10.1016/j.automatica.2021.109829.
- “Routing and scheduling of mobile energy storage systems in active
  distribution network based on probabilistic voltage sensitivity analysis and
  Hall's theorem,” *Applied Energy* 386 (2025), DOI
  10.1016/j.apenergy.2025.125535.
