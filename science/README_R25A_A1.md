# Conversation A — R25A / Acceleration A1 of 6

Implements exact Forward × Backward mobility resource pruning on top of R24.
No hours-long MIP solve is authorized in A1.
The compiler only removes a MOVE/state when an optimistic lower bound on remaining support debt already exceeds an unconditional physical upper bound on all possible remaining repayment after that decision.
Terminal service is unrestricted and STAY is legal, so backward spatial pruning is explicitly audited and is expected to be zero.

Next: A2 exact route dominance / equivalent-state merge.
