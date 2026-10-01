"""Exact zero UB/LB certificate for nonnegative intervention objectives."""
from v42_two.contract import relative_gap as inherited_relative_gap
def certified_gap(incumbent,bound):
    # Relative gap has a zero denominator at an exactly proven zero optimum.
    # Equality of UB=LB=0 is an exact certificate, not a relaxed tolerance.
    if incumbent==0. and bound==0.:return 0.
    return inherited_relative_gap(incumbent,bound)
