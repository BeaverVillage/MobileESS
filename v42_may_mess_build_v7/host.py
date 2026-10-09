"""Scheduler-owned host adapter; all logs and process receipts are on D:."""
from pathlib import Path
import sys
import traceback

import psutil
from v42_pr134_b1.common import atomic, process, now
from .coordinator import runtime_path
from .common import environment
from .process_probe import job_information


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    mode, root = argv[0], runtime_path(argv[1])
    root.mkdir(parents=True, exist_ok=True)
    environment(root)
    sys.stdout = (root / (mode + '_v7r2.stdout.log')).open('a', encoding='utf-8', buffering=1)
    sys.stderr = (root / (mode + '_v7r2.stderr.log')).open('a', encoding='utf-8', buffering=1)
    psutil.Process().nice(psutil.NORMAL_PRIORITY_CLASS)
    atomic(root / (mode.upper() + '_V7R2_HOST.json'), dict(process=process(), UTC=now(), mode=mode,
                                                  job=job_information()))
    try:
        if mode == 'coordinator':
            from .coordinator import run
        elif mode == 'monitor':
            from .monitor import run
        elif mode == 'watchdog':
            from .watchdog import run
        else:
            raise ValueError('HOST_MODE_MUST_BE_COORDINATOR_MONITOR_OR_WATCHDOG')
        run(root)
    except BaseException as error:
        atomic(root / (mode.upper() + '_V7R2_HOST_ERROR.json'), dict(error=str(error),
               traceback=traceback.format_exc(), UTC=now(), process=process()))
        traceback.print_exc()
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
