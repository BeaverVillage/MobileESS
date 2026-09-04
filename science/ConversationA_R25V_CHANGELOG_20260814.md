# Conversation A — R25V causal multi-start and exact-CG round-trip reduction

Issue 153 completed in 1,992.6 seconds. Its exact compact phase ended when the
incumbent improved from -1927.2633 to -1929.6200; the certified combined gap
immediately fell to 2.9031%. The compact tree had already spent most of its time
searching for that feasible discrete plan.

R25V therefore shifts the preceding causal plan by one five-minute slot and
submits it as a partial native MIP start. Current h=H-1 decisions and h=H
occupancy remain undefined so Gurobi completes the new terminal extension.
The same-issue restricted-master solution is retained as a second independent
start. Both are non-binding and must pass current-model feasibility.

Exact root column generation now requests 32 paths per MESS and QCP solve rather
than 16. The reduced-cost closure rule, numerical guard, and lower-bound
authority are unchanged. The non-authoritative restricted primal phase moves
from 60/120/600 to 30/60/300 seconds (minimum/stall/maximum), and its auxiliary
primal enrichment cap moves from 96 to 64 paths per family.

No physical variable, row, AC QCP, objective coefficient, causal state,
OpenDSS gate, or globally certified 3% acceptance rule changes.
