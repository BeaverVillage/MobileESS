"""Exact, cost-gated affine grid extensions. All individual physics inherited."""
import math,re
import numpy as np
import gurobipy as gp
from v42_native.contracts import require

CANDIDATES={'M1-F0':0,'M1-F1':1,'M1-F2':2,'M1-F3':3,'M1-F4':4,'M1-FCRA':5}
def evaluate(expr,values):
    if isinstance(expr,gp.Var):return values[expr.VarName]
    if isinstance(expr,gp.LinExpr):return expr.getConstant()+sum(expr.getCoeff(i)*values[expr.getVar(i).VarName] for i in range(expr.size()))
    return float(expr)
def map_bindings(bindings,values):
    for var,expr in bindings:values[var.VarName]=evaluate(expr,values)
    return values
def expr(base,w,x):
    return float(base)+gp.quicksum(float(w[k])*x[k] for k in np.flatnonzero(w))
def response(m,name,expression,bindings,lo=-gp.GRB.INFINITY,hi=gp.GRB.INFINITY):
    v=m.addVar(lb=lo,ub=hi,name=name);m.addConstr(v==expression,name=name.split('[')[0]+'_binding')
    bindings.append((v,expression));return v
def add_compressed(m,coefficients,controls,authority,label,bindings,cost):
    authority.validate();require(len(coefficients)==len(controls)>0,'GRID_HORIZON')
    level=CANDIDATES[label];rho=m.addVar(lb=0,ub=1,name='rho_max')
    cos=np.cos(2*np.pi*np.arange(16)/16);sin=np.sin(2*np.pi*np.arange(16)/16)
    dominated=lambda n:re.fullmatch(r'transformer\.mess_(?:idc|sta)\d{2}_tx::[abc]',n.lower()) is not None
    for t,(c,x) in enumerate(zip(coefficients,controls)):
        require(c.slot==t and len(x)==len(c.control_names) and len(c.coefficient_sha256)==64,'COEFFICIENT_IDENTITY')
        # Fixed AIDC controls are floats: their terms remain exact affine constants.
        variable=np.array([not isinstance(v,(float,int,np.floating)) for v in x])
        def nnz(w):return int(np.count_nonzero(np.asarray(w)[variable]))
        def audit(family,k,old,new,enabled):
            selected=bool(enabled and new<old)
            cost.append(dict(slot=t,family=family,index=k,old_occurrences=int(old),new_occurrences=int(new),selected=selected))
            return selected
        for n,b in enumerate(c.voltage_constant):
            v=expr(b,c.voltage_matrix[:,n],x);nz=nnz(c.voltage_matrix[:,n])
            bounded=level==5
            if audit('voltage',n,2*nz,nz+1+(0 if bounded else 2),level>=4):
                v=response(m,f'response_voltage[{t},{n}]',v,bindings,authority.voltage_lower_squared if bounded else -gp.GRB.INFINITY,authority.voltage_upper_squared if bounded else gp.GRB.INFINITY)
                if bounded:continue
            m.addConstr(v>=authority.voltage_lower_squared,name='voltage_lower')
            m.addConstr(v<=authority.voltage_upper_squared,name='voltage_upper')
        ap=np.asarray(c.branch_limits)*math.cos(math.pi/16);require(np.all(ap>0),'LINE_RATINGS')
        pa=c.flow_p_constant+c.flow_p_matrix@c.anchor;qa=c.flow_q_constant+c.flow_q_matrix@c.anchor
        raw=(pa[:,None]*cos+qa[:,None]*sin)/ap[:,None];active=np.argmax(raw,axis=1)
        grad=(cos[active,None]*c.flow_p_matrix+sin[active,None]*c.flow_q_matrix)/ap[:,None]
        correction=c.current_matrix.T-grad
        bias=c.current_constant+c.current_matrix.T@c.anchor-np.max(raw,axis=1)
        for k,name in enumerate(c.branch_names):
            wp,wq=c.flow_p_matrix[k],c.flow_q_matrix[k]
            p=expr(c.flow_p_constant[k],wp,x);q=expr(c.flow_q_constant[k],wq,x)
            if not dominated(name):
                if name.lower().startswith('transformer.'):
                    # One-use current expression deliberately remains unfactored.
                    m.addConstr(expr(c.current_constant[k],c.current_matrix[:,k],x)<=1,name='transformer_current')
                    cost.append(dict(slot=t,family='transformer_current',index=k,old_occurrences=nnz(c.current_matrix[:,k]),new_occurrences=nnz(c.current_matrix[:,k])+2,selected=False))
                else:
                    delta=expr(-correction[k]@c.anchor,correction[k],x)
                    old=sum(nnz((cos[f]*wp+sin[f]*wq)/ap[k]+correction[k])+1 for f in range(16))
                    new=nnz(wp)+nnz(wq)+nnz(correction[k])+3+sum(int(cos[f]!=0)+int(sin[f]!=0)+2 for f in range(16))
                    if audit('line',k,old,new,level>=2):
                        lp=response(m,f'response_line_P[{t},{k}]',p,bindings)
                        lq=response(m,f'response_line_Q[{t},{k}]',q,bindings)
                        delta=response(m,f'response_line_correction[{t},{k}]',delta,bindings)
                    else:lp,lq=p,q
                    for f in range(16):m.addConstr((cos[f]*lp+sin[f]*lq)/ap[k]+delta+float(bias[k])<=rho,name='line_thermal_face')
            rating=c.transformer_ratings[k]
            if rating is not None:
                require(rating>0,'TRANSFORMER_RATING')
                old=sum(nnz(cos[f]*wp+sin[f]*wq) for f in range(16))
                new=nnz(wp)+nnz(wq)+2+sum(int(cos[f]!=0)+int(sin[f]!=0) for f in range(16))
                if audit('transformer_kVA',k,old,new,level>=3):
                    p=response(m,f'response_transformer_P[{t},{k}]',p,bindings)
                    q=response(m,f'response_transformer_Q[{t},{k}]',q,bindings)
                for f in range(16):m.addConstr(cos[f]*p+sin[f]*q<=rating*math.cos(math.pi/16),name='transformer_kVA')
    return rho
def compressed_grid(m,bundle,anchor,p,q,label,bindings,cost):
    require(label in CANDIDATES and label!='M1-F0','COMPRESSED_CANDIDATE')
    pp={};qq={}
    for s,t in p:
        pp[s,t]=response(m,f'injection_P[{s},{t}]',p[s,t],bindings)
        qq[s,t]=response(m,f'injection_Q[{s},{t}]',q[s,t],bindings)
    # Reuse original stage, coefficient identities, fixed-AIDC control assembly.
    import v42_bootstrap.grid as original
    old=original.add_grid
    original.add_grid=lambda model,coeff,controls,authority:add_compressed(model,coeff,controls,authority,label,bindings,cost)
    try:return original.frozen_grid(m,bundle,anchor,pp,qq)
    finally:original.add_grid=old
