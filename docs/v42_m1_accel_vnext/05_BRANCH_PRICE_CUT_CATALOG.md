# Root valid inequality catalog and pricing compatibility

Implemented family, every MESS m and slot t:
sum_s Pch[m,s,t] <= p_limit * charge_mode[m,t];
sum_s Pdis[m,s,t] <= p_limit * (1-charge_mode[m,t]).
Original unit DAG flow selects at most one stay location at a slot. All exchange
at other sites is zero, and original mode/connection rows bound active power.
Thus these inequalities hold for ALL original integer solutions, including all
legal movement/travel and terminal SOC histories. No site fleet-capacity limit
is invented. Toy original integer optimum is unchanged; the original arc LP
is strengthened from -1 to -0.5. Exact full-enumeration D-W already implies them.

Master form aggregates per-column f_ch=C-p*d and f_dis=D+p*d-p, each <=0.
For each slot add sum_m,p lambda[m,p]*f[m,p]<=0. These rows are implied by every
physical column and lambda>=0, including unseen full-domain columns. Therefore
the full D-W feasible set and optimum are IDENTICAL, and no stronger root bound
is promised. Benchmark tests numerical/presolve work only. Local route flow,
movement consistency, SOC recurrence and PCS linear inequalities likewise hold
on conv(X_m^I); their master reintroduction cannot strengthen the full D-W root.
Fleet occupancy/clique restrictions without an original capacity row are invalid
and are rejected. Genuine cross-block cover cuts would require an independently
proved original joint resource constraint; none is assumed or implemented here.

Pricing compatibility: cut reduced cost is c-pi*B*x-alpha-sigma*f(x), sigma<=0.
Since f(x)<=0 for ALL original local integers, original rc equals cut rc plus
sigma*f(x)>=cut rc. Cut RHS is zero. Eliminating these cut duals leaves the SAME
global-dual objective and makes every full-column dual constraint weaker. Thus
original coupling pi/convexity alpha remain a valid unstabilized original-RMP
dual, with the unchanged full-domain pricing/corrected-bound implementation.
No cost rounding, smoothed certificate, new global floor or incumbent LB is needed.
Certificate numerical audits remain 1e-8/1e-6; no cut objective is used as a LB.

Bounded root benchmark: original versus cut RMP from identical 1,604 columns;
original-true-dual pricing root only (one explored root, no child nodes), Threads=1.
Root LB/old corrected LB are recorded as inherited, and new corrected LB is NULL
because this is not a four-way terminal Certification run. Any selection requires
>=20% total root-work reduction and objective/audit equivalence; otherwise reject.
