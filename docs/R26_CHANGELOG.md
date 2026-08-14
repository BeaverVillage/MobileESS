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
