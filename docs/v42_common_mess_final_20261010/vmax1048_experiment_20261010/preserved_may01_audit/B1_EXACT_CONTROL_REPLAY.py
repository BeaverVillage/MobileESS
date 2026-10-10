"""Separate zero-optimizer instrumented replay of preserved B1 May01 Fresh."""
from pathlib import Path
import importlib.util
import json
import os
import sys
import tempfile
import numpy as np

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "B1_MAY01_EXACT_CONTROL_REPLAY"
ATTEMPT = Path(r"D:\MobileESS_V42\runtime\v42_may_campaign\native90_build_reuse_20261009_01\dates\B1\2025-05-01")
OPS = ATTEMPT / "output/OPERATIONS"
HELPER = ROOT / "FACTORIAL_FRESH_REPLAY.py"
CODE = Path(r"D:\v42u4final")
sys.dont_write_bytecode = True


def main():
    if OUT.exists():
        raise PermissionError("B1_EXACT_CONTROL_DIAGNOSTIC_ALREADY_EXISTS")
    spec = importlib.util.spec_from_file_location("external_original_fresh_diagnostic", HELPER)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    helper.ROOT, helper.ATTEMPT, helper.OPS = OUT, ATTEMPT, OPS
    result = helper.read(ATTEMPT / "RESULT.json")
    request = helper.read(ATTEMPT / "request.json")
    assert request["arm"] == "B1" and request["day"] == "2025-05-01"
    source_before, executed_sources = [], []
    for row in result["evaluation"]["reviewer_source_SHA"]:
        actual = helper.receipt(row["path"])
        assert actual == row
        source_before.append(actual)
        relative = Path(row["path"]).relative_to(Path(r"D:\MobileESS_V42")) if str(row["path"]).lower().startswith("d:\\mobileess_v42\\") else None
        current = CODE / relative if relative is not None else Path(row["path"])
        executed = helper.receipt(current)
        assert executed["sha256"] == row["sha256"] and executed["bytes"] == row["bytes"]
        executed_sources.append(executed)
    physical = helper.read(OPS / "FRESH/RAW_PHYSICAL_INPUT_LOG.json")
    binding_paths = [ATTEMPT / "request.json", ATTEMPT / "RESULT.json", OPS / "PLANNING/V42_DAYAHEAD_DECISION_FREEZE.json",
        OPS / "ACTUAL/ACTUAL_FIXED_TRAJECTORY.npz", OPS / "ACTUAL/ACTUAL_MESS_TRAJECTORY.npz",
        OPS / "FRESH/RAW_PHYSICAL_INPUT_LOG.json", OPS / "FRESH/RAW_CONTROL_LOG.json",
        OPS / "FRESH/fresh/OPENDSS_PHASE_ARRAYS.npz", Path(physical["Actual_exogenous"]["path"]),
        Path(request["input_folder"]) / "NATIVE_INPUT.json", Path(request["input_folder"]) / "OPERATIONS.json", HELPER]
    before = [helper.receipt(path) for path in binding_paths]
    with np.load(OPS / "ACTUAL/ACTUAL_MESS_TRAJECTORY.npz", allow_pickle=False) as archive:
        original = {key: archive[key].copy() for key in archive.files}
    assert np.count_nonzero(original["P_kw"]) == np.count_nonzero(original["Q_kvar"]) == 0
    OUT.mkdir()
    temp = OUT / "tmp"
    temp.mkdir()
    tempfile.tempdir = str(temp)
    os.environ.update(TEMP=str(temp), TMP=str(temp), PYTHONDONTWRITEBYTECODE="1")
    diagnostic = helper.run_variant("EXACT_B1_MAY01", True, True, original, request, before)
    with np.load(OPS / "FRESH/fresh/OPENDSS_PHASE_ARRAYS.npz", allow_pickle=False) as old, np.load(
            diagnostic["diagnostic_raw_AC"]["path"], allow_pickle=False) as new:
        identities = {key: helper.bit_equal(old[key], new[key]) for key in old.files}
    assert all(identities.values()), "B1_ORIGINAL_ARRAYS_BIT_EXACT_REPRODUCTION_REQUIRED"
    observed_path = OUT / "factorial/EXACT_B1_MAY01/OBSERVED_CONTROL_ITERATIONS.json"
    observed = helper.read(observed_path)
    assert len(observed) == 96 and all(row["control_actions_done"] for row in observed)
    assert {row["configured_max_control_iterations"] for row in observed} == {100}
    assert {row["control_parameters_sha"] for row in observed} == {diagnostic["control_parameters_sha"]}
    assert [helper.receipt(path) for path in binding_paths] == before
    assert [helper.receipt(row["path"]) for row in source_before] == source_before
    assert [helper.receipt(row["path"]) for row in executed_sources] == executed_sources
    proof = dict(schema="V42_B1_EXACT_MAY01_CONTROL_DIAGNOSTIC_V1", PASS=True, diagnostic_only=True,
        original_B1_result_not_modified=True, original_B1_arrays_bit_exact=identities,
        historical_unrecorded_iterations_remain_UNKNOWN=True,
        arm="B1", day="2025-05-01", new_AC_solves=96, Native_optimizer_calls=0,
        control_actions_done_slots=sum(row["control_actions_done"] for row in observed),
        max_control_iterations_observed=max(row["control_iterations"] for row in observed),
        max_electrical_iterations_observed=max(row["electrical_iterations"] for row in observed),
        configured_max_control_iterations=sorted({row["configured_max_control_iterations"] for row in observed}),
        configured_max_electrical_iterations=sorted({row["configured_max_electrical_iterations"] for row in observed}),
        common_regulator_settings_SHA=diagnostic["control_parameters_sha"],
        original_source_before_after_equal=True, original_binding_before_after_equal=True,
        unchanged_original_sources=source_before, identical_executed_sources=executed_sources,
        original_binding_receipts=before, diagnostic_script=helper.receipt(__file__),
        observed_controls=helper.receipt(observed_path),
        diagnostic_receipt=helper.receipt(OUT / "factorial/EXACT_B1_MAY01/DIAGNOSTIC_RECEIPT.json"))
    helper.write(OUT / "B1_EXACT_CONTROL_REPLAY_RESULT.json", proof)
    print(json.dumps({key: proof[key] for key in ("PASS", "control_actions_done_slots", "max_control_iterations_observed",
        "max_electrical_iterations_observed", "configured_max_control_iterations", "configured_max_electrical_iterations",
        "common_regulator_settings_SHA", "original_B1_arrays_bit_exact", "observed_controls")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
