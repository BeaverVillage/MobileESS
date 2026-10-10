# Full96 trajectory hull research

For stage-local original C3A arrays, partition variables into four vehicle blocks
and nonunit grid variables w. Reuse `v42_m1_hybrid.blocks` without changing a
coefficient, bound, integer type, original objective or fixed AIDC decision.
Let X_u be each entire original 96-slot mixed-integer vehicle domain, including
the mobility DAG, connection delays, travel energy, SOC, charge mode, PCS16 P/Q,
and initial/terminal rows. The master keeps **every** mixed and nonunit original
row, and replaces x_u by a convex combination of trajectories in X_u.

## Mathematical guarantees

1. Every original integer plan gives one feasible trajectory in each X_u. Choose
   one column of weight one per unit and its unchanged grid w. Thus all integer
   plans are preserved. Projection of a master combination retains original
   coupling and objective exactly in the mathematical formulation.
2. X_u lies in its original local LP domain; convexity preserves every linear
   local constraint. Therefore the complete DW relaxation projects into the
   original C3A LP. Its optimum cannot be lower. Strict strengthening is possible
   but must be measured on May01, not inferred from the fixture.
3. A finite restricted master excludes ungenerated trajectories. Its objective
   has **no Global LB authority**. Native column products are rounded and used
   only for selecting search prices. Even an optimal RMP is not a certificate.
4. For signed original mixed-row multipliers y, define exact
   q_u=c_u-B_u^T y and q_0=c_0-B_0^T y. Weak duality gives
   LB=ObjCon+b^T y+beta_0+sum_u beta_u whenever beta_u <= min_{X_u}q_u^T x_u.
   Nonunit beta_0 uses the unchanged original exact checker and a separately
   replayed equality-implied finite envelope. No native model bounds are changed.
5. Integer pricing is searched with the original full96 MILP, never a window or
   SOC discretization. Its incumbent generates numerical search columns; its
   objective/BestBound is not promoted. A separate binary-partition tree covers
   **all** original integer trajectories, including ones not seen by the MILP.
   Each leaf is bounded by exact signed original-row duality with the leaf's
   binary bounds. Splits exhaust z=0/1. Parent certificates remain valid in both
   children immediately, so interruption never loses an unsearched region.
   The minimum of leaf bounds is a conservative integer-pricing bound. Exact
   Farkas certificates may discard a leaf only when 0 >= positive bound is
   independently verified. Native INFEASIBLE alone never discards a region.
6. Global verification independently rebuilds every exact price from original
   mixed rows, checks the entire cover and nonunit bound, and sums them once.
   Rounded native price errors are outward-corrected. All signs are checked;
   invalid raw Pi is rejected, never clipped or repaired.

Full integer pricing optimum and full DW closure remain NOT_PROVEN unless
independently established. An incomplete cover can still certify a stronger
bound. The published bound is max(existing exact L1, independently checked
candidate), so the previously certified lower bound cannot be weakened.

## Why this differs from previous failures

- PR167/169 use short-window local hulls; X_u here is a full-horizon domain with
  original boundary conditions and all travel/SOC/mode/PCS links.
- PR182 enumerates huge extended formulations. Here columns are generated
  dynamically; no full trajectory catalog is enumerated or preallocated.
- PR183 delegates physics to a large recourse problem after an integer assignment.
  Here complete vehicle physics is retained **inside pricing**.
- PR185/187 add 651 local Route–SOC rows; this formulation adds none of them.
- PR188 branches the entire grid LP on isolated binaries. Here disjunctions are
  proof regions inside each full96 integer pricing problem, using multidimensional
  coupling prices; the grid is not rebuilt in every branch.
- PR190 uses one scalar physical support direction. DW prices all mixed rows.
- PR202 retains LP pricing and finite-box dual search. Here integer disjunction
  bounds are included explicitly; missing columns are covered by an independently
  checked partition. L1 is an initial certificate, not a target for dual blending.

## Complexity and tractability

For K generated columns per unit, native RMP size is n_nonunit+4K columns and
m_nonunit+m_coupling+4 rows. All original grid coefficients remain. Each pricing
model has only one vehicle's original rows/columns. Store sparse active leaf
duals and a bounded frontier; never enumerate all paths or all mode words.
Exact cover work is proportional to active dual nonzeros plus local columns
per visited proof leaf. Worst-case exact integer pricing and CG are exponential;
600 seconds does **not** guarantee hull closure or 3% gap. A bounded cover and
NOT_PROVEN state are first-class outcomes.

Stage adapter requires independent day/stage, case, matrix, domain, fixed-input
and complete fixed-decision identities. B3 M1 must use its A1, M2 its A2. Missing
B3 saved identity/arrays means NOT_RUN; B2 evidence is never reassigned.

Production code, campaign, queue, frozen artifacts, Supervisor and Windows tasks
are untouched. The production 3%/5400-second contract is not replaced by the
research 600-second ceiling. No automatic production promotion is implemented.
