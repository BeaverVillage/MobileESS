"""Offline, exogenous-only representative-period selection for Mobile ESS."""

AXIS_STEPS_2025 = 105_120
AXIS_STEPS_2024 = 105_408
STEPS_PER_DAY = 288
STEPS_PER_WEEK = 2_016
BURN_IN_STEPS = 576

FORBIDDEN_FEATURE_TOKENS = (
    "controller",
    "objective",
    "solver",
    "violation",
    "selected_route",
    "mess_action",
    "rack_assignment",
    "realized_wan",
    "replan",
    "opendss",
    "e5c",
)
