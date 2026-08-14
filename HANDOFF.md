# R25R Stage-1 handoff

## Objective

Complete and verify the 54 causally chained Stage-1 rolling issues 113–166 with
the frozen scientific contract:

- five-minute cadence;
- H54 look-ahead (4.5 hours), with h0-only physical commit;
- four Gurobi threads;
- no solver time or node limit in the current exact completion run;
- globally certified modeled-total-objective gap at or below 3%;
- numerical, causality, transition, and Fresh Exact OpenDSS gates before commit.

Do not treat the restricted-master native Gurobi MIP gap as the scientific gap.
Only `global_certified_gap`, formed from a feasible incumbent and an exact
all-column lower bound, is authoritative.

## R25Q failure and R25R correction

R25Q stopped at issue 136, root column-generation iteration 4. A reduced-cost
accounting discrepancy of `0.00011129066137919501` exceeded the fixed `0.0001`
audit tolerance. A stricter retry then returned Gurobi status 13 (`SUBOPTIMAL`).
The implementation had discarded the preceding fully `OPTIMAL`, finite dual
snapshot even though its measured error was within the conservative hard cap of
`0.0005`.

R25R:

- retains the best fully `OPTIMAL` root and child dual snapshots;
- retains the matching branch candidate and numerical parameter state;
- accepts a retained bounded snapshot only within the hard cap;
- weakens the minimization lower bound by the measured numerical guard;
- limits stricter retries to two when a bounded candidate is available, while
  retaining the full retry schedule when no safe candidate exists;
- verifies the R25Q prefix and resumes at issue 136 without rewriting the
  committed issues 113–135.

No physical feasible set, objective, causality rule, or 3% gap semantics was
changed.

## Frozen lineage

- R25P parent result SHA-256:
  `0ed41aa7bdc1f055dde5fd7c50e4ceffb4d4cc0a1795d0ec1b37d49481fa9833`
- R25Q parent result SHA-256:
  `8d8c8f15bdfbc3e9200aeebb88f8a262f4da2e727d1155ac76b989f42b7cc2b0`
- issue 135 post-wrapper SHA-256:
  `9800ab463f99727ecf551f228953dbe1467f9e748ef1727e2bad92673568e66a`
- issue 136 PRE/internal-state SHA-256:
  `94eb40044d0089ce26fcc298675952a5a154277e48371412c4871edb447b7625`
- R25R science bundle SHA-256:
  `4c2e39b4f136f36a6d3c13f61acb93a7f32b256cfc75d06404cef8fe9ddf312d`

## Validation already completed

- full `science/release_self_test.py`: PASS;
- R25R retained-optimal-dual proof: PASS;
- exact packaged issue 136 root diagnostic: PASS;
- issue 136 root pricing closed in 19 iterations with guarded lower bound
  `-767.2110384345891` and maximum reduced-cost audit error
  `7.10743213610563e-05`;
- diagnostic performed no h0 commit and no long integer/B&P solve.

## Runtime snapshot

At the 2026-08-14 handoff snapshot, the external WSL run was still healthy and
must not be interrupted by repository work:

- issues 113–148 completed and committed: 36/54;
- issue 149 was `OPTIMIZING` on four threads;
- process CPU was about 382%, RSS about 3.5 GiB, with no memory pressure;
- issue 149 exact all-column root objective was about `-1698.079891`;
- current incumbent was about `-1645.691820`;
- conservative global certified gap was about 3.18%, not the displayed native
  restricted-master gap of about 1.83%;
- a root-only 3% certificate would require an incumbent of approximately
  `-1648.62` or better.

The active runtime and its result archives are intentionally not committed.
After completion, inspect the generated `ConversationA_R25R...tar.gz` before
declaring the Stage-1 final freeze.

## Performance finding and next decision

The slow issue is dominated by integer search, not AC power flow. On issue 149,
root exact pricing/QCP took about 132 seconds while the restricted integer master
ran for more than 3,300 seconds and explored roughly 600,000 nodes. Replacing the
grid model alone with a sensitivity OPF therefore does not address the primary
bottleneck.

Proposed next work, pending explicit approval:

1. Add honest progress output that labels the Gurobi value as
   `RMP_NATIVE_GAP` and separately reports `GLOBAL_CERTIFIED_GAP` and the 3%
   incumbent threshold.
2. Stop using unlimited `MIPGap=0` optimization for a restricted master whose
   scientific role is incumbent generation. Use a bounded primal-search phase
   with an objective stop at the exact certificate threshold, then transition to
   an explicitly selected bound-strengthening or fail-closed path.
3. For operational real-time use, separate the exact offline certificate from a
   hierarchical controller: slower discrete route/work scheduling and a fast
   five-minute continuous dispatch layer.
4. A sensitivity-based linear OPF may be used in that fast lower layer with a
   trust region, refreshed sensitivities, Fresh OpenDSS h0 verification, and a
   corrective fallback. It should not be presented as the fix for the current
   mobility-integrality bottleneck.

Do not relax the scientific 3% criterion or alter the causal state chain merely
to improve runtime. Any online/offline contract split must be explicit and
separately validated.
