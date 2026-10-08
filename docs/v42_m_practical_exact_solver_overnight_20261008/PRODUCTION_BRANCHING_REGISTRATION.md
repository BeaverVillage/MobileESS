# Evidence-selected production branching

The one 1800s Cuts=0/Heuristics=0 control completed with status TIME_LIMIT, 2 nodes, 181531 main simplex iterations and Work3803.5253. Root main simplex iterations were180009, and the one completed nonroot LP used1522. After its OPTIMAL callback at286.802s, the remaining1513.381s added3295.1155 Work without another completed-node callback or a reported main-simplex-iteration increment. All observed cut counts were0. Independent full-domain source/objective/replay/bound audit PASS.

The exact internal subphase is unavailable. Expensive native branch-candidate/probing or other unexposed node work is an **inference**, not a proven cause. This is new measured node evidence, unlike another blind root-cut loop.

The initial production candidate selects one deterministic low-cost branch scoring architecture: **VarBranch=2 (Maximum Infeasibility Branching)**, Cuts=0, Heuristics=0, CutPasses=0. It keeps Threads1, Method2, NodeMethod1, Crossover2, MIPFocus3, MIPGap.005, all three tolerances1e-8, Seed20260929, DegenMoves0, and every original scientific coefficient/bound/type/row/objective/axis. Branch scoring changes; mathematical pruning and the scientific domain do not. This is one production choice, not a canary repeat or parameter sweep. No alternatives VarBranch0/1/3 are registered for testing.

One initial fresh production solve, TimeLimit10800s maximum, clipped to the same immutable deadline. Complete current replay-PASS incumbent as start. Never claim a native tree resume. At60min, fewer than10 nodes and <=1e-6 bound gain triggers a clean terminate, including payload-free POLLING inside a long internal operation. Switch attention to the already-running external M0, with no duplicated external root; consume/import its queue after it finishes. Additional production only if new incumbent/proof evidence changes the starting state; no identical deterministic restart after an unproductive prefix.

Observe MIPNODE_BRVAR on original variable axes, main node completion, native global bound, every incumbent, Work/Runtime/RSS and original replay. Any unavailable internal basis/node proof remains explicitly unavailable.

Official strategy definitions: [Gurobi VarBranch reference](https://docs.gurobi.com/projects/optimizer/en/current/reference/parameters.html#varbranch). POLLING carries no queryable payload: [Gurobi callback reference](https://docs.gurobi.com/projects/optimizer/en/current/reference/numericcodes/callbacks.html).
