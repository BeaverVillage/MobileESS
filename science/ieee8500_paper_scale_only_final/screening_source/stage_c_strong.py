"""Critical-window fixed-paper-route MESS P/Q reoptimization for diagnosis.

The 96-slot route, traffic energy and objective are inherited. P/Q in the
critical windows are newly optimized for each rating. All 96 slots are then
checked with the original paper PCC overlay and exact OpenDSS. These results
are screening diagnostics; production must start from fresh policy searches.
"""
import json
import math
import os
import sys
import time
from pathlib import Path

for key in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[key] = "1"
sys.dont_write_bytecode = True
import gurobipy as gp
import numpy as np
from stage_a_strong import Engine, PAPER, HERE, authority_guard, read, sha
from stage_c_coefficients import SLOTS, configure, pcc_for, save

SLOT_SET = set(SLOTS)
SCALES = (1., 1.25, 1.5, 1.75, 2.)
SERVICES = [f"IDC{i:02}" for i in range(1, 13)] + [f"STA{i:02}" for i in range(1, 13)]
SERVICE_INDEX = {s: i for i, s in enumerate(SERVICES)}
FACES = 16
COS = math.cos(math.pi / FACES)


def source_route(policy):
    rows = read(PAPER / policy / "FINAL_AUTHORITY.json")["trajectory_slots"]
    by = {(r["mess_id"], r["slot"]): r for r in rows}
    ids = sorted({r["mess_id"] for r in rows})
    assert len(ids) == 6 and len(by) == 576
    return ids, by


def coeff_path(label, policy, t):
    return HERE / "stage_c_strong" / "coefficients" / label / policy / f"slot_{t:02d}" / "COEFFICIENTS.npz"


def model_for(point, policy, scale, folder):
    ids, route = source_route(policy)
    model = gp.Model(f"PAPER_{policy}_MESS_{scale:.2f}")
    model.Params.Threads = 4
    model.Params.OutputFlag = 0
    model.Params.NumericFocus = 2
    assert model.Params.TimeLimit >= 1e90 and model.Params.WorkLimit >= 1e90
    rho = model.addVar(lb=0., ub=1., name="rho")
    energy, p, q = {}, {}, {}
    pmax, smax = 300. * scale, 400. * scale
    emin, emax, initial = 440. * scale, 1080. * scale, 760. * scale
    for mid in ids:
        for t in range(97):
            energy[mid, t] = model.addVar(lb=emin, ub=emax, name=f"energy[{mid},{t}]")
            if t < 96:
                energy[mid, t].Start = route[mid, t]["battery_energy_kwh"] + 760. * (scale - 1.)
        model.addConstr(energy[mid, 0] == initial)
        model.addConstr(energy[mid, 96] == initial)
        for t in range(96):
            r = route[mid, t]
            connected = r["mode"] == "CONNECTED"
            if t in SLOT_SET and connected:
                direction = model.addVar(vtype=gp.GRB.BINARY, name=f"direction[{mid},{t}]")
                discharge = model.addVar(lb=0., ub=pmax, name=f"discharge[{mid},{t}]")
                charge = model.addVar(lb=0., ub=pmax, name=f"charge[{mid},{t}]")
                qvar = model.addVar(lb=-smax, ub=smax, name=f"Q[{mid},{t}]")
                model.addConstr(discharge <= pmax * direction)
                model.addConstr(charge <= pmax * (1 - direction))
                p[mid, t] = discharge - charge
                q[mid, t] = qvar
                direction.Start = float(r["p_kw"] > 0.)
                discharge.Start = max(0., r["p_kw"])
                charge.Start = max(0., -r["p_kw"])
                qvar.Start = r["q_kvar"]
                for f in range(FACES):
                    angle = 2. * math.pi * f / FACES
                    model.addConstr(math.cos(angle) * p[mid, t] + math.sin(angle) * qvar <= smax * COS)
                gain = .95 * .25 * charge - .25 * discharge / .95
            else:
                fixed_p = float(r["p_kw"])
                fixed_q = float(r["q_kvar"])
                assert abs(fixed_p) <= pmax + 1e-6 and math.hypot(fixed_p, fixed_q) <= smax + 1e-6
                p[mid, t], q[mid, t] = fixed_p, fixed_q
                gain = .95 * .25 * max(-fixed_p, 0.) - .25 * max(fixed_p, 0.) / .95
            travel = float(r["energy_safe_kwh"]) if r["departure_slot"] == t and r["mode"] == "TRANSIT" else 0.
            model.addConstr(energy[mid, t] >= emin + travel)
            model.addConstr(energy[mid, t + 1] == energy[mid, t] + gain - travel)
    model.setObjective(rho, gp.GRB.MINIMIZE)
    model.update()
    return model, rho, p, q, energy, ids, route


def expressions(t, route, ids, p, q):
    controls = [gp.LinExpr(0.) for _ in range(48)]
    for mid in ids:
        r = route[mid, t]
        if r["mode"] == "CONNECTED":
            i = SERVICE_INDEX[r["service_id"]]
            controls[i] += p[mid, t]
            controls[24 + i] += q[mid, t]
    return controls


def affine(z, controls, array_name, jac_name, index):
    base = z[array_name][index]
    jac = z[jac_name][:, index]
    real = gp.LinExpr(float(np.real(base)))
    imag = gp.LinExpr(float(np.imag(base))) if np.iscomplexobj(base) else None
    for k, expr in enumerate(controls):
        if abs(jac[k]) < 1e-14:
            continue
        real += float(np.real(jac[k])) * expr
        if imag is not None:
            imag += float(np.imag(jac[k])) * expr
    return real, imag


def add_row(model, rho, z, controls, t, kind, index):
    names = {"line": ("line", "line_J"), "low": ("v2", "v2_J"),
             "high": ("v2", "v2_J"), "tx": ("tx", "tx_J"),
             "kva": ("S", "S_J")}
    re, im = affine(z, controls, *names[kind], index)
    if kind == "low":
        model.addConstr(re >= .95 ** 2, name=f"low_{t}_{index}")
    elif kind == "high":
        model.addConstr(re <= 1.05 ** 2, name=f"high_{t}_{index}")
    else:
        rating = 1. if kind != "kva" else float(z["kva_rating"][index])
        bound = rho if kind == "line" else 1.
        for f in range(FACES):
            angle = 2. * math.pi * f / FACES
            model.addConstr(math.cos(angle) * re + math.sin(angle) * im <= COS * rating * bound,
                            name=f"{kind}_{t}_{index}_{f}")


def predicted(z, control_values):
    v2 = z["v2"] + control_values @ z["v2_J"]
    line = z["line"] + control_values @ z["line_J"]
    tx = z["tx"] + control_values @ z["tx_J"]
    kva = z["S"] + control_values @ z["S_J"]
    return {"low": v2, "high": v2, "line": np.abs(line),
            "tx": np.abs(tx), "kva": np.abs(kva) / z["kva_rating"]}


def optimize(point, policy, scale, folder):
    start = time.perf_counter()
    model, rho, p, q, energy, ids, route = model_for(point, policy, scale, folder)
    seen = {t: {kind: set() for kind in ("line", "low", "high", "tx", "kva")} for t in SLOTS}
    controls = {t: expressions(t, route, ids, p, q) for t in SLOTS}
    rating = np.asarray(read(PAPER / "AXES.json")["winding_rating_kVA"])
    # Every hard-limit family is present; separation adds any newly critical
    # native element. No feeder asset, phase or reactive sign is excluded.
    for t in SLOTS:
        with np.load(coeff_path(point["label"], policy, t)) as z:
            arrays = {k: z[k] for k in z.files}
            arrays["kva_rating"] = rating
            initial = {"line": np.argsort(np.abs(arrays["line"]))[-12:],
                       "low": np.argsort(arrays["v2"])[:6],
                       "high": np.argsort(arrays["v2"])[-6:],
                       "tx": np.argsort(np.abs(arrays["tx"]))[-4:],
                       "kva": np.argsort(np.abs(arrays["S"]) / arrays["kva_rating"])[-4:]}
            for kind, indices in initial.items():
                for index in indices:
                    index = int(index)
                    add_row(model, rho, arrays, controls[t], t, kind, index)
                    seen[t][kind].add(index)
    rounds = []
    while True:
        model.optimize()
        if model.Status != gp.GRB.OPTIMAL or not model.SolCount:
            save(folder / "OPTIMIZATION_FAILURE.json", dict(status=int(model.Status),
                 incumbent_count=int(model.SolCount), scale=scale, policy=policy))
            return None
        added = 0
        max_violation = 0.
        for t in SLOTS:
            vals = np.zeros(48)
            for mid in ids:
                r = route[mid, t]
                if r["mode"] == "CONNECTED":
                    i = SERVICE_INDEX[r["service_id"]]
                    vals[i] += float(p[mid, t].getValue()) if isinstance(p[mid, t], gp.LinExpr) else float(p[mid, t])
                    vals[24 + i] += float(q[mid, t].X) if isinstance(q[mid, t], gp.Var) else float(q[mid, t])
            with np.load(coeff_path(point["label"], policy, t)) as z:
                arrays = {k: z[k] for k in z.files}
                arrays["kva_rating"] = rating
                values = predicted(arrays, vals)
                violations = {"line": values["line"] - rho.X,
                              "low": .95 ** 2 - values["low"],
                              "high": values["high"] - 1.05 ** 2,
                              "tx": values["tx"] - 1., "kva": values["kva"] - 1.}
                for kind, violation in violations.items():
                    max_violation = max(max_violation, float(np.max(violation)))
                    for index in np.flatnonzero(violation > 1e-6):
                        index = int(index)
                        if index not in seen[t][kind]:
                            add_row(model, rho, arrays, controls[t], t, kind, index)
                            seen[t][kind].add(index)
                            added += 1
        rounds.append(dict(round=len(rounds), linear_rho=float(rho.X),
                           max_linear_violation=max_violation, added_native_rows=added,
                           Gurobi_work=float(model.Work)))
        save(folder / "OPTIMIZATION_PROGRESS.json", rounds)
        print("CUT_ROUND", point["label"], policy, scale, len(rounds), added, rho.X, flush=True)
        if not added:
            break
    dispatch = []
    for mid in ids:
        for t in range(96):
            r = route[mid, t]
            pp = float(p[mid, t].getValue()) if isinstance(p[mid, t], gp.LinExpr) else float(p[mid, t])
            qq = float(q[mid, t].X) if isinstance(q[mid, t], gp.Var) else float(q[mid, t])
            dispatch.append(dict(mess_id=mid, slot=t, service_id=r["service_id"],
                                 mode=r["mode"], p_kw=pp, q_kvar=qq,
                                 energy_kwh=float(energy[mid, t].X),
                                 soc_fraction=float(energy[mid, t].X) / (1200. * scale)))
    save(folder / "DISPATCH.json", dispatch)
    save(folder / "OPTIMIZATION.json", dict(status="PASS", objective="minimize_max_line_loading",
         policy=policy, scale=scale, critical_slots=list(SLOTS), unchanged_paper_routes=True,
         outside_critical_window_pq="frozen paper dispatch", Q_sign_restriction=False,
         Pmax_kW=300. * scale, Smax_kVA=400. * scale, capacity_kWh=1200. * scale,
         Emin_kWh=440. * scale, Emax_kWh=1080. * scale,
         initial_terminal_kWh=760. * scale, efficiency=.95,
         Gurobi_status=int(model.Status), work=float(model.Work), rounds=rounds,
         wall_seconds=time.perf_counter() - start))
    model.dispose()
    return dispatch


def exact(point, policy, scale, dispatch, folder):
    by = {(r["mess_id"], r["slot"]): r for r in dispatch}
    source = source_route(policy)[1]
    pcc = pcc_for(policy) * (point["aidc_scale"] / 2.)
    e = Engine(folder / "runtime")
    rows = []
    try:
        for t in range(96):
            configure(e, t, point["background_scale"])
            x = np.r_[pcc[t], np.zeros(48)]
            for mid in sorted({r["mess_id"] for r in dispatch}):
                r = by[mid, t]
                if r["mode"] == "CONNECTED":
                    i = SERVICE_INDEX[r["service_id"]]
                    x[12 + i] += r["p_kw"]
                    x[36 + i] += r["q_kvar"]
            e.controls(x)
            e.d.Solution.SolveSnap()
            converged = bool(e.d.Solution.Converged()) and e.d.Error.Number() == 0
            if not converged:
                rows.append(dict(slot=t, converged=False, AC_PASS=False))
                break
            v2, line, tx, apparent = e.arrays()
            v = np.sqrt(v2)
            li = np.abs(line)
            txmax = float(np.abs(tx).max())
            kvamax = float((np.abs(apparent) / e.ax["kva_rating"]).max())
            j = int(li.argmax())
            row = dict(slot=t, rho=float(li[j]), Vmin=float(v.min()),
                       Vmax=float(v.max()), transformer_current=txmax,
                       transformer_kva=kvamax,
                       critical_line=str(e.ax["line_label"][j]),
                       converged=True, controls_settled=bool(e.d.Solution.ControlActionsDone()))
            row["AC_PASS"] = (row["controls_settled"] and row["Vmin"] >= .95 - 1e-9
                              and row["Vmax"] <= 1.05 + 1e-9
                              and max(row["rho"], txmax, kvamax) <= 1. + 1e-9)
            rows.append(row)
    finally:
        e.close()
    critical = max(rows, key=lambda r: r.get("rho", -1.))
    pmax = max(abs(r["p_kw"]) for r in dispatch)
    qmax = max(abs(r["q_kvar"]) for r in dispatch)
    emin = min(r["energy_kwh"] for r in dispatch)
    emax = max(r["energy_kwh"] for r in dispatch)
    result = dict(kind="CRITICAL_SLOT_NEW_MESS_PQ_OPTIMIZATION_EXACT_96_SLOT_DIAGNOSTIC",
                  BG=point["background_scale"], AIDC=point["aidc_scale"], MESS=scale,
                  policy=policy, rho=critical.get("rho"), critical_line=critical.get("critical_line"),
                  critical_slot=critical["slot"], Vmin=min(r.get("Vmin", 1e9) for r in rows),
                  Vmax=max(r.get("Vmax", -1e9) for r in rows),
                  transformer_current=max(r.get("transformer_current", 0.) for r in rows),
                  transformer_kva=max(r.get("transformer_kva", 0.) for r in rows),
                  max_abs_P=pmax, max_abs_Q=qmax, SOC_min=emin / (1200. * scale),
                  SOC_max=emax / (1200. * scale), E_min_kWh=emin, E_max_kWh=emax,
                  AC_PASS=len(rows) == 96 and all(r["AC_PASS"] for r in rows),
                  paper_overlay_sha256=sha(PAPER / "IEEE8500_PCC_Overlay.dss"),
                  rows=rows)
    save(folder / "EXACT_AC.json", result)
    return result


def main():
    authority_guard()
    selection = read(HERE / "STAGE_B_STRONG_TOP2.json")["selection"]
    cases = []
    for point in selection:
        for scale in SCALES:
            policies = {}
            for policy in ("B2", "B3"):
                folder = HERE / "stage_c_strong" / "results" / point["label"] / f"MESS_{scale:.2f}" / policy
                folder.mkdir(parents=True, exist_ok=True)
                if (folder / "EXACT_AC.json").exists():
                    policies[policy] = read(folder / "EXACT_AC.json")
                    continue
                dispatch = optimize(point, policy, scale, folder)
                if dispatch is None:
                    policies[policy] = dict(AC_PASS=False, optimizer_status="NO_OPTIMAL_SOLUTION")
                    continue
                policies[policy] = exact(point, policy, scale, dispatch, folder)
            case = dict(BG=point["background_scale"], AIDC=point["aidc_scale"], MESS=scale,
                        B2=policies["B2"], B3=policies["B3"])
            cases.append(case)
            save(HERE / "STAGE_C_STRONG_RUNNING.json", dict(status="RUNNING", cases=cases))
    save(HERE / "STAGE_C_STRONG_COMPLETE.json", dict(status="COMPLETE", cases=cases))


if __name__ == "__main__":
    main()
