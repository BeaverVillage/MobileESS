# M1 root LP exact sparse compression

Stacked on PR106 `0360f9db7a27068dc53665b263a93adfd870250f`. Accepted A1 anchor reused; zero A1 optimize calls. Original route/SOC/individual PCS source and all physical limits preserved.

Selected **M1-F3**, Threads=1, Method=2. Nonzeros: 138,620,454 → 8,282,350 (94.0252% reduction). Production root LP 180.04s, complete=True; PR106 reference 1600.32s was unfinished. Separate LP relaxation walls and MIP root processing walls are reported without conflation.

One optimize-only 1800s production: P1 UB=0.6696147314213984, LB=0.5718494710510547, gap=0.1460022544050313; P1 quality=False, P2 complete=False, physical=True, robust grid=True, **M1 accepted=False**. Remaining bottleneck: POST_LP_ROOT_PROCESSING. A2/M2/Actual/Fresh AC/IEEE8500 not run; Problem13 remains false.

See [50-question Korean review](FINAL_REVIEW_KO.md), [algebraic proof](EXACT_PROJECTION_PROOF.md), [structural comparison](FORMULATION_STRUCTURAL_COMPARISON.csv), [LP comparison](P1_LP_RELAXATION_COMPARISON.csv), [root canaries](ROOT_NODE_CANARY.csv), [frozen selection](FORMULATION_SELECTION.json) and [final flags](FINAL_FLAGS.json).

The three Method=1 LP attempts all reached their identical 600s cap without a completed optimum. Their original logs and comparison remain preserved. One secondary cohort used the same three candidates, Threads=1, Method=2, and the same 600s cap. The measured comparison to PR106 includes the method change and does not isolate the causal speed contribution of matrix compression alone.
