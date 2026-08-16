# R26 changelog

## Unreleased

- Added explicit global-certificate versus restricted-native gap reporting and
  a MIPSOL stop helper that uses only an exact external lower bound.
- Added immutable, checksummed RoutePlan state chains with deterministic shifts,
  transit preservation, committed-prefix audit, and no-teleport validation.
- Added configurable HARD/SOFT event rules, hysteresis, dwell, maximum refresh,
  and reason coalescing.
- Added a one-worker nonblocking planner manager, stale/invalid candidate
  rejection, and boundary-only atomic plan persistence.
- Added the AC-aware QCP dispatch conditioning/audit interface and mandatory
  Fresh OpenDSS commit-gate interface.
- Added the 54-issue controller driver, fixed experiment matrix, audit metrics,
  contract/schema files, 17 regression tests, and a non-authoritative smoke
  adapter.
- Added R25S, an interruption-safe wrapper that resumes immutable R25R science
  from the latest verified causal POST state without deleting completed issues.
- Added explicit `LOCAL_REPAIR` versus `FULL_REPLAN` requests. Local scopes are
  unions of affected MESS/jobs, full requests dominate coalescing, and an empty
  local scope escalates fail-closed to a full request.
- Added an authority-checked opportunity-gap trigger, the 60-minute five-minute
  plus 210-minute fifteen-minute horizon (26 integer stages), and a
  structural-signature-scoped generalized-Benders cut cache.
- Added exact-safe initial path seeding and compact VarHint transfer, final-gap
  reporting repair, and legacy R25T nested-gap resume compatibility.
- Changed annual evaluation from full calendar months to one predeclared
  contiguous seven-day block per month. R26/baselines score all 2,016 monthly
  issues; R25T supplies one matching 54-issue oracle window per month. Monthly
  burn-in remains 48 causal hours and is excluded from reported metrics.
