# Exact WAN factorized joint MILP

Independent worktree/branch from PR99 exact head `3309cd230cd8235201f5578d392241fa98e059bc`. PR100/PR101 remain independent. No Dantzig-Wolfe, column pool, restricted MILP or scientific authority changes.

Stage A computes exact full-path support projections and an idempotent fixed point without Cartesian Option materialization. Full May removes zero w, 417,968 unsupported f1 events and 24,774 r1 states. Stage B audits every preserved coefficient, including deterministic event ranks; no aggregation is implemented. Stage C replaces pair/time binaries with unique pair and timing choices, deterministic maximal-rate byte states and continuous path routing.

Run bounded gates: `python -B -m v42_exact.gates`, `python -B -m v42_exact.contracts`, `python -B -m v42_exact.real`, then `python -B -m pytest -q`. Run supervised full build/comparison and A1: `python -B -m v42_exact.supervisor`. A previous entered optimization must not be retried automatically. Production imports no complete-option oracle.

The A1 timer is separate from preparation/build/validation, with Seed 20260929, Threads 1, MIPGap 0.005 and TimeLimit 3600. Existing scientific objective order is preserved. No M1/A2/M2/Fresh AC runs here. Final receipts report actual measurements and certificate limits. Local logs/large physical artifacts are hashed in LOCAL_EVIDENCE_MANIFEST.json.

## Measured outcome

Selected F2: 2796366 binary, 5124335 continuous, 9358534 rows, 100455768 nonzeros; build 331.1238250999886 s. A1 optimize wall 3600.6734204999957 s; incumbent None, bound 0.6716023396111563, gap None; accepted False. Native grid, job population and physical/scientific authorities remain frozen.

Binary reduction is 7,005,709 (71.4717%); nonzeros fall by 16.130% but rows rise from 4,070,611 to 9,358,534 and continuous states increase. This is a measured size tradeoff, not a demonstrated solve-speed improvement. F1 is a complete measured build reused only under the cached-source proof; F0 is the immutable PR99 build receipt. F3 is ineligible because aggregation was not proved.

The native log reports presolve 109.93 s and initial root relaxation 1557.90 s. Gurobi returned TIME_LIMIT, zero solutions, one node, bound 0.6716023396111563. Incumbent and gap are null; physical validation is NOT_RUN_NO_INCUMBENT. No 0.5% certificate, accepted A1 or downstream execution is claimed. Native TimeLimit was 3600 s; return wall was 3600.673 s, within the preregistered 5-second publication grace.

Progress records retain requested and actual elapsed times. SIMPLEX was not journaled by the callback; external raw-log/RSS observations near 300/600/1800 seconds supplement the delayed callback records, with the timestamp of every stale bound stated. See MAY_A1_GUROBI.log and MAY_A1_EXTERNAL_OBSERVATIONS.json.

The full objective equivalence audit finds 1499 singleton classes because original deterministic tie rank offsets differ. An auxiliary audit excluding only that tie finds 117 classes, 97 non-singletons covering 1479 jobs. No aggregation/decomposition is asserted.

Validation: 341 tests passed (one inherited calibration warning), synthetic cases A–J, 16 adversarial authorities, 200 standalone pair/start contracts, 1106 mappings in each direction, and three complete-domain real subsets with all original native electrical rows. Real subsets certify equivalence and do not substitute for the full 1499-job May solve. All 385 original tracked files and the production source freeze are verified byte-for-byte.
