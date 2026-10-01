# Conditional connection-aware mode hull

For each unit and control time, let `y = sum_s x_stay[m,s,t]` and
`z = charge_mode[m,t]`. Keep every original F3 variable, bound and row.
The only permitted extra inequalities are:

* H1: `z <= y`.
* H2: `sum_s Pch[m,s,t] <= Pmax*z`.
* H3: `sum_s Pdis[m,s,t] <= Pmax*(y-z)`.

Build S1 only when the frozen baseline optimum violates at least one row
by more than the preregistered tolerance. A violated point authorizes the
comparison but does not prove that the optimal objective will increase:
another baseline-optimal point may satisfy all rows.

Exactness concerns the physical projection onto routes, P, Q and original
SOC. In transit, the original auxiliary mode bit may be 1 even with all
power zero. H1 fixes that unused auxiliary freedom to 0. This does not
remove a physical trajectory. It can remove an original **auxiliary bit
assignment**, so equality of the complete original integer assignments
including an unused mode bit is not claimed.

The authoritative authorization and execution status are in
`MODE_HULL_ROOT_SUMMARY.json` and `STRENGTHENING_CANDIDATES.json`.
