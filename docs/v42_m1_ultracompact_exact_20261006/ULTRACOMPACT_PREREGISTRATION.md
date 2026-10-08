# PR161 C2 exact exhaustive audit preregistration

Base: `4f45f04d685d5d5e689463f953695fe40d52cf98`, Draft PR161.
Only this selected C2 and its immutable physical authorities may be used.
N=4, H=96, P1, MIPGap=.005, all original numerical tolerances unchanged.

Order: freeze/hash C2; read-only Gurobi 13.0.2 Model.presolve with no optimize;
universal exact row/column scans; exact rational PCS clipping/face minimization;
correlated reachable-state support; all network/equality/auxiliary families;
fixed-point implied bounds; independent proof replay; fixtures and start transport;
all candidate native presolves; materiality/resource gates; bounded benchmarks.

Only full-LP redundant rows are deletable. Unknown and integer-only results stay.
Rows are tested in the requested A-K order. Columns are tested in A-J order.
Exact stored binary64 values are rationals; native tiny-coefficient behavior is
recorded, never used to silently alter scientific coefficients. Any substitution
whose exact result cannot be represented under the current numerical authority
is rejected. Fill-in/density/coefficient costs must be recorded before adoption.

PCS local analytic structures are canonicalized by the stored 16 planes and
homogeneous connected P bounds. Rational vertex enumeration and Farkas certificates
replace per-row LPs. At most 16 small LP checks per distinct preregistered PCS
structure and 16 per normalized security polygon are allowed only if needed.
No large-scale LP redundancy solves. No optimizer-generated bound is a proof.
Correlated support takes max over reachable per-state PCS regions for each unit;
aggregate SOC bounds are never incorrectly allocated to individual perspectives.
Cross-family and native SOS/GUB alternatives are design audits unless exact
equivalence and sparsity improvement are independently certified.

C3A: new full-LP deletions and implied fixes/bounds. C3B: beneficial exact sparse
substitution or contraction. C3C: any beneficial exactly equivalent lifted network
or polygon representation. Equal candidates are permitted and run only once.

Materiality versus frozen C2: >=10% rows/nnz/continuous or >=15% presolved rows/nnz.
If false, stop heavy benchmarks. If exactness or resource gate fails, stop heavy.
Sequential root microbenchmarks: frozen C2 and best distinct C3, <=240 seconds
each (native TimeLimit 230 seconds, independent wall guard at 235 seconds).
Root run uses the current full-MILP root settings with NodeLimit=1, identical
starts and read-only callbacks; root Work/time comes from the native root log,
with its printed precision recorded, not overall Work mislabeled as root Work.
Sequential development MILP: frozen C2 and best C3, <=300 seconds each
(native TimeLimit 285 seconds; independent wall guard at 293 seconds).
Only one benchmark sequence; no parameter sweeps/tournament/3600-second run.
Root selection >=15% time or Work, or meaningful earlier B&B, valid LB/gap or
material first-new-valid-incumbent improvement. Numerical bound noise <=1e-6
is not treated as a scientific speedup. Size alone cannot select C3.
Resource conflicts defer the benchmark; no unrelated processes are killed.

Mandatory existing 1536 assignments, route exhaustion, PR160 exact certificate
replay, PR161 inverse algebra/bounds proof, fractional LP proofs, new adversarial
cases, and original physical-start preservation must pass before heavy solves.
Verifier reconstructs proofs from frozen C2 and does not call production deletion
decisions. All artifacts stay in the new namespace; parent evidence is immutable.
