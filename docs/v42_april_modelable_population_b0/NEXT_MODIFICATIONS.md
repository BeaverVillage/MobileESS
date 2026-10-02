# Required current authority changes before physical execution

The old missing-GPU NO-DROP gate is superseded. All modelable source fields are
complete on 30 days; unmodelable raw rows are retained separately, never imputed.

1. PR121 reference: pending UID 8504781 needs 96 GPUs and only fits AIDC05.
   On April 17/18, Q50-expired RUNNING jobs retain that site's physical capacity
   indefinitely without a causal completion receipt. Four later April 18 pending
   rows are retained behind it under strict FCFS. Do not use future Actual end times,
   revise the frozen placement after results, split the gang, drop or resize jobs.
   A reviewed common placement/release authority is needed to resolve this conflict.
2. Current CC4 date binding exists on all 30 days, but nominal execution-lag occupancy
   plus the known fixed reference exceeds 780 GPU on 15 days (maximum 1527.7423).
   A common, causal, grid-independent forecast/service capacity binding is needed;
   it must conserve full GPUh/tails and explicitly define any permitted queueing.
   This task did not silently introduce aggregate retiming, clipping or an anonymous
   LP job schedule. The per-slot capacity lower bounds do not depend on site ordering.
3. After resolving these common input authorities, certify J_FLEX complete options,
   generate date-specific current Planning grid coefficients and Actual causal
   occupancy, freeze common schedules, and run all April B0 diagnostics. Retain the
   0.95–1.05 primary Planning band and no Actual P/Q/schedule/route repair.

No old baseline recovery or extra raw GPU archaeology is required. No coverage
percentage gate is proposed. GPUh coverage remains not identifiable from source.
