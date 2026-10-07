# Execution authority and timing

The user's latest instruction explicitly permits concurrent heavy optimization:
`있어도 그냥 진행해. 남는 cpu 코어가 있을 거 아니야. 메모리도 부족하지 않고 그냥 계속 진행해.`
`USER_CONCURRENCY_AUTHORIZATION.json` supersedes the preregistration's exclusive-concurrency requirement. Scientific equations, solver settings, Threads=1 and native TimeLimit=600 remain fixed.

A separately owned M-stage file-based runner was discovered after S_B finished. It had not matched the module-name concurrency guard. S_B overlapped that run and must not be used as an isolated timing or speedup comparison. Its raw primal residual failure remains a diagnostic observation, not an infeasibility proof. No shell is repeated to hide the overlap.

The May19 service-owned driver was briefly held while S_C's static child continued. The same PID/creation-time/command identity was resumed immediately after the user's instruction. This was not a memory/RAM/paging gate. No source or solver setting changed during the hold, and no native clock/point was resumed: S_C had not yet begun native optimization.

Later native solves may overlap the externally owned M-stage job under the updated authority. Nothing in this task modifies that job or its source. May19 native execution uses the frozen source commit; inherited compression evidence labels its scientific generator's earlier authority separately and does not assert capture at that earlier Git checkout.
