BUILD7BR3 — REACHABLE MOVE-DOMAIN CONSISTENCY FIX

BR2 correctly pruned structurally unreachable move binaries, making mv a strict subset of the immutable moves authority. The departure-energy expression still iterated moves and looked up mv[(mid,h,slot)], causing KeyError for a deliberately pruned arc. BR3 iterates only mv.items() on every read side. An AST release gate forbids any Load-context mv[...] lookup in build_full. No physics, route feasible set, sparse-grid equation, memory setting, objective, tolerance, or no-look-ahead contract is changed.
