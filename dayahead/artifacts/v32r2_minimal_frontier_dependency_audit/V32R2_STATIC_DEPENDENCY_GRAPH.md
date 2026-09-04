
# V32R2 static dependency graph

The trace contains 20 objects and separates `B1/B0` from
`B3/B2`.  Every object has exactly one class: `{'DECISION_DRIVING': 11, 'DIAGNOSTIC_ONLY': 3, 'NOT_REQUIRED': 2, 'PHYSICAL_REPLAY_REQUIRED': 4, 'UNRESOLVED': 0}`.

The frozen execution chain is `x_DA -> causal y_ACT -> exact C1 PCC injection
-> immutable Fresh trajectory`.  V30's planning inequality consumes only the
reduced same-slot vector `s[t,i]`, the matched anchor site injection, and
`M_CURRENT`; it does not consume the full branch/phase tensor after `s` has
been formed.

`traffic_mobility.json` is a legacy container with separable namespaces.
`_mess_authority` and `replay_mess` read only the engineering `mess` records.
Neither reads `actual_volume` or a traffic quantile.  Accordingly the absent
2025-02-28 SCATS actual is diagnostic metadata, not a frontier input.

For B0/B1, `CASE_ACTUATORS` disables controllable MESS and the lower-level
model applies the same frozen maintenance trajectory.  For B2/B3, distinct
P/Q schedules are needed, but the B2-anchored rung order and all-scenario
planning/Fresh gates are already frozen by V29R2.  General-day orchestration
is missing; a new MESS policy is not.
