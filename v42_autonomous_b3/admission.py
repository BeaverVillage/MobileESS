"""Evidence-bound canary admission and explicit production promotion.

Each May date can run as a scoped real canary until one date completes all
source-matched stages and Actual/Fresh validation. Failed dates do not promote
production or prevent the next independent date's canary execution.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
import hashlib
import json
import math
import re

from v42_b3_joint.contracts import canonical, digest, require, require_sha
from v42_b3_joint.source_coordinator import output_from_document
from v42_b3_joint.policy import COMMON_MESS_VERSION, native_limit
from v42_b3_joint.m_acceptance import verify_m_acceptance
from v42_pr134_b1.common import replace_file

_permit = ContextVar("v42_b3_qualified_execution_permit", default=None)
_native_zero = ContextVar("v42_b3_native_zero_diagnostic", default=False)
DAYS = tuple(f"2025-05-{i:02d}" for i in range(1, 32))


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def record(path):
    path = Path(path).resolve()
    with path.open("rb") as stream:
        sha = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": sha}


def checked(receipt, root=None):
    require(isinstance(receipt, dict) and set(receipt) == {"path", "bytes", "sha256"},
            "SEALED_FILE_RECEIPT_REQUIRED")
    path = Path(receipt["path"]).resolve()
    if root is not None:
        require(path.is_relative_to(Path(root).resolve()), "SEALED_FILE_PATH_ESCAPE")
    require(record(path) == receipt, "SEALED_FILE_SHA_DRIFT:" + str(path))
    return path


def source_seal(root):
    root = Path(root).resolve()
    files = {}
    for folder in sorted(root.glob("v42_*")):
        # Independent B2 recovery and UI/supervisor edits cannot relabel or
        # invalidate an otherwise identical B3 scientific source identity.
        if (folder.name.startswith("v42_b2_") and folder.name != "v42_b2_seed_recovery_v19") or folder.name in {
                "v42_autonomous", "v42_autonomous_b2", "v42_autonomous_monitor"}:
            continue
        if folder.is_dir():
            for path in sorted(folder.rglob("*.py")):
                files[path.relative_to(root).as_posix()] = record(path)["sha256"]
        elif folder.suffix == ".py":
            files[folder.relative_to(root).as_posix()] = record(folder)["sha256"]
    require("v42_b3_joint/source_coordinator.py" in files and
            "v42_autonomous_b3/worker.py" in files, "COMPLETE_B3_SOURCE_SEAL_REQUIRED")
    return {"schema": "B3_AUTONOMOUS_SOURCE_SEAL_V1", "root": str(root),
            "files": files, "source_sha": digest(files)}


def validate_seal(seal, root):
    require(seal.get("schema") == "B3_AUTONOMOUS_SOURCE_SEAL_V1" and
            Path(seal["root"]).resolve() == Path(root).resolve() and
            digest(seal["files"]) == seal["source_sha"], "B3_SOURCE_SEAL_IDENTITY_DRIFT")
    require_sha(seal["source_sha"])
    for relative, expected in seal["files"].items():
        path = (Path(root) / relative).resolve()
        require(path.is_relative_to(Path(root).resolve()) and record(path)["sha256"] == expected,
                "B3_SOURCE_SEAL_FILE_DRIFT:" + relative)
    return seal


def validate_request(request):
    require(request.get("arm") == "B3" and request.get("day") in DAYS and
            type(request.get("worker_slot")) is int and request["worker_slot"] == 1,
            "B3_EXACTLY_ONE_WORKER_MAY_DATE_REQUIRED")
    root, output = Path(request["code_root"]).resolve(), Path(request["output"]).resolve()
    from v42_svr11.authority import active
    epoch=active()
    owned=Path(epoch['root'])/'dates/B3'/request['day'] if epoch and request.get('svr11_campaign') else root/'runtime/b3'
    require(output.is_relative_to(owned) and output != owned,
            "ISOLATED_B3_ATTEMPT_OUTPUT_REQUIRED")
    require(Path(request["campaign_root"]).resolve() != output and
            not Path(request["campaign_root"]).resolve().is_relative_to(output),
            "B1_B2_EVIDENCE_WRITE_SEPARATION_REQUIRED")
    require(isinstance(request.get("run_id"), str) and request["run_id"] and
            isinstance(request.get("attempt_id"), str) and request["attempt_id"],
            "B3_ATTEMPT_IDENTITY_REQUIRED")
    return root, output


def scientific_run_id(request):
    """Bind the transport campaign identity to the original ASCII token API."""
    original = request["run_id"]
    require(isinstance(original, str) and original, "B3_CAMPAIGN_RUN_ID_REQUIRED")
    alias = original if re.fullmatch(r"[A-Za-z0-9_-]{1,100}", original) else (
        re.sub(r"[^A-Za-z0-9_-]", "_", original)[:87] + "_" + hashlib.sha256(original.encode()).hexdigest()[:12])
    require(request.get("scientific_run_id", alias) == alias, "B3_SCIENTIFIC_RUN_ID_BINDING_DRIFT")
    return alias


def verify_qualification(path, source_sha):
    qualification = read(path)
    day = qualification.get("qualified_day", qualification.get("day"))
    require(qualification.get("schema") == "B3_REAL_CANARY_QUALIFICATION_U4_V2" and
            qualification.get("common_mess_version") == COMMON_MESS_VERSION and
            qualification.get("source_sha") == source_sha and
            day in DAYS and qualification.get("day", day) == day and qualification.get("worker_count") == 1 and
            qualification.get("evidence_kind") == "SOURCE", "REAL_SOURCE_MATCHED_B3_CANARY_REQUIRED")
    root = Path(qualification["canary_output"]).resolve()
    for receipt in qualification["artifacts"]:
        checked(receipt, root)
    checkpoint = read(root / "B3_SOURCE_CHECKPOINT.json")
    require(checkpoint.get("status") == "COMPLETE" and checkpoint.get("inflight") is None and
            checkpoint.get("completed") == ["A1", "M1", "A2", "M2"] and
            checkpoint["identity"]["evidence_kind"] == "SOURCE" and
            checkpoint["identity"]["source_sha"] == source_sha and checkpoint["identity"]["day"] == day,
            "B3_CANARY_FULL_PIPELINE_INCOMPLETE")
    for stage in ("A1", "M1", "A2", "M2"):
        out = output_from_document(read(root / stage / "B3_SOURCE_STAGE_OUTPUT.json"))
        require(out.sha == checkpoint["result_shas"][stage] and out.evidence_kind == "SOURCE" and
                out.request.authority.source_sha == source_sha and out.request.authority.day == day and
                out.request.stage == stage,
                "B3_CANARY_STAGE_SHA_OR_SOURCE_DRIFT")
        physical, bounds = out.physical_evidence, out.global_evidence
        require(physical.get("original_integer_physical_verified") is True and
                (stage.startswith("M") or bounds.get("original_global_bound_verified") is True) and
                bounds.get("bound_scope") == "STAGE_FIXED_INPUT_GLOBAL" and
                bounds.get("joint_global_optimality_claim") is False,
                "B3_CANARY_INDEPENDENT_ORIGINAL_PROOFS_REQUIRED")
        if stage.startswith("M"):
            verify_m_acceptance(out.source_result, physical, bounds)
        else:
            lower, upper = Fraction(bounds["exact_LB"]), Fraction(bounds["exact_UB"])
            require(0 <= lower <= upper and (upper == 0 or (upper - lower) / upper <= Fraction(1, 200)),
                    "B3_CANARY_EXACT_GAP_NOT_ACCEPTED")
        ledger = json.loads(out.ledger_receipt)
        require(ledger.get("source_sha") == source_sha and ledger.get("day") == day and
                ledger.get("stage") == stage and ledger.get("native_limit_seconds") == native_limit(stage) and
                ledger.get("P2_calls") == 0 and ledger.get("Threads") == 1 and
                ledger.get("wall_limit_seconds") is None and
                type(ledger.get("measured_native_runtime")) in (float, int) and
                math.isfinite(ledger["measured_native_runtime"]) and 0 <= ledger["measured_native_runtime"]
                and (stage.startswith("M") or ledger["measured_native_runtime"] <= 5400),
                "B3_CANARY_ORIGINAL_STAGE_NATIVE_ACCOUNTING_REQUIRED")
        if stage == "A1":
            reuse = out.source_packet.get("b1_reuse", {})
            require(ledger["native_call_count"] == 0 and ledger["measured_native_runtime"] == 0 and
                    reuse.get("verified_reuse") is True and reuse.get("new_native_optimize_calls") == 0,
                    "B3_CANARY_VERIFIED_B1_A1_ZERO_NATIVE_REQUIRED")
        else:
            require(ledger["native_call_count"] > 0 and ledger["quarantined"] is False,
                    "B3_CANARY_REAL_NATIVE_ENTRY_REQUIRED")
    actual, validation = read(root / "B3_SOURCE_ACTUAL_RESULT.json"), read(root / "B3_SOURCE_VALIDATION.json")
    require(digest(actual) == checkpoint["actual_result_sha"] and
            digest(validation) == checkpoint["validation_sha"] and
            actual.get("scientific_certified") is True and actual["result"].get("PASS") is True and
            validation.get("PASS") is True, "B3_CANARY_REAL_ACTUAL_FRESH_VALIDATION_REQUIRED")
    return qualification


def qualification_status(path, source_sha, *, seal=None, code_root=None):
    """Classify evidence without turning a failed day's evidence into a gate."""
    if seal is not None:
        try:
            seal = read(seal) if isinstance(seal, (str, Path)) else seal
            validate_seal(seal, code_root or seal["root"])
            require(seal["source_sha"] == source_sha, "B3_CURRENT_SOURCE_IDENTITY_DRIFT")
        except Exception as error:
            return {"status": "GLOBAL_SOURCE_INTEGRITY_FAILURE", "qualified": False,
                    "global_source_block": True, "reason": str(error)}
    if path is None or not Path(path).is_file():
        return {"status": "ABSENT", "qualified": False, "global_source_block": False}
    # A source repair retains the previous qualification at its original path.
    # The new source's fully verified qualification has a separate identity.
    candidate = Path(path).with_name(Path(path).stem + "." + source_sha + ".json")
    if candidate.is_file():
        path = candidate
    try:
        document = read(path)
        if document.get("source_sha") != source_sha:
            return {"status": "SOURCE_MISMATCH", "qualified": False, "global_source_block": False}
        qualification = verify_qualification(path, source_sha)
        return {"status": "QUALIFIED", "qualified": True, "global_source_block": False,
                "qualified_day": qualification.get("qualified_day") or qualification.get("day"),
                "qualification": record(path)}
    except Exception as error:
        return {"status": "INVALID_DAY_EVIDENCE", "qualified": False, "global_source_block": False,
                "reason": str(error)}


def publish_qualification(output, source_sha, destination):
    output, destination = Path(output).resolve(), Path(destination).resolve()
    artifacts = [record(output / "B3_SOURCE_CHECKPOINT.json"),
                 record(output / "B3_SOURCE_ACTUAL_RESULT.json"),
                 record(output / "B3_SOURCE_VALIDATION.json")]
    artifacts += [record(output / stage / "B3_SOURCE_STAGE_OUTPUT.json")
                  for stage in ("A1", "M1", "A2", "M2")]
    day = read(output / "B3_SOURCE_CHECKPOINT.json")["identity"]["day"]
    document = {"schema": "B3_REAL_CANARY_QUALIFICATION_U4_V2", "source_sha": source_sha,
                "common_mess_version": COMMON_MESS_VERSION,
                "day": day, "qualified_day": day, "worker_count": 1, "evidence_kind": "SOURCE",
                "canary_output": str(output), "artifacts": artifacts}
    # Validate the fully materialized receipt before atomic publication.
    temporary = destination.with_name(destination.name + ".candidate")
    temporary.parent.mkdir(parents=True, exist_ok=True)
    temporary.write_text(canonical(document) + "\n", encoding="utf-8")
    verify_qualification(temporary, source_sha)
    if destination.exists():
        try:
            verify_qualification(destination, source_sha)
            temporary.unlink()
            return record(destination)
        except (ValueError, KeyError, OSError):
            preserved_destination = destination
            destination = destination.with_name(destination.stem + "." + source_sha + ".json")
            require(not destination.exists(), "CANARY_QUALIFICATION_NEVER_OVERWRITTEN")
            # The old artifact and all its recorded paths remain intact.
            require(preserved_destination != destination, "QUALIFICATION_SOURCE_IDENTITY_REQUIRED")
            replace_file(temporary, destination)
    else:
        replace_file(temporary, destination)
    return record(destination)


@dataclass(frozen=True)
class ExecutionPermit:
    day: str
    source_sha: str
    code_root: Path
    mode: str
    request_sha: str


@contextmanager
def execution_permit(request, seal):
    root, _ = validate_request(request)
    validate_seal(seal, root)
    from v42_svr11.authority import active
    if active() is not None and request.get('svr11_campaign') is True:
        epoch=active()
        require(request['day'] in DAYS and seal['source_sha']==epoch['execution_SHA']
            and request['manifest_SHA']==record(request['manifest'])['sha256'], 'SVR11_B3_EPOCH_PERMIT_DRIFT')
        mode='USER_AUTHORIZED_SVR11_FULL_MAY_FAIL_CONTINUE'
    elif request.get("canary") is True:
        mode = "USER_AUTHORIZED_REAL_CANARY"
    else:
        verify_qualification(request["qualification"], seal["source_sha"])
        mode = "REAL_CANARY_QUALIFIED_PRODUCTION"
    token = _permit.set(ExecutionPermit(request["day"], seal["source_sha"], root, mode, digest(request)))
    try:
        yield _permit.get()
    finally:
        _permit.reset(token)


def require_permit(action, *, context=None):
    if _native_zero.get() and action in {"NATIVE", "NATIVE_OPTIMIZE", "NATIVE_GUARD", "NATIVE_MODEL_PREFLIGHT"}:
        raise PermissionError("B3_DIAGNOSTIC_ALL_NATIVE_ENTRY_FORBIDDEN:" + action)
    permit = _permit.get()
    if permit is None or context is None:
        raise PermissionError("B3_PRODUCTION_NOT_AUTHORIZED:" + action)
    require(context.request.authority.day == permit.day and
            context.request.authority.source_sha == permit.source_sha and
            context.producer_source_sha == permit.source_sha and
            context.source_registry.evidence_kind == "SOURCE" and
            context.source_registry.root == permit.code_root,
            "B3_QUALIFIED_PERMIT_CONTEXT_DRIFT")
    return permit.mode
