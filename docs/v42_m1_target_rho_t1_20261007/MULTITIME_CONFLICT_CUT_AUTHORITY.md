# Two-time fleet covers and route/SOC incompatibility

The original route graph has 53626 time-increasing arcs. The verifier checks
original FULL flow incidence, unit-source RHS, original movement-energy
coefficients, original connection rows and the exact preimages of flow rows
in C3A. It also checks every compact binary node-through-mass link, including
frozen deterministic aliases, and binary selectors for parallel arcs.
Nonnegative unit flow in this acyclic graph with binary node masses has one
integral path. Although most STAY aliases are typed C route_flow auxiliaries,
they are integral when the original C3A node-activity binaries are integral.
They must NOT be treated as independent free continuous choices in this proof.

Between connected STAY(s,t) and STAY(v,u), a path must run from(s,t+1) to(v,u).
The constructor uses forward time-DAG DP. The verifier uses backward DP.
Movement energies are exact binary64 rationals represented on a common integer
power-of-two denominator, with no floating shortest-path tolerance.
The complete original graph is a safe supergraph of each unit's live arcs;
no path in this supergraph proves no physical path in the unit model.
Minimum movement energy exceeding

    SOCupper[t+1]-SOClower[u] + sum_{q=t+1..u-1} alpha_ch[q]*Pmax

also proves incompatibility. Charging in EVERY intervening slot is allowed
in this bound, even in transit; this is conservative and never prunes a
possibly feasible schedule. Report the SOC-only conflict count honestly.
At two nearby times this envelope can be nonbinding; that does not justify
inventing a tighter incumbent-dependent SOC assumption.

For proven incompatible STAY states, insert y_s,t+y_v,u<=1.
Adversarial checks include every adjacent-slot same-site identity, impossible
adjacent different-site pair, and every original short MOVE edge as a positive
path witness. No route-domain restriction is made by candidate ranking.

For selected grid rows at t and u, individual capacity maxima give a safe
per-unit baseline M_m=max_s kappa_t[m,s]+max_v kappa_u[m,v]. Given connected
state s at t, define

    C_m,s=kappa_t[m,s]+max(0,max_{compatible v} kappa_u[m,v]).

The zero alternative includes all transit/other unconnected states at u.
Thus C<=M and the total two-time corrective contribution is bounded by
M_m-sum_s(M_m-C_m,s)*STAY[m,s,t]. Summing the two exact original grid rows gives
the globally valid normalized route-coupled cross-fleet support cut

    sum_m,s (M_m-C_m,s)/2*STAY[m,s,t] - rho
        <= (sum_m M_m-B_t-B_u)/2.

INTEGER_TWO_TIME_CROSS_MESS_ROUTE_SOC_COVER additionally conditions on complete
cross-fleet connected assignments at BOTH times, only when every within-unit
pair is route/SOC-compatible under the conservative envelope. Original
support bounds then imply delta=(B_t+B_u-sum assigned kappa)/2. For delta>T1,
the same global integer lifting gives

    delta*sum_{a in both-time assignment}STAY_a-rho<=delta*(|A|-1).

If any assignment state is absent, original rho>=0 proves validity; if all
are present, both original grid requirements prove it. This is a cross-fleet
two-time cover, not a four-slot MESS04 hull or a repeated one-slot mode cut.
The static independent verifier rebuilds every selected delta and capacity,
verifies native outward relaxation, and rejects mutation of exact algebra.
All cuts are static; callbacks do telemetry/vector storage only.
