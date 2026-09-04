# V39A Final Readiness Review

V39A is **FAIL-CLOSED**.  The accepted V37 RW/RSP schedules and the frozen
12-AIDC capacities cannot be spatially realized without splitting GPU gangs or
changing temporal execution.  May was not started.

## Scientific result

- Gurobi built 62 day/mode relaxation models: 48 optimal,
  14 infeasible.
- The first IIS is 2025-05-21 RW with
  11 constraints.
- The decisive slot-local contradiction begins at May 21 slot 60: 15 concurrent
  32-GPU gangs exist, while the frozen site capacities can host at most 14 such
  indivisible gangs.  This remains impossible even under forbidden arbitrary
  per-slot remapping and with WAN limits removed.
- Hard slot-local contradictions occur on 2025-05-21, 2025-05-22, 2025-05-23, 2025-05-24.
- V39B temporal-scheduler redesign is scientifically required; it was not implemented.

## Preserved science

Temporal schedules, runtime authority, CENTER, C1, MESS K/beam/seed, site
capacities, gang indivisibility, V38 fixed inter-AIDC WAN paths, and Rack
authority are unchanged.  The V38 failure evidence remains intact at
`cf7762d82f485d9f7f463bb6e5119f2e5d197a13`.

The site-power equation passes algebraic aggregate conservation, but production
site GPU/IT/PCC Parquets are intentionally schema-only and carry
`BLOCKED_NOT_MATERIALIZED`; fabricating trajectories after infeasibility would
violate fail-closed semantics.

## Reproducibility and launch gate

- Voltage frozen byte SHA: `3ee89daad6d63cffb70c1a890f5141cf33bf4c951c9a9c364ae36692bcda6151` (PASS).
- V39A focused tests: 17/17 PASS.
- V38 relevant regression: 13/13 PASS.
- V37 clean-code regression with frozen input cache: 80/80 PASS.
- Broader C1/voltage/restoration regression: 42/42 PASS.
- May preflight: READY=0, NOT_READY=31,
  missing=0.
- V39A implementation fingerprint: `8cc98af7f4b88d1ba8a580c3badab0536d51db23774bc8aceb5d2a22a83ad063`.
- `V39A_SCIENCE_FROZEN=NO`
- `MAY_CAMPAIGN_LAUNCH_READY=NO`
- `MAY_STARTED=NO`
