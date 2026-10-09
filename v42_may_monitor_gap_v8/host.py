"""Ordinary-user Scheduler entry point; no Solver or Coordinator operations."""
from pathlib import Path
import sys
import traceback
from v42_pr134_b1.common import atomic, process, now
from v42_may_campaign.process_probe import job_information


def main():
    role, root = sys.argv[1], Path(sys.argv[2]).resolve()
    sys.stdout = (root/(role+'_gap_v8.stdout.log')).open('a',encoding='utf-8',buffering=1)
    sys.stderr = (root/(role+'_gap_v8.stderr.log')).open('a',encoding='utf-8',buffering=1)
    atomic(root/(role.upper()+'_GAP_V8_HOST.json'),dict(process=process(),job=job_information(),UTC=now()))
    try:
        if role == 'monitor':
            from .monitor import run
            run(root)
        elif role == 'watchdog':
            from .service import watchdog
            watchdog(root)
        else:
            raise ValueError('READ_ONLY_MONITOR_ROLE_REQUIRED')
    except Exception as error:
        atomic(root/(role.upper()+'_GAP_V8_ERROR.json'),dict(error=repr(error),traceback=traceback.format_exc(),UTC=now()))
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
