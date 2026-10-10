"""One primal MESS engine for B2 M and B3 M1/M2."""

VERSION = 'V42_COMMON_MESS_PRIMAL_ANYTIME_U4_V1'
NATIVE_LIMIT_SECONDS = 1800.


def optimize_case(*args, **kwargs):
    from .engine import optimize_case as implementation
    return implementation(*args, **kwargs)
