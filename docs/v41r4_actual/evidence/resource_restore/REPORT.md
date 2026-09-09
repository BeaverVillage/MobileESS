# Temporary burst return correction

The burst exit condition counted every DA-eligible pending Actual policy, including policies whose date was occupied by a DA/Fresh worker. Date-exclusive dispatch prevented those units from running. As a result, no runnable Actual remained but the reservation stayed at DA2 + Actual8 instead of returning to normal4.

Correction: distinguish dispatchable pending Actual from pending units on occupied dates. Automatic exit requires no dispatchable pending Actual and no active Actual. NORMAL_4 remains sticky after the transition. Normal dispatch visits dates chronologically and runs each eligible policy Actual after its DA/Fresh, without global Actual-first priority.

The user requested return after the missed drain. Newly completed DA had since generated additional Actual work. All live workers fit within four, so the coordinator was replaced and normal4 was applied immediately without stopping or suspending any day worker. The adapter, resource authority, and status are operational changes only. Numerical method and performance bindings were verified unchanged. Regression evidence and before/after operational artifacts are stored alongside this report.
