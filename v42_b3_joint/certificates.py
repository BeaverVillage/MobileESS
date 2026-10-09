"""Exact gap and provenance checks; mock receipts remain mock evidence."""
from fractions import Fraction
from .contracts import Certificate, require, require_sha
from .policy import gap_target, require_production_authorization


def exact_bound(value):
    require(isinstance(value, str) and value.strip() == value and bool(value), "EXACT_GLOBAL_LB_UB_REQUIRED")
    try:
        result = Fraction(value)
    except (ValueError, ZeroDivisionError) as exc:
        raise ValueError("FINITE_EXACT_GLOBAL_BOUND_REQUIRED") from exc
    require(result >= 0, "NONNEGATIVE_RHO_BOUND_REQUIRED")
    return result


def verify_certificate(request, result, *, evidence_kind="MOCK"):
    if evidence_kind != "MOCK":
        require_production_authorization("REAL_CERTIFICATE_ADMISSION")
    cert = result.certificate
    require(isinstance(cert, Certificate), "INDEPENDENT_GLOBAL_CERTIFICATE_REQUIRED")
    require(cert.stage == request.stage == result.stage, "CERTIFICATE_STAGE_DRIFT")
    require(cert.authority_sha == request.authority.sha == result.authority.sha, "CERTIFICATE_AUTHORITY_DRIFT")
    require(cert.fixed_input_sha == request.fixed_input_sha == result.fixed_input_sha, "CERTIFICATE_FIXED_INPUT_DRIFT")
    require(cert.decision_sha == result.decision_sha, "CERTIFICATE_DECISION_SHA_DRIFT")
    for value in (cert.authority_sha, cert.fixed_input_sha, cert.decision_sha, cert.global_domain_sha, cert.verifier_source_sha, cert.original_model_sha):
        require_sha(value)
    require(cert.global_domain_sha == request.authority.physical_domain_sha, "GLOBAL_ORIGINAL_DOMAIN_SHA_DRIFT")
    require(cert.original_global_bound_verified is True, "ORIGINAL_GLOBAL_BOUND_VERIFIER_REQUIRED")
    require(cert.bound_scope == "STAGE_FIXED_INPUT_GLOBAL", "LOCAL_RESTRICTED_OR_JOINT_BOUND_FORBIDDEN")
    require(cert.evidence_kind == evidence_kind and evidence_kind in ("MOCK", "REAL"), "CERTIFICATE_EVIDENCE_KIND_DRIFT")
    require(cert.objective == "min rho_max" and type(cert.p2_calls) is int and cert.p2_calls == 0, "B3_P1_ONLY_REQUIRED")
    lower, upper = exact_bound(cert.lower_bound), exact_bound(cert.upper_bound)
    require(lower <= upper, "GLOBAL_LB_EXCEEDS_UB")
    gap = Fraction(0) if upper == 0 else (upper - lower) / upper
    require(gap <= gap_target(request.stage), "STAGE_GLOBAL_GAP_NOT_ACCEPTED")
    return {"contract_verified": True, "gap_exact": str(gap), "target_exact": str(gap_target(request.stage)),
            "scope": cert.bound_scope, "scientific_certified": False,
            "evidence_kind": evidence_kind, "joint_global_optimality_claim": False}
