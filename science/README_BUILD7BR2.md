BUILD7BR2 — SPARSE GRID + MEMORY-HARDENED FULL-54 PILOT

BUILD7BR1 did not return a solver status. The WSL/Ubuntu session terminated abruptly
after the presolved MIQCP reached 130,727 variables, 113,833 binaries, 3,159,255 linear
nonzeros, and 1,705 quadratic constraints. No Python exception, Gurobi status, wrapper
trap, or final result archive was produced.

The parent formulation also expanded every downstream branch-flow expression directly
inside voltage and line constraints, producing 20,993,620 linear nonzeros before
presolve. BR2 replaces that dense symbolic expansion with explicit branch-flow
variables and local nodal-balance/voltage-recursion equations. This is algebraically
equivalent for the frozen radial anchored-LinDistFlow contract but substantially
sparser.

BR2 keeps Threads=1, MIPGap=0, MIPGapAbs=0, and all 1e-9 solver tolerances. It uses
Gurobi's exact MIQCP outer-approximation method (MIQCPMethod=1), PreSparsify=2,
NodefileStart=0.5 GB, and a dynamic SoftMemLimit with WSL memory headroom.

It also removes only structurally unreachable MESS route binaries and adds the
previously-required 24 dedicated MESS service-transformer kVA constraints across the
full future horizon.

Before optimize(), BR2 writes a PREOPT checkpoint outside the result directory and then
updates a live heartbeat approximately every 20 seconds. If WSL is externally killed
again, these files provide resource/model evidence even when the final archive cannot
be created.

No physical limit, SLA priority, no-look-ahead contract, forecast authority, objective
priority, MIP optimality gap, or feasibility tolerance is relaxed.
