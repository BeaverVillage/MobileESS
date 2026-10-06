# RMP dual sign forensic

## Proven findings and unresolved cause

The PR155 executed master constructor transports the original CSR coefficients,
RHS, senses, names and bounds verbatim; no row negation/normalization. Convexity
is sum(lambda)=1. For minimization native Pi has <= nonpositive, >= nonnegative,
equality unrestricted signs. Pricing uses c-B.T@Pi-alpha with multiplier+1.
The saved RMP42 obeys this convention for every original row family and all four
convexity equalities. Row/dual-axis SHA matches the checkpoint.

Source: [Gurobi Pi/BarPi reference](https://docs.gurobi.com/projects/optimizer/en/current/reference/attributes/constraintlinear.html).
Method2/Crossover1 returns terminal X/Pi/RC after crossover. BarPi describes the
barrier point and must not be substituted for terminal Pi. The code used Pi;
there is no evidence that RMP43 mixed representations. Barrier numeric->optimal
in its log is a warning/observation, not a proof of the exact failed dual entry.

RMP43 point_file/dual_SHA/objective are null. The executed source asserts the
Pi signs BEFORE np.savez of point/pi/alpha/lambda. Thus the rejected raw vector
and row-level failure were lost. This evidence-capture defect is proven. The
FIRST failed family, value, and exact sign root cause remain UNRESOLVED. Code
conversion, row normalization, stale/serialized dual and numerical mechanisms
cannot be selected without inventing evidence. No full-scale replay was run.

## Independent existing-state audit

All1841 retained-column reduced costs are computed two independent ways:
stored master coupling c-a.T@Pi-alpha versus original local-domain objective
(c-B.T@Pi).T@x-alpha. Max difference5.204170427930421e-18.
This proves transport identity, not equality to a saved native RC vector.
RMP42 used1825 lambdas;16 subsequent columns were not in that optimal RMP.
Native RC vectors/bound duals were not saved; only max-error scalar2.997428694140325e-14
is preserved. CSV explicitly marks native RC comparison UNRESOLVED, never fakes
per-column solver RC. Primal objective independently reconstructs exactly the
saved .5729695797088222. Free-coordinate manual stationarity residual up to
1.9804307933163345e-15 precludes substituting unbounded support from an incomplete
b.T@Pi sum. No residual is rounded away to claim exact strong duality.

Existing corrected-bound rational arithmetic (RMP36/global proof/alpha/same-dual
pricing lower bounds with unchanged1e-8 safety) reconstructs .5501655188774129.
Aggregated approved root floor .5687115725336208 is preserved. This formula
check is not materiality recomputation or authority for RMP43.

## Implemented repair and guard

Before any gate, durable snapshot saves exact CSR/row and column axes, native
X/Pi/RC and optional BarX/BarPi/bases from the same terminal model. Immutable
identity hashes reject axis/point/dual mutations. Independent audit includes
all reduced costs and lower/upper bound dual terms in strong duality; nonzero
support at an infinite bound is rejected. Actual wrong-sign Pi, even1e-15,
remains rejected with no projection or tolerance change. Pricing is reached
only after this guard AND the existing original-row/manual-RC audits; existing
full-domain corrected-bound certificate remains unchanged.

Small sign/scaling/bound/representation/rejection fixtures pass. This repairs
evidence preservation and strengthens future acceptance. It DOES NOT establish
EXACT_DUAL_AUTHORITY_PASS for the missing historical rejected point.

## Mandatory stop

STOP_DUAL_AUTHORITY_UNRESOLVED / EXACT_DUAL_AUTHORITY_PASS=false.
No restricted integer master, new root solve/pricing, early-B&P,600s comparison,
7200s development, P2, campaign or materiality solve. No full-scale solver
parameters, scientific inputs, physical constraints or thresholds were changed.
