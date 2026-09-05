# V40A bounded iterative AIDC–MESS co-optimization

The B3 decision sequence is `A0 → M1_ROUTE_PQ → A1_FEEDBACK → MF_FIXED_ROUTE_PQ`.
There is one fleet mobility-search stage and one AIDC feedback pass. The inherited
fleet search still evaluates four vehicles, beam parents, seeds, restricted
candidates and full MILP children. Those internal counts are reported separately.
This method does not certify a global joint optimum or convergence.

`initial.build_initial` materializes the predeclared April 1 development A0 from
the existing causal RSP schedule and RW-anchored placement authority. It does not
replace the RSP scheduler. If that initial authority requires an escalation that
has no accepted certificate, it fails closed. `accepted_initial.materialize_accepted_a0`
can import a byte-verified accepted A0, including terminal-safe temporal repair,
existing migration, fixed WAN paths, checkpoint and READY/restart evidence. It
checks reconstructed PCC power against the accepted power trajectory. Importing
such an A0 does not authorize reuse of an old B3 final result.

`feedback.solve_feedback` fixes every M1 mobility and P/Q decision. It uses all
inherited Planning voltage, line-current, transformer-current and transformer-kVA
constraints with exact integer-GPU C1 tables. Pending placement and the inherited
standby temporal domain are intersected with per-job terminal preservation.
The user's clarified policy fixes RUNNING jobs when the A0/M1 state is feasible;
no additional performance-driven RUNNING migration is admitted. Lexicographic
objectives are rho_max, complete-interval site/time occupancy deviation, zero
additional RUNNING migrations, and a deterministic tie break. Solver incumbents,
bounds and termination codes are retained, including WorkLimit termination.

`recourse.solve_fixed_route` accepts no route table or mobility search API. It
optimizes only P/Q, battery energy and the inherited electrical direction binary.
The coordinator accepts A1/MF only after hard checks and objective nondegradation
within the predeclared tolerance. Invalid candidates retain the previously
verified feasible incumbent; unexpected implementation errors fail closed.

`postfreeze.production_verification` seals complete AIDC, route, P/Q and source
authorities before Fresh. If necessary it uses the unchanged V17/V37R3 fixed
discrete AC restoration contract and refreezes each electrical correction before
rechecking Fresh. AIDC and all mobility fields remain fixed. The Actual step is
the inherited frozen-decision identity/replay gate; it is not a newly implemented
realized-demand or traffic simulation.

The development entrypoint accepts April 1 only:

```powershell
python -m dayahead.tools.run_v40a_development_smoke
```

An implementation continuation may supply `--reuse-m1-from` with an existing
April M1 checkpoint. The loader requires identical A0 PCC, all Planning
coefficients, M1 source bytes, search settings and checkpoint identity. The
comparison uses the measured common A0/M1 prefix for both methods; this avoids
performing the expensive search again. Reports distinguish the represented
pipeline from continuation wallclock and development debugging attempts.

Artifacts are in `dayahead/artifacts/v40a_bounded_iterative_aidc_mess_coopt`.
The complete JSON payload is the canonical typed joint authority. Parquet files
provide job/slot comparison tables and have file hashes in the artifact manifest.

The preserved V39L launcher, monitor and liveness code are unchanged. No V40A May
campaign is registered or launched here. B0/B1/B2 numerical reuse and a new May
B3 campaign require the separate later task specified by the user.
