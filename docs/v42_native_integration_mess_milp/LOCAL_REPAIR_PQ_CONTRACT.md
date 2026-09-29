# Bounded continuous P/Q proposal

New LP adapter consumes an explicitly authorized frozen suffix of at most 16 control slots and a shared at-most-10-second in-process deadline. The production caller must place it under external execution supervision as well; this function alone cannot guarantee wall time across a stalled solver/API call. No production Actual wrapper is asserted ready.

Location/connection, charge direction, route energy, job schedules and migrations are fixed. Only P/Q and the resulting energy trajectory change inside supplied delta-P/delta-Q reserves. Transit has P=Q=0. Inner16 PCS, physical power bounds, exact efficiency/quarter-hour energy balance, SOC limits, observed initial energy and frozen terminal energy remain hard. Future compensating P is permitted only within the supplied frozen reserve suffix, never by reading future Actual state.

Optimize electrical rho first, lock it, then minimize absolute P change and finally Q change: Q-first intervention preference at equal electrical quality, no arbitrary P/Q weight. A P change recomputes every SOC boundary through terminal equality. M3 paper policy forbids this repair. No new route or discrete MILP in Actual; the adapter checks integer variable count=0.

Output is PROPOSAL_REQUIRES_FRESH_AC, never an automatically executed dispatch. Native current-state adapter, margin/trigger/reserve authorities and Fresh validation remain required. Unit tests demonstrate P/Q changes with compensating SOC on synthetic data only.
