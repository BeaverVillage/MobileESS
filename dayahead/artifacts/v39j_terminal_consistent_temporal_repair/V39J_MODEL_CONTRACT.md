# V39J model contract and compact-formulation proof

Contract: BASELINE_RELATIVE_PER_JOB_TERMINAL_STATE_PRESERVATION.

This is an isolated candidate for May 24, 25, and 26, 2025. The evaluation is
inter-day independent and intra-day stateful. The live campaign, its HOLD,
and May17/May23 authorities are not edited. There is no new inter-day carry.

The accepted source HEAD is `2be60a1d47b4a4a422ccf5c9d6bce22ca4dc489b`.
V39H/refreeze contains uncommitted source at that HEAD; the byte-identical
copied overlay is separately pinned by the source manifest. HEAD alone is
not represented as a complete V39H source snapshot.

## Per-job contract

H = issue slot 120, with half-open reservations [start, start + duration).
Duration is the frozen positive safe reservation duration, GPU request is
immutable, execution is contiguous and indivisible, and each reservation
has one site state. Site state may be UNASSIGNED, exactly as in the original
authority for PENDING reservations wholly after H.

For each job, its entire reservation profile at and after H must equal its
baseline profile. No sum across jobs can substitute for this equality.

Let s0, d, a0 denote its baseline start, fixed duration, and site state.
For an interval, its nonempty post-H profile has support
[max(H,s0),s0+d) at site state a0.

* If s0+d <= H, the baseline support is empty. Candidate equality holds iff
  s+d <= H. Its site is irrelevant to the empty tail.
* If s0+d > H, equality of the nonempty supports gives s+d = s0+d.
  Since d is fixed, s=s0. Equality at any occupied post-H slot also forces
  a=a0. Conversely s=s0 and a=a0 give identical profiles at every post-H
  slot. This includes s0>=H and jobs crossing H.

Thus the compact rule is necessary and sufficient, not just sufficient.
GPU requests are checked independently, so equality also holds in GPU units.
The unit tests exhaustively compare these compact conditions with explicit
per-slot/per-site occupancy, including both assigned and unassigned states,
and separately reject changed durations, GPU requests, and site mutation.

The original earliest start and RW-completion latest start are retained.
Eligible in-day latest starts become min(original_latest, H-d); baseline
tails receive the singleton original start. This is a terminal condition,
not an added customer SLA, arbitrary delay ceiling, or same-day completion
requirement for all jobs.

## Baseline site authority

RUNNING sites are the frozen RW-anchored initial sites used by migration-OFF
V39H. For PENDING reservations crossing H, terminal sites are the preserved
pre-refreeze B1 original-RSP witness's destination sites; PENDING placement
is not migration. PENDING reservations starting at/after H have no AIDC
assignment in that authority. The user explicitly selected preservation of
their existing unassigned state. There are 198 / 109 / 83 such reservations
on the three dates. No AIDC or future physical state is fabricated for them.
V39H's arbitrary smallest-compatible-site computational label outside its
site domain is eliminated. V39J uses UNASSIGNED in both allocation keys and
exported terminal state. It creates no physical AIDC for these jobs.

Cohorts include terminal category, baseline terminal site, original state,
fixed site, safe duration in seconds and slots, GPU request, start/window,
and eligibility. Completion is exactly start plus duration. Every
member therefore has the same per-job terminal domain. Integral counts
expand to a bijection of UIDs and whole intervals; no terminal obligation
can be exchanged for another job's obligation.

## Unchanged science and verification domain

The original V39H eligibility is retained as `v39h_eligible`. Only D-1-visible
PENDING standby jobs satisfying that condition and IN_DAY_COMPLETE remain
temporally eligible. As required by the addendum, CROSS_BOUNDARY and
POST_H_ONLY are excluded from temporal repair. Safe seconds, reservation
slots, GPUs, non-preemption, gang indivisibility, capacities, Rack semantics,
voltage .95/1.05, line/transformer limits, C1 integer tables and inner polygon,
RW completion noninferiority, and migration OFF remain frozen. PENDING site
choice stays free except where terminal preservation requires a fixed site.

The unmodified V39H model builder and grid evaluator are reused from the
SHA-pinned source overlay with only a terminal-cohort adapter and runtime
thread configuration. Full aggregate capacity and intervention objective
retain their original reservation horizon. Site/grid constraints remain
exactly [24,120). No physical certification beyond that interval is made.
Actual, Fresh, future observations, campaign execution and migration solves
are not inputs or execution paths of the V39J runner.

## Exact feasibility sequence and presolve certificates

Stage A tests primary = 108 / 29568 / 13086. A feasible witness plus the old
global lower bound certifies that same primary optimum. Only if Stage A is
infeasible does Stage B test the terminal-safe feasible set without that
equality. Only if B is feasible is a new primary optimization necessary.
Secondary, tertiary and migration optimizations are never requested.

Before a numerical solve, exact integer presolve retains all jobs whose
time and site are fixed, omitting all other nonnegative load. At a site and
slot, a mandatory GPU sum exceeding the frozen capacity is a checkable
infeasibility certificate for the relaxed subsystem and the full model.
The certificate applies first to A and then to B because it does not use
the primary equality. It is a feasibility proof, not a fabricated Gurobi
status or a voltage monotonicity assertion. No solver capacity is needed
when this exact contradiction already proves the requested answer.

A required source-level objective identity audit precedes this proof. The
actual objective sums per-job symmetric interval deviation; it is not the
absolute value of net aggregate load deviation. Every job contributes
2*g*min(delay,d); there is no site term or omitted constant. GPU-slots are
integer 15-minute slot units. The identity audit reconstructs all old
certified values using explicit per-job occupancy arrays over complete
reservation intervals.

A second independent proof sums each job's maximum allowed original
intervention 2*g*min(delay,d). If this upper bound is below the certified
old optimum, V39J is infeasible: every member of the restricted feasible set
would otherwise need an objective both below the upper bound and above the
old V39H lower bound. This is an infeasibility certificate; it is not an
aggregate replacement for the per-job terminal invariant.

Eliminating V39H's unused post-day numerical site label does not weaken the
lower-bound argument. Every V39J reservation maps to a V39H reservation by
reinstating its former smallest-compatible-site dummy label solely in that
older model's representation. It has no post-day site constraint consumer
and no objective cost; timing, total occupancy and all in-day physics stay
identical. Thus the feasible-set subset argument holds under this exact
projection while V39J itself preserves UNASSIGNED without inventing a site.

For May25/May26, a valid U<L certificate bypasses both Gurobi model assembly
and numerical solves. For May24, U>=L is inconclusive: the complete model
with primary=108 is assembled, and an exact mandatory-capacity presolver
tests its feasibility. The same row contradiction is checked after removing
that equality. A checkable integer contradiction resolves both feasibility
problems without numerical search; no Gurobi solver status is fabricated.

When exact presolve proves infeasibility, all temporal decisions are
discarded and the original RSP plus the existing 2 / 8 / 15 migration
witnesses is verified read-only. No partially repaired schedule is used.

Runtime budget is at most 16 solver threads, with production settings
unchanged. A numerical V39J solve may use one model/one thread only after
a production slot is stably free (a held day or sufficiently few remaining
unheld days). Four active admitted production workers reserve all 16 threads.
Model assembly and exact integer arithmetic are not Gurobi optimize calls.
If presolve certifies all dates, actual V39J solver threads and parallel day
solves are both zero.
