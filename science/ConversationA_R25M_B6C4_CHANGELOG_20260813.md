# Conversation A — R25M B6-C4 Changelog

## Status
STATIC IMPLEMENTATION PASS; runtime effect deferred to C5.

## Changes
- Removed closest-to-0.5-only branch selection.
- Added deterministic shortlist with mild early/mid-horizon mobility weighting.
- Reserved a non-mobility candidate slot when both disjunction classes exist.
- Added selection-only two-child continuous-QCP strong probes.
- Added reliability pseudocosts updated only from exact child lower-bound improvements.
- Exact child all-column pricing remains mandatory for any certified lower bound.

## Unchanged scientific core
- main.py SHA-256: `f7b5d12f3e0f1933a928d3955d573e4c12597686aa1512302f2f791d34973bf6` (byte-identical to C3)
- physical feasible set unchanged
- objective unchanged
- H54 / 5-min cadence / 3% target / Threads=1 unchanged
- Fresh Exact OpenDSS contract unchanged

## Decomposition module
- C3 SHA-256: `df4802da78538dd5c48f1ecc07c2d8d69e91e5fe89882a9b7e42477e7d8e56ed`
- C4 SHA-256: `a740625c51c31bee5e8c88b99bafad5687c2cee743f8e9919553d9db3da35ca4`

No long issue152 solve was run in C4.
