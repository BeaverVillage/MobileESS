"""Read-only Actual telemetry; physical slot completion stays event based."""
from datetime import datetime, timezone
from pathlib import Path
import json
import math


def read(path):
    try:
        value = json.loads(Path(path).read_text(encoding='utf-8-sig'))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def timestamp(value):
    try:
        parsed = datetime.fromisoformat(value)
        return parsed.timestamp() if parsed.tzinfo is not None else None
    except (TypeError, ValueError, OverflowError):
        return None


def actual_state(case, arm, now=None):
    case = Path(case)
    progress = read(case/'ACTUAL/progress.json')
    heartbeat = read(case/'ACTUAL/HEARTBEAT.json')
    latest = heartbeat.get('latest')
    event_time = timestamp(progress.get('UTC'))
    heartbeat_time = timestamp(heartbeat.get('UTC'))
    if isinstance(latest, dict) and heartbeat_time is not None:
        if event_time is None or heartbeat_time >= event_time:
            progress = dict(progress, **latest)
    now = datetime.now(timezone.utc).timestamp() if now is None else now
    telemetry = dict(event_age_seconds=max(0., now-event_time) if event_time is not None else None)
    # Independent Fresh and subsequent variants must not inherit the old probe count.
    if 'FRESH' in str(progress.get('phase', '')).upper():
        return progress, heartbeat, telemetry
    activity = read(case/'CURRENT_AC_R029_PERFORMANCE.json')
    stamp = timestamp(activity.get('UTC'))
    count = activity.get('complete_probe_calls')
    if (activity.get('arm') == arm and stamp is not None and
            type(count) is int and count >= 0 and math.isfinite(stamp)):
        telemetry.update(completed_probe_calls=count, activity_UTC=activity['UTC'],
                         activity_age_seconds=max(0., now-stamp),
                         activity_scope='ACTUAL_ALL_VARIANTS_COMPLETED_PROBES')
    return progress, heartbeat, telemetry
