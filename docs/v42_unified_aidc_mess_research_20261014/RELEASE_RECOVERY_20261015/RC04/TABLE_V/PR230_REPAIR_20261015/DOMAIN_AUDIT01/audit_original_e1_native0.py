"""Reissue original public E1 receipts and audit D0 descriptors without geometry.

Run from any directory with Python 3.11. The default output directory is this
file's directory. --output NEW_DIRECTORY permits a reproducible second run.
Every output is exclusive-created. No model, optimizer, AC or Actual is entered.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import importlib.abc
import importlib.machinery
import json
import math
from pathlib import Path
import sys
import time
import types

HERE = Path(__file__).resolve().parent
REPO = next(p for p in HERE.parents if (p / "v42_integration").is_dir())
TABLE = HERE.parents[1]
EXEC = TABLE / "EXECUTION02"
SLOT, OFFSET, END = 900, 24, 120


class RejectSolverImport(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in {"gurobipy", "highspy", "opendssdirect", "dss"}:
            raise RuntimeError("NATIVE0_AUDIT_FORBIDS_SOLVER_OR_AC_IMPORT:" + fullname)
        return None


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def record(path):
    path = Path(path)
    return dict(path=str(path.resolve()), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                bytes=path.stat().st_size)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True,
        separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def canonical(value):
    if isinstance(value, dict):
        if all(isinstance(k, str) for k in value):
            return {k: canonical(v) for k, v in value.items()}
        return [[canonical(k), canonical(v)] for k, v in sorted(value.items(), key=lambda kv: repr(kv[0]))]
    if isinstance(value, (tuple, list)):
        return [canonical(v) for v in value]
    return value


def fingerprint(data):
    # Independent serialization; do not call the production input_fingerprint.
    return digest(canonical(dict(bundle=data[0], jobs={u: asdict(j) for u, j in data[1].items()},
        bounds={u: asdict(b) for u, b in data[2].items()}, resources=asdict(data[3]),
        raw=data[4], prep=data[7])))


def checked(receipt):
    actual = record(receipt["path"])
    assert actual["sha256"] == receipt["sha256"] and actual["bytes"] == receipt["bytes"], receipt
    return read(receipt["path"])


def write_new(path, payload):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(payload)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=HERE)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    report_path = args.output / "DOMAIN_AUDIT.json"
    uid_path = args.output / "UID_DOMAIN_AUDIT.json"
    ko_path = args.output / "KO.md"
    assert not any(p.exists() for p in (report_path, uid_path, ko_path)), "APPEND_ONLY_OUTPUT_ALREADY_EXISTS"
    began = time.perf_counter()
    sys.meta_path.insert(0, RejectSolverImport())
    sys.path.insert(0, str(REPO))
    # The package initializer imports gurobipy. Only the unchanged pure service
    # adapter is needed: expose its real source directory as a namespace package
    # so the numerical audit does not import or construct a solver environment.
    native_namespace = types.ModuleType("v42_native")
    native_namespace.__path__ = [str(REPO / "v42_native")]
    native_namespace.__spec__ = importlib.machinery.ModuleSpec("v42_native", loader=None, is_package=True)
    sys.modules["v42_native"] = native_namespace
    from v42_integration.actual_validation import load_stats
    from v42_integration.d0_a_planning import compile_d0_known_data
    from v42_integration.experimental_qos import ExperimentalQoSProvider, FROZEN_SEED
    from v42_integration.qos import ObservedJob, QoSWindowProvider
    from v42_integration.table_v_flex_planning import compile_flex_descriptors, verify_native_migration_authority
    from v42_job_capability import checkpoint_records
    from v42_native.service import service_identity

    basic_dir = EXEC / "INPUTS/BASIC"
    flex_dir = EXEC / "INPUTS/FULL_FLEX"
    basic = read(basic_dir / "D0_CASE_MANIFEST.json")
    manifest = read(flex_dir / "TABLE_V_FLEX_CASE_MANIFEST.json")
    policy = read(flex_dir / "TABLE_V_FLEXIBILITY_POLICY_FREEZE.json")
    saved_audit = read(flex_dir / "TABLE_V_FLEX_INPUT_AUDIT.json")
    failed = read(TABLE / "EXECUTION01/INPUTS/FULL_FLEX/TABLE_V_FLEXIBILITY_POLICY_FREEZE.json")
    previous = read(TABLE / "CAUSE_AUDIT01/ORIGINAL_RECEIPT_DOMAIN_RESTORATION.json")
    certificate = read(EXEC / "B1/A1/NATIVE0_FULL_FLEX_MODEL_CERTIFICATE.json")
    result = read(EXEC / "B1/A1/P1_ONLY_RESULT.json")
    paths = sorted(set(list((EXEC / "INPUTS").rglob("*.json")) + [
        TABLE / "EXECUTION01/INPUTS/FULL_FLEX/TABLE_V_FLEXIBILITY_POLICY_FREEZE.json",
        TABLE / "CAUSE_AUDIT01/ORIGINAL_RECEIPT_DOMAIN_RESTORATION.json",
        EXEC / "B1/A1/NATIVE0_FULL_FLEX_MODEL_CERTIFICATE.json", EXEC / "B1/A1/P1_ONLY_RESULT.json",
        Path(basic["initial_record"]["path"]), Path(basic["source_native_record"]["path"]),
        Path(policy["strict_stats_record"]["path"])]))
    before = [record(p) for p in paths]
    state = checked(basic["initial_record"])
    assert digest({k: state[k] for k in state["initial_state_payload_keys"]}) == state["common_initial_state_sha"]
    assert digest({k: v for k, v in state.items() if k != "freeze_sha"}) == state["freeze_sha"]
    native = checked(basic["source_native_record"])
    for merge in basic["source_physical_merge"]:
        projection = checked(merge["source_record"])
        assert digest(native[merge["field"]]) == merge["original_value_sha"]
        assert digest(projection[merge["field"]]) == merge["current_value_sha"]
        native[merge["field"]] = deepcopy(projection[merge["field"]])
        native["D0_current_physical_projection"] = deepcopy(merge["source_record"])
    compiled = compile_d0_known_data(basic["initial_record"], source_bundle=native,
        backlog_contract=basic["backlog_contract"], source_identity=basic["identity"],
        cc4_receipt=basic["forecast_receipt"])
    data, classification, basic_audit, receipts, windows = compiled
    assert fingerprint(data) == read(basic_dir / "D0_PLANNING_INPUT_AUDIT.json")["a_input_sha"], (fingerprint(data), basic_audit["a_input_sha"], read(basic_dir / "D0_PLANNING_INPUT_AUDIT.json")["a_input_sha"])
    base = dict(state=state, manifest=basic, data=data, windows=windows,
        forecast=basic["forecast_receipt"], input_audit=basic_audit)
    stats = load_stats(policy["strict_stats_record"]["path"])
    assert stats.sha == policy["strict_stats_sha"]
    now = compile_flex_descriptors(base, strict_stats=stats,
        source_records=manifest["science_derivation"]["source_records"])
    assert not now["issues"]
    assert now["identity"] == manifest["identity"] == previous["repair"]["new_identity"]
    assert fingerprint(now["data"]) == manifest["full_flex_input_sha"] == saved_audit["a_input_sha"]
    assert digest(now["science_derivation"]) == manifest["identity"]["science_sha"]
    assert digest(now["case_derivation"]) == manifest["identity"]["case_sha"]
    strict = QoSWindowProvider(stats, case_sha=policy["case_sha"], provider_sha=policy["provider_sha"])
    issuer = ExperimentalQoSProvider(strict, scenario="E1", participation="FLEX30",
        case_sha=policy["case_sha"], seed=policy["spec"]["seed"])
    assert issuer.stats.sha == policy["stats_sha"] and policy["spec"]["seed"] == FROZEN_SEED
    initial = {r["uid"]: r for key in ("running", "pending") for r in state[key]}
    rows = {r["uid"]: r for r in policy["domain_mask"]}
    old_rows = {r["uid"]: r for r in failed["domain_mask"]}
    uid_rows, restored, counter = [], [], Counter()
    begin = state["begin_epoch_seconds"]
    resources = now["data"][3]
    for uid, source in policy["known_observed_records"].items():
        job = ObservedJob(**dict(source, representation_starts_seconds=tuple(source["representation_starts_seconds"])))
        context = policy["known_source_contexts"][uid]
        issuer.register_observed(uid, **context)
        receipt = issuer.issue(job)
        assert canonical(dict(receipt.to_dict(), receipt_sha=digest(receipt.to_dict()))) == policy["known_issued_receipts"][uid]
        # Separate arithmetic from the provider implementation and the saved mask.
        membership_sha = digest(dict(rule="UID_EPISODE_SHA256_THRESHOLD_V1", seed=FROZEN_SEED,
            uid=uid, episode_id=context["episode_id"]))
        member = int(membership_sha, 16) * 100 < 30 * 2**256
        assert member is receipt.participant and membership_sha == receipt.membership_sha
        budget = (3600 if receipt.model_metadata["qos"] == "standby" else 1800) if member and receipt.eligible_for_contract else 0
        assert budget == receipt.budget_seconds
        lower = max(job.submit_seconds, job.event_seconds,
            job.release_seconds if job.release_seconds is not None else -math.inf,
            job.hard_earliest_start_seconds if job.hard_earliest_start_seconds is not None else -math.inf)
        upper = min(job.reference_start_seconds + budget,
            job.hard_latest_start_seconds if job.hard_latest_start_seconds is not None else math.inf)
        if job.completion_deadline_seconds is not None:
            upper = min(upper, job.completion_deadline_seconds - job.nominal_service_seconds)
        arithmetic_starts = tuple(sorted(set(t for t in job.representation_starts_seconds if lower <= t <= upper)))
        assert arithmetic_starts == receipt.allowed_starts_seconds
        assert all(t >= begin for t in arithmetic_starts)
        counter["all_observed_receipts"] += 1
        if uid not in rows:
            assert initial[uid] in state["running"] and initial[uid]["q50"] <= initial[uid]["elapsed_compute_seconds"]
            continue
        d, native_job, bound, raw = rows[uid], now["data"][1][uid], now["data"][2][uid], now["data"][4][uid]
        expected = (OFFSET,) if job.state == "RUNNING" else tuple(
            OFFSET + int((t - begin) / SLOT) for t in arithmetic_starts if begin <= t < begin + 86400)
        assert all(OFFSET <= t < END for t in expected)
        assert expected == native_job.qos_allowed_starts == now["windows"][uid] == tuple(d["allowed_native_starts"])
        assert list(native_job.initial_sites) == d["initial_sites"]
        eligible = member and receipt.eligible_for_contract
        assert native_job.checkpoint_authorized == eligible == d["checkpoint_authorized"]
        assert native_job.initial_sites == (tuple(initial[uid]["compatible_sites"]) if job.state == "PENDING" or eligible else (initial[uid]["site"],))
        assert all(s in initial[uid]["compatible_sites"] and native_job.gpu <= resources.capacities[s]
            and native_job.gpu <= max(resources.rack_limits[s]) for s in native_job.initial_sites)
        remaining = max(0, initial[uid]["q50"] - initial[uid]["elapsed_compute_seconds"]) if job.state == "RUNNING" else initial[uid]["q50"]
        assert native_job.service_slots == math.ceil(remaining / SLOT) == d["full_service_slots"]
        assert raw["exact_service_seconds"] == remaining and native_job.elapsed_seconds == initial[uid]["elapsed_compute_seconds"]
        assert raw["risk_nominal_completion_issue_slot"] - raw["reference_end"] == data[4][uid]["risk_nominal_completion_issue_slot"] - data[4][uid]["reference_end"]
        limit = max(max(expected), END) + native_job.service_slots
        if job.completion_deadline_seconds is not None:
            limit = min(limit, math.floor((job.completion_deadline_seconds - (begin - OFFSET * SLOT)) / SLOT))
        assert bound.latest_completion == limit
        assert all(s + native_job.service_slots <= limit for s in expected)
        # Exact service decomposition covers every authorized STAY start, including post-D0 carry.
        carry = [service_identity(remaining, native_job.gpu,
            ((native_job.initial_sites[0], s, s + native_job.service_slots),), H=END)["tail_compute_seconds"] for s in expected]
        cp = checkpoint_records(native_job, expected[0], min(expected[0] + native_job.service_slots, END))
        for control, physical in cp:
            elapsed_at_checkpoint = native_job.elapsed_seconds + physical - native_job.event * SLOT if job.state == "RUNNING" else physical - expected[0] * SLOT
            assert elapsed_at_checkpoint > 0 and abs(elapsed_at_checkpoint / 1800 - round(elapsed_at_checkpoint / 1800)) < 1e-9
            assert control == math.ceil(physical / SLOT)
        old_starts = old_rows[uid]["allowed_native_starts"]
        assert set(old_starts).issubset(expected)
        added = sorted(set(expected) - set(old_starts))
        if added:
            assert job.state == "PENDING" and all(s < d["reference_native_slot"] for s in added)
            restored.append(dict(uid=uid, old=old_starts, restored=list(expected), added=added, participant=member))
            counter["restored_UIDs"] += 1
            counter["restored_starts"] += len(added)
            counter["restored_MEMBER" if member else "restored_NONMEMBER"] += 1
        counter[job.state + "_positive_remaining"] += 1
        counter["checkpoint_UIDs"] += int(eligible)
        counter["positive_remaining_UIDs"] += 1
        counter["authorized_start_slots"] += len(expected)
        counter["UIDs_with_post_D0_STAY_carry"] += int(max(carry) > 0)
        uid_rows.append(dict(uid=uid, state=job.state, participant=member, budget_seconds=budget,
            receipt_sha=digest(receipt.to_dict()), allowed_native_starts=list(expected),
            allowed_D0_seconds=[begin + (s - OFFSET) * SLOT for s in expected],
            source_hard_contract=receipt.hard_contract, initial_sites=list(native_job.initial_sites),
            checkpoint_authorized=eligible, physical_checkpoint_records_at_earliest_start=len(cp),
            service_slots=native_job.service_slots, exact_service_seconds=remaining,
            minimum_STAY_carry_seconds=min(carry), maximum_STAY_carry_seconds=max(carry),
            latest_completion_native_slot=limit))
    assert counter["restored_UIDs"] == 992 and counter["restored_starts"] == 3667
    assert counter["restored_MEMBER"] == 281 and counter["restored_NONMEMBER"] == 711
    assert counter["positive_remaining_UIDs"] == 1555 and counter["checkpoint_UIDs"] == 454
    expired = [r for r in state["running"] if r["q50"] <= r["elapsed_compute_seconds"]]
    hold = Counter()
    for row in expired:
        hold[row["site"], OFFSET] += row["gpu"]
    assert len(expired) == 69 and sum(hold.values()) == 187
    assert dict(hold) == resources.fixed_gpu == data[3].fixed_gpu
    assert all(key[1] == OFFSET for key in hold)
    assert resources.capacities == state["capacities"] and sum(resources.capacities.values()) == 780
    assert resources.fixed_wan == data[3].fixed_wan and resources.fixed_transfers == data[3].fixed_transfers
    migration = verify_native_migration_authority(resources, policy["migration_authority"])
    assert migration == policy["migration_numeric_source_check"]
    assert asdict(resources) == asdict(data[3])
    assert policy["spec"]["R2"] == "HOLD" and policy["spec"]["P2_calls"] == 0
    assert digest(now["audit_rows"]) == digest(policy["domain_mask"])
    frozen_source_comparison = []
    for expected in manifest["source_freeze"]["files"]:
        current = record(expected["path"])
        frozen_source_comparison.append(dict(expected=expected, current=current, exact_bytes_equal=current == expected))
    assert certificate["source_identity"] == result["source_identity"] == manifest["identity"]
    assert certificate["native_binding"] == result["native_binding"]
    assert certificate["rows"] == certificate["native_binding"]["rows"]
    assert result["D0_input_sha"] == fingerprint(now["data"])
    assert before == [record(p) for p in paths], "EXISTING_RAW_CHANGED_DURING_AUDIT"
    assert not any(n in sys.modules for n in ("gurobipy", "highspy", "opendssdirect", "dss"))
    uid_payload = dict(schema="PR230_INDEPENDENT_E1_UID_DESCRIPTOR_AUDIT_V1", rows=uid_rows, restoration=restored)
    write_new(uid_path, json.dumps(uid_payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    descriptor_sha = digest(canonical(dict(jobs={u: asdict(j) for u, j in now["data"][1].items()},
        bounds={u: asdict(b) for u, b in now["data"][2].items()}, resources=asdict(resources),
        windows=now["windows"], receipt_ledger=issuer.export_ledger())))
    report = dict(schema="PR230_ORIGINAL_E1_D0_INDEPENDENT_NATIVE0_AUDIT_V1", status="PASS_DESCRIPTOR_AUDIT",
        created_utc=datetime.now(timezone.utc).isoformat(), identity=manifest["identity"], counts=dict(counter),
        original_E1_typed_issuer_reissued_exactly=True, independent_membership_window_budget_arithmetic_exact=True,
        saved_mask_and_original_receipts_equal=True, no_D0_past_authority=True,
        D0_axis=dict(begin_epoch_seconds=begin, native_offset=OFFSET,
            native_slot_zero_seconds=begin-OFFSET*SLOT, end_exclusive_native_slot=END,
            formula="begin+(native_slot-24)*900", original_timezone="UTC+10_SOURCE_D0"),
        Release_Deadline_membership_budget_compatibility_prestart_checkpoint_descriptors="PASS",
        GPU_rack_WAN_numeric_authority="PASS_DESCRIPTOR_AND_ORIGINAL_PACKET",
        full_service_carry_exact_STAY_identity="PASS_ALL_AUTHORIZED_STARTS",
        expired_running_physical_hold=dict(UIDs=len(expired), GPU=sum(hold.values()), native_slot=OFFSET,
            by_site=canonical(dict(hold)), semantics="CURRENT_D0_SLOT_HOLD_OBSERVED_COMPLETION_REQUIRED_FOR_ACTUAL_RELEASE"),
        independent_SHA=dict(BASIC_typed_input_sha=fingerprint(data), FULL_FLEX_typed_input_sha=fingerprint(now["data"]),
            receipt_ledger_sha=digest(issuer.export_ledger()), UID_descriptor_domain_sha=descriptor_sha,
            UID_descriptor_domain_sha_scope="UNMATERIALIZED_TYPED_DESCRIPTORS_NOT_NATIVE_COLUMN_GEOMETRY"),
        saved_geometry_evidence=dict(saved_native_binding=certificate["native_binding"],
            stored_certificate_and_result_binding_equal=True, geometry_SHA_independently_recomputed=False,
            matrix_SHA_independently_recomputed=False, objective_SHA=result.get("objective_sha"),
            objective_SHA_independently_recomputed=False,
            status="STORED_BINDING_CONSISTENT_GEOMETRY_AND_OBJECTIVE_NOT_INDEPENDENTLY_CERTIFIED",
            reason="No persisted matrix/column/objective arrays; audit authorization forbids model or geometry materialization."),
        policy=dict(R1="PRESERVED", R2="HOLD", P2_calls=0, source_hard_contracts_extended=False),
        frozen_source_comparison=frozen_source_comparison, old_inputs_and_Raw_unchanged=True,
        read_input_records=before, audit_source=record(Path(__file__)), UID_evidence=record(uid_path),
        operations=dict(Native_calls=0, model_builds=0, geometry_materializations=0, optimize=0,
            Actual_calls=0, AC_calls=0, private_future_reads=0, solver_import_guard="ENFORCED",
            native_package_initializer="BYPASSED_FOR_UNCHANGED_PURE_SERVICE_MODULE_ONLY"),
        limitations=["Descriptor authorization and exact STAY service accounting do not prove coupled feasibility.",
            "Checkpoint records/authority and WAN scalars are checked; millions of migration options are not materialized.",
            "Existing Matrix/Domain binding equality is evidence consistency, not an independent geometry hash check.",
            "No Original FULL point replay, DW Phase I/P1 or Global LB/UB/gap is certified by this audit."],
        wall_seconds=time.perf_counter()-began)
    write_new(report_path, json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    changed = sum(not r["exact_bytes_equal"] for r in frozen_source_comparison)
    write_new(ko_path, "# PR230 E1/D0 독립 Native0 도메인 감사\n\n"
        "원본 typed E1 발급기 재발급과 별도 membership·window·budget 산술이 저장 receipts와 모두 일치했다. "
        "992개 PENDING UID의 3,667개 시작 슬롯 복원을 독립 확인했다(MEMBER 281 / NONMEMBER 711). "
        "양수 잔여서비스 1,555 UID, checkpoint 권한 454 UID와 D0 이전 시작 금지, 원본 hard release/deadline, "
        "호환 site·GPU·rack·WAN 수치, 모든 STAY 시작의 전체 서비스와 carry를 검사했다. "
        "Q50 만료 RUNNING 69 UID / 187 GPU의 D0 현재 슬롯 물리 점유도 보존됐다.\n\n"
        "독립 descriptor SHA는 실제 Native matrix/column geometry SHA와 구별한다. 기존 certificate/result의 "
        "Matrix·Domain binding은 서로 일치하지만, matrix/column/objective 배열이 보존되지 않아 이번 Native0 감사에서는 "
        "실제 geometry 및 Objective SHA를 독립 재계산하지 않았다. FULL-feasible, DW 하한, 정수해 또는 Global Gap 인증이 아니다.\n\n"
        f"원본 frozen Source와 현재 작업 소스의 byte 차이 {changed}건은 JSON에 개별 기록했다. "
        "기존 입력·Raw는 변경하지 않았으며 Native/model build/geometry materialization/Actual/AC 호출은 모두 0회다. "
        "R1 유지, R2 HOLD, P2 0회를 확인했다.\n\n"
        "재현: `python audit_original_e1_native0.py --output NEW_DIRECTORY`\n")
    print(json.dumps(dict(status=report["status"], counts=dict(counter), descriptor_sha=descriptor_sha,
        frozen_source_byte_differences=changed, Native_calls=0, model_builds=0, output=str(report_path)), ensure_ascii=False))


if __name__ == "__main__":
    main()
