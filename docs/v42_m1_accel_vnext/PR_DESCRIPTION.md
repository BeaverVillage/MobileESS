Exact root-CG runtime is dominated by pricing and repeated RMP solves. Add isolated prototypes and bounded screening for five exact accelerators against frozen PR152 (63e81dc3b6d236549f566e65e07dcd05ac0a160c); no accelerator is selected and the authoritative 1,604-column checkpoint is unchanged.

- Persistent RMP/basis: exact matrix/objective identity; slower than cold (213.68 vs 203.53 seconds), rejected.
- Box stabilization: Discovery-only guidance LP did not finish optimally within its cap; unselected.
- Exact pricing: continuous-resource hybrid proof/toy equivalence; full-scale comparison incomplete and overlapping timing excluded.
- Exact parallel-arc elimination: zero eligible variables on the actual model; rejected.
- Integer-valid mode-linking cuts: toy arc-LP improvement but redundant for full D-W; root comparison interrupted, completed calls preserved without replay.

The single final paired experiment stopped at 125.07 seconds when available RAM fell below the preserved 1 GiB floor during candidate preparation. Actual foreign native overlap was recorded; timings are NONCOMPARABLE and cannot select a method. Following the latest user instruction, worker presence/overlap itself did not pause the final experiment. No authoritative continuation, Certification, branch nodes/B&P production, or May production was run from this lane.

Validation: 19 lightweight tests pass; full pytest reports 1,900 passed / 1 failed / 0 errors. The unchanged historical PR144 branch-scope assertion failure is independently reproduced on exact PR152 and documented, not suppressed. All 12,919 original tracked files remain byte-identical; independent original-matrix saved-point audits and SHA256 manifest checks pass. See docs/v42_m1_accel_vnext/FINAL_REVIEW_KO.md and VERIFICATION.json for results and limitations.
