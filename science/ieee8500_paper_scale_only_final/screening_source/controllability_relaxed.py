"""Continuous paper-PCC B0 control potential, for screening only.

Each critical slot is relaxed independently. AIDC demand may move across
sites and time within the unchanged paper site power table bounds; the
unmodeled jobs are presumed served in other slots. Six fractional MESS can use the original 24 electrical ports;
the fixed original travel and SOC chronology are deliberately relaxed. Hence
the gap is an optimistic capability diagnostic, not a production prediction.
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
from stage_a_strong import HERE, PAPER, authority_guard, read, sha
from stage_c_coefficients_old import save

OUT = HERE / "controllability_search_20260920"
SCALES = (1., 1.25, 1.5, 1.75, 2.)
FACES = 16
COS = math.cos(math.pi/FACES)


def affine(z, values, kind, index):
    raw = z[kind][index]
    jac = z[kind+"_J"][:,index]
    constant = raw - np.dot(jac,z["x"])
    if np.iscomplexobj(raw):
        real = gp.LinExpr(float(np.real(constant)))
        imag = gp.LinExpr(float(np.imag(constant)))
        for k, var in enumerate(values):
            c = jac[k]
            if isinstance(var,(gp.Var,gp.LinExpr)):
                if abs(c.real)>1e-13:real += float(c.real)*var
                if abs(c.imag)>1e-13:imag += float(c.imag)*var
            else:
                real += float(c.real)*float(var)
                imag += float(c.imag)*float(var)
        return real,imag
    result=gp.LinExpr(float(constant))
    for k,var in enumerate(values):
        c=float(jac[k])
        if abs(c)<1e-13:continue
        result += c*var if isinstance(var,(gp.Var,gp.LinExpr)) else c*float(var)
    return result,None


def add_witness(model,z,values,rho,kind,index,angle=None,rating=None):
    if kind in ("low","high"):
        expr,_=affine(z,values,"v2",index)
        if kind=="low":model.addConstr(expr >= .95**2)
        else:model.addConstr(expr <= 1.05**2)
        return
    source={"line":"line","tx":"tx","kva":"S"}[kind]
    re,im=affine(z,values,source,index)
    if angle is None:angle=float(np.angle(z[source][index]))
    bound=rho if kind=="line" else (1. if kind=="tx" else float(rating))
    model.addConstr(math.cos(angle)*re+math.sin(angle)*im <= bound)


def solve_slot(z,lower,upper,rating,mode,scale,slot,conserve_slot_aidc=False):
    start=time.perf_counter()
    model=gp.Model(f"RELAXED_{mode}_{slot}_{scale}")
    model.Params.OutputFlag=0
    model.Params.Threads=4
    model.Params.NumericFocus=2
    rho=model.addVar(lb=0.,ub=1.,name="rho")
    x=z["x"]
    values=[]
    for i in range(12):
        if mode in ("aidc","joint"):
            values.append(model.addVar(lb=float(lower[i]),ub=float(upper[i]),name=f"AIDC_P[{i}]"))
        else:values.append(float(x[i]))
    if conserve_slot_aidc and mode in ("aidc","joint"):
        model.addConstr(gp.quicksum(values[:12])==float(x[:12].sum()))
    if mode in ("mess","joint"):
        y=[];p=[];q=[]
        pmax=300.*scale;smax=400.*scale
        energy_discharge_limit=min(pmax,(760.-440.)*scale*.95/.25)
        energy_charge_limit=min(pmax,(1080.-760.)*scale/(.95*.25))
        assert energy_discharge_limit==pmax and energy_charge_limit==pmax
        for j in range(24):
            yy=model.addVar(lb=0.,ub=6.,name=f"fractional_MESS[{j}]")
            pp=model.addVar(lb=-pmax*6.,ub=pmax*6.,name=f"MESS_P[{j}]")
            qq=model.addVar(lb=-smax*6.,ub=smax*6.,name=f"MESS_Q[{j}]")
            model.addConstr(pp <= energy_discharge_limit*yy)
            model.addConstr(-pp <= energy_charge_limit*yy)
            for face in range(FACES):
                angle=2*math.pi*face/FACES
                model.addConstr(math.cos(angle)*pp+math.sin(angle)*qq<=smax*COS*yy)
            y.append(yy);p.append(pp);q.append(qq)
        model.addConstr(gp.quicksum(y)<=6.)
        values.extend(p);values.extend(q)
    else:values.extend([0.]*48)
    model.setObjective(rho,gp.GRB.MINIMIZE)
    seen={k:set() for k in ("low","high")}
    initial={"line":np.argsort(np.abs(z["line"]))[-10:],
             "low":np.argsort(z["v2"])[:8],
             "high":np.argsort(z["v2"])[-8:],
             "tx":np.argsort(np.abs(z["tx"]))[-4:],
             "kva":np.argsort(np.abs(z["S"])/rating)[-4:]}
    for kind,indices in initial.items():
        for idx in indices:
            idx=int(idx)
            add_witness(model,z,values,rho,kind,idx,rating=rating[idx] if kind=="kva" else None)
            if kind in seen:seen[kind].add(idx)
    rounds=[]
    while True:
        model.optimize()
        if model.Status!=gp.GRB.OPTIMAL:
            return dict(status="SOLVER_NOT_OPTIMAL",solver_status=int(model.Status),mode=mode,scale=scale,slot=slot)
        v=np.array([float(a.X) if isinstance(a,gp.Var) else float(a) for a in values])
        delta=v-x
        predicted={kind:z[kind]+delta@z[kind+"_J"] for kind in ("v2","line","tx","S")}
        line=np.abs(predicted["line"]);tx=np.abs(predicted["tx"]);kva=np.abs(predicted["S"])/rating
        violations={"line":line-rho.X,"low":.95**2-predicted["v2"],
                    "high":predicted["v2"]-1.05**2,"tx":tx-1.,"kva":kva-1.}
        max_violation=max(float(np.max(v)) for v in violations.values())
        added=0
        for kind,vec in violations.items():
            if kind in ("line","tx","kva"):
                ids=np.flatnonzero(vec>2e-5)
                ids=ids[np.argsort(vec[ids])[-20:]]
                source={"line":"line","tx":"tx","kva":"S"}[kind]
                for idx in ids:
                    idx=int(idx)
                    add_witness(model,z,values,rho,kind,idx,
                                angle=float(np.angle(predicted[source][idx])),
                                rating=rating[idx] if kind=="kva" else None)
                    added+=1
            else:
                ids=np.flatnonzero(vec>2e-5)
                ids=ids[np.argsort(vec[ids])[-20:]]
                for idx in ids:
                    idx=int(idx)
                    if idx not in seen[kind]:
                        add_witness(model,z,values,rho,kind,idx)
                        seen[kind].add(idx)
                        added+=1
        rounds.append(dict(round=len(rounds),rho=float(rho.X),max_violation=max_violation,added=added))
        if added==0:
            break
        if len(rounds)>40:
            return dict(status="CUT_SEPARATION_NOT_CLOSED",mode=mode,scale=scale,slot=slot,rounds=rounds)
    result=dict(status="PASS",mode=mode,scale=scale,slot=slot,
                relaxed_rho=float(max(line)),linear_objective=float(rho.X),
                Vmin=float(np.sqrt(max(float(predicted["v2"].min()),0.))),
                Vmax=float(np.sqrt(float(predicted["v2"].max()))),
                transformer_current=float(tx.max()),transformer_kva=float(kva.max()),
                AIDC_total_P_conserved=bool(abs(v[:12].sum()-x[:12].sum())<1e-7),
                AIDC_peak_P_reduction_kW=float(x[:12].sum()-v[:12].sum()),
                AIDC_temporal_work_shift_relaxed=not conserve_slot_aidc,
                max_abs_MESS_P=float(np.abs(v[12:36]).max()),
                max_abs_MESS_Q=float(np.abs(v[36:60]).max()),
                rounds=rounds,wall_seconds=time.perf_counter()-start)
    model.dispose()
    return result


def run_candidate(point):
    label=point["label"]
    manifest=read(OUT/"sensitivity"/label/"MANIFEST.json")
    assert manifest["paper_overlay_sha256"]==sha(PAPER/"IEEE8500_PCC_Overlay.dss")
    with np.load(PAPER/"B3_A1_electrical_rows/PCC_IMPLIED_BOUNDS.npz") as bounds:
        lower=bounds["lower"].copy()*(point["aidc_scale"]/2.)
        upper=bounds["upper"].copy()*(point["aidc_scale"]/2.)
    rating=np.asarray(read(PAPER/"AXES.json")["winding_rating_kVA"])
    folder=OUT/"relaxed"/label
    folder.mkdir(parents=True,exist_ok=True)
    records=[]
    for t in manifest["selected_slots"]:
        with np.load(OUT/"sensitivity"/label/f"slot_{t:02d}.npz") as archive:
            z={k:archive[k] for k in archive.files}
        assert np.all(z["x"][:12]>=lower[t]-1e-6) and np.all(z["x"][:12]<=upper[t]+1e-6)
        for mode in ("aidc","mess","joint"):
            scales=(1.,) if mode=="aidc" else SCALES
            for scale in scales:
                path=folder/f"slot_{t:02d}_{mode}_MESS_{scale:.2f}.json"
                if path.exists():result=read(path)
                else:
                    result=solve_slot(z,lower[t],upper[t],rating,mode,scale,t)
                    save(path,result)
                if result["status"]!="PASS":raise RuntimeError((label,t,mode,scale,result["status"]))
                records.append(result)
                print("RELAXED",label,t,mode,scale,round(result["relaxed_rho"],6),flush=True)
        save(folder/"RUNNING.json",dict(status="RUNNING",records=records))
    b0=point["rho"]
    floor=manifest["outside_slot_exact_rho_floor"]
    summary=[]
    aidc_slot={r["slot"]:r for r in records if r["mode"]=="aidc"}
    aidc_best=max(r["relaxed_rho"] for r in aidc_slot.values())
    for scale in SCALES:
        mess_best=max(r["relaxed_rho"] for r in records if r["mode"]=="mess" and r["scale"]==scale)
        joint_best=max(r["relaxed_rho"] for r in records if r["mode"]=="joint" and r["scale"]==scale)
        full_day_floor_adjusted=max(joint_best,floor)
        summary.append(dict(BG=point["background_scale"],AIDC=point["aidc_scale"],MESS=scale,
              exact_B0_rho=b0,Vmin=point["Vmin"],Vmax=point["Vmax"],
              B0_critical_line=point["critical_line"],B0_critical_slot=point["critical_slot"],
              relaxed_best_achievable_rho=joint_best,
              controllability_gap=b0-joint_best,
              outside_slot_exact_rho_floor=floor,
              floor_adjusted_relaxed_rho=full_day_floor_adjusted,
              floor_adjusted_gap=b0-full_day_floor_adjusted,
              AIDC_contribution_potential=b0-aidc_best,
              MESS_contribution_potential=b0-mess_best,
              AIDC_and_MESS_overlap=b0-aidc_best-mess_best+joint_best,
              exact_B0_AC_PASS=point["AC_PASS"],
              relaxed_kind="optimistic independent critical-slot continuous electrical relaxation",
              Pmax_kW=300.*scale,Smax_kVA=400.*scale,capacity_kWh=1200.*scale,
              Emin_kWh=440.*scale,Emax_kWh=1080.*scale,initial_terminal_kWh=760.*scale))
    result=dict(status="COMPLETE",label=label,selected_slots=manifest["selected_slots"],
                paper_overlay_sha256=manifest["paper_overlay_sha256"],
                paper_AIDC_bounds_sha256=sha(PAPER/"B3_A1_electrical_rows/PCC_IMPLIED_BOUNDS.npz"),
                limitation="No job/WAN/mobility chronology or integer dispatch; peak AIDC demand may move to other slots without proving those jobs feasible. Values are optimistic capability upper bounds, not B1/B2/B3 production outcomes",
                summary=summary)
    save(folder/"SUMMARY.json",result)
    return result


def main():
    authority_guard()
    points=read(OUT/"B0_SEARCH_COMPLETE.json")["eligible"]
    unique={p["label"]:p for p in points}
    summaries=[]
    for point in sorted(unique.values(),key=lambda r:-r["aidc_scale"]):
        summaries.append(run_candidate(point))
        save(OUT/"RELAXED_SCREEN_RUNNING.json",dict(status="RUNNING",summaries=summaries))
    save(OUT/"RELAXED_SCREEN_COMPLETE.json",dict(status="COMPLETE",summaries=summaries))


if __name__=="__main__":main()
