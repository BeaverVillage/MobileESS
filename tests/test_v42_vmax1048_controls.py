"""Original body/namespace isolation and immutable control observation evidence."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest

from v42_vmax1048 import actual_controls as controls


def _original_voltage(engine, nodes):
    return nodes


def _original_backend(engine, trajectory, slots=96):
    # Preserve a trajectory+slot frame as the real original 96-slot body does.
    backend = sys.modules["dayahead.v28r2.opendss_backend"]
    result=[]
    for slot in range(slots):
        result.append(backend._voltage_vector(engine, (slot,)))
    return result


def _original_fresh():
    return None


def _parameter_projection(inventory):
    return {"regulators": [{"name": r["name"], "voltage": r["voltage"]}
        for r in inventory["regulators"]], "max_control_iterations": inventory["max_control_iterations"]}


@pytest.fixture
def original(monkeypatch):
    expected = dict(regulators=[dict(name="creg"+str(i), initial_tap=1., enabled=True, voltage=120.) for i in range(7)],
        CapControl_count=0, solution_mode=0, max_control_iterations=100)
    state = dict(inventory=deepcopy(expected), taps=[1.0125]*7, caps=[1,1,1,1], done=True)
    def assert_inventory(inv):
        if not all(r["enabled"] for r in inv["regulators"]):
            raise ValueError("SOURCE_REGCONTROL_DISABLED")
        if _parameter_projection(inv) != _parameter_projection(expected):
            raise ValueError("SOURCE_REGCONTROL_PARAMETER_OR_MODE_DRIFT")
    source = dict(expected=expected, inventory=lambda engine:state["inventory"],
        native_state=lambda engine:(state["taps"],state["caps"]))
    authority = SimpleNamespace(source=lambda:source, assert_inventory=assert_inventory,
        regulator_parameters=_parameter_projection,
        digest=lambda value:hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest())
    backend = SimpleNamespace(run_fresh_opendss=_original_backend, _voltage_vector=_original_voltage)
    modules = {
        "v42_regcontrol": dict(authority=authority),
        "v42_may_campaign_native90": dict(operations=SimpleNamespace(fresh=_original_fresh)),
        "dayahead": {},
        "dayahead.v28r2": dict(opendss_backend=backend, opendss_mapping=SimpleNamespace(apply_trajectory_slot=_original_fresh)),
        "v42_pr134_b1": dict(replay=SimpleNamespace(fresh=_original_fresh)),
    }
    for name, attributes in modules.items():
        module=ModuleType(name);module.__dict__.update(attributes);monkeypatch.setitem(sys.modules,name,module)
    monkeypatch.setitem(sys.modules,"dayahead.v28r2.opendss_backend",backend)
    solution = SimpleNamespace(ControlActionsDone=lambda:state["done"], Converged=lambda:True,
        ControlIterations=lambda:5, Iterations=lambda:17, TotalIterations=lambda:17,
        MostIterationsDone=lambda:7, MaxControlIterations=lambda:100, MaxIterations=lambda:15, ControlMode=lambda:0)
    return backend, SimpleNamespace(Solution=solution), state


def trajectory(namespace):
    return SimpleNamespace(day="2025-05-01",case="B2",namespace=namespace)


def test_capture_only_original_actual_body_and_preserve_values(original,tmp_path):
    backend, engine, state=original
    original_code=backend.run_fresh_opendss.__code__
    with controls.observer_context(tmp_path,source_SHA="a"*64) as observer:
        assert backend.run_fresh_opendss(engine,trajectory("DAYAHEAD")) == [(i,) for i in range(96)]
        assert not observer.rows
        assert backend.run_fresh_opendss(engine,trajectory("ACTUAL")) == [(i,) for i in range(96)]
    assert backend._voltage_vector is _original_voltage
    assert backend.run_fresh_opendss.__code__ is original_code
    result=json.loads((tmp_path/"ACTUAL_FRESH_CONTROL_OBSERVER.json").read_text())
    assert result["PASS"] and result["slots"]==96
    assert result["max_observed_Solution_Iterations_total"]==17
    assert result["max_observed_Solution_MostIterationsDone_per_control_pass"]==7
    assert result["configured_MaxIterations"]==[15]
    assert result["execution_source_SHA"]=="a"*64
    assert result["original_source_SHA_before_after_equal"]
    assert observer.rows[0]["previous_taps"]==[1.]*7
    assert observer.rows[1]["tap_changes"]==[0.]*7
    assert observer.rows[0]["regulator_enabled"]==[True]*7
    assert state["taps"]==[1.0125]*7 and state["caps"]==[1,1,1,1]


def test_control_failure_preserves_error_and_partial_observation(original,tmp_path):
    backend, engine, state=original
    with pytest.raises(ValueError,match="CONTROLS_NOT_COMPLETE"):
        with controls.observer_context(tmp_path):
            backend.run_fresh_opendss(engine,trajectory("ACTUAL"),slots=1)
            state["done"]=False
            backend.run_fresh_opendss(engine,trajectory("ACTUAL"),slots=1)
    assert backend._voltage_vector is _original_voltage
    result=json.loads((tmp_path/"ACTUAL_FRESH_CONTROL_OBSERVER.json").read_text())
    assert result["status"]=="INCOMPLETE_OR_FAILED" and result["slots"]==1 and not result["PASS"]


def test_original_parameter_drift_is_rejected(original,tmp_path):
    backend, engine, state=original
    state["inventory"]["regulators"][0]["voltage"]=121.
    with pytest.raises(ValueError,match="PARAMETER_OR_MODE_DRIFT"):
        with controls.observer_context(tmp_path):
            backend.run_fresh_opendss(engine,trajectory("ACTUAL"))
    result=json.loads((tmp_path/"ACTUAL_FRESH_CONTROL_OBSERVER.json").read_text())
    assert not result["PASS"] and result["slots"]==0


def test_planning_failure_reports_actual_not_run_and_prevents_overwrite(original,tmp_path):
    with controls.observer_context(tmp_path):
        pass
    result=json.loads((tmp_path/"ACTUAL_FRESH_CONTROL_OBSERVER.json").read_text())
    assert result["status"]=="NOT_RUN" and result["max_observed_ControlIterations"] is None
    with pytest.raises(PermissionError,match="OVERWRITE_FORBIDDEN"):
        with controls.observer_context(tmp_path):
            pass


def test_changed_original_source_receipt_cannot_pass(original,tmp_path):
    backend, engine, state=original
    path=tmp_path/"source.py";path.write_text("first",encoding="utf8")
    with controls.observer_context(tmp_path/"observer") as observer:
        observer.sources.append(controls._receipt(path))
        backend.run_fresh_opendss(engine,trajectory("ACTUAL"))
        path.write_text("second",encoding="utf8")
    result=json.loads((tmp_path/"observer/ACTUAL_FRESH_CONTROL_OBSERVER.json").read_text())
    assert not result["PASS"] and not result["original_source_SHA_before_after_equal"]
