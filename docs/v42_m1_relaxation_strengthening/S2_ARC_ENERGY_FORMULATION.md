# Conditional arc-energy flow

For every surviving unit/arc pair introduce continuous departure-energy
mass G. A fractional arc carries proportional energy bounds:

`Emin*x <= G <= Emax*x`.

Travel arrival energy is `A = G - travel_energy*x`; a stay arrival is
`A = G + dt*(eta_charge*Pch - Pdis/eta_discharge)`. Require
`Emin*x <= A <= Emax*x`. At every intermediate network node,
outgoing G equals incoming A. The source outgoing G equals battery.initial;
the collective terminal incoming A equals battery.terminal.

The baseline diagnostic fixes x, Pch and Pdis to their saved LP optimum
without changing any original variable. Only a certified infeasible
diagnostic authorizes S2. A feasible extension means precisely these
equations cannot eliminate the saved optimum, so S2 must be skipped.
An inconclusive solve never authorizes strengthening.

If authorized, retain **all original SOC variables and recurrences**.
No SOC recurrence is replaced. Arc energy is an additional extension.
Travel ends at the native connection-ready node, including the inherited
unconnected arrival-to-connection interval.
