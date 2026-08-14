BUILD7BR5 — VERIFIED GLOBAL 8-THREAD + BOUND-FOCUSED 1.5% SPEED TRIAL

Forensic result from BUILD7BR4:
- The requested final-pass Threads=8 did NOT become the actual Gurobi runtime thread count.
- Gurobi logged `Thread count was 1 (of 16 available processors)` for every pass,
  including the final economic pass.
- The final economic pass alone took about 1555.8 s of the 1761.2 s total runtime.
- BR4 nevertheless closed correctly at 1.4929% and Fresh Exact OpenDSS passed.
- Peak Python RSS was only about 3.16 GB and >23 GB system memory remained available
  at termination, so an actual 8-thread trial has substantial memory headroom.

BR5 therefore applies Threads globally at the model environment (default 8) rather than
relying only on a per-pass setting. Gurobi 13 InheritParams=1 is explicitly enabled so
multi-objective environments inherit global runtime parameters. The final pass still
overrides only MIPGap=0.015 and MIPFocus=3.

Why MIPFocus=3:
BR4 found a strong incumbent much earlier than it reached the 1.5% stopping criterion;
the remaining runtime was dominated by slow best-bound movement. Gurobi documents
MIPFocus=3 as the bound-focused mode.

Other speed settings:
- MultiObjPre=2 for aggressive initial multi-objective presolve.
- Existing sparse branch-flow formulation retained.
- Existing exact reachability pruning retained.
- MIQCPMethod=1, PreSparsify=2, NodefileStart=0.5 GB and SoftMemLimit retained.
- MIPGap=0 and all 1e-9 tolerances remain for objectives 1–4.

Runtime verification:
After optimization BR5 parses Gurobi's own log. It will not claim the 8-thread speed
trial succeeded unless the final objective actually reports the requested thread count.

Override example if 8 threads proves slower or memory-heavy:
  MOBILEESS_GUROBI_THREADS=4 bash <runfile>

No physical constraint, causal authority, objective hierarchy, or no-look-ahead rule is
relaxed.
