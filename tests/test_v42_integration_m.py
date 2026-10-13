"""Boundary regressions: Raw authority, direct transport and stage isolation."""
from copy import deepcopy
from fractions import Fraction
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import numpy as np
import pytest
from scipy import sparse

from v42_integration.m_engine import (
    IncumbentBank, PathGraph, _start_classification, admit_registry, binding,
    direct_joint, file_record, optimize_mess, pin_pools, strict_full, vector_sha,
)


class Move:
    def __init__(self, source, depart, destination, connect):
        self.source, self.depart, self.destination, self.connect = source, depart, destination, connect
        self.energy_kwh = 1.

    def validate(self, horizon):
        assert 0 <= self.depart < self.connect <= horizon


class Budget:
    def __init__(self, remaining=0.):
        self.value = remaining
        self.calls = []

    def remaining(self):
        return self.value

    def used(self):
        return 0.


def fixture(folder):
    units = [f"MESS{u:02d}" for u in range(1, 5)]
    arcs = [(site, t, site, t + 1, None) for site in ("A", "B") for t in range(4)]
    arcs += [("A", 0, "B", 1, Move("A", 0, "B", 1)),
             ("B", 2, "A", 3, Move("B", 2, "A", 3))]
    names = ["rho_max"]
    for unit in units:
        names.extend(f"arc[{unit},{k}]" for k in range(len(arcs)))
        names.extend(f"node_activity[{unit},{site},{t}]" for site in ("A", "B") for t in range(5))
        names.extend(f"charge_mode[{unit},{t}]" for t in range(4))
        names.append(f"Pdis[{unit},0]")
    n = len(names)
    index = {name: j for j, name in enumerate(names)}
    types = np.array(["C" if name == "rho_max" or name.startswith("Pdis[") else "B" for name in names])
    lower, upper, objective = np.zeros(n), np.ones(n), np.zeros(n)
    upper[0], objective[0] = 10., 1.
    rows, rhs, senses, rownames = [], [], [], []
    for unit in units:
        for site in ("A", "B"):
            for t in range(5):
                terms = {}
                for k, arc in enumerate(arcs):
                    j = index[f"arc[{unit},{k}]"]
                    if arc[:2] == (site, t):
                        terms[j] = terms.get(j, 0.) + 1.
                    if arc[2:4] == (site, t):
                        terms[j] = terms.get(j, 0.) - 1.
                if t < 4:
                    target = 1. if site == "A" and t == 0 else 0.
                    rows.append(terms)
                    rhs.append(target)
                    senses.append("=")
                    rownames.append(f"flow[{unit},{site},{t}]")
                else:
                    # Allow either end site; nodes preserve terminal occupancy.
                    pass
    rows.append({0: -1., index["arc[MESS03,0]"]: 2.})
    rhs.append(-1.)
    senses.append("<")
    rownames.append("thermal_peak")
    rr, cc, vv = [], [], []
    for i, terms in enumerate(rows):
        for j, value in terms.items():
            if value:
                rr.append(i); cc.append(j); vv.append(value)
    A = sparse.csr_matrix((vv, (rr, cc)), shape=(len(rows), n))
    d = dict(names=np.array(names), types=types, lower=lower, upper=upper,
             objective=objective, constant=np.array(0.), rhs=np.array(rhs),
             sense=np.array(senses), row_names=np.array(rownames))
    battery = SimpleNamespace(initial=5., terminal=5., minimum=0., maximum=10.,
                              dt_hours=.25, eta_charge=.9, eta_discharge=.9, p_limit=1.)
    case = SimpleNamespace(A=A, d=d, original_A=A, original_d=d,
        graph=(["A", "B"], {u: "A" for u in units}, arcs, battery, {}),
        lift=lambda point: point.copy(), case_sha="fixture_case", bundle={"day": "2025-05-01"},
        output=Path(folder), identity=dict(arm="B3", stage="M1", aidc_anchor="A1_SHA", qos_sha="QOS_SHA"))
    def point(moving=False, rho=None):
        x = np.zeros(n)
        x[0] = (2. if moving else 3.) if rho is None else rho
        graph = PathGraph(case)
        for unit in units:
            path = graph.complete(unit, [8, 9] if moving and unit == "MESS03" else [])
            vertices = {arcs[k][:2] for k in path} | {(arcs[path[-1]][2], 4)}
            for k in path:
                x[index[f"arc[{unit},{k}]"]] = 1.
            for site, t in vertices:
                x[index[f"node_activity[{unit},{site},{t}]"]] = 1.
        return x
    case.strict_validator = validator
    return case, point


def validator(case, path, evidence):
    from v42_m1_research.check_ub import matrix_replay
    with np.load(path, allow_pickle=False) as z:
        assert z.files == ["point"]
        point = z["point"].copy()
    checked = matrix_replay(case.A, case.d, point)
    if not checked["PASS"] or not checked["integer_pattern_exact"]:
        raise ValueError("FIXTURE_FULL_REPLAY_REJECTED")
    return dict(PASS=True, Global_UB=float(point[0]), exact_Global_UB=str(Fraction(float(point[0]))),
                point_vector_sha256=vector_sha(point),
                strict_raw_C3A_and_FULL_integer_and_binary_pattern_exact=True,
                original_matrix_and_96_slot_physical_replay=dict(PASS=True, case_sha=case.case_sha))


def cert(case, point):
    path = case.output / "TEMP.npz"
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, point=point)
    return validator(case, path, {})


def test_global_moving_best_survive_worse_seed_and_capture(tmp_path):
    case, point = fixture(tmp_path)
    bank = IncumbentBank(case)
    bank.offer(point(True), cert(case, point(True)))
    bank.offer(point(False, 4.), cert(case, point(False, 4.)))
    assert bank.fields() == dict(BEST_GLOBAL_UB=2., BEST_MOVING_FEASIBLE_UB=2.)
    bank.offer(point(False, 3.), cert(case, point(False, 3.)))
    assert bank.best[0][0] == 2.
    bad = cert(case, point(False))
    bad["original_matrix_and_96_slot_physical_replay"]["case_sha"] = "other_case"
    with pytest.raises(ValueError, match="CURRENT_RAW_FULL"):
        bank.offer(point(False), bad)


def test_registry_rejects_new_qos_anchor_date_and_changed_bytes(tmp_path):
    case, point = fixture(tmp_path)
    bank = IncumbentBank(case)
    bank.offer(point(True), cert(case, point(True)))
    key = binding(case)
    records = bank.save(tmp_path, key)
    assert len(admit_registry(case, records, tmp_path / "OK", validator, key)) == 2
    for field in ("day", "qos_sha", "aidc_anchor"):
        drift = dict(key, **{field: "different"})
        assert admit_registry(case, records, tmp_path / field, validator, drift) == []
    np.savez_compressed(records[0]["raw"]["path"], point=point(False))
    assert admit_registry(case, records[:1], tmp_path / "bytes", validator, key) == []


def test_full_complete_winner_is_pinned_and_stay_is_also_selectable(tmp_path):
    case, point = fixture(tmp_path)
    bank = IncumbentBank(case)
    bank.offer(point(True), cert(case, point(True)))
    pools = pin_pools(case, point(False), bank)
    graph = PathGraph(case)
    assert graph.complete("MESS03", [8, 9]) in pools["MESS03"]
    assert graph.complete("MESS03") in pools["MESS03"]
    # Separate legal moves are not a substitute for the complete path.
    broken = dict(pools, MESS03=[[8], [9]])
    with pytest.raises(ValueError):
        direct_joint(case, point(True), broken)


def test_exact_direct_substitution_preserves_rows_modes_and_raw_start(tmp_path):
    case, point = fixture(tmp_path)
    bank = IncumbentBank(case)
    bank.offer(point(True), cert(case, point(True)))
    pools = pin_pools(case, point(True), bank)
    A, d, lift, start, proof = direct_joint(case, point(True), pools)
    assert proof["PASS"] and proof["original_charge_modes_retained"] == 16
    assert A.shape[0] == case.A.shape[0] + 4
    assert np.array_equal(lift @ start, point(True))
    assert np.array_equal(d["rhs"][:-4], case.d["rhs"])
    assert np.array_equal(d["sense"][:-4], case.d["sense"])
    assert (A[:-4] != case.A @ lift).nnz == 0
    K = len(proof["keep_columns"])
    z = start.copy()
    z[0] = 3.
    for i, entry in enumerate(proof["lambda_axis"]):
        z[K+i] = float(entry["path"] == PathGraph(case).complete(entry["unit"]))
    projected = lift @ z
    assert np.array_equal(projected, point(False))
    assert np.allclose(A @ z, np.r_[case.A @ projected, np.ones(4)])


def test_initial_registry_replay_precedes_cold_and_initial_is_not_mutated(tmp_path):
    case, point = fixture(tmp_path)
    bank = IncumbentBank(case)
    bank.offer(point(True), cert(case, point(True)))
    records = bank.save(tmp_path, binding(case))
    initial = point(False)
    saved = initial.copy()
    case.cold_initializer = lambda *args: (_ for _ in ()).throw(AssertionError("warm must bypass cold"))
    result, accepted = optimize_mess(case, initial, records, Budget())
    assert np.array_equal(initial, saved)
    assert accepted[0] == 2.
    assert result["BEST_GLOBAL_UB"] == 2.
    assert result["FULL_validated"] and not result["execution_completion"]
    assert not result["global_gap_certified"] and result["gap_status"] == "NOT_CERTIFIED"
    assert not result["cold_initializer_used"]


def test_raw_route_metadata_is_rejected_not_silently_folded_into_point(tmp_path):
    case, point = fixture(tmp_path)
    packet = tmp_path / "BAD.npz"
    np.savez_compressed(packet, point=point(False), route_selection=np.array([1., 0.]))
    with pytest.raises(ValueError, match="RAW_POINT_PACKET_AXIS_DRIFT"):
        strict_full(case, packet)


def test_start_no_new_incumbent_is_not_automatically_failure():
    messages = ["User MIP start did not produce a new incumbent solution"]
    assert _start_classification(messages, dict(executed=True, current_pool_ObjVal=1.), 2.) == \
        "NO_NEW_INCUMBENT_EQUAL_OR_BETTER_PRESENT"
    assert _start_classification(messages, dict(executed=True, current_pool_ObjVal=None), 2.) == \
        "NO_NEW_INCUMBENT_CAUSE_NOT_ESTABLISHED"
    assert _start_classification([], dict(executed=False), 2.) == "ATTRIBUTE_READBACK_ONLY"


def test_cold_beam_uses_complete_current_dag_without_archive_or_solver(tmp_path, monkeypatch):
    from v42_integration import m_candidates
    case, point = fixture(tmp_path)
    case.graph[3].terminal = 3.
    bank = IncumbentBank(case)
    bank.offer(point(False), cert(case, point(False)))
    context = dict(rows=[dict(slot=t, current_loading=3., coeff={'rho_max': '-1'}, rhs='-3')
                         for t in range(4)])
    # These explicit fixture contexts exercise route grammar only. They are
    # not claimed as real current-grid source projections or physical solves.
    monkeypatch.setattr(m_candidates, 'grid_context', lambda *args: context)
    monkeypatch.setattr(m_candidates, 'pcs_vertices', lambda *args: np.array([[-1., -1.], [-1., 1.], [1., -1.], [1., 1.]]))
    pools = m_candidates.generate(case, point(False), bank, Budget())
    graph = PathGraph(case)
    for unit, paths in pools.items():
        assert graph.complete(unit) in paths
        assert all(graph.validate(unit, path) for path in paths)
        assert any(sum(graph.arcs[k][-1] is not None for k in path) >= 2 for path in paths)
    receipt = json.loads((case.output/'COMMON_M_PR222/FRESH_BEAM_AND_REDISPATCH_ADMISSION.json').read_text())
    assert receipt['LP_calls'] == 0
    assert not receipt['historical_Raw_read'] and not receipt['archived_candidate_pool_read']
    assert receipt['no_MOVE_forcing']


@pytest.mark.parametrize("arm,stage", [("B2", "M"), ("B3", "M1"), ("B3", "M2")])
def test_same_common_core_records_stage_specific_anchor(tmp_path, arm, stage):
    case, point = fixture(tmp_path)
    case.identity.update(arm=arm, stage=stage, aidc_anchor=stage + "_AIDC")
    result, accepted = optimize_mess(case, point(False), [], Budget())
    assert result["arm"] == arm and result["stage"] == stage
    assert result["binding"]["aidc_anchor"] == stage + "_AIDC"
    assert result["engine_version"] == "PR222_CASE_EXPLICIT_EXACT_DIRECT_JOINT_V1"
    assert result["P2_calls"] == 0 and result["AIDC_optimization_calls"] == 0
