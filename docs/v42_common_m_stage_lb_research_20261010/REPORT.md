# B2 M / B3 M1 / B3 M2: proved finite envelopes and short LB trial

Draft PR [#202](https://github.com/BeaverVillage/MobileESS/pull/202) continues
`codex/v42-b2-lb-rescue-20261010`. At this continuation's start, remote and local
HEAD were both `b1e6224a1e51a2d0323f74de622be0a2e8f1ac5f`, with a clean worktree.
PR #201 was checked at `6539d06f6cfab23c78d649b7f5ed5da2aabf4724` and the
original B3 PR #191 at `40b6f94dcd80e470f93c73b7479fdd2d9d91c3f2`.
Initial common algorithm/cap commit: `1eae7e5574c5028b24535e4a1d3cd0cd5b427994`.
Finite-envelope implementation: `f90c514d7ea42311d14fd404d14d55d399981057`.
The PR HEAD identifies the final reporting commit.

**Implementation PASS is limited to the actual saved B2 numerical data and
tested B2/B3 adapter contracts. Scientific Improvement PASS was not obtained.**
The single fresh RMP returned finite Pi but failed the strict original-coordinate
dual sign gate; no fresh candidate was independently certified. This is research,
with no production promotion, new date PASS, or campaign restart.

## Confirmed defects and remaining causes

The common DateBudget previously ignored an explicit requested cap and passed
the full remaining 5,400 seconds. The research implementation uses
`min(valid requested cap, remaining measured Native budget)`, rejects invalid
explicit caps, and preserves omitted-cap defaults and legacy B3 ledger replay.
Actual Runtime and overshoot are retained; unknown Runtime remains quarantine.
The reused six real Gurobi TimeLimit readbacks did not call optimize; they are
parameter checks, not executed production DateBudget or B3 stage measurements.
The new actual RMP readback below also confirms TimeLimit30 and Threads1.

The second confirmed defect was a finite-original-box precondition in DualSearch
that rejected the real C3A's 48,547 unbounded helper axes. B2 already had the V18
proof provider; B3 did not. The fix binds the existing equality-implication proof
to a stage-local calculation and original independent certification path, without
replacing model infinities by arbitrary numbers.

Saved B2 evidence distinguishes May01/02's finite but weak duals and valid negative
pricing certificates from May03's no-finite-Pi/pricing-NOT_RUN. The existing
L1/L4-once, L2/L3-twice caps and zero-gain scheduling favor UB after the pilots.
Increasing only those caps would repeat unsuccessful LB work. May01's signed
finite-box residual penalties were dominated by injection_Q, injection_P and
response_line_Q (approximately -8.25650e12, -3.01991e12, -2.24959e12).
This is original B2 evidence, not B3 observation. The short fresh RMP's invalid
signs provide an additional measured admission failure. They do not establish a
solver NUMERICAL status, nor prove that the full LP optimum or integer hull is weak.
Actual B3 numerical convergence/dual quality remains NOT_MEASURED.

## Common algorithm and finite-envelope contract

The opt-in shared DualSearch computes exact rational residual sign breakpoints,
ranks convex blends/equality candidates, suppresses repeated dual/column content,
and delegates at most two proposals to the original independent checker. Novel
catalog content after independently certified gain >=0.001 may authorize one
additional bounded LB opportunity. That threshold is an experiment filter; the
final M-stage acceptance remains the original independent 3% Global gap.

For a proved box the unchanged theorem is
`LB = c0 + b^T y + sum_j min(l_j*(c-A^T y)_j, u_j*(c-A^T y)_j)`.
Coefficients and duals are exact rationals of their stored binary64 values.
For <= rows y<=0; for >= rows y>=0; equality multipliers are unrestricted.
Ranking, RMP objective, Native ObjBound and mere finite Pi never publish Global LB.

`ProvedEnvelope` owns one independently derived/verified box per issued factory,
case and attempt. Its identity includes stage, date, source, input, entire fixed
decision, case, matrix and domain SHA. Every access revalidates the source/context
and original matrix/domain bytes. The cache seals proof and bound content, keeps
private read-only arrays, and returns copies. Changed SHA, foreign stage/date,
inward rounding, delegate drift or cache tampering fail closed. Already-finite
original bounds need no derive/verify. No global, disk or cross-attempt proof cache
is admitted. Restored B3 certificates create a new factory and replay proof anew.

The B2 adapter reuses `_finite_box_provider()` and the original V18 derive/verify;
it does not introduce another envelope derivation implementation. The common
M-stage certification callback sends its own proved finite bounds to the unchanged
original checker. The existing V19 -> V18 -> common M-stage rebinding/restoration
route is retained and tested. Production sealed request admission is required by
the adapter but was NOT_RUN against a freshly built real research case here.

B3's provider is issued under the original immutable SourceRegistry and binds
the complete current A1 for M1 or current A2 for M2. An opt-in checker scope routes
original aliases and NONUNIT certificate-only projections through the stage's
proved envelope; unit domains/models remain intact. Original exact decomposed
pricing sum versus full signed certificate and final physical/UB verification
remain mandatory. Pre-scope original delegates are guarded, including during final
verification; scopes restore aliases and ContextVar in finally. No M1/M2 proof,
dual, bound, column or Runtime is shared. The unchanged default coordinator retains
A1 -> M1 -> A2 -> M2. No qualified actual fixed A1/A2 input was available, so B3
selected-C3A infinity counts and Native experiments are NOT_RUN. The provider tests
use marked fixture models/cases and the real original proof/checker math.

## Native-zero gates and actual B2 data

The earlier 30 focused tests PASS (7.2510267 seconds), six parameter readbacks
PASS (0.0570421 seconds, optimize0), and owned saved May01 certificate replay
(16.661916 seconds) were reused, not rerun. The original exact checker and box
verifier each matched the saved case/dual/exact LB; this is not a certificate for
a newly built research source/date.

For this defect, **16 new tests + 8 affected existing tests = 24 unique PASS**,
zero final failures/errors/skips and Native/model attempts. Initial execution
was 23/24: a genuine B3 lazy delegate snapshot captured a changed helper too late.
It was fixed to use the factory's pre-scope snapshot and validate active final-check
delegates. Only the affected B3 six new + five old tests were rerun, 11/11 PASS.
Actual test executions=35, combined gate wall=8.5806686 seconds. The original
entire suite and earlier 30 tests were not repeated. Source/protected bytes matched
within each gate; the single intentional code fix between gates is recorded.

Actual saved May01 C3A has 779,129 rows and 306,040 columns, including **48,547
unbounded helper axes**. The actual `_finite_box_provider` source function and
DualSearch.select were exercised once in the completed Native-denied audit:
derive1, independent verify1, select1, original checker2, cache hits3. The proof
contained every original feasible point; A/d, original bound bytes, matrix/domain
SHA and input/source bytes matched before/after. No
`FINITE_ORIGINAL_BOX_REQUIRED` remained in this completed actual-data selection.
Its exact independently checked selected bound was negative, not adopted; the
saved positive L1 remained. Receipt wall=199.7522482 seconds, including profiling
overhead (derive42.9101362, verify46.3657310); this is not Native Runtime.

This audit explicitly substitutes two saved-data admission hooks for the sealed
factory checks. Full production factory issuance and new research case construction
are NOT_RUN, not silently treated as PASS. Numerical arrays, original V18 proof
and original rational checker are real. An earlier codec failure and interrupted
partial derive from excessive profiler I/O are preserved separately: completed
receipt counters1/1 are not a claim that all historical derive entries totaled1.

## Single actual May01 RMP30 result

User-authorized stopping of the existing campaign was completed before this
finite-envelope continuation. The restart source was identified as the exact
Windows Supervisor task's PT5M trigger; task XML was preserved and that task
disabled. Exact owned workers/supervisor were stopped; source, queue, scientific
ledger and frozen results were preserved. Unfinished Runtime was recorded UNKNOWN.
Fresh resource preflight found no execution collision for this one private trial.
This work does not re-enable the task or start any campaign.

The published PR #201 B2 representation was used on the original saved RMP:
`A_native=R*A*S`, `x=S*z`, `Pi_original=R*Pi_native`, with exact positive dyadic
row/column maps. All coefficient/RHS/domain/start and post-solve model readbacks
were checked. A correct infinity readback guard accepts only same-sign infinity
or the backend infinity sentinel for originally unbounded axes; finite bounds
remain byte exact. It does not change the scientific domain. This standalone
saved-data trial did not create a new production case or adapt B3 scaling.

| Measurement | Actual result |
| --- | --- |
| Native calls / LP pricing / P2 | 1 / 0 / 0 |
| TimeLimit readback / Threads | 30.0 seconds / 1 |
| Measured Native Runtime | 30.115000009536743 seconds |
| TimeLimit overshoot / experiment budget overshoot | 0.11500000953674316 / 0 seconds |
| Solver status / SolCount | 11 INTERRUPTED / 0 |
| Finite Pi / original-coordinate restore | Finite Pi returned; byte-exact inverse restoration confirmed |
| Sign admission | FAIL: 1,057 rows, ORIGINAL_PI_SIGN_INVALID_NO_CLIPPING |
| Fresh DualSearch / original candidate checker | NOT_RUN after sign rejection |
| Fresh independently certified Candidate LB | NOT_AVAILABLE |
| Preprocessing / model build + readback | 4.4101322 / 1.4027843 seconds |
| optimize wall / whole single trial wall | 30.6938255 / 37.4357030 seconds |

Runtime was neither capped nor rewritten to30. The development experiment's
aggregate ceiling210 (RMP30 plus conditionally four LP45) is separate from the
unchanged production total5400 and is not permission for another RMP. The invalid
Pi was not clipped into an admissible dual. No fresh mixture, equality repair,
duplicate solve, LP pricing or expanded trial followed. Native0 saved-Pi diagnostics
found 1,057 sign violations; the largest was voltage_upper[63,239], a <= row with
positive multiplier `1010397306016255/512` (about1.97343e12). This is substantial,
not an accepted rounding tolerance. The raw restored dual differs from L1 on29,268
rows; full float residual c-A^Ty max absolute=45,875,785,601.468925, nonzero50,168.
That float residual is diagnostic, not an exact certificate. After the exception,
fresh read-only source/input and protected1005+approved2 checks still matched.
The raw optimize return and ledger retain status/Runtime before mathematical
admission. The persisted pre-optimize inflight flag was false before the in-memory
flag update; the physically returned final call row is true. The raw history is
preserved, not backfilled. Total research wall across interrupted/preflight/gate
history is UNKNOWN; the measured phases are not summed into a fabricated total.

## Stage results and preservation

| Stage | Implementation evidence | Certified bracket before -> retained after | Actual science |
| --- | --- | --- | --- |
| B2 May01 M | Actual saved 48,547-axis proof/select PASS; rebound contracts PASS | LB0.38895900867731903 / UB0.5406756909532602 / gap28.060570285386962% -> unchanged | Fresh RMP sign gate FAIL; no new certified LB; improvement PASS not obtained |
| B3 M1 / fixed A1 | Stage provider/checker/isolation fixtures PASS | NOT_AVAILABLE -> NOT_RUN | Actual selected matrix/proof/Native NOT_RUN |
| B3 M2 / fixed A2 | Separate stage provider/checker/isolation fixtures PASS | NOT_AVAILABLE -> NOT_RUN | Actual selected matrix/proof/Native NOT_RUN |

No B2 certificate or Runtime is reassigned to B3. No new date/campaign PASS or
final certification is inferred from this saved checkpoint. The original L1 exact LB is
`72763421188672844413290555716948908315532491447013/187072209578355573530071658587684226515959365500928`.

Original matrix builders, integer domains, voltage/current/SOC/travel/mode/PQ
rows, raw rational checker, V18 derive/verify and original complete pricing retain
their source bytes. The original scientific A/d and bounds were preserved. In the
campaign's 1007-file source catalog the two declared shared research changes are
budget/m_stage; the other1005 match existing hashes. Frozen Source35/36/37, input
artifacts, queue, ledger and B3 reservation are preserved. Original precision,
Threads1, P2zero, Native total5400, M gap3% and A gap0.5% are unchanged.
No production deployment, long solve, full-month experiment or campaign restart
was performed. The Draft does not qualify production promotion.

## Failed candidates and next research priority

The saved exact raw-dual ray maximum over49 distinct breakpoints/23279 crossing
columns is alpha0/gain0. Earlier equality arithmetic cancelled48,547 helper
residuals but still gave a very negative bound; its first run failed a source guard
and remains diagnostic. The newly qualified actual-data selected candidate also
did not improve L1. The fresh finite RMP Pi failed sign admission. These outcomes
do not justify more blend/equality micro-adjustment or longer Native execution.

The next priority is exact temporal integer strengthening of the 96-slot
location/travel/SOC/mode/PQ structure. A Native0 toy pilot proves a SOC-aware
multi-time conflict `z[u,s,t]+z[u,r,v]<=1` when an optimistic upper-energy path DP
proves the ordered visits unreachable under original losses and maximum charging.
Its exact toy fractional witness violates by1/2; all toy original integer feasible
plans are preserved. This is a proof pilot, not actual May01 separation or LB gain.
Actual matrix separation, complete original-grid validity replay and stage-specific
gain would precede any further Native test. Existing single-slot hull constraints
are retained; no new production cut or domain change was added here.

Compact receipt hashes, phase measurements and source hashes are in
[EVIDENCE.json](EVIDENCE.json). Large arrays/proofs and failed raw histories remain
in their read-only external artifact locations; they are not copied into this PR.
