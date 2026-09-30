# Exact compact AIDC event/state MILP

This reformulates the PR98 complete trajectory feasible set. The 900-second control boundary convention and all physical authorities remain unchanged. It is one joint MILP across jobs, sites and all 96 electrical slots, with inherited pre-horizon and post-horizon service slots. No per-job optimization replaces the coupled problem.

## Sets and parameters

J is the admitted explicit positive-service population. K contains authorized sites. T is the finite service boundary axis; the electrical/control horizon is a subset. S_j is the unchanged finite ServiceBoundary start set. C_j contains exact checkpoints computed with the inherited 1800-second physical phase and ceiling adapter, including causal RUNNING elapsed seconds. D_j contains authorized destination sites. W_j is the sparse set of (source,destination,transfer-start) events with a valid PR98 deterministic maximal-rate transfer template. No W_j index contains a checkpoint or original start.

G_j is the indivisible GPU gang and d_j the frozen Q50 service-slot count (remaining nominal service for RUNNING). C_k is the unchanged site capacity. fixed_GPU, fixed_WAN and fixed_active contain only immutable usage. L_j is the inherited latest completion, including authorized carryout. A transfer template supplies transfer_end E, restart_end R, per-link bytes B and active-transfer indicators A. Requested TS service boundaries are consumed without recalculation. A physical checkpoint can coincide with the current RUNNING boundary, giving an authorized empty source segment.

## Events and states

Binary y[j,k,s] chooses start and source. Binary q[j,k,c] exits source computation at checkpoint c. Binary w[j,k,d,tau] initiates transfer. Binary f0[j,k,t] finishes normally, and binary f1[j,d,t] finishes after migration. Continuous r0[j,k,t], h[j,k,t], r1[j,k,t] in [0,1] respectively mean source compute, checkpoint-ready waiting, and destination compute during slot t.

All sets are sparse. Static site/rack/residency rights constrain y and w. q contains only checkpoints having a compatible authorized start with an immutable-capacity-feasible prefix. WAN templates are reused without changing zero-rate waiting, payload, rates, paths or restart. A necessary remaining-work bound screens w using the largest completed prefix available by tau; this does not join checkpoint and transfer indices. Full service equations decide compatibility of the actually selected events. Completion events stop at L_j. States cover reachable bounding spans; unused slots in a span are forced to zero by the equations. True nonmigrating singleton schedules are substituted as constants after legacy validation.

## Constraints

For each nonconstant job:

    sum y = 1
    sum q <= 1
    sum f0 + sum q = 1
    sum w = sum q = sum f1

Let S_checkpoint[j,k,c] contain exactly the starts compatible with checkpoint c. Then:

    q[j,k,c] <= sum_{s in S_checkpoint[j,k,c]} y[j,k,s]

Using zero states outside each finite span and including its terminal boundary:

    r0[k,t] - r0[k,t-1] = y[k,t] - q[k,t] - f0[k,t]
    h[k,t]  - h[k,t-1]  = q[k,t] - sum_d w[k,d,t]
    r1[d,t] - r1[d,t-1] = sum_{k,tau:R(k,d,tau)=t} w[k,d,tau] - f1[d,t]

Missing events equal zero. Nonnegativity permits tau=c, forbids departure before checkpoint, and requires finish at the occupied site. Terminal zero prevents lost waiting or unfinished computation. Every job satisfies:

    sum r0 + sum r1 = d_j
    sum r1 >= sum q

The second inequality preserves useful post-migration service. Transfer, waiting and restart consume no compute. Resource coupling is:

    fixed_GPU[k,t] + sum_j G_j (r0[j,k,t]+r1[j,k,t]) <= C_k
    fixed_WAN[l,t] + sum_w B[w,l,t] w <= WAN_capacity[l,t]
    fixed_active[t] + sum_w A[w,t] w <= max_active_transfers

Tail GPU capacity is the same inherited authority as the legacy validator; D24 is not an invented completion deadline. Gang/rack compatibility remains non-additive whole-gang authority.

## Runtime, CC4 and grid coupling

For either completion event at site k and time t, compute the original adjusted end:

    adjusted_end = risk_nominal_completion_issue_slot + t - reference_end
    risk[k,u] += gamma90 * risk_exposure(G_j, adjusted_end, k, frozen_kernel)[k,u] * f

Fixed and Q50-expired RUNNING contributions remain constants. gamma90=2.423057443558147. The unchanged bind_headroom function receives known GPU from r0/r1 and completion-event risk. PR97 CC4 nominal/reserve timing, Q10/Q90 envelope, carryout, work conservation, depletion and L1 reference deviation are reused. The same C1 power coefficients, affine grid rows and rho receive known GPU plus anonymous nominal load. MESS P/Q are fixed zero for canonical A1 or supplied accepted M1 anchors for A2; the job formulation is identical.

## Lexicographic objectives

Minimize, in order: P1 rho, P2 reserve shortfall, P3 CC4 reference deviation, sum q, sum (s-reference_start)y, sum 1[k!=reference_site]y, then a deterministic non-scientific physical event-rank sum. Ranks are assigned by sorted job UID, event family, and event tuple. Tied sums use the frozen single-thread deterministic solver. This last tie does not reproduce the old option index. All six scientific levels must agree within the inherited locking tolerances (rho 1e-7, later 1e-8). No weighted sum mixes priorities. No complete option indices are built for ties.

## Integrality and exactness

Each state is a cumulative sum of integer event impulses with zero initial value, hence integer conditional on binary events; [0,1] makes it 0 or 1. Exactly one start and exactly one source exit force one contiguous source segment. Source-specific h and nonnegativity enforce checkpoint <= transfer-start and the same source. Exactly one transfer entry and post finish force one contiguous destination segment at that destination. Full service fixes its end to R+d_j-(c-s). No second start, finish, migration, free switch, gap, gang split or fractional service is possible. f0 plus service similarly forces t=s+d_j for normal completion. Compatible-start constraints reproduce checkpoint phase and useful-prefix authority.

An old option maps uniquely to those event impulses and interval states. Conversely an integral compact path reconstructs a single old Option with the same physical checkpoint, deterministic WAN template, restart, intervals and completion. The unchanged validator and aggregate capacity checks are applied after reconstruction. Bounded pool enumeration tests the reverse direction, including absence of compact-only paths; fixed-event feasibility tests cover the forward direction. Independent old/compact objective solves verify all scientific levels. These arguments hold before seeing the May build result.

## Execution gates

Equivalence must pass before the full May build-only attempt. That attempt has an external 600-second process-tree cap and never calls optimize. A completed build permits the separate bounded A1 canary with MIPGap=0.001, Threads=1, Seed=20260929. Raw incumbents are distinct from physically validated and quality-accepted plans. A failed build stops production work and permits only documentation of one next exact decomposition candidate. M1, compact A2, M2, Fresh AC and the final response kernel remain gated in that order.
