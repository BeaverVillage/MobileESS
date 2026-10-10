"""Independent physical acceptance and optional M-stage global certification."""
from fractions import Fraction
from .contracts import require
from .policy import COMMON_MESS_VERSION


def verify_m_acceptance(result, physical, bounds):
    require(result.get("engine_version") == COMMON_MESS_VERSION
        and result.get("feasible_accepted") is True and result.get("accepted") is True
        and result.get("PASS") is True, "M_COMMON_ENGINE_PHYSICAL_ACCEPTANCE_REQUIRED")
    require(physical.get("PASS") is True and physical.get("original_integer_physical_verified") is True,
        "M_ORIGINAL_FULL_PHYSICAL_ACCEPTANCE_REQUIRED")
    require(bounds.get("bound_scope") == "STAGE_FIXED_INPUT_GLOBAL"
        and bounds.get("joint_global_optimality_claim") is False,
        "M_GLOBAL_EVIDENCE_SCOPE_REQUIRED")
    upper = Fraction(bounds["exact_UB"])
    require(upper >= 0 and str(upper) == str(Fraction(result["exact_Global_UB"])),
        "M_INDEPENDENT_EXACT_UB_DRIFT")
    lower = bounds.get("exact_LB")
    if lower is None:
        require(bounds.get("original_global_bound_verified") is False
            and bounds.get("global_gap_certified") is False
            and result.get("global_gap_certified") is False
            and result.get("exact_Global_LB") is None and result.get("certified_gap") is None,
            "M_UNKNOWN_LB_MUST_NOT_CLAIM_GLOBAL_CERTIFICATION")
    else:
        lower = Fraction(lower)
        require(0 <= lower <= upper and bounds.get("original_global_bound_verified") is True,
            "M_INDEPENDENT_GLOBAL_BOUND_REQUIRED")
        gap = Fraction(0) if upper == 0 else (upper - lower) / upper
        certified = gap <= Fraction(3, 100)
        require(bounds.get("global_gap_certified") is certified
            and result.get("global_gap_certified") is certified
            and str(lower) == str(Fraction(result["exact_Global_LB"]))
            and result.get("exact_gap") == str(gap), "M_GLOBAL_GAP_CERTIFICATION_DRIFT")
    return True
