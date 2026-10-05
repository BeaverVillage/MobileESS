"""Gated pending stages only; one experiment each and no continuation loop."""
from .common import *
import sys

def main():
    from .stage5 import run as fifth
    from .combination import run as final
    from .finalize import run as finalize
    if not (OUT/'05_ROOT_CUT_BENCHMARK.json').exists():fifth()
    if not (OUT/'M1_ACCEL_FINAL_COMBINATION.json').exists():final()
    finalize()
    print('ALL_PENDING_EXPERIMENTS_TERMINAL; STOP; NO_MORE_OPTIMIZE',flush=True)

if __name__=='__main__':main()
