"""The inherited Planning rows, with explicit AIDC and MESS control inputs."""
from __future__ import annotations
import math
import numpy as np
import gurobipy as gp
from gurobipy import GRB
from dayahead.grid_lp import LINE_POLYGON_FACES, V_MIN_SQUARED, V_MAX_SQUARED
from dayahead.v28r2.electrical_subproblem import anchored_polygon_parameters, anchored_polygon_loading, is_dominated_mess_current_row


def controls_from_trajectory(coefficients, pcc, trajectory):
    x = np.zeros((len(coefficients), len(coefficients[0].control_names)))
    x[:, :12] = np.asarray(pcc, dtype=float)
    names = coefficients[0].control_names
    for r in trajectory:
        if r.service_id is not None:
            x[r.slot, names.index(f"mess_p_kw[{r.service_id}]")] += r.p_kw
            x[r.slot, names.index(f"mess_q_kvar[{r.service_id}]")] += r.q_kvar
    if not np.isfinite(x).all(): raise ValueError("NONFINITE_CONTROLS")
    return x


def add_grid(model, coefficients, controls, objective_cap=1.0):
    """Same voltage, anchored line polygon, transformer current and kVA rows as V34."""
    rho = model.addVar(lb=0, ub=objective_cap, name="rho_max")
    row_counts = dict(voltage=0, line_current=0, transformer_current=0, transformer_kva=0)
    def expr(constant, weights, t):
        nz = np.flatnonzero(weights)
        return float(constant) + gp.quicksum(float(weights[k])*controls[t][k] for k in nz)
    for t, c in enumerate(coefficients):
        for n, constant in enumerate(c.voltage_constant):
            v = model.addVar(lb=V_MIN_SQUARED, ub=V_MAX_SQUARED, name=f"v_squared[{t},{n}]")
            model.addConstr(v == expr(constant, c.voltage_matrix[:, n], t))
            row_counts["voltage"] += 1
        bias, correction, _ = anchored_polygon_parameters(c)
        for k, branch in enumerate(c.branch_names):
            if not is_dominated_mess_current_row(branch):
                if branch.startswith("transformer."):
                    model.addConstr(expr(c.current_constant[k], c.current_matrix[:, k], t) <= 1,
                                    name=f"tx_current[{t},{k}]")
                    row_counts["transformer_current"] += 1
                else:
                    p = model.addVar(lb=-GRB.INFINITY, name=f"line_p[{t},{k}]")
                    q = model.addVar(lb=-GRB.INFINITY, name=f"line_q[{t},{k}]")
                    delta = model.addVar(lb=-GRB.INFINITY, name=f"line_delta[{t},{k}]")
                    model.addConstr(p == expr(c.flow_p_constant[k], c.flow_p_matrix[k], t))
                    model.addConstr(q == expr(c.flow_q_constant[k], c.flow_q_matrix[k], t))
                    model.addConstr(delta == expr(-correction[:,k]@c.anchor, correction[:,k], t))
                    apothem = c.branch_limits[k]*math.cos(math.pi/LINE_POLYGON_FACES)
                    for f in range(LINE_POLYGON_FACES):
                        angle = 2*math.pi*f/LINE_POLYGON_FACES
                        model.addConstr((math.cos(angle)*p+math.sin(angle)*q)/apothem+delta+float(bias[k]) <= rho,
                                        name=f"line_current[{t},{k},{f}]")
                        row_counts["line_current"] += 1
            rating = c.transformer_ratings[k]
            if rating is not None:
                p = model.addVar(lb=-GRB.INFINITY, name=f"tx_p[{t},{k}]")
                q = model.addVar(lb=-GRB.INFINITY, name=f"tx_q[{t},{k}]")
                model.addConstr(p == expr(c.flow_p_constant[k], c.flow_p_matrix[k], t))
                model.addConstr(q == expr(c.flow_q_constant[k], c.flow_q_matrix[k], t))
                for f in range(LINE_POLYGON_FACES):
                    angle = 2*math.pi*f/LINE_POLYGON_FACES
                    model.addConstr(math.cos(angle)*p+math.sin(angle)*q <= rating*math.cos(math.pi/LINE_POLYGON_FACES),
                                    name=f"tx_kva[{t},{k},{f}]")
                    row_counts["transformer_kva"] += 1
    return rho, row_counts


def evaluate_grid(coefficients, controls, nodes, tolerance=1e-7):
    voltage=[]; lines=[]; tx=[]; kva=[]; txpoly=[]
    branch_names = coefficients[0].branch_names
    li=[k for k,n in enumerate(branch_names) if not n.startswith("transformer.") and not is_dominated_mess_current_row(n)]
    ti=[k for k,n in enumerate(branch_names) if n.startswith("transformer.") and not is_dominated_mess_current_row(n)]
    for t,c in enumerate(coefficients):
        x=np.asarray(controls[t],float)
        v2=c.voltage_constant+c.voltage_matrix.T@x
        if not np.isfinite(x).all() or np.any(v2<0): raise ValueError("INVALID_GRID_STATE")
        voltage.append(np.sqrt(v2));lines.append(anchored_polygon_loading(c,x)[li])
        tx.extend((c.current_constant+c.current_matrix.T@x)[ti].tolist())
        p=c.flow_p_constant+c.flow_p_matrix@x;q=c.flow_q_constant+c.flow_q_matrix@x
        for k,rating in enumerate(c.transformer_ratings):
            if rating is not None:
                kva.append(math.hypot(p[k],q[k])/rating)
                txpoly.append(max(math.cos(2*math.pi*f/LINE_POLYGON_FACES)*p[k]+math.sin(2*math.pi*f/LINE_POLYGON_FACES)*q[k]
                                  for f in range(LINE_POLYGON_FACES))/(rating*math.cos(math.pi/LINE_POLYGON_FACES)))
    v=np.asarray(voltage);l=np.asarray(lines)
    t,k=np.unravel_index(np.argmax(l),l.shape);critical=branch_names[li[k]]
    counts={"voltage":int(((v<math.sqrt(V_MIN_SQUARED)-tolerance)|(v>math.sqrt(V_MAX_SQUARED)+tolerance)).sum()),
            "line_current":int((l>1+tolerance).sum()),"transformer_current":sum(x>1+tolerance for x in tx),
            "transformer_kva":sum(x>1+tolerance for x in kva),"transformer_polygon":sum(x>1+tolerance for x in txpoly)}
    return {"status":"PASS" if not any(counts.values()) else "FAIL", "rho_max":float(l.max()),
            "critical_line":critical,"critical_phase":critical.rsplit("::",1)[-1],"critical_slot":int(t),
            "Vmin":float(v.min()),"Vmax":float(v.max()),"maximum_line_loading":float(l.max()),
            "maximum_transformer_phase_current":max(tx,default=0),"maximum_transformer_kVA":max(kva,default=0),
            "transformer_metric_units":"NORMALIZED_TO_INHERITED_RATING", "violations":counts,
            "coefficient_SHAs":[c.coefficient_sha256 for c in coefficients]}
