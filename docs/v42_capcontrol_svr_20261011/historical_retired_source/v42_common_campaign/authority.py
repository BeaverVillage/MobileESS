"""Explicit immutable execution authority, separate from historical epochs."""
from contextlib import contextmanager
from pathlib import Path
from fractions import Fraction
import math
import json
import msvcrt
import os
import psutil

from v42_pr134_b1.common import atomic, digest, now, read, record, sha
from . import VERSION, DAYS

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = "COMMON_U4_QUALIFICATION_MANIFEST.json"


def source_files():
    files = {}
    for folder in sorted(ROOT.glob("v42_*")):
        if folder.is_dir():
            for path in sorted(folder.rglob("*.py")):
                files[path.relative_to(ROOT).as_posix()] = sha(path)
        elif folder.suffix == ".py":
            files[folder.relative_to(ROOT).as_posix()] = sha(folder)
    return files


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
            raise PermissionError("COMMON_U4_PROCESS_LEASE_ALREADY_OWNED:" + str(path)) from error
        try:
            yield
        finally:
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)


def checked(receipt):
    if record(receipt["path"]) != receipt:
        raise PermissionError("COMMON_U4_FILE_SHA_DRIFT:" + receipt["path"])
    return Path(receipt["path"]).resolve()


def verify_real_canary(receipt, arm, manifest):
    """Recheck owned evidence rather than accepting a producer's PASS alone."""
    result = read(checked(receipt))
    identity = result.get("identity", {})
    if (result.get("PASS") is not True or result.get("actual_ac_physical_pass") is not True
            or result.get("source_SHA") != manifest["execution_SHA"]
            or identity.get("arm") != arm or identity.get("day") not in DAYS):
        raise PermissionError("COMMON_U4_BOTH_REAL_E2E_CANARIES_REQUIRED:" + arm)
    if manifest.get('DSTATCOM_design'):
        from v42_dstatcom.authority import verify_physical_result
        verify_physical_result(result,manifest,arm,identity['day'])
    if arm == "B3":
        from v42_autonomous_b3.admission import verify_qualification, validate_seal
        seal = read(checked(manifest["B3_source_seal"]))
        validate_seal(seal, ROOT)
        verify_qualification(Path(receipt["path"]).parents[5] / "B3_PRODUCTION_QUALIFICATION.json",
            seal["source_sha"])
        return result
    stage = result.get("scientific", {})
    evaluation = result.get("evaluation", {})
    if (stage.get("engine_version") != VERSION or stage.get("feasible_accepted") is not True
            or stage.get("error") is not None or stage.get("P2_calls") != 0
            or stage.get("scientific_case_sha") != stage.get("case_sha")
            or evaluation.get("PASS") is not True or evaluation.get("physical_violation") is not False
            or evaluation.get("Actual_reoptimization") != 0
            or evaluation.get("local_PQ_repair") != 0 or evaluation.get("global_PQ_repair") != 0):
        raise PermissionError("COMMON_U4_B2_CANARY_INDEPENDENT_CONTRACT_REQUIRED")
    proof = read(checked(stage["certificate"]["strict_UB"]))
    if (proof.get("PASS") is not True
            or proof.get("strict_raw_C3A_and_FULL_integer_and_binary_pattern_exact") is not True
            or proof.get("case_sha") != stage["case_sha"]
            or Fraction(proof["exact_Global_UB"]) != Fraction(stage["exact_Global_UB"])):
        raise PermissionError("COMMON_U4_B2_CANARY_FULL_LITERAL_REPLAY_REQUIRED")
    for file in result.get("files", []):
        checked(file)
    summary = evaluation.get("summary", {})
    if (summary.get("convergence_count") != 96 or summary.get("OpenDSS_solve_count") != 96
            or summary.get("schedule_mutation_count") != 0):
        raise PermissionError("COMMON_U4_B2_CANARY_REAL_96_SLOT_FRESH_REQUIRED")
    fresh = evaluation["Fresh"]
    for key in ("receipt", "control_log", "physical_input_log"):
        checked(fresh[key])
    ledger = read(checked(result["native_ledger"]))
    total = 0.
    if ledger.get("inflight") is not None or not ledger.get("calls"):
        raise PermissionError("COMMON_U4_B2_CANARY_REAL_MEASURED_NATIVE_REQUIRED")
    for row in ledger["calls"]:
        runtime = row.get("Native_Runtime")
        limit = row.get("effective_TimeLimit")
        if (row.get("entered_native") is not True or row.get("runtime_unavailable") is not False
                or type(runtime) not in (int, float) or not math.isfinite(runtime) or runtime < 0
                or total >= 1800 or limit <= 0 or limit > 1800-total):
            raise PermissionError("COMMON_U4_B2_CANARY_CUMULATIVE_NATIVE_CALL_DRIFT")
        total += runtime
    if not math.isclose(total, ledger["measured_Native_Runtime"], abs_tol=1e-9, rel_tol=0):
        raise PermissionError("COMMON_U4_B2_CANARY_RUNTIME_MEASUREMENT_DRIFT")
    return result


def verify_manifest(path, *, production=False):
    path = Path(path).resolve()
    manifest = read(path)
    if (manifest.get("schema") != "V42_COMMON_U4_QUALIFICATION_V1"
            or manifest.get("algorithm_version") != VERSION
            or Path(manifest["code_root"]).resolve() != ROOT
            or manifest.get("native_M_limit_seconds") != 1800
            or manifest.get("A_gap_target") != .005
            or manifest.get("Threads") != 1 or manifest.get("P2_calls") != 0
            or manifest.get("execution_SHA") != digest(manifest["execution_sources"])):
        raise PermissionError("COMMON_U4_MANIFEST_POLICY_DRIFT")
    for name, expected in manifest["execution_sources"].items():
        file = (ROOT / name).resolve()
        if not file.is_relative_to(ROOT) or sha(file) != expected:
            raise PermissionError("COMMON_U4_SOURCE_SHA_DRIFT:" + name)
    if set(manifest["input_folders"]) != set(DAYS):
        raise PermissionError("COMMON_U4_ALL_MAY_INPUTS_REQUIRED")
    for receipt in manifest["B1_results"].values():
        checked(receipt)
    checked(manifest["preflight"])
    preflight = read(manifest["preflight"]["path"])
    if preflight.get("PASS") is not True or preflight.get("source_SHA") != manifest["execution_SHA"]:
        raise PermissionError("COMMON_U4_REAL_PREFLIGHT_REQUIRED")
    if manifest.get('DSTATCOM_design'):
        from v42_dstatcom.authority import verify_design
        verify_design(manifest['DSTATCOM_design'],manifest['execution_SHA'])
    if production:
        verify_control_audit(path.parent, manifest)
        official = read(path.parent / "COMMON_U4_CAMPAIGN_MANIFEST.json")
        if (official.get("schema") != "V42_COMMON_U4_CAMPAIGN_V1"
                or official.get("source_SHA") != manifest["execution_SHA"]
                or official.get("qualification_manifest") != record(path)):
            raise PermissionError("COMMON_U4_CAMPAIGN_EPOCH_DRIFT")
        for arm in ("B2", "B3"):
            verify_real_canary(official["canaries"][arm], arm, manifest)
    return manifest


def verify_control_audit(root, manifest):
    """A required causal audit can hold production while canaries continue."""
    if manifest.get('common_control_audit_required') is not True:
        return
    path = Path(root) / 'COMMON_CONTROL_AUDIT_STATUS.json'
    if not path.is_file():
        raise PermissionError('COMMON_U4_COMMON_CONTROL_AUDIT_PENDING')
    status = read(path)
    if (status.get('schema') != 'COMMON_U4_CONTROL_AUDIT_STATUS_V1'
            or status.get('source_SHA') != manifest['execution_SHA']
            or status.get('status') != 'PASS'
            or status.get('common_control_implementation_defect') is not False):
        raise PermissionError('COMMON_U4_COMMON_CONTROL_AUDIT_DISPATCH_HELD')
    audit = read(checked(status['audit']))
    baseline = manifest.get('control_audit_baseline')
    if (audit.get('schema') != 'V42_MAY01_COMMON_CONTROL_CAUSAL_AUDIT_V1'
            or not baseline or audit.get('baseline_RESULT') != baseline
            or audit.get('audit_complete') is not True
            or audit.get('common_control_implementation_defect') is not False
            or audit.get('same_Actual_factorial_full_PQ_bit_exact') is not True
            or audit.get('regcontrol_count') != 7
            or audit.get('original_control_settings_preserved') is not True
            or audit.get('original_canary_evidence_preserved') is not True):
        raise PermissionError('COMMON_U4_CONTROL_AUDIT_AUTHORITATIVE_VERDICT_REQUIRED')
    original = read(checked(baseline))
    if audit.get('baseline_source_SHA') != original.get('source_SHA'):
        raise PermissionError('COMMON_U4_CONTROL_AUDIT_BASELINE_SOURCE_DRIFT')


def verify_request(request):
    manifest_path = Path(request["manifest"]).resolve()
    manifest = verify_manifest(manifest_path, production=request.get("canary") is not True)
    root = manifest_path.parent
    arm, day = request.get("arm"), request.get("day")
    if (arm not in ("B2", "B3") or day not in DAYS
            or request.get("run_id") != manifest["run_id"]
            or request.get("source_SHA") != manifest["execution_SHA"]
            or request.get("manifest_SHA") != sha(manifest_path)
            or Path(request["root"]).resolve() != root
            or request.get("native_budget_seconds") != 1800
            or request.get("Threads") != 1 or request.get("P2_calls") != 0):
        raise PermissionError("COMMON_U4_REQUEST_AUTHORITY_DRIFT")
    attempt = root / "dates" / arm / day / "attempts" / request["attempt_id"]
    for key, name in (("result", "RESULT.json"), ("progress", "progress.json")):
        if Path(request[key]).resolve() != attempt / name:
            raise PermissionError("COMMON_U4_ATTEMPT_PATH_DRIFT:" + key)
    if arm == "B2":
        if Path(request["output"]).resolve() != attempt / "output":
            raise PermissionError("COMMON_U4_B2_OUTPUT_PATH_DRIFT")
        if Path(request["input_folder"]).resolve() != Path(manifest["input_folders"][day]).resolve():
            raise PermissionError("COMMON_U4_FIXED_INPUT_PATH_DRIFT")
        for receipt in manifest["input_receipts"][day]:
            checked(receipt)
    return manifest


def assert_peers(request):
    seen = {(request["arm"], request["day"])}
    slots = {request["worker_slot"]}
    for proc in psutil.process_iter(("pid", "name")):
        if proc.pid == os.getpid() or (proc.info["name"] or "").lower() not in ("python.exe", "pythonw.exe"):
            continue
        try:
            args = proc.cmdline()
            module = args[args.index("-m") + 1] if "-m" in args else ""
            if module == "v42_common_campaign.worker":
                peer = read(args[-1])
                if peer.get("run_id") != request["run_id"] or peer.get("source_SHA") != request["source_SHA"]:
                    raise PermissionError("COMMON_U4_OTHER_CAMPAIGN_ACTIVE")
                key = (peer["arm"], peer["day"])
                if key in seen or peer["arm"] != request["arm"] or peer["worker_slot"] in slots:
                    raise PermissionError("COMMON_U4_DUPLICATE_DAY_SLOT_OR_ARM")
                seen.add(key); slots.add(peer["worker_slot"])
            elif module.endswith(".worker") and module.startswith(("v42_autonomous_b", "v42_may_campaign", "v42_b2_")):
                raise PermissionError("COMMON_U4_HISTORICAL_CAMPAIGN_WORKER_ACTIVE:" + str(proc.pid))
        except psutil.Error:
            continue
    if len(slots) > (3 if request["arm"] == "B2" else 1):
        raise PermissionError("COMMON_U4_WORKER_COUNT_EXCEEDED")
