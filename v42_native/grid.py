"""Native all-face linear grid rows recovered from V40A/V42 response authority.

Inputs are explicitly bound coefficient objects and controls in kW/kvar.
No coefficient generation, future Actual load, or implicit security margin.
"""
from dataclasses import dataclass
import math,re
import numpy as np
import gurobipy as gp
from .contracts import require
from .voltage import require_planning,Stage


@dataclass(frozen=True)
class GridAuthority:
    topology_sha:str
    mapping_sha:str
    service_sha:str
    pq_sha:str
    voltage_lower_squared:float
    voltage_upper_squared:float
    frozen:bool=False
    stage:Stage|None=None

    def validate(self):
        require(self.frozen and all(len(s)==64 for s in (self.topology_sha,self.mapping_sha,self.service_sha,self.pq_sha)),'GRID_FREEZE_MISSING')
        require_planning(self.voltage_lower_squared,self.voltage_upper_squared,self.stage)


def add_grid(model,coefficients,controls,authority):
    authority.validate();require(len(coefficients)==len(controls)>0,'GRID_HORIZON')
    rho=model.addVar(lb=0,ub=1,name='rho_max')
    def expr(base,w,x):return float(base)+gp.quicksum(float(w[k])*x[k] for k in np.flatnonzero(w))
    dominated=lambda name:re.fullmatch(r'transformer\.mess_(?:idc|sta)\d{2}_tx::[abc]',name.lower()) is not None
    for t,(c,x) in enumerate(zip(coefficients,controls)):
        require(c.slot==t and len(x)==len(c.control_names) and len(c.coefficient_sha256)==64,'COEFFICIENT_IDENTITY')
        for n,b in enumerate(c.voltage_constant):
            v=expr(b,c.voltage_matrix[:,n],x)
            model.addConstr(v>=authority.voltage_lower_squared,name='voltage_lower')
            model.addConstr(v<=authority.voltage_upper_squared,name='voltage_upper')
        angles=2*np.pi*np.arange(16)/16;cos=np.cos(angles);sin=np.sin(angles)
        ap=np.asarray(c.branch_limits)*math.cos(math.pi/16)
        require(np.all(ap>0),'LINE_RATINGS')
        pa=c.flow_p_constant+c.flow_p_matrix@c.anchor;qa=c.flow_q_constant+c.flow_q_matrix@c.anchor
        raw=(pa[:,None]*cos+qa[:,None]*sin)/ap[:,None];active=np.argmax(raw,axis=1)
        grad=(cos[active,None]*c.flow_p_matrix+sin[active,None]*c.flow_q_matrix)/ap[:,None]
        correction=c.current_matrix.T-grad
        bias=c.current_constant+c.current_matrix.T@c.anchor-np.max(raw,axis=1)
        for k,name in enumerate(c.branch_names):
            p=expr(c.flow_p_constant[k],c.flow_p_matrix[k],x);q=expr(c.flow_q_constant[k],c.flow_q_matrix[k],x)
            if not dominated(name):
                if name.lower().startswith('transformer.'):
                    model.addConstr(expr(c.current_constant[k],c.current_matrix[:,k],x)<=1,name='transformer_current')
                else:
                    delta=expr(-correction[k]@c.anchor,correction[k],x)
                    for f in range(16):model.addConstr((cos[f]*p+sin[f]*q)/ap[k]+delta+float(bias[k])<=rho,name='line_thermal_face')
            rating=c.transformer_ratings[k]
            if rating is not None:
                require(rating>0,'TRANSFORMER_RATING')
                for f in range(16):model.addConstr(cos[f]*p+sin[f]*q<=rating*math.cos(math.pi/16),name='transformer_kVA')
    return rho
