# Live UB/LB display

The monitor read A-stage UB/LB only from final RESULT/progress fields, omitting the full Pricing trace and validated incumbent trajectory. It also showed only the active stage: after A2 completed, M2 preparation replaced the visible values with dashes and hid the completed A2 bounds.

The independent read-only helper now reads rational full-Pricing lower bounds and independently validated integer incumbents while A1/A2 run. Restricted LP objectives are shown separately and never promoted to integer UB or global LB. M stages can also show independently validated K48 results before a Joint result is available. Missing values explain whether model preparation, Pricing, K48 or FULL incumbent validation is pending. Tiny nonzero gaps use scientific notation.

A stage history table retains M1/A2/M2 values with source attempt, reuse status and certification scope. The active M2 UB remains pending until FULL validation even though completed A2 UB is available in the history. This avoids mixing different fixed plans and stages. Actual/Fresh retain their separate physical status.

The deployed helper is a copy of `v44_monitor_bounds/bounds.py` in the external monitor directory. Only the HTTP monitor was restarted; worker 56372, coordinator, affinity, scientific sources and Native ledgers were untouched. Regression tests cover pending/zero/nonfinite values, exact rational lower bounds, validated callbacks, rejected physical candidates, partial trace writes, restricted-bound exclusion, cross-stage reuse and rendered JavaScript syntax. Browser verification showed M2 K48 LB 0.3394632265, completed A2 UB 0.5362899155 / LB 0.5362899153 / gap 3.346e-08%, and separately marked reused M1.

Live monitor: http://127.0.0.1:8795/. Restart and before/after evidence are retained under campaign004/AUTONOMOUS_RECOVERY/MONITOR_BOUNDS_20261018T034457Z. The original failed May02 case and all sealed recovery revisions remain unchanged.
