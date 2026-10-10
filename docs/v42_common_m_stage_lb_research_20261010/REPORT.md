# Common B2 M / B3 M1 / B3 M2 lower-bound research

This is a development-only change based on PR #201, remote head
`6539d06f6cfab23c78d649b7f5ed5da2aabf4724`. PR #191 was checked at
`40b6f94dcd80e470f93c73b7479fdd2d9d91c3f2`. Of the requested B3 bridge,
numerical policy, runtime, operations and common M-stage files, their base
versions differ only by one source-runtime expression between those heads.
Implementation commit: `1eae7e5574c5028b24535e4a1d3cd0cd5b427994`.
Draft PR: https://github.com/BeaverVillage/MobileESS/pull/202

No production promotion is justified by this report. The existing campaign
was stopped by the user's earlier direct instruction, but subsequently a new
supervisor and three workers were observed. Their restart cause was not established.
This worktree does not stop those current workers, restart the campaign,
change its queue or B3 reservation, or modify its frozen
sources. No date is declared PASS by these development gates.

## Observed causes and limits

The saved Source36 B2 observations distinguish separate failures:

| Cause | Evidence | B3 M1/M2 evidence |
| --- | --- | --- |
| RMP numerical convergence | May01/02 returned finite Pi from a time-limited RMP; May03 returned no finite Pi and skipped its L2 pricing | Code inspected; actual solver NOT_RUN |
| Weak dual quality | May01 L2 finite-box correction about -1.51325e13; May02 about -2.61418e12 | NOT_MEASURED |
| Pricing or certification failure | May01/02 completed original four-unit pricing and obtained valid negative certificates, correctly not adopted; May03 pricing NOT_RUN | NOT_RUN |
| Scheduler prematurely excludes LB work | L1/L4 once and L2/L3 twice; after zero-gain pilots the original efficiency selection favors UB. Increasing only the caps does not fix this | Same rebound common scheduler, route verified |
| Weak LP relaxation | Possible, but no complete exact primal/dual optimality witness was established; NOT_PROVEN | NOT_PROVEN |
| Time-coupled integer hull | All 96-slot route/SOC/mode rows remain. L4's identical LB does not establish exact integer pricing or hull closure | NOT_PROVEN |

The original rational theorem remains
`LB = ObjCon + b^T y + sum_j min(lower_j*(c-A^T y)_j, upper_j*(c-A^T y)_j)`.
Every stored binary64 coefficient is interpreted as an exact rational. Dual
signs are `<=: y<=0`, `>=: y>=0`; equality multipliers are unrestricted.
Large residual penalties are dominated by injection_Q, injection_P and
response_line_Q (May01 approximately -8.25650e12, -3.01991e12 and -2.24959e12).
May02 also has a large response_line_correction contribution (-4.85051e11).
Weighted RHS, residual and group terms exactly reproduce the saved certificates.
Raw RMP duals and assembled full pricing duals are distinguished throughout.

Source35 and Source36 have different case identities even where their stored
dual bytes and numerical bounds coincide. No certificate was reassigned to
another source, B3 stage, or fixed input.

## Algorithm and actual stage connections

`v42_m1_anytime.dual_stabilization` is shared by all three opt-in paths. It
uses exact rational convex blending and every residual sign breakpoint along
the segment. The finite-box expression is concave: a crossing changes the
right slope by `-(upper-lower)*abs(delta residual)`. This finds the exact best
weight, including weights a fixed grid misses. A triangular affine-equality
repair preserves rational input and every inequality multiplier. Computational
ranks are candidates; at most two candidates go to the original independent
checker. Only the original complete pricing certificate and Frontier publish LB.
The tiny exact test `x=1/2, 0<=x<=1, objective=x` demonstrates a useful weight
`alpha=1/64` between dual0 and dual64: exact LB1/2, while every positive coarse
grid weight is too large. This is a synthetic theorem witness, not a B2/B3 day result.

The pool is newly constructed per stage/attempt and binds stage, day, source,
input, full fixed-input SHA, case, selected matrix and selected domain. Dual and
pricing content keys consume identical attempts before delegation, including
failed and zero-gain calls. RMP catalog keys hash mathematical unit vectors,
not output filenames. A novel catalog following an independently certified
gain of at least 0.001 may permit one additional bounded L2 after stagnation;
the original UB methods and reserve checks remain. This is one experimental
opportunity, not a guarantee that its next solve will improve LB. The 0.001
threshold uses an exact Fraction and is separate from final gap acceptance.

B2 calls `factory_for_request(path)` and `worker.run(path, lb_rescue=factory)`.
The factory verifies the actual sealed request and current fixed B2 packets.
A same-code rebound sets the optional keyword default, so the existing
V19 -> V18 prepare/seed routing is preserved. For unbounded affine helpers,
the original source-pinned `certificate_box.derive` and independent `verify`
provide a computational finite-box view. Original model bounds remain intact.
New research manifests must explicitly declare the new common module and
updated common source hashes; existing production manifests are not rewritten.

B3 calls `MSourceBridge.execute(context, ledger, progress, lb_rescue=factory)`
with `factory_for_context(context, registry)`. The original immutable
SourceRegistry resolves both the adapter and common module after admission.
The entire fixed AIDC payload, planning, PCC authority, selected C3A matrix
and domain are verified. M1 uses its A1 decision and M2 its A2 decision;
separate pools and certificates are required. Static source API SHA/signature
entries were updated and checked against real source AST for both stages.
The default SourceCoordinator continues its original A1 -> M1 -> A2 -> M2
calls without enabling this research option. If a stage has no prepared proved
finite box, optional stabilization records NOT_RUN and retains original pricing.

The common pipeline remains `feedback_master -> dw RMP -> original full-domain
four-unit pricing -> independent signed Global certificate -> Frontier -> final
integer/physical and exact LB replay`. Extra RMP closure evidence is not claimed
for a stabilized price different from the original RMP price. Original Global
certification and final replay remain mandatory.

## RMP representation and Native budget

PR #201's B2 RMP adapter is not automatically reused by B3. It depends on
B2-owned construction/entry guards; B3 resolves its own model and ledger under
SourceRegistry and a different numerical policy. The shared dual search is
independent of that adapter. The standalone B2 short experiment uses the
published PR #201 representation, not the uncommitted production follow-up.

The exact representation is `A_native=R*A*S`, `x=S*z`, `Pi_original=R*Pi_native`;
RHS, costs, bounds and complete starts are transformed consistently and checked
by exact array readback. Convexity/lambda identities and original coordinates
are retained. No coefficient is dropped or perturbed. Eligibility and better
coefficient range do not prove conditioning, convergence or LB improvement.
B3 scaling-performance validation is NOT_RUN.

A concrete common budget bug was fixed: DateBudget ignored requested_seconds
and passed all remaining Native time, even for RMP30 or LP45. It now uses
`min(valid requested cap, remaining measured Native budget)`. Omitted caps keep
the 5400-second default; invalid explicit caps are rejected. B3 restart validation
distinguishes newly marked requested-cap rows from legacy full-remaining rows,
without rewriting old ledgers. Actual Runtime and overshoot remain recorded;
unknown Runtime still quarantines. This is a code finding, not a measured B3
production timeout diagnosis.

## Stage results and development gates

| Environment | Before certified LB / UB / gap | After | Actual science status |
| --- | --- | --- | --- |
| B2 May01 M, owned Source36 saved frontier | 0.38895900867731903 / 0.5406756909532602 / 28.060570285386962% | Stored-dual segment maximum retains the same bracket; fresh RMP NOT_RUN | Saved certificate rechecked; final date PASS=false |
| B3 M1, actual fixed A1 | NOT_AVAILABLE | NOT_RUN | No qualified real representative case was available |
| B3 M2, actual fixed A2 | NOT_AVAILABLE | NOT_RUN | No qualified real A2/M2 representative case was available |

These are distinct stage results. A B2 numerical result supplies no B3 bound,
point, column, certificate or Runtime. Source36 saved proof verification is not
a certificate for the new research source. The saved frontier is a particular
checkpoint, not a claim about all Runtime before the earlier user stop.

Gate 1: **30 focused tests PASS**, zero failures/errors/skips, 7.2510267 seconds
wall time. Retained Gurobi Model construction, optimize and factory were denied
during the gate; attempted calls were empty. Exact ray/sign/repair, independent
checker admission, finite-envelope proof, stage/fixed-input isolation, actual
common-loop routing, B2 V19/V18 rebound/restoration, B3 source AST, duplicate
pricing, bounded evidence-based rescue, requested caps and legacy resume are
covered. One compatibility test exercises 31*4 Fake parameter entries; this
is not a 31-day solver campaign. No broad historical suite was run.

The owned saved Source36 May01 L1 was separately checked once using the original
rational checker and once using original finite-box witness verification.
Case, dual SHA and exact bound matched. Model/Native attempts were empty and
source/input bytes were unchanged. The full recheck span was 16.661916 seconds;
finite-box replay took 14.0670207 seconds and the rational checker 1.2453193 seconds.
All were Native-zero work. Exact LB:
`72763421188672844413290555716948908315532491447013/187072209578355573530071658587684226515959365500928`.

Gate 2: **NOT_RUN_PRODUCTION_RESOURCE_COLLISION_UNCONFIRMED**. The authorized
standalone driver was invoked once, and failed its real-worker preflight before
creating a Model or entering Native. Three actual B2 worker processes had started
after the earlier stop, under supervisor PID86136. Latest user instructions
prohibit stopping them. The host had 16 logical/10 physical CPUs, CPU35.4%, and
8.01GiB available of 31.711GiB RAM; each worker already used about 2.94-3.01GiB.
Resource independence was not established, so the driver was not weakened or
retried. The failed invocation and exact process evidence are retained.
Native Runtime=0, model preparations=0, Native calls=0 for this attempt; solver
wall time is NOT_RUN. Failed invocation tool wall was 1.2339774 seconds; it is
not a model-build or full solver wall measurement. Total research wall was not
tracked by a single clock and is UNKNOWN. These phase measurements are not
relabelled as total optimization time. No fresh Pi, convergence or improved LB is claimed.
Four LP pricing calls are not prepared in that limited driver and are NOT_RUN.
Actual B3 M1/M2 solver trials are NOT_RUN. No 5400-second optimization or full
31-day experiment is authorized by these gates.

## Preservation, unsuccessful candidates and next gate

The new worktree modifies common orchestration and requested-cap accounting;
the other 1005 of the campaign's 1007 original declared source files match
their existing hashes. Matrix builders, decomposition, exact physical/integer
checkers, original pricing and finite-box proof code retain their bytes. All
protected files and frozen Source35/36/37 are unchanged across Gate 1. Original
input matrices/types/bounds are unchanged by the candidate operations.
Threads=1, P2=0, Native5400 total, M gap3% and A gap0.5% remain. B2 and B3 retain
their own existing precision policies. Production deployment remains disabled.

Unsuccessful candidates: all positive fixed-grid blends weakened May01's LB;
the exact segment maximum over 49 distinct breakpoints and 23279 crossing
columns is alpha=0, gain=0. Pure equality repair cancelled 48547 helper residuals
and improved the raw computational bound from about -1.72385e13 to -9.73805e12,
still far below the owned L1. Its first external generation had an explicit
source start/end mismatch; it is diagnostic and not qualified certification.
The changed function AST was subsequently distinguished, not used to disguise
that failed source guard. Neither candidate warrants expanded Native trials.

Structural review: route-SOC, travel/location, mode-P/Q and grid-MESS coupling
already participate in unchanged original rows. A new inequality needs an exact
implication proof for every original integer plan, and exact hull claims need
complete-domain pricing closure. No such new proof was established here; no
cut or integer-domain change was added. A next experiment should first obtain
a numerically useful original-coordinate RMP dual, then compare complete
stage-specific pricing and exact independent gain. Expansion requires material
certified gain and actual independent B3 inputs; the final PASS criterion stays
the original Global gap, physical replay and Native deadline.

Artifact hashes and the final Draft PR link are recorded in `EVIDENCE.json` and
the PR description. No production promotion follows automatically from this PR.
