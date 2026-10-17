from datetime import date,datetime,timedelta,timezone

DAYS=tuple(f'2025-05-{i:02d}' for i in range(1,8))
ARMS=('B0','B1','B2','B3')
MAIN_ORDER=tuple((day,arm) for day in DAYS for arm in ('B0','B1','B3'))
B2_ORDER=tuple((day,'B2') for day in DAYS)
AEST=timezone(timedelta(hours=10))
KST=timezone(timedelta(hours=9))
K48_SECONDS=300.
JOINT_SECONDS=900.
A_SECONDS=5400.
JOINT_CALL_CAP=140.
M_GAP=.03
A_GAP=.005
KNOWN_POLICY='B1_RESEARCH_RELAXED_KNOWN_WINDOW_V1'


def require_day(day):
    if day not in DAYS:raise ValueError('V44_ONLY_MAY01_TO_MAY07')
    return day


def axis(day):
    require_day(day);midnight=datetime.combine(date.fromisoformat(day),datetime.min.time(),AEST)
    issue=midnight-timedelta(hours=6);end=midnight+timedelta(days=1)
    return dict(day=day,timezone='AEST_FIXED_UTC_PLUS_10',issue_AEST=issue.isoformat(),
        issue_UTC=issue.astimezone(timezone.utc).isoformat(),issue_KST=issue.astimezone(KST).isoformat(),
        begin_AEST=midnight.isoformat(),end_AEST=end.isoformat(),issue_seconds=issue.timestamp(),
        day_start_seconds=midnight.timestamp(),end_seconds=end.timestamp(),dt_seconds=900,
        evaluation_slots=96,execution_slots=120,prefix_slots=24)


def policy():
    return dict(mode='PREPARE_ONLY',days=list(DAYS),cases=28,Main_workers=1,B2_workers=2,
        Threads=1,three_heavy_workers_certified=False,admission='B2_TWO_FIRST_MAIN_WAITS_WHILE_B2_ACTIVE_OR_READY',
        K48_Native_seconds=K48_SECONDS,Joint_Native_seconds=JOINT_SECONDS,
        K48_budget_separate=True,Joint_single_call_cap=JOINT_CALL_CAP,A1_A2_Native_seconds=A_SECONDS,
        A1_A2_gap=A_GAP,M_gap=M_GAP,Known_research_policy=KNOWN_POLICY,
        Unknown_policy='R1_FLEX30_C1',R1_authority='R1_ASSUMED',
        FORECAST_CAUSAL_AVAILABILITY='NOT_CERTIFIED',RAM_numeric_gate=False,
        new_algorithms=False,initial_state_copied_from_prior_optimized_day=False,
        execution_requires_separate_explicit_user_permit=True)
