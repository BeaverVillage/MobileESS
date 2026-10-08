"""Compatibility entry point for the Native-only, read-only campaign display."""
from v42_campaign_monitor.monitor import view, run

if __name__ == '__main__':
    import sys
    run(sys.argv[1])
