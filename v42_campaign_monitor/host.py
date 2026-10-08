"""Reuse the OS host; replace only the read-only monitor entry point."""
import sys
from v42_may_campaign import host, monitor as original
from .monitor import run


if __name__ == '__main__':
    if len(sys.argv) != 3 or sys.argv[1] != 'monitor':
        raise SystemExit('Only monitor <campaign-root> is supported')
    original.run = run
    raise SystemExit(host.main())
