"""Exact typed deserialization of already audited public Table V descriptors.

No reference scheduler or domain issuance is rerun. Every reconstructed BASIC
and FULL_FLEX tuple must match its existing input fingerprint before use.
This metadata context intentionally has no runnable stage factories.
"""
from copy import deepcopy
from dataclasses import replace
import math
from pathlib import Path


def load_frozen_typed_context(execution_root):
    from v42_integration import release_initial_states as initial
    from v42_integration.d0_a_planning import _compile_d0_known_data, classify_d0_backlog, input_fingerprint
    from v42_integration.experimental_qos import ExperimentalQoSProvider
    from v42_integration.actual_validation import load_stats
    from v42_integration.qos import QoSWindowProvider
    from v42_integration.policy import digest
    from v42_integration.table_v_flex_planning import require_flex_case, require_flex_context
    from v42_native.service import boundary

    root = Path(execution_root)
    basic_dir, flex_dir = root / "INPUTS/BASIC", root / "INPUTS/FULL_FLEX"
    basic = initial.read(basic_dir / "D0_CASE_MANIFEST.json")
    manifest = initial.read(flex_dir / "TABLE_V_FLEX_CASE_MANIFEST.json")
    require_flex_case(manifest)
    if manifest["parent_basic_manifest"] != basic:
        raise ValueError("FROZEN_TYPED_PARENT_BASIC_MANIFEST_DRIFT")
    audit = initial.read(flex_dir / "TABLE_V_FLEX_INPUT_AUDIT.json")
    policy = initial.read(flex_dir / "TABLE_V_FLEXIBILITY_POLICY_FREEZE.json")
    if (policy["spec"] != manifest["science_derivation"]["policy"]
            or policy["known_observed_records"] != manifest["science_derivation"]["public_records"]
            or policy["case_sha"] != manifest["identity"]["case_sha"]):
        raise ValueError("FROZEN_TYPED_POLICY_AND_SCIENCE_MANIFEST_MISMATCH")
    state = initial.load_initial_state(manifest["initial_record"])
    public_native = basic_dir / "D0_NATIVE_PUBLIC_INPUT.json.gz"
    if public_native.is_file():
        native = initial.read(public_native)
    else:
        native = initial.read(initial.checked(basic["source_native_record"]))
        for merge in basic["source_physical_merge"]:
            projection = initial.read(initial.checked(merge["source_record"]))
            native[merge["field"]] = deepcopy(projection[merge["field"]])
            native["D0_current_physical_projection"] = deepcopy(merge["source_record"])
    rows, base_audit = classify_d0_backlog(state, source_identity=basic["identity"])
    data, _, _, _, _ = _compile_d0_known_data(state, rows, base_audit, native,
        basic["backlog_contract"], basic["identity"], basic["forecast_receipt"], {},
        basic["initial_record"], "FROZEN_TYPED_DESERIALIZATION_ONLY")
    expected_basic = initial.read(basic_dir / "D0_PLANNING_INPUT_AUDIT.json")["a_input_sha"]
    if input_fingerprint(data) != expected_basic:
        raise ValueError("FROZEN_TYPED_BASIC_INPUT_FINGERPRINT_MISMATCH")
    if public_native.is_file() and digest(native) != digest(data[0]):
        raise ValueError("FROZEN_TYPED_PUBLIC_NATIVE_BUNDLE_MISMATCH")
    stats = load_stats(initial.checked(policy["strict_stats_record"]))
    strict = QoSWindowProvider(stats, case_sha=policy["case_sha"], provider_sha=policy["provider_sha"])
    provider = ExperimentalQoSProvider(strict, scenario="E1", participation="FLEX30",
        case_sha=policy["case_sha"], seed=policy["spec"]["seed"], receipts=policy["known_issued_receipts"])
    if provider.stats.sha != policy["stats_sha"]:
        raise ValueError("FROZEN_TYPED_E1_PROVIDER_AUTHORITY_MISMATCH")
    bundle, jobs, bounds, resources, raw, _, _, prep = data
    bundle, raw, jobs, bounds, prep = deepcopy(bundle), deepcopy(raw), dict(jobs), dict(bounds), deepcopy(prep)
    bundle["D0_source_identity"] = deepcopy(manifest["identity"])
    bundle["Table_V_full_flex_policy"] = deepcopy(policy["spec"])
    masks = {r["uid"]: r for r in policy["domain_mask"]}
    originals = {r["uid"]: r for key in ("running", "pending") for r in state[key]}
    if set(jobs) != set(masks):
        raise ValueError("FROZEN_TYPED_POSITIVE_UID_MEMBERSHIP_MISMATCH")
    windows = {}
    for uid, original in list(jobs.items()):
        mask, receipt, row = masks[uid], provider.receipts[uid], originals[uid]
        model, running = receipt.model_metadata, original.state == "RUNNING"
        starts = tuple(mask["allowed_native_starts"])
        receipt_starts = ((24,) if running else tuple(24 + int((t - state["begin_epoch_seconds"]) / 900)
            for t in receipt.allowed_starts_seconds if state["begin_epoch_seconds"] <= t < state["end_epoch_seconds"]))
        if starts != receipt_starts:
            raise ValueError("FROZEN_TYPED_MASK_AND_ISSUED_RECEIPT_DISAGREE:" + uid)
        eligible = receipt.participant and receipt.eligible_for_contract
        reference = mask["reference_native_slot"]
        jobs[uid] = replace(original, reference_start=reference,
            reference_site=policy["reference_records"][uid]["reference_site"],
            initial_sites=tuple(mask["initial_sites"]), checkpoint_authorized=eligible,
            qos_policy_id=receipt.policy_id, qos_receipt_sha=digest(receipt.to_dict()),
            qos_allowed_starts=starts, qos_budget_seconds=receipt.budget_seconds,
            batch_eligible=model["batch_eligible"], qos=model["qos"], protected=model["protected"])
        bounds[uid] = boundary(jobs[uid], starts, digest(receipt.to_dict()), manifest["identity"]["runtime_sha"], H=120)
        deadline = policy["known_observed_records"][uid]["completion_deadline_seconds"]
        if deadline is not None:
            hard_end = math.floor((deadline - (state["begin_epoch_seconds"] - 24 * 900)) / 900)
            bounds[uid] = replace(bounds[uid], latest_completion=min(bounds[uid].latest_completion, hard_end))
        windows[uid] = starts
        raw[uid].update(reference_start_if_authorized=reference, reference_end=reference + original.service_slots,
            planning_site=jobs[uid].reference_site, can_timeshift=eligible and not running and len(starts) > 1,
            can_checkpoint_migrate=eligible, can_prestart_place=not running,
            compatible_sites=deepcopy(row["compatible_sites"]), Table_V_E1_receipt_sha=digest(receipt.to_dict()))
        if not running:
            raw[uid]["risk_nominal_completion_issue_slot"] += reference - original.reference_start
    bundle["known_population"] = [deepcopy(raw[r["job_uid"]]) for r in bundle["known_population"]]
    prep.update(classes={}, domain_authority="TABLE_V_E1_FULL_FLEX_UNMATERIALIZED",
        full_migration_domain_active=True, checkpoint_domain_scope="ORIGINAL_E1_FLEX30_SOURCE_WAN_HARD_CONTRACT",
        Table_V_full_flex_policy_sha=digest(policy["spec"]))
    typed = (bundle, jobs, bounds, deepcopy(resources), raw, {}, {}, prep)
    if input_fingerprint(typed) != audit["a_input_sha"] or audit["a_input_sha"] != manifest["full_flex_input_sha"]:
        raise ValueError("FROZEN_TYPED_FULL_FLEX_INPUT_FINGERPRINT_MISMATCH")
    context = dict(day=manifest["day"], manifest=manifest, state=state, data=typed, input_audit=audit,
        tablev_flex=policy, windows=windows, receipts={u: provider.receipts[u] for u in jobs},
        frozen_typed_metadata_only=True, runnable_stage_factories_present=False)
    require_flex_context(context)
    return context
