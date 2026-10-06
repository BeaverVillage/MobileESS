# Exact current node-activity derivation

Only current immutable PR159/160 A1/source matrices, column attributes and graph
are used. Historical PR124 node-activity/parallel-selector design was inspected
with git show; none of its matrix, cache, start, scientific data or evidence was
copied. Current long arcs already account for travel transit and connection delay.

Let x_e in [0,1] be every current reachable stay or movement arc; preserve all
original conservation rows and the original all-allowed-sites terminal equation.
Append binary z_v = sum(outgoing x_e) for t<H, and z_v = sum(incoming x_e)
at H. Keep all original physical equations/PCS/mode/grid rows and stored coefficients.
If two distinct scientific arcs have the same tail and head, retain their original
binary selectors. Actual current graph has no parallel tail/head pairs.

Forward proof: an original binary unit route induces exactly one visited node
at each arrival/departure boundary; z is its indicator. All original values and
physical decisions are copied identically. Terminal z covers every allowed site.

Reverse proof: every positive flow in the acyclic temporal graph is reachable
from the unique unit source; otherwise chase a positive predecessor backwards,
contradicting acyclicity and zero source RHS. At the current visited node, choose
the earliest head of a positive outgoing arc. Its positive incoming mass equals
binary z (or original flow and z), hence is one. A positive predecessor from any
other earlier node would itself be a visited successor earlier than this chosen
head. Thus incoming flow comes only from the current node. A simple tail/head
pair then has x=1. For parallel pairs, retained binary selectors plus unit mass
force exactly one selected arc. All other outgoing arcs are zero. Induction from
source to allowed terminal yields exactly one original integer path. Distinct
parallel scientific trips remain distinguishable. No TU claim about the combined
SOC/PCS/grid matrix is made or needed.

Physical equivalence: each stay is the same flow x_e; all connected charging,
discharging, Q and stored PCS16 perspective inequalities are unchanged. Movement
arcs retain original route ID, source/destination/depart/arrive/connect and mobility
energy coefficient in the original departure-slot SOC balance. A long arc creates
no artificial P/Q opportunity in transit. Global mode, SOC bounds, both SOC endpoints,
grid injection/response/limit rows, rho P1 objective and numerical authority are copied.

Fractional projection: relax z and selectors. Any original nonnegative unit DAG
flow decomposes into allowed-terminal paths of total mass one. Each node's through
mass is in [0,1], so defining z imposes no additional restriction. Conversely,
compact flows satisfy every original continuous row. Thus C0 projects EXACTLY onto
the old original-arc LP, not merely the same integer set. PR160 certificates are
independently replayed on current original rows and their anchors before C1 execution.
Integer-only redundancy or unknown proofs do not authorize any deletion.

C2 records exact fixed/singleton variables, proportional/constant/bound-implied
rows and sparse unit aliases. No nonrepresentable coefficient/RHS is accepted.
SOC bounds use original stored charge/discharge coefficients, both endpoints,
unit stay mass and maximum possible departure travel cost; aggregate SOC bounds
are never incorrectly distributed as individual site perspective bounds. Q bounds
use the exact current PCS16 vertex hull. All accepted substitutions transport
eliminated bounds and integer types. Dense/non-unit substitutions are cost-audited
and retained. A network chain with intermediate connection, SOC timing, energy
or terminal decisions is not contracted. Long movement arcs are already the
exact transit contraction in the authority; no sampled path set is introduced.

The static loop iterates fixed variables, row simplification, singleton implications,
proportional duplicates/dominance, current reachability, exact unit/deterministic
aliases, safe bounds and grid auxiliary checks to a recorded fixed point. Current
forward/backward sets cover the original graph; no new route is deleted. The
independent verifier reconstructs all C1 rows under the stored inverse map and
proves every omitted row is zero, a retained proportional implication or follows
from retained variable bounds, without invoking production deletion decisions.
