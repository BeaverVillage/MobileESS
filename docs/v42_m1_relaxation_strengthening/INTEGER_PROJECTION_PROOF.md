# Integer physical projection proof

This proof is conditional on a candidate being authorized and implemented
with the equations documented in S1/S2. A numerical verification PASS is
reported separately; the proof does not imply that unexecuted tests passed.

The native forward time network is acyclic. Unit flow, binary arcs and the
single source/collective terminal equalities select one complete path.
At any time, that path uses at most one stay arc. Thus y is either 0
(in transit) or 1 (staying at one site). All other sites have zero Pch,
Pdis and Q by the retained connection constraints.

For S1, when y=1 the native site-wise mode rows already imply H2 and H3
because only one site can carry active power. H1 is automatic. When y=0,
all active power is zero; choose the unused mode bit z=0. All three rows
hold and the route/P/Q/SOC trajectory is unchanged. Consequently every
original physical integer trajectory has an S1 extension. The reverse
inclusion holds because all original rows remain. The physical projections
are identical; unused z assignments in transit need not be identical.

For S2, set G on each selected arc to original SOC at its departure and
set G=0 on each unselected arc. Departure bounds follow from original SOC
bounds. On a selected stay arc the original recurrence gives precisely
the stated arrival update. On an unselected stay arc its Pch/Pdis are zero.
On a selected travel arc, native SOC subtracts travel energy immediately
after departure. The unit cannot charge or discharge while traveling, so
that SOC remains constant until the connection-ready arrival node.
Thus the arc arrival expression equals original SOC at that node, and
arrival bounds follow from native SOC bounds, including all transit slots.
At each visited intermediate node, the unique outgoing departure SOC is
the unique incoming arrival SOC. Unvisited nodes carry zero mass and power.
Initial and collective terminal energy equal the retained original endpoint
SOC equalities. This constructs an S2 extension for every original integer
physical trajectory. Conversely, retention of all original F3 rows gives
the reverse inclusion after G is projected away.

S3 combines both independent extensions. G does not change z, and transit
canonicalization of z does not change power or energy, so their extensions
are compatible. No incumbent-derived restriction is used in this proof.

The LP projection is intentionally allowed to shrink. Equality of physical
integer projections does not assert LP equality, optimality of the inherited
incumbent, or a MIP certificate from an LP optimum.

S3 numerical recovery uses exactly the same LP polyhedron. Since every
surviving x has its original bounds 0 <= x <= 1 and Emin >= 0, the retained
row G >= Emin*x implies G >= 0. The retained row G <= Emax*x implies
G <= Emax. Explicit variable bounds [0,Emax] therefore remove no feasible
extended LP point or integer point. No row, coefficient, physical limit or
objective changes; no extra strengthening family is introduced. The
interrupted unbounded-variable representation and its source/logs are
preserved in S3_NUMERICAL_RECOVERY.json and S3_INITIAL_SOURCE.zip. The
20-case exhaustive comparisons were rerun with the recovered S3 representation.
