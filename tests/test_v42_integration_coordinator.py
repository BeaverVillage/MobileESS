"""Static/full-matrix common coordinator boundaries; no fake Optimize claims."""
from dataclasses import replace
import json

import numpy as np
import pytest

from v42_integration.a_engine import authorized_data
from v42_integration.coordinator import run_arm, verify_sources, _full_m
from v42_integration.fixture_validation import build_fixture, miniature_m, fixture_full_validator, native0
from v42_integration.m_engine import direct_joint, pin_pools, IncumbentBank, _native_joint
from v42_a_stage_domain_v2.stay_projection import incidence, lift_counts, project_extended, reconstruct_counts


class NoSolveBudget:
    """Deliberately no remaining solve budget; never represents an execution."""
    def remaining(self): return 0.
    def used(self): return 0.


class Native0Budget:
    def remaining(self): return 1.
    def used(self): return 0.


def test_native0_builds_original_a_and_m_readback_with_no_optimize(tmp_path):
    receipt = native0(tmp_path/"NATIVE0")
    assert receipt["optimizer_calls"] == receipt["M"]["Native_optimize_calls"] == 0
    assert receipt["A"]["rows"] > 0 and receipt["A"]["anonymous_variable_count"] == 192
    assert receipt["direct_proof"]["original_charge_modes_retained"] == 16
    assert receipt["direct_proof"]["original_source_rows_semantically_preserved"] > 100
    assert receipt["full_end_to_end"] == "NOT_EXECUTED"


def test_qos_contract_class_aggregation_and_histogram_original_rows(tmp_path):
    case = build_fixture(tmp_path/"INPUT")
    a_case = case.make_a_case("B1", "A1", case.initial_mess, tmp_path/"A")
    data, domains = authorized_data(a_case)
    assert len(data[7]["classes"]) == 1
    job = data[1]["known-a"]
    starts = [(site,start) for start,site in domains["known-a"].stays]
    spec = incidence(job, starts, 2, "same_contract")
    # Every integer class assignment has the same original GPU/service and
    # intervention projection after lossless count compression and restore.
    for first in spec.starts:
        for second in spec.starts:
            counts = {key: int(key==first)+int(key==second) for key in spec.starts}
            point = lift_counts(spec, counts, integral=True)
            assert project_extended(spec, point, integral=True) == point["y"]
            plans = reconstruct_counts(spec, counts)
            assert len(plans) == 2
            assert sum(b-a for plan in plans for site,a,b in plan.segments) == 2
            assert sum(point["r0"].values())*job.gpu == 2
    changed = dict(a_case.window_slots, **{"known-b": (24,)})
    different, _ = authorized_data(replace(a_case, window_slots=changed))
    assert len(different[7]["classes"]) == 2
    assert all(len(v)==1 for v in different[7]["classes"].values())


def test_toy_full_soc_mode_rows_and_literal_start_transport(tmp_path):
    case, point = miniature_m(tmp_path, "AIDC_FULL_ANCHOR")
    np.savez_compressed(tmp_path/"RAW.npz", point=point)
    cert = fixture_full_validator(case, tmp_path/"RAW.npz")
    bank = IncumbentBank(case); bank.offer(point, cert)
    pools = pin_pools(case, point, bank, case.candidate_pools)
    A, d, lift, start, proof = direct_joint(case, point, pools)
    assert np.array_equal(lift@start, point)
    assert np.array_equal(A@start, np.r_[case.A@point, np.ones(4)])
    assert proof["original_charge_modes_retained"] == 16
    assert sum(str(name).startswith("SOC_balance") for name in case.d["row_names"]) == 16
    exported = case.plan_exporter(case, point)
    assert _full_m(dict(FULL_validated=True, mess=exported)) == exported
    assert all(len(values)==96 for values in exported["P_by_site"].values())
    assert exported["physical_fixture_slots"] == 4


def test_b0_b2_same_common_actual_and_b2_common_m_native0(tmp_path):
    result = {}
    for arm in ("B0", "B2"):
        case = build_fixture(tmp_path/(arm+"_INPUT"))
        producer = case.make_m_case
        def readback_case(*args):
            current = producer(*args)
            def readback(current, budget, packet, folder, seconds):
                return _native_joint(current, budget, packet, folder, 0., native0=True)
            current.joint_solver = readback
            return current
        case.make_m_case = readback_case
        result[arm] = run_arm(arm, case, Native0Budget(), tmp_path/arm)
    assert np.array_equal(result["B0"]["actual"]["occupancy_GPU"], result["B2"]["actual"]["occupancy_GPU"])
    assert result["B0"]["actual"]["queue_ledger"] == result["B2"]["actual"]["queue_ledger"]
    assert result["B2"]["stages"]["M1"]["engine_version"] == "PR222_CASE_EXPLICIT_EXACT_DIRECT_JOINT_V1"
    assert not result["B2"]["stages"]["M1"]["execution_completion"]
    assert result["B2"]["stages"]["M1"]["native_call"]["Native_optimize_calls"] == 0
    # Literal Gurobi model/Start readback is not an Optimize execution.


def test_source_drift_rejected_before_case_execution(tmp_path):
    case = build_fixture(tmp_path/"INPUT")
    expected = case.input_receipts[0]
    with open(expected["path"], "a", encoding="utf8") as stream:
        stream.write("\n ")
    with pytest.raises(ValueError, match="FROZEN_INPUT_OR_SOURCE_DRIFT"):
        verify_sources(case.source_freeze, case.input_receipts)
