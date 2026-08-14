# Conversation A — R25R

R25Q committed authoritative PASS results through issue 135 and stopped before
committing issue 136.  At issue 136 root-CG iteration 4, an OPTIMAL QCP solve
produced a finite reduced-cost accounting mismatch of
`0.00011129066137919501`.  This was above the fixed `0.0001` audit tolerance
but below the frozen conservative hard cap `0.0005`.

R25Q correctly attempted stricter QCP-dual solves, but the final stricter solve
returned Gurobi `SUBOPTIMAL` (status 13).  The recovery branch then discarded
the earlier OPTIMAL snapshot and failed closed.  R25R retains the best OPTIMAL
snapshot before every stricter retry.  If a later retry is non-optimal, the
retained snapshot may be used only when its measured error is finite and inside
the unchanged hard cap.  Exact pricing closure uses that measured guard, and
the minimization lower bound is weakened by the guard once per MESS.  Branching
state is also captured from the retained OPTIMAL solution rather than read from
the failed retry.  When such a bounded OPTIMAL candidate exists, two stricter
retries are attempted; deeper retries continue only when no finite candidate is
inside the hard cap.  This avoids repeatedly driving a numerically fragile QCP
barrier below `1e-10` after a conservative certificate fallback is already
available.

The same lifecycle repair is applied to root and child QCP pricing.  No
constraint, objective coefficient, causal transition, 3% target, or physical
commit rule changes.  R25R resumes from the SHA-bound issue 135 POST state and
runs issue 136 through 166 without solver time or node limits.
