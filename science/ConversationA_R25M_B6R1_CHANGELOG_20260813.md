# Conversation A — R25M B6R1 changelog

- Diagnosed uploaded B6 screen failure: `AttributeError: Unable to retrieve attribute 'ObjVal'` at the first CG iteration.
- Confirmed the continuous projected RMP itself solved optimally; failure occurred only after pricing mutated the model.
- Cache `rmp_obj = float(m.ObjVal)` immediately after each optimal RMP solve.
- Never query `ObjVal` after adding columns / `m.update()` without a re-solve.
- At exact pricing closure, set `full_lb` from the cached objective of the solved RMP.
- Added `ConversationA_R25M_B6_CG_LIVE.json` so each pricing iteration survives later failures.
- Scientific model, objective, feasible set, exact pricing, global 3% certificate logic, H54, 5-min cadence, Threads=1, and causal guards are unchanged.
