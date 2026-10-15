"""Date-bound D0 adapter around the unchanged complete native formulation.

Compiling creates public descriptors and lazy original A/M factories. It does
not build a native matrix, call a solver, replay Actual, or solve OpenDSS.
May01 remains the exact source/case of the saved successful P1 point.
"""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import zipfile

import numpy as np

from . import release_initial_states as initial
from . import d0_case as original
from .d0_a_planning import classify_d0_backlog, _compile_d0_known_data, input_fingerprint
from .unified_contract import digest

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "docs/v42_unified_aidc_mess_research_20261014/RELEASE_RECOVERY_20261015"
SAVED = BASE / "RC01/A1_P1_120/CASE"
INITIALS = BASE / "RC02/INITIAL_STATES"
ARCHIVE = Path("D:/v42_may_joint_repair_campaign_20261013")
CC4_BASE = Path("D:/MobileESS_V42/docs/v42_may_b0_zero_margin_holdout")
SOURCE13 = ("v42_integration/d0_case.py", "v42_integration/d0_a_planning.py",
    "v42_integration/d0_execution.py", "v42_integration/d0_resource.py", "v42_integration/a_engine.py",
    "v42_root/native.py", "v42_native/grid.py", "v42_final/reserve.py", "v42_temporal/service.py",
    "v42_two/contract.py", "v42_integration/m_engine.py", "v42_integration/m_candidates.py",
    "v42_integration/aidc_sensitivity_runtime.py")
_VERIFIED_IMMUTABLE_FILES = {}


def seal(doc, field):
    doc = deepcopy(doc)
    doc[field] = digest(doc)
    return doc


def require_day(day):
    if day not in {f"2025-05-{i:02d}" for i in range(1, 32)}:
        raise ValueError("RELEASE_INDEPENDENT_MAY_DATE_REQUIRED")


def original_source_freeze():
    saved = initial.read(SAVED / "D0_CASE_MANIFEST.json")["source_freeze"]
    current = [initial.record(ROOT / path) for path in SOURCE13]
    if current != saved["files"] or digest(current) != saved["source_sha"]:
        raise ValueError("DATE_CASE_ORIGINAL_SOURCE13_DRIFT")
    return deepcopy(saved)


def verify_sources(records):
    seen = set()
    for receipt in records:
        key = (receipt["path"], receipt["sha256"], receipt["bytes"])
        if key not in seen:
            cached = _VERIFIED_IMMUTABLE_FILES.get(key)
            if cached is None or not cached[0].is_file() or cached[0].stat().st_size != cached[1] or cached[0].stat().st_mtime_ns != cached[2]:
                path = initial.checked(receipt)
                if len(_VERIFIED_IMMUTABLE_FILES) >= 512:
                    _VERIFIED_IMMUTABLE_FILES.clear()
                _VERIFIED_IMMUTABLE_FILES[key] = (path, path.stat().st_size, path.stat().st_mtime_ns)
            seen.add(key)


def load_state(day, receipt=None):
    require_day(day)
    if receipt is None:
        entry = initial.read(INITIALS / day / "INITIAL_STATE_RECEIPT.json")
        if entry["status"] != "INPUT_READY":
            raise ValueError("DATE_INITIAL_STATE_NOT_READY")
        receipt = entry["initial_state"]
    state = initial.load_initial_state(receipt)
    if state["day"] != day or state["begin_epoch_seconds"] != initial.midnight(day):
        raise ValueError("DATE_INITIAL_STATE_SAME_DAY_BINDING_REQUIRED")
    if (state.get("status") != "DDAY_INITIAL_STATE_AUTHORIZED" or state.get("MODEL_ASSUMPTION") is not True
        or state.get("KESTREL_OBSERVED_SITE") is not False or state.get("initial_queue_verified") is not True
        or state.get("active_running_site_authority") is not True or state.get("full96_initial_state_authorized") is not True):
        raise ValueError("DATE_APPROVED_INITIAL_MODEL_AND_QUEUE_AUTHORITY_REQUIRED")
    verify_sources(state["source_receipts"] + list(state["policy_sources"].values()))
    return state, deepcopy(receipt)


def coefficient_axes(certificate, day):
    """Read original archive headers and small axes; never materialize matrices."""
    from .production_case import FIELDS
    if (certificate.get("day") != day or certificate.get("schema") != "V42_SVR11_LDC_INTERVAL_ELECTRICAL_CERTIFICATE_V2"
        or certificate["input_identity"]["identity"]["inputs"]["day"] != day
        or certificate.get("Actual_inputs_read") != 0 or certificate.get("tap_optimization_variables") != 0):
        raise ValueError("DATE_APPROVED_11SVR_FORECAST_CERTIFICATE_REQUIRED")
    receipt = certificate["outputs"]["planning_coefficients"]
    path = initial.checked(receipt)
    shapes = {}
    with zipfile.ZipFile(path) as archive:
        for field in FIELDS + ("anchor_control",):
            with archive.open(field + ".npy") as stream:
                version = np.lib.format.read_magic(stream)
                shape, fortran, dtype = np.lib.format._read_array_header(stream, version)
            if fortran or not shape or shape[0] != 96 or dtype.kind != "f":
                raise ValueError("DATE_COEFFICIENT_ORIGINAL_96_AXIS_REQUIRED:" + field)
            shapes[field] = list(shape)
    with np.load(path, allow_pickle=False) as packet:
        controls, branches = tuple(map(str, packet["control_names"])), tuple(map(str, packet["branch_names"]))
        ratings = packet["rating_a"].copy()
    if len(controls) != 60 or sum(n.startswith("transformer.") for n in branches) != 153:
        raise ValueError("DATE_COEFFICIENT_ORIGINAL_11SVR_CURRENT_AXIS_REQUIRED")
    if ratings.shape != (len(branches),) or not np.isfinite(ratings).all() or np.any(ratings <= 0):
        raise ValueError("DATE_THERMAL_CURRENT_DENOMINATORS_REQUIRED")
    return dict(PASS=True, day=day, original_coefficient=deepcopy(receipt), field_shapes=shapes,
        control_count=60, transformer_current_rows=153, branch_current_rows=len(branches),
        coefficient_regeneration_calls=0, Native_calls=0, AC_solves=0,
        global_nonlinear_envelope_certified=certificate["global_nonlinear_envelope_certified"],
        validity_scope=certificate["validity_scope"], independent_Fresh_AC_required=True)


def merge_same_day_physical(native, day):
    """Original three-field physical projection, using that day's certificate."""
    cert_path = ARCHIVE / "models" / day / "ELECTRICAL_CERTIFICATE.json"
    cert = initial.read(cert_path)
    axes = coefficient_axes(cert, day)
    bundle = deepcopy(native)
    changes = []
    for field, value in (("electrical_certificate", initial.record(cert_path)),
        ("grid_outputs", cert["outputs"]), ("route_table", native["route_table"])):
        changes.append(dict(field=field, original_value_sha=digest(native[field]), current_value_sha=digest(value),
            source_record=initial.record(cert_path), source_scope="SAME_DAY_APPROVED_IEEE123_11SVR_PHYSICAL_ONLY"))
        bundle[field] = deepcopy(value)
    # This extra field is provenance only. The original mathematical compiler
    # consumes the same resource, service, CC4 and physical fields as May01.
    bundle["D0_date_physical_projection"] = initial.record(cert_path)
    return bundle, cert, changes, axes


def compile_contracts(day, state, initial_record, native):
    from .cc4_policy_inputs import load_frozen_cc4
    from .production_case import KERNEL, TIMING
    template = initial.read(SAVED / "D0_CASE_MANIFEST.json")
    begin = state["begin_epoch_seconds"]
    cc4 = load_frozen_cc4(CC4_BASE / "MAY_CC4_BINDING.json", CC4_BASE / "CC4" / ("DAY_" + day.replace("-", "") + ".json"),
        kernel_path=KERNEL, runtime_integrity_path=ROOT / "v42_final/runtime_bundle/INTEGRITY.json",
        planning_bundle_path=ARCHIVE / "raw" / day / "NATIVE_INPUT_TEMPLATE_B1.json")
    source_issue = datetime.fromisoformat(cc4["issue_time"]).timestamp()
    if cc4["target_day"] != day or source_issue > begin:
        raise ValueError("DATE_CC4_SAME_DAY_ASOF_REQUIRED")
    prior = [r for r in state["running"] + state["pending"] if r["origin_unknown"]]
    if any(r["submit_seconds"] >= begin for r in prior):
        raise ValueError("DATE_PREOBSERVED_CC4_DEBIT_COHORT_NOT_ESTABLISHED")
    axis = deepcopy(template["time_axis"])
    axis.update(planning_issue_epoch_seconds=begin, evaluation_begin_seconds=begin, evaluation_end_seconds=begin + 86400,
        public_issue_ISO=datetime.fromtimestamp(begin, timezone.utc).isoformat(), native_slot_zero_seconds=begin - 21600)
    backlog = deepcopy(template["backlog_contract"])
    backlog.pop("contract_sha")
    backlog.update(issue_seconds=begin, end_seconds=begin + 86400, initial_state_sha=state["common_initial_state_sha"])
    backlog = seal(backlog, "contract_sha")
    forecast = deepcopy(template["forecast_receipt"])
    forecast.pop("forecast_receipt_sha")
    forecast.update(issue_seconds=begin, day_begin_seconds=begin, forecast_source_available_seconds=source_issue,
        source_issue_time=cc4["issue_time"], target_day=day, model_id=cc4["model_id"], prediction_index=cc4["prediction_index"],
        Q50_GPUh=cc4["q50_hourly_GPUh"], Q90_GPUh=cc4["q90_hourly_GPUh"], cc4_sha=cc4["prediction_sha"],
        runtime_sha=cc4["runtime_sha"], kernel_sha=cc4["kernel_sha"], original_prediction_row_sha=cc4["original_selected_row_sha"],
        source_receipts=cc4["source_receipts"], initial_preobserved_D1_unknown_reclassified_known=len(prior),
        preobserved_debit_reason="ALL_PREOBSERVED_SUBMIT_BEFORE_TARGET_DAY_COHORT_BEGIN",
        model_selection_retrospective=cc4["selection_retrospective"])
    forecast = seal(forecast, "forecast_receipt_sha")
    campaign = initial.read(ARCHIVE / "CAMPAIGN_MANIFEST.json")
    physical = deepcopy(template["physical"])
    physical.update(equipment={k: campaign[k] for k in ("hardware", "scenario", "thermal")},
        electrical_certificate=deepcopy(native["electrical_certificate"]))
    freeze = original_source_freeze()
    science_payload = deepcopy(template["science_payload"])
    science_payload.update(source=freeze["source_sha"], backlog=backlog["contract_sha"], time_axis=digest(axis),
        physical=digest(physical), CC4=forecast["forecast_receipt_sha"])
    science = digest(science_payload)
    public = {k: state[k] for k in ("running", "pending", "historical_completed")}
    native_record = initial.record(ARCHIVE / "raw" / day / "NATIVE_INPUT_TEMPLATE_B1.json")
    case_payload = dict(science_sha=science, initial_semantic_sha=state["common_initial_state_sha"],
        public_input_sha=digest(public), forecast=forecast["forecast_receipt_sha"], native_source=native_record,
        timing=initial.record(TIMING))
    identity = dict(science_sha=science, case_sha=digest(case_payload), initial_state_sha=state["common_initial_state_sha"],
        cc4_sha=cc4["prediction_sha"], runtime_sha=cc4["runtime_sha"])
    manifest = dict(schema="D0_INDEPENDENT_DATE_PLANNING_CASE_V1", day=day, name=original.SCIENCE,
        identity=identity, source_sha=freeze["source_sha"], physical_sha=digest(physical), time_axis_sha=digest(axis),
        qos_sha=backlog["contract_sha"], response_sha=initial.read(native["electrical_certificate"]["path"])["outputs"]["planning_coefficients"]["sha256"],
        initial_record=initial_record, source_native_record=native_record, source_freeze=freeze, physical=physical,
        time_axis=axis, backlog_contract=backlog, forecast_receipt=forecast, science_payload=science_payload, case_payload=case_payload,
        backlog_contract_sha=backlog["contract_sha"], forecast_receipt_sha=forecast["forecast_receipt_sha"],
        historical_prefix_gate_excluded=True, no_historical_UB_LB_or_plan_transfer=True,
        initial_authority="APPROVED_DATE_SOURCE_PREFIX_AND_ORIGINAL_PR125_MODEL_RULES",
        date_compiler_source=[initial.record(__file__), initial.record(initial.__file__)],
        mathematical_source13_unchanged=True, P2_execution_authorized=False)
    return manifest, backlog, forecast, cc4


def require_date_case(manifest, *, stage=None):
    """Exact manifest verifier exposed to the production P1-only executor."""
    if manifest.get("schema") == "D0_STATE_CONDITIONED_PLANNING_CASE_V1":
        return original.require_case(manifest, stage=stage)
    if manifest.get("schema") != "D0_INDEPENDENT_DATE_PLANNING_CASE_V1":
        raise ValueError("DATE_EXPLICIT_D0_CASE_MANIFEST_REQUIRED")
    day = manifest["day"]
    require_day(day)
    if manifest.get("manifest_sha") != digest({k: v for k, v in manifest.items() if k != "manifest_sha"}):
        raise ValueError("DATE_CASE_MANIFEST_SEAL_DRIFT")
    if original_source_freeze() != manifest["source_freeze"]:
        raise ValueError("DATE_CASE_SOURCE13_DRIFT")
    verify_sources(manifest["date_compiler_source"] + [manifest["initial_record"], manifest["source_native_record"]]
        + list(manifest["physical"]["equipment"].values()) + [manifest["physical"]["electrical_certificate"]]
        + manifest["forecast_receipt"]["source_receipts"])
    state, _ = load_state(day, manifest["initial_record"])
    public = {k: state[k] for k in ("running", "pending", "historical_completed")}
    expected_payload = dict(science_sha=manifest["identity"]["science_sha"],
        initial_semantic_sha=state["common_initial_state_sha"], public_input_sha=digest(public),
        forecast=manifest["forecast_receipt"]["forecast_receipt_sha"], native_source=manifest["source_native_record"],
        timing=manifest["case_payload"]["timing"])
    if (state["day"] != day or state["common_initial_state_sha"] != manifest["identity"]["initial_state_sha"]
        or manifest["case_payload"] != expected_payload):
        raise ValueError("DATE_CASE_INITIAL_OR_NATIVE_INPUT_BINDING_DRIFT")
    if (manifest["identity"]["case_sha"] != digest(manifest["case_payload"])
        or manifest["identity"]["science_sha"] != digest(manifest["science_payload"])
        or manifest["physical_sha"] != digest(manifest["physical"])
        or manifest["time_axis_sha"] != digest(manifest["time_axis"])):
        raise ValueError("DATE_CASE_SCIENCE_CASE_PHYSICAL_AXIS_DRIFT")
    axis = manifest["time_axis"]
    begin = initial.midnight(day)
    if (axis["planning_issue_epoch_seconds"] != begin or axis["evaluation_begin_seconds"] != begin
        or axis["evaluation_end_seconds"] != begin + 86400 or axis["native_model_slots"] != [24, 120]
        or axis["slots"] != 96 or axis["dt_seconds"] != 900 or axis["native_slot_zero_seconds"] != begin - 21600
        or axis["historical_six_hour_prefix_is_new_gate"] is not False):
        raise ValueError("DATE_CASE_EXACT_96_SLOT_ORIGINAL_TIME_PROJECTION_REQUIRED")
    template = initial.read(SAVED / "D0_CASE_MANIFEST.json")
    expected_backlog = deepcopy(template["backlog_contract"])
    expected_backlog.pop("contract_sha")
    expected_backlog.update(issue_seconds=begin, end_seconds=begin + 86400, initial_state_sha=state["common_initial_state_sha"])
    expected_backlog = seal(expected_backlog, "contract_sha")
    forecast = manifest["forecast_receipt"]
    if (manifest["backlog_contract"] != expected_backlog or forecast["forecast_receipt_sha"] != digest({
        k: v for k, v in forecast.items() if k != "forecast_receipt_sha"}) or forecast["target_day"] != day
        or forecast["issue_seconds"] != begin or forecast["forecast_source_available_seconds"] > begin
        or forecast["actual_future_UIDs_used"] is not False or forecast["forecast_modifications"] != 0
        or forecast["fit_calls"] != 0):
        raise ValueError("DATE_CASE_ORIGINAL_BACKLOG_OR_CAUSAL_CC4_CONTRACT_DRIFT")
    expected_science = deepcopy(template["science_payload"])
    expected_science.update(source=manifest["source_sha"], backlog=expected_backlog["contract_sha"],
        time_axis=digest(axis), physical=digest(manifest["physical"]), CC4=forecast["forecast_receipt_sha"])
    native = initial.read(initial.checked(manifest["source_native_record"]))
    if (manifest["science_payload"] != expected_science or native["day"] != day
        or forecast["Q50_GPUh"] != native["C0_Q50"] or forecast["Q90_GPUh"] != native["C0_Q90"]
        or native["capacities"] != state["capacities"]):
        raise ValueError("DATE_CASE_ORIGINAL_SCIENCE_OR_LITERAL_SOURCE_CC4_DRIFT")
    if (manifest["physical"]["network"], manifest["physical"]["AIDC"], manifest["physical"]["installed_GPU"],
        manifest["physical"]["installed_SVR"], manifest["physical"]["original_RegControl"]) != ("IEEE123", 12, 780, 11, 7):
        raise ValueError("DATE_CASE_ORIGINAL_PHYSICAL_CONTRACT_DRIFT")
    if stage is not None and stage not in ("A1", "M1", "A2", "M2"):
        raise ValueError("DATE_CASE_ORIGINAL_FOUR_STAGE_REQUIRED")
    return manifest


def _require_context(context):
    require_date_case(context["manifest"])
    if (context["data"][0]["D0_source_identity"] != context["manifest"]["identity"]
        or input_fingerprint(context["data"]) != context["input_audit"]["a_input_sha"]):
        raise ValueError("DATE_CASE_NATIVE_INPUT_FINGERPRINT_DRIFT")
    return context


def attach_factories(context, output, call_cap):
    """Lazy exact original physical/A/M producers; no matrices are built here."""
    from .d0_a_planning import D0ACase
    from .production_case import ProductionPhysicalContext, planning_power, initial_mess, TIMING
    from .a_engine import PlanningGridContext
    from .coordinator import _full_a, _full_m
    from .m_engine import _write
    physical_cache, issued_m = {}, {}
    manifest, data = context["manifest"], context["data"]

    def materialize_physical():
        if not physical_cache:
            from v42_native.grid import GridAuthority
            from v42_native.voltage import Stage, voltage_for
            import pandas as pd
            campaign = initial.read(ARCHIVE / "CAMPAIGN_MANIFEST.json")
            physical = ProductionPhysicalContext(manifest["source_freeze"], campaign, data[0])
            power, idle, swing, power_sources = planning_power(data[0], physical.certificate)
            limits = voltage_for(Stage.A1)
            authority = GridAuthority(physical.certificate["input_identity"]["identity"]["inputs"]["OpenDSS_master"]["sha256"],
                digest(data[0]["capacities"]), digest(data[0]), digest(data[0]["battery"]), limits.lower_squared, limits.upper_squared,
                True, stage=Stage.A1, transformer_current_authority_sha256=physical.thermal["transformer_current_authority_sha256"],
                thermal_authority=physical.thermal, require_all_transformer_currents=True)
            physical_cache.update(physical=physical, power=power, idle=idle, swing=swing, authority=authority,
                timing=pd.read_csv(TIMING), initial_mess=initial_mess(data[0]), power_sources=power_sources)
        return physical_cache

    def make_a_case(stage="A1", fixed_mess=None, folder=None, upstream_m_result=None):
        _require_context(context)
        if stage not in ("A1", "A2"):
            raise ValueError("DATE_A1_A2_STAGE_REQUIRED")
        cached = materialize_physical()
        if stage == "A1" and fixed_mess is not None and fixed_mess != cached["initial_mess"]:
            raise ValueError("DATE_A1_INITIAL_ZERO_MESS_ANCHOR_REQUIRED")
        if stage == "A2":
            issued = issued_m.get((upstream_m_result or {}).get("case_sha"))
            if (not issued or issued["stage"] != "M1" or upstream_m_result.get("D0_source_identity") != manifest["identity"]
                or upstream_m_result.get("FULL_validated") is not True or upstream_m_result.get("stage") != "M1"
                or upstream_m_result.get("D0_fixed_AIDC_anchor") != issued["AIDC_anchor"]):
                raise ValueError("DATE_A2_CURRENT_BOUND_FULL_M1_REQUIRED")
            verified = _full_m(upstream_m_result)
            if verified["plan_sha"] != issued["output_MESS_anchor"] or verified != fixed_mess:
                raise ValueError("DATE_A2_FIXED_M1_ANCHOR_DRIFT")
        fixed_mess = fixed_mess or cached["initial_mess"]
        timing = cached["timing"]
        grid = PlanningGridContext(cached["physical"].coefficients, cached["power"], cached["idle"], cached["swing"],
            tuple(timing.Q10), tuple(timing.Q90), tuple(context["cc4"]["kernel"]), cached["authority"], fixed_mess)
        stage_sha = digest(dict(parent=manifest["identity"]["case_sha"], stage=stage,
            input_MESS_anchor=fixed_mess["plan_sha"], backlog_contract=context["backlog"]["contract_sha"]))
        return D0ACase(data, grid, Path(folder or output / stage), stage_sha, stage, "B3", context["windows"],
            context["receipts"], call_cap=float(call_cap), d0_input_audit=context["input_audit"])

    def make_m_case(stage, aidc, folder):
        from v42_may_campaign_native90.m_model import build_case
        from .m_candidates import generate
        from .m_engine import export_plan
        _require_context(context)
        if stage not in ("M1", "M2") or aidc.get("stage") != ("A1" if stage == "M1" else "A2"):
            raise ValueError("DATE_M_STAGE_CURRENT_A_STAGE_REQUIRED")
        if (aidc.get("source_identity") != manifest["identity"] or aidc.get("D0_input_sha") != context["input_audit"]["a_input_sha"]
            or aidc.get("D0_issue_seconds") != manifest["time_axis"]["planning_issue_epoch_seconds"]):
            raise ValueError("DATE_M_STAGE_CURRENT_A_SOURCE_BINDING_REQUIRED")
        if stage == "M1" and aidc.get("case_sha") != make_a_case("A1").case_sha:
            raise ValueError("DATE_M1_CURRENT_A1_STAGE_CASE_DRIFT")
        if stage == "M2" and aidc.get("input_MESS_anchor") not in {
            r["output_MESS_anchor"] for r in issued_m.values() if r["stage"] == "M1" and r.get("output_MESS_anchor")}:
            raise ValueError("DATE_M2_BOUND_A2_M1_ANCHOR_REQUIRED")
        if stage == "M2" and aidc.get("case_sha") != digest(dict(parent=manifest["identity"]["case_sha"], stage="A2",
            input_MESS_anchor=aidc["input_MESS_anchor"], backlog_contract=context["backlog"]["contract_sha"])):
            raise ValueError("DATE_M2_CURRENT_A2_STAGE_CASE_DRIFT")
        if (aidc.get("FULL_feasible") is not True or aidc.get("FULL_point_replay", {}).get("PASS") is not True
            or not 0 <= aidc.get("FULL_max_residual", np.inf) <= 1e-5):
            raise ValueError("DATE_M_STAGE_ORIGINAL_FULL_A_REQUIRED")
        _full_a(aidc)
        sites = sorted(data[0]["capacities"])
        planning = dict(sites=sites, PCC_P_kw=np.asarray([aidc["AIDC_P_by_site"][s] for s in sites]).T.tolist(),
            PCC_Q_kvar=np.asarray([aidc["AIDC_Q_by_site"][s] for s in sites]).T.tolist(),
            complete_AIDC_anchor=aidc["aidc_anchor"], CC4_service=aidc["CC4_service"], CC4_carryout=aidc["CC4_carryout"],
            anonymous_resource_envelope=aidc["anonymous_resource_envelope"])
        binding = dict(PASS=True, day=manifest["day"], arm="B3", stage=stage, AIDC_anchor=aidc["aidc_anchor"],
            QoS_SHA=context["backlog"]["contract_sha"], parent_case_sha=manifest["identity"]["case_sha"])
        case = build_case(dict(bundle=data[0], planning=planning, identity=binding),
            dict(day=manifest["day"], arm="B3", stage=stage, output=str(folder)), integration_context=materialize_physical()["physical"])
        case.identity.update(arm="B3", stage=stage, aidc_anchor=aidc["aidc_anchor"], qos_sha=context["backlog"]["contract_sha"],
            science_sha=manifest["identity"]["science_sha"], D0_parent_case_sha=manifest["identity"]["case_sha"], D0_source_sha=manifest["source_sha"],
            physical_sha=manifest["physical_sha"], time_axis_sha=manifest["time_axis_sha"], cc4_sha=manifest["identity"]["cc4_sha"],
            runtime_sha=manifest["identity"]["runtime_sha"])
        case.case_sha = digest(case.identity)
        case.candidate_generator, case.plan_exporter = generate, export_plan
        case.mess_stage_budget_seconds = 0.
        _write(Path(folder) / "INTEGRATION_COMPLETE_AIDC_BINDING.json", binding)
        _write(Path(folder) / "SCIENTIFIC_CASE_IDENTITY.json", dict(case_sha=case.case_sha, **case.identity))
        issued_m[case.case_sha] = dict(stage=stage, AIDC_anchor=aidc["aidc_anchor"], output_MESS_anchor=None)
        return case

    def bind_m_result(result):
        issued = issued_m.get(result.get("case_sha"))
        if (not issued or result.get("stage") != issued["stage"] or result.get("FULL_validated") is not True
            or result.get("binding", {}).get("aidc_anchor") != issued["AIDC_anchor"]):
            raise ValueError("DATE_M_RESULT_ISSUED_CURRENT_FULL_BINDING_REQUIRED")
        plan = _full_m(result)
        if plan.get("case_sha") != result["case_sha"]:
            raise ValueError("DATE_M_RESULT_PLAN_STAGE_CASE_DRIFT")
        issued["output_MESS_anchor"] = plan["plan_sha"]
        result = deepcopy(result)
        result.update(D0_source_identity=deepcopy(manifest["identity"]), D0_fixed_AIDC_anchor=issued["AIDC_anchor"])
        return result

    context.update(make_a_case=make_a_case, make_m_case=make_m_case, bind_m_result=bind_m_result,
        materialize_physical=materialize_physical, physical_materialized=False)
    return context


def compile_date_case(day, *, output, initial_receipt=None, call_cap=120.):
    """Concrete 96-slot public Native inputs; matrices and solvers stay lazy."""
    require_day(day)
    output = Path(output)
    if output.exists():
        raise FileExistsError("DATE_CASE_OUTPUT_ALREADY_EXISTS:" + str(output))
    original_source_freeze()
    state, initial_record = load_state(day, initial_receipt)
    if day == "2025-05-01":
        context = original.build_planning_inputs(output=output, call_cap=call_cap)
        saved = initial.read(SAVED / "D0_CASE_MANIFEST.json")
        saved_audit = initial.read(SAVED / "D0_PLANNING_INPUT_AUDIT.json")
        if context["manifest"] != saved or context["input_audit"]["a_input_sha"] != saved_audit["a_input_sha"]:
            raise ValueError("MAY01_SAVED_P1_SOURCE_CASE_INPUT_EXACT_COMPATIBILITY_FAILED")
        context["date_case_compile_acceptance"] = dict(PASS=True, day=day, saved_P1_case_exact_preserved=True,
            identity=context["manifest"]["identity"], input_sha=context["input_audit"]["a_input_sha"],
            Native_calls=0, AC_solves=0, native_model_builds=0)
        initial.write_json(output / "DATE_CASE_COMPILE_ACCEPTANCE.json", context["date_case_compile_acceptance"])
        return context
    native_path = ARCHIVE / "raw" / day / "NATIVE_INPUT_TEMPLATE_B1.json"
    native = initial.read(native_path)
    if native["day"] != day or native["capacities"] != state["capacities"]:
        raise ValueError("DATE_NATIVE_RAW_SAME_DAY_RESOURCE_REQUIRED")
    native, certificate, merge, axes = merge_same_day_physical(native, day)
    manifest, backlog, forecast, cc4 = compile_contracts(day, state, initial_record, native)
    classification, audit = classify_d0_backlog(state, source_identity=manifest["identity"])
    data, classification, audit, receipts, windows = _compile_d0_known_data(state, classification, audit,
        native, backlog, manifest["identity"], forecast, {}, initial_record, "INDEPENDENT_DATE_ORIGINAL_SOURCE")
    if audit["status"] != "PASS":
        raise ValueError("DATE_D0_SOURCE_LEGAL_START_WINDOW_NOT_CERTIFIED:" + str(audit["no_legal_D0_start_window_UIDs"]))
    manifest.update(source_physical_merge=merge, coefficient_axis_audit=axes)
    manifest = seal(manifest, "manifest_sha")
    context = dict(manifest=manifest, state=state, data=data, classification=classification, input_audit=audit,
        receipts=receipts, windows=windows, backlog=backlog, forecast=forecast, cc4=cc4)
    _require_context(context)
    acceptance = dict(PASS=True, day=day, status="COMPILED_PUBLIC_NATIVE_INPUTS", identity=manifest["identity"],
        initial_semantic_sha=state["common_initial_state_sha"], input_sha=audit["a_input_sha"],
        Native_calls=0, AC_solves=0, native_model_builds=0, domain_materialization="NOT_RUN",
        source13_exact=True, running_UIDs=audit["running_UIDs"], pending_UIDs=audit["pending_UIDs"],
        running_GPU=audit["initial_running_GPU"], native_jobs=len(data[1]), original_native_internal_slots=[24, 120],
        evaluation_slots=[0, 96], original_hard_contracts_preserved=True, original_P1_objective_unchanged=True,
        P2_calls=0, original_MESS_Beam_Joint_K48_producers_retained=True, production_heavy_execution="NOT_RUN",
        candidate_global_nonlinear_feasibility_certified=False, Actual96_and_Fresh_required=True,
        lazy_factory_runtime_materialization="NOT_RUN", physics=axes)
    context["date_case_compile_acceptance"] = acceptance
    output.mkdir(parents=True)
    for name, value in (("D0_CASE_MANIFEST.json", manifest), ("D0_PLANNING_INPUT_AUDIT.json", audit),
        ("D0_BACKLOG_RESEARCH_CONTRACT.json", backlog), ("D0_CC4_FORECAST_RECEIPT.json", forecast),
        ("DATE_CASE_COMPILE_ACCEPTANCE.json", acceptance)):
        initial.write_json(output / name, value)
    initial.write_json(output / "D0_NATIVE_PUBLIC_INPUT.json.gz", data[0], compressed=True)
    initial.write_json(output / "D0_PUBLIC_KNOWN_CLASSIFICATION.json.gz", classification, compressed=True)
    return attach_factories(context, output, call_cap)


def _production_context(context, day):
    context.update(day=day, require_case=require_date_case, production_case_verifier=require_date_case)
    return context


_compile_date_case_impl = compile_date_case


def compile_date_case(day, *, output, initial_receipt=None, call_cap=120.):
    return _production_context(_compile_date_case_impl(day, output=output,
        initial_receipt=initial_receipt, call_cap=call_cap), day)


def load_date_case(day, output, *, call_cap=120.):
    """Rebuild descriptors in a temporary directory; verify saved bytes only.

    Native models, solvers and AC are never entered, and the saved input
    directory is never modified. Parent stage checkpoints remain separate.
    """
    from tempfile import TemporaryDirectory
    output = Path(output)
    saved_manifest = initial.read(output / "D0_CASE_MANIFEST.json")
    require_date_case(saved_manifest)
    with TemporaryDirectory(prefix="v42_date_input_recheck_") as temporary:
        scratch = Path(temporary) / "CASE"
        context = compile_date_case(day, output=scratch, initial_receipt=saved_manifest["initial_record"], call_cap=call_cap)
        for path in scratch.rglob("*"):
            if path.is_file():
                saved = output / path.relative_to(scratch)
                if not saved.is_file() or saved.read_bytes() != path.read_bytes():
                    raise ValueError("RESUME_FROZEN_DATE_INPUT_ARTIFACT_DRIFT:" + str(saved))
        if context["manifest"] != saved_manifest:
            raise ValueError("RESUME_FROZEN_DATE_MANIFEST_DERIVATION_DRIFT")
        if day == "2025-05-01":
            make_a = context["make_a_case"]
            def make_a_at_saved_output(stage="A1", fixed_mess=None, folder=None, upstream_m_result=None):
                return make_a(stage, fixed_mess=fixed_mess, folder=folder or output / stage, upstream_m_result=upstream_m_result)
            context["make_a_case"] = make_a_at_saved_output
        else:
            context = attach_factories(context, output, call_cap)
        context["loaded_from_frozen_directory"] = True
    return _production_context(context, day)
