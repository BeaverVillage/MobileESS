"""B3-specific P1-only acceptance, separate from active B1/B2 policy."""
from fractions import Fraction

STAGES = ("A1", "M1", "A2", "M2", "PLANNING_FREEZE", "ACTUAL", "FRESH_AC", "VALIDATION")
B3_NATIVE_EXECUTION_AUTHORIZED = False
B3_PRODUCTION_CAMPAIGN_STARTED = False
B3_FRESH_AC_EXECUTED = False
NATIVE_LIMIT_SECONDS = 5400
THREADS = 1


def gap_target(stage):
    if stage not in STAGES[:4]:
        raise ValueError("OPTIMIZATION_STAGE_REQUIRED")
    return Fraction(1, 200) if stage.startswith("A") else Fraction(3, 100)


def parameters(stage):
    gap = gap_target(stage)
    return {"Threads": 1, "MIPGap": float(gap), "P2_calls": 0,
            "objective": "min rho_max", "native_limit_seconds": 5400,
            "wall_limit_seconds": None, "budget_basis": "MEASURED_NATIVE_RUNTIME_ONLY",
            "FeasibilityTol": 1e-6 if stage.startswith("A") else 1e-8,
            "OptimalityTol": 1e-6 if stage.startswith("A") else 1e-8,
            "IntFeasTol": 1e-5 if stage.startswith("A") else 1e-8}


def require_production_authorization(action="NATIVE"):
    # Deliberately unconditional. Neither environment variables, mutable module
    # flags, B1/B2 scopes nor a caller-provided Boolean unlock this preparation.
    # Future execution needs a separately reviewed implementation and evidence.
    raise PermissionError("B3_PRODUCTION_NOT_AUTHORIZED:" + action)
