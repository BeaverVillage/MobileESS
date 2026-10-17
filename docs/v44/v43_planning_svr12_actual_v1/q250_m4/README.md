# Active policy: Q +/-250 kvar per vehicle, four-thread M stages

The user authorized a new M operating subdomain through
`V44_M_Q250_BARRIER_THREADS4_GAP3_V1`, entered with
`python -m v44.q250_m4 --execute`. This supersedes the older serial two-thread
overlay. The inherited cap300/barrier receipts are preserved as historical
baseline metadata; the final Q250/M4 overlay explicitly overrides them.

B2 M1 and B3 M1/M2 build Q variable bounds [-250,250] kvar and connected Q
rows with coefficient 250 into the original FULL model before matrix export,
exact projection, transport proof, independent K16/K32/K48 or Joint optimization.
The original PCS rating remains 400 kVA, active power limit 300 kW. SOC, energy,
routes, route authority, site capacity, WAN, voltage/thermal constraints and
feasibility tolerances retain their existing definitions. Row/column order and
count are unchanged. The original FULL domain is deliberately restricted; it
is not claimed mathematically identical to the historical +/-400 Q domain.

The original PCS/P polygon used by Beam and its fixed-route LP score is
intersected with Q +/-250, including newly introduced edge intersections.
The original FULL validator replays the new rows and bounds. An export guard
also rejects a per-vehicle Q value outside the cap; commands are never clipped.
The final M identity includes the Q policy SHA. New requests append the policy
sources to the source manifest and hash, and new stage checkpoints carry the
final policy explicitly. Historical strict source files are not modified.

All M Native calls, including independent K48 and Joint, configure Threads=4.
Root Method=2 (Barrier), Joint inner MIPGap=0.03, original K48 parameters otherwise
unchanged. May02 retains the existing homogeneous Barrier/robust crossover
basis settings. K48 total 300 seconds, Joint total 900 seconds, call cap
300 seconds and the original ten-second return reserve are preserved. Early
completion is allowed; the caps do not force a call to consume its full limit.

A1/A2 retain their original one-thread construction/solve environment, 5400
second budget and 0.5% acceptance threshold. May01 Golden003 A1 is reused
without reoptimization; B3 A1 reuses same-date B1. B0/B1 and Actual/Fresh have
no new Q optimization or thread policy. Actual/Fresh retains SVR12 AUTO/TIME
and its original independent safety verdicts.

Fresh campaign003 starts May01 B2 from zero. No previous M point, bound,
checkpoint or clock is imported. One Case Worker runs at a time: May01 through
May07 B2, then Main per date B0 -> B1 -> B3. B3 M2 follows its same-case A2.
campaign001/campaign002 and all original Raw remain preserved. The interrupted
May02 call in campaign002 is explicitly marked user-interrupted and is not
promoted as a completed or reconciled Native call.

At commit: IMPLEMENTED_NOT_EXECUTED. All 151 lightweight regressions passed.
The original small M1/M2 builders were captured without optimization to compare
matrix differences: only Q bounds and connected Q coefficients change. The
two-variable Native guard smoke configured four threads and passed; its tiny
presolved model used one execution thread, so it is not a parallel speed test.
No full new-Q Actual/Fresh PASS is claimed. Live execution status belongs to
the separate campaign003 runtime receipts.
