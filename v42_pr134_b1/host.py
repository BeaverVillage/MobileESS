"""Scheduler-owned entry point with durable redirected logs."""
import sys,traceback
from .common import *

def main():
    mode,root=sys.argv[1],Path(sys.argv[2]);root.mkdir(parents=True,exist_ok=True)
    sys.stdout=(root/(mode+'.stdout.log')).open('a',encoding='utf8',buffering=1)
    sys.stderr=(root/(mode+'.stderr.log')).open('a',encoding='utf8',buffering=1)
    psutil.Process().nice(psutil.NORMAL_PRIORITY_CLASS)
    atomic(root/(mode.upper()+'_HOST.json'),dict(process=process(),UTC=now(),memory_guards=False,artificial_slowdown=False))
    try:
        if mode=='coordinator':
            from .coordinator import run
        elif mode=='watchdog':
            from .watchdog import run
        elif mode=='monitor':
            from .monitor import run
        else:raise ValueError('HOST_MODE')
        run(root)
    except Exception as e:
        atomic(root/(mode.upper()+'_HOST_ERROR.json'),dict(error=str(e),traceback=traceback.format_exc(),UTC=now()));traceback.print_exc();return 1
    return 0

if __name__=='__main__':sys.exit(main())
