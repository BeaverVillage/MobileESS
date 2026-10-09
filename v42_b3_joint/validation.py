"""Receipt interfaces to original physics; no substitute physical equations."""
import json
from .contracts import AIDCDecision, MESSDecision, PhysicalReceipt, require, require_sha
from .certificates import verify_certificate
from .policy import require_production_authorization


def verify_physical(request, result, *, evidence_kind="MOCK"):
    if evidence_kind != "MOCK":
        require_production_authorization("REAL_PHYSICAL_ADMISSION")
    receipt = result.physical
    require(isinstance(receipt, PhysicalReceipt), "ORIGINAL_INTEGER_PHYSICAL_RECEIPT_REQUIRED")
    require(receipt.stage == request.stage and receipt.authority_sha == request.authority.sha,
            "PHYSICAL_STAGE_AUTHORITY_DRIFT")
    require(receipt.fixed_input_sha == request.fixed_input_sha and receipt.decision_sha == result.decision_sha,
            "PHYSICAL_FIXED_OR_DECISION_DRIFT")
    require(receipt.evidence_kind == evidence_kind, "PHYSICAL_EVIDENCE_KIND_DRIFT")
    require(receipt.original_integer_physical_verified is True, "ORIGINAL_INTEGER_PHYSICAL_VERIFIER_REQUIRED")
    require_sha(receipt.replay_sha)
    require_sha(receipt.verifier_source_sha)
    require_sha(receipt.original_model_sha)
    require(receipt.original_model_sha == result.certificate.original_model_sha, "PHYSICAL_ORIGINAL_MODEL_SHA_DRIFT")
    return {"contract_verified": True, "evidence_kind": evidence_kind,
            "original_physics_executed": False}


def verify_stage(request, result, *, budget=None, evidence_kind="MOCK"):
    require(result.stage == request.stage and result.authority == request.authority, "STAGE_AUTHORITY_DRIFT")
    require(isinstance(result.aidc, AIDCDecision), "COMPLETE_AIDC_DECISION_REQUIRED")
    require((result.mess is not None) == (request.stage != "A1"), "MESS_OFF_ONLY_AT_A1")
    require(result.mess is None or isinstance(result.mess, MESSDecision), "COMPLETE_MESS_DECISION_REQUIRED")
    if request.fixed_aidc is not None:
        require(result.aidc.sha == request.fixed_aidc.sha, "M_STAGE_CHANGED_FIXED_AIDC")
    if request.fixed_mess is not None:
        require(result.mess.sha == request.fixed_mess.sha, "A2_CHANGED_FIXED_MESS")
    certificate = verify_certificate(request, result, evidence_kind=evidence_kind)
    physical = verify_physical(request, result, evidence_kind=evidence_kind)
    receipt = json.loads(result.native_receipt)
    require(evidence_kind == "MOCK", "REAL_BUDGET_VERIFICATION_DEFERRED")
    require(receipt.get("stage") == request.stage and receipt.get("evidence_kind") == "MOCK", "STAGE_NATIVE_LEDGER_IDENTITY")
    require(receipt.get("authority_sha") == request.authority.sha and receipt.get("fixed_input_sha") == request.fixed_input_sha
            and receipt.get("request_sha") == request.request_sha, "NATIVE_LEDGER_INPUT_IDENTITY_DRIFT")
    require(receipt.get("native_limit_seconds") == 5400 and receipt.get("wall_limit_seconds") is None
            and receipt.get("budget_basis") == "MEASURED_NATIVE_RUNTIME_ONLY", "NATIVE_ONLY_90_MIN_REQUIRED")
    require(type(receipt.get("P2_calls")) is int and receipt["P2_calls"] == 0 and type(receipt.get("Threads")) is int and receipt["Threads"] == 1
            and type(receipt.get("real_native_optimize_calls")) is int and receipt["real_native_optimize_calls"] == 0,
            "B3_NATIVE_ZERO_P1_SINGLE_THREAD_REQUIRED")
    runtime = receipt.get("simulated_native_runtime")
    require(type(runtime) in (int, float) and 0 <= runtime <= 5400 and receipt.get("quarantined") is False,
            "INVALID_OR_EXHAUSTED_NATIVE_RUNTIME")
    calls = receipt.get("calls")
    require(isinstance(calls, list) and receipt.get("simulated_calls") == len(calls), "LEDGER_CALLS_REQUIRED")
    total = 0
    for call in calls:
        value = call.get("Runtime")
        require(type(value) in (int, float) and 0 <= value <= 5400 and call.get("runtime_unavailable") is False,
                "LEDGER_MEASURED_RUNTIME_REQUIRED")
        require(total < 5400 and call.get("effective_TimeLimit") == 5400 - total
                and type(call.get("failed")) is bool and call.get("kind") in ("LP", "MILP", "PRICING", "QCP"),
                "LEDGER_REMAINING_LIMIT_DRIFT")
        total += value
    require(total == runtime and receipt.get("remaining_seconds") == 5400 - runtime, "LEDGER_CUMULATIVE_RUNTIME_DRIFT")
    if budget is not None:
        require(budget.stage == request.stage and result.native_receipt == budget.sealed_receipt(), "BACKEND_LEDGER_SUBSTITUTION")
    return {"certificate": certificate, "physical": physical, "status": "STATIC_CONTRACT_PASS",
            "scientific_certified": False}
