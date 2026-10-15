"""Public Table V date binding; no planning, Actual, or solver IO."""
from datetime import datetime, timezone, timedelta


def require_day(day):
    if type(day) is not str or day not in {f'2025-05-{n:02d}' for n in range(1, 32)}:
        raise ValueError('TABLE_V_INDEPENDENT_MAY_DATE_REQUIRED')
    return day


def context_day(context):
    """The current manifest owns the day; public source axes must agree."""
    state = context.get('state') or {}
    day = require_day(context['manifest'].get('day', context.get('day', state.get('day'))))
    if ('state' in context and context['state'].get('day') != day
            or 'day' in context and context['day'] != day
            or 'data' in context and context['data'][0].get('day') != day):
        raise ValueError('TABLE_V_CURRENT_DATE_STATE_AND_NATIVE_SOURCE_DRIFT')
    begin = state.get('begin_epoch_seconds')
    if begin is not None:
        midnight = datetime.fromisoformat(day).replace(tzinfo=timezone(timedelta(hours=10))).timestamp()
        if begin != midnight:
            raise ValueError('TABLE_V_CURRENT_DATE_AEST_MIDNIGHT_REQUIRED')
    return day
