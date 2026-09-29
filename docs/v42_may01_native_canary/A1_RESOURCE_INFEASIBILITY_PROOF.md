# Exact-safe May-01 A1 resource infeasibility certificate

This is a native-input necessary-condition certificate, not a full A1 MILP benchmark or an operating schedule. It stops complete-option enumeration before constructing the electrical model. A feasible relaxation would **not** pass the canary.

All 1605 source-admitted jobs have T2=false, so authorized execution starts equal their frozen reference starts. Pre-start site choice cannot change aggregate occupancy. A legal checkpoint migration is the only modeled action that can interrupt that original execution interval. The PR90 `validate` contract requires a positive integer transfer interval followed by restart before control_end=120. The native WAN authority allows at most one active transfer per slot. Thus at most 120 jobs can migrate, even granting the entire issue-origin horizon (more generous than D-day-only control).

Let b_j(t) be the original reference gang occupancy. Relax each job's migration indicator to 0<=z_j<=1, require sum(z)<=120, and remove **all** of its original occupancy when z=1, including before checkpoint. Omit destination compute, tail, rack, site, WAN path, checkpoint, electrical, and terminal constraints. This strictly enlarges the feasible set. Every original legal solution maps into this relaxation; none of these diagnostic deletions is accepted for execution.

The summed same-hour P2 nominal rows in `v42_native.envelope.bind` require sum_j b_j(t)*(1-z_j) + Q50(hour(t)) <= 780 even with uncertainty headroom zero. Q90-Q50 can incur reserve shortfall; Q50 and known service cannot. For each slot, removing the 120 largest live gangs gives an independent analytic lower bound valid even for fractional z (unit upper bounds).

At D-day slot 11 (02:45 AEST; issue-origin 35):

- 614 live original jobs occupy 780 GPU.
- The 120 largest live gangs total 286 GPU.
- Remaining known GPU is at least 494.
- C0 nominal is 742.672582512395 equivalent GPU (GPUh divided by its one-hour support).
- Required total is at least 1236.672582512395, exceeding 780 by **456.672582512395 GPU**.

There are 28 violating necessary rows. Gurobi independently returned INFEASIBLE (status 3) for the continuous superset, with 1605 variables, 97 rows and 62024 nonzeros. Its IIS contains the transfer-count bound and slots 33/35. `MAY01_RESOURCE_NECESSARY_BOUND.csv` permits a direct arithmetic audit; the certificate SHA-binds LP, IIS, request, receipt, and result.

The supervised invocation took 5.062s, including source loading and diagnostic work; optimize() took 0.012000s. These are **projection timings**, not full A1 runtimes. MIPGap parameter remained .001; actual gap, objective, incumbent, full-model counts, and timeout gaps are null. External cap was 600s; solver TimeLimit used the remaining budget. No timeout occurred.

The first launch failed before optimize() because Gurobi could not write an LP through the Unicode physical path. Its evidence is preserved in `PRE_SOLVE_IO_FAILURE.json`. A tested ASCII-temporary-output adapter allowed one subsequent optimization, with unchanged native input and mathematical constraints. No completed solve was rerun.

No M1/A2/M2 or Fresh AC is permissible without an A1 incumbent. More solver time, a new response kernel, or MESS electrical support cannot create GPU capacity. A source-authorized resolution of this nominal/known resource incompatibility is required before measuring the requested four-block computation. No automatic C0 scaling, T2 alteration, shift, clipping, service deletion, or capacity increase is proposed or applied.
