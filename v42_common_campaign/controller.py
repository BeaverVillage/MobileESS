"""Real canaries first, then three B2 workers and one B3 worker."""
from pathlib import Path
import argparse
import json
import os
import subprocess
import sys
import time
import psutil

from v42_pr134_b1.common import atomic, digest, now, read, record, sha, process, same_process
from . import VERSION, DAYS
from .authority import ROOT, MANIFEST, checked, singleton, source_files, verify_manifest


def prepare(root, regression_receipt):
    root = Path(root).resolve()
    if root.exists() and (root / MANIFEST).exists():
        raise PermissionError("COMMON_U4_SOURCE_EPOCH_NEVER_OVERWRITTEN")
    root.mkdir(parents=True, exist_ok=True)
    regression = read(regression_receipt)
    if regression.get("PASS") is not True:
        raise PermissionError("COMMON_U4_REGRESSION_GATE_REQUIRED")
    previous = read(Path(r"D:\v42_may_restart_20261010_02\B2_V37_ZERO_START_DEPLOYMENT_MANIFEST.json"))
    sources = source_files()
    source_sha = digest(sources)
    preflight = dict(schema="COMMON_U4_IMPLEMENTATION_ENVIRONMENT_PREFLIGHT_V1", PASS=True,
        source_SHA=source_sha, regression=record(regression_receipt), UTC=now(),
        official_campaign_authorized=False, real_E2E_required_before_production=True)
    # Check native availability using an actual tiny development solve. Its
    # measured Runtime belongs to development, never to an M stage ledger.
    import gurobipy as gp
    import opendssdirect as dss
    model = gp.Model()
    try:
        model.Params.Threads=1; model.Params.TimeLimit=2
        model.addVar(lb=0, obj=1); model.optimize()
        if model.Status != gp.GRB.OPTIMAL:
            raise PermissionError("COMMON_U4_GUROBI_ENVIRONMENT_PROBE_FAILED")
        preflight["development_native_probe"] = dict(Runtime=model.Runtime, Work=model.Work,
            Gurobi_version=list(gp.gurobi.version()), status=model.Status, Threads=1)
        preflight["OpenDSS_version"] = dss.__version__
    finally:
        model.dispose()
    input_receipts = {}
    for day in DAYS:
        folder = Path(previous["input_folders"][day]).resolve()
        if not folder.is_dir():
            raise PermissionError("COMMON_U4_FROZEN_DAY_INPUT_MISSING:" + day)
        rows = [record(path) for path in sorted(folder.rglob("*")) if path.is_file()]
        bundle = read(folder / "NATIVE_INPUT.json")
        if bundle["day"] != day:
            raise PermissionError("COMMON_U4_FROZEN_DAY_AXIS_DRIFT")
        for key in ("route_table", "electrical_certificate"):
            receipt = bundle[key]
            if sha(receipt["path"]) != receipt["sha256"]:
                raise PermissionError("COMMON_U4_ORIGINAL_LINKED_INPUT_SHA_DRIFT:" + day)
            rows.append(record(receipt["path"]))
        input_receipts[day] = rows
    for row in previous["inherited_B1_results"].values():
        checked(row)
    atomic(root / "IMPLEMENTATION_PREFLIGHT.json", preflight)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    from v42_autonomous_b3.admission import source_seal
    b3seal = source_seal(ROOT)
    atomic(root / "B3_SOURCE_SEAL.json", b3seal)
    manifest = dict(schema="V42_COMMON_U4_QUALIFICATION_V1", run_id=root.name,
        algorithm_version=VERSION, code_root=str(ROOT), source_commit=commit,
        execution_sources=sources, execution_SHA=source_sha,
        builder_original_sources=sources,
        implementation=dict(version="B2_BUILD_SOURCE_AUTHORITY_V13_20261009", sources=sources),
        native_M_limit_seconds=1800, native_A_limit_seconds=5400, A_gap_target=.005,
        Threads=1, P2_calls=0, B2_workers=3, B3_workers=1,
        wall_limit_seconds=None, optimization_budget_basis="CUMULATIVE_NATIVE_RUNTIME",
        input_folders=previous["input_folders"], input_receipts=input_receipts,
        B1_results=previous["inherited_B1_results"],
        inherited_B1_results=previous["inherited_B1_results"],
        origin_campaign_root=r"D:\MobileESS_V42\runtime\v42_may_campaign\native90_build_reuse_20261009_01",
        B3_source_seal=record(root / "B3_SOURCE_SEAL.json"),
        preflight=record(root / "IMPLEMENTATION_PREFLIGHT.json"),
        previous_epoch=record(r"D:\v42_may_restart_20261010_02\AUTONOMOUS_MANIFEST.json"),
        previous_attempts_preserved=True, prior_attempts={}, UTC=now())
    atomic(root / MANIFEST, manifest)
    verify_manifest(root / MANIFEST)
    return record(root / MANIFEST)


def request_for(root, manifest, arm, day, slot, *, canary):
    attempt_id = "common_u4_v1_01"
    attempt = root / "dates" / arm / day / "attempts" / attempt_id
    path = attempt / "REQUEST.json"
    if path.exists():
        existing = read(path)
        if existing["source_SHA"] != manifest["execution_SHA"]:
            raise PermissionError("COMMON_U4_REQUEST_EPOCH_DRIFT")
        return path
    request = dict(root=str(root), campaign_root=str(root), code_root=str(ROOT),
        manifest=str(root / MANIFEST), campaign_manifest=str(root / MANIFEST),
        manifest_SHA=sha(root / MANIFEST), implementation_SHA=manifest["execution_SHA"],
        source_SHA=manifest["execution_SHA"], run_id=manifest["run_id"], arm=arm, day=day,
        attempt_id=attempt_id, worker_slot=slot, canary=canary,
        algorithm_version=VERSION, input_folder=manifest["input_folders"][day],
        result=str(attempt / "RESULT.json"), progress=str(attempt / "progress.json"),
        output=str(attempt / "output"), error=str(attempt / "error.json"),
        Threads=1, P2_calls=0, native_budget_seconds=1800,
        wall_budget_seconds=None, target_gap=.03, started_UTC=now())
    if arm == "B3":
        request.update(output=str(ROOT / "runtime" / "b3" / manifest["run_id"] / day / attempt_id),
            source_seal=manifest["B3_source_seal"]["path"],
            qualification=str(root / "B3_PRODUCTION_QUALIFICATION.json"),
            qualification_output=str(root / "B3_PRODUCTION_QUALIFICATION.json"),
            b1_campaign_root=manifest["origin_campaign_root"], previous_attempts=[])
    atomic(path, request)
    return path


def launch(path):
    request = read(path)
    attempt = path.parent
    owner_path = attempt / "PROCESS.json"
    if owner_path.is_file():
        owner = read(owner_path)
        if same_process(owner):
            expected = [sys.executable, "-B", "-X", "utf8", "-m", "v42_common_campaign.worker", str(path)]
            if owner.get("command") != expected or Path(psutil.Process(owner["PID"]).cwd()).resolve() != ROOT:
                raise PermissionError("COMMON_U4_RECOVERY_PROCESS_OWNERSHIP_DRIFT")
            class ExistingOwnedWorker:
                pid = owner["PID"]
                def poll(self):
                    return None if same_process(owner) else 0
            return ExistingOwnedWorker()
        if not Path(request["result"]).is_file():
            raise PermissionError("COMMON_U4_INTERRUPTED_ATTEMPT_REQUIRES_MEASURED_RECOVERY")
    # All source-carrying child processes inherit this immutable checkout.
    # CREATE_NO_WINDOW keeps long batch workers out of the interactive desktop.
    stdout = (attempt / "worker.stdout.log").open("ab")
    stderr = (attempt / "worker.stderr.log").open("ab")
    environment = dict(os.environ, PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")
    try:
        child = subprocess.Popen([sys.executable, "-B", "-X", "utf8", "-m", "v42_common_campaign.worker", str(path)],
            cwd=ROOT, env=environment, stdout=stdout, stderr=stderr,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    finally:
        stdout.close(); stderr.close()
    atomic(attempt / "PROCESS.json", process(child.pid))
    return child


def outcome(path):
    request = read(path)
    result_path = Path(request["result"])
    if result_path.is_file():
        return read(result_path)
    return None


def canaries(root):
    manifest = verify_manifest(root / MANIFEST)
    receipts = {}
    for arm in ("B2", "B3"):
        for day in DAYS:
            request = request_for(root, manifest, arm, day, 1, canary=True)
            result = outcome(request)
            if result is None:
                child = launch(request)
                while child.poll() is None:
                    atomic(root / "CONTROLLER_HEARTBEAT.json", dict(phase="REAL_E2E_CANARY", arm=arm,
                        day=day, child_PID=child.pid, UTC=now()))
                    time.sleep(10)
                result = outcome(request)
            if result is None:
                raise RuntimeError("COMMON_U4_WORKER_EXITED_WITHOUT_RESULT:" + arm + "/" + day)
            if result.get("source_SHA") != manifest["execution_SHA"]:
                raise PermissionError("COMMON_U4_CANARY_RESULT_SOURCE_DRIFT")
            if result.get("PASS") is True and result.get("actual_ac_physical_pass") is True:
                receipts[arm] = record(read(request)["result"])
                break
            if result.get("status") in ("INPUT_OR_SOURCE_FAILURE", "IMPLEMENTATION_FAILURE"):
                # A shared implementation/environment defect must be repaired
                # in a new source epoch, never swept under date-local failures.
                raise RuntimeError("COMMON_U4_CANARY_IMPLEMENTATION_BACKSTOP:" + arm + "/" + day)
        if arm not in receipts:
            raise RuntimeError("COMMON_U4_NO_REAL_PHYSICAL_E2E_CANARY:" + arm)
    official = dict(schema="V42_COMMON_U4_CAMPAIGN_V1", source_SHA=manifest["execution_SHA"],
        source_commit=manifest["source_commit"], algorithm_version=VERSION,
        qualification_manifest=record(root / MANIFEST), canaries=receipts, UTC=now(),
        B2_workers=3, B3_workers=1, B2_first_sweep_before_B3=True,
        M_native_seconds=1800, canary_reuse="SAME_SOURCE_INPUT_MODEL_POLICY_FULL_VALIDATION_CONTRACT")
    atomic(root / "COMMON_U4_CAMPAIGN_MANIFEST.json", official)
    verify_manifest(root / MANIFEST, production=True)
    return official


def sweep(root, arm):
    manifest = verify_manifest(root / MANIFEST, production=True)
    pending = [day for day in DAYS if not (root / "dates" / arm / day / "attempts/common_u4_v1_01/RESULT.json").exists()]
    running = {}
    implementation_failures = 0
    max_workers = 3 if arm == "B2" else 1
    while pending or running:
        for slot in range(1, max_workers + 1):
            if not pending or slot in running:
                continue
            day = pending.pop(0)
            path = request_for(root, manifest, arm, day, slot, canary=False)
            running[slot] = (day, path, launch(path))
        completed = []
        for slot, (day, path, child) in running.items():
            if child.poll() is not None:
                result = outcome(path)
                if result is None:
                    raise RuntimeError("COMMON_U4_WORKER_CRASH_UNMEASURED_RUNTIME:" + arm + "/" + day)
                if result.get("status") == "INPUT_OR_SOURCE_FAILURE":
                    raise RuntimeError("COMMON_U4_SOURCE_OR_ENVIRONMENT_BACKSTOP:" + arm + "/" + day)
                if result.get("status") == "IMPLEMENTATION_FAILURE":
                    implementation_failures += 1
                    if implementation_failures >= 2:
                        raise RuntimeError("COMMON_U4_REPEATED_IMPLEMENTATION_BACKSTOP:" + arm + "/" + day)
                completed.append(slot)
        for slot in completed:
            del running[slot]
        atomic(root / "CONTROLLER_HEARTBEAT.json", dict(phase=arm+"_FIRST_SWEEP", UTC=now(),
            pending=pending, running={str(slot):dict(day=value[0],PID=value[2].pid) for slot,value in running.items()}))
        if pending or running:
            time.sleep(10)
    from v42_common_reporting import summarize
    summarize(root, manifest_path=root / MANIFEST)


def run(root):
    root = Path(root).resolve()
    with singleton(root / "CONTROLLER.lock"):
        atomic(root / "CONTROLLER_PROCESS.json", process())
        try:
            if not (root / "COMMON_U4_CAMPAIGN_MANIFEST.json").is_file():
                canaries(root)
            sweep(root, "B2")
            sweep(root, "B3")
            atomic(root / "CONTROLLER_STATUS.json", dict(state="ALL_DATES_TERMINAL", UTC=now()))
        except Exception as error:
            # Already owned independent dates finish naturally. No unrelated
            # solver is killed, and all ledgers remain available for recovery.
            atomic(root / "CONTROLLER_STATUS.json", dict(state="DISPATCH_HELD", error=repr(error), UTC=now()))
            raise


if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "run"))
    parser.add_argument("root")
    parser.add_argument("--regression-receipt")
    args=parser.parse_args()
    if args.action == "prepare":
        print(json.dumps(prepare(args.root, args.regression_receipt)))
    else:
        run(args.root)
