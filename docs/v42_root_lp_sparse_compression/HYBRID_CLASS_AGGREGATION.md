# Exact staying counts with individual migration lanes

For N identical jobs, Y[k,s] is an integer histogram of complete authorized nonmigration trajectories. Each selected histogram unit contributes a whole GPU gang for precisely the fixed service duration D; its finish is at s+D. This preserves path-level service, not just total class service.

Each migration lane remains a complete optional individual-job formulation with its own source, checkpoint, pair, WAN start, maximal-rate payload recurrence, restart, final service and completion event. A lane is either entirely unused or carries exactly one migrated job. Class cardinality is sum(Y) plus sum(selected migration lanes) = N. No shared nonlinear remaining-payload minimum is introduced.

Forward mapping counts the nonmigrating trajectories and assigns sorted migrated paths to optional lanes. Reverse mapping extracts each complete migrated path and expands every integer staying histogram entry into that many complete paths. Sorting the resulting physical multiset and assigning it to stable UIDs completes the mapping. Only classes whose complete job/boundary/resource/Runtime/six-objective signatures match may use this symmetry.
