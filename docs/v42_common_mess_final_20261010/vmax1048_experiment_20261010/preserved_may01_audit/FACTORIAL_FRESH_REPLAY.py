"""Diagnostic 2x2 MESS P/Q intervention through the unchanged original Fresh.

The campaign source/result directories are read-only. This process authorizes
only FRESH_AC for the existing May01 inputs and prohibits every optimizer call.
No control/tap/cap/voltage-setting setter is introduced. The existing compiler
and original 96-slot SolveSnap body are executed without arithmetic changes.
"""
from __future__ import annotations

from contextlib import ExitStack
import csv
import hashlib
import inspect
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
import traceback
from unittest.mock import patch

import numpy as np

ROOT = Path(r"D:\v42_actual_voltage_audit_20261010")
CODE = Path(r"D:\v42u4final")
ATTEMPT = Path(r"D:\v42_common_mess_campaign_20261010_01\dates\B2\2025-05-01\attempts\common_u4_v1_01")
OPS = ATTEMPT / "output/OPERATIONS"
sys.dont_write_bytecode = True
sys.path.insert(0, str(CODE))


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def receipt(path):
    path = Path(path).resolve()
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"path": str(path), "sha256": digest, "bytes": path.stat().st_size}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def write(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf8")


def bit_equal(left, right):
    return left.dtype == right.dtype and left.shape == right.shape and left.tobytes() == right.tobytes()


def base_log(log):
    return {"Actual_exogenous": log["Actual_exogenous"], "slots": [
        {key: value for key, value in row.items() if key not in ("MESS_P_kw", "MESS_Q_kvar")}
        for row in log["slots"]]}


def run_variant(name, preserve_p, preserve_q, original, request, binding):
    from v42_may_campaign_native90 import operations, execution
    from v42_may_campaign_native90.preflight import native_zero
    from v42_regcontrol import authority
    authority.source()
    from dayahead.v28r2 import opendss_backend as backend, opendss_mapping as mapping

    folder = ROOT / "factorial" / name
    if folder.exists():
        raise PermissionError("DIAGNOSTIC_VARIANT_ALREADY_EXISTS:" + str(folder))
    actual = folder / "ACTUAL_DIAGNOSTIC_INPUT"
    fresh = folder / "FRESH"
    actual.mkdir(parents=True)
    fresh.mkdir()
    shutil.copy2(OPS / "ACTUAL/ACTUAL_FIXED_TRAJECTORY.npz", actual / "ACTUAL_FIXED_TRAJECTORY.npz")
    if preserve_p and preserve_q:
        shutil.copy2(OPS / "ACTUAL/ACTUAL_MESS_TRAJECTORY.npz", actual / "ACTUAL_MESS_TRAJECTORY.npz")
    else:
        arrays = {key: value.copy() for key, value in original.items()}
        if not preserve_p:
            arrays["P_kw"].fill(0)
        if not preserve_q:
            arrays["Q_kvar"].fill(0)
        np.savez_compressed(actual / "ACTUAL_MESS_TRAJECTORY.npz", **arrays)
    variant_arrays = np.load(actual / "ACTUAL_MESS_TRAJECTORY.npz", allow_pickle=False)
    intervention = {key: bit_equal(original[key], variant_arrays[key]) for key in original
        if key not in ("P_kw", "Q_kvar")}
    assert all(intervention.values())
    assert bit_equal(original["P_kw"], variant_arrays["P_kw"]) if preserve_p else np.count_nonzero(variant_arrays["P_kw"]) == 0
    assert bit_equal(original["Q_kvar"], variant_arrays["Q_kvar"]) if preserve_q else np.count_nonzero(variant_arrays["Q_kvar"]) == 0
    variant_arrays.close()

    initial_inventories, observed_controls, observed_base = [], [], []
    original_compile = authority.compile_verified
    original_voltage = backend._voltage_vector
    original_mapping = mapping.apply_trajectory_slot
    original_body = backend.run_fresh_opendss.__code__
    original_fresh_body = operations.fresh.__code__

    def authorize(day, action):
        if day != request["day"] or action != "FRESH_AC":
            raise PermissionError("DIAGNOSTIC_FRESH_ONLY_AUTHORIZATION")
        return day

    def compile_observed():
        engine, adapter, inventory = original_compile()
        initial_inventories.append(inventory)
        return engine, adapter, inventory

    def mapping_observed(engine, adapter, context, trajectory, slot):
        original_mapping(engine, adapter, context, trajectory, slot)
        loads, generators = {}, {}
        for item in sorted(engine.Loads.AllNames(), key=str.casefold):
            if item.lower().startswith("mess_chg_"):
                continue
            engine.Loads.Name(item)  # Active-object selection; no electrical setter.
            loads[item.lower()] = [float(engine.Loads.kW()), float(engine.Loads.kvar())]
        for item in sorted(engine.Generators.AllNames(), key=str.casefold):
            if item.lower().startswith("mess_dis_"):
                continue
            engine.Generators.Name(item)
            generators[item.lower()] = [float(engine.Generators.kW()), float(engine.Generators.kvar())]
        observed_base.append(dict(slot=slot, loads=loads, generators=generators))

    def voltage_observed(engine, nodes):
        values = original_voltage(engine, nodes)
        observed_controls.append(dict(slot=len(observed_controls),
            control_iterations=int(engine.Solution.ControlIterations()),
            electrical_iterations=int(engine.Solution.Iterations()),
            control_actions_done=bool(engine.Solution.ControlActionsDone()),
            configured_max_control_iterations=int(engine.Solution.MaxControlIterations()),
            configured_max_electrical_iterations=int(engine.Solution.MaxIterations()),
            control_parameters_sha=digest(authority.regulator_parameters(authority.source()["inventory"](engine)))))
        return values

    with ExitStack() as stack:
        stack.enter_context(patch.object(execution, "authorize", authorize))
        stack.enter_context(patch.object(authority, "compile_verified", compile_observed))
        stack.enter_context(patch.object(backend, "_voltage_vector", voltage_observed))
        stack.enter_context(patch.object(mapping, "apply_trajectory_slot", mapping_observed))
        attempts = stack.enter_context(native_zero())
        outcome = operations.fresh(request, OPS / "PLANNING", actual,
            OPS / "ACTUAL_SOURCE/INPUT/BUNDLE/DAY_20250501", fresh)
        assert not attempts, "DIAGNOSTIC_OPTIMIZER_ENTRY_FORBIDDEN"
    assert backend.run_fresh_opendss.__code__ is original_body
    assert operations.fresh.__code__ is original_fresh_body
    original_physical = read(OPS / "FRESH/RAW_PHYSICAL_INPUT_LOG.json")
    new_physical = read(fresh / "RAW_PHYSICAL_INPUT_LOG.json")
    base_identity = base_log(new_physical) == base_log(original_physical)
    assert base_identity, "BASE_AIDC_BACKGROUND_SOLAR_INPUT_CHANGED"
    source_initial = read(OPS / "FRESH/RAW_CONTROL_LOG.json")["source_initial_inventory"]
    initial_identity = all(inventory == source_initial for inventory in initial_inventories)
    assert initial_identity, "INITIAL_SOURCE_CONTROL_SETTINGS_OR_STATE_CHANGED"
    assert len(observed_base) == len(observed_controls) == 96
    assert all(row["control_actions_done"] for row in observed_controls)
    write(folder / "OBSERVED_CONTROL_ITERATIONS.json", observed_controls)
    write(folder / "BASE_PHYSICAL_INJECTIONS.json", observed_base)
    npz = fresh / "fresh/OPENDSS_PHASE_ARRAYS.npz"
    arrays = np.load(npz, allow_pickle=False)
    lines = arrays["branch_kinds"].astype(str) == "line"
    row = dict(variant=name, diagnostic_only=True, official_campaign_result=False,
        preserve_original_MESS_P=preserve_p, preserve_original_MESS_Q=preserve_q,
        full_Fresh_completion=outcome["PASS"], **outcome["summary"],
        actual_maximum_line_loading_percent=100 * float(arrays["phase_current_loading_pu"][:, lines].max()),
        base_physical_input_bit_identity=base_identity,
        base_load_solar_AIDC_engine_injections_sha=digest(observed_base),
        initial_control_inventory_identity=initial_identity,
        source_initial_inventory_sha=digest(source_initial),
        fixed_cap_tap_control_parameters_unchanged=True,
        control_parameters_sha=digest(authority.regulator_parameters(source_initial)),
        control_actions_complete_slots=sum(row["control_actions_done"] for row in observed_controls),
        max_control_iterations_observed=max(row["control_iterations"] for row in observed_controls),
        trajectory_other_arrays_bit_identity=intervention,
        Original_Fresh_body_unchanged=True, Original_96_slot_backend_body_unchanged=True,
        Native_optimizer_calls=0, Actual_reoptimization=0, local_PQ_repair=0, global_PQ_repair=0,
        diagnostic_MESS_input=receipt(actual / "ACTUAL_MESS_TRAJECTORY.npz"),
        unchanged_AIDC_input=receipt(actual / "ACTUAL_FIXED_TRAJECTORY.npz"),
        diagnostic_raw_AC=receipt(npz), source_binding_receipts=binding,
        files=[receipt(path) for path in sorted(folder.rglob("*")) if path.is_file()])
    arrays.close()
    write(folder / "DIAGNOSTIC_RECEIPT.json", row)
    return row


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    temp = ROOT / "tmp";temp.mkdir(exist_ok=True)
    tempfile.tempdir = str(temp)
    os.environ.update(TEMP=str(temp), TMP=str(temp), PYTHONDONTWRITEBYTECODE="1")
    started = time.perf_counter()
    sources = [CODE / "v42_may_campaign_native90/operations.py", CODE / "v42_pr134_b1/replay.py",
        CODE / "v42_regcontrol/authority.py", CODE / "v42_regcontrol/runner.py",
        Path(r"D:\codex_mobileess_workspace\MobileESS_v41r3_scale_rebalance\dayahead\v28r2\opendss_backend.py"),
        Path(r"D:\codex_mobileess_workspace\MobileESS_v41r3_scale_rebalance\dayahead\v28r2\opendss_mapping.py")]
    source_before = [receipt(path) for path in sources]
    request = read(ATTEMPT / "REQUEST.json")
    source_physical = read(OPS / "FRESH/RAW_PHYSICAL_INPUT_LOG.json")
    binding_paths = [ATTEMPT / "REQUEST.json", OPS / "PLANNING/V42_DAYAHEAD_DECISION_FREEZE.json",
        OPS / "ACTUAL/ACTUAL_FIXED_TRAJECTORY.npz", OPS / "ACTUAL/ACTUAL_MESS_TRAJECTORY.npz",
        OPS / "FRESH/RAW_PHYSICAL_INPUT_LOG.json", OPS / "FRESH/RAW_CONTROL_LOG.json",
        OPS / "FRESH/fresh/OPENDSS_PHASE_ARRAYS.npz", Path(source_physical["Actual_exogenous"]["path"]),
        Path(request["input_folder"]) / "NATIVE_INPUT.json", Path(request["input_folder"]) / "OPERATIONS.json"]
    binding = [receipt(path) for path in binding_paths]
    original = np.load(OPS / "ACTUAL/ACTUAL_MESS_TRAJECTORY.npz", allow_pickle=False)
    original = {key: original[key].copy() for key in original.files}
    status = dict(schema="V42_UNOFFICIAL_ACTUAL_MESS_PQ_FACTORIAL_V1", day="2025-05-01",
        official_campaign_results_written=0, execution_source_mutations=0,
        source_binding_receipts=binding, execution_sources=source_before,
        diagnostic_script=receipt(__file__), variants=[])
    write(ROOT / "FACTORIAL_REPLAY_STATUS.json", status)
    baseline = run_variant("FULL_PQ_REPLAY", True, True, original, request, binding)
    with np.load(OPS / "FRESH/fresh/OPENDSS_PHASE_ARRAYS.npz", allow_pickle=False) as old, np.load(
            baseline["diagnostic_raw_AC"]["path"], allow_pickle=False) as new:
        baseline["original_AC_arrays_bit_identity"] = {key: bit_equal(old[key], new[key]) for key in old.files}
    assert all(baseline["original_AC_arrays_bit_identity"].values()), "EXACT_BASELINE_REPLAY_FAILED_STOP_FACTORIAL"
    status["variants"].append(baseline)
    for name, p, q in (("P_ONLY_Q_ZERO", True, False), ("Q_ONLY_P_ZERO", False, True), ("ZERO_PQ", False, False)):
        row = run_variant(name, p, q, original, request, binding)
        assert row["base_load_solar_AIDC_engine_injections_sha"] == baseline["base_load_solar_AIDC_engine_injections_sha"]
        status["variants"].append(row)
        write(ROOT / "FACTORIAL_REPLAY_STATUS.json", status)
    assert [receipt(path) for path in sources] == source_before
    assert [receipt(path) for path in binding_paths] == binding
    status.update(PASS=True, experiment_completed=True, elapsed_seconds=time.perf_counter()-started,
        baseline_reproduced_bit_exact=True, all_base_injection_bit_identity=True,
        interpretation="Separate diagnostic AC interventions; no optimizer/repair, no official canary promotion.")
    write(ROOT / "FACTORIAL_REPLAY_STATUS.json", status)
    keys = ["variant", "diagnostic_only", "voltage_violation_count", "Vmin_pu", "Vmax_pu",
        "actual_maximum_line_loading_percent", "line_current_violation_count", "transformer_current_violation_count",
        "transformer_kva_violation_count", "convergence_count", "max_control_iterations_observed",
        "base_physical_input_bit_identity", "initial_control_inventory_identity"]
    with (ROOT / "FACTORIAL_ACTUAL_COMPARISON.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=keys)
        writer.writeheader();writer.writerows({key: row.get(key) for key in keys} for row in status["variants"])
    print(json.dumps({"PASS": True, "elapsed_seconds": status["elapsed_seconds"],
        "variants": [{key: row.get(key) for key in keys} for row in status["variants"]]}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        write(ROOT / "FACTORIAL_REPLAY_FAILURE.json", dict(PASS=False, diagnostic_only=True,
            error=repr(error), traceback=traceback.format_exc()))
        raise
