"""Exact stacked scenario constraints on one common PCC/GPU decision."""
from copy import copy
from dataclasses import replace
import math,hashlib
import numpy as np

def merge(contexts):
    from dayahead.v28r2.electrical_subproblem import is_dominated_mess_current_row
    contexts=list(contexts.items());base=contexts[0][1];out=copy(base);allc=[]
    for t in range(96):
        cs=[x.coefficients[t] for _,x in contexts]
        assert all(np.array_equal(x.anchor,cs[0].anchor) and x.control_names==cs[0].control_names for x in cs)
        assert np.count_nonzero(cs[0].anchor[12:])==0
        names=[]
        for (label,_),coeff in zip(contexts,cs):
            for name in coeff.branch_names:
                if is_dominated_mess_current_row(name):names.append(name)
                else:
                    n,p=name.rsplit('::',1);names.append(n+'@'+label+'::'+p)
        fields={}
        for name in ('voltage_constant','current_constant','flow_p_constant','flow_q_constant','flow_p_matrix','flow_q_matrix'):
            fields[name]=np.concatenate([getattr(x,name) for x in cs],axis=0)
        for name in ('voltage_matrix','current_matrix'):
            fields[name]=np.concatenate([getattr(x,name) for x in cs],axis=1)
        for name in ('branch_limits','transformer_ratings'):
            fields[name]=tuple(v for x in cs for v in getattr(x,name))
        allc.append(replace(cs[0],**fields,branch_names=tuple(names),coefficient_sha256=hashlib.sha256('|'.join(x.coefficient_sha256 for x in cs).encode()).hexdigest()))
    out.coefficients=tuple(allc);out.nodes=[f'{n}@{s}' for s,x in contexts for n in x.nodes]
    out.v41r4_scenarios=dict(contexts)
    return out

def add_grid(model,coefficients,controls,objective_cap=1.):
    """Substitute all passive grid auxiliaries; no scenario decision variables."""
    import gurobipy as gp
    from dayahead.grid_lp import LINE_POLYGON_FACES,V_MIN_SQUARED,V_MAX_SQUARED
    from dayahead.v28r2.electrical_subproblem import anchored_polygon_parameters,is_dominated_mess_current_row
    rho=model.addVar(lb=0,ub=objective_cap,name='rho_max')
    counts=dict(voltage=0,line_current=0,transformer_current=0,transformer_kva=0)
    def expr(a,b,t):
        # All 48 MESS controls are identically zero, including their anchors.
        assert all(isinstance(x,(int,float)) and x==0 for x in controls[t][12:])
        nz=np.flatnonzero(b[:12]);return float(a)+gp.LinExpr([float(b[i]) for i in nz],[controls[t][i] for i in nz])
    for t,x in enumerate(coefficients):
        for j,a in enumerate(x.voltage_constant):
            v=expr(a,x.voltage_matrix[:,j],t)
            model.addConstr(v>=V_MIN_SQUARED,name=f'ROB_Vmin[{t},{j}]')
            model.addConstr(v<=V_MAX_SQUARED,name=f'ROB_Vmax[{t},{j}]');counts['voltage']+=2
        bias,corr,_=anchored_polygon_parameters(x)
        for j,name in enumerate(x.branch_names):
            if not is_dominated_mess_current_row(name):
                if name.startswith('transformer.'):
                    model.addConstr(expr(x.current_constant[j],x.current_matrix[:,j],t)<=1,name=f'ROB_TX_CURRENT[{t},{j}]');counts['transformer_current']+=1
                else:
                    ap=x.branch_limits[j]*math.cos(math.pi/LINE_POLYGON_FACES)
                    for face in range(LINE_POLYGON_FACES):
                        cos=math.cos(2*math.pi*face/LINE_POLYGON_FACES);sin=math.sin(2*math.pi*face/LINE_POLYGON_FACES)
                        a=(cos*x.flow_p_constant[j]+sin*x.flow_q_constant[j])/ap+bias[j]-corr[:,j]@x.anchor
                        b=(cos*x.flow_p_matrix[j]+sin*x.flow_q_matrix[j])/ap+corr[:,j]
                        model.addConstr(expr(a,b,t)<=rho,name=f'ROB_P1[{t},{j},{face}]');counts['line_current']+=1
            rating=x.transformer_ratings[j]
            if rating is not None:
                for face in range(LINE_POLYGON_FACES):
                    cos=math.cos(2*math.pi*face/LINE_POLYGON_FACES);sin=math.sin(2*math.pi*face/LINE_POLYGON_FACES)
                    model.addConstr(expr(cos*x.flow_p_constant[j]+sin*x.flow_q_constant[j],cos*x.flow_p_matrix[j]+sin*x.flow_q_matrix[j],t)<=rating*math.cos(math.pi/LINE_POLYGON_FACES),name=f'ROB_TX_KVA[{t},{j},{face}]');counts['transformer_kva']+=1
    return rho,counts
