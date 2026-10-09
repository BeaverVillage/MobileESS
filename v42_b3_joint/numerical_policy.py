"""Versioned May precision at the B3 source Native admission boundary.

This adapter changes Solver arithmetic settings only. Original model/replay
tolerances, Method, integrality, objective, pricing and built-in heuristics are
preserved. The May25 original-row diagnostic is reference evidence, not a B3
scientific certificate. No Solver is imported here.
"""
import math
from .contracts import digest, require

VERSION = "B3_MAY_PRECISION_ORIGINAL_ROWS_V1"
DAYS = frozenset(f"2025-05-{n:02d}" for n in range(1, 32))
STAGES = frozenset(("A1", "M1", "A2", "M2"))
COMPONENTS = frozenset(("P1", "ORIGINAL_P1", "PHASE_I", "INTEGER_CONTROL",
    "NODE_LP", "LOCAL_PRICING", "FEASIBILITY_LP", "FEASIBILITY_MIP", "LP_DUAL",
    "UB", "PRICING", "RMP"))
PRECISION = dict(FeasibilityTol=1e-9, OptimalityTol=1e-9, NumericFocus=3, ScaleFlag=2)
SOURCE_PARAMETERS = ("Threads", "TimeLimit", "Method", "NodeMethod", "MIPGap",
    "IntFeasTol", "Heuristics", "Cuts", "Seed", "Presolve", "Crossover", "MIPFocus",
    "FeasibilityTol", "OptimalityTol", "NumericFocus", "ScaleFlag")


def policy_sha():
    return digest(dict(version=VERSION, days=sorted(DAYS), stages=sorted(STAGES),
        precision=PRECISION, A_components=["PHASE_I", "ORIGINAL_P1"],
        A_phase_I_Presolve=0, A_phase_I_Method_preserved=2,
        M_all_admitted_components=True, scientific_acceptance_tolerance_unchanged=True))


def required_settings(day, stage, component):
    require(day in DAYS and stage in STAGES and component in COMPONENTS,
        "B3_NUMERICAL_EXACT_MAY_STAGE_COMPONENT_REQUIRED")
    values = dict(PRECISION) if stage.startswith("M") or component in ("PHASE_I", "ORIGINAL_P1") else {}
    if stage.startswith("A") and component == "PHASE_I":
        values["Presolve"] = 0
    return values


def settings_metadata(day, stage, component, effective=None):
    overrides = required_settings(day, stage, component)
    effective = dict(effective or {})
    heuristics = effective.get("Heuristics")
    return dict(version=VERSION, policy_sha=policy_sha(), day=day, stage=stage,
        component=component, overrides=overrides, effective_parameters=effective,
        numerical_precision_override=bool(overrides),
        phase_I_original_rows=stage.startswith("A") and component == "PHASE_I",
        original_method_unchanged=True, solver_policy_unchanged=not bool(overrides),
        scientific_acceptance_tolerance_unchanged=True,
        heuristics_parameter=heuristics,
        built_in_heuristics_active=heuristics > 0 if type(heuristics) in (int, float) else None,
        heuristics_changed=False, scientific_certified=False)


def _snapshot(model):
    values = {name: getattr(model.Params, name) for name in SOURCE_PARAMETERS
              if hasattr(model.Params, name)}
    # Source apply_policy precedes its finite budget assignment. Infinity here
    # is a transient constructor setting, never a Native admission TimeLimit.
    if "TimeLimit" in values and not math.isfinite(values["TimeLimit"]):
        del values["TimeLimit"]
    return values


def apply_native_precision(model, *, day, stage, component, evidence_kind="SOURCE"):
    overrides = required_settings(day, stage, component)
    require(evidence_kind in ("SOURCE", "FAKE_SOURCE_TEST"), "B3_NUMERICAL_EVIDENCE_KIND_REQUIRED")
    before = _snapshot(model)
    if stage.startswith("A") and component == "PHASE_I":
        require(before.get("Method") == 2, "B3_PHASE_I_ORIGINAL_METHOD_TWO_REQUIRED")
    setter = getattr(model, "setParam", None)
    require(callable(setter) or evidence_kind == "FAKE_SOURCE_TEST", "SOURCE_MODEL_SET_PARAM_REQUIRED")
    for name, value in overrides.items():
        if callable(setter):
            setter(name, value)
        else:
            setattr(model.Params, name, value)
    after = _snapshot(model)
    require(all(after.get(name) == value for name, value in overrides.items()),
        "B3_NUMERICAL_PARAMETER_READBACK_DRIFT")
    protected = {name: value for name, value in before.items() if name not in overrides}
    require(all(after.get(name) == value for name, value in protected.items()),
        "B3_NUMERICAL_ORIGINAL_PARAMETER_CHANGED")
    receipt = settings_metadata(day, stage, component, after)
    receipt["protected_parameters"] = protected
    receipt["content_sha"] = digest(receipt)
    return receipt


def verify_settings_receipt(receipt, *, day, stage, component):
    overrides = required_settings(day, stage, component)
    require(receipt.get("content_sha") == digest({key: value for key, value in receipt.items()
        if key != "content_sha"}), "B3_NUMERICAL_RECEIPT_CONTENT_DRIFT")
    require(receipt.get("version") == VERSION and receipt.get("policy_sha") == policy_sha()
        and receipt.get("day") == day and receipt.get("stage") == stage
        and receipt.get("component") == component and receipt.get("overrides") == overrides,
        "B3_NUMERICAL_POLICY_IDENTITY_DRIFT")
    effective = receipt["effective_parameters"]
    require(all(effective.get(name) == value for name, value in overrides.items())
        and all(effective.get(name) == value for name, value in receipt["protected_parameters"].items()),
        "B3_NUMERICAL_RECEIPT_SETTINGS_DRIFT")
    require(not (stage.startswith("A") and component == "PHASE_I") or effective.get("Method") == 2,
        "B3_PHASE_I_ORIGINAL_METHOD_TWO_REQUIRED")
    expected = settings_metadata(day, stage, component, effective)
    require(all(receipt.get(name) == value for name, value in expected.items()),
        "B3_NUMERICAL_RECEIPT_METADATA_DRIFT")
    return True


def assert_native_precision(model, receipt, *, day, stage, component):
    verify_settings_receipt(receipt, day=day, stage=stage, component=component)
    overrides = required_settings(day, stage, component)
    current = _snapshot(model)
    require(current == receipt["effective_parameters"]
        and all(current.get(name) == value for name, value in overrides.items())
        and all(current.get(name) == value for name, value in receipt["protected_parameters"].items()),
        "B3_NUMERICAL_NATIVE_ENTRY_SETTINGS_DRIFT")
    require(not (stage.startswith("A") and component == "PHASE_I") or current.get("Method") == 2,
        "B3_PHASE_I_ORIGINAL_METHOD_TWO_REQUIRED")
    return True


def bind_apply_precision(original_apply, *, stage, evidence_kind="SOURCE"):
    """Reuse source apply_policy, then override only the versioned settings."""
    require(callable(original_apply), "ORIGINAL_SOLVER_POLICY_CALLABLE_REQUIRED")
    def apply_precision(model, policy, gp, *, day, component):
        effective = original_apply(model, policy, gp)
        receipt = apply_native_precision(model, day=day, stage=stage,
            component=component, evidence_kind=evidence_kind)
        effective.update(receipt["overrides"])
        apply_precision.last_receipt = receipt
        return effective
    apply_precision.last_receipt = None
    return apply_precision
