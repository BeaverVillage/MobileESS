"""A domain audit may consume only evidence available at issue time."""
from datetime import datetime


def instant(value):
    result = datetime.fromisoformat(str(value).replace('Z','+00:00'))
    if result.tzinfo is None:
        raise ValueError('EXPLICIT_INFORMATION_TIMEZONE_REQUIRED')
    return result


def require_causal_information(records, issue_time):
    issue = instant(issue_time)
    forbidden = {'actual_end','realized_end','future_duration','actual_runtime','future_outcome'}
    for row in records:
        if forbidden.intersection(row) or row.get('future_outcome_used',False):
            raise PermissionError('FUTURE_INFORMATION_ACCESS_REJECTED')
        if 'available_at' not in row or instant(row['available_at']) > issue:
            raise PermissionError('FUTURE_INFORMATION_ACCESS_REJECTED')
    return True
