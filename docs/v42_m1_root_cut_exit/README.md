# M1 exact global-bound proof policy

Stacked on PR107 `f8dcd7e4545108aa5ab684ab97fe2dcd99fdbca8`. Inherited M1-F3, complete routes/SOC/individual PCS and 0.955–1.045 robust band are unchanged. A1 optimize=0; AUTO baseline reused without a solve.

At user request, CP0 was gracefully interrupted at 558.705s and preserved as a partial diagnostic; CP1 was cancelled and never executed. The goal was revised from root exit to useful global-bound proof. [Revised preregistration](REVISED_PROOF_EXPERIMENT_CONTRACT.json) supersedes the archived CP0/CP1 contract.

New primary: Heuristics=0, MIPFocus=3, CutPasses=AUTO, DegenMoves=AUTO, Method=2, Threads=1, Seed=20260929, MIPGap=.005, 600s cap and no NodeLimit. Cuts and individual families remain AUTO. Conditional DegenMoves=0 run=True; only permitted after completed root LP and >=120s post-LP root delay. Selected=PROOF_AUTO. Production authorized=False, run=False; its single cumulative optimize-only budget is 1800s. First branch or primal improvement cannot authorize production.

Final source=PROOF_AUTO: UB=0.6696147314213984, LB=0.571849460049452, gap=0.14600227083478132, nodes=1.0. Production P1 quality=False; P2 complete=False; independent physical=True, robust grid=True; **M1 accepted=False**. Remaining bottleneck=POST_LP_ROOT_PROCESSING_WITH_INSUFFICIENT_GLOBAL_BOUND_GAIN.

Interpretation is ROOT_LOOP_POLICY_EFFECT, an operational comparison rather than pure cut ablation or complete heuristic/probing isolation. Prioritize BestBd(t), Gap(t) and solver-certified quality. Callback observations carry their timestamps/ages; first non-root time is an observed upper bound on branch creation. All native logs are preserved. [Gurobi CutPasses](https://docs.gurobi.com/projects/optimizer/en/current/reference/parameters.html#cutpasses), [MIPFocus](https://docs.gurobi.com/projects/optimizer/en/current/reference/parameters.html#mipfocus), [DegenMoves](https://docs.gurobi.com/projects/optimizer/en/current/reference/parameters.html#degenmoves).

See [50-question Korean review](FINAL_REVIEW_KO.md), [proof canaries](PROOF_CANARY_COMPARISON.csv), [policy gate](SOLVER_POLICY_SELECTION.json), [acceptance](M1_ACCEPTANCE.json), and [final flags](FINAL_FLAGS.json). A2/M2/Actual/Fresh AC/IEEE8500 remain unrun; Problem13 FINAL_VALIDATED=false.
