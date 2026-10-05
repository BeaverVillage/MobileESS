"""Integer-valid mode linking cuts; full D-W convexification implies them."""
from fractions import Fraction as F
import numpy as np
import gurobipy as gp

def coefficients(block,x):
    p=F(float(block.battery.p_limit));c=[F(0) for _ in range(96)];d=[F(0) for _ in range(96)];mode=[F(0) for _ in range(96)]
    for j,n in enumerate(block.d['names']):
        name=str(n)
        if not name.startswith(('Pch[','Pdis[','charge_mode[')):continue
        t=int(name.rsplit(',',1)[1][:-1]);v=F(float(x[j]))
        if name.startswith('Pch['):c[t]+=v
        elif name.startswith('Pdis['):d[t]+=v
        else:mode[t]=v
    return np.array([float(c[t]-p*mode[t]) for t in range(96)]+
                    [float(d[t]+p*mode[t]-p) for t in range(96)])

def install(master,blocks,values=None):
    # Every coefficient <=0 for an exact integer local column. Therefore each
    # row sum(lambda*coefficient)<=0 follows from lambda>=0 and is redundant.
    values=values if values is not None else [coefficients(blocks[c['unit']],c['x']) for c in master.column_data]
    matrix=np.asarray(values).T;assert np.max(matrix,initial=0)<=1e-8
    rows=[]
    for i in range(192):
        nz=np.flatnonzero(matrix[i]);expr=gp.LinExpr(matrix[i,nz].tolist(),[master.lambdas[j] for j in nz])
        rows.append(master.model.addConstr(expr<=0,name=f'VALID_MODE_LINK[{i}]'))
    master.model.update()
    return rows,dict(rows_added=192,columns_added=0,nnz_added=int(np.count_nonzero(matrix)),
        maximum_column_coefficient=float(np.max(matrix,initial=0)),
        full_DW_root_bound_effect_theoretical=0.,original_integer_domain_preserved=True)

def eliminate_duals(sigma,column_coefficients):
    # For <=0 rows sigma<=0 and f(x)<=0: rc_original = rc_cut + sigma*f >= rc_cut.
    s=np.asarray(sigma);f=np.asarray(column_coefficients)
    if np.any(s>0) or np.any(f>0):raise ValueError('Exact nonpositive signs required')
    return sum((F(float(a))*F(float(b)) for a,b in zip(s,f)),F(0))
