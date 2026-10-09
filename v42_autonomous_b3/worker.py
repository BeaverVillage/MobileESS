"""One real B3 date: verified B1 A1 -> M1 -> A2 -> M2 -> Actual/Fresh."""
from contextlib import contextmanager, nullcontext
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import replace
import hashlib
import gzip
import json
import msvcrt
import os
import pickle
import sys
import threading
import traceback

from v42_b3_joint.a_source import ASourceBridge
from v42_b3_joint.contracts import Authority, StageRequest, canonical, digest, require
from v42_b3_joint.grid_binding import InjectionAuthority
from v42_b3_joint.m_source import MSourceBridge
from v42_b3_joint.native_ledger import SourceStageLedger
from v42_b3_joint.operations_bridge import SourceOperationsBridge
from v42_b3_joint.source_coordinator import SourceCoordinator, output_document, verify_output
from v42_b3_joint.source_runtime import RealStageContext, SourceRegistry, source_input_identity, jsonable
from .admission import (read, record, checked, source_seal, execution_permit,
                        validate_request, publish_qualification)
from .reuse import B1A1ReuseBridge
from .ledger import CumulativeStageLedger
from .diagnostic import native_zero_diagnostic
from .accounting import collect_native_accounting
from v42_pr134_b1.common import replace_file
from v42_a_stage_domain_v2 import AUTHORITY as ORIGINAL_DOMAIN_AUTHORITY
from v42_a_stage_domain_v2.domain import physical_starts


def now():
    return datetime.now(timezone.utc).isoformat()


def atomic(path, document):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(canonical(document) + "\n", encoding="utf-8")
    replace_file(temporary, path)


@contextmanager
def singleton(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        if stream.tell() == 0:
            stream.write(b"0"); stream.flush()
        stream.seek(0)
        try:
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as error:
            raise PermissionError("B3_SINGLE_WORKER_ALREADY_OWNED") from error
        try:
            yield
        finally:
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)


def b1_origin(request):
    campaign = Path(request["campaign_root"]).resolve()
    day = request["day"]
    manifest_path = Path(request.get("campaign_manifest", campaign / "AUTONOMOUS_MANIFEST.json")).resolve()
    manifest = read(manifest_path) if manifest_path.is_file() else {}
    root = Path(request.get("b1_campaign_root", manifest.get("origin_campaign_root", campaign))).resolve()
    if manifest.get("B1_results"):
        final_path = checked(manifest["B1_results"]["B1/" + day], root)
    else:
        checkpoint_path = Path(request.get("b1_checkpoint", root / "CHECKPOINT_V18.json")).resolve()
        checkpoint = read(checkpoint_path)
        row = checkpoint["dates"]["B1/" + day]
        require(row.get("status") == "PASS" and row.get("result_SHA"), "B1_DAY_COMPLETION_AUTHORITY_REQUIRED")
        final_path = Path(row["result"]).resolve()
        require(final_path.is_relative_to(root) and record(final_path)["sha256"] == row["result_SHA"],
                "B1_FINAL_RESULT_AUTHORITY_SHA_DRIFT")
    final = read(final_path)
    require(final.get("PASS") is True and final.get("status") == "PASS" and
            final["identity"]["arm"] == "B1" and final["identity"]["day"] == day,
            "B1_DAY_COMPLETION_IDENTITY_DRIFT")
    # A successful recovery RESULT can seal A artifacts in an earlier output.
    # Follow its exact receipts, never infer the source from attempt names.
    sources = [receipt for receipt in final["files"]
               if Path(receipt["path"]).name == "A_NATIVE_SOURCE_FREEZE.json"]
    results = [receipt for receipt in final["files"] if Path(receipt["path"]).name == "A_RESULT.json"]
    require(len(sources) == len(results) == 1, "B1_FINAL_SEALED_A1_SOURCE_AXIS_REQUIRED")
    source_path, result_path = checked(sources[0], root), checked(results[0], root)
    b1 = source_path.parent
    require(result_path.parent == b1, "B1_SUCCESSFUL_ATTEMPT_OUTPUT_OWNERSHIP_DRIFT")
    origin_paths = (b1 / "A_PREPARE_RECEIPT.json", b1 / "STATIC/CAMPAIGN_INITIAL_STATE.pkl.gz",
                    b1 / "STATIC/DATA/DATA.pkl", b1 / "STATIC/DOMAIN" / day / "PHYSICAL_DOMAIN_CACHE.json",
                    b1 / "STATIC/DOMAIN" / day / "PHYSICAL_DOMAIN_CACHE.pkl.gz")
    for path in origin_paths:
        receipts = [receipt for receipt in final["files"] if Path(receipt["path"]).resolve() == path]
        require(len(receipts) == 1 and checked(receipts[0], root) == path,
                "B1_FINAL_ORIGINAL_PREPARATION_DOMAIN_RECEIPT_REQUIRED:" + str(path))
    frozen = read(source_path)
    require(frozen.get("PASS") is True and frozen.get("day") == day and frozen.get("arm") == "B1",
            "COMPLETED_B1_SAME_DAY_SOURCE_REQUIRED")
    inputs = Path(frozen["inputs"]["NATIVE_INPUT.json"]["path"]).resolve().parent
    for name in ("NATIVE_INPUT.json", "WINDOWS.json"):
        require(checked(frozen["inputs"][name]) == inputs / name, "B1_A1_INPUT_ORIGIN_PATH_DRIFT")
    # Both the accepted A stage and final B1 completion must be preserved.
    result = read(result_path)
    require(result.get("PASS") is True and result.get("accepted") is True,
            "B1_SAME_DAY_A1_NOT_COMPLETE")
    return b1, inputs


def original_domain_sha(b1, day):
    cache = read(b1 / "STATIC" / "DOMAIN" / day / "PHYSICAL_DOMAIN_CACHE.json")
    require(cache.get("PASS") is True and cache.get("day") == day and
            cache.get("scientific_candidates_removed") == 0,
            "B1_COMPLETE_ORIGINAL_PHYSICAL_DOMAIN_RECEIPT_REQUIRED")
    # The on-disk cache lists class representatives, while the scientific
    # authority covers every job. Expand exact saved class membership before
    # hashing; a representative-only digest is not the original domain SHA.
    with checked(cache["frozen_DATA"], b1).open("rb") as stream:
        data = pickle.load(stream)
    roster = {}
    for members in data[7]["classes"].values():
        representative_sha = cache["complete_domain_hashes"][members[0]]
        for uid in members:
            require(uid not in roster, "B1_COMPLETE_DOMAIN_DUPLICATE_JOB")
            roster[uid] = representative_sha
    require(set(roster) == set(data[1]) and cache["jobs"] == len(roster) and
            cache["representatives"] == len(data[7]["classes"]) and
            set(cache["complete_domain_hashes"]) == {members[0] for members in data[7]["classes"].values()},
            "B1_COMPLETE_DOMAIN_ORIGINAL_JOB_AXIS")
    actual = hashlib.sha256(json.dumps(roster, sort_keys=True, separators=(",", ":"),
                                      default=str, allow_nan=False).encode()).hexdigest()
    expected = data[7].get("physical_domain_hash")
    if expected is None:
        # The original DATA pickle predates physical-domain construction.
        # Its accepted Native-zero initial state independently seals the FULL
        # job-domain roster and the scientific hash added by that construction.
        preparation = read(b1 / "A_PREPARE_RECEIPT.json")
        require(preparation.get("PASS") is True and preparation.get("day") == day and
                preparation.get("arm") == "B1" and preparation.get("Native_calls") == 0,
                "B1_ORIGINAL_DOMAIN_PREPARATION_AUTHORITY_REQUIRED")
        with gzip.open(checked(preparation["state"], b1), "rb") as stream:
            initial = pickle.load(stream)
        # Original prepare_fast_active adds its authority marker and widens
        # allowed_starts using the unchanged physical_starts producer. Verify
        # precisely those original transformations, including all other fields.
        expected_bounds = {uid: replace(bound, allowed_starts=physical_starts(data[1][uid], bound, data[3].control_end))
                           for uid, bound in data[2].items()}
        initial_data = initial["data"]
        require(initial_data[0] == dict(data[0], aidc_domain_authority=ORIGINAL_DOMAIN_AUTHORITY) and
                jsonable(initial_data[1]) == jsonable(data[1]) and jsonable(initial_data[2]) == jsonable(expected_bounds) and
                jsonable(initial_data[3]) == jsonable(data[3]) and jsonable(initial_data[4]) == jsonable(data[4]) and
                initial_data[7]["classes"] == data[7]["classes"] and
                {uid: domain.sha for uid, domain in initial["domains"].items()} == roster,
                "B1_COMPLETE_DOMAIN_INITIAL_STATE_ROSTER_DRIFT")
        expected = initial["data"][7]["physical_domain_hash"]
    require(actual == expected, "B1_COMPLETE_DOMAIN_SCIENTIFIC_HASH_DRIFT")
    return actual


def setup(request, seal, pipeline):
    b1, inputs = b1_origin(request)
    input_identity = source_input_identity(inputs)
    bundle = input_identity["bundle"]
    ops = read(inputs / "OPERATIONS.json")
    electrical = read(bundle["electrical_certificate"]["path"])
    require(record(bundle["electrical_certificate"]["path"])["sha256"] ==
            bundle["electrical_certificate"]["sha256"], "ORIGINAL_ELECTRICAL_AUTHORITY_SHA_DRIFT")
    grid_inputs = electrical["input_identity"]["identity"]["inputs"]
    authority = Authority(day=request["day"], input_sha=input_identity["input_sha"],
        grid_sha=grid_inputs["OpenDSS_master"]["sha256"], pcc_mapping_sha=digest(list(bundle["capacities"])),
        physical_domain_sha=original_domain_sha(b1, request["day"]),
        forecast_sha=digest(ops["forecast_inputs"]),
        runtime_sha=digest({key: bundle.get(key) for key in
            ("runtime_provider", "runtime_provider_ready", "RUNTIME_PROVIDER_READY", "C0_Q50", "C0_Q90",
             "CC4_reserve_GPU", "runtime_reserve_gamma", "runtime_survival_kernel", "C0_binding")}),
        source_sha=seal["source_sha"],
        planning_cutoff=ops["forecast_inputs"]["AEMO"]["cutoff_fixed_aest"],
        forecast_available_at=ops["forecast_inputs"]["AEMO"]["demand_issue"],
        pcc_ids=tuple(bundle["capacities"]), mess_ids=tuple(bundle["initial_MESS_sites"]))
    registry = SourceRegistry(request["code_root"], seal["files"])
    # Original constructors are resolved only within the admitted source scope.
    provisional = RealStageContext(StageRequest("A1", authority), inputs, pipeline / "A1",
        canonical(bundle), registry, object(), {}, seal["source_sha"], request["run_id"])
    with registry.execution_scope(provisional):
        load = registry.callable("v42_temporal/native.py", "load_power")
        certificate, _, _, _ = load(bundle)
        original = registry.resolve("v42_may01.prepare")
        coefficients = registry.callable("v42_pr134_b1/native.py", "original_coefficients_for_day")(
            original, certificate, request["day"])
        validation = registry.callable("v42_may_campaign_native90/bindings.py", "check_coefficients")(
            request["day"], certificate, coefficients)
        require(validation.get("PASS") is True, "B3_ORIGINAL_COEFFICIENT_AUTHORITY_FAILED")
    names = list(coefficients[0].control_names)
    validity = {"grid_sha": authority.grid_sha, "pcc_mapping_sha": authority.pcc_mapping_sha,
        "producer_source_sha": authority.source_sha, "units": "kW_kvar",
        "sign_convention": "ORIGINAL_NATIVE_CONTROL_SIGN", "sensitivity_scope": "ORIGINAL_FULL_CONTROL_DOMAIN",
        "phase_mapping_sha": digest({"control_names": names,
                                     "coefficients": [c.coefficient_sha256 for c in coefficients]}),
        "verifier_source_sha": seal["files"]["v42_may_campaign_native90/bindings.py"],
        "coefficient_sha256_by_slot": [c.coefficient_sha256 for c in coefficients], "control_names": names}
    grid = InjectionAuthority(registry, authority, validity_json=canonical(validity))
    def factory(stage_request, packets, output):
        return RealStageContext(stage_request, inputs, output, canonical(bundle), registry, grid,
                                packets, seal["source_sha"], request["run_id"])
    return authority, factory, b1, inputs


def realized_inputs(operations, frozen):
    # Read source exogenous observations only after immutable Planning freeze.
    import pandas as pd
    context, registry = operations.context, operations.registry
    with registry.execution_scope(context):
        ops = read(context.input_folder / "OPERATIONS.json")
        provenance = read(Path(ops["current_day_folder"]) / "SOURCE_PROVENANCE.json")
        resolver = registry.callable("v42_capacity/common.py", "resolve")
        actual_path = resolver(provenance["daily_sources"]["aemo_actual.parquet"])
        frame = pd.read_parquet(actual_path)
        require(len(frame) == 96, "B3_ORIGINAL_ACTUAL_96_SLOTS_REQUIRED")
        return {"load": frame.demand_mw.tolist(), "pv": frame.rooftop_pv_mw.tolist(),
                "aidc_state": operations.expected_aidc_state(frozen)}


def no_active_b2(request):
    import psutil
    for process in psutil.process_iter(("pid", "cmdline")):
        try:
            command = process.info["cmdline"] or []
            text = " ".join(command)
            if (".worker" in text and "v42_" in text and "B2" in text and
                    str(Path(request["campaign_root"])).lower() in text.lower()):
                raise PermissionError("B3_START_REQUIRES_B2_SWEEP_WORKERS_IDLE:" + str(process.info["pid"]))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue


def run(request_path):
    request_path = Path(request_path).resolve()
    request = read(request_path)
    code_root, envelope = validate_request(request)
    require(code_root == Path(__file__).resolve().parents[1], "B3_WORKER_CHECKOUT_IDENTITY_DRIFT")
    envelope.mkdir(parents=True, exist_ok=True)
    seal = read(request["source_seal"]) if request.get("source_seal") else source_seal(code_root)
    pipeline = envelope / "PIPELINE"
    identity = {"run_id": request["run_id"], "arm": "B3", "day": request["day"],
                "attempt_id": request["attempt_id"], "worker_slot": 1, "source_SHA": seal["source_sha"]}
    heartbeat = {"identity": identity, "worker": {"PID": os.getpid()}, "stage": "ADMISSION", "phase": "SOURCE_ADMISSION"}
    heartbeat_lock = threading.Lock()
    stopped = threading.Event()
    def progress(value):
        with heartbeat_lock:
            heartbeat.update(jsonable(value))
            phase = str(value.get("phase", ""))
            if value.get("stage"):
                heartbeat["stage"] = value["stage"]
            elif phase.startswith("A1"):
                heartbeat["stage"] = "A1"
            heartbeat["timestamp_UTC"] = now()
            atomic(envelope / "HEARTBEAT.json", heartbeat)
            if request.get("progress") and Path(request["progress"]).resolve() != envelope / "HEARTBEAT.json":
                atomic(request["progress"], heartbeat)
    def ticker():
        while not stopped.wait(15):
            progress({})
    thread = threading.Thread(target=ticker, daemon=True)
    progress({})
    thread.start()
    result = {"identity": identity, "started_UTC": now(), "worker_PID": os.getpid(),
              "source_sha": seal["source_sha"], "request": record(request_path),
              "status": "FAIL", "PASS": False}
    try:
        # One campaign-wide OS lease covers the entire date pipeline.
        with singleton(Path(request["campaign_root"]) / "autonomous" / "B3_SINGLE_WORKER.lock"), execution_permit(request, seal), (native_zero_diagnostic() if request.get("prepare_only") is True else nullcontext()):
            if request.get("prepare_only") is not True:
                no_active_b2(request)
            atomic(envelope / "B3_SOURCE_ADMISSION.json", {"PASS": True, "identity": identity,
                "source_sha": seal["source_sha"], "source_seal": seal,
                "qualification_mode": "REAL_CANARY" if request.get("canary") else "QUALIFIED_PRODUCTION",
                "worker_count": 1, "Native_calls": 0})
            authority, context_factory, b1, inputs = setup(request, seal, pipeline)
            atomic(envelope / "B3_INPUT_AUTHORITY.json", authority.to_dict())
            reuse = B1A1ReuseBridge(b1)
            if request.get("prepare_only") is True:
                context = context_factory(StageRequest("A1", authority), {}, pipeline / "A1")
                ledger = CumulativeStageLedger(context, previous_attempts=request.get("previous_attempts", ()), progress=progress)
                output = reuse.execute(context, ledger, progress)
                verify_output(context, output, reuse, ledger)
                atomic(context.output / "B3_SOURCE_STAGE_OUTPUT.json", output_document(output))
                require(ledger.receipt()["native_call_count"] == 0 and ledger.used() == 0,
                        "NATIVE_ZERO_DIAGNOSTIC_LEDGER_REQUIRED")
                guard_path = envelope / "NATIVE_ZERO_DIAGNOSTIC_GUARD.json"
                atomic(guard_path, {"PASS": True, "Native_calls": 0, "Native_Runtime": 0,
                    "ledger": record(ledger.path), "original_native_zero_scope": True,
                    "source_native_admission_blocked": True,
                    "full_production_qualification": False})
                result.update(status="NATIVE_ZERO_A1_REUSE_VERIFIED", PASS=True, Native_calls=0,
                              A1_reuse=record(context.output / "B1_A1_VERIFIED_REUSE.json"),
                              native_zero_guard=record(guard_path), production_qualified=False)
            else:
                coordinator = SourceCoordinator(pipeline, context_factory, ASourceBridge(), MSourceBridge(),
                    a1_bridge=reuse, ledger_factory=lambda context: CumulativeStageLedger(context,
                        previous_attempts=request.get("previous_attempts", ()),
                        progress=lambda value: progress(dict(value, stage=context.request.stage))))
                outcome = coordinator.run(authority, operations_factory=SourceOperationsBridge,
                                          realized_inputs=realized_inputs, progress=progress)
                require(outcome["status"] == "COMPLETE" and outcome["validation"]["PASS"] is True,
                        "B3_FINAL_INDEPENDENT_VALIDATION_FAILED")
                stages = {}
                for stage, output in coordinator.outputs.items():
                    receipt = json.loads(output.ledger_receipt)
                    bounds = output.global_evidence
                    stages[stage] = {"result_sha": output.sha, "original_model_sha": output.model_sha,
                        "exact_LB": bounds["exact_LB"], "exact_UB": bounds["exact_UB"],
                        "native_seconds": receipt["measured_native_runtime"], "native_calls": receipt["native_call_count"],
                        "original_integer_physical_verified": True, "independent_global_verified": True}
                fresh_path = pipeline / "M2" / "OPERATIONS" / "FRESH" / "FRESH_RESULT.json"
                result.update(status="PASS", PASS=True, stages=stages,
                    native_seconds=sum(value["native_seconds"] for value in stages.values()),
                    A1_reuse=record(pipeline / "A1" / "B1_A1_VERIFIED_REUSE.json"),
                    actual=record(pipeline / "B3_SOURCE_ACTUAL_RESULT.json"),
                    validation=record(pipeline / "B3_SOURCE_VALIDATION.json"), Fresh=record(fresh_path),
                    checkpoint=record(pipeline / "B3_SOURCE_CHECKPOINT.json"))
                result["evaluation"] = {"Fresh": {"folder": str(fresh_path.parent),
                    "files": [record(path) for path in (fresh_path,
                        fresh_path.parent / "fresh" / "OPENDSS_PHASE_ARRAYS.npz") if path.is_file()]}}
                result["files"] = result["evaluation"]["Fresh"]["files"]
                result["Native_Runtime"] = result["native_seconds"]
                if request.get("canary") is True:
                    result["production_qualification"] = publish_qualification(pipeline, seal["source_sha"],
                        request.get("qualification_output", str(Path(request["campaign_root"]) / "autonomous" / "B3_PRODUCTION_QUALIFICATION.json")))
    except Exception as error:
        result.update(failure_class=type(error).__name__, reason=str(error), traceback=traceback.format_exc())
    finally:
        stopped.set()
        thread.join(timeout=2)
        result.update(collect_native_accounting(pipeline, identity, request.get("previous_attempts", ())))
        if result["PASS"] is not True:
            result["failed_stage"] = heartbeat.get("stage", "ADMISSION")
            atomic(envelope / "FAILURE.json", result)
        result["completed_UTC"] = now()
        atomic(envelope / "RESULT.json", result)
        if request.get("result") and Path(request["result"]).resolve() != envelope / "RESULT.json":
            atomic(request["result"], result)
        progress({"phase": result["status"], "state": result["status"]})
    return result


if __name__ == "__main__":
    outcome = run(sys.argv[1])
    print(canonical({"status": outcome["status"], "PASS": outcome["PASS"], "reason": outcome.get("reason")}))
    raise SystemExit(0 if outcome["PASS"] else 1)
