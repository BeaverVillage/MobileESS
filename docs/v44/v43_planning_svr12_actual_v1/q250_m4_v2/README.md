# Active Q250 / four-thread M policy

Entry point: `python -m v44.q250_m4_v2 --execute`, policy
`V44_M_Q250_BARRIER_THREADS4_GAP3_V2`, fresh campaign004.

B2 M1 and B3 M1/M2 use per-vehicle Q +/-250 kvar in original FULL variable
bounds and connected-Q rows, plus the same cap in Beam/fixed-route LP scoring
and export admission. PCS400/P300, SOC, routes and physical safety remain.
The Q restriction is an explicit new domain, identified in each M Case SHA,
request source SHA and checkpoint. No Actual command clipping is performed.
All M Native calls use four-thread Barrier, Joint gap3%; A stages retain one
thread, 5400 seconds and 0.5% acceptance. K48 total300, Joint total900, call
cap300 and the original return reserve remain unchanged. May02 retains the
existing robust Barrier/crossover settings. Golden003 is reused without A1
reoptimization; B3 A1 reuses same-date B1. All arms retain SVR12 Actual/Fresh.

One Case Worker processes B2 May01..07 first, then Main B0 -> B1 -> B3 per date.
campaign004 starts from May01 with new M models/clocks and no old M point or
checkpoint import. Historical strict source files and all prior Raw remain.
Full new-Q Actual/Fresh physical success has not yet been established.

The initial overlay's cloned solve namespace captured the pre-construction
optimizer. The unchanged Native scope guard rejected that call during model
construction, before optimize. Those failed source/attempt files remain in
campaign003. V2 resolves the original module's optimize function at call time,
so the original build_case Native0 capture patch works exactly as before.
No solver guard was removed or weakened. Regression tests now create the
adapter first and then patch native.optimize, matching production ordering.

Validation at commit: 167 lightweight regressions pass; original small M1/M2
model capture, exact matrix differences, policy/Case binding, scope restoration,
new polygon edges and unchanged A admission are covered. A tiny guarded Native
smoke configured Threads4 and passed; it is not a speed or physical benchmark.
Commit status: IMPLEMENTED_NOT_EXECUTED; runtime progress is recorded separately
in campaign004. No additional campaign validation loop was introduced.
