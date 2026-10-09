# May25 recovery and all-May precision

The first May25 Phase I solve was OPTIMAL but its unmodified primal point failed
the original 1e-6 row replay. Equality row 16476 contains `-4*x + y` at about
2.9715e10. The raw values have an actual residual of 3.814697265625e-6, including
when evaluated with exact rational arithmetic. This is not a display artifact.

The existing precision override was incorrectly restricted to May11. V9 applies
FeasibilityTol=1e-9, OptimalityTol=1e-9, NumericFocus=3 and ScaleFlag=2 to A's
PHASE_I/ORIGINAL_P1 on every May01–31 date and to every B2 Native entry. Phase I
also uses Presolve=0 on all May dates to avoid the observed postsolve residual.
Method=2 is retained. Other A components retain their original policy.
Heuristics=0.05 remains enabled; no new heuristic is introduced.

Three separate, finite, isolated diagnostics used the exact saved May25 matrix,
bounds, variable types, RHS and objective. Precision alone failed; dual simplex
with precision also failed. The same barrier method with precision and original
rows passed primal and dual replay, with maximum row violation
7.105427357601002e-15. All three Native calls and both failures are preserved.
Diagnostic points/bounds/runtime never enter a production attempt or its ledger.

The user explicitly requested stopping May26 and restarting May25 first. May26
PID 81804 was stopped with Native calls/runtime zero. The previous Coordinator
is held and exited. A new immutable source permit and separate attempt/journal
reset only May25 and the explicitly interrupted May26. May01–24 PASS results,
previous failure, partial artifacts, ledgers, checkpoints and source permits
remain unchanged. The OS Coordinator orders May25 → May26 → May27–31, then B2
with three workers, after all 31 B1 dates are terminal. It requires no Codex turn.
Completed dates are not rerun or retroactively relabelled with the new policy.

All A science reuses the frozen V6 run/prepare functions. Only its Native
authority/precision metadata and source receipts are ported, with reverse AST
equality checked. B2 reuses its admitted V7 constructor and the original M
Hybrid/exact certificates. Presolve, precision and metadata are Solver policy
changes; model coefficients, constraints, original data, integer/physical
replay and acceptance tolerances are unchanged.

Native=0 regressions: 112 PASS, including all 31 A dates × 2 components, 31 real
tiny Gurobi B2 models with optimize admission denied, explicit recovery and
original result preservation, B1 terminal barrier, automatic three-slot B2
dispatch, restart adoption, paths/inputs/ledgers, and the certified Gap display.
The DOM test passes. These are not FULL B2/B3 scientific certification.

B2 FULL/Compact/C3A validation remains deferred until all B1 workers exit and
is still NOT_TESTED. Failed validation blocks B2 rather than falling back to one
worker. Actual B1→B2 transition remains NOT_YET_OBSERVED. B3 uses separate
A1/A2/M1/M2 source routes; its owner has been instructed to apply and verify the
same policy without starting B3 or modifying the running B1/B2 campaign.

Only newly deployed, read-only Gap V8/V8R2 monitor/watchdog tasks are superseded
and disabled with their prior XML preserved. Historical research Solver and
Coordinator task definitions are unchanged. V9 uses ordinary LeastPrivilege
InteractiveToken tasks. Logoff persistence and closing the entire Codex app
have not been experimentally proven; Scheduler ownership, job flags and
changing heartbeats are recorded from the real V9 processes.
