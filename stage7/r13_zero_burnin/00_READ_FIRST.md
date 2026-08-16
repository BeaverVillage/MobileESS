# Conversation C Stage 7 — R13 zero-burn-in authority

R13 prospectively supersedes the prior controller-burn-in contracts.  The
48-hour/576-step field retained by PR #3 is selection/input-window provenance;
the controller executes zero burn-in steps.

Each of the twelve frozen representative weeks starts at `week_start_aest`
from a deterministic canonical cold-start PRE state.  Jobs, WAN containers,
and accumulated debts are empty/zero by experimental design.  MESS energy is
the midpoint of `E_FLOOR` and `E_MAX` parsed from the SHA-pinned scientific
source.  MESS locations use the previously frozen pre-outcome home-service
mapping and every MESS starts in `STAY` with no committed movement profile.

This is an experimental initialization assumption, not a claim that the state
matches the physical system immediately before the representative week.  All
methods must receive the same PRE state for a given episode.

Old R8/R11/R12 burn-in evidence is retained as forensic lineage and is never
retroactively marked PASS.  Stage 7 does not execute a seven-day evaluation.
Only the four season-preregistered one-step production transitions required to
prove initializer/checkpoint binding may execute Gurobi/OpenDSS.
