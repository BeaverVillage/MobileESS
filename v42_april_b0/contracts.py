"""Fail-closed authority and immutable, causal offline replay boundaries."""
from datetime import datetime
from math import isfinite
import re

from v42_native.contracts import digest, require

BASE = 'e2d4779685fff6d0cf022c649733b2ca41fdfc08'
CRITERIA = ('planning_policy', 'frozen_schedule_generation', 'dday_replay',
            'causal_boundary', 'forecast_actual_mapping',
            'no_anonymous_promotion', 'no_future_leakage')
QUANTILES = (.90, .95, .975, .99)


def authority_gate(audit):
    missing = [k for k in CRITERIA if audit.get('criteria', {}).get(k) is not True]
    if audit.get('base_head') != BASE:
        missing.append('exact_base')
    for key in CRITERIA:
        evidence = audit.get('criterion_evidence', {}).get(key, [])
        if not evidence or any(not e.get('path') or not isinstance(e.get('line'), int)
                               or e['line'] < 1 or not re.fullmatch('[0-9a-f]{64}', e.get('sha256', ''))
                               or e.get('supports_authority') is not True for e in evidence):
            missing.append(key + '_positive_evidence')
    return dict(B0_APRIL_EXECUTION_AUTHORIZED=not missing,
                classification='AUTHORIZED' if not missing else 'BLOCKED_B0_ACTUAL_AUTHORITY',
                missing=missing)


def require_execution(audit, data):
    require(authority_gate(audit)['B0_APRIL_EXECUTION_AUTHORIZED'], 'BLOCKED_B0_ACTUAL_AUTHORITY')
    require(data.get('PASS') is True and data.get('authoritative') is True
            and data.get('synthetic') is False and data.get('future_filled') is False,
            'BLOCKED_APRIL_DATA_AUTHORITY')


def require_april(date, frozen_dates):
    day = datetime.strptime(date, '%Y-%m-%d')
    require(day.month == 4 and date in frozen_dates, 'APRIL_ONLY_PREREGISTERED_DATE')


def freeze_plan(plan, *, frozen_at, issue_time, inputs_available_at, authoritative, anonymous_promoted=False,
                synthetic=False, future_used=False):
    require(authoritative is True and anonymous_promoted is False and synthetic is False,
            'NO_INVENTED_OR_ANONYMOUS_B0_SCHEDULE')
    require(future_used is False and all(isfinite(t) for t in (inputs_available_at, issue_time, frozen_at))
            and inputs_available_at <= issue_time <= frozen_at, 'FUTURE_INFORMATION_FORBIDDEN')
    require(all(k in plan for k in ('route', 'known_jobs', 'P', 'Q')), 'INCOMPLETE_FROZEN_PLAN')
    return dict(schedule_sha256=digest(plan), frozen_at=frozen_at)


def require_replay(plan, freeze, da, dday):
    sha = digest(plan)
    require(freeze['schedule_sha256'] == sha, 'FROZEN_PLAN_CHANGED')
    require(da.get('schedule_sha256') == dday.get('schedule_sha256') == sha, 'SAME_PLAN_SHA_REQUIRED')
    require(freeze['frozen_at'] <= da['started_at'] and freeze['frozen_at'] <= dday['started_at'],
            'FREEZE_BEFORE_AC')
    require(da.get('OFFLINE_CALIBRATION_DIAGNOSTIC_ONLY') is True
            and da.get('operational_gate') is False, 'DA_AC_OFFLINE_ONLY')
    for receipt in (da, dday):
        require(all(receipt.get(k) is False for k in ('P_repair', 'Q_repair', 'route_repair',
                'schedule_repair', 'global_reoptimization')), 'IMMUTABLE_REPLAY_NO_REPAIR')
        require(receipt.get('engine') == 'OpenDSS' and receipt.get('fresh_run') is True
                and receipt.get('synthetic') is False, 'FRESH_AC_REQUIRED')
    return True


def feasibility_labels(s0, s2=None):
    require(s0 is None or type(s0) is bool, 'S0_STATE')
    require(s2 is None or type(s2) is bool, 'S2_STATE')
    return dict(B0_PHYSICALLY_FEASIBLE=s0, B0_ROBUST_MARGIN_FEASIBLE=s2)
