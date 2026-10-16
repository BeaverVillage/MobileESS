# V43 selective port matrix

| Component | Source | V43 status | Admission |
|---|---|---|---|
| May01 AIDC adapter | PR189 `v42_may_campaign_native90/a_stage.py` | restored byte-exact | Gate A required |
| Other-date recovery | PR189 `v42_may31_recovery_v10` | present, not activated | date-specific original routing |
| Phase I / pricing | PR189 canary, phase1, compact_rowgen | preserved | exact zero, omitted rows, complete pricing |
| Known frozen execution | PR223 / PR228 | NOT_PORTED | after Gate A |
| Signed sensitivity | PR223 `aidc_sensitivity_runtime.py`, `sensitivity_policy.py` | NOT_PORTED | audit complete original line-phase/time axis |
| Pending pre-site | PR224/225/226/228 release_actual, research_presite_actual/contract | NOT_PORTED | strict UID authority and Q50/Q90 guards |
| Current AC admission | `current_ac_admission.py` | NOT_PORTED | current observed state only |
| Seedless K48 | PR231 | NOT_PORTED | after Gate B, same-case bound |
| Adaptive Beam–4 MESS Joint | PR219–222 | NOT_PORTED | Original FULL / physical contract |
| V42.2 D0/E1/FLEX30 AIDC MILP | PR231 | EXCLUDED | prohibited wholesale import |

No candidate, incumbent, historical UB/LB, Native time or solved state is imported into the new Golden attempt. External original causal inputs are referenced read-only by SHA.
