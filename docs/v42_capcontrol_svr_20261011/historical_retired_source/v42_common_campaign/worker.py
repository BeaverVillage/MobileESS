"""One date, one immutable source epoch, one owned result publication."""
from pathlib import Path
from contextlib import ExitStack
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
    physical_audit=None
    physical_events=None
    try:
        shared = Path(r"D:\MobileESS_V42\runtime\v42_may_campaign\native_slots")
        slot = shared / (f"SLOT_{request['worker_slot']}.lock" if request["arm"] == "B2" else "COMMON_B3.lock")
        with singleton(attempt / "WORKER.lock"), singleton(slot), ExitStack() as physical_scope:
            if manifest.get('DSTATCOM_design'):
                if request['arm']!='B2':
                    raise PermissionError('DSTATCOM_B3_INDEPENDENT_PLANNING_ACTUAL_ADAPTER_REQUIRED')
                from v42_dstatcom.operations import independent_scopes
                physical_events=physical_scope.enter_context(independent_scopes(request,manifest))
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
        if physical_events is not None:
            physical_audit=physical_events['Actual']
            if physical_audit is None or physical_events['Planning'] is None:
                raise PermissionError('DSTATCOM_REAL_FORECAST_AND_ACTUAL_FRESH_REQUIRED')
            hardware_PASS=physical_audit.result['hardware_and_controller_PASS']
            original_PASS=result.get('actual_ac_physical_pass') is True
            planning_PASS=physical_events['Planning_physical_PASS']
            result.update(DSTATCOM_scenario_SHA=physical_audit.scenario['scenario_SHA'],
                DSTATCOM_physical_audit=physical_audit.receipt,
                DSTATCOM_Planning_physical_audit=physical_events['Planning'].receipt,
                DSTATCOM_Planning_physical_PASS=planning_PASS,
                DSTATCOM_control_independence=physical_events['independence'],
                DSTATCOM_hardware_and_controller_PASS=hardware_PASS,
                original_Fresh_physical_PASS=original_PASS,
                actual_ac_physical_pass=original_PASS and hardware_PASS,
                PASS=result.get('PASS') is True and hardware_PASS and planning_PASS)
            if original_PASS and not hardware_PASS:
                result['status']='DSTATCOM_HARDWARE_OR_CONTROL_FAILED'
            elif not planning_PASS:
                result['status']='DSTATCOM_FORECAST_PLANNING_AC_FAILED'
    except Exception as error:
        text = str(error)
        status = ("INPUT_OR_SOURCE_FAILURE" if isinstance(error, PermissionError)
            or "SHA_DRIFT" in text or "INPUT" in text else "IMPLEMENTATION_FAILURE")
        result.update(PASS=False, status=status, error=repr(error), traceback=traceback.format_exc())
        atomic(attempt / "error.json", dict(error=repr(error), traceback=traceback.format_exc(), UTC=now()))
    finally:
        stopped.set(); ticker_thread.join(timeout=2)
        if physical_events is not None:
            physical_audit=physical_events['Actual']
            if physical_events['Planning'] is not None:
                result.update(DSTATCOM_Planning_physical_audit=physical_events['Planning'].receipt,
                    DSTATCOM_Planning_physical_PASS=physical_events['Planning_physical_PASS'])
        if physical_audit is not None:
            result.update(DSTATCOM_scenario_SHA=physical_audit.scenario['scenario_SHA'],
                DSTATCOM_physical_audit=physical_audit.receipt)
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
