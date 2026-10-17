# Active policy: one Worker, two-thread Barrier M stages

The user's latest instruction supersedes the previous two-date B2 concurrency:
`V44_SERIAL_ONE_WORKER_M_BARRIER_THREADS2_GAP3_V1` is the active operational
policy, entered through `python -m v44.serial_m2 --execute`.

Only one Case Worker runs at a time. B2 processes May01 through May07 in order;
then Main processes B0, B1 and B3 per date. B2 M1 and B3 M1/M2 use Solver
`Threads=2`, Root `Method=2` (Barrier), Joint `MIPGap=0.03`. K16/K32/K48 also
use Threads=2 and Barrier; their original model, independent LB proof and total
300-second budget remain unchanged. Joint total 900 seconds, call cap 300
seconds and the existing ten-second return reserve remain unchanged.

A stages retain Threads=1, their 5400-second budget and 0.5% acceptance gap.
Actual remains one Worker with the same SVR12 AUTO/TIME physics and checks.
B3 reuses same-date B1 A1; Golden003 May01 A1 is not reoptimized. Fresh
`campaign002` starts May01 B2 with a new M model and new K48/Joint clocks, no
old M incumbent or clock imported. The first full Case finishes before May02
B2 starts. All `campaign001` Raw and measured ledgers are preserved.

This is an explicit overlay over the immutable original V43 science. Its
final settings override the older cap300/barrier operational metadata. Both
the inherited policy and the final policy source SHA are retained. Original
source files are not edited. The M-only scope routes the original Native
thread assignment and its thread guard together; every day/arm/model/lease,
source, P2 prohibition and physical constraint check remains active. A/Actual
and the strict defaults are restored on scope exit.

For the measured May02 Joint crossover stall only, retain the validated
homogeneous Barrier and robust initial crossover basis settings. The identical
first Joint model produced one unique FULL-verified point at UB
`0.5904364205096045` in the separate diagnostic. Its Root relaxation completed
in 178.59 seconds (189 seconds including preceding work); first integer
candidate was at 197 seconds, and the accepted literal FULL point was found
at 237 seconds. Earlier first candidates did not pass the literal integer
gate and were not accepted. This diagnostic is not a campaign Actual/Fresh
result and its point is not imported into the fresh campaign.

The requested Root LP comparison used the same saved May02 first Joint model,
one common MIP presolve and two independent continuous LP copies. Both had
177758 rows / 23210 columns / 955147 nonzeros, exact equal coefficients,
bounds, RHS and objective. Both ran sequentially on logical CPU 0 with one
thread and a 300-second limit. Barrier reached OPTIMAL in 91.807 seconds;
Dual Simplex in 212.925 seconds (2.319x). Objectives agreed at approximately
0.5305661927004168; independently computed row residuals were 1.0232e-11 and
7.2077e-11. This isolates algorithm choice on that extracted LP, not the
effect of two concurrent dates. Its common presolve differs from the internal
MIP preprocessing trajectory, so do not equate its times with production Root
times. Production CPU affinity is not changed by this comparison.

The requested 3% inner MILP Gap can stop integer search earlier after a feasible
incumbent exists. It does not directly accelerate the Root LP. The fixed-route
P/Q/SOC candidate score is a separate continuous HiGHS LP (two-second cap,
no MIP Gap), not a FULL UB or global LB. Original FULL and independent global
gap checks remain in force.

Prestart verification: 135 lightweight tests PASS, plus a separate tiny Native
guard smoke call confirming configured Threads=2. No full physical simulation
was added as a prestart check. The production campaign contains no additional
validation loop. There is no general speedup guarantee or 28-Case PASS claim.
The existing monitor URL and screen are retained and show the serial policy.
