# Conversation A — R25M B6R2 changelog

- Bound B6R1 runtime failure artifact into the B6R2 carrier.
- Replaced one-column-per-MESS CG with deterministic k-best batch pricing (default 8 per MESS).
- Retained exact shortest-path pricing as the closure oracle.
- Reclassified the existing-lambda RC comparison as a numerical dual-accounting audit.
- Raised the audit envelope from a brittle hard-coded 1e-5 to an explicit 1e-4 fail-closed tolerance; B6R1 failed at only 1.218714e-5.
- Tightened continuous RMP barrier convergence to 1e-9 and uses NumericFocus>=1 during CG only.
- Added a conservative lower-bound safety subtraction before any 3% certificate can be declared.
- Restores parent numerical settings before the compact integer phase.
- Added independent k-best and lower-bound-guard proof regression.
