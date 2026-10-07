# Cross-MESS grid support and integer covers

Only stored original binary64 values interpreted as exact rationals are used.
The independent verifier also recovers each selected native FULL grid row
through the frozen coordinate inverse and proves exact equality to the C3A row.
It substitutes original response/injection binding equalities, retaining all
frozen A1 constants. No coefficient sign is assumed from a branch name.

Each selected normalized original row has the form

    B - sum_m corrective_effect_m <= rho.

The stored rho coefficient must be strictly negative; normalization divides by
its exact positive opposite. For each connected STAY(m,s,t), use signed net
power P=Pdis-Pch and Q. Exact energy_balance and SOC bounds imply

    Pdis <= min(original power upper bound,(SOCupper_t-SOClower_t+1)/alpha_dis)
    Pch  <= min(original power upper bound,(SOCupper_t+1-SOClower_t)/alpha_ch).

Original PCS16 and Q bounds are retained. Zero power is feasible in this
conservative support region. The support kappa for the correctly signed grid
direction is certified by two nonnegative facet multipliers lambda such that
lambda*A=direction and lambda*b=kappa. The independent verifier reads facets
from original FULL rows, never accepts production-generated facet coefficients.
Connection rows and PCS facets imply zero corrective effect in transit.
One integral path per MESS implies at most one connected site per time.
Therefore the globally valid cross-fleet support cut is

    -sum_m,s kappa[m,s,r]*STAY[m,s,t] - rho <= -B.

Unlike a T1-only row, this preserves original schedules at rho>T1 too.
The required correction at T1 is the exact rational B-T1; see each grid proof.
These support rows can be implied by the original LP; no strengthening claim
is made merely because a row is inserted.

New INTEGER_CROSS_MESS_COVER rows use a specific original connected-state
assignment A. Its safely bounded corrective capacity C implies rho>=delta=B-C
if all assignment states are present. Only delta>T1 candidates are considered.
Since every original rho>=0 and every reconstructed STAY is integral in the
original integer domain, the globally valid lifted conflict cover is

    delta*sum_{a in A} STAY_a - rho <= delta*(|A|-1).

If all states are present the original grid row proves the inequality. If any
state is absent its left condition reduces to rho>=a nonpositive number.
Thus the row preserves every original integer-feasible schedule, rather than
silently imposing an objective cutoff. The proof verifier reconstructs delta
from original capacities and checks each state inverse independently.
Candidate state pools rank/limit cut enumeration only; the solve retains all
9322 original binaries, every route and every original continuous bound.

Native <= rows use downward coefficient rounding and upward RHS rounding.
All involved columns have original lower bound0. Consequently native rounding
relaxes the rational inequality globally, including all fractional states.
This is proved algebraically, not inferred from sampled trajectories.
Every capacity/direction, exact cut coefficient/RHS and native coefficient
mutation is rejected. Prior full integer reference points are also replayed.
No optimization call is used for support construction or verification.
