# Conversation A — R25K B4 Changelog

## Evidence-driven diagnosis
R25J/B3 confirmed B2 numerical scaling (`Matrix min 2e-06`) but all Auto/0/1 kernels remained at root node for the full 300 s. Auto had the best 300-s gap and is frozen for B4.

## Changes
1. Freeze MIQCPMethod=-1 when B4 is active.
2. Set CutPasses=3 to force a finite root-cut budget.
3. Add BranchPriority with STAY > occupancy > job/defer > mode.
4. Add exact `mode <= active_STAY` symmetry normalization.
5. Densify debt/SOC future-STAY implied cuts to every time step.
6. Add all-prefix projected SOC mobility-energy cover cuts.

## Not changed
MIPGap=3%, Threads=1, H54, 5-min cadence, objective, physical feasible set, previous-plan VarHint-only policy, causality and AC commit gates.
