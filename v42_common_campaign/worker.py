"""One date, one immutable source epoch, one owned result publication."""
from pathlib import Path
import os
import sys
import threading
import time
import traceback

from v42_pr134_b1.common import atomic, now, read, record, process
from .authority import ROOT, singleton, verify_request, assert_peers


def run(request_path):
    request = read(request_path)
    manifest = verify_request(request)
    assert_peers(request)
    attempt = Path(request["result"]).parent
    if Path(request["result"]).exists():
        raise PermissionError("COMMON_U4_COMPLETED_ATTEMPT_NEVER_REEXECUTED")
    attempt.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    stopped = threading.Event()
    mutex = threading.RLock()
    state = dict(arm=request["arm"], day=request["day"], stage="ADMISSION", phase="SOURCE_ADMISSION",
        source_SHA=request["source_SHA"], source_commit=manifest["source_commit"],
        worker=process(), request=record(request_path), started_UTC=now())
    def progress(value):
        with mutex:
            state.update(value, updated_UTC=now(), worker_wall_seconds=time.perf_counter()-started)
            atomic(request["progress"], state)
    def ticker():
        while not stopped.wait(10):
            progress({})
    ticker_thread = threading.Thread(target=ticker, daemon=True)
    result = dict(identity={key: request[key] for key in ("run_id", "arm", "day", "attempt_id")},
        source_SHA=request["source_SHA"], source_commit=manifest["source_commit"],
        algorithm_version=manifest["algorithm_version"], started_UTC=now(), PASS=False,
        status="IMPLEMENTATION_FAILURE", worker=process(), request=record(request_path),
        actual_ac_physical_pass=False)
    progress({}); ticker_thread.start()
    try:
        shared = Path(r"D:\MobileESS_V42\runtime\v42_may_campaign\native_slots")
        slot = shared / (f"SLOT_{request['worker_slot']}.lock" if request["arm"] == "B2" else "COMMON_B3.lock")
        with singleton(attempt / "WORKER.lock"), singleton(slot):
            if request["arm"] == "B2":
                from .b2 import run as execute
                result.update(execute(request, manifest, progress))
            else:
                from v42_autonomous_b3.worker import run as execute
                # The existing sealed canary permit, original SourceRegistry,
                # StageCoordinator and numeric policies remain the B3 authority.
                inner = dict(request, result=str(Path(request["output"]) / "RESULT.json"),
                    progress=str(Path(request["output"]) / "HEARTBEAT.json"))
                inner_path = attempt / "B3_SOURCE_REQUEST.json"
                atomic(inner_path, inner)
                outcome = execute(inner_path)
                result.update(outcome)
                # Existing Fresh completion marks execution and convergence;
                # the common campaign separately requires no physical exposure.
                pipeline = Path(request["output"]) / "PIPELINE"
                actual_path = pipeline / "B3_SOURCE_ACTUAL_RESULT.json"
                ac_pass = False
                if actual_path.is_file():
                    actual = read(actual_path)
                    ac = actual.get("result", {}).get("fresh_ac", {})
                    summary = ac.get("summary", {})
                    if not summary:
                        summary = actual.get("result", {}).get("summary", {})
                    ac_pass = outcome.get("PASS") is True and summary.get("physical_violation") is False
                result.update(source_SHA=request["source_SHA"], actual_ac_physical_pass=ac_pass,
                    PASS=ac_pass,
                    status="COMPLETED_PHYSICAL_PASS" if ac_pass else "ACTUAL_AC_FAILED" if outcome.get("PASS") is True
                        else outcome.get("classification", outcome.get("status", "IMPLEMENTATION_FAILURE")),
                    stage_outputs={stage: record(pipeline / stage / "B3_SOURCE_STAGE_OUTPUT.json")
                        for stage in ("A1", "M1", "A2", "M2")
                        if (pipeline / stage / "B3_SOURCE_STAGE_OUTPUT.json").is_file()})
    except Exception as error:
        text = str(error)
        status = ("INPUT_OR_SOURCE_FAILURE" if isinstance(error, PermissionError)
            or "SHA_DRIFT" in text or "INPUT" in text else "IMPLEMENTATION_FAILURE")
        result.update(PASS=False, status=status, error=repr(error), traceback=traceback.format_exc())
        atomic(attempt / "error.json", dict(error=repr(error), traceback=traceback.format_exc(), UTC=now()))
    finally:
        stopped.set(); ticker_thread.join(timeout=2)
        result.update(completed_UTC=now(), worker_wall_seconds=time.perf_counter()-started)
        ledger_path = attempt / "NATIVE_RUNTIME_LEDGER.json"
        if ledger_path.is_file():
            ledger = read(ledger_path)
            result.update(native_ledger=record(ledger_path), Native_Runtime=ledger["measured_Native_Runtime"],
                native_runtime_seconds=ledger["measured_Native_Runtime"], native_calls=len(ledger["calls"]),
                native_budget_overshoot_seconds=max(0., ledger["measured_Native_Runtime"]-1800))
            if any(row.get("runtime_unavailable") for row in ledger["calls"]):
                result.update(status="INPUT_OR_SOURCE_FAILURE", Native_Runtime=None,
                    actual_native_runtime="UNKNOWN", PASS=False)
        # B3's original worker owns its envelope result; the public common epoch
        # publication is a different path, leaving that original record intact.
        atomic(request["result"], result)
        progress(dict(phase=result["status"], state=result["status"]))
    return result


if __name__ == "__main__":
    outcome = run(sys.argv[1])
    print({"status": outcome["status"], "PASS": outcome["PASS"]})
    raise SystemExit(0 if outcome["PASS"] else 1)
