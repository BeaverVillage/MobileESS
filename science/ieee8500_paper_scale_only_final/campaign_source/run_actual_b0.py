"""One original-controller B0 Actual replay after B0 DA exact PASS."""
import importlib.util
import json
import os
import sys
import traceback
from pathlib import Path

BASE = Path(__file__).absolute().parent
SOURCE = BASE / "validate_actual_final.py"
sys.path.insert(0, str(BASE))
spec = importlib.util.spec_from_file_location("paper_final_actual_b0", SOURCE)
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)


def main():
    assert v.read(BASE / "B0/COMPLETE.json")["status"] == "PASS"
    out = BASE / "Actual"
    assert not out.exists(), "B0 Actual already started in this production namespace"
    out.mkdir()
    v.H = out
    v.selected = lambda: {"B0": (v.read(BASE / "REFERENCE_JOBS.json"), [])}
    (out / "BATTERY_EFFICIENCY_AUTHORITY.json").write_bytes(
        (v.METHOD / "BATTERY_EFFICIENCY_AUTHORITY.json").read_bytes())
    files = [SOURCE, Path(__file__), BASE / "B0/COMPLETE.json",
             BASE / "FINAL_CANDIDATE_FREEZE.json", BASE / "electrical_engine.py",
             BASE / "PCC_Master.dss", BASE / "IEEE8500_PCC_Overlay.dss",
             BASE / "PCC_OVERLAY_INVENTORY.json", BASE / "REFERENCE_JOBS.json",
             BASE / "AIDC_2X_AUTHORITY.json", BASE / "HEADROOM_AUTHORITY.json",
             BASE / "D1_AEMO_VIC1_FORECAST.json", BASE / "SCREENING_RULE.json",
             BASE / "actual_power_binding.py", v.METHOD / "robust_search.py",
             v.METHOD / "frozen_code/qsafe.py"]
    v.save(out / "RULE_FREEZE.json", dict(
        status="FROZEN_BEFORE_ACTUAL", policy="B0", date="2025-05-01",
        BG_scale=.552, AIDC_absolute_scale=2.4, MESS_scale=2.,
        Actual_controller="original violation-triggered Q-only robust V2",
        source_files=[v.rec(path) for path in files],
        scheduling_optimizer_calls=0))
    v.verify()
    v.protect()
    ns = v.kernel()
    import dayahead.v40d_actual.mobility_inputs as mobility
    historical_repo = Path("C:/codex_mobileess_workspace/MobileESS_v40a_bounded_iterative_coopt")
    aliases = {
        str(historical_repo / "dayahead/v35/execution.py"):
            (Path("C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance/dayahead/v35/execution.py"),
             "dd50172ebc176a638421174c620694bd0f6180d6f714739dc485706ebf90c1da"),
        str(historical_repo / "dayahead/mess_physics.py"):
            (Path("C:/codex_mobileess_workspace/MobileESS_v41r2_780gpu_capacity_rebase/dayahead/mess_physics.py"),
             "d7bac71fb7522a8c94cf181b3a3ca8dcf1034b8faa6cf561ad3663ef2726a50b"),
    }
    original_reference = mobility.reference
    def reference(path):
        path = Path(path)
        if path.exists():
            return original_reference(path)
        local, expected = aliases[str(path)]
        assert v.sha(local) == expected
        return dict(path=str(path), sha256=expected, bytes=local.stat().st_size)
    mobility.reference = reference
    v.save(out / "HISTORICAL_READ_ALIASES.json", dict(status="BYTE_IDENTICAL_READ_ONLY",
        aliases={name: dict(local_copy=str(local), sha256=digest)
                 for name, (local, digest) in aliases.items()}))
    import gurobipy as gp
    gp.Model.optimize = lambda *args, **kwargs: (_ for _ in ()).throw(
        RuntimeError("DA_OPTIMIZER_FORBIDDEN_IN_ACTUAL"))
    authority = v.inputs(ns)
    assert (out / "B0/INPUT_READY.json").exists()
    v.run_policy("B0", ns, authority)
    v.verify()
    result = v.read(out / "B0/COMPLETE.json")
    assert result["AC_feasible"] and result["scheduling_optimizer_calls"] == 0
    v.save(out / "B0_GATE.json", dict(status="PASS", result=v.rec(out / "B0/COMPLETE.json"),
                                     controller_parity_authority=v.rec(BASE.parent / "ACTUAL_PIPELINE_PARITY_FREEZE.json")))
    print("B0_ACTUAL_PASS", result["summary"]["max_phase_line_loading_pu"], flush=True)


if __name__ == "__main__":
    try:
        main()
    except BaseException as exc:
        out = BASE / "Actual"
        out.mkdir(exist_ok=True)
        (out / "B0_FAILURE.json").write_text(json.dumps(dict(error=repr(exc),
            traceback=traceback.format_exc()), indent=2), encoding="utf-8")
        raise
