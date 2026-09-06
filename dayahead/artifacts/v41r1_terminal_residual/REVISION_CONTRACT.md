# V41R1 independent-day terminal residual

Scientific scheduling and all electrical/Actual evaluation remain 96 slots.
Day slot = issue slot minus 24; D00..D24 = issue [24,120).
The full runtime scalar Q90 duration is retained. Each eligible in-day PENDING
choice must satisfy max(0, issue_start + duration - 120) <= its own common
reference residual. No aggregate offsets or terminal objective exist.

The 215 PENDING-at-issue jobs with pre-D00 reference starts are fixed carry-in:
PRE_DAY_START_FIXED_CARRY_IN_PENDING_AT_ISSUE. Their start, site and admission
stay frozen. Pre-day + in-day + terminal service equals their full duration.
Unadmitted work remains unadmitted. No after-H scheduling variable is created.
All policy-days initialize from their own authoritative daily snapshot, never
another optimized policy-day's terminal state.

The user's final voltage scope supersedes earlier voltage-margin instructions:
VOLTAGE_SECURITY_MARGIN_REVISION = CANCELLED_BY_USER
EPSILON_V_UP = NOT_INTRODUCED
NEW_VOLTAGE_MARGIN = NONE
The existing lower voltage limit, 1.05 pu upper limit, branch/phase current and
rho constraints, corrected mapper, Fresh and Actual OpenDSS remain unchanged.
No Actual outcome may tune, clip, repair or re-optimize these quantities.

The five objective priorities remain rho_max, mean H4 shortfall, migration
count, reference deviation and stable tie. ML remains deterministic scalar
Q90 and capped H4 GPUh, service level metadata exactly 0.85. Actual uses frozen
Day-Ahead decisions and realized runtime with existing physical rack dispatch;
no ML fitting or optimization in Actual. A0-M1-A1-MF-freeze-Fresh remains intact.

Preserve old May01 evidence and execute new B0 DayAhead, B0 Actual, B1 DayAhead,
B1 Actual under one scientific commit. Report raw electrical outcomes. Full
May is forbidden unless every mandatory revised pilot validation gate passes.
