"""Require a completed objective-bearing Root log, not a time-limit timer."""
from pathlib import Path
import math, re

ROOT_OBJECTIVE=re.compile(r'^Root relaxation:\s+objective\s+([^,\s]+),.*?([\d.]+) seconds\b',re.I)
ROOT_TIMER=re.compile(r'^Root relaxation:.*?([\d.]+) seconds\b',re.I)

def completion(log):
    lines=[line.strip() for line in log.splitlines() if line.strip().startswith('Root relaxation:')]
    if len(lines)!=1:
        return dict(completed=False,status='ROOT_MESSAGE_MISSING_OR_MULTIPLE',completed_seconds=None,
            reported_elapsed_seconds=None,message=lines)
    line=lines[0];match=ROOT_TIMER.search(line);elapsed=float(match[1]) if match else None
    match=ROOT_OBJECTIVE.search(line)
    try:
        objective=float(match[1]) if match else None
    except ValueError:objective=None
    completed=bool(match and objective is not None and math.isfinite(objective)
        and math.isfinite(float(match[2])) and float(match[2])>0 and
        not any(word in line.lower() for word in ('time limit','interrupted','infeasible','unbounded')))
    return dict(completed=completed,status='COMPLETED' if completed else 'INCOMPLETE',
        completed_seconds=float(match[2]) if completed else None,
        reported_elapsed_seconds=elapsed,reported_objective=objective,message=line)

def verified_report(report):
    import hashlib
    receipt=report['full']['native_log'];path=Path(receipt['path']);data=path.read_bytes()
    if hashlib.sha256(data).hexdigest()!=receipt['sha256']:
        raise PermissionError('ROOT180_NATIVE_LOG_BYTE_DRIFT')
    return completion(data.decode('utf-8-sig'))

def require_completed(report):
    result=verified_report(report)
    if not result['completed']:
        raise PermissionError('ROOT180_NATIVE_ROOT_NOT_COMPLETED')
    if result['completed_seconds']!=report['full']['Root_LP_seconds']:
        raise PermissionError('ROOT180_ROOT_TIMER_LOG_DRIFT')
    return result
