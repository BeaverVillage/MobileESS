"""Separated exact-case warm/cold integration attempt; campaign HOLD persists.

Import and prepare are Native0. No archived script is executed, no module
globals are patched, and all new files stay in the supplied attempt output.
The exact historical May01 problem is a regression, never a new QoS bound.
"""
from __future__ import annotations

import argparse
from copy import copy
import gc
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from scipy import sparse

from .budget import IntegrationBudget
from .m_engine import (APPROVED_JOINT_PARAMETERS, PR222_SHA, PathGraph,
                       _BudgetAdapter, _native_joint, _write, binding,
                       direct_joint, domain_sha, file_record, matrix_sha,
                       optimize_mess, strict_full, vector_sha)

ARCHIVE = Path("D:/v42_may_joint_repair_campaign_20261013")
DIAGNOSIS = Path("D:/v42_b2_stationary_diagnosis_20261013")
OUTPUT = Path("D:/v42_integration_validation_20261013")
WINNER = DIAGNOSIS / "PR220/calls/008_R2_LATE_SMALL/native/FINAL_RAW.npz"
WINNER_FILE_SHA = "3f3314b0ca9235ffeff02e3d4bdaab97477f4390992fddbd486a047ebd62d686"


def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def _arrays(path):
    with np.load(path, allow_pickle=False) as packet:
        return {key: packet[key].copy() for key in packet.files}


def source_records():
    root = Path(__file__).resolve().parents[1]
    relative = ["v42_integration/m_engine.py", "v42_integration/pr222_regression.py",
                "v42_integration/budget.py", "v42_integration/m_candidates.py", "v42_m1_research/check_ub.py",
                "v42_common_mess/engine.py", "v42_common_mess/model.py",
                "v42_common_mess/fixed_pattern.py", "v42_common_mess/budget.py",
                "v42_bootstrap/m1.py", "v42_native/mess.py",
                "tools/u4_primal_alns/pilot.py", "v42_bootstrap/attribution.py",
                "tools/time_decomposed_lb/grid.py", "v42_ultracompact/current_verify.py",
                "v42_ultracompact/polytope.py"]
    return {name: file_record(root / name) for name in relative}


def load_case(day, output, archive=ARCHIVE):
    """Restore current named matrices and exact inverse aliases read-only."""
    from v42_bootstrap.m1 import native_inputs
    archive, output = Path(archive).resolve(), Path(output).resolve()
    if output.is_relative_to(archive) or output.is_relative_to(DIAGNOSIS.resolve()):
        raise ValueError("HISTORICAL_OUTPUT_WRITE_FORBIDDEN")
    folder = archive / "dates/B2" / day / "attempts/attempt_01/output"
    input_path = archive / "inputs/B2" / day / "NATIVE_INPUT.json"
    paths = [folder / name for name in ("DENSE_RESPONSE_A.npz", "DENSE_RESPONSE_DATA.npz",
              "FULL_A.npz", "FULL_DATA.npz", "CURRENT_C2_ALIASES.json", "CURRENT_C2_AXES.npz",
              "SCIENTIFIC_CASE_IDENTITY.json", "FIXED_AIDC_ANCHOR.json")]
    records = [file_record(path) for path in paths] + [file_record(input_path)]
    selected_d, original_d = _arrays(paths[1]), _arrays(paths[3])
    A = sparse.load_npz(paths[0]).tocsr()
    full = sparse.load_npz(paths[2]).tocsr()
    aliases, columns = _read(paths[4]), _arrays(paths[5])["columns"]
    identity, bundle = _read(paths[6]), _read(input_path)
    sites, initial, routes, battery, receipt = native_inputs(bundle)
    graph = (sites, initial,
        [(s, t, s, t+1, None) for s in sites for t in range(96)] +
        [(r.source, r.depart, r.destination, r.connect, r) for r in dict.fromkeys(routes)], battery, receipt)
    size = max(full.shape[1], int(np.max(columns))+1, max(p["column"] for p in aliases)+1)
    def lift(point):
        x = np.zeros(size)
        x[columns] = point[:len(columns)]
        for packet in reversed(aliases):
            x[packet["column"]] = packet["constant"] + sum(
                coefficient*x[int(k)] for k, coefficient in packet["terms"].items())
        return x[:full.shape[1]].copy()
    identity = dict(identity, arm="B2", stage="M", day=day,
                    aidc_anchor=file_record(paths[-1])["sha256"],
                    qos_sha="HISTORICAL_EXACT_PR220_CASE_NO_NEW_QOS",
                    binary_count=int(np.count_nonzero(selected_d["types"] == "B")))
    case = SimpleNamespace(A=A, d=selected_d, original_A=full, original_d=original_d,
        graph=graph, case_sha=identity["case_sha"], identity=identity,
        bundle=bundle, aliases=aliases, selected_columns=columns, lift=lift,
        output=output, strict_validator=strict_full, planning=_read(paths[-1]),
        original_files=records, archive_folder=folder)
    actual_key = binding(case)
    for family, actual in (("original_matrix_sha", actual_key["original_matrix_sha"]),
                           ("original_domain_sha", actual_key["original_domain_sha"])):
        if identity.get(family) and identity[family] != actual:
            raise ValueError("ARCHIVED_NUMERIC_CASE_SOURCE_DRIFT:" + family)
    output.mkdir(parents=True, exist_ok=True)
    _write(output / "PR222_CASE_SOURCE_BINDING.json", dict(PASS=True, day=day, binding=actual_key,
        current_case_sha=case.case_sha, files=records, source_files=source_records(),
        baseline_PR207="497609b46faa14ea7e32a9483a333ab32fd264ef", baseline_PR222=PR222_SHA,
        historical_case_only=True, Native_optimize_calls=0,
        cold_candidate_source="PRE_FIRST_NATIVE_ADAPTIVE_POOL_001"))
    return case


def archived_candidates(case):
    source_path = case.archive_folder / "PR221/ADAPTIVE_POOL_001.json"
    packet = _read(source_path)
    # Existing path geometry is explicit caller data. No historical Raw point
    # enters a cold run; the distinction is retained in the receipt.
    pools = packet["pools"]
    graph = PathGraph(case)
    for unit, paths in pools.items():
        for path in paths:
            graph.validate(unit, path)
    return pools, file_record(source_path)


def cached_exact_validator(case, warm_record, stored_certificate):
    """Reuse only byte-identical already validated exact-case witness receipt."""
    original = strict_full
    def validate(current_case, path, evidence=None):
        with np.load(path, allow_pickle=False) as packet:
            if packet.files != ["point"]:
                raise ValueError("RAW_POINT_PACKET_AXIS_DRIFT")
            point = packet["point"].copy()
        if (binding(current_case) == binding(case)
                and vector_sha(point) == stored_certificate["point_vector_sha256"]
                and file_record(warm_record["path"]) == warm_record):
            reused = dict(stored_certificate, point_path=str(path),
                point_file_sha256=file_record(path)["sha256"], existing_FULL_receipt_reused=True,
                exact_numeric_case_rechecked=True)
            return reused
        return original(current_case, path, evidence)
    return validate


def run(mode, seconds=60., output=OUTPUT, ledger=None, day="2025-05-01"):
    output = Path(output).resolve()
    attempt = output / (mode + "_" + day)
    if attempt.exists():
        raise ValueError("ATTEMPT_ALREADY_EXISTS_BUDGET_NOT_RESET")
    case = load_case(day, attempt)
    budget = IntegrationBudget(ledger or output / "INTEGRATION_BUDGET_LEDGER.json")
    case.mess_stage_budget_seconds = float(seconds)
    if mode == "binding":
        key = binding(case)
        _write(attempt / "NATIVE0_BINDING_RESULT.json", dict(PASS=True, day=day, binding=key,
                    Native_optimize_calls=0, no_other_date_incumbent_admitted=True,
                    source_binding_only=True, optimizer_model_readback=False))
        return dict(PASS=True, Native_optimize_calls=0, source_binding_only=True)
    candidates, candidate_record = None, None
    if mode in ("warm", "native0"):
        candidates, candidate_record = archived_candidates(case)
        case.candidate_pools = candidates
    else:
        from .m_candidates import generate
        case.candidate_generator = generate
    initial, registry = None, []
    if mode in ("warm", "native0"):
        winner_record = file_record(WINNER)
        if winner_record["sha256"] != WINNER_FILE_SHA:
            raise ValueError("PR220_EXACT_WINNER_RAW_SHA_DRIFT")
        initial = _arrays(WINNER)["point"]
        stored = _read(DIAGNOSIS / "PR220_CURRENT_MAY01_FULL_REPLAY.json")
        if stored["original_matrix_and_96_slot_physical_replay"]["case_sha"] != case.case_sha:
            raise ValueError("PR220_EXACT_WINNER_CASE_RECEIPT_DRIFT")
        case.strict_validator = cached_exact_validator(case, winner_record, stored)
        registry = [dict(origin="PR220_EXACT_CURRENT_FULL_REPLAY", binding=binding(case), raw=winner_record)]
    _write(attempt / "CANDIDATE_SOURCE.json", dict(source=candidate_record,
        historical_native_witness_supplied=mode in ("warm", "native0"),
        prior_generated_candidate_geometry=mode in ("warm", "native0"),
        fresh_cold_beam_generation=mode == "cold", fresh_cold_beam_performance_claimed=False,
        no_cross_date_raw_reuse=True))
    if mode == "native0":
        from .m_engine import IncumbentBank, pin_pools
        bank = IncumbentBank(case)
        bank.offer(initial, case.strict_validator(case, WINNER, {}))
        pools = pin_pools(case, initial, bank, candidates)
        packet = direct_joint(case, initial, pools)
        _write(attempt / "EXACT_INTEGER_AND_ROW_EQUIVALENCE.json", packet[-1])
        native, captures = _native_joint(case, _BudgetAdapter(budget), packet,
                                          attempt / "JOINT", 0., native0=True)
        _write(attempt / "PR222_REGRESSION.json", dict(PASS=True, Native_optimize_calls=0,
            readback=native, full_receipt_reused=True, known_FULL_UB=bank.fields(),
            source_sha=source_records(), solver_Start_processing_not_run=True))
        return native
    if mode not in ("warm", "cold"):
        raise ValueError("UNKNOWN_PR222_REGRESSION_MODE")
    result, point = optimize_mess(case, initial, registry, budget)
    _write(attempt / "PR222_REGRESSION.json", dict(result=result,
        warm_restoration=mode == "warm", cold_historical_raw_witness_omitted=mode == "cold",
        source_files_after=source_records(), campaign_HOLD_preserved=True,
        old_B2_May01_Native_seconds=1003.5010001659393,
        old_B2_May02_Native_seconds=943.4019999504089,
        historical_ledgers_modified=False, new_QoS_case_UB_transfer=False))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("native0", "warm", "cold", "binding"), required=True)
    parser.add_argument("--seconds", type=float, default=60.)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--ledger", type=Path)
    parser.add_argument("--day", default="2025-05-01")
    args = parser.parse_args()
    result = run(args.mode, args.seconds, args.output, args.ledger, args.day)
    print(json.dumps(dict(PASS=result.get("PASS"), status=result.get("status"),
                         FULL_validated=result.get("FULL_validated"),
                         Native_Runtime=result.get("stage_solve_seconds")), ensure_ascii=False))


if __name__ == "__main__":
    main()
