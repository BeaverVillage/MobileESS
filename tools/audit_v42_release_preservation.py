"""Release-only MESS/provider preservation and dated-source inventory.

No optimizer, model construction, controller, forecast fit or campaign call is
imported or executed. Historical solve costs are observations, not a forecast
of the new D0 problem. Evidence is written to a new directory only.
"""
from __future__ import annotations

import argparse
import ast
import csv
from datetime import datetime, timezone, timedelta
from hashlib import sha256
import io
import gzip
import json
import math
from pathlib import Path
import struct
import subprocess
from time import perf_counter
import zipfile

ROOT = Path(__file__).resolve().parents[1]
BASE = Path("docs/v42_unified_aidc_mess_research_20261014")
REFERENCE = "490ff3ef7821705fc82c3823242d79093eb480b9"
DEFAULT_OUTPUT = ROOT / BASE / "RELEASE_RECOVERY_20261015/RC01/MESS"
CC4_BASE = Path("D:/MobileESS_V42/docs/v42_may_b0_zero_margin_holdout")
PROTECTED = (
    "v42_integration/m_engine.py", "v42_integration/m_candidates.py",
    "v42_integration/mess_actual.py", "v42_integration/mess_scaling.py",
    "v42_integration/coordinator.py", "v42_integration/unified_contract.py",
    "v42_integration/cc4_policy_inputs.py", "v42_integration/production_case.py",
    "v42_integration/actual_validation.py", "v42_integration/dday_boundary.py",
    "v42_common_mess", "v42_native/mess.py", "v42_native/mess_domain.py",
    "v42_m1_research/check_ub.py", "tools/time_decomposed_lb",
    "tools/critical_grid_cg", "v42_final/runtime.py", "v42_final/workload.py",
    "v42_final/inference", "v42_final/runtime_bundle", "v42_svr11", "v42_thermal",
    str(BASE / "UNIFIED_NATIVE_RUNTIME_LEDGER.json"),
    str(BASE / "SHARED_SOURCE_CASE_MANIFEST.json"),
    str(BASE / "UNIFIED_PHYSICAL_AUTHORITY.json"),
    str(BASE / "UNIFIED_INTERFACE_CONTRACT.json"),
)


def git(root, *args):
    return subprocess.check_output(["git", *map(str, args)], cwd=root)


def record(path):
    path = Path(path)
    if not path.is_file():
        return dict(path=str(path), exists=False, sha256=None, bytes=None)
    with path.open("rb") as stream:
        digest = sha256()
        for chunk in iter(lambda: stream.read(1048576), b""):
            digest.update(chunk)
    return dict(path=str(path.resolve()), exists=True, sha256=digest.hexdigest(), bytes=path.stat().st_size)


def read(path):
    path = Path(path)
    raw = path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix == ".gz" else raw)


def archived(root, relative, reference=REFERENCE):
    """Read an immutable Git blob without checking out a sparse artifact."""
    raw = git(root, "show", reference + ":" + relative)
    doc = json.loads(gzip.decompress(raw) if relative.endswith(".gz") else raw)
    return doc, dict(git_ref=reference, path=relative, sha256=sha256(raw).hexdigest(), bytes=len(raw))


def byte_preservation(root, reference=REFERENCE, protected=PROTECTED):
    rows = []
    entries = git(root, "ls-tree", "-r", "-z", reference, "--", *protected).split(b"\0")
    for entry in entries:
        if not entry:
            continue
        header, raw_path = entry.split(b"\t", 1)
        _, kind, oid = header.decode().split()
        if kind != "blob":
            continue
        relative = raw_path.decode("utf-8")
        original = git(root, "cat-file", "blob", oid)
        checkout = git(root, "cat-file", "--filters", reference + ":" + relative)
        actual = record(Path(root) / relative)
        expected = sha256(original).hexdigest()
        expected_checkout = sha256(checkout).hexdigest()
        rows.append(dict(relative=relative, git_blob=oid, reference_raw_blob_sha256=expected,
            reference_checkout_sha256=expected_checkout,
            checkout_filter_changes_blob_bytes=original != checkout,
            current=actual, status=("PASS" if actual["sha256"] == expected_checkout else
                "SPARSE_NOT_MATERIALIZED" if not actual["exists"] else "DRIFT")))
    return dict(PASS=bool(rows) and all(x["status"] != "DRIFT" for x in rows),
        baseline=reference, checked_files=len(rows),
        materialized_files=sum(x["current"]["exists"] for x in rows),
        comparison="EXACT_CHECKOUT_BYTES_AT_BASELINE_WITH_EXISTING_GIT_FILTERS;RAW_BLOB_SHA_ALSO_RECORDED",
        git_attributes_current=record(Path(root) / ".gitattributes"),
        original_CRLF_checkout_not_rewritten=True,
        sparse_absence_is_not_new_execution_evidence=True, files=rows)


def causal_day(day, issue_time, target_day):
    """The campaign's original fixed AEST (+10), not the host timezone."""
    boundary = datetime.fromisoformat(day).replace(tzinfo=timezone(timedelta(hours=10)))
    try:
        issue = datetime.fromisoformat(issue_time)
        if issue.tzinfo is None:
            raise ValueError("CC4_ISSUE_TIME_TIMEZONE_REQUIRED")
        good = target_day == day and issue <= boundary
    except (ValueError, TypeError):
        good = False
    return dict(PASS=good, requested_day=day, target_day=target_day, issue_time=issue_time,
        D0_boundary=boundary.isoformat(), future_issue_used=not good)


def original_prediction_row(path, index):
    """Read one literal float64 .npy row using the standard library only."""
    with zipfile.ZipFile(path) as archive, archive.open("q.npy") as stream:
        if stream.read(6) != b"\x93NUMPY":
            raise ValueError("CC4_NPY_MAGIC")
        major, minor = stream.read(2)
        header_size = struct.unpack("<H" if major == 1 else "<I", stream.read(2 if major == 1 else 4))[0]
        header = ast.literal_eval(stream.read(header_size).decode("latin1"))
        shape = header["shape"]
        if header["fortran_order"] or shape[1:] != (24, 2) or header["descr"] not in ("<f8", "=f8"):
            raise ValueError("CC4_ORIGINAL_ARRAY_SCHEMA")
        if type(index) is not int or not 0 <= index < shape[0]:
            raise ValueError("CC4_ORIGINAL_ROW_INDEX")
        stream.read(index * 48 * 8)
        raw = stream.read(48 * 8)
        if len(raw) != 48 * 8:
            raise ValueError("CC4_ORIGINAL_ROW_TRUNCATED")
    values = struct.unpack("<48d", raw)
    return [values[k] for k in range(0, 48, 2)], [values[k] for k in range(1, 48, 2)], raw, list(shape)


def cc4_inventory(day, binding_path, day_path):
    binding, daily = read(binding_path), read(day_path)
    checks, sources = [], []
    for role in ("prediction", "ledger", "selection"):
        expected = binding["interface"][role]
        actual = record(expected["path"])
        checks.append(actual["exists"] and all(actual[k] == expected[k] for k in ("sha256", "bytes")))
        sources.append(dict(role=role, expected=expected, actual=actual))
    causal = causal_day(day, daily["issue_time"], daily["target_day"])
    literal, ledger_match, numeric_sha = False, False, None
    if all(checks):
        interface = binding["interface"]
        index = daily["prediction_index"]
        q50, q90, raw, shape = original_prediction_row(interface["prediction"]["path"], index)
        literal = (q50 == daily["Q50_GPUh"] and q90 == daily["Q90_GPUh"]
            and index in binding["indices"] and shape == binding["array_shape"])
        numeric_sha = sha256(raw).hexdigest()
        with Path(interface["ledger"]["path"]).open(encoding="utf-8-sig", newline="") as stream:
            ledger = list(csv.DictReader(stream))
        ledger_match = (index < len(ledger) and ledger[index]["target_day"] == day
            and datetime.fromisoformat(ledger[index]["issue_time"]) == datetime.fromisoformat(daily["issue_time"]))
    anonymous = not daily.get("future_job_ids", []) and not daily.get("unknown_profile_site_allocation_bound", False)
    return dict(day=day, status="PASS_FROZEN_ROW_AND_ISSUE_TIME" if all(checks) and causal["PASS"] and literal and ledger_match and anonymous else "NOT_CERTIFIED",
        daily_file=record(day_path), binding_file=record(binding_path), source_files=sources,
        causal_issue=causal, original_prediction_row_equal=literal, original_ledger_equal=ledger_match,
        selected_row_sha256=numeric_sha, model_id=binding["interface"]["model"],
        fit_calls=binding["fit_calls"], forecast_modifications=binding["forecast_modifications"],
        inherited_selection_retrospective=binding["inherited_model_selection_retrospective"],
        fit_ingestion_receipts_certified=not binding["unexported_fit_ingestion_receipts_not_certified"],
        inherited_limitations_removed=False, forecasting_causality_not_recertified_by_file_presence=True)


def date_authority(day, candidates):
    """Require a date-specific authority; a May01 file cannot fill another day."""
    same_day = [x for x in candidates if x.get("day") == day and x.get("authorized") is True]
    return dict(day=day, status="FOUND_DATE_SPECIFIC_AUTHORITY" if same_day else "NOT_FOUND_IN_AUDITED_SCOPE",
        candidates=same_day, May01_state_copied=False, independent_day_ready=bool(same_day),
        continuous_carry_contract_supplied=False)


def historical_stage(doc, stage, source):
    call = doc.get("native_call", doc.get("Native_call", {}))
    seed = doc.get("current_case_seed", {}).get("Native_call", {})
    native = float(call["Native_Runtime"]) + float(seed.get("Native_Runtime", 0))
    return dict(stage=stage, evidence=source, case_sha=doc["case_sha"],
        scope="PR223_HISTORICAL_STAGE_ONLY_NOT_NEW_D0", Native_seconds=native,
        main_Native_seconds=call["Native_Runtime"], seed_Native_seconds=seed.get("Native_Runtime", 0),
        solver_status=call.get("native_status", call.get("status")),
        TimeLimit=call.get("TimeLimit", call.get("cap_seconds")),
        stage_wall_seconds=doc.get("wall_seconds"), build_wall_seconds=doc.get("build_wall_seconds"),
        stage_solve_seconds_including_score=doc.get("stage_solve_seconds"),
        FULL_validated=doc.get("FULL_validated", doc.get("FULL_feasible", False)),
        historical_warm_start=doc.get("historical_witness_supplied"),
        observed_return_is_new_D0_feasibility_guarantee=False,
        new_D0_Native_forecast_certified=False, new_D0_Wall_forecast_certified=False)


def proposed_budget(stage, observation, native_cap, return_reserve=30., overshoot_reserve=30.):
    """Bounded proposal only; never authorization or an invented measurement."""
    if (not all(math.isfinite(float(v)) for v in (native_cap, return_reserve, overshoot_reserve))
            or native_cap <= 0 or min(return_reserve, overshoot_reserve) < 0):
        raise ValueError("RELEASE_BUDGET_PROPOSAL_INVALID_CAP_OR_RESERVE")
    return dict(stage=stage, status="PROPOSAL_ONLY_NOT_AUTHORIZED_NOT_RUN",
        proposed_stage_total_solve_cap_seconds=float(native_cap),
        proposed_Optimize_cap_seconds=min(140., float(native_cap)) if stage in ("M1", "M2") else float(native_cap),
        existing_4Joint_140_second_call_clamp_preserved=stage in ("M1", "M2"),
        initialization_and_score_share_stage_cap=True,
        P2_or_extra_native_call_authorized=False,
        proposed_return_reserve_seconds=float(return_reserve),
        proposed_overshoot_reserve_seconds=float(overshoot_reserve),
        proposed_ledger_envelope_seconds=float(native_cap + return_reserve + overshoot_reserve),
        evidence=observation, measured_for_new_D0=False, certified_new_D0_runtime_estimate=None,
        guaranteed_FULL_feasible=False, expected_Wall_seconds=None,
        workers=1, Threads=1, requires_new_Source_Case_and_user_budget=True)


def current_a1(root):
    directory = Path(root) / BASE / "RELEASE_RECOVERY_20261015/RC01/A1_P1_120"
    path = directory / "A1_P1_RESULT.json"
    if not path.exists():
        return dict(status="NOT_AVAILABLE_AT_AUDIT", FULL_gate=False)
    result = read(path)
    ledger = read(directory / "SEPARATE_NATIVE_LEDGER_180.json")
    gate = (result.get("P1_acceptance") is True and result.get("FULL_feasible") is True
        and result.get("FULL_point_replay", {}).get("PASS") is True
        and result.get("Native_calls") == 1 and len(ledger["calls"]) == 1
        and ledger["authorization"]["scope"] == "D0_A1_P1_EXACTLY_ONE_CALL")
    return dict(status=result["status"], FULL_gate=gate, evidence=record(path),
        ledger_evidence=record(directory / "SEPARATE_NATIVE_LEDGER_180.json"),
        source_identity=result["source_identity"], stage_case_sha=result["stage_case_sha"],
        objective=result["objective"], bound=result["bound"], gap=result["gap"],
        Native_seconds=result["Native_Runtime"], SolCount=result["SolCount"],
        separate_limit_seconds=ledger["limit_seconds"],
        separate_unused_seconds=ledger["limit_seconds"] - ledger["conservative_solve_seconds"],
        unused_seconds_authorize_M1_A2_M2_K48=False,
        A1_objective_is_MESS_Global_LB=False, old_MESS_incumbent_used=False)


def fixed_plan_shape(root):
    relative = "docs/v42_common_am_qos_integration/receipts/DDAY_V5_FINAL/DDAY_V5_B3_FINAL_ATTEMPT01/B3/M2/COMMON_M_PR222/FULL_MESS_PHYSICAL_ANCHOR.json"
    plan, source = archived(root, relative)
    units = sorted(plan["routes"])
    shape = dict(units=len(units), nodes=len(plan["P_by_site"]),
        route_slots={u: len(plan["routes"][u]) for u in units},
        P_slots={u: len(plan["P_kW"][u]) for u in units}, Q_slots={u: len(plan["Q_kvar"][u]) for u in units},
        Mode_slots={u: len(plan["Mode"][u]) for u in units}, SOC_points={u: len(plan["SOC"][u]) for u in units})
    good = (shape["units"] == 4 and shape["nodes"] == 24
        and all(v == 96 for name in ("route_slots", "P_slots", "Q_slots", "Mode_slots") for v in shape[name].values())
        and all(v == 97 for v in shape["SOC_points"].values()))
    return dict(PASS=good, source=source, physical_axes=shape, original_plan_sha=plan["plan_sha"],
        case_sha=plan["case_sha"], scope="HISTORICAL_FIXED_PR223_M2_ONLY_NOT_NEW_D0_PLAN",
        full_24_site_P_Q_preserved=True, station_injections_replaced_by_zero=False,
        new_D0_handoff=False, new_FULL_replay_or_model_build=False)


def budget_evidence(root):
    prefix = "docs/v42_common_am_qos_integration/receipts/DDAY_V5_FINAL/DDAY_V5_B3_FINAL_ATTEMPT01/B3/"
    stages = []
    for stage in ("M1", "A2", "M2"):
        relative = prefix + stage + ("/A_RESULT.json.gz" if stage == "A2" else "/COMMON_M_PR222/M_STAGE_RESULT.json.gz")
        doc, source = archived(root, relative)
        stages.append(historical_stage(doc, stage, source))
    certificate, source = archived(root, "docs/v42_b2_minimax_beam1800/K32_K48_LB_CERTIFICATES.json")
    k48 = certificate["certificates"]["K48"]["proof"]
    k32 = certificate["certificates"]["K32"]["proof"]
    history = dict(evidence=source, case_sha=k48["case_sha"], scope="ORIGINAL_EXACT_HISTORICAL_CASE_ONLY",
        K48_Native_seconds=k48["Native_Runtime"], K32_Native_seconds=k32["Native_Runtime"],
        K32_plus_K48_Native_seconds=k32["Native_Runtime"] + k48["Native_Runtime"],
        K48_requested_seconds=180, K48_solver_status=k48["solver_status"],
        K48_root_completed=k48["root_relaxation_completed"], Global_LB=k48["Global_LB"],
        certificate_wall_seconds=k48["wall_seconds"],
        certificate_wall_is_Optimize_wall=False, total_stage_Wall_seconds=None,
        bound_transferred_to_new_D0=False)
    proposals = [proposed_budget(s["stage"], s, 180. if s["stage"].startswith("M") else 120.) for s in stages]
    proposals.append(proposed_budget("K48", history, 180.))
    return dict(status="NEW_D0_M1_A2_M2_K48_NOT_RUN_NO_BUDGET_AUTHORIZATION", historical_stages=stages,
        historical_K48=history, bounded_followup_proposals=proposals,
        requested_followup_envelope_seconds=sum(x["proposed_ledger_envelope_seconds"] for x in proposals),
        total_is_success_runtime_prediction=False, prior_UB_LB_transferred=False,
        new_D0_UB=None, new_D0_Global_LB=None, new_D0_Global_Gap=None,
        stage_chain=["A1_FULL_gate", "M1", "A2", "M2", "Actual96", "Fresh_AC"],
        K48_separate_same_Source_Case_bound_gate=True, solver_calls_this_audit=0)


def authority_inventory(root):
    scopes = [Path(root) / "docs", Path("D:/v42_common_am_qos_integration_20261013/docs"),
        Path("D:/v42_integration_validation_20261013"), Path("D:/MobileESS_V42/docs")]
    names = []
    for scope in scopes:
        if scope.exists():
            listed = subprocess.run(["rg", "--files", str(scope)], capture_output=True, check=False)
            if listed.returncode not in (0, 1):
                raise RuntimeError("DATE_AUTHORITY_INVENTORY_SEARCH_FAILED:" + str(scope))
            names.extend(Path(x) for x in listed.stdout.decode("utf-8").splitlines()
                if any(token in Path(x).name.upper() for token in ("DDAY_INITIAL_STATE_FREEZE", "D0_INITIAL_STATE_AUTHORITY")))
    candidates = []
    for path in sorted(set(names)):
        doc = read(path)
        # A separate authority receipt must name its date; receipt PASS alone is
        # not a portable date authority. The approved May01 freeze is explicit.
        day = doc.get("day")
        approved = day == "2025-05-01" and path.name == "V42_MAY01_DDAY_INITIAL_STATE_FREEZE.json"
        candidates.append(dict(**record(path), day=day, authorized=approved,
            semantics="MAY01_APPROVED_MODEL_STATE_ONLY" if approved else "RECEIPT_NOT_PORTABLE_TO_ANOTHER_DATE"))
    days = []
    for day in ("2025-05-02", "2025-05-10", "2025-05-12"):
        cc4 = cc4_inventory(day, CC4_BASE / "MAY_CC4_BINDING.json", CC4_BASE / "CC4" / ("DAY_" + day.replace("-", "") + ".json"))
        initial = date_authority(day, candidates)
        original = Path("D:/MobileESS_V42/runtime/v42_may_campaign/candidate_20261009_implementation01/inputs/B2") / day
        repair = Path("D:/v42_may_joint_repair_campaign_20261013/inputs/B2") / day
        days.append(dict(day=day, CC4=cc4, D0_initial_authority=initial,
            source_input_inventory=[record(folder / "NATIVE_INPUT.json") for folder in (original, repair)],
            source_packet_presence_is_D0_authority=False,
            campaign_ready=False, blocker="DATE_SPECIFIC_D0_00_AUTHORITY_REQUIRED" if not initial["independent_day_ready"] else "MAY01_RELEASE_AND_DATE_SOLVE_GATES_REQUIRED"))
    return dict(audited_search_scopes=list(map(str, scopes)), authority_candidates=candidates, dates=days,
        May01_copy_forbidden=True, absence_claim_scope="ONLY_LISTED_SOURCE_TREES_AND_NAMES",
        all_31_day_authorities_certified=False,  independent_and_carry_modes_mixed=False,
        campaign_autostart_authorized=False, Native_calls=0)


def interface_review(root):
    old, source = archived(root, str(BASE / "SHARED_SOURCE_CASE_MANIFEST.json").replace("\\", "/"))
    physical, physical_source = archived(root, str(BASE / "UNIFIED_PHYSICAL_AUTHORITY.json").replace("\\", "/"))
    interface, interface_source = archived(root, str(BASE / "UNIFIED_INTERFACE_CONTRACT.json").replace("\\", "/"))
    integrity = read(Path(root) / "v42_final/runtime_bundle/INTEGRITY.json")
    assets = []
    for item in integrity["files"]:
        actual = record(Path(root) / "v42_final/runtime_bundle" / item["relative"])
        assets.append(dict(expected=item, actual=actual, PASS=actual["sha256"] == item["sha256"]))
    return dict(official_UB=["Adaptive Beam Search", "4-MESS Joint MILP", "Original FULL", "Incumbent Registry"],
        official_Global_LB="K48", MESS_count=physical["MESS_count"], nodes=physical["charging_site_count_expected"],
        slots=interface["slots"], slot_seconds=interface["slot_seconds"],
        STAY_and_MOVE_retained=True, signed_P_Q_and_SOC_retained=True,
        MESS_sign=interface["mess_P_Q"], net_load=interface["net_load"],
        IEEE=physical["IEEE"], installed_SVR=physical["installed_SVR"], RegControl=physical["existing_RegControl"],
        original_voltage_current_transformer_limits_preserved=True,
        intentional_time_shift_seconds=0, Checkpoint_Migration_enabled=False,
        historical_manifest=source, historical_bindings=old["bindings"], historical_anchor_status=old["anchor_status"],
        old_manifest_is_release_authorization=False,
        new_D0_requires_new_Source_Science_Case_Policy_binding=True,
        inherited_old_interface_module_and_active_comparison_not_promoted=True,
        physical_authority=physical_source, interface_contract=interface_source,
        runtime_provider=integrity["study_provider"], runtime_state_key=integrity["state_key"],
        runtime_base_model_retrained=integrity["base_model_retrained"], runtime_assets=assets,
        runtime_assets_PASS=all(x["PASS"] for x in assets), Runtime_CC4_refit_calls=0,
        new_MESS_formulation=False, new_Beam_scoring=False, compression_repeated=False,
        release_freeze_promoted=False, release_freeze_requires_May01_all_four_stages_Actual96_Fresh_PASS=True,
        Scheduling_or_InitialPlacement_sensitivity_added=False,
        sensitivity_scope="ACTUAL_PENDING_PRESITE_ONLY_LATEST_11224a62_INSTRUCTION",
        S1_DW_Mode384_SOC384_research_executed=False)


def run(root=ROOT, output=DEFAULT_OUTPUT):
    began = perf_counter()
    root, output = Path(root), Path(output)
    if output.exists() and any(output.iterdir()):
        raise ValueError("RELEASE_PRESERVATION_OUTPUT_EXISTS_USE_NEW_DIRECTORY")
    output.mkdir(parents=True, exist_ok=True)
    before = byte_preservation(root)
    if not before["PASS"]:
        raise ValueError("FROZEN_MESS_PROVIDER_SOURCE_BYTE_DRIFT")
    interface = interface_review(root)
    budget = budget_evidence(root)
    dates = authority_inventory(root)
    a1 = current_a1(root)
    fixed = fixed_plan_shape(root)
    after = byte_preservation(root)
    if before != after or not after["PASS"]:
        raise ValueError("RELEASE_AUDIT_MUTATED_FROZEN_SOURCE")
    report = dict(status="PASS_PRESERVATION_NOT_CAMPAIGN_CERTIFICATION", baseline=REFERENCE,
        **interface, byte_preservation_PASS=True, checked_files=before["checked_files"],
        canonical_318_681_ledger_byte_unchanged=True, Native_optimize_calls=0, presolve_calls=0,
        IIS_calls=0, model_build_calls=0, wall_seconds=perf_counter() - began,
        current_release_A1=a1, historical_fixed_MESS_interface=fixed,
        new_D0_M1_A2_M2_K48="NOT_RUN_NOT_AUTHORIZED", historical_UB_LB_transferred=False,
        campaign_verdict="CAMPAIGN_BLOCKED_WITH_EXACT_REASONS",
        blockers=(["NEW_D0_A1_FULL_GATE_NOT_ESTABLISHED"] if not a1["FULL_gate"] else []) + [
            "NEW_D0_M1_A2_M2_K48_SEPARATE_BUDGET_NOT_APPROVED",
            "NEW_D0_FULL96_ACTUAL_FRESH_AC_NOT_EXECUTED",
            "MAY02_MAY10_MAY12_DATE_SPECIFIC_APPROVED_D0_STATE_NOT_FOUND_IN_AUDITED_SCOPE",
            "31_DAY_LEDGER_RESUME_BUDGET_AND_MAY01_RELEASE_GATE_REQUIRED"],
        upstream_canary_status="SEE_AGENT_A_RELEASE_EVIDENCE_NOT_CERTIFIED_BY_THIS_SOURCE_AUDIT")
    for name, document in (("MESS_OFFICIAL_ALGORITHM_PRESERVATION.json", report),
        ("FROZEN_SOURCE_BYTE_PROOF.json", dict(before=before, after=after)),
        ("FOLLOWUP_BUDGET_EVIDENCE.json", budget), ("REPRESENTATIVE_DATE_SOURCE_INVENTORY.json", dates)):
        (output / name).write_text(json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    (output / "MESS_RELEASE_REVIEW_KO.md").write_text(
        "MESS 공식 Adaptive Beam → 4-MESS Joint MILP → Original FULL → Incumbent Registry와 K48을 보존했다. "
        "기준 490ff3ef7의 코어·Runtime/CC4·IEEE123/11 SVR/7 RegControl·물리 계약 및 기존 Native 원장 바이트를 비교했다. "
        "기존 Git checkout CRLF 필터를 명시하고 raw blob SHA와 실제 checkout SHA를 각각 기록했으며 원본 파일은 다시 쓰지 않았다. "
        "이번 감사는 모델 생성·solver 호출 0회다.\n\n"
        "추가 정정11224a62를 적용한다. Scheduling/기본 최초 배치는 기존 방식이며 민감도는 Actual PENDING Pre-site만의 정책이다. "
        "May01 A1→M1→A2→M2→Actual96→Fresh AC가 모두 통과하기 전 Release Freeze로 승격하지 않는다.\n\n"
        "Supervisor의 신규 D0 A1 P1은 1회, 50.622 Native초, Objective=Bound 0.64211779208034, Gap0, Original FULL PASS다. "
        "신규180초 원장의 남은 129.378초는 다른 실험의 실행 권한이 아니다.\n\n"
        "과거 PR223 M1/M2는 약 85.73/85.97 Native초, 146.05/148.47 Wall초로 반환됐다. "
        "그 실행은 과거 Case의 warm witness 및 FULL 검증이며 새 D0 성공·소요시간의 증명이 아니다. "
        "K48 과거 180.036초와 Bound도 옛 exact Case만의 자료다. 새 D0 M1/A2/M2/K48는 미실행·예산 미승인이다. "
        "제안은 M1 180, A2 120, M2 180, K48 180 단계별 누적 solve초와 각각 반환30+오버슈트30초이며, "
        "M1/M2 내부 4-Joint 단일 호출의 기존140초 상한을 유지하고 초기화·scoring도 단계 상한에 포함한다. P2/추가 호출은 자동 승인하지 않는다. "
        "합계 900초는 승인 요청 상한안이다. 새 D0 Wall/성공시간 예측은 미인증이다.\n\n"
        "May02·May10·May12의 원본 CC4 일별 행과 issue-time은 확인했다. 기존 모델 선택의 회고성·fit ingestion 미인증 한계는 남는다. "
        "조사한 원본 트리에서 대표 날짜별 공인 D0 00:00 초기 상태를 찾지 못했다. May01 상태를 복사하지 않는다. "
        "파일이 존재하는 날짜별 원래 Planning packet도 D0 초기 상태 승인으로 대체하지 않는다.\n\n"
        "CAMPAIGN_BLOCKED_WITH_EXACT_REASONS: 후속 단계별 예산, "
        "새 D0 M1/A2/M2·Actual96·Fresh AC, 대표일별 공인 초기 상태, 31일 계산 예산·Resume/Date Ledger gate가 필요하다. "
        "AIDC Canary의 실제 입장 및 계통 결과는 Agent A 자료로 별도 판정한다. 과거 UB/LB/Actual PASS는 이전하지 않는다.\n",
        encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = run(output=args.output)
    print(json.dumps({k: result[k] for k in ("status", "checked_files", "Native_optimize_calls", "wall_seconds")}, ensure_ascii=False))
