# Proposed common control contract — blocked, not activated

For April and May, B0/B1/B2/B3 must share the same topology, equipment,
control settings and slot-state semantics. Tap/cap states are exogenous
conventional physical controls, not optimizer decisions, intervention or P/Q
repair. AIDC/workload/Runtime/CC4 remain present in every arm. AIDC flexibility
is allowed only in B1/B3; MESS only in B2/B3. B0 retains its frozen PR125
reference, FCFS/capacity admission, C1 conversion and zero MESS.

The audited existing regulator law is source static/snapshot convergence with
maxcontroliter=100, sequential state within the day and a source-initial
compile per day. Future Actual must evolve its own state from its own inputs
using that same law. It must not consume a Planning tap/cap trajectory.
Planning finite-difference perturbations may hold the already-converged
anchor state locally; Planning must not optimize equipment states.

No target, deadband, delay, tap step, capacitor threshold, initial state or
objective may be selected using April or May outcomes. No P/Q/schedule repair,
migration, retiming, MESS activation or Actual optimization is authorized.
Voltage violations are measurements and must not fail the diagnostic's
convergence/control-isolation gate.

This intended contract is **not production-ready**. Current exact source has
zero CapControl objects and no switching parameters. The requested capacitor
law therefore cannot be frozen or activated. No synthetic settings or fixed
bank state are promoted to autonomous-control authority. The common contract
applies equally to all arms and months, including this same blocking condition.
May scientific execution remains NOT_RUN. No April-only workaround is used.
