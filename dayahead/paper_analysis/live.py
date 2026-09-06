"""Opt-in process-local observers around the unchanged production functions.

Observers read results/attributes only. Their writes fail closed. No model
parameter, control, candidate, route, or OpenDSS command is changed.
"""
from contextlib import contextmanager
import math
import os
from pathlib import Path
import numpy as np
from .storage import STAGES, MISSING, digest, write_json, write_npz, write_parquet

_CHILD_CONTEXT = None


def child_initialize(root, initializer, initargs):
    from dayahead.v40a import observability
    observability.initialize(root, initializer, initargs)
    _enter_child()


def baseline_child_initialize(initializer, initargs):
    from dayahead.v39e.runtime import initialize_runtime_worker
    initialize_runtime_worker(initializer, initargs)
    _enter_child()


def _enter_child():
    global _CHILD_CONTEXT
    root = os.environ.get("MOBILEESS_PAPER_CAPTURE_ROOT")
    if not root:
        raise RuntimeError("RESULT_PERSISTENCE_FAIL:CHILD_CAPTURE_ROOT_MISSING")
    _CHILD_CONTEXT = capture(Path(root), child=True)
    _CHILD_CONTEXT.__enter__()


def model_record(model, stage, index):
    def attr(name, owner=None):
        try:
            value = getattr(owner if owner is not None else model, name)
            if isinstance(value, float) and not math.isfinite(value):
                return MISSING
            return value
        except (AttributeError, RuntimeError):
            return MISSING
        except Exception as error:
            # Gurobi reports unavailable attributes through GurobiError.
            if type(error).__name__ == "GurobiError":
                return MISSING
            raise
    row = {"solver": "Gurobi", "pid": os.getpid(), "optimize_call_index": index,
        "internal_stage": stage, "paper_stage": STAGES.get(stage, stage)}
    for field, name in (("status", "Status"), ("incumbent", "ObjVal"), ("bound", "ObjBound"),
        ("gap", "MIPGap"), ("node_count", "NodeCount"), ("work", "Work"), ("runtime", "Runtime"),
        ("solution_count", "SolCount"), ("model_name", "ModelName")):
        row[field] = attr(name)
    for name in ("Threads", "WorkLimit", "TimeLimit", "Seed", "MIPGap", "MIPGapAbs", "FeasibilityTol", "OptimalityTol", "IntFeasTol"):
        row[name] = attr(name, model.Params)
    return row


@contextmanager
def capture(root, *, child=False):
    import gurobipy as gp
    from dayahead.v40a import observability, grid
    from dayahead.v39e import runtime
    from dayahead.v28r2 import opendss_backend as backend
    from .numeric_snapshot import grid_arrays
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    previous_env = os.environ.get("MOBILEESS_PAPER_CAPTURE_ROOT")
    os.environ["MOBILEESS_PAPER_CAPTURE_ROOT"] = str(root)
    saved = (gp.Model.optimize, observability._original, observability.initialize,
             runtime.initialize_runtime_worker, grid.evaluate_grid,
             backend.run_fresh_opendss, backend._voltage_vector, backend._branch_measurement, backend._native_state)
    counts = {"solver": 0, "grid": 0, "fresh": 0}
    active = None
    # Respect an outer execution guard (Actual forbids optimization entirely).
    original_optimize = observability._original if gp.Model.optimize is observability.counted_optimize else gp.Model.optimize

    def optimize(model, *args, **kwargs):
        try:
            return original_optimize(model, *args, **kwargs)
        finally:
            counts["solver"] += 1
            stage = observability._stage if observability._stage != "UNSPECIFIED" else ("M1" if child else "UNSPECIFIED")
            record = model_record(model, stage, counts["solver"])
            # Candidate identity remains its literal model name; no guessed beam state.
            record.update(candidate_ID=record["model_name"], K_level=MISSING, beam_state=MISSING)
            write_json(root / "solver" / f"{os.getpid()}_{counts['solver']:07d}.json", record)

    def evaluate(coefficients, controls, nodes, *args, **kwargs):
        result = saved[4](coefficients, controls, nodes, *args, **kwargs)
        counts["grid"] += 1
        key = digest({"controls": controls, "coefficients": [c.coefficient_sha256 for c in coefficients]})
        destination = root / "planning" / key
        write_npz(destination / "raw_arrays.npz", **grid_arrays(coefficients, controls, nodes))
        write_json(destination / "summary.json", result)
        return result

    def voltage(odd, nodes):
        result = saved[6](odd, nodes)
        if active is not None:
            active["slot"] += 1
        return result

    def branch(odd, b):
        result = saved[7](odd, b)
        if active is not None:
            nc = int(odd.CktElement.NumConductors())
            buses = [str(v).split(".")[0].lower() for v in odd.CktElement.BusNames()]
            terminal = buses.index(str(b.parent_bus).lower())
            order = list(odd.CktElement.NodeOrder())
            phase = "ABC".index(b.phase)+1
            local = next(k for k in range(nc) if order[terminal*nc+k] == phase)
            powers = odd.CktElement.Powers()
            position = terminal*nc+local
            rating_kva = None
            if b.branch_id.startswith("transformer."):
                rating_kva = float(odd.Transformers.kVA())
                rating_a = rating_kva/(float(odd.Transformers.kV())*(math.sqrt(3) if odd.CktElement.NumPhases()>=2 else 1))
            else:
                rating_a = float(odd.Lines.NormAmps())
            active["branches"].append({"slot": active["slot"], "branch_id": b.branch_id, "phase": b.phase,
                "sending_bus": b.parent_bus, "receiving_bus": b.child_bus,
                "P_flow_kW": float(powers[2*position]), "Q_flow_kvar": float(powers[2*position+1]),
                "I_amp": result[0], "rating_amp": rating_a, "I_loading_pu": result[1],
                "rating_kVA": rating_kva, "total_kVA": result[2]*rating_kva if rating_kva is not None else None})
        return result

    def native(odd):
        result = saved[8](odd)
        if active is not None:
            active["feeder_power"].append(list(map(float, odd.Circuit.TotalPower())))
        return result

    def fresh(**kwargs):
        nonlocal active
        parent = active
        active = {"slot": -1, "branches": [], "feeder_power": []}
        try:
            result = saved[5](**kwargs)
            counts["fresh"] += 1
            destination = root / "fresh" / f"{os.getpid()}_{counts['fresh']:04d}"
            import pandas as pd
            if active["slot"] != 95 or len(active["feeder_power"]) != 96:
                raise RuntimeError("RESULT_PERSISTENCE_FAIL:FRESH_CAPTURE_INCOMPLETE")
            frame = pd.DataFrame(active["branches"])
            nodes = {n.lower(): i for i, n in enumerate(result.node_names)}
            for field, bus_field in (("V_send_pu", "sending_bus"), ("V_recv_pu", "receiving_bus")):
                frame[field] = [result.voltage_pu[r.slot, nodes[str(getattr(r,bus_field)).lower()+"."+str("ABC".index(r.phase)+1)]]
                                for r in frame.itertuples(index=False)]
            frame["delta_V_pu"] = frame.V_send_pu-frame.V_recv_pu
            frame["abs_delta_V_pu"] = frame.delta_V_pu.abs()
            write_parquet(destination / "branch_power_flow.parquet", frame)
            trajectory = kwargs["trajectory"]
            write_npz(destination / "feeder_and_injections.npz", feeder_P_Q_opendss_sign=np.asarray(active["feeder_power"]),
                AIDC_P=trajectory.pcc_p_kw, AIDC_Q=trajectory.pcc_q_kvar,
                MESS_P=trajectory.mess_p_kw, MESS_Q=trajectory.mess_q_kvar,
                MESS_locations=trajectory.mess_locations_96x4, losses=result.losses_kw_kvar)
            result.write(destination)
            write_json(destination / "capture_provenance.json", {"schedule_sha256": result.schedule_sha256,
                "namespace": result.namespace, "day": result.day, "case": result.case,
                "trajectory_identity_before_after": trajectory.immutable_sha256,
                "extra_OpenDSS_commands": 0, "extra_Solve_calls": 0})
            return result
        finally:
            active = parent

    gp.Model.optimize = optimize
    observability._original = optimize
    observability.initialize = child_initialize
    runtime.initialize_runtime_worker = baseline_child_initialize
    grid.evaluate_grid = evaluate
    backend.run_fresh_opendss = fresh
    backend._voltage_vector = voltage
    backend._branch_measurement = branch
    backend._native_state = native
    try:
        yield counts
    except BaseException as error:
        write_json(root / f"CAPTURE_STATUS_{os.getpid()}.json", {"status": "RESULT_PERSISTENCE_FAIL", "error": repr(error), "counts": counts})
        raise
    else:
        write_json(root / f"CAPTURE_STATUS_{os.getpid()}.json", {"status": "PASS", "counts": counts})
    finally:
        (gp.Model.optimize, observability._original, observability.initialize, runtime.initialize_runtime_worker,
         grid.evaluate_grid, backend.run_fresh_opendss, backend._voltage_vector,
         backend._branch_measurement, backend._native_state) = saved
        if previous_env is None:
            os.environ.pop("MOBILEESS_PAPER_CAPTURE_ROOT", None)
        else:
            os.environ["MOBILEESS_PAPER_CAPTURE_ROOT"] = previous_env
