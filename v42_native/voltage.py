"""User-frozen Problem 13 voltage authorities; squared Planning variables."""
from .contracts import digest, require

PLANNING_LOWER_PU = .955
PLANNING_UPPER_PU = 1.045
PLANNING_LOWER_SQUARED = .912025
PLANNING_UPPER_SQUARED = 1.092025
ACTUAL_LOWER_PU = .95
ACTUAL_UPPER_PU = 1.05


def authority():
    return dict(stages=['A1', 'M1', 'A2', 'M2'], lower_pu=PLANNING_LOWER_PU,
                upper_pu=PLANNING_UPPER_PU, lower_squared=PLANNING_LOWER_SQUARED,
                upper_squared=PLANNING_UPPER_SQUARED,
                Actual_lower_pu=ACTUAL_LOWER_PU, Actual_upper_pu=ACTUAL_UPPER_PU,
                fallback_allowed=False)


def authority_sha():
    return digest(authority())


def require_planning(lower, upper):
    require((lower, upper) == (PLANNING_LOWER_SQUARED, PLANNING_UPPER_SQUARED),
            'PLANNING_VOLTAGE_AUTHORITY_MISMATCH')
