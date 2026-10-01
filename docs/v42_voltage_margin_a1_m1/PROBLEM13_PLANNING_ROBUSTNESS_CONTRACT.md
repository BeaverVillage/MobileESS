Planning uses 0.955–1.045 pu (squared 0.912025–1.092025) in A1/M1/A2/M2. This is an engineering robustness hypothesis, not a proof that linear Planning implies AC feasibility.

MESS route, movement, charging, discharging, Q and SOC remain joint native MILP decisions. Actual local P, Q and P/Q repair are removed. The frozen route/movement/P/Q is replayed as-is. Fresh OpenDSS must independently pass convergence, 0.95–1.05 physical voltage, line current, transformer current and kVA. A failure remains FAIL; no rescue, emergency full reoptimization or margin fallback.

Problem 13 is not finally validated here: A2/M2, frozen final Planning, Actual replay and Fresh AC remain required future work. This task stops after one M1. Existing unknown-arrival site-only authority is unchanged; no fabricated future individual jobs or new temporal/migration permissions.
