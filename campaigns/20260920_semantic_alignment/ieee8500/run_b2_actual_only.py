"""IEEE8500 May-1 B2 Actual-only Q recourse on frozen physical execution."""
import os
for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[name] = "4"
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PROD = ROOT / "IEEE8500_FINAL_MAY01_PRODUCTION_20260918_STAGING" / "production"
OLD = PROD / "Actual" / "B2"
RUN = HERE / "B2_MAY01_ACTUAL_ONLY_EVENT_R6"
sys.path.insert(0, str(PROD))
from electrical_engine import Engine
from actual_controller import Controller, Limits, ac_feasible


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


class ExactAC:
    def __init__(self, folder, data):
        self.engine = Engine(folder)
        self.data = data
        self.engine.md = data["md"]
        self.engine.mpv = data["mpv"]
        self.engine.ap = data["PCC_P"]
        self.engine.aq = data["PCC_Q"]

    def apply(self, slot, q):
        e = self.engine
        data = self.data
        x = np.r_[data["PCC_P"][slot], np.zeros(48)]
        for j, service in enumerate(data["locations"][slot]):
            if data["connected"][slot, j]:
                k = e.services.index(service)
                x[12 + k] += data["P_EXEC"][slot, j]
                x[36 + k] += q[j]
            else:
                assert data["P_EXEC"][slot, j] == q[j] == 0
        e.inputs(slot, x)
        try:
            e.solve()
        except AssertionError:
            line = np.full(len(e.ax["line_label"]), 2.)
            tx = np.full(len(e.ax["tx_label"]), 2.)
            return dict(v=np.zeros(len(e.nodes)), line=line, tx=tx,
                        ipu=np.r_[line, tx], kva=np.full(len(e.ax["kva_label"]), 2.),
                        taps=[], caps=[], converged=False, settled=False,
                        line_rho=2., state={})
        v2, line_complex, tx_complex, kva_complex = e.arrays()
        state = e.state(slot)
        line = np.abs(line_complex)
        tx = np.abs(tx_complex)
        kva = np.abs(kva_complex) / e.ax["kva_rating"]
        settled = bool(e.d.Solution.ControlActionsDone())
        return dict(v=np.sqrt(v2), line=line, tx=tx, ipu=np.r_[line, tx], kva=kva,
                    taps=[r["tap_number"] for r in state["regulators"]],
                    caps=[c["step_states"] for c in state["capacitors"]],
                    converged=bool(e.d.Solution.Converged() and settled), settled=settled,
                    line_rho=float(line.max()), state=state)

    def close(self):
        self.engine.close()


def source_inputs():
    assert not RUN.exists(), "PREEXISTING_RUN_NAMESPACE"
    RUN.mkdir(parents=True)
    with np.load(OLD / "ACTUAL_INPUTS.npz") as z:
        data = {key: z[key].copy() for key in z.files}
    with np.load(OLD / "FINAL_ACTUAL" / "EXECUTION.npz") as z:
        assert np.array_equal(data["P_EXEC"], z["P_EXEC"]), "OLD_P_EXEC_MISMATCH"
        assert np.array_equal(data["energy_after"], z["energy_after"]), "OLD_SOC_MISMATCH"
    old = json.loads((OLD / "COMPLETE.json").read_text(encoding="utf-8"))
    assert old["AC_feasible"] and abs(old["summary"]["max_phase_line_loading_pu"] - 0.8612974975163099) < 1e-10
    ids = list(data["ids"])
    frame = pd.read_parquet(OLD / "ACTUAL_MESS_TIMESERIES.parquet")
    def values(field):
        return frame.pivot(index="slot", columns="mess_id", values=field).reindex(index=range(96), columns=ids).to_numpy()
    travel = values("travel_energy_kWh").astype(float)
    assert np.array_equal(values("P_EXEC").astype(float), data["P_EXEC"])
    assert np.array_equal(values("Q_EXEC").astype(float), data["Q_EXEC"])
    assert np.array_equal(values("Q_CMD").astype(float), data["Q_EXEC"]), "DA_Q_PHYSICAL_BASELINE_DRIFT"
    assert np.array_equal(values("energy_after_kWh").astype(float), data["energy_after"])
    assert np.array_equal(values("connected").astype(bool), data["connected"])
    audit = json.loads((OLD / "ACTUAL_MESS_AUDIT.json").read_text(encoding="utf-8"))
    initial = np.array([audit["initial_energy"][mid] for mid in ids], float)
    assert np.array_equal(initial, np.full(len(ids), 1520.))
    # Verify the original actuator's frozen output before any OpenDSS trial.
    energy = initial.copy()
    maximum_soc_error = 0.0
    for slot in range(96):
        p = data["P_EXEC"][slot]
        available = energy - travel[slot]
        energy = available + .95 * np.maximum(-p, 0) * .25 - np.maximum(p, 0) * .25 / .95
        maximum_soc_error = max(maximum_soc_error, float(np.max(np.abs(energy - data["energy_after"][slot]))))
        if maximum_soc_error >= 1e-9:
            save(RUN / "STOP_P_SOC.json", dict(slot=slot, max_error=maximum_soc_error))
            raise AssertionError("P_SOC_PARITY_STOP")
    save(RUN / "INPUT_AUDIT.json", dict(status="PASS", date="2025-05-01", policy="B2",
         planning_source=str(PROD / "B2" / "FINAL_AUTHORITY.json"),
         planning_SHA=sha(PROD / "B2" / "FINAL_AUTHORITY.json"),
         fresh_source=str(PROD / "B2" / "Fresh" / "AC_VALIDATION.json"),
         fresh_SHA=sha(PROD / "B2" / "Fresh" / "AC_VALIDATION.json"),
         actual_inputs_SHA=sha(OLD / "ACTUAL_INPUTS.npz"),
         old_execution_SHA=sha(OLD / "FINAL_ACTUAL" / "EXECUTION.npz"),
         old_rho=old["summary"]["max_phase_line_loading_pu"],
         P_EXEC_exact=True, SOC_exact_input_copy=True,
         actuator_SOC_recurrence_max_error=maximum_soc_error,
         scales=dict(BG=.45, AIDC=2.10, MESS=2.00, PV=.50)))
    return data, travel, initial


def main():
    started = time.time()
    data, travel, initial = source_inputs()
    limits = Limits(pmax=600., smax=800., emin=880., emax=2160., eta_c=.95, eta_d=.95, dt=.25)
    control = Controller(limits, initial)
    da_rows = json.loads((PROD / "B2" / "Fresh" / "AC_VALIDATION.json").read_text(encoding="utf-8"))["slots"]
    assert len(da_rows) == 96 and all(row["slot"] == t and row["feasible"] for t, row in enumerate(da_rows))
    q = data["Q_EXEC"].copy()
    accepted = []
    events = []
    exact_trials = 0
    axes = json.loads((PROD / "AXES.json").read_text(encoding="utf-8"))
    source_sha = sha(HERE / "actual_controller.py")
    for slot in range(96):
        def evaluate(p, trial_q):
            nonlocal exact_trials
            assert np.array_equal(p, data["P_EXEC"][slot]), "P_EXEC_CHANGED"
            engine = ExactAC(RUN / "runtime" / f"slot_{slot:02d}" / f"trial_{exact_trials:05d}", data)
            exact_trials += 1
            try:
                for prior in range(slot):
                    r = engine.apply(prior, q[prior])
                    if not (r["converged"] and np.array_equal(r["v"], accepted[prior]["v"]) and r["taps"] == accepted[prior]["taps"]):
                        raise AssertionError("CAUSAL_PREFIX_DRIFT")
                return engine.apply(slot, trial_q)
            finally:
                engine.close()

        p, chosen_q, result, event = control.step(slot=slot, p_da=data["P_EXEC"][slot],
            q_da=data["Q_EXEC"][slot], connected=data["connected"][slot],
            travel_energy=travel[slot], evaluate=evaluate,
            da_exact=dict(rho=da_rows[slot]["max_phase_line_loading_pu"],
                          vmin=da_rows[slot]["Vmin_pu"], vmax=da_rows[slot]["Vmax_pu"]))
        assert event["trigger"] != "NONE" or event["exact_trials"] == 1, "NO_EVENT_Q_SEARCH"
        if not np.array_equal(p, data["P_EXEC"][slot]) or np.max(np.abs(control.energy - data["energy_after"][slot])) >= 1e-9:
            save(RUN / "STOP_P_SOC.json", dict(slot=slot, event=event))
            raise AssertionError("P_SOC_PARITY_STOP")
        q[slot] = chosen_q
        accepted.append(result)
        events.append(event)
        save(RUN / "PROGRESS.json", dict(status="RUNNING", slots_complete=slot + 1,
             exact_trials=exact_trials, AC_PASS_so_far=all(x["AC_PASS"] for x in events),
             event_trigger_slots=sum(x["event_triggered"] for x in events),
             Q_interventions=sum(x["Q_intervention"] for x in events),
             elapsed_seconds=time.time() - started, controller_SHA=source_sha))
        if slot % 8 == 0 or not event["AC_PASS"]:
            print("B2_SLOT", slot, event["status"], event["AC_PASS"], exact_trials, flush=True)
    assert sha(HERE / "actual_controller.py") == source_sha, "CONTROLLER_SOURCE_DRIFT"
    # The accepted trajectory gets a separate uninterrupted 96-slot solve.
    engine = ExactAC(RUN / "continuous_runtime", data)
    independent = []
    try:
        for slot in range(96):
            independent.append(engine.apply(slot, q[slot]))
    finally:
        engine.close()
    max_error = max(float(np.max(np.abs(a[k] - b[k]))) for a, b in zip(accepted, independent)
                    for k in ("v", "line", "tx", "kva"))
    assert max_error < 1e-9 and all(a["taps"] == b["taps"] for a, b in zip(accepted, independent)), "CONTINUOUS_REPLAY_DRIFT"
    assert all(ac_feasible(r) for r in independent), "AC_96_PASS_FAILED"
    assert np.array_equal(data["P_EXEC"], np.load(OLD / "FINAL_ACTUAL" / "EXECUTION.npz")["P_EXEC"])
    assert np.array_equal(data["energy_after"], np.load(OLD / "FINAL_ACTUAL" / "EXECUTION.npz")["energy_after"])
    np.savez_compressed(RUN / "EXECUTION.npz", P_EXEC=data["P_EXEC"], Q_EXEC=q,
                        energy_after=data["energy_after"], locations=data["locations"])
    rho = max(float(r["line"].max()) for r in independent)
    critical_slot = int(np.argmax([r["line"].max() for r in independent]))
    critical_index = int(np.argmax(independent[critical_slot]["line"]))
    summary = dict(status="PASS", date="2025-05-01", policy="B2", old_Actual_rho=0.8612974975163099,
                   new_Q_only_Actual_rho=rho, P_EXEC_exact=True, SOC_exact=True,
                   AC_PASS_slots=sum(ac_feasible(r) for r in independent), Q_interventions=sum(x["Q_intervention"] for x in events),
                   event_trigger_slots=sum(x["event_triggered"] for x in events),
                   max_abs_delta_Q=max(x["max_abs_delta_Q"] for x in events),
                   critical_slot=critical_slot, critical_line=axes["line"][critical_index],
                   Vmin=min(float(r["v"].min()) for r in independent),
                   Vmax=max(float(r["v"].max()) for r in independent),
                   exact_trials=exact_trials, continuous_replay_max_error=max_error,
                   runtime_seconds=time.time()-started, workers=1, threads=4,
                   controller_SHA256=source_sha, future_Actual_leakage=False, P_correction=False)
    if summary["Q_interventions"] >= 0.9 * 96:
        summary["status"] = "DIAGNOSTIC_HOLD_HIGH_INTERVENTION_RATIO"
    save(RUN / "EVENTS.json", events)
    save(RUN / "COMPLETE.json", summary)
    if summary["status"] != "PASS":
        print("B2_DIAGNOSTIC_HOLD", json.dumps(summary), flush=True)
        return
    save(HERE.parent / "CONTROLLER_CANDIDATE_FREEZE.json", dict(status="CANDIDATE_FROZEN_AFTER_B2_PASS",
         controller_SHA256=source_sha, source=str(HERE / "actual_controller.py"), IEEE123_source=str(HERE.parent / "IEEE123" / "actual_controller.py"),
         IEEE123_SHA256=sha(HERE.parent / "IEEE123" / "actual_controller.py"), B2_preflight=str(RUN / "COMPLETE.json")))
    assert sha(HERE.parent / "IEEE123" / "actual_controller.py") == source_sha
    print("B2_COMPLETE", json.dumps(summary), flush=True)


if __name__ == "__main__":
    try:
        main()
    except BaseException as error:
        if RUN.exists():
            save(RUN / "FAILURE.json", dict(error=repr(error), time=time.time()))
        raise
